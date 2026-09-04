/* Easter egg: mash the theme toggle (10× within 5s) → "zdecyduj się 🙃" toast +
 * a hidden achievement. Issue #289, umbrella #278.
 *
 * A group-A "delight" egg built on the #282 foundation. It wires nothing global
 * of its own (only the `window.__themeSpamReady` init flag): it consumes
 * `window.easterEggs` for the deduped award + reduced-motion gate, and
 * `window.showToast` (project.js) for the toast.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER tumbleweed.js,
 * so the trigger listens on every page for a logged-in user. `window.showToast`
 * and `window.easterEggs` are read at trigger time, never at module load —
 * project.js only defines `showToast` inside its own DOMContentLoaded handler,
 * so bundle listener-registration order must not matter.
 *
 * The whole file is an IIFE so its small helpers (`STYLE_ID`, …) don't collide
 * at bundle top level with project.js / easter_eggs.js / the other group-A
 * eggs — a top-level `const` collision there is a bundle-wide SyntaxError (see
 * CLAUDE.md, and the same rule on konami.js / badumtss.js / logo_spin.js /
 * tumbleweed.js).
 *
 * Trigger: a `click` listener directly on `#theme-toggle`, NOT a
 * MutationObserver on `data-theme` — project.js sets `data-theme` on every
 * page load (`setTheme(currentTheme)` unconditionally), which would be a
 * built-in false positive for an attribute observer. `#theme-toggle` is a
 * plain `<button>` (no navigation, unlike logo_spin.js's `<a>`), so the click
 * buffer lives in memory like konami's key buffer, not sessionStorage.
 *
 * Effect on every fresh burst of 10 clicks within 5s (per #289 — it replays,
 * like the other group-A eggs, not one-shot):
 *   - a "Zdecyduj się 🙃" toast;
 *   - the hidden `frontend-ee-niezdecydowany` achievement (POSTed once per
 *     session by `window.easterEggs.award`, which dedupes via sessionStorage);
 *   - full motion: a quick 360° spin of the toggle button itself;
 *   - prefers-reduced-motion: the toast + achievement only, no spin.
 *
 * This egg NEVER calls `setTheme` / writes `localStorage.theme` / the theme
 * cookie — it only counts clicks on a button project.js's own listener
 * already handles, so the theme always ends in whatever state the user's last
 * click left it in (#289's "bez psucia preferencji").
 */

(function () {
    'use strict';

    const SLUG = 'frontend-ee-niezdecydowany';

    const TOGGLE_SELECTOR = '#theme-toggle';
    // 10 clicks within a 5s sliding window.
    const THRESHOLD = 10;
    const WINDOW_MS = 5000;

    const STYLE_ID = 'ee-theme-spam-style';
    const SPIN_CLASS = 'ee-toggle-spin';
    // Keep in sync with the `600ms` literal in SPIN_CSS; the class is stripped a
    // hair later so the animation is never cut short.
    const SPIN_MS = 600;
    const SPIN_CLEAR_MS = SPIN_MS + 80;

    // One `@keyframes` turn + the class rule that drives it. Injected once as a
    // <style> element — CSP `style-src` allows 'unsafe-inline' (see
    // config/settings/base.py). The nested media query is defence in depth: the
    // JS reduced-motion gate already skips this branch, but if the class is
    // ever added anyway the animation still collapses to nothing.
    const SPIN_CSS =
        '@keyframes ee-toggle-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}'
        + '.ee-toggle-spin{animation:ee-toggle-spin 600ms ease-in-out}'
        + '@media (prefers-reduced-motion: reduce){.ee-toggle-spin{animation:none}}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    // A sliding window of the last THRESHOLD click timestamps. Stale entries
    // fall out on their own (no idle timer needed, unlike badumtss's typed
    // buffer): pushing past THRESHOLD just shifts the oldest one off.
    let clickTimestamps = [];
    let clickHandler = null;
    let boundToggle = null;
    const activeTimers = new Set();

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = SPIN_CSS;
        document.head.appendChild(style);
    }

    function spinToggle(toggle) {
        ensureKeyframes();
        toggle.classList.add(SPIN_CLASS);

        const id = setTimeout(() => {
            activeTimers.delete(id);
            toggle.classList.remove(SPIN_CLASS);
        }, SPIN_CLEAR_MS);
        activeTimers.add(id);
    }

    function showNiezdecydowanyToast() {
        if (typeof window.showToast !== 'function') return;
        window.showToast('Zdecyduj się 🙃', 'Niezdecydowany', 'info');
    }

    function triggerThemeSpam() {
        const ee = window.easterEggs;

        if (ee && typeof ee.award === 'function') {
            ee.award(SLUG);
        }

        showNiezdecydowanyToast();

        const reduced = !!(ee && typeof ee.reducedJuice === 'function' && ee.reducedJuice());
        if (reduced) return;

        const toggle = document.querySelector(TOGGLE_SELECTOR);
        if (toggle) spinToggle(toggle);
    }

    // Push the click into the sliding window and fire when THRESHOLD clicks all
    // fall within WINDOW_MS of each other. Deliberately does not read/write
    // `data-theme` or `localStorage.theme` — project.js's own listener already
    // owns the actual toggle, so the theme is never touched here.
    function handleToggleClick() {
        const now = Date.now();
        clickTimestamps.push(now);
        if (clickTimestamps.length > THRESHOLD) {
            clickTimestamps.shift();
        }

        // `delta >= 0` guards against a system clock wound backward (NTP/DST)
        // mid-burst: without it a negative delta still satisfies `<= WINDOW_MS`
        // and a stale, far-apart click would wrongly look like it's inside the
        // window (same class of guard as tumbleweed.js rejecting a future
        // stored timestamp).
        const delta = now - clickTimestamps[0];
        if (clickTimestamps.length === THRESHOLD && delta >= 0 && delta <= WINDOW_MS) {
            clickTimestamps = [];
            triggerThemeSpam();
        }
    }

    function teardownThemeSpam() {
        if (clickHandler && boundToggle) {
            boundToggle.removeEventListener('click', clickHandler);
        }
        clickHandler = null;
        boundToggle = null;
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        document.querySelectorAll(`.${SPIN_CLASS}`).forEach((el) => {
            el.classList.remove(SPIN_CLASS);
        });
        clickTimestamps = [];
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            if (document.body.dataset.userIsAuthenticated !== 'true') return;

            const toggle = document.querySelector(TOGGLE_SELECTOR);
            if (toggle) {
                clickHandler = handleToggleClick;
                boundToggle = toggle;
                toggle.addEventListener('click', clickHandler);
            }

            const ee = window.easterEggs;
            if (ee && typeof ee.registerTeardown === 'function') {
                ee.registerTeardown('themeSpam', teardownThemeSpam);
            }
        } finally {
            // Init-complete signal, mirroring window.__konamiReady /
            // window.__logoSpinReady. The E2E test waits on it before clicking
            // (page `load` isn't synced with bundle execution).
            window.__themeSpamReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/theme_spam.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in konami.js /
     * badumtss.js / logo_spin.js / tumbleweed.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the click buffer, the bound listener, the spin
     * timers) survives between tests. `_resetForTests()` is the per-test reset
     * the `beforeEach` in tests/js/theme_spam.test.js must call; it is attached
     * here only, so it never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            THRESHOLD,
            WINDOW_MS,
            handleToggleClick,
            triggerThemeSpam,
            spinToggle,
            showNiezdecydowanyToast,
            teardownThemeSpam,
            _resetForTests: teardownThemeSpam,
        };
    }
})();
