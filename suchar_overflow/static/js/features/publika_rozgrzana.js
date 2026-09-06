/* Easter egg: 10 głosów „śmieszne" pod rząd (żaden „suchar"/dry pomiędzy) w
 * oknie 60 s → mały combo-meter na liście sucharów, a po dziesiątym toast
 * „Publika Rozgrzana 🔥" + ukryty achievement `frontend-ee-publika-rozgrzana`.
 * Issue #296, umbrella #279 (żarty w mechanice).
 *
 * Built on the #282 easter-egg foundation. It wires nothing global of its own
 * (only the `window.__publikaRozgrzanaReady` init flag): it consumes
 * `window.easterEggs` for the session-deduped award + the reduced-motion gate,
 * and `window.showToast` (project.js) for the toast. Both are read at trigger
 * time, never at module load — project.js only defines `showToast` inside its
 * own DOMContentLoaded handler, so bundle listener-registration order must not
 * matter.
 *
 * The whole file is an IIFE so its helpers (`readChain`, `buildMeter`, …) don't
 * collide at bundle top level with project.js / easter_eggs.js / the other
 * eggs — a top-level `const` collision there is a bundle-wide SyntaxError (see
 * CLAUDE.md, and the same rule on konami.js / badumtss.js / logo_spin.js /
 * tumbleweed.js / theme_spam.js / archeolog.js). It sits in base.html's global
 * `{% compress js %}` block right after archeolog.js (same-block concatenation,
 * so `BASE_JS_BUNDLES` stays 1).
 *
 * Trigger: a delegated `click` listener on `document` in the CAPTURE phase,
 * scoped to `/suchary` and its sub-pages (like tumbleweed.js / archeolog.js).
 * Capture (not bubble) guarantees it runs before voting.js's bubble-phase
 * delegated listener regardless of which script's DOMContentLoaded handler
 * registered first — so `willActivate()` reads the button's state BEFORE
 * voting.js's optimistic `classList.toggle('active')`, i.e. the same
 * `!wasActive` voting.js itself computes. It never calls `preventDefault` — the
 * vote must still go through.
 *
 * The chain state lives in `sessionStorage` (`{count, firstAt}`), NOT memory:
 * the list paginates with full page reloads and shows 10 suchary per page, so
 * an in-memory counter could only ever be built on a single page where all 10
 * are still unvoted-by-you. logo_spin.js hit the same "state must survive
 * navigation" wall; CLAUDE.md documents that as an accepted deviation from the
 * issue's literal "stan w pamięci strony" wording.
 *
 * Reset (chain cleared, meter hidden):
 *   - any `.btn-vote[data-vote-type="dry"]` click;
 *   - UN-voting a funny (removing a funny vote is not "a funny vote in a row");
 *   - 60 s after the chain's first funny vote. This is authoritative and LAZY:
 *     `readChain()` discards an expired chain on the next click. A visual-only
 *     `setTimeout` additionally hides the meter for a user who simply stopped
 *     clicking; on a fresh page load a live chain re-arms that timer to its
 *     *remaining* window, not a fresh 60 s (cf. tumbleweed.js).
 *
 * Effect on every fresh run of 10 (per #296 — it replays, like the other eggs,
 * not one-shot): a „Publika Rozgrzana" toast + `window.easterEggs.award(SLUG)`
 * (POSTs once per session via the sessionStorage dedupe). The per-increment
 * meter pulse is gated by `prefers-reduced-motion`; the meter itself (with its
 * count) still shows under reduced motion.
 */

(function () {
    'use strict';

    const SLUG = 'frontend-ee-publika-rozgrzana';

    const PATH_ROOT = '/suchary';

    // 10 funny votes in a row within 60 s.
    const THRESHOLD = 10;
    const WINDOW_MS = 60000;

    // sessionStorage chain: JSON `{count, firstAt}`.
    const STORAGE_KEY = 'ee_publika_combo';

    const METER_ID = 'ee-publika-meter';
    const STYLE_ID = 'ee-publika-style';
    const PULSE_CLASS = 'ee-publika-pulse';
    // Keep in sync with the `320ms` literal in PULSE_CSS; the class is stripped a
    // hair later so the animation is never cut short.
    const PULSE_MS = 320;
    const PULSE_CLEAR_MS = PULSE_MS + 60;

    const TOAST_TITLE = 'Publika Rozgrzana';
    const TOAST_BODY = '10 głosów „śmieszne” z rzędu — rozkręcasz publikę! 🔥';

    // One `@keyframes` bump + the class rule that drives it. Injected once as a
    // <style> element — CSP `style-src` allows 'unsafe-inline' (see
    // config/settings/base.py), which covers both this and the inline `style`
    // props on the meter. The nested media query is defence in depth: the JS
    // reduced-motion gate already skips adding the class.
    const PULSE_CSS =
        '@keyframes ee-publika-pulse{0%{transform:scale(1)}45%{transform:scale(1.18)}100%{transform:scale(1)}}'
        + '.ee-publika-pulse{animation:ee-publika-pulse 320ms ease-out}'
        + '@media (prefers-reduced-motion: reduce){.ee-publika-pulse{animation:none}}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    let clickHandler = null;
    // Visual-only: hides the meter + clears the chain WINDOW_MS after the
    // chain's `firstAt`. The authoritative reset is lazy (readChain() refuses an
    // expired chain on the next click) — this is just so a user who stops
    // clicking sees the meter go away. Re-armed on load to the chain's
    // *remaining* time (cf. tumbleweed.js's cooldownRemaining()).
    let expiryTimer = null;
    // A single ref, NOT a Set: only one pulse runs at a time (it drives one
    // shared class on one element), so a rapid second increment must
    // clear-and-replace this timer — otherwise the first timer's callback
    // strips `PULSE_CLASS` mid-way through the second pulse. (konami.js's
    // `Set` is right there because each of its timers owns a distinct
    // container; here they'd fight over the same class.)
    let pulseTimer = null;

    function isOnSucharyPath() {
        try {
            const pathname = String(window.location.pathname || '');
            return pathname === PATH_ROOT || pathname.startsWith(`${PATH_ROOT}/`);
        } catch {
            return false;
        }
    }

    // ── sessionStorage chain ───────────────────────────────────────────────────

    // Returns `{count, firstAt}` for a chain that is still within its 60 s
    // window, or null when absent / malformed / expired. `elapsed < 0` (a
    // `firstAt` in the future — system clock wound back by NTP/DST) also reads
    // as "no chain", mirroring theme_spam.js / tumbleweed.js.
    //
    // `count` is bounded to an integer in `[1, THRESHOLD)`. This is cheap
    // hygiene against a garbled write, not a security boundary — like every
    // `frontend-ee-` egg the award is ultimately one `window.easterEggs.award`
    // console call away — but a chain at/past the threshold is never a state
    // this module stores (it `resetCombo()`s before firing), so refusing it
    // costs nothing.
    function readChain() {
        let raw;
        try {
            raw = sessionStorage.getItem(STORAGE_KEY);
        } catch {
            return null;
        }
        if (!raw) return null;

        let chain;
        try {
            chain = JSON.parse(raw);
        } catch {
            return null;
        }
        if (
            !chain
            || !Number.isFinite(chain.firstAt)
            || !Number.isInteger(chain.count)
            || chain.count <= 0
            || chain.count >= THRESHOLD
        ) {
            return null;
        }

        const elapsed = Date.now() - chain.firstAt;
        if (elapsed < 0 || elapsed >= WINDOW_MS) return null;

        return chain;
    }

    function writeChain(chain) {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(chain));
        } catch {
            // Storage unavailable — the egg just can't build a chain this
            // session; nothing throws.
        }
    }

    function clearChain() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch {
            // Nothing to do.
        }
    }

    // ── Combo-meter (a floating pill, styled inline with project custom props) ──

    function reducedJuice() {
        const ee = window.easterEggs;
        return !!(ee && typeof ee.reducedJuice === 'function' && ee.reducedJuice());
    }

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = PULSE_CSS;
        document.head.appendChild(style);
    }

    function buildMeter() {
        const meter = document.createElement('div');
        meter.id = METER_ID;
        meter.setAttribute('aria-hidden', 'true');
        // Set property-by-property (not `cssText`): jsdom's CSSOM silently drops
        // custom properties / some shorthands set through `cssText`, and every
        // sibling egg sets inline styles this way. Colours come from the
        // project's theme-aware custom properties (variables.css), each with a
        // literal fallback; no Bootstrap classes.
        meter.style.position = 'fixed';
        meter.style.right = '1rem';
        meter.style.bottom = '1rem';
        meter.style.zIndex = '2147483000';
        meter.style.display = 'flex';
        meter.style.alignItems = 'center';
        meter.style.gap = '0.4rem';
        meter.style.padding = '0.4rem 0.7rem';
        meter.style.borderRadius = 'var(--radius-md, 0.75rem)';
        meter.style.background = 'var(--bg-surface, #ffffff)';
        meter.style.color = 'var(--text-main, #1a1a2e)';
        meter.style.border = '1px solid var(--border-color, rgba(0, 0, 0, 0.1))';
        meter.style.boxShadow = 'var(--shadow-md, 0 10px 15px -3px rgba(0, 0, 0, 0.1))';
        meter.style.font = '600 0.85rem var(--font-sans, system-ui, sans-serif)';
        meter.style.pointerEvents = 'none';

        const flame = document.createElement('span');
        flame.textContent = '🔥';
        meter.appendChild(flame);

        const label = document.createElement('span');
        label.className = 'ee-publika-count';
        meter.appendChild(label);

        return meter;
    }

    function getMeter() {
        return document.getElementById(METER_ID);
    }

    function renderMeter(count) {
        let meter = getMeter();
        if (!meter) {
            meter = buildMeter();
            document.body.appendChild(meter);
        }
        const label = meter.querySelector('.ee-publika-count');
        if (label) label.textContent = `${count}/${THRESHOLD}`;

        if (reducedJuice()) return;

        ensureKeyframes();
        meter.classList.remove(PULSE_CLASS);
        // Force reflow so re-adding the class restarts the animation (no-op in
        // jsdom, harmless).
        void meter.offsetWidth;
        meter.classList.add(PULSE_CLASS);
        // Clear-and-replace: a second increment within PULSE_CLEAR_MS restarts
        // the pulse above, so the previous strip-the-class timer must be
        // cancelled or it would end this new pulse early.
        clearPulseTimer();
        pulseTimer = setTimeout(() => {
            pulseTimer = null;
            const current = getMeter();
            if (current) current.classList.remove(PULSE_CLASS);
        }, PULSE_CLEAR_MS);
    }

    function clearPulseTimer() {
        if (pulseTimer !== null) {
            clearTimeout(pulseTimer);
            pulseTimer = null;
        }
    }

    function removeMeter() {
        const meter = getMeter();
        if (meter) meter.remove();
    }

    function clearExpiryTimer() {
        if (expiryTimer !== null) {
            clearTimeout(expiryTimer);
            expiryTimer = null;
        }
    }

    function armExpiryTimer(ms) {
        clearExpiryTimer();
        expiryTimer = setTimeout(() => {
            expiryTimer = null;
            clearChain();
            removeMeter();
        }, Math.max(0, ms));
    }

    function resetCombo() {
        clearChain();
        clearExpiryTimer();
        clearPulseTimer();
        removeMeter();
    }

    // ── Award ──────────────────────────────────────────────────────────────────

    function showPublikaToast() {
        if (typeof window.showToast === 'function') {
            window.showToast(TOAST_BODY, TOAST_TITLE, 'success');
        }
    }

    function firePublikaRozgrzana() {
        const ee = window.easterEggs;
        if (ee && typeof ee.award === 'function') {
            // Dedupes via sessionStorage — POSTs to /frontend-event once per
            // session even though the toast replays on every fresh run of 10.
            ee.award(SLUG);
        }
        showPublikaToast();
    }

    // ── Click handling (capture phase — see initPublikaRozgrzana) ──────────────

    // Whether this `.btn-vote` click will ADD a vote of its type. Read in the
    // capture phase, before voting.js's bubble-phase optimistic
    // `classList.toggle('active')` — so `!hasActive` is the intended post-click
    // state, exactly the `!wasActive` voting.js computes for itself.
    function willActivate(btn) {
        return !btn.classList.contains('active');
    }

    function handleVoteClick(e) {
        const btn = e.target && e.target.closest
            ? e.target.closest('.btn-vote')
            : null;
        if (!btn) return;

        const voteType = btn.dataset ? btn.dataset.voteType : null;
        if (voteType !== 'funny' && voteType !== 'dry') return;

        // A „dry" click (either direction) breaks the run, and so does removing
        // a funny vote — neither is "a funny vote in a row".
        if (voteType === 'dry' || !willActivate(btn)) {
            resetCombo();
            return;
        }

        // A funny vote is being ADDED — extend, or start, the chain.
        const now = Date.now();
        const existing = readChain(); // null if absent or already expired
        const chain = existing
            ? { count: existing.count + 1, firstAt: existing.firstAt }
            : { count: 1, firstAt: now };

        if (chain.count >= THRESHOLD) {
            resetCombo();
            firePublikaRozgrzana();
            return;
        }

        writeChain(chain);
        renderMeter(chain.count);
        armExpiryTimer(chain.firstAt + WINDOW_MS - now);
    }

    // ── Init / teardown ───────────────────────────────────────────────────────

    function teardownPublikaRozgrzana() {
        if (clickHandler) {
            document.removeEventListener('click', clickHandler, { capture: true });
            clickHandler = null;
        }
        clearExpiryTimer();
        clearPulseTimer();
        removeMeter();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        clearChain();
    }

    function initPublikaRozgrzana() {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;
        if (!isOnSucharyPath()) return;

        clickHandler = handleVoteClick;
        document.addEventListener('click', clickHandler, { capture: true });

        const ee = window.easterEggs;
        if (ee && typeof ee.registerTeardown === 'function') {
            ee.registerTeardown('publikaRozgrzana', teardownPublikaRozgrzana);
        }

        // Resume a chain still alive from an earlier page in this session: show
        // the meter and re-arm the expiry timer for the REMAINING window.
        const chain = readChain();
        if (chain) {
            renderMeter(chain.count);
            armExpiryTimer(chain.firstAt + WINDOW_MS - Date.now());
        } else {
            clearChain();
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        try {
            initPublikaRozgrzana();
        } finally {
            // Init-complete signal, mirroring window.__archeologReady /
            // window.__themeSpamReady. The E2E test waits on it before voting
            // (page `load` isn't synced with bundle execution).
            window.__publikaRozgrzanaReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/publika_rozgrzana.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in the sibling eggs).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the bound listener, the expiry + pulse timers)
     * survives between tests. `_resetForTests()` is the per-test reset the
     * `beforeEach` in tests/js/publika_rozgrzana.test.js must call (it also
     * clears the sessionStorage chain key); it is attached here only, so it
     * never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            SLUG,
            THRESHOLD,
            WINDOW_MS,
            STORAGE_KEY,
            METER_ID,
            STYLE_ID,
            PULSE_CLASS,
            TOAST_TITLE,
            TOAST_BODY,
            isOnSucharyPath,
            readChain,
            writeChain,
            clearChain,
            renderMeter,
            removeMeter,
            resetCombo,
            handleVoteClick,
            firePublikaRozgrzana,
            initPublikaRozgrzana,
            teardownPublikaRozgrzana,
            _resetForTests: teardownPublikaRozgrzana,
        };
    }
})();
