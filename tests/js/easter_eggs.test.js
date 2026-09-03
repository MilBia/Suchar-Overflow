/**
 * Unit tests for the easter-egg foundation helpers in
 * suchar_overflow/static/js/features/easter_eggs.js (issue #282).
 *
 * Classic browser script; its guarded CommonJS tail exposes the `window.easter
 * Eggs` surface to Vitest (inert in the browser — see the file and CLAUDE.md
 * "JS tests (Vitest)"). `require()` runs the module body, which registers a
 * `DOMContentLoaded` listener that never fires here (jsdom is past `load`), so
 * these tests drive the exported helpers directly.
 */
const path = require("node:path");

const MODULE_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);

let ee;

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({}) }));
  delete window.EE_AUDIO;
  delete window.matchMedia;

  ee = require(MODULE_PATH);
});

afterEach(() => {
  ee.teardownAll();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("session dedupe — alreadyAwarded / markAwarded", () => {
  it("reports a slug as awarded only after it is marked", () => {
    expect(ee.alreadyAwarded("frontend-ee-x")).toBe(false);
    ee.markAwarded("frontend-ee-x");
    expect(ee.alreadyAwarded("frontend-ee-x")).toBe(true);
    expect(sessionStorage.getItem("awarded_frontend-ee-x")).toBe("1");
  });

  it("treats a broken sessionStorage as 'not yet awarded'", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("private mode");
    });
    expect(ee.alreadyAwarded("frontend-ee-x")).toBe(false);
    spy.mockRestore();
  });
});

describe("award() — dedupe + POST in one call", () => {
  function posts() {
    return globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
  }

  it("awards once, then no-ops, and fires exactly one POST", () => {
    expect(ee.award("frontend-ee-x")).toBe(true);
    expect(ee.award("frontend-ee-x")).toBe(false);
    expect(ee.award("frontend-ee-x")).toBe(false);

    const sent = posts();
    expect(sent).toHaveLength(1);
    expect(JSON.parse(sent[0][1].body)).toEqual({ event_slug: "frontend-ee-x" });
    expect(sent[0][1].headers["X-CSRFToken"]).toBe("test-token");
    expect(sent[0][1].method).toBe("POST");
  });

  it("does not POST when the slug is already marked", () => {
    sessionStorage.setItem("awarded_frontend-ee-x", "1");
    expect(ee.award("frontend-ee-x")).toBe(false);
    expect(posts()).toHaveLength(0);
  });
});

describe("awardFrontendAchievement()", () => {
  it("swallows a rejected fetch without throwing", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    await expect(ee.awardFrontendAchievement("frontend-ee-x")).resolves.toBeUndefined();
  });
});

describe("mute preference — DEFAULT MUTED", () => {
  it("is muted when no preference has been stored", () => {
    expect(ee.isMuted()).toBe(true);
  });

  it("is unmuted only for the explicit opt-in value '0'", () => {
    ee.setMuted(false);
    expect(localStorage.getItem("ee_muted")).toBe("0");
    expect(ee.isMuted()).toBe(false);

    ee.setMuted(true);
    expect(localStorage.getItem("ee_muted")).toBe("1");
    expect(ee.isMuted()).toBe(true);
  });

  it("falls back to muted when localStorage throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(ee.isMuted()).toBe(true);
    spy.mockRestore();
  });
});

describe("playSound()", () => {
  let constructed;

  beforeEach(() => {
    constructed = [];
    globalThis.Audio = vi.fn(function Audio(src) {
      constructed.push(src);
      this.src = src;
      this.currentTime = 0;
      this.play = vi.fn(() => Promise.resolve());
    });
  });

  it("does nothing while muted (default)", () => {
    window.EE_AUDIO = { rimshot: "/static/audio/rimshot.wav" };
    ee.playSound("rimshot");
    expect(constructed).toHaveLength(0);
  });

  it("plays a known cue once unmuted and reuses the cached element", () => {
    ee.setMuted(false);
    window.EE_AUDIO = { rimshot: "/static/audio/rimshot.wav" };

    ee.playSound("rimshot");
    ee.playSound("rimshot");

    expect(constructed).toEqual(["/static/audio/rimshot.wav"]);
    expect(globalThis.Audio.mock.instances[0].play).toHaveBeenCalledTimes(2);
  });

  it("no-ops for an unknown cue or when EE_AUDIO is absent", () => {
    ee.setMuted(false);
    ee.playSound("rimshot"); // no EE_AUDIO
    window.EE_AUDIO = { rimshot: "/static/audio/rimshot.wav" };
    ee.playSound("dust"); // not in map
    expect(constructed).toHaveLength(0);
  });

  it("swallows a rejected play() promise", () => {
    ee.setMuted(false);
    window.EE_AUDIO = { rimshot: "/static/audio/rimshot.wav" };
    globalThis.Audio = vi.fn(function Audio(src) {
      this.src = src;
      this.play = vi.fn(() => Promise.reject(new Error("autoplay blocked")));
    });
    expect(() => ee.playSound("rimshot")).not.toThrow();
  });
});

describe("reduced-motion gate — reducedJuice / withJuice", () => {
  it("suppresses juice when matchMedia is unavailable", () => {
    expect(ee.reducedJuice()).toBe(true);
    const fn = vi.fn();
    ee.withJuice(fn);
    expect(fn).not.toHaveBeenCalled();
  });

  it("mirrors the (prefers-reduced-motion: reduce) match", () => {
    window.matchMedia = vi.fn((q) => ({ matches: true, media: q }));
    expect(ee.reducedJuice()).toBe(true);

    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));
    expect(ee.reducedJuice()).toBe(false);

    const fn = vi.fn();
    ee.withJuice(fn);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("suppresses juice when matchMedia itself throws", () => {
    window.matchMedia = vi.fn(() => {
      throw new Error("boom");
    });
    expect(ee.reducedJuice()).toBe(true);
  });
});

describe("DOMContentLoaded init", () => {
  beforeEach(() => {
    delete window.__easterEggsReady;
  });

  it("flips window.__easterEggsReady once init runs for an authed body", () => {
    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(window.__easterEggsReady).toBe(true);
  });

  it("still flips the flag for an anonymous body (finally block)", () => {
    document.body.dataset.userIsAuthenticated = "false";
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(window.__easterEggsReady).toBe(true);
  });
});

describe("teardown registry", () => {
  it("runs every registered callback once and clears them", () => {
    const a = vi.fn();
    const b = vi.fn();
    ee.registerTeardown("a", a);
    ee.registerTeardown("b", b);

    ee.teardownAll();
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);

    ee.teardownAll(); // second drain is a no-op
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("exposes the same surface on window.easterEggs", () => {
    expect(window.easterEggs).toBe(ee);
  });
});
