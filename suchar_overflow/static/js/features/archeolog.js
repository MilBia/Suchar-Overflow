/* Easter egg: scroll do samego dołu ostatniej strony paginacji listy sucharów
 * (wymagane co najmniej 5 stron ogółem) → toast "Dotarłeś do dna. Sucharów.
 * Gratulacje." + ukryty achievement `frontend-ee-archeolog`. Issue #290,
 * umbrella #278.
 *
 * A group-A "delight" egg built on the #282 foundation. It wires nothing
 * global of its own (only the `window.__archeologReady` init flag): it
 * consumes `window.easterEggs` for the deduped award, and `window.showToast`
 * (project.js) for the toast. Both are read at trigger time, never at module
 * load — project.js only defines `showToast` inside its own DOMContentLoaded
 * handler, so bundle listener-registration order must not matter.
 *
 * The whole file is an IIFE so its small helpers (`STYLE_ID`-style constants,
 * …) don't collide at bundle top level with project.js / easter_eggs.js / the
 * other group-A eggs — a top-level `const` collision there is a bundle-wide
 * SyntaxError (see CLAUDE.md, and the same rule on konami.js / badumtss.js /
 * logo_spin.js / tumbleweed.js / theme_spam.js).
 *
 * Trigger: scoped to `/suchary` and its sub-pages (like tumbleweed.js). A
 * throttled passive `scroll` listener checks `scrollY + innerHeight >=
 * scrollHeight - threshold` AND that the pagination nav shows no "Next" link
 * AND the active page number is >= MIN_TOTAL_PAGES. The active-page number
 * doubles as the *total* page count here (we only ever check it once we've
 * already confirmed there's no next page) — a brand-new deployment with fewer
 * than 5 pages of suchary can never award this, per issue #290: nobody should
 * get "Archeolog" for reaching the bottom of an almost-empty site.
 *
 * The "Next" / active-page state is read structurally (last `<li>` in
 * `.pagination` has no `<a>`; `.page-item.active .page-link` holds the page
 * number), never by matching the localized "Next" label text — templates
 * render in Polish (LANGUAGE_CODE = "pl"), and the active page number is
 * never elided by Django's `get_elided_page_range()` since it always includes
 * the current page.
 *
 * Fires at most once per session (award() dedupes via sessionStorage): the
 * toast is only shown when `award()` reports the first award this session,
 * so a scroll listener re-firing near the threshold can't spam it. Pure
 * text/toast effect — no animation, so there is nothing for
 * `prefers-reduced-motion` to gate.
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
            const scrollHeight = document.documentElement
                ? document.documentElement.scrollHeight
                : 0;
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
        const nextItem = items[items.length - 1];
        const hasNext = nextItem.querySelector('a') !== null;

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

    function handleScroll() {
        if (settledThisPage) return;

        const now = Date.now();
        if (now - lastCheckAt < SCROLL_THROTTLE_MS) return;
        lastCheckAt = now;

        if (!isNearBottom()) return;
        if (!isEligibleLastPage()) return;

        settledThisPage = true;
        triggerArcheolog();
    }

    function teardownArcheolog() {
        if (scrollHandler) {
            window.removeEventListener('scroll', scrollHandler);
            scrollHandler = null;
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
     * module's mutable state (the bound listener, the throttle timestamp, the
     * settled flag) survives between tests. `_resetForTests()` is the per-test
     * reset the `beforeEach` in tests/js/archeolog.test.js must call; it is
     * attached here only, so it never reaches a real browser. */
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
            triggerArcheolog,
            initArcheolog,
            teardownArcheolog,
            _resetForTests: teardownArcheolog,
        };
    }
})();
