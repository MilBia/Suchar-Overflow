/* Easter egg: ostylowane powitanie w konsoli devtools przeglądarki dla każdego,
 * kto zajrzy pod maskę. Issue #287, parasol #278.
 *
 * Egg „delight" z grupy A, ale najlżejszy z rodziny: nie podpina listenerów,
 * nie rusza DOM-u, nie gra dźwięku ani nie odpytuje sieci — po prostu emituje
 * jeden `console.log("%c…", style)` z wordmarkiem ASCII i krótkim polskim
 * mrugnięciem wskazującym repo.
 *
 * Ładowany w globalnym bloku `{% compress js %}` w base.html, PO logo_spin.js.
 * NIE zależy od `window.easterEggs` (brak bramki reduced-motion, brak
 * przyznawania, brak dźwięku), więc kolejność w bundlu poza project.js jest
 * bez znaczenia.
 *
 * Cały plik to IIFE, żeby jego helpery nie wyciekały do współdzielonego
 * scope'u bundla, gdzie żyją też project.js / easter_eggs.js / konami.js /
 * badumtss.js / logo_spin.js — kolizja `const` na najwyższym poziomie to
 * SyntaxError obejmujący cały bundle (patrz CLAUDE.md i ta sama reguła w
 * siostrzanych eggach).
 *
 * „Bez spamu": pokazywane raz na sesję przeglądarki. Flaga żyje w
 * `sessionStorage` (przeżywa nawigację w karcie, znika przy nowej sesji), z
 * fallbackiem w pamięci na wypadek, gdy storage rzuci wyjątkiem (tryb prywatny
 * / zablokowany storage).
 */

(function () {
    'use strict';

    const SESSION_KEY = 'ee_console_shown';
    const REPO_URL = 'https://github.com/MilBia/Suchar-Overflow';

    // ASCII wordmark — a nod to the cracker-stack logo. Built as an array joined
    // with "\n" and kept backslash-free on purpose: a trailing "\" inside a
    // single-quoted line would escape the closing quote.
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
