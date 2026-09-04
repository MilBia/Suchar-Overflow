/**
 * Unit tests for the "spin the logo" easter egg in
 * suchar_overflow/static/js/features/logo_spin.js (issue #285).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so the tests drive the exported helpers directly.
 *
 * The real `features/easter_eggs.js` is wired in first so `window.easterEggs`
 * (the reduced-motion gate this egg delegates to) behaves for real.
 * `vi.resetModules()` re-runs neither required CJS module, so both expose
 * `_resetForTests()` for the per-test cleanup.
 *
 * Trigger model: the logo is an `<a href="/">`, so every click navigates and
 * the count cannot live in memory. `handleLogoClick` records a "chain" in
 * sessionStorage (each click within 3 s of the previous bumps `count`);
 * `checkAndFire` runs on the next page load and fires the effect once `count`
 * reaches the threshold while the chain is still fresh.
 *
 * Pure delight: NO achievement, NO frontend-ee- slug, NO network. Several
 * tests assert `globalThis.fetch` and `easterEggs.award` are never called.
 */
const path = require("node:path");

const LOGO_SPIN_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/logo_spin.js",
);
const EASTER_EGGS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);

const STYLE_ID = "ee-logo-spin-style";
const SPIN_CLASS = "ee-logo-spin";
const POOL_ID = "ee-logo-suchary";
const THRESHOLD = 7;
const CHAIN_MS = 3000;
const POOL = [
  "Suchość powietrza: 12%. Suchość tego suchara: 98%.",
  "Ten serwis zasilany jest wyłącznie sucharami z odzysku.",
  "Wykryto suchar klasy premium. Nawilżanie niedostępne.",
];

let logoSpin;

/** Fire the logo click handler as a plain primary-button click. */
function click(extra) {
  logoSpin.handleLogoClick({ button: 0, ...(extra ?? {}) });
}

/** N quick clicks, 100 ms apart (well inside the 3 s chain window). */
function rapidClicks(n) {
  for (let i = 0; i < n; i += 1) {
    click();
    vi.advanceTimersByTime(100);
  }
}

function setPool(arr) {
  const s = document.createElement("script");
  s.type = "application/json";
  s.id = POOL_ID;
  s.textContent = JSON.stringify(arr);
  document.body.appendChild(s);
}

function styleEl() {
  return document.getElementById(STYLE_ID);
}

function logoEl() {
  return document.querySelector(".navbar-brand");
}

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = '<a class="navbar-brand" href="/"></a>';
  setPool(POOL);
  // innerHTML reset drops children but not <body>'s own attributes / window flags.
  delete document.body.dataset.userIsAuthenticated;
  delete window.__logoSpinReady;
  styleEl()?.remove();

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => ({}) }),
  );
  window.showToast = vi.fn();
  delete window.EE_AUDIO;
  delete window.matchMedia; // jsdom: absence => reducedJuice() === true

  require(EASTER_EGGS_PATH);
  window.easterEggs._resetForTests();

  logoSpin = require(LOGO_SPIN_PATH);
  logoSpin._resetForTests();
});

afterEach(() => {
  window.easterEggs.teardownAll();
  logoSpin._resetForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("click chain — handleLogoClick", () => {
  it("records the first click as a chain of length 1", () => {
    click();
    const state = JSON.parse(sessionStorage.getItem("ee_logo_clicks"));
    expect(state.count).toBe(1);
    expect(typeof state.last).toBe("number");
  });

  it("bumps the chain while clicks stay within 3 s of each other", () => {
    rapidClicks(4);
    expect(JSON.parse(sessionStorage.getItem("ee_logo_clicks")).count).toBe(4);
  });

  it("caps the stored count at the threshold", () => {
    rapidClicks(THRESHOLD + 5);
    expect(JSON.parse(sessionStorage.getItem("ee_logo_clicks")).count).toBe(
      THRESHOLD,
    );
  });

  it("restarts the chain when the gap since the last click exceeds 3 s", () => {
    rapidClicks(4);
    vi.advanceTimersByTime(CHAIN_MS + 500);
    click();
    expect(JSON.parse(sessionStorage.getItem("ee_logo_clicks")).count).toBe(1);
  });

  it("never fires the effect itself (that is checkAndFire's job on next load)", () => {
    rapidClicks(THRESHOLD + 2);
    expect(window.showToast).not.toHaveBeenCalled();
    expect(styleEl()).toBeNull();
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(false);
  });

  it("ignores non-primary mouse buttons", () => {
    click({ button: 1 });
    click({ button: 2 });
    expect(sessionStorage.getItem("ee_logo_clicks")).toBeNull();
  });

  it("ignores clicks chorded with Ctrl / Alt / Meta / Shift", () => {
    click({ ctrlKey: true });
    click({ altKey: true });
    click({ metaKey: true });
    click({ shiftKey: true });
    expect(sessionStorage.getItem("ee_logo_clicks")).toBeNull();
  });

  it("never touches the network or the achievement system", () => {
    const award = vi.spyOn(window.easterEggs, "award");
    rapidClicks(THRESHOLD);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(award).not.toHaveBeenCalled();
  });
});

describe("checkAndFire — on page load", () => {
  it("does nothing with fewer than 7 clicks in the chain", () => {
    rapidClicks(THRESHOLD - 1);
    expect(logoSpin.checkAndFire()).toBe(false);
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("fires the effect once the chain reaches 7 fresh clicks", () => {
    rapidClicks(THRESHOLD);
    expect(logoSpin.checkAndFire()).toBe(true);
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("clears the chain after firing so a replay needs another 7 clicks", () => {
    rapidClicks(THRESHOLD);
    logoSpin.checkAndFire();
    expect(sessionStorage.getItem("ee_logo_clicks")).toBeNull();
    expect(logoSpin.checkAndFire()).toBe(false);
  });

  it("replays on a fresh burst of 7 (not one-shot)", () => {
    rapidClicks(THRESHOLD);
    expect(logoSpin.checkAndFire()).toBe(true);
    logoSpin._resetForTests();
    window.showToast.mockClear();

    rapidClicks(THRESHOLD);
    expect(logoSpin.checkAndFire()).toBe(true);
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("does not fire when the 7-click chain has gone stale before load", () => {
    rapidClicks(THRESHOLD);
    vi.advanceTimersByTime(CHAIN_MS + 500);
    expect(logoSpin.checkAndFire()).toBe(false);
    expect(window.showToast).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("ee_logo_clicks")).toBeNull();
  });

  it("does not fire when a 3 s gap broke the chain mid-way", () => {
    rapidClicks(4);
    vi.advanceTimersByTime(CHAIN_MS + 500);
    rapidClicks(3);
    expect(logoSpin.checkAndFire()).toBe(false);
  });

  it("keeps a still-building chain in storage across loads", () => {
    rapidClicks(3);
    expect(logoSpin.checkAndFire()).toBe(false);
    expect(JSON.parse(sessionStorage.getItem("ee_logo_clicks")).count).toBe(3);
  });

  it("does nothing with no stored chain", () => {
    expect(logoSpin.checkAndFire()).toBe(false);
  });

  it("does nothing with garbage in storage", () => {
    sessionStorage.setItem("ee_logo_clicks", "not json");
    expect(logoSpin.checkAndFire()).toBe(false);
    sessionStorage.setItem("ee_logo_clicks", JSON.stringify({ foo: 1 }));
    expect(logoSpin.checkAndFire()).toBe(false);
  });

  it("never touches the network or the achievement system when firing", () => {
    const award = vi.spyOn(window.easterEggs, "award");
    rapidClicks(THRESHOLD);
    logoSpin.checkAndFire();
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(award).not.toHaveBeenCalled();
  });
});

describe("effect — triggerLogoSpin", () => {
  it("shows a toast whose text is one of the pool entries", () => {
    logoSpin.triggerLogoSpin();
    expect(window.showToast).toHaveBeenCalledTimes(1);
    const [text, icon, type] = window.showToast.mock.calls[0];
    expect(POOL).toContain(text);
    expect(icon).toBe("🌀");
    expect(type).toBe("info");
  });

  it("spins the logo: adds the class and injects the @keyframes block", () => {
    window.matchMedia = vi.fn(() => ({ matches: false }));
    logoSpin.triggerLogoSpin();
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(true);
    expect(styleEl()).not.toBeNull();
    expect(styleEl().textContent).toContain("@keyframes ee-logo-spin");
  });

  it("removes the spin class once the animation window elapses", () => {
    window.matchMedia = vi.fn(() => ({ matches: false }));
    logoSpin.triggerLogoSpin();
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(true);
    vi.advanceTimersByTime(2000);
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(false);
  });

  it("injects the <style> only once across repeated triggers", () => {
    window.matchMedia = vi.fn(() => ({ matches: false }));
    logoSpin.triggerLogoSpin();
    logoSpin.triggerLogoSpin();
    expect(document.querySelectorAll(`#${STYLE_ID}`).length).toBe(1);
  });

  it("shows the toast but does not spin under prefers-reduced-motion (no matchMedia)", () => {
    logoSpin.triggerLogoSpin();
    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(false);
    expect(styleEl()).toBeNull();
  });

  it("does not spin when easterEggs.reducedJuice() is true", () => {
    window.matchMedia = vi.fn(() => ({ matches: false }));
    vi.spyOn(window.easterEggs, "reducedJuice").mockReturnValue(true);
    logoSpin.triggerLogoSpin();
    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(false);
  });

  it("spins under full motion when reduced motion is not requested", () => {
    window.matchMedia = vi.fn(() => ({ matches: false }));
    logoSpin.triggerLogoSpin();
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(true);
    expect(styleEl()).not.toBeNull();
  });

  it("skips the toast when the pool element is absent", () => {
    document.getElementById(POOL_ID).remove();
    window.matchMedia = vi.fn(() => ({ matches: false }));
    logoSpin.triggerLogoSpin();
    expect(window.showToast).not.toHaveBeenCalled();
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(true);
  });

  it("skips the toast when the pool is an empty array", () => {
    document.getElementById(POOL_ID).textContent = "[]";
    logoSpin.triggerLogoSpin();
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("does not throw when the logo is missing from the DOM", () => {
    logoEl().remove();
    window.matchMedia = vi.fn(() => ({ matches: false }));
    expect(() => logoSpin.triggerLogoSpin()).not.toThrow();
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });
});

describe("teardown / _resetForTests", () => {
  it("removes the injected style, the spin class and the stored chain", () => {
    window.matchMedia = vi.fn(() => ({ matches: false }));
    rapidClicks(THRESHOLD);
    logoSpin.triggerLogoSpin();

    logoSpin.teardownLogoSpin();

    expect(styleEl()).toBeNull();
    expect(logoEl().classList.contains(SPIN_CLASS)).toBe(false);
    expect(sessionStorage.getItem("ee_logo_clicks")).toBeNull();
  });
});
