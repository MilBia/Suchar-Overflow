/* Easter egg: scroll do samego dołu ostatniej strony paginacji listy sucharów
 * (wymagane co najmniej 5 stron ogółem) → toast "Dotarłeś do dna. Sucharów.
 * Gratulacje." + ukryty achievement `frontend-ee-archeolog`. Issue #290,
 * parasol #278.
 *
 * Egg „delight" z grupy A zbudowany na fundamencie #282. Nie podpina żadnego
 * własnego globala (poza flagą inicjalizacji `window.__archeologReady`):
 * korzysta z `window.easterEggs` dla zdeduplikowanego przyznania i z
 * `window.showToast` (project.js) na toast. Oba czytane są w chwili triggera,
 * nigdy w czasie ładowania modułu — project.js definiuje `showToast` dopiero
 * we własnym handlerze DOMContentLoaded, więc kolejność rejestracji listenerów
 * w bundlu nie może mieć znaczenia.
 *
 * Cały plik to IIFE, żeby jego drobne helpery (stałe w stylu `STYLE_ID`, …)
 * nie kolidowały na najwyższym poziomie bundla z project.js / easter_eggs.js /
 * pozostałymi eggami grupy A — kolizja `const` to SyntaxError obejmujący cały
 * bundle (patrz CLAUDE.md i ta sama reguła w konami.js / badumtss.js /
 * logo_spin.js / tumbleweed.js / theme_spam.js).
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

(function () {
    'use strict';

    const SLUG = 'frontend-ee-archeolog';

    const PATH_ROOT = '/suchary';

    // How close to the bottom of the document counts as "reached the end".
    const BOTTOM_THRESHOLD_PX = 150;
    // Scroll fires far more often than this needs checking; throttle the
    // (cheap, but non-trivial) pagination DOM read, same idea as
    // tumbleweed.js's ACTIVITY_THROTTLE_MS.
    const SCROLL_THROTTLE_MS = 200;

    // Below this many total pages, the achievement is unobtainable — a fresh
    // deployment doesn't have enough suchary yet for "reaching the bottom" to
    // mean anything (issue #290).
    const MIN_TOTAL_PAGES = 5;

    const TOAST_TITLE = 'Archeolog';
    const TOAST_BODY = 'Dotarłeś do dna. Sucharów. Gratulacje.';

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

    function isOnSucharyPath() {
        try {
            const pathname = String(window.location.pathname || '');
            return pathname === PATH_ROOT || pathname.startsWith(`${PATH_ROOT}/`);
        } catch {
            return false;
        }
    }

    function isNearBottom() {
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
    function getPaginationInfo() {
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
        const hasNext =
            !nextItem.classList.contains('disabled') && nextItem.querySelector('a') !== null;

        const activeLink = pagination.querySelector('li.page-item.active .page-link');
        const currentPage = activeLink ? parseInt(activeLink.textContent, 10) : NaN;

        return { hasNext, currentPage };
    }

    // Last page of a list with at least MIN_TOTAL_PAGES pages total.
    function isEligibleLastPage() {
        const info = getPaginationInfo();
        if (!info || info.hasNext) return false;
        return Number.isFinite(info.currentPage) && info.currentPage >= MIN_TOTAL_PAGES;
    }

    function showArcheologToast() {
        if (typeof window.showToast !== 'function') return;
        window.showToast(TOAST_BODY, TOAST_TITLE, 'info');
    }

    function triggerArcheolog() {
        const ee = window.easterEggs;
        if (!ee || typeof ee.award !== 'function') return;

        // award() dedupes via sessionStorage and only returns true the first
        // time this session — that's what makes this a once-per-session toast
        // without any separate cooldown bookkeeping.
        if (ee.award(SLUG)) {
            showArcheologToast();
        }
    }

    // The actual geometry check, run at most once per throttle window (via
    // handleScroll below) — never called directly off a scroll event.
    function checkScrollPosition() {
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
    function handleScroll() {
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

    function teardownArcheolog() {
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

    function initArcheolog() {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;
        if (!isOnSucharyPath()) return;

        scrollHandler = handleScroll;
        window.addEventListener('scroll', scrollHandler, { passive: true });

        const ee = window.easterEggs;
        if (ee && typeof ee.registerTeardown === 'function') {
            ee.registerTeardown('archeolog', teardownArcheolog);
        }
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

    /* Test-only export for Vitest + jsdom (tests/js/archeolog.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in the sibling eggs).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the bound listener, the throttle timestamp and
     * pending trailing timer, the settled flag) survives between tests.
     * `_resetForTests()` is the per-test reset the `beforeEach` in
     * tests/js/archeolog.test.js must call; it is attached here only, so it
     * never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            SLUG,
            MIN_TOTAL_PAGES,
            BOTTOM_THRESHOLD_PX,
            SCROLL_THROTTLE_MS,
            TOAST_TITLE,
            TOAST_BODY,
            isOnSucharyPath,
            isNearBottom,
            getPaginationInfo,
            isEligibleLastPage,
            handleScroll,
            checkScrollPosition,
            triggerArcheolog,
            initArcheolog,
            teardownArcheolog,
            _resetForTests: teardownArcheolog,
        };
    }
})();
