/* Easter egg: type "suchar" / "badumtss" / "ba dum tss" → 🥁 toast + a puff of
 * settling dust. Issue #284, umbrella #278.
 *
 * A group-A "delight" egg built on the #282 foundation. It wires nothing global
 * of its own (only the `window.__baDumTssReady` init flag): it consumes
 * `window.easterEggs` for the reduced-motion gate and the muted-by-default sound
 * helper, and `window.showToast` (project.js) for the toast.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER konami.js, so
 * the trigger listens on every page for a logged-in user. `window.showToast`
 * and `window.easterEggs` are read at trigger time, never at module load —
 * project.js only defines `showToast` inside its own DOMContentLoaded handler,
 * so bundle listener-registration order must not matter.
 *
 * The whole file is an IIFE so its many small helpers (`rand`, `STYLE_ID`, …)
 * don't leak into the shared bundle scope where project.js / easter_eggs.js /
 * konami.js also live — a top-level `const` collision there is a bundle-wide
 * SyntaxError (see CLAUDE.md, and the same rule on konami.js).
 *
 * Pure delight: NO achievement, NO frontend-ee- slug, NO network. The effect
 * replays on every entry (like konami, deliberately not one-shot):
 *   - full motion: ~24 dust motes drifting down across the viewport, ~2 s;
 *   - prefers-reduced-motion: the toast only, no overlay at all;
 *   - a "🥁 / ba dum tss" toast;
 *   - the rimshot cue via `window.easterEggs.playSound` (muted unless opted in).
 */

(function () {
    'use strict';

    // Literal suffixes to match against the tail of the typed-key buffer. Spaces
    // are ordinary single-character keys, so "ba dum tss" is matched verbatim.
    const PHRASES = ['suchar', 'badumtss', 'ba dum tss'];
    const LONGEST_PHRASE = PHRASES.reduce((n, p) => Math.max(n, p.length), 0);

    // Idle timeout after which a half-typed phrase is forgotten, so "sucha" now
    // and "r" a minute later don't combine into a hit.
    const IDLE_MS = 2000;

    const STYLE_ID = 'ee-badumtss-style';
    const OVERLAY_CLASS = 'ee-dust-overlay';
    const DUST_PARTICLES = 24;
    // Per-mote animation bounds. The overlay must outlive the last mote or motes
    // vanish mid-fall (cf. konami: lifetime ≥ maxDelay + maxDuration), so keep
    // `MOTE_MAX_DELAY_S + MOTE_MAX_DURATION_S <= OVERLAY_LIFETIME_MS / 1000`.
    const MOTE_MIN_DURATION_S = 1.2;
    const MOTE_MAX_DURATION_S = 1.7;
    const MOTE_MAX_DELAY_S = 0.4;
    const OVERLAY_LIFETIME_MS = 2200;

    // `@keyframes` for the drifting motes. Injected once as a <style> element —
    // CSP `style-src` allows 'unsafe-inline' (see config/settings/base.py),
    // which covers both this block and the per-particle inline `style=` below.
    const DRIFT_KEYFRAMES =
        '@keyframes ee-badumtss-drift{'
        + '0%{transform:translate(0,-8vh) scale(0.5);opacity:0}'
        + '15%{opacity:0.75}'
        + '100%{transform:translate(var(--ee-dx,0),108vh) scale(1);opacity:0}'
        + '}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    // A bounded string of the last few typed characters. Comparing its tail with
    // each phrase is O(1) and immune to any junk or repeated prefix.
    let charBuffer = '';
    let idleTimer = null;
    let keydownHandler = null;
    const activeTimers = new Set();
    const activeOverlays = new Set();

    function rand(min, max) {
        return min + Math.random() * (max - min);
    }

    function clearBuffer() {
        charBuffer = '';
        if (idleTimer !== null) {
            clearTimeout(idleTimer);
            idleTimer = null;
        }
    }

    function armIdleClear() {
        if (idleTimer !== null) clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
            idleTimer = null;
            charBuffer = '';
        }, IDLE_MS);
    }

    // ── Dust overlay ────────────────────────────────────────────────────────────

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = DRIFT_KEYFRAMES;
        document.head.appendChild(style);
    }

    function makeOverlay() {
        const overlay = document.createElement('div');
        overlay.className = OVERLAY_CLASS;
        overlay.setAttribute('aria-hidden', 'true');
        // Set property-by-property (not `cssText`): jsdom's CSSOM silently drops
        // custom properties and some shorthands set through `cssText`, and the
        // per-particle styles below rely on `--ee-dx`.
        overlay.style.position = 'fixed';
        overlay.style.inset = '0';
        overlay.style.pointerEvents = 'none';
        overlay.style.overflow = 'hidden';
        overlay.style.zIndex = '2147483000';
        return overlay;
    }

    function makeMote() {
        const mote = document.createElement('div');
        const size = rand(4, 10).toFixed(1);
        mote.style.position = 'absolute';
        mote.style.top = '0';
        mote.style.left = `${rand(-2, 98).toFixed(1)}%`;
        mote.style.width = `${size}px`;
        mote.style.height = `${size}px`;
        mote.style.borderRadius = '50%';
        // Warm mid-grey at high alpha + a soft glow so the motes read as dust on
        // both the light and dark themes (konami's crackers are opaque for the
        // same reason). Deliberately not theme-aware — one calm tone for both.
        mote.style.background = 'rgba(146, 128, 104, 0.85)';
        mote.style.boxShadow = '0 0 3px rgba(120, 104, 82, 0.7)';
        mote.style.setProperty('--ee-dx', `${rand(-10, 10).toFixed(1)}vw`);
        mote.style.animationName = 'ee-badumtss-drift';
        mote.style.animationDuration =
            `${rand(MOTE_MIN_DURATION_S, MOTE_MAX_DURATION_S).toFixed(2)}s`;
        mote.style.animationTimingFunction = 'ease-in';
        mote.style.animationDelay = `${rand(0, MOTE_MAX_DELAY_S).toFixed(2)}s`;
        mote.style.animationFillMode = 'both';
        return mote;
    }

    function scheduleRemoval(overlay, ms) {
        const id = setTimeout(() => {
            activeTimers.delete(id);
            activeOverlays.delete(overlay);
            overlay.remove();
        }, ms);
        activeTimers.add(id);
    }

    // Full-motion only — the reduced-motion branch never calls this.
    function dustBurst() {
        ensureKeyframes();
        const overlay = makeOverlay();
        for (let i = 0; i < DUST_PARTICLES; i += 1) {
            overlay.appendChild(makeMote());
        }
        document.body.appendChild(overlay);
        activeOverlays.add(overlay);
        scheduleRemoval(overlay, OVERLAY_LIFETIME_MS);
    }

    function showBaDumTssToast() {
        if (typeof window.showToast !== 'function') return;
        window.showToast('ba dum tss', '🥁', 'success');
    }

    function triggerBaDumTss() {
        const ee = window.easterEggs;

        showBaDumTssToast();

        if (ee && typeof ee.playSound === 'function') {
            ee.playSound('rimshot');
        }

        const reduced = !!(ee && typeof ee.reducedJuice === 'function' && ee.reducedJuice());
        if (!reduced) dustBurst();
    }

    // Push the key into the bounded buffer and fire when its tail matches a
    // phrase. Ignores keystrokes typed into a form field (so a phrase can't be
    // swallowed mid-edit, nor fired from one) and any chord with a Ctrl/Alt/Meta
    // modifier (browser/OS shortcuts such as Ctrl+A, Alt+←).
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

        // Only printable single-character keys extend the buffer; "Shift",
        // "ArrowLeft", "Enter" etc. are inert (they also don't break a phrase).
        if (typeof e.key !== 'string' || e.key.length !== 1) return;

        charBuffer = (charBuffer + e.key.toLowerCase()).slice(-LONGEST_PHRASE);
        armIdleClear();

        if (PHRASES.some((phrase) => charBuffer.endsWith(phrase))) {
            clearBuffer();
            triggerBaDumTss();
        }
    }

    function teardownBaDumTss() {
        if (keydownHandler) {
            document.removeEventListener('keydown', keydownHandler);
            keydownHandler = null;
        }
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        activeOverlays.forEach((el) => el.remove());
        activeOverlays.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        clearBuffer();
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            if (document.body.dataset.userIsAuthenticated !== 'true') return;

            keydownHandler = handleKeydown;
            document.addEventListener('keydown', keydownHandler);

            const ee = window.easterEggs;
            if (ee && typeof ee.registerTeardown === 'function') {
                ee.registerTeardown('badumtss', teardownBaDumTss);
            }
        } finally {
            // Init-complete signal, mirroring window.__konamiReady /
            // window.__easterEggsReady. The E2E test waits on it before typing
            // (page `load` isn't synced with bundle execution).
            window.__baDumTssReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/badumtss.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in konami.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the char buffer, idle timer, overlay timers, the
     * keydown listener) survives between tests. `_resetForTests()` is the
     * per-test reset the `beforeEach` in the JS test must call; it is attached
     * here only, so it never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            PHRASES,
            handleKeydown,
            triggerBaDumTss,
            dustBurst,
            showBaDumTssToast,
            teardownBaDumTss,
            _resetForTests: teardownBaDumTss,
        };
    }
})();
