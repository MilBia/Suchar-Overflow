/**
 * Unit tests for the "Archeolog" scroll-to-bottom easter egg in
 * suchar_overflow/static/js/features/archeolog.js (issue #290).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so most tests drive the exported helpers directly.
 *
 * The real `features/easter_eggs.js` is wired in first so `window.easterEggs`
 * (the deduped award this egg delegates to) behaves for real.
 * `vi.resetModules()` does not re-run a required CJS module, so both modules
 * expose `_resetForTests()` for the per-test cleanup.
 */
const path = require("node:path");

const ARCHEOLOG_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/archeolog.js",
);
const EASTER_EGGS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);

const SLUG = "frontend-ee-archeolog";
const MIN_TOTAL_PAGES = 5;

let archeolog;

function frontendEventPosts() {
  return globalThis.fetch.mock.calls.filter(
    ([url]) => url === "/api/achievements/frontend-event",
  );
}

/** Put jsdom's `location.pathname` where the test needs it. */
function setPath(pathname) {
  window.history.pushState({}, "", pathname);
}

/**
 * Build the `.pagination` nav exactly like suchar_list.html: Previous, page
 * numbers, Next. `hasNext: false` renders the "Next" slot as a disabled
 * `<span>` (no `<a>`) — the structural signal the module reads, not the
 * (localized) label text.
 */
function makePagination({ currentPage, hasNext }) {
  const nav = document.createElement("nav");
  nav.setAttribute("aria-label", "Page navigation");
  const nextItem = hasNext
    ? '<li class="page-item"><a class="page-link" href="?page=x">Next</a></li>'
    : '<li class="page-item disabled"><span class="page-link">Next</span></li>';
  nav.innerHTML = `
    <ul class="pagination">
      <li class="page-item"><a class="page-link" href="?page=1">Previous</a></li>
      <li class="page-item active"><span class="page-link" aria-current="page">${currentPage}</span></li>
      ${nextItem}
    </ul>
  `;
  document.body.appendChild(nav);
  return nav;
}

/** Set the three scroll-geometry reads archeolog.js relies on. */
function setScrollMetrics({ scrollY, innerHeight = 800, scrollHeight }) {
  Object.defineProperty(window, "scrollY", { value: scrollY, configurable: true });
  Object.defineProperty(window, "innerHeight", {
    value: innerHeight,
    configurable: true,
  });
  Object.defineProperty(document.documentElement, "scrollHeight", {
    value: scrollHeight,
    configurable: true,
  });
}

/** scrollY + innerHeight === scrollHeight: right at the bottom edge. */
function setAtBottom(scrollHeight = 3000) {
  setScrollMetrics({ scrollY: scrollHeight - 800, innerHeight: 800, scrollHeight });
}

function setAtTop(scrollHeight = 3000) {
  setScrollMetrics({ scrollY: 0, innerHeight: 800, scrollHeight });
}

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  delete document.body.dataset.userIsAuthenticated;
  delete window.__archeologReady;
  setPath("/");
  setAtTop();

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => ({}) }),
  );
  window.showToast = vi.fn();
  delete window.EE_AUDIO;

  require(EASTER_EGGS_PATH);
  window.easterEggs._resetForTests();

  archeolog = require(ARCHEOLOG_PATH);
  archeolog._resetForTests();
});

afterEach(() => {
  window.easterEggs.teardownAll();
  archeolog._resetForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("path gate — isOnSucharyPath", () => {
  it("is true anywhere under /suchary", () => {
    setPath("/suchary");
    expect(archeolog.isOnSucharyPath()).toBe(true);
    setPath("/suchary/");
    expect(archeolog.isOnSucharyPath()).toBe(true);
    setPath("/suchary/add/");
    expect(archeolog.isOnSucharyPath()).toBe(true);
  });

  it("is false everywhere else", () => {
    setPath("/");
    expect(archeolog.isOnSucharyPath()).toBe(false);
    setPath("/achievements/");
    expect(archeolog.isOnSucharyPath()).toBe(false);
    setPath("/suchary-archiwum/");
    expect(archeolog.isOnSucharyPath()).toBe(false);
  });
});

describe("isNearBottom", () => {
  it("is true right at the bottom edge and beyond", () => {
    setAtBottom(3000);
    expect(archeolog.isNearBottom()).toBe(true);

    setScrollMetrics({ scrollY: 3000, innerHeight: 800, scrollHeight: 3000 });
    expect(archeolog.isNearBottom()).toBe(true);
  });

  it("is true within the bottom threshold", () => {
    setScrollMetrics({
      scrollY: 3000 - 800 - (archeolog.BOTTOM_THRESHOLD_PX - 10),
      innerHeight: 800,
      scrollHeight: 3000,
    });
    expect(archeolog.isNearBottom()).toBe(true);
  });

  it("is false well above the bottom", () => {
    setAtTop(3000);
    expect(archeolog.isNearBottom()).toBe(false);
  });
});

describe("getPaginationInfo / isEligibleLastPage", () => {
  it("returns null / false when there is no pagination at all", () => {
    expect(archeolog.getPaginationInfo()).toBeNull();
    expect(archeolog.isEligibleLastPage()).toBe(false);
  });

  it("is false when a next page exists, regardless of the page number", () => {
    makePagination({ currentPage: 12, hasNext: true });
    expect(archeolog.isEligibleLastPage()).toBe(false);
  });

  it(`is false on the last page when total pages < ${MIN_TOTAL_PAGES}`, () => {
    makePagination({ currentPage: MIN_TOTAL_PAGES - 1, hasNext: false });
    expect(archeolog.isEligibleLastPage()).toBe(false);
  });

  it(`is true on the last page with exactly ${MIN_TOTAL_PAGES} total pages`, () => {
    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    expect(archeolog.isEligibleLastPage()).toBe(true);
  });

  it("is true on the last page of a much longer list", () => {
    makePagination({ currentPage: 42, hasNext: false });
    expect(archeolog.isEligibleLastPage()).toBe(true);
  });
});

describe("handleScroll — end-to-end trigger", () => {
  it("awards and toasts when at the bottom of an eligible last page", () => {
    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();

    archeolog.handleScroll();

    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(window.showToast).toHaveBeenCalledWith(
      archeolog.TOAST_BODY,
      archeolog.TOAST_TITLE,
      "info",
    );
    expect(frontendEventPosts()).toHaveLength(1);
    expect(JSON.parse(frontendEventPosts()[0][1].body)).toEqual({
      event_slug: SLUG,
    });
  });

  it("does nothing when scrolled to the bottom but not on the last page", () => {
    makePagination({ currentPage: 3, hasNext: true });
    setAtBottom();

    archeolog.handleScroll();

    expect(window.showToast).not.toHaveBeenCalled();
    expect(frontendEventPosts()).toHaveLength(0);
  });

  it(`does nothing on the last page of a list under ${MIN_TOTAL_PAGES} pages`, () => {
    makePagination({ currentPage: MIN_TOTAL_PAGES - 1, hasNext: false });
    setAtBottom();

    archeolog.handleScroll();

    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("does nothing on the eligible last page while not near the bottom", () => {
    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtTop();

    archeolog.handleScroll();

    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("throttles rapid scroll events — a second call within the window is a no-op", () => {
    vi.useFakeTimers();
    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    // Not at the bottom, so the first (throttle-consuming) call fires nothing.
    setAtTop();
    archeolog.handleScroll();

    setAtBottom();
    // Still inside the throttle window — the eligible geometry is ignored.
    vi.advanceTimersByTime(archeolog.SCROLL_THROTTLE_MS - 50);
    archeolog.handleScroll();
    expect(window.showToast).not.toHaveBeenCalled();

    // Past the throttle window — now it's checked and fires.
    vi.advanceTimersByTime(100);
    archeolog.handleScroll();
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("fires once per page load — settles and never re-triggers or re-checks", () => {
    vi.useFakeTimers();
    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();

    archeolog.handleScroll();
    expect(window.showToast).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(archeolog.SCROLL_THROTTLE_MS * 5);
    archeolog.handleScroll();
    archeolog.handleScroll();

    // Settled — no second toast and no second award POST this session.
    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(frontendEventPosts()).toHaveLength(1);
  });
});

describe("teardown / reset", () => {
  function dispatchScroll() {
    window.dispatchEvent(new Event("scroll"));
  }

  it("teardownArcheolog detaches the scroll listener", () => {
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/suchary/");
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(window.__archeologReady).toBe(true);

    archeolog.teardownArcheolog();

    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();
    dispatchScroll();

    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("_resetForTests clears the settled flag so a fresh scroll is re-evaluated", () => {
    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();
    archeolog.handleScroll();
    expect(window.showToast).toHaveBeenCalledTimes(1);

    archeolog._resetForTests();
    window.easterEggs._resetForTests();
    sessionStorage.clear(); // fresh session dedupe too — award() also checks storage

    archeolog.handleScroll();
    expect(window.showToast).toHaveBeenCalledTimes(2);
  });
});

describe("DOMContentLoaded init", () => {
  function dispatchScroll() {
    window.dispatchEvent(new Event("scroll"));
  }

  it("wires the listener for an authed body on /suchary and flips __archeologReady", () => {
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/suchary/");
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__archeologReady).toBe(true);

    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();
    dispatchScroll();

    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("does not wire the listener for an anonymous body", () => {
    document.body.dataset.userIsAuthenticated = "false";
    setPath("/suchary/");
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__archeologReady).toBe(true);

    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();
    dispatchScroll();

    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("does not wire the listener off the suchar list", () => {
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/achievements/");
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__archeologReady).toBe(true);

    makePagination({ currentPage: MIN_TOTAL_PAGES, hasNext: false });
    setAtBottom();
    dispatchScroll();

    expect(window.showToast).not.toHaveBeenCalled();
  });
});
