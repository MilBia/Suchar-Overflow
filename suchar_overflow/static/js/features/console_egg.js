/* Easter egg: a styled greeting in the browser devtools console for whoever
 * opens the hood. Issue #287, umbrella #278.
 *
 * A group-A "delight" egg, but the lightest of the family: it wires no
 * listeners, touches no DOM, plays no sound and hits no network — it just
 * emits a single `console.log("%c…", style)` with an ASCII wordmark and a
 * short Polish wink that points at the repo.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER logo_spin.js.
 * It does NOT depend on `window.easterEggs` (no reduced-motion gate, no award,
 * no sound), so bundle order past project.js is irrelevant.
 *
 * The whole file is an IIFE so its helpers don't leak into the shared bundle
 * scope where project.js / easter_eggs.js / konami.js / badumtss.js /
 * logo_spin.js also live — a top-level `const` collision there is a bundle-wide
 * SyntaxError (see CLAUDE.md, and the same rule on the sibling eggs).
 *
 * "No spam": shown once per browser session. The flag lives in `sessionStorage`
 * (survives in-tab navigation, gone on a new session) with an in-memory
 * fallback for when storage throws (private mode / storage blocked).
 */

(function () {
    'use strict';

    const SESSION_KEY = 'ee_console_shown';
    const REPO_URL = 'https://github.com/MilBia/Suchar-Overflow';

    // ASCII wordmark — a nod to the cracker-stack logo. Kept backslash-free on
    // purpose: a trailing "\" is a line-continuation inside this template
    // literal and would silently eat the newline.
    const ART = [
        '   .========.',
        '   | o  o  o |   Suchar Overflow',
        '   | o  o  o |   suche żarty, świeży kod',
        "   '========'",
    ].join('\n');

    const TEXT =
        '😉 Zaglądasz pod maskę? Kod, Issues i suchary czekają:\n   ' + REPO_URL;

    const ART_STYLE =
        "color:#E58E26;font-family:'Fira Code',ui-monospace,monospace;"
        + 'font-weight:bold;line-height:1.15';
    const TEXT_STYLE =
        'color:inherit;font-family:ui-sans-serif,system-ui,sans-serif;font-size:12px';

    // In-memory dedupe for the current page; `sessionStorage` covers the rest of
    // the session. Reset between Vitest tests via `_resetForTests`.
    let shownThisPage = false;

    function hasShown() {
        if (shownThisPage) return true;
        try {
            return sessionStorage.getItem(SESSION_KEY) === '1';
        } catch {
            return false;
        }
    }

    function markShown() {
        shownThisPage = true;
        try {
            sessionStorage.setItem(SESSION_KEY, '1');
        } catch {
            // Storage unavailable — the in-page flag above still dedupes.
        }
    }

    // Emit the greeting once per session. Returns true on the call that actually
    // logs, false when it was already shown.
    function logConsoleEgg() {
        if (hasShown()) return false;
        markShown();
        try {
            console.log('%c' + ART + '\n%c' + TEXT, ART_STYLE, TEXT_STYLE);
        } catch {
            // A console that rejects styled logging is not worth an error.
        }
        return true;
    }

    // Gate on the same authed-body flag the sibling eggs use: this greeting is
    // aimed at contributors, and the rest of group A is logged-in-only too.
    function initConsoleEgg() {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;
        logConsoleEgg();
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            initConsoleEgg();
        } finally {
            // Init-complete signal, mirroring window.__baDumTssReady /
            // window.__easterEggsReady. The E2E test waits on it before reading
            // the captured console output (page `load` isn't synced with bundle
            // execution).
            window.__consoleEggReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/console_egg.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in badumtss.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so the
     * in-memory `shownThisPage` flag survives between tests. `_resetForTests()`
     * clears it AND the sessionStorage dedupe key; it is attached here only, so
     * it never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            SESSION_KEY,
            REPO_URL,
            ART,
            TEXT,
            hasShown,
            markShown,
            logConsoleEgg,
            initConsoleEgg,
            _resetForTests: () => {
                shownThisPage = false;
                try {
                    sessionStorage.removeItem(SESSION_KEY);
                } catch {
                    // Nothing to clear.
                }
            },
        };
    }
})();
