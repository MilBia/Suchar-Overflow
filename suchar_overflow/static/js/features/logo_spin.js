/* Easter egg: mash the navbar logo 7× in quick succession → a short logo spin
 * and a toast with a random "meta-suchar" about dryness / the site. Issue #285,
 * umbrella #278.
 *
 * A group-A "delight" egg built on the #282 foundation. It wires nothing global
 * of its own (only the `window.__logoSpinReady` init flag): it consumes
 * `window.easterEggs` for the reduced-motion gate and `window.showToast`
 * (project.js) for the toast.
 *
 * Unlike konami.js / badumtss.js, whose trigger is a keydown long after load,
 * this egg's effect can fire from `checkAndFire()` INSIDE its own
 * `DOMContentLoaded` handler (see below), i.e. before any later keystroke. That
 * call reaches `window.showToast`, which project.js only defines inside its own
 * `DOMContentLoaded` handler — so this DOES depend on project.js being listed
 * first in base.html's `{% compress js %}` block, so that its handler (and thus
 * `showToast`) is registered, and runs, before this file's. `showToast` /
 * `easterEggs` are still looked up at call time, never captured at module load,
 * so a missing helper degrades gracefully rather than throwing.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER badumtss.js
 * (and, as above, after project.js).
 * The whole file is an IIFE so its small helpers (`rand`, `STYLE_ID`, …) don't
 * collide at bundle top level with project.js / easter_eggs.js / konami.js /
 * badumtss.js — a top-level `const` clash there is a bundle-wide SyntaxError
 * (see CLAUDE.md, and the same rule on konami.js / badumtss.js).
 *
 * Trigger model — WHY sessionStorage and not an in-memory counter: the logo is
 * `<a href="{% url 'home' %}">` and #285 requires the click to still navigate
 * home, so every click reloads the page and no in-memory state survives.
 * `handleLogoClick` therefore records a "chain" in sessionStorage — each click
 * within 3 s of the previous one bumps `count` — and `checkAndFire`, run once
 * per page load, fires the effect when `count` has reached the threshold while
 * the chain is still fresh, then clears it. It replays on every fresh burst of
 * 7 (deliberately not one-shot, like konami / badumtss).
 *
 * Pure delight: NO achievement, NO frontend-ee- slug, NO network. It consumes
 * only `easterEggs.reducedJuice()` and `window.showToast`. The meta-suchar pool
 * is a JSON data island (`#ee-logo-suchary`) emitted by base.html for
 * authenticated users — deliberately NOT inside `{% compress js %}` (#285), so
 * its translated text is not minified into the bundle.
 */

(function () {
    'use strict';

    // sessionStorage key for the click chain: `{ count, last }`.
    const STORAGE_KEY = 'ee_logo_clicks';
    // Max gap between two clicks that still counts as the same chain.
    const CHAIN_MS = 3000;
    // Clicks needed, within one unbroken chain, to fire the effect.
    const CLICK_THRESHOLD = 7;

    const LOGO_SELECTOR = '.navbar-brand';
    const POOL_ELEMENT_ID = 'ee-logo-suchary';

    const STYLE_ID = 'ee-logo-spin-style';
    const SPIN_CLASS = 'ee-logo-spin';
    // Keep in sync with the `600ms` literal in SPIN_CSS; the class is stripped a
    // hair later so the animation is never cut short.
    const SPIN_MS = 600;
    const SPIN_CLEAR_MS = SPIN_MS + 80;

    // One `@keyframes` turn + the class rule that drives it. Injected once as a
    // <style> element — CSP `style-src` allows 'unsafe-inline' (see
    // config/settings/base.py). The nested media query is defence in depth: the
    // JS reduced-motion gate already skips this branch, but if the class is ever
    // added anyway the animation still collapses to nothing.
    const SPIN_CSS =
        '@keyframes ee-logo-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}'
        + '.ee-logo-spin{animation:ee-logo-spin 600ms ease-in-out}'
        + '@media (prefers-reduced-motion: reduce){.ee-logo-spin{animation:none}}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    let clickHandler = null;
    let boundLogo = null;
    const activeTimers = new Set();

    // Reduced-motion gate. Delegates to the #282 foundation's single check, with
    // a direct-media-query fallback if easter_eggs.js failed to load — a user
    // who asked for reduced motion must not get the spin just because the
    // foundation is missing. Mirrors `easterEggs.reducedJuice()` (reduced when
    // asked, or when the environment can't tell us).
    function prefersReducedMotion() {
        const ee = window.easterEggs;
        if (ee && typeof ee.reducedJuice === 'function') return ee.reducedJuice();
        try {
            if (typeof window.matchMedia !== 'function') return true;
            return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        } catch {
            return true;
        }
    }

    // ── Click-chain persistence ────────────────────────────────────────────────

    function readState() {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            if (!raw) return { count: 0, last: 0 };
            const parsed = JSON.parse(raw);
            if (
                !parsed
                || typeof parsed.count !== 'number'
                || typeof parsed.last !== 'number'
            ) {
                return { count: 0, last: 0 };
            }
            return { count: parsed.count, last: parsed.last };
        } catch {
            return { count: 0, last: 0 };
        }
    }

    function writeState(state) {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch {
            // Storage unavailable — the egg just won't trigger this session.
        }
    }

    function clearState() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch {
            // Nothing to do.
        }
    }

    // Record one logo click. Ignores non-primary buttons and any chord with a
    // Ctrl/Alt/Meta/Shift modifier (open-in-new-tab / OS shortcuts), which
    // otherwise navigate elsewhere or not at all and shouldn't feed the chain.
    // Never fires the effect: the 7th click navigates home, so `checkAndFire`
    // on the next load is what actually triggers it.
    function handleLogoClick(e) {
        if (e && (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey)) return;
        if (e && typeof e.button === 'number' && e.button !== 0) return;

        const now = Date.now();
        const { count, last } = readState();
        const chained = last > 0 && now - last < CHAIN_MS;
        const next = chained ? Math.min(count + 1, CLICK_THRESHOLD) : 1;
        writeState({ count: next, last: now });
    }

    // Run once per page load. Fires the effect if the chain reached the
    // threshold and its last click is still within CHAIN_MS (so mashing the
    // logo, then wandering off and navigating minutes later, does not trigger
    // it). Clears a fired or stale chain; leaves a still-building one alone.
    function checkAndFire() {
        const { count, last } = readState();
        if (last === 0) return false;

        const now = Date.now();
        if (now - last >= CHAIN_MS) {
            clearState();
            return false;
        }
        if (count >= CLICK_THRESHOLD) {
            clearState();
            triggerLogoSpin();
            return true;
        }
        return false;
    }

    // ── Effect ────────────────────────────────────────────────────────────────

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = SPIN_CSS;
        document.head.appendChild(style);
    }

    function spinLogo() {
        const logo = document.querySelector(LOGO_SELECTOR);
        if (!logo) return;

        ensureKeyframes();
        logo.classList.add(SPIN_CLASS);

        const id = setTimeout(() => {
            activeTimers.delete(id);
            logo.classList.remove(SPIN_CLASS);
        }, SPIN_CLEAR_MS);
        activeTimers.add(id);
    }

    // Random entry from the JSON data island, or null when it is absent /
    // empty / unparseable (the spin still runs; only the toast is skipped).
    function pickMetaSuchar() {
        const el = document.getElementById(POOL_ELEMENT_ID);
        if (!el) return null;
        try {
            const pool = JSON.parse(el.textContent);
            if (!Array.isArray(pool) || pool.length === 0) return null;
            return pool[Math.floor(Math.random() * pool.length)];
        } catch {
            return null;
        }
    }

    function triggerLogoSpin() {
        const text = pickMetaSuchar();
        if (text && typeof window.showToast === 'function') {
            window.showToast(text, '🌀', 'info');
        }
        if (!prefersReducedMotion()) spinLogo();
    }

    function teardownLogoSpin() {
        if (clickHandler && boundLogo) {
            boundLogo.removeEventListener('click', clickHandler);
        }
        clickHandler = null;
        boundLogo = null;
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        document.querySelectorAll(`.${SPIN_CLASS}`).forEach((el) => {
            el.classList.remove(SPIN_CLASS);
        });
        clearState();
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            if (document.body.dataset.userIsAuthenticated !== 'true') return;

            const logo = document.querySelector(LOGO_SELECTOR);
            if (logo) {
                clickHandler = handleLogoClick;
                boundLogo = logo;
                // Not preventDefault: the click must still navigate home (#285).
                logo.addEventListener('click', clickHandler);
            }

            checkAndFire();

            const ee = window.easterEggs;
            if (ee && typeof ee.registerTeardown === 'function') {
                ee.registerTeardown('logoSpin', teardownLogoSpin);
            }
        } finally {
            // Init-complete signal, mirroring window.__konamiReady /
            // window.__baDumTssReady. The E2E test waits on it before clicking
            // (page `load` isn't synced with bundle execution).
            window.__logoSpinReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/logo_spin.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in konami.js /
     * badumtss.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the bound click listener, the spin timers)
     * survives between tests. `_resetForTests()` is the per-test reset the
     * `beforeEach` must call; it is attached here only, so it never reaches a
     * real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            STORAGE_KEY,
            CHAIN_MS,
            CLICK_THRESHOLD,
            handleLogoClick,
            checkAndFire,
            triggerLogoSpin,
            spinLogo,
            pickMetaSuchar,
            teardownLogoSpin,
            _resetForTests: teardownLogoSpin,
        };
    }
})();
