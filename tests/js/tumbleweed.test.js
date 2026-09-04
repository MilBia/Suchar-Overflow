/**
 * Unit tests for the "tumbleweed after inactivity" easter egg in
 * suchar_overflow/static/js/features/tumbleweed.js (issue #288).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so most tests drive the exported helpers directly.
 *
 * The real `features/easter_eggs.js` is wired in first so `window.easterEggs`
 * (the reduced-motion gate this egg delegates to) behaves for real.
 * `vi.resetModules()` re-runs neither required CJS module, so both expose
 * `_resetForTests()` for the per-test cleanup.
 *
 * This egg is pure delight: no achievement, no slug, no network. Several tests
 * assert `globalThis.fetch` and `window.easterEggs.award` are never called.
 */
const path = require("node:path");

const TUMBLEWEED_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/tumbleweed.js",
);
const EASTER_EGGS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);

const STYLE_ID = "ee-tumbleweed-style";
const OVERLAY_SELECTOR = "div.ee-tumbleweed-overlay";
const IDLE_MS = 120000;
const COOLDOWN_MS = 300000;
const STORAGE_KEY = "ee_tumbleweed_last";

let tumbleweed;

function overlays() {
  return [...document.body.querySelectorAll(OVERLAY_SELECTOR)];
}

/** Put jsdom's `location.pathname` where the test needs it. */
function setPath(pathname) {
  window.history.pushState({}, "", pathname);
}

/** Authenticate + place on /suchary + (re)fire the module's init. */
function initOnSucharyList() {
  document.body.dataset.userIsAuthenticated = "true";
  setPath("/suchary/");
  tumbleweed.initTumbleweed();
}

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  // innerHTML = "" drops children but not <body>'s own attributes / window flags.
  delete document.body.dataset.userIsAuthenticated;
  delete window.__tumbleweedReady;
  document.head.querySelector(`#${STYLE_ID}`)?.remove();
  setPath("/");

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => ({}) }),
  );
  window.showToast = vi.fn();
  delete window.EE_AUDIO;
  delete window.matchMedia; // jsdom: absence => reducedJuice() === true

  require(EASTER_EGGS_PATH);
  window.easterEggs._resetForTests();

  tumbleweed = require(TUMBLEWEED_PATH);
  tumbleweed._resetForTests();
});

afterEach(() => {
  window.easterEggs.teardownAll();
  tumbleweed._resetForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("path gate — isOnSucharyPath", () => {
  it("is true anywhere under /suchary", () => {
    setPath("/suchary");
    expect(tumbleweed.isOnSucharyPath()).toBe(true);
    setPath("/suchary/");
    expect(tumbleweed.isOnSucharyPath()).toBe(true);
    setPath("/suchary/add/");
    expect(tumbleweed.isOnSucharyPath()).toBe(true);
  });

  it("is false everywhere else", () => {
    setPath("/");
    expect(tumbleweed.isOnSucharyPath()).toBe(false);
    setPath("/achievements/");
    expect(tumbleweed.isOnSucharyPath()).toBe(false);
    setPath("/stats/leaderboard/");
    expect(tumbleweed.isOnSucharyPath()).toBe(false);
  });

  it("does not match a look-alike sibling route (prefix, not substring)", () => {
    setPath("/suchary-archiwum/");
    expect(tumbleweed.isOnSucharyPath()).toBe(false);
    setPath("/sucharyy");
    expect(tumbleweed.isOnSucharyPath()).toBe(false);
  });
});

describe("idle timer", () => {
  it("rolls a tumbleweed after IDLE_MS of inactivity on /suchary", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    expect(overlays()).toHaveLength(0);
    vi.advanceTimersByTime(IDLE_MS);

    expect(overlays()).toHaveLength(1);
    expect(document.getElementById(STYLE_ID)).toBeTruthy();
  });

  it("does nothing before the idle threshold is reached", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS - 1);
    expect(overlays()).toHaveLength(0);
  });

  it("any activity resets the idle countdown", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS - 1);
    tumbleweed.handleActivity();
    vi.advanceTimersByTime(IDLE_MS - 1);
    expect(overlays()).toHaveLength(0);

    vi.advanceTimersByTime(1);
    expect(overlays()).toHaveLength(1);
  });

  it("resets on a real event dispatched at the listened target", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS - 1);
    window.dispatchEvent(new Event("mousemove"));
    vi.advanceTimersByTime(IDLE_MS - 1);
    expect(overlays()).toHaveLength(0);

    vi.advanceTimersByTime(1);
    expect(overlays()).toHaveLength(1);
  });

  it("treats a touch/pen `pointerdown` as activity (mobile has no mousemove)", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS - 1);
    window.dispatchEvent(new Event("pointerdown"));
    vi.advanceTimersByTime(IDLE_MS - 1);
    expect(overlays()).toHaveLength(0);
  });

  it("throttles a burst of activity — only the first re-arm inside the window counts", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    // First reset lands the next fire at (IDLE_MS - 2000) + IDLE_MS.
    vi.advanceTimersByTime(IDLE_MS - 2000);
    tumbleweed.handleActivity();
    // 500 ms later (< ACTIVITY_THROTTLE_MS) a second reset is ignored, so the
    // fire time does NOT move to (IDLE_MS - 1500) + IDLE_MS.
    vi.advanceTimersByTime(500);
    tumbleweed.handleActivity();

    vi.advanceTimersByTime(IDLE_MS - 500); // total: 2*IDLE_MS - 2000
    expect(overlays()).toHaveLength(1);
  });

  it("does not roll while the tab is backgrounded, and does not burn the cooldown", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    const hidden = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS * 2);
    expect(overlays()).toHaveLength(0);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();

    // Back to the foreground: the next idle window rolls it.
    hidden.mockReturnValue("visible");
    vi.advanceTimersByTime(IDLE_MS);
    expect(overlays()).toHaveLength(1);
  });

  it("never arms the timer off /suchary", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/");
    tumbleweed.initTumbleweed();

    vi.advanceTimersByTime(IDLE_MS * 3);
    expect(overlays()).toHaveLength(0);
  });

  it("never arms the timer for an anonymous visitor", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    document.body.dataset.userIsAuthenticated = "false";
    setPath("/suchary/");
    tumbleweed.initTumbleweed();

    vi.advanceTimersByTime(IDLE_MS * 3);
    expect(overlays()).toHaveLength(0);
  });
});

describe("cooldown", () => {
  it("does not fire again within COOLDOWN_MS of the last roll", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS);
    expect(overlays()).toHaveLength(1);
    overlays()[0].remove(); // clear the DOM so a second roll would be visible

    // Another full idle window passes, but we are still within the cooldown.
    vi.advanceTimersByTime(IDLE_MS);
    expect(overlays()).toHaveLength(0);
  });

  it("fires again once the cooldown has elapsed", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS);
    overlays()[0].remove();

    // Once COOLDOWN_MS has elapsed since that first roll, the next idle check
    // (re-armed to land exactly on the lapse) rolls another one.
    vi.advanceTimersByTime(COOLDOWN_MS);
    expect(overlays()).toHaveLength(1);
  });

  it("records the fire time in sessionStorage", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS);

    const stored = Number(sessionStorage.getItem(STORAGE_KEY));
    expect(stored).toBe(Date.now());
    expect(tumbleweed.onCooldown()).toBe(true);
  });

  it("a stored fire time from a prior page load suppresses the roll", () => {
    vi.useFakeTimers();
    sessionStorage.setItem(STORAGE_KEY, String(Date.now()));
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    initOnSucharyList();

    vi.advanceTimersByTime(IDLE_MS);
    expect(overlays()).toHaveLength(0);
  });

  it("ignores a future timestamp (system clock wound back) rather than wedging", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    sessionStorage.setItem(STORAGE_KEY, String(Date.now() + 60 * 60 * 1000));

    expect(tumbleweed.onCooldown()).toBe(false);

    initOnSucharyList();
    vi.advanceTimersByTime(IDLE_MS);
    expect(overlays()).toHaveLength(1);
  });

  it("does not throw when sessionStorage.setItem throws (private mode / quota)", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("storage blocked");
      });
    initOnSucharyList();

    expect(() => vi.advanceTimersByTime(IDLE_MS)).not.toThrow();
    expect(overlays()).toHaveLength(1); // the visual effect still runs

    setItem.mockRestore();
  });
});

describe("rollTumbleweed — full motion", () => {
  beforeEach(() => {
    // Fake timers here too: triggerTumbleweed() schedules the removal timeout,
    // and a real Node timer would otherwise outlive the test.
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
  });

  it("appends an overlay carrying an <svg> and the caption", () => {
    tumbleweed.triggerTumbleweed();

    const overlay = overlays()[0];
    expect(overlay).toBeTruthy();
    expect(overlay.querySelector("svg")).toBeTruthy();
    expect(overlay.textContent).toContain(tumbleweed.CAPTION);
  });

  it("injects the @keyframes <style> once", () => {
    tumbleweed.triggerTumbleweed();
    tumbleweed.triggerTumbleweed();
    expect(document.head.querySelectorAll(`#${STYLE_ID}`)).toHaveLength(1);
  });

  it("does not fire a toast in the full-motion path", () => {
    tumbleweed.triggerTumbleweed();
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("builds the caption with textContent, not markup", () => {
    tumbleweed.triggerTumbleweed();
    const overlay = overlays()[0];
    // The caption node holds text only — no injected elements.
    const caption = overlay.querySelector(".ee-tumbleweed-caption");
    expect(caption).toBeTruthy();
    expect(caption.children).toHaveLength(0);
    expect(caption.textContent).toBe(tumbleweed.CAPTION);
  });

  it("carries no id on the visual particles (only the <style> has one)", () => {
    tumbleweed.triggerTumbleweed();
    expect(overlays()[0].querySelectorAll("[id]")).toHaveLength(0);
  });

  it("removes the overlay after its lifetime", () => {
    tumbleweed.triggerTumbleweed();
    expect(overlays()).toHaveLength(1);

    vi.advanceTimersByTime(tumbleweed.OVERLAY_LIFETIME_MS + 100);
    expect(overlays()).toHaveLength(0);
  });

  it("never touches the network or the achievement system (pure delight)", () => {
    const award = vi.spyOn(window.easterEggs, "award");
    tumbleweed.triggerTumbleweed();
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(award).not.toHaveBeenCalled();
  });
});

describe("rollTumbleweed — prefers-reduced-motion", () => {
  it("surfaces the caption as a toast and skips the overlay entirely", () => {
    // matchMedia absent => easterEggs.reducedJuice() === true
    tumbleweed.triggerTumbleweed();

    expect(window.showToast).toHaveBeenCalledWith(
      tumbleweed.CAPTION,
      "🌾",
      "info",
    );
    expect(overlays()).toHaveLength(0);
    expect(document.getElementById(STYLE_ID)).toBeNull();
  });

  it("falls back to matchMedia when window.easterEggs is missing", () => {
    window.matchMedia = vi.fn((q) => ({ matches: true, media: q }));
    const saved = window.easterEggs;
    delete window.easterEggs;
    try {
      tumbleweed.triggerTumbleweed();
      expect(window.showToast).toHaveBeenCalledTimes(1);
      expect(overlays()).toHaveLength(0);
    } finally {
      window.easterEggs = saved;
    }
  });

  it("does not throw when window.showToast is unavailable", () => {
    delete window.showToast;
    expect(() => tumbleweed.triggerTumbleweed()).not.toThrow();
  });
});

describe("teardown / reset", () => {
  it("teardownTumbleweed detaches the activity listeners and the idle timer", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/suchary/");
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(window.__tumbleweedReady).toBe(true);

    tumbleweed.teardownTumbleweed();

    // A real scroll event must no longer re-arm anything, and the pending
    // timer must be gone.
    window.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(IDLE_MS * 3);
    expect(overlays()).toHaveLength(0);
  });

  it("_resetForTests clears the overlay, the <style> and the cooldown marker", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    tumbleweed.triggerTumbleweed();
    sessionStorage.setItem(STORAGE_KEY, String(Date.now()));

    tumbleweed._resetForTests();

    expect(overlays()).toHaveLength(0);
    expect(document.getElementById(STYLE_ID)).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe("DOMContentLoaded init", () => {
  it("wires the timer for an authed body on /suchary and flips __tumbleweedReady", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/suchary/");
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__tumbleweedReady).toBe(true);
    vi.advanceTimersByTime(IDLE_MS);
    expect(overlays()).toHaveLength(1);
  });

  it("flips __tumbleweedReady but stays inert off /suchary", () => {
    vi.useFakeTimers();
    document.body.dataset.userIsAuthenticated = "true";
    setPath("/");
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__tumbleweedReady).toBe(true);
    vi.advanceTimersByTime(IDLE_MS * 3);
    expect(overlays()).toHaveLength(0);
  });

  it("flips __tumbleweedReady but stays inert for an anonymous body", () => {
    vi.useFakeTimers();
    document.body.dataset.userIsAuthenticated = "false";
    setPath("/suchary/");
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__tumbleweedReady).toBe(true);
    vi.advanceTimersByTime(IDLE_MS * 3);
    expect(overlays()).toHaveLength(0);
  });
});
