/* Easter egg: scroll do samego dołu ostatniej strony paginacji listy sucharów
 * (wymagane co najmniej 5 stron ogółem) → toast "Dotarłeś do dna. Sucharów.
 * Gratulacje." + ukryty achievement `frontend-ee-archeolog`. Issue #290,
 * parasol #278.
 *
 * Egg „delight" z grupy A zbudowany na fundamencie #282. Nie podpina żadnego
 * własnego globala (poza flagą inicjalizacji `window.__archeologReady`):
 * korzysta z `easterEggs` (easter_eggs.js) dla zdeduplikowanego przyznania i z
 * `showToast` (toast.js) na toast.
 *
 * Moduł ES (#468), importowany we wpisie `project` (webpack/src/js/project.js) po easter_eggs.js.
 *
 * Trigger: ograniczony do `/suchary` i jego podstron (jak tumbleweed.js).
 * Pasywny listener `scroll`, throttlowany z krawędzią trailing (samo
 * leading-edge groziłoby przeoczeniem dyskretnego skoku na dół — np.
 * naciśnięcie `End` albo gest, który zatrzymuje się tuż przy krawędzi — który
 * nie odpala kolejnego zdarzenia `scroll` do ponownego sprawdzenia w oknie
 * throttla), sprawdza `scrollY + innerHeight >= scrollHeight - threshold` ORAZ
 * że nawigacja paginacji nie pokazuje linku „Next" ORAZ że numer aktywnej
 * strony jest >= MIN_TOTAL_PAGES. Numer aktywnej strony pełni tu jednocześnie
 * rolę *całkowitej* liczby stron (sprawdzamy go dopiero, gdy potwierdziliśmy
 * już brak następnej strony) — świeżo postawiony deployment z mniej niż 5
 * stronami sucharów nigdy tego nie przyzna, per issue #290: nikt nie powinien
 * dostać „Archeologa" za dotarcie do dna niemal pustego serwisu.
 *
 * Stan „Next" / aktywnej strony czytany jest strukturalnie (ostatni `<li>` w
 * `.pagination` nie ma `<a>`; `.page-item.active .page-link` trzyma numer
 * strony), nigdy przez dopasowanie zlokalizowanego tekstu etykiety „Next" —
 * szablony renderują się po polsku (LANGUAGE_CODE = "pl"), a numer aktywnej
 * strony nigdy nie jest pomijany przez `get_elided_page_range()` Django, bo
 * zawsze zawiera bieżącą stronę.
 *
 * Odpala najwyżej raz na sesję (award() deduplikuje przez sessionStorage):
 * toast pokazuje się tylko, gdy `award()` zgłasza pierwsze przyznanie w tej
 * sesji, więc listener scrolla odpalający się ponownie przy progu nie może go
 * spamować. Czysty efekt tekst/toast — brak animacji, więc nie ma czego
 * bramkować przez `prefers-reduced-motion`.
 */

import { easterEggs } from './easter_eggs.js';
import { showToast } from '../toast.js';

export const SLUG = 'frontend-ee-archeolog';

const PATH_ROOT = '/suchary';

// How close to the bottom of the document counts as "reached the end".
export const BOTTOM_THRESHOLD_PX = 150;
// Scroll fires far more often than this needs checking; throttle the
// (cheap, but non-trivial) pagination DOM read, same idea as
// tumbleweed.js's ACTIVITY_THROTTLE_MS.
export const SCROLL_THROTTLE_MS = 200;

// Below this many total pages, the achievement is unobtainable — a fresh
// deployment doesn't have enough suchary yet for "reaching the bottom" to
// mean anything (issue #290).
export const MIN_TOTAL_PAGES = 5;

export const TOAST_TITLE = 'Archeolog';
export const TOAST_BODY = 'Dotarłeś do dna. Sucharów. Gratulacje.';

// ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
let scrollHandler = null;
let lastCheckAt = 0;
// Pending trailing-edge check, scheduled by handleScroll (see there).
let scrollThrottleTimer = null;
// Once true for this page load, skip further checks — either we've
// already fired this session, or the page/pagination state can't change
// without a full reload (the app does full page reloads, like the other
// path-scoped eggs).
let settledThisPage = false;

export function isOnSucharyPath() {
    try {
        const pathname = String(window.location.pathname || '');
        return pathname === PATH_ROOT || pathname.startsWith(`${PATH_ROOT}/`);
    } catch {
        return false;
    }
}

export function isNearBottom() {
    try {
        const scrollY = window.scrollY || window.pageYOffset || 0;
        const innerHeight = window.innerHeight || 0;
        // Belt-and-suspenders: `documentElement.scrollHeight` is the right
        // read in standards mode (Django always renders a doctype), but
        // this mirrors the codebase's habit of checking both signals
        // rather than trusting a single one (see tumbleweed.js's
        // isDocumentHidden(), which checks visibilityState AND hidden).
        const scrollHeight = Math.max(
            document.documentElement ? document.documentElement.scrollHeight : 0,
            document.body ? document.body.scrollHeight : 0,
        );
        return scrollY + innerHeight >= scrollHeight - BOTTOM_THRESHOLD_PX;
    } catch {
        return false;
    }
}

// Reads the pagination nav once and returns { hasNext, currentPage }, or
// null when there is no pagination at all (a single page — never eligible,
// since that's always fewer than MIN_TOTAL_PAGES).
export function getPaginationInfo() {
    const pagination = document.querySelector('nav[aria-label] .pagination');
    if (!pagination) return null;

    const items = pagination.querySelectorAll(':scope > li.page-item');
    if (items.length === 0) return null;

    // Structure is always Previous, page numbers…, Next (see
    // suchar_list.html) — the last item is the "Next" slot. It has no <a>
    // when there is no next page (rendered as a disabled <span> instead).
    // The `.disabled` class check is a second, redundant signal for the
    // same fact (suchar_list.html sets both) — cheap insurance against
    // that template changing shape later without this reading stale.
    const nextItem = items[items.length - 1];
    const hasNext = !nextItem.classList.contains('disabled') && nextItem.querySelector('a') !== null;

    const activeLink = pagination.querySelector('li.page-item.active .page-link');
    const currentPage = activeLink ? parseInt(activeLink.textContent, 10) : NaN;

    return { hasNext, currentPage };
}

// Last page of a list with at least MIN_TOTAL_PAGES pages total.
export function isEligibleLastPage() {
    const info = getPaginationInfo();
    if (!info || info.hasNext) return false;
    return Number.isFinite(info.currentPage) && info.currentPage >= MIN_TOTAL_PAGES;
}

function showArcheologToast() {
    showToast(TOAST_BODY, TOAST_TITLE, 'info');
}

export function triggerArcheolog() {
    // award() dedupes via sessionStorage and only returns true the first
    // time this session — that's what makes this a once-per-session toast
    // without any separate cooldown bookkeeping.
    if (easterEggs.award(SLUG)) {
        showArcheologToast();
    }
}

// The actual geometry check, run at most once per throttle window (via
// handleScroll below) — never called directly off a scroll event.
export function checkScrollPosition() {
    if (settledThisPage) return;
    if (!isNearBottom()) return;
    if (!isEligibleLastPage()) return;

    settledThisPage = true;
    triggerArcheolog();
}

// Leading-edge throttle with a trailing check. A single discrete jump to
// the bottom (a keyboard `End`, or a scroll gesture that stops moving
// right at the edge) can fire its last `scroll` event inside the throttle
// window with no further event to re-check on — a plain leading-edge
// throttle would then silently miss that arrival for the rest of the page
// load. Scheduling one trailing timeout for the remainder of the window
// guarantees a check still happens even when no more `scroll` events do.
//
// `elapsed < 0` (system clock wound backward mid-session — NTP/DST) is
// treated as "due now" rather than getting stuck waiting out a window
// that will never elapse — same guard shape as tumbleweed.js's
// lastFireAt() / theme_spam.js's click-window check, kept on Date.now()
// rather than performance.now() for consistency with those.
export function handleScroll() {
    if (settledThisPage) return;

    const now = Date.now();
    const elapsed = now - lastCheckAt;

    if (elapsed < 0 || elapsed >= SCROLL_THROTTLE_MS) {
        if (scrollThrottleTimer !== null) {
            clearTimeout(scrollThrottleTimer);
            scrollThrottleTimer = null;
        }
        lastCheckAt = now;
        checkScrollPosition();
        return;
    }

    if (scrollThrottleTimer === null) {
        scrollThrottleTimer = setTimeout(() => {
            scrollThrottleTimer = null;
            lastCheckAt = Date.now();
            checkScrollPosition();
        }, SCROLL_THROTTLE_MS - elapsed);
    }
}

export function teardownArcheolog() {
    if (scrollHandler) {
        window.removeEventListener('scroll', scrollHandler);
        scrollHandler = null;
    }
    if (scrollThrottleTimer !== null) {
        clearTimeout(scrollThrottleTimer);
        scrollThrottleTimer = null;
    }
    lastCheckAt = 0;
    settledThisPage = false;
}

// ── Init ─────────────────────────────────────────────────────────────────

export function initArcheolog() {
    if (document.body.dataset.userIsAuthenticated !== 'true') return;
    if (!isOnSucharyPath()) return;

    scrollHandler = handleScroll;
    window.addEventListener('scroll', scrollHandler, { passive: true });

    easterEggs.registerTeardown('archeolog', teardownArcheolog);
}

document.addEventListener('DOMContentLoaded', () => {
    try {
        initArcheolog();
    } finally {
        // Init-complete signal, mirroring window.__tumbleweedReady /
        // window.__themeSpamReady. The E2E test waits on it before
        // scrolling (page `load` isn't synced with bundle execution).
        window.__archeologReady = true;
    }
});

/* Per-test reset (detach + wyczyszczenie stanu modułu). Statycznie importowany moduł żyje jedną
 * instancją na plik testów, więc `beforeEach`/`afterEach` wołają to zamiast `vi.resetModules()`. */
export { teardownArcheolog as _resetForTests };
