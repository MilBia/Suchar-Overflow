/**
 * Unit tests for the "Niezdecydowany" theme-toggle-spam easter egg in
 * suchar_overflow/static/js/features/theme_spam.js (issue #289).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so most tests drive the exported helpers directly.
 *
 * The real `features/easter_eggs.js` is wired in first so `window.easterEggs`
 * (the deduped award + reduced-motion gate this egg delegates to) behaves for
 * real. `vi.resetModules()` does not re-run a required CJS module, so both
 * modules expose `_resetForTests()` for the per-test cleanup.
 */
const path = require("node:path");

const THEME_SPAM_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/theme_spam.js",
);
const EASTER_EGGS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);

const SLUG = "frontend-ee-niezdecydowany";
const STYLE_ID = "ee-theme-spam-style";
const SPIN_CLASS = "ee-toggle-spin";
const THRESHOLD = 10;

let themeSpam;

function frontendEventPosts() {
  return globalThis.fetch.mock.calls.filter(
    ([url]) => url === "/api/achievements/frontend-event",
  );
}

function makeToggleButton() {
  const btn = document.createElement("button");
  btn.id = "theme-toggle";
  document.body.appendChild(btn);
  return btn;
}

/**
 * Feed `count` clicks into the exported handler, `gapMs` apart, advancing the
 * fake clock between them. Calls the handler directly (like konami.test.js
 * calls `handleKeydown` directly) rather than dispatching DOM `click` events —
 * the real listener is only attached by the module's own DOMContentLoaded
 * init, which most of these tests don't run.
 */
function clickToggle(count, gapMs) {
  for (let i = 0; i < count; i += 1) {
    if (i > 0) vi.advanceTimersByTime(gapMs);
    themeSpam.handleToggleClick();
  }
}

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-theme");
  document.head.querySelector(`#${STYLE_ID}`)?.remove();

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({}) }));
  window.showToast = vi.fn();
  delete window.EE_AUDIO;
  delete window.matchMedia; // jsdom: absence => reducedJuice() === true

  require(EASTER_EGGS_PATH);
  window.easterEggs._resetForTests();

  themeSpam = require(THEME_SPAM_PATH);
  themeSpam._resetForTests();
});

afterEach(() => {
  window.easterEggs.teardownAll();
  themeSpam._resetForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("click-window matcher — handleToggleClick", () => {
  it("fires on 10 clicks within the 5s window", () => {
    vi.useFakeTimers();

    clickToggle(THRESHOLD, 400); // 9 * 400ms = 3.6s, inside the window

    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(frontendEventPosts()).toHaveLength(1);
    expect(JSON.parse(frontendEventPosts()[0][1].body)).toEqual({
      event_slug: SLUG,
    });
  });

  it("does NOT fire when the 10 clicks are spread past 5s (fake-clock canary)", () => {
    vi.useFakeTimers();

    clickToggle(THRESHOLD, 600); // 9 * 600ms = 5.4s, past the window

    expect(window.showToast).not.toHaveBeenCalled();
    expect(frontendEventPosts()).toHaveLength(0);
  });

  it("does nothing on 9 clicks (below the threshold)", () => {
    vi.useFakeTimers();

    clickToggle(THRESHOLD - 1, 100);

    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("is a sliding window of the last 10 clicks, not a rolling counter", () => {
    vi.useFakeTimers();

    // 5 slow clicks (well outside any 5s window with the next batch), then a
    // fast burst of 10 — only the last 10 should ever be evaluated together.
    clickToggle(5, 2000);
    clickToggle(THRESHOLD, 200);

    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("replays the effect on a fresh burst of 10, but POSTs the award only once", () => {
    vi.useFakeTimers();

    clickToggle(THRESHOLD, 200);
    clickToggle(THRESHOLD, 200);

    expect(window.showToast).toHaveBeenCalledTimes(2);
    expect(frontendEventPosts()).toHaveLength(1); // sessionStorage dedupe
  });

  it("does not touch the theme — never writes localStorage.theme or data-theme", () => {
    vi.useFakeTimers();
    localStorage.setItem("theme", "dark");
    document.documentElement.setAttribute("data-theme", "dark");

    clickToggle(THRESHOLD, 200);

    expect(localStorage.getItem("theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});

describe("triggerThemeSpam — spin effect", () => {
  it("full-motion path: adds the spin class and injects keyframes", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    const btn = makeToggleButton();

    themeSpam.triggerThemeSpam();

    expect(btn.classList.contains(SPIN_CLASS)).toBe(true);
    expect(document.getElementById(STYLE_ID)).toBeTruthy();
  });

  it("reduced-motion path: no spin class, no keyframes injected", () => {
    // matchMedia absent => easterEggs.reducedJuice() === true
    const btn = makeToggleButton();

    themeSpam.triggerThemeSpam();

    expect(btn.classList.contains(SPIN_CLASS)).toBe(false);
    expect(document.getElementById(STYLE_ID)).toBeNull();
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("strips the spin class after the animation", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    const btn = makeToggleButton();

    themeSpam.triggerThemeSpam();
    expect(btn.classList.contains(SPIN_CLASS)).toBe(true);

    vi.advanceTimersByTime(1000);
    expect(btn.classList.contains(SPIN_CLASS)).toBe(false);
  });

  it("does nothing when #theme-toggle is missing", () => {
    expect(() => themeSpam.triggerThemeSpam()).not.toThrow();
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });
});

/**
 * Dispatch `count` real DOM `click` events on `btn`, `gapMs` apart, advancing
 * the fake clock between them. Unlike `clickToggle()`, this exercises the
 * module's actual attached listener — used only where wiring itself (attach /
 * detach) is under test.
 */
function dispatchClicks(btn, count, gapMs) {
  for (let i = 0; i < count; i += 1) {
    if (i > 0) vi.advanceTimersByTime(gapMs);
    btn.dispatchEvent(new Event("click"));
  }
}

describe("teardown / reset", () => {
  it("_resetForTests clears the click buffer", () => {
    vi.useFakeTimers();
    clickToggle(THRESHOLD - 1, 100); // mid-burst, not yet fired

    themeSpam._resetForTests();

    clickToggle(THRESHOLD - 1, 100); // alone, must not complete the burst
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("teardownThemeSpam detaches the click listener", () => {
    document.body.dataset.userIsAuthenticated = "true";
    const btn = makeToggleButton();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(window.__themeSpamReady).toBe(true);

    themeSpam.teardownThemeSpam();

    vi.useFakeTimers();
    dispatchClicks(btn, THRESHOLD, 100);
    expect(window.showToast).not.toHaveBeenCalled();
  });
});

describe("DOMContentLoaded init", () => {
  it("wires the listener for an authed body and flips __themeSpamReady", () => {
    delete window.__themeSpamReady;
    document.body.dataset.userIsAuthenticated = "true";
    const btn = makeToggleButton();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__themeSpamReady).toBe(true);

    vi.useFakeTimers();
    dispatchClicks(btn, THRESHOLD, 100);
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("does not wire the listener for an anonymous body", () => {
    delete window.__themeSpamReady;
    document.body.dataset.userIsAuthenticated = "false";
    const btn = makeToggleButton();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__themeSpamReady).toBe(true);

    vi.useFakeTimers();
    dispatchClicks(btn, THRESHOLD, 100);
    expect(window.showToast).not.toHaveBeenCalled();
  });
});
