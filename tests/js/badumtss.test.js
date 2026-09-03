/**
 * Unit tests for the "ba dum tss" / dust easter egg in
 * suchar_overflow/static/js/features/badumtss.js (issue #284).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so most tests drive the exported helpers directly.
 *
 * The real `features/easter_eggs.js` is wired in first so `window.easterEggs`
 * (the reduced-motion gate + muted sound helper this egg delegates to) behaves
 * for real. `vi.resetModules()` re-runs neither required CJS module, so both
 * expose `_resetForTests()` for the per-test cleanup.
 *
 * This egg is pure delight: no achievement, no slug, no network. Several tests
 * assert `globalThis.fetch` is never called.
 */
const path = require("node:path");

const BADUMTSS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/badumtss.js",
);
const EASTER_EGGS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);

const STYLE_ID = "ee-badumtss-style";
const IDLE_MS = 2000;
const DUST_PARTICLES = 24;

let badumtss;

/** Feed a string one `keydown` at a time through the exported handler. */
function type(text, extra) {
  [...text].forEach((ch) =>
    badumtss.handleKeydown({ key: ch, target: null, ...(extra ?? {}) }),
  );
}

function overlays() {
  return [...document.body.querySelectorAll("div.ee-dust-overlay")];
}

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  document.head.querySelector(`#${STYLE_ID}`)?.remove();

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => ({}) }),
  );
  window.showToast = vi.fn();
  delete window.EE_AUDIO;
  delete window.matchMedia; // jsdom: absence => reducedJuice() === true

  require(EASTER_EGGS_PATH);
  window.easterEggs._resetForTests();

  badumtss = require(BADUMTSS_PATH);
  badumtss._resetForTests();
});

afterEach(() => {
  window.easterEggs.teardownAll();
  badumtss._resetForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("phrase matcher — handleKeydown", () => {
  it("fires on 'suchar'", () => {
    type("suchar");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("fires on 'badumtss'", () => {
    type("badumtss");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("fires on 'ba dum tss' (spaces are part of the phrase)", () => {
    type("ba dum tss");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("shows the 🥁 toast with the canned text", () => {
    type("suchar");
    expect(window.showToast).toHaveBeenCalledWith("ba dum tss", "🥁", "success");
  });

  it("does nothing on a partial phrase", () => {
    type("sucha");
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("matches a phrase typed after junk keys", () => {
    type("qwe123");
    type("suchar");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("matches when the phrase is a suffix of a longer word", () => {
    type("niesuchar");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("never touches the network (pure delight — no achievement)", () => {
    type("suchar");
    type("badumtss");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("ignores keystrokes typed into a form field", () => {
    type("suchar", { target: { tagName: "INPUT" } });
    type("suchar", { target: { tagName: "TEXTAREA" } });
    type("suchar", { target: { tagName: "SELECT" } });
    type("suchar", { target: { isContentEditable: true } });
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("ignores chords with a Ctrl / Alt / Meta modifier", () => {
    type("suchar", { ctrlKey: true });
    type("suchar", { altKey: true });
    type("suchar", { metaKey: true });
    expect(window.showToast).not.toHaveBeenCalled();

    // A stray Ctrl+x mid-word is dropped, not buffered — the word still lands.
    type("suc");
    type("x", { ctrlKey: true });
    type("har");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("only buffers single-character keys, not named keys", () => {
    type("sucha");
    badumtss.handleKeydown({ key: "Shift", target: null });
    badumtss.handleKeydown({ key: "ArrowLeft", target: null });
    type("r");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("replays the effect on every entry (no dedupe)", () => {
    type("suchar");
    type("suchar");
    type("badumtss");
    expect(window.showToast).toHaveBeenCalledTimes(3);
  });
});

describe("idle buffer clear", () => {
  it("clears the buffer after the idle timeout so a split phrase does not fire", () => {
    vi.useFakeTimers();
    type("sucha");
    vi.advanceTimersByTime(IDLE_MS + 1);
    type("r");
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("keeps the buffer alive while typing continues within the idle window", () => {
    vi.useFakeTimers();
    type("suc");
    vi.advanceTimersByTime(IDLE_MS - 100);
    type("har");
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });
});

describe("dustBurst", () => {
  it("full-motion path: injects keyframes and spawns drifting particles", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));

    badumtss.triggerBaDumTss();

    const overlay = overlays()[0];
    expect(overlay).toBeTruthy();
    expect(document.getElementById(STYLE_ID)).toBeTruthy();

    const motes = overlay.querySelectorAll("div");
    expect(motes).toHaveLength(DUST_PARTICLES);
    expect(motes[0].style.animationName).toBe("ee-badumtss-drift");
    expect(motes[0].style.getPropertyValue("--ee-dx")).toMatch(/vw$/);
  });

  it("reduced-motion path: toast only — no overlay, no keyframes", () => {
    // matchMedia absent => easterEggs.reducedJuice() === true
    badumtss.triggerBaDumTss();

    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(overlays()).toHaveLength(0);
    expect(document.getElementById(STYLE_ID)).toBeNull();
  });

  it("keeps every mote's (delay + duration) within the overlay lifetime", () => {
    // Otherwise a mote is culled mid-fall when scheduleRemoval yanks the
    // container (cf. konami: lifetime >= maxDelay + maxDuration).
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    badumtss.triggerBaDumTss();

    const OVERLAY_LIFETIME_S = 2.2;
    const motes = [...overlays()[0].querySelectorAll("div")];
    expect(motes).toHaveLength(DUST_PARTICLES);
    for (const mote of motes) {
      const delay = parseFloat(mote.style.animationDelay);
      const duration = parseFloat(mote.style.animationDuration);
      expect(delay + duration).toBeLessThanOrEqual(OVERLAY_LIFETIME_S);
    }
  });

  it("removes the overlay after its lifetime", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));

    badumtss.triggerBaDumTss();
    expect(overlays()).toHaveLength(1);

    vi.advanceTimersByTime(3000);
    expect(overlays()).toHaveLength(0);
  });

  it("particles carry no id and no <use> — nothing to collide on", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    badumtss.triggerBaDumTss();

    const overlay = overlays()[0];
    expect(overlay.querySelectorAll("[id]")).toHaveLength(0);
    expect(overlay.querySelectorAll("use")).toHaveLength(0);
  });

  it("still shows the effect when window.easterEggs is missing", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    const saved = window.easterEggs;
    delete window.easterEggs;
    try {
      type("suchar");
      expect(window.showToast).toHaveBeenCalledTimes(1);
      expect(overlays()).toHaveLength(1);
    } finally {
      window.easterEggs = saved;
    }
  });
});

describe("sound", () => {
  it("asks easterEggs to play the rimshot cue on a match", () => {
    const spy = vi.spyOn(window.easterEggs, "playSound");
    type("suchar");
    expect(spy).toHaveBeenCalledWith("rimshot");
  });
});

describe("teardown / reset", () => {
  it("_resetForTests clears overlays, keyframes and the buffer", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    type("suc"); // mid-phrase
    badumtss.triggerBaDumTss(); // leaves an overlay + <style>

    badumtss._resetForTests();

    expect(overlays()).toHaveLength(0);
    expect(document.getElementById(STYLE_ID)).toBeNull();

    // Buffer is empty: the remaining letters alone must not fire.
    window.showToast.mockClear();
    type("har");
    expect(window.showToast).not.toHaveBeenCalled();
  });

  it("teardownBaDumTss detaches the document keydown listener", () => {
    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(window.__baDumTssReady).toBe(true);

    badumtss.teardownBaDumTss();

    [..."suchar"].forEach((key) => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key }));
    });
    expect(window.showToast).not.toHaveBeenCalled();
  });
});

describe("DOMContentLoaded init", () => {
  it("wires the listener for an authed body and flips __baDumTssReady", () => {
    delete window.__baDumTssReady;
    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__baDumTssReady).toBe(true);

    [..."suchar"].forEach((key) => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key }));
    });
    expect(window.showToast).toHaveBeenCalledTimes(1);
  });

  it("does not wire the listener for an anonymous body", () => {
    delete window.__baDumTssReady;
    document.body.dataset.userIsAuthenticated = "false";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__baDumTssReady).toBe(true);

    [..."suchar"].forEach((key) => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key }));
    });
    expect(window.showToast).not.toHaveBeenCalled();
  });
});
