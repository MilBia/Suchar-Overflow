/* Easter egg: the Konami code (↑ ↑ ↓ ↓ ← → ← → B A) — issue #283, umbrella #278.
 *
 * A group-A "delight" egg built on the #282 foundation. It wires nothing global
 * of its own (only the `window.__konamiReady` init flag): it consumes
 * `window.easterEggs` for the session-deduped award and the reduced-motion gate,
 * and `window.showToast` (project.js) for the wink.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER easter_eggs.js,
 * so the trigger listens on every page for a logged-in user. `window.showToast`
 * and `window.easterEggs` are read at trigger time, never at module load —
 * project.js only defines `showToast` inside its own DOMContentLoaded handler,
 * so bundle listener-registration order must not matter.
 *
 * The whole file is an IIFE so its many small helpers (`rand`, `STYLE_ID`, …)
 * don't leak into the shared bundle scope where project.js / easter_eggs.js and
 * a future group-A egg (#284+) also live — a top-level `const` collision there
 * is a bundle-wide SyntaxError.
 *
 * Effect on every correct entry (per #283 — it replays, it is not one-shot):
 *   - full motion: a downpour of ~40 mini-crackers falling across the viewport;
 *   - prefers-reduced-motion: a single static scatter, no movement;
 *   - a "Kod Konami 😉" toast;
 *   - the hidden `frontend-ee-konami` achievement (POSTed once per session by
 *     `window.easterEggs.award`, which dedupes via sessionStorage).
 */

(function () {
    'use strict';

    const SLUG = 'frontend-ee-konami';

    const SEQUENCE = [
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

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const STYLE_ID = 'ee-konami-style';

    // `@keyframes` for the falling crackers. Injected once as a <style> element —
    // CSP `style-src` allows 'unsafe-inline' (see config/settings/base.py), which
    // covers both this block and the per-particle inline `style=` below.
    const RAIN_KEYFRAMES =
        '@keyframes ee-konami-fall{'
        + '0%{transform:translate(0,-12vh) rotate(0);opacity:0}'
        + '8%{opacity:1}'
        + '100%{transform:translate(var(--ee-dx,0),112vh) rotate(var(--ee-spin,360deg));opacity:1}'
        + '}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    // A fixed-length sliding window of the last SEQUENCE.length keys. A rolling
    // index / hand-rolled state machine mishandles the repeated prefix
    // (↑ ↑ …): an odd run of ArrowUp before the real code would desync it and
    // the egg would never fire. Comparing a bounded buffer is O(1) and immune to
    // any junk prefix or repeat.
    let keyBuffer = [];
    let keydownHandler = null;
    const activeTimers = new Set();
    const activeContainers = new Set();

    // ── Cracker particle ────────────────────────────────────────────────────────
    // A compact original cracker (the inner shape of svgs/icon-cracker-stack.svg
    // — one rounded rect + three seed dots), built element-by-element. NOT a
    // clone of that file: its body is a `<defs><g id>` + `<use href="#...">`, so
    // 40 copies in the document would collide on the id and every `<use>` would
    // resolve the first.
    function makeCrackerEl() {
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('width', '24');
        svg.setAttribute('height', '8');
        svg.setAttribute('viewBox', '0 0 70 22');
        svg.setAttribute('aria-hidden', 'true');

        const rect = document.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('width', '70');
        rect.setAttribute('height', '22');
        rect.setAttribute('rx', '4');
        rect.setAttribute('fill', '#E58E26');
        svg.appendChild(rect);

        [15, 35, 55].forEach((cx) => {
            const dot = document.createElementNS(SVG_NS, 'circle');
            dot.setAttribute('cx', String(cx));
            dot.setAttribute('cy', '11');
            dot.setAttribute('r', '2.5');
            dot.setAttribute('fill', '#F3E5AB');
            svg.appendChild(dot);
        });

        return svg;
    }

    function rand(min, max) {
        return min + Math.random() * (max - min);
    }

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = RAIN_KEYFRAMES;
        document.head.appendChild(style);
    }

    function makeContainer() {
        const container = document.createElement('div');
        container.setAttribute('aria-hidden', 'true');
        // Set property-by-property (not `cssText`): jsdom's CSSOM silently drops
        // custom properties and some shorthands set through `cssText`, and the
        // per-particle styles below rely on `--ee-dx` / `--ee-spin`.
        container.style.position = 'fixed';
        container.style.inset = '0';
        container.style.pointerEvents = 'none';
        container.style.overflow = 'hidden';
        container.style.zIndex = '2147483000';
        return container;
    }

    function scheduleRemoval(container, ms) {
        const id = setTimeout(() => {
            activeTimers.delete(id);
            activeContainers.delete(container);
            container.remove();
        }, ms);
        activeTimers.add(id);
    }

    // Render the crackers. `reduced` → a motion-free static scatter that just
    // appears and is cleared; otherwise the full falling downpour.
    function crackerBurst(reduced) {
        const container = makeContainer();
        document.body.appendChild(container);
        activeContainers.add(container);

        if (reduced) {
            for (let i = 0; i < 16; i += 1) {
                const cracker = makeCrackerEl();
                cracker.style.position = 'absolute';
                cracker.style.left = `${rand(8, 88)}%`;
                cracker.style.top = `${rand(12, 82)}%`;
                cracker.style.transform = `rotate(${rand(-40, 40)}deg)`;
                container.appendChild(cracker);
            }
            scheduleRemoval(container, 1100);
            return;
        }

        ensureKeyframes();
        for (let i = 0; i < 42; i += 1) {
            const span = document.createElement('span');
            span.style.position = 'absolute';
            span.style.top = '0';
            span.style.left = `${rand(-2, 98)}%`;
            span.style.setProperty('--ee-dx', `${rand(-12, 12).toFixed(1)}vw`);
            span.style.setProperty('--ee-spin', `${rand(-540, 540).toFixed(0)}deg`);
            span.style.animationName = 'ee-konami-fall';
            span.style.animationDuration = `${rand(1.7, 3.3).toFixed(2)}s`;
            span.style.animationTimingFunction = 'linear';
            span.style.animationDelay = `${rand(0, 0.9).toFixed(2)}s`;
            span.style.animationFillMode = 'both';
            span.appendChild(makeCrackerEl());
            container.appendChild(span);
        }
        scheduleRemoval(container, 4500);
    }

    function showKonamiToast() {
        if (typeof window.showToast !== 'function') return;
        window.showToast(
            'Góra, góra, dół, dół… nieźle! 😉',
            'Kod Konami',
            'success',
        );
    }

    function triggerKonami() {
        const ee = window.easterEggs;

        if (ee && typeof ee.award === 'function') {
            ee.award(SLUG);
        }

        showKonamiToast();

        const reduced = !!(ee && typeof ee.reducedJuice === 'function' && ee.reducedJuice());
        crackerBurst(reduced);
    }

    // Push the key into the sliding window and fire when it equals SEQUENCE.
    // Ignores keystrokes typed into a form field (so the arrows + "ba" can't be
    // swallowed mid-edit, nor fired from one) and any chord with a
    // Ctrl/Alt/Meta modifier (browser/OS shortcuts such as Ctrl+A, Alt+←).
    function handleKeydown(e) {
        if (e.ctrlKey || e.altKey || e.metaKey) return;

        const target = e.target;
        if (
            target
            && (target.tagName === 'INPUT'
                || target.tagName === 'TEXTAREA'
                || target.tagName === 'SELECT'
                || target.isContentEditable)
        ) {
            return;
        }

        const key = typeof e.key === 'string' && e.key.length === 1
            ? e.key.toLowerCase()
            : e.key;

        keyBuffer.push(key);
        if (keyBuffer.length > SEQUENCE.length) {
            keyBuffer.shift();
        }

        if (
            keyBuffer.length === SEQUENCE.length
            && keyBuffer.every((k, i) => k === SEQUENCE[i])
        ) {
            keyBuffer = [];
            triggerKonami();
        }
    }

    function teardownKonami() {
        if (keydownHandler) {
            document.removeEventListener('keydown', keydownHandler);
            keydownHandler = null;
        }
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        activeContainers.forEach((el) => el.remove());
        activeContainers.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        keyBuffer = [];
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            if (document.body.dataset.userIsAuthenticated !== 'true') return;

            keydownHandler = handleKeydown;
            document.addEventListener('keydown', keydownHandler);

            const ee = window.easterEggs;
            if (ee && typeof ee.registerTeardown === 'function') {
                ee.registerTeardown('konami', teardownKonami);
            }
        } finally {
            // Init-complete signal, mirroring window.__easterEggsReady /
            // window.__hiddenAchievementsReady. The E2E test waits on it before
            // dispatching keys (page `load` isn't synced with bundle execution).
            window.__konamiReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/konami.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in easter_eggs.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the key buffer, timers, containers, the keydown
     * listener) survives between tests. `_resetForTests()` is the per-test reset
     * the `beforeEach` in tests/js/konami.test.js must call; it is attached here
     * only, so it never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            SEQUENCE,
            handleKeydown,
            triggerKonami,
            crackerBurst,
            showKonamiToast,
            teardownKonami,
            _resetForTests: teardownKonami,
        };
    }
})();
