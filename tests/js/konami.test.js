/**
 * Unit tests for the Konami-code easter egg in
 * webpack/src/js/features/konami.js (issue #283).
 *
 * An ES module (#468): importing it registers a `DOMContentLoaded` listener that does not fire
 * here (jsdom is past `load`), so most tests drive the exported helpers directly. The real
 * `easter_eggs.js` is imported (the deduped award + reduced-motion gate this egg delegates to),
 * `toast.js` is mocked. Each module lives as one instance per file, so both expose
 * `_resetForTests()` for the per-test cleanup.
 */
import { showToast } from '../../webpack/src/js/toast.js';
import { easterEggs, _resetForTests as resetEasterEggs } from '../../webpack/src/js/features/easter_eggs.js';
import * as konami from '../../webpack/src/js/features/konami.js';

vi.mock('../../webpack/src/js/toast.js', () => ({ showToast: vi.fn() }));

const KONAMI_SEQUENCE = [
    'ArrowUp',
    'ArrowUp',
    'ArrowDown',
    'ArrowDown',
    'ArrowLeft',
    'ArrowRight',
    'ArrowLeft',
    'ArrowRight',
    'b',
    'a',
];

const STYLE_ID = 'ee-konami-style';
const RAIN_PARTICLES = 42;
const STATIC_PARTICLES = 16;

function feed(keys, extra) {
    keys.forEach((key) => konami.handleKeydown({ key, target: null, ...(extra ?? {}) }));
}

function frontendEventPosts() {
    return globalThis.fetch.mock.calls.filter(([url]) => url === '/api/achievements/frontend-event');
}

function rainContainers() {
    return [...document.body.querySelectorAll("div[aria-hidden='true']")];
}

beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    document.body.innerHTML = '';
    document.head.querySelector(`#${STYLE_ID}`)?.remove();

    document.head.innerHTML = '<meta name="csrf-token" content="test-token" />';
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({}) }));
    showToast.mockClear();
    delete window.EE_AUDIO;
    delete window.matchMedia; // jsdom: absence => reducedJuice() === true

    resetEasterEggs();
    konami._resetForTests();
});

afterEach(() => {
    easterEggs.teardownAll();
    konami._resetForTests();
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe('sequence matcher — handleKeydown', () => {
    it('fires once on the full correct sequence', () => {
        feed(KONAMI_SEQUENCE);

        expect(showToast).toHaveBeenCalledTimes(1);
        expect(frontendEventPosts()).toHaveLength(1);
        expect(JSON.parse(frontendEventPosts()[0][1].body)).toEqual({
            event_slug: 'frontend-ee-konami',
        });
    });

    it('does nothing on a partial sequence', () => {
        feed(KONAMI_SEQUENCE.slice(0, 9));

        expect(showToast).not.toHaveBeenCalled();
        expect(frontendEventPosts()).toHaveLength(0);
    });

    it('a mistyped key does not block a subsequent clean run', () => {
        feed(['ArrowUp', 'ArrowUp', 'KeyX']);
        feed(KONAMI_SEQUENCE);

        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('tolerates junk keys before the real sequence', () => {
        feed(['ArrowDown', 'Enter', ' ']);
        feed(KONAMI_SEQUENCE);

        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('fires with an odd-length ArrowUp prefix (sliding window, not a rolling index)', () => {
        // A hand-rolled state machine desyncs here: 3rd ArrowUp mismatches index 2,
        // the "restart from key 0" fallback lands on index 1, and the following
        // ArrowDown then fails against ArrowUp — the code never completes.
        feed(['ArrowUp', 'ArrowUp', 'ArrowUp', ...KONAMI_SEQUENCE.slice(2)]);

        expect(showToast).toHaveBeenCalledTimes(1);
        expect(frontendEventPosts()).toHaveLength(1);
    });

    it('accepts uppercase B and A (case-insensitive)', () => {
        feed([...KONAMI_SEQUENCE.slice(0, 8), 'B', 'A']);

        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('ignores keystrokes typed into a form field', () => {
        feed(KONAMI_SEQUENCE, { target: { tagName: 'INPUT' } });
        feed(KONAMI_SEQUENCE, { target: { tagName: 'TEXTAREA' } });
        feed(KONAMI_SEQUENCE, { target: { isContentEditable: true } });

        expect(showToast).not.toHaveBeenCalled();
        expect(frontendEventPosts()).toHaveLength(0);
    });

    it('ignores chords with a Ctrl / Alt / Meta modifier', () => {
        feed(KONAMI_SEQUENCE, { ctrlKey: true });
        feed(KONAMI_SEQUENCE, { altKey: true });
        feed(KONAMI_SEQUENCE, { metaKey: true });

        expect(showToast).not.toHaveBeenCalled();

        // A stray Ctrl+A mid-attempt is dropped, not buffered — so the real
        // sequence around it still completes.
        feed(KONAMI_SEQUENCE.slice(0, 5));
        feed(['a'], { ctrlKey: true });
        feed(KONAMI_SEQUENCE.slice(5));
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('replays the effect every entry but POSTs the award only once', () => {
        feed(KONAMI_SEQUENCE);
        feed(KONAMI_SEQUENCE);

        expect(showToast).toHaveBeenCalledTimes(2);
        expect(rainContainers()).toHaveLength(2);
        expect(frontendEventPosts()).toHaveLength(1); // sessionStorage dedupe
    });
});

describe('crackerBurst', () => {
    it('full-motion path: injects keyframes and spawns falling particles', () => {
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));

        konami.triggerKonami();

        const container = rainContainers()[0];
        expect(container).toBeTruthy();
        expect(document.getElementById(STYLE_ID)).toBeTruthy();

        const spans = container.querySelectorAll('span');
        expect(spans).toHaveLength(RAIN_PARTICLES);
        expect(spans[0].style.animationName).toBe('ee-konami-fall');
        expect(spans[0].style.getPropertyValue('--ee-dx')).toMatch(/vw$/);
        expect(container.querySelectorAll('svg')).toHaveLength(RAIN_PARTICLES);
    });

    it('reduced-motion path: a static scatter, no keyframes, no animation', () => {
        // matchMedia absent => easterEggs.reducedJuice() === true
        konami.triggerKonami();

        const container = rainContainers()[0];
        expect(container).toBeTruthy();
        expect(document.getElementById(STYLE_ID)).toBeNull();
        expect(container.querySelectorAll('span')).toHaveLength(0);

        const crackers = container.querySelectorAll('svg');
        expect(crackers).toHaveLength(STATIC_PARTICLES);
        expect(crackers[0].style.animationName).toBe('');
        expect(crackers[0].style.transform).toMatch(/^rotate\(/);
    });

    it('particles are original <svg> elements — no id / <use> collision', () => {
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
        konami.triggerKonami();

        const container = rainContainers()[0];
        expect(container.querySelectorAll('[id]')).toHaveLength(0);
        expect(container.querySelectorAll('use')).toHaveLength(0);
        expect(container.querySelector('rect').getAttribute('fill')).toBe('#E58E26');
    });

    it('removes the container after its timeout', () => {
        vi.useFakeTimers();
        konami.triggerKonami();
        expect(rainContainers()).toHaveLength(1);

        vi.advanceTimersByTime(5000);
        expect(rainContainers()).toHaveLength(0);
    });
});

describe('teardown / reset', () => {
    it('_resetForTests clears containers, keyframes and match position', () => {
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
        feed(KONAMI_SEQUENCE.slice(0, 4)); // mid-sequence
        konami.triggerKonami(); // leaves a container + <style>

        konami._resetForTests();

        expect(rainContainers()).toHaveLength(0);
        expect(document.getElementById(STYLE_ID)).toBeNull();

        // Position is back to 0: the remaining 6 keys alone must not fire.
        showToast.mockClear();
        feed(KONAMI_SEQUENCE.slice(4));
        expect(showToast).not.toHaveBeenCalled();
    });

    it('teardownKonami detaches the document keydown listener', () => {
        document.body.dataset.userIsAuthenticated = 'true';
        document.dispatchEvent(new Event('DOMContentLoaded'));
        expect(window.__konamiReady).toBe(true);

        konami.teardownKonami();

        KONAMI_SEQUENCE.forEach((key) => {
            document.dispatchEvent(new KeyboardEvent('keydown', { key }));
        });
        expect(showToast).not.toHaveBeenCalled();
    });
});

describe('DOMContentLoaded init', () => {
    it('wires the listener for an authed body and flips __konamiReady', () => {
        delete window.__konamiReady;
        document.body.dataset.userIsAuthenticated = 'true';
        document.dispatchEvent(new Event('DOMContentLoaded'));

        expect(window.__konamiReady).toBe(true);

        KONAMI_SEQUENCE.forEach((key) => {
            document.dispatchEvent(new KeyboardEvent('keydown', { key }));
        });
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('does not wire the listener for an anonymous body', () => {
        delete window.__konamiReady;
        document.body.dataset.userIsAuthenticated = 'false';
        document.dispatchEvent(new Event('DOMContentLoaded'));

        expect(window.__konamiReady).toBe(true);

        KONAMI_SEQUENCE.forEach((key) => {
            document.dispatchEvent(new KeyboardEvent('keydown', { key }));
        });
        expect(showToast).not.toHaveBeenCalled();
    });
});
