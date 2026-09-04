/* Easter egg: sit still on the suchar list for two minutes → a tumbleweed rolls
 * across the bottom of the screen with the line "cisza… aż tak sucho?", then
 * clears. Issue #288, umbrella #278.
 *
 * A group-A "delight" egg built on the #282 foundation. It wires nothing global
 * of its own (only the `window.__tumbleweedReady` init flag): it consumes
 * `window.easterEggs` for the reduced-motion gate and `window.showToast`
 * (project.js) for the reduced-motion fallback.
 *
 * Unlike the keydown eggs (konami / badumtss), the trigger here is *absence* of
 * input: passive `scroll` / `mousemove` / `keydown` / `pointerdown` listeners
 * each reset a 120 s idle timer, and the timer firing is the event (skipped
 * while the tab is backgrounded). It is scoped to the
 * suchar list — `initTumbleweed` only attaches and arms when
 * `location.pathname` starts with `/suchary` (the app does full page reloads,
 * so re-checking on navigation is unnecessary). A `sessionStorage` timestamp
 * keeps it to at most once per 5 minutes across the list's paginated reloads.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER console_egg.js.
 * The whole file is an IIFE so its small helpers (`rand`, `STYLE_ID`, …) don't
 * collide at bundle top level with project.js / easter_eggs.js / konami.js /
 * badumtss.js / logo_spin.js — a top-level `const` clash there is a bundle-wide
 * SyntaxError (see CLAUDE.md, and the same rule on the sibling eggs).
 *
 * Pure delight: NO achievement, NO frontend-ee- slug, NO network, NO sound. The
 * effect replays on every fresh 120 s of stillness once the cooldown is up:
 *   - full motion: a tumbleweed SVG rolls right-to-left along the lower screen
 *     edge, the caption riding beneath it, ~4 s;
 *   - prefers-reduced-motion: the caption only, as a toast — no overlay.
 */

(function () {
    'use strict';

    // Idle time before the tumbleweed rolls; any activity resets it.
    const IDLE_MS = 120000;
    // Minimum gap between two rolls, held in sessionStorage so the list's
    // paginated reloads don't let it re-fire every 2 minutes.
    const COOLDOWN_MS = 300000;
    const STORAGE_KEY = 'ee_tumbleweed_last';

    // The suchar list and everything under it arm the egg (issue #288). Matched
    // as an exact page or a `/`-delimited prefix so a hypothetical sibling route
    // like `/suchary-archiwum/` never counts.
    const PATH_ROOT = '/suchary';

    // Activity that resets the idle countdown. `pointerdown` covers a tap on
    // touch / pen where there is no `mousemove` (issue names scroll/mousemove/
    // keydown, but a phone reader only taps).
    const ACTIVITY_EVENTS = ['scroll', 'mousemove', 'keydown', 'pointerdown'];
    // High-frequency events (`mousemove` on a 1 kHz mouse, per-frame `scroll`)
    // don't need to re-arm the timer more than about once a second — the idle
    // window is 120 s, so this much slack in the reset is immaterial.
    const ACTIVITY_THROTTLE_MS = 1000;

    const CAPTION = 'cisza… aż tak sucho?';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const STYLE_ID = 'ee-tumbleweed-style';
    const OVERLAY_CLASS = 'ee-tumbleweed-overlay';
    const CAPTION_CLASS = 'ee-tumbleweed-caption';
    // Keep in sync with the `4s` roll literal in ROLL_KEYFRAMES; the overlay is
    // pulled a hair later so the roll never cuts off mid-screen.
    const OVERLAY_LIFETIME_MS = 4400;

    // `@keyframes` for the roll (the wrapper crosses the viewport) and the spin
    // (the SVG turns as it goes). Injected once as a <style> element — CSP
    // `style-src` allows 'unsafe-inline' (see config/settings/base.py), which
    // covers both this block and the per-element inline `style=` below.
    const ROLL_KEYFRAMES =
        '@keyframes ee-tumbleweed-roll{'
        + 'from{transform:translateX(calc(100vw + 120px))}'
        + 'to{transform:translateX(-160px)}'
        + '}'
        + '@keyframes ee-tumbleweed-spin{'
        // Negative = counter-clockwise on screen (CSS y points down): the way a
        // ball actually rolls when it travels right-to-left along the ground.
        + 'from{transform:rotate(0)}to{transform:rotate(-1080deg)}'
        + '}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    let idleTimer = null;
    let activityHandler = null;
    let lastActivityReset = 0;
    const activeTimers = new Set();
    const activeOverlays = new Set();

    function rand(min, max) {
        return min + Math.random() * (max - min);
    }

    // True only on the suchar list / its sub-pages.
    function isOnSucharyPath() {
        try {
            const pathname = String(window.location.pathname || '');
            return pathname === PATH_ROOT || pathname.startsWith(`${PATH_ROOT}/`);
        } catch {
            return false;
        }
    }

    // Reduced-motion gate. Delegates to the #282 foundation's single check, with
    // a direct-media-query fallback if easter_eggs.js failed to load — a user
    // who asked for reduced motion must not get the roll just because the
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

    // ── Cooldown persistence ──────────────────────────────────────────────────

    function lastFireAt() {
        try {
            const last = Number(sessionStorage.getItem(STORAGE_KEY));
            // Reject a non-positive or *future* timestamp: if the system clock
            // was wound back (NTP / DST) after we stored it, `Date.now() - last`
            // would go negative and wedge the cooldown on for hours.
            return Number.isFinite(last) && last > 0 && last <= Date.now()
                ? last
                : 0;
        } catch {
            return 0;
        }
    }

    function onCooldown() {
        const last = lastFireAt();
        return last > 0 && Date.now() - last < COOLDOWN_MS;
    }

    // Milliseconds still owed on the cooldown (0 once it has lapsed).
    function cooldownRemaining() {
        const last = lastFireAt();
        if (last <= 0) return 0;
        return Math.max(0, COOLDOWN_MS - (Date.now() - last));
    }

    function recordFire() {
        try {
            sessionStorage.setItem(STORAGE_KEY, String(Date.now()));
        } catch {
            // Storage unavailable — worst case the egg can re-fire a touch more
            // often this session.
        }
    }

    function clearCooldown() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch {
            // Nothing to do.
        }
    }

    // ── Idle timer ────────────────────────────────────────────────────────────

    function armIdleTimer(delayMs = IDLE_MS) {
        if (idleTimer !== null) {
            clearTimeout(idleTimer);
            idleTimer = null;
        }
        if (!isOnSucharyPath()) return;
        idleTimer = setTimeout(onIdle, delayMs);
    }

    function onIdle() {
        idleTimer = null;
        if (!isOnSucharyPath()) return;
        if (isDocumentHidden()) {
            // Background tab: CSS animations are frozen there, so a roll now
            // would burn the cooldown on something nobody sees. Wait out
            // another idle window and re-check when it fires (the tab may be
            // foreground by then; if not, we wait again).
            armIdleTimer();
            return;
        }
        if (onCooldown()) {
            // Still resting: come back exactly when the cooldown lapses, so the
            // tumbleweed reappears promptly for a viewer who stays idle rather
            // than after a further full IDLE_MS. Any activity meanwhile re-arms
            // the full idle wait.
            armIdleTimer(cooldownRemaining());
            return;
        }
        triggerTumbleweed();
        recordFire();
        armIdleTimer();
    }

    function isDocumentHidden() {
        try {
            return document.visibilityState === 'hidden' || document.hidden === true;
        } catch {
            return false;
        }
    }

    // Passive listener body — every activity kind funnels here. Throttled: a
    // burst of `mousemove` / `scroll` only needs to re-arm the timer about once
    // a second (see ACTIVITY_THROTTLE_MS).
    function handleActivity() {
        const now = Date.now();
        if (now - lastActivityReset < ACTIVITY_THROTTLE_MS) return;
        lastActivityReset = now;
        armIdleTimer();
    }

    // ── Effect ────────────────────────────────────────────────────────────────

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = ROLL_KEYFRAMES;
        document.head.appendChild(style);
    }

    function makeOverlay() {
        const overlay = document.createElement('div');
        overlay.className = OVERLAY_CLASS;
        overlay.setAttribute('aria-hidden', 'true');
        // Set property-by-property (not `cssText`): jsdom's CSSOM silently drops
        // custom properties and some shorthands set through `cssText`.
        overlay.style.position = 'fixed';
        overlay.style.left = '0';
        overlay.style.right = '0';
        overlay.style.bottom = '0';
        overlay.style.height = '30vh';
        overlay.style.pointerEvents = 'none';
        overlay.style.overflow = 'hidden';
        overlay.style.zIndex = '2147483000';
        return overlay;
    }

    // A dry bramble: a rough ring plus a few chords through the middle, built
    // element-by-element (no external file to clone, so nothing to collide on
    // by `id`). Deliberately one warm tan tone — readable on both themes, like
    // badumtss's dust motes.
    function makeTumbleweedSvg() {
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('width', '72');
        svg.setAttribute('height', '72');
        svg.setAttribute('viewBox', '0 0 100 100');
        svg.setAttribute('aria-hidden', 'true');
        svg.style.display = 'block';
        svg.style.animationName = 'ee-tumbleweed-spin';
        svg.style.animationDuration = '4s';
        svg.style.animationTimingFunction = 'linear';
        svg.style.animationIterationCount = '1';
        svg.style.animationFillMode = 'both';

        const stroke = '#b58b5a';

        const ring = document.createElementNS(SVG_NS, 'circle');
        ring.setAttribute('cx', '50');
        ring.setAttribute('cy', '50');
        ring.setAttribute('r', '38');
        ring.setAttribute('fill', 'none');
        ring.setAttribute('stroke', stroke);
        ring.setAttribute('stroke-width', '3');
        svg.appendChild(ring);

        // Chords roughly every 30° evoke the tangled bramble inside the ring;
        // a random start offset and per-chord length jitter keep no two rolls
        // looking quite the same.
        const offset = rand(0, 30);
        for (let deg = offset; deg < 180 + offset; deg += 30) {
            const rad = (deg * Math.PI) / 180;
            const len = rand(30, 38);
            const dx = Math.cos(rad) * len;
            const dy = Math.sin(rad) * len;
            const line = document.createElementNS(SVG_NS, 'line');
            line.setAttribute('x1', (50 - dx).toFixed(1));
            line.setAttribute('y1', (50 - dy).toFixed(1));
            line.setAttribute('x2', (50 + dx).toFixed(1));
            line.setAttribute('y2', (50 + dy).toFixed(1));
            line.setAttribute('stroke', stroke);
            line.setAttribute('stroke-width', '2');
            svg.appendChild(line);
        }

        return svg;
    }

    function makeCaption() {
        const caption = document.createElement('div');
        caption.className = CAPTION_CLASS;
        caption.textContent = CAPTION;
        caption.style.marginTop = '6px';
        caption.style.fontStyle = 'italic';
        caption.style.fontSize = '0.95rem';
        caption.style.color = '#b58b5a';
        caption.style.textShadow = '0 1px 2px rgba(0, 0, 0, 0.35)';
        caption.style.whiteSpace = 'nowrap';
        return caption;
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
    function rollTumbleweed() {
        ensureKeyframes();
        const overlay = makeOverlay();

        const wrapper = document.createElement('div');
        wrapper.style.position = 'absolute';
        wrapper.style.bottom = '12%';
        wrapper.style.left = '0';
        wrapper.style.display = 'inline-flex';
        wrapper.style.flexDirection = 'column';
        wrapper.style.alignItems = 'center';
        wrapper.style.animationName = 'ee-tumbleweed-roll';
        wrapper.style.animationDuration = '4s';
        wrapper.style.animationTimingFunction = 'linear';
        wrapper.style.animationIterationCount = '1';
        wrapper.style.animationFillMode = 'both';

        wrapper.appendChild(makeTumbleweedSvg());
        wrapper.appendChild(makeCaption());
        overlay.appendChild(wrapper);

        document.body.appendChild(overlay);
        activeOverlays.add(overlay);
        scheduleRemoval(overlay, OVERLAY_LIFETIME_MS);
    }

    function showCaptionToast() {
        if (typeof window.showToast !== 'function') return;
        window.showToast(CAPTION, '🌾', 'info');
    }

    function triggerTumbleweed() {
        if (prefersReducedMotion()) {
            showCaptionToast();
            return;
        }
        rollTumbleweed();
    }

    // ── Teardown ──────────────────────────────────────────────────────────────

    function teardownTumbleweed() {
        if (activityHandler) {
            ACTIVITY_EVENTS.forEach((type) => {
                window.removeEventListener(type, activityHandler);
            });
            activityHandler = null;
        }
        if (idleTimer !== null) {
            clearTimeout(idleTimer);
            idleTimer = null;
        }
        lastActivityReset = 0;
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        activeOverlays.forEach((el) => el.remove());
        activeOverlays.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        clearCooldown();
    }

    // ── Init ─────────────────────────────────────────────────────────────────

    function initTumbleweed() {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;
        if (!isOnSucharyPath()) return;

        activityHandler = handleActivity;
        ACTIVITY_EVENTS.forEach((type) => {
            window.addEventListener(type, activityHandler, { passive: true });
        });
        armIdleTimer();

        const ee = window.easterEggs;
        if (ee && typeof ee.registerTeardown === 'function') {
            ee.registerTeardown('tumbleweed', teardownTumbleweed);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        try {
            initTumbleweed();
        } finally {
            // Init-complete signal, mirroring window.__konamiReady /
            // window.__logoSpinReady. The E2E test waits on it before faking the
            // idle clock (page `load` isn't synced with bundle execution).
            window.__tumbleweedReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/tumbleweed.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in konami.js /
     * badumtss.js / logo_spin.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the idle timer, the bound activity listener, the
     * overlay timers) survives between tests. `_resetForTests()` is the per-test
     * reset the `beforeEach` must call; it is attached here only, so it never
     * reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            IDLE_MS,
            COOLDOWN_MS,
            CAPTION,
            STORAGE_KEY,
            OVERLAY_LIFETIME_MS,
            isOnSucharyPath,
            handleActivity,
            armIdleTimer,
            onCooldown,
            triggerTumbleweed,
            rollTumbleweed,
            initTumbleweed,
            teardownTumbleweed,
            _resetForTests: teardownTumbleweed,
        };
    }
})();
