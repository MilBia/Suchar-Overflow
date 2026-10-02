/**
 * Unit tests for the "ba dum tss" / dust easter egg in
 * webpack/src/js/features/badumtss.js (issue #284).
 *
 * An ES module (#468): importing it registers a `DOMContentLoaded` listener that does not fire
 * here (jsdom is past `load`), so most tests drive the exported helpers directly. The real
 * `easter_eggs.js` is imported (the reduced-motion gate + muted sound helper this egg delegates
 * to), `toast.js` is mocked. Each module lives as one instance per file, so both expose
 * `_resetForTests()` for the per-test cleanup.
 *
 * This egg is pure delight: no achievement, no slug, no network. Several tests
 * assert `globalThis.fetch` is never called.
 */
import { showToast } from '../../webpack/src/js/toast.js';
import { easterEggs, _resetForTests as resetEasterEggs } from '../../webpack/src/js/features/easter_eggs.js';
import * as badumtss from '../../webpack/src/js/features/badumtss.js';

vi.mock('../../webpack/src/js/toast.js', () => ({ showToast: vi.fn() }));

const STYLE_ID = 'ee-badumtss-style';
const IDLE_MS = 2000;
const DUST_PARTICLES = 24;

/** Feed a string one `keydown` at a time through the exported handler. */
function type(text, extra) {
    [...text].forEach((ch) => badumtss.handleKeydown({ key: ch, target: null, ...(extra ?? {}) }));
}

function overlays() {
    return [...document.body.querySelectorAll('div.ee-dust-overlay')];
}

beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    document.body.innerHTML = '';
    // innerHTML = "" drops children but not <body>'s own attributes / window flags.
    delete document.body.dataset.userIsAuthenticated;
    delete window.__baDumTssReady;
    document.head.querySelector(`#${STYLE_ID}`)?.remove();

    document.head.innerHTML = '<meta name="csrf-token" content="test-token" />';
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({}) }));
    showToast.mockClear();
    delete window.EE_AUDIO;
    delete window.matchMedia; // jsdom: absence => reducedJuice() === true

    resetEasterEggs();
    badumtss._resetForTests();
});

afterEach(() => {
    easterEggs.teardownAll();
    badumtss._resetForTests();
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe('phrase matcher — handleKeydown', () => {
    it("fires on 'suchar'", () => {
        type('suchar');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it("fires on 'badumtss'", () => {
        type('badumtss');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it("fires on 'ba dum tss' (spaces are part of the phrase)", () => {
        type('ba dum tss');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('shows the 🥁 toast with the canned text', () => {
        type('suchar');
        expect(showToast).toHaveBeenCalledWith('ba dum tss', '🥁', 'success');
    });

    it('does nothing on a partial phrase', () => {
        type('sucha');
        expect(showToast).not.toHaveBeenCalled();
    });

    it('matches a phrase typed after junk keys', () => {
        type('qwe123');
        type('suchar');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('matches when the phrase is a suffix of a longer word', () => {
        type('niesuchar');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('is case-insensitive (buffer is lower-cased)', () => {
        type('SUCHAR');
        type('Ba Dum Tss');
        expect(showToast).toHaveBeenCalledTimes(2);
    });

    it('never touches the network or the achievement system (pure delight)', () => {
        const award = vi.spyOn(easterEggs, 'award');
        type('suchar');
        type('badumtss');
        expect(globalThis.fetch).not.toHaveBeenCalled();
        expect(award).not.toHaveBeenCalled();
    });

    it('ignores keystrokes typed into a form field', () => {
        type('suchar', { target: { tagName: 'INPUT' } });
        type('suchar', { target: { tagName: 'TEXTAREA' } });
        type('suchar', { target: { tagName: 'SELECT' } });
        type('suchar', { target: { isContentEditable: true } });
        expect(showToast).not.toHaveBeenCalled();
    });

    it('ignores chords with a Ctrl / Alt / Meta modifier', () => {
        type('suchar', { ctrlKey: true });
        type('suchar', { altKey: true });
        type('suchar', { metaKey: true });
        expect(showToast).not.toHaveBeenCalled();

        // A stray Ctrl+x mid-word is dropped, not buffered — the word still lands.
        type('suc');
        type('x', { ctrlKey: true });
        type('har');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('only buffers single-character keys, not named keys', () => {
        type('sucha');
        badumtss.handleKeydown({ key: 'Shift', target: null });
        badumtss.handleKeydown({ key: 'ArrowLeft', target: null });
        type('r');
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('replays the effect on every entry (no dedupe)', () => {
        type('suchar');
        type('suchar');
        type('badumtss');
        expect(showToast).toHaveBeenCalledTimes(3);
    });
});

describe('idle buffer clear', () => {
    it('clears the buffer after the idle timeout so a split phrase does not fire', () => {
        vi.useFakeTimers();
        type('sucha');
        vi.advanceTimersByTime(IDLE_MS + 1);
        type('r');
        expect(showToast).not.toHaveBeenCalled();
    });

    it('keeps the buffer alive while typing continues within the idle window', () => {
        vi.useFakeTimers();
        type('suc');
        vi.advanceTimersByTime(IDLE_MS - 100);
        type('har');
        expect(showToast).toHaveBeenCalledTimes(1);
    });
});

describe('dustBurst', () => {
    it('full-motion path: injects keyframes and spawns drifting particles', () => {
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));

        badumtss.triggerBaDumTss();

        const overlay = overlays()[0];
        expect(overlay).toBeTruthy();
        expect(document.getElementById(STYLE_ID)).toBeTruthy();

        const motes = overlay.querySelectorAll('div');
        expect(motes).toHaveLength(DUST_PARTICLES);
        expect(motes[0].style.animationName).toBe('ee-badumtss-drift');
        expect(motes[0].style.getPropertyValue('--ee-dx')).toMatch(/vw$/);
    });

    it('reduced-motion path: toast only — no overlay, no keyframes', () => {
        // matchMedia absent => easterEggs.reducedJuice() === true
        badumtss.triggerBaDumTss();

        expect(showToast).toHaveBeenCalledTimes(1);
        expect(overlays()).toHaveLength(0);
        expect(document.getElementById(STYLE_ID)).toBeNull();
    });

    it("keeps every mote's (delay + duration) within the overlay lifetime", () => {
        // Otherwise a mote is culled mid-fall when scheduleRemoval yanks the
        // container (cf. konami: lifetime >= maxDelay + maxDuration).
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
        badumtss.triggerBaDumTss();

        const OVERLAY_LIFETIME_S = 2.2;
        const motes = [...overlays()[0].querySelectorAll('div')];
        expect(motes).toHaveLength(DUST_PARTICLES);
        for (const mote of motes) {
            const delay = parseFloat(mote.style.animationDelay);
            const duration = parseFloat(mote.style.animationDuration);
            expect(delay + duration).toBeLessThanOrEqual(OVERLAY_LIFETIME_S);
        }
    });

    it('removes the overlay after its lifetime', () => {
        vi.useFakeTimers();
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));

        badumtss.triggerBaDumTss();
        expect(overlays()).toHaveLength(1);

        vi.advanceTimersByTime(3000);
        expect(overlays()).toHaveLength(0);
    });

    it('particles carry no id and no <use> — nothing to collide on', () => {
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
        badumtss.triggerBaDumTss();

        const overlay = overlays()[0];
        expect(overlay.querySelectorAll('[id]')).toHaveLength(0);
        expect(overlay.querySelectorAll('use')).toHaveLength(0);
    });
});

describe('sound', () => {
    it('asks easterEggs to play the rimshot cue on a match', () => {
        const spy = vi.spyOn(easterEggs, 'playSound');
        type('suchar');
        expect(spy).toHaveBeenCalledWith('rimshot');
    });
});

describe('teardown / reset', () => {
    it('_resetForTests clears overlays, keyframes and the buffer', () => {
        window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
        type('suc'); // mid-phrase
        badumtss.triggerBaDumTss(); // leaves an overlay + <style>

        badumtss._resetForTests();

        expect(overlays()).toHaveLength(0);
        expect(document.getElementById(STYLE_ID)).toBeNull();

        // Buffer is empty: the remaining letters alone must not fire.
        showToast.mockClear();
        type('har');
        expect(showToast).not.toHaveBeenCalled();
    });

    it('teardownBaDumTss detaches the document keydown listener', () => {
        document.body.dataset.userIsAuthenticated = 'true';
        document.dispatchEvent(new Event('DOMContentLoaded'));
        expect(window.__baDumTssReady).toBe(true);

        badumtss.teardownBaDumTss();

        [...'suchar'].forEach((key) => {
            document.dispatchEvent(new KeyboardEvent('keydown', { key }));
        });
        expect(showToast).not.toHaveBeenCalled();
    });
});

describe('DOMContentLoaded init', () => {
    it('wires the listener for an authed body and flips __baDumTssReady', () => {
        delete window.__baDumTssReady;
        document.body.dataset.userIsAuthenticated = 'true';
        document.dispatchEvent(new Event('DOMContentLoaded'));

        expect(window.__baDumTssReady).toBe(true);

        [...'suchar'].forEach((key) => {
            document.dispatchEvent(new KeyboardEvent('keydown', { key }));
        });
        expect(showToast).toHaveBeenCalledTimes(1);
    });

    it('does not wire the listener for an anonymous body', () => {
        delete window.__baDumTssReady;
        document.body.dataset.userIsAuthenticated = 'false';
        document.dispatchEvent(new Event('DOMContentLoaded'));

        expect(window.__baDumTssReady).toBe(true);

        [...'suchar'].forEach((key) => {
            document.dispatchEvent(new KeyboardEvent('keydown', { key }));
        });
        expect(showToast).not.toHaveBeenCalled();
    });
});
