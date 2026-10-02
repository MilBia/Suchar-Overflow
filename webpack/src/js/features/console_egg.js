/* Easter egg: ostylowane powitanie w konsoli devtools przeglądarki dla każdego,
 * kto zajrzy pod maskę. Issue #287, parasol #278.
 *
 * Egg „delight" z grupy A, ale najlżejszy z rodziny: nie podpina listenerów,
 * nie rusza DOM-u, nie gra dźwięku ani nie odpytuje sieci — po prostu emituje
 * jeden `console.log("%c…", style)` z wordmarkiem ASCII i krótkim polskim
 * mrugnięciem wskazującym repo.
 *
 * Moduł ES (#468), importowany przez wpis `project` (webpack/src/js/project.js)
 * po logo_spin.js. NIE zależy od `easterEggs` (brak bramki reduced-motion, brak
 * przyznawania, brak dźwięku), więc nic nie importuje.
 *
 * „Bez spamu": pokazywane raz na sesję przeglądarki. Flaga żyje w
 * `sessionStorage` (przeżywa nawigację w karcie, znika przy nowej sesji), z
 * fallbackiem w pamięci na wypadek, gdy storage rzuci wyjątkiem (tryb prywatny
 * / zablokowany storage).
 */
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

const TEXT = '😉 Zaglądasz pod maskę? Kod, Issues i suchary czekają:\n   ' + REPO_URL;

const ART_STYLE = "color:#E58E26;font-family:'Fira Code',ui-monospace,monospace;" + 'font-weight:bold;line-height:1.15';
const TEXT_STYLE = 'color:inherit;font-family:ui-sans-serif,system-ui,sans-serif;font-size:12px';

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

/* Per-test reset (tests/js/console_egg.test.js): clears the in-memory `shownThisPage` flag AND
 * the sessionStorage dedupe key. Module export only — never reaches `window`. NOT dead code, see
 * CLAUDE.md "JS tests (Vitest)". */
export function _resetForTests() {
    shownThisPage = false;
    try {
        sessionStorage.removeItem(SESSION_KEY);
    } catch {
        // Nothing to clear.
    }
}

export { SESSION_KEY, REPO_URL, ART, TEXT, hasShown, markShown, logConsoleEgg, initConsoleEgg };
