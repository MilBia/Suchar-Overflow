/**
 * Unit tests for the dedupe / counter logic in
 * suchar_overflow/static/js/features/hidden_achievements.js.
 *
 * The file is a classic browser script; its guarded CommonJS tail exposes the
 * internal helpers to Vitest (inert in the browser — see the file and
 * CLAUDE.md "JS tests (Vitest)"). These tests are the regression net for the
 * `sessionStorage`/`localStorage` dedupe behaviour that #282 will later extract
 * into a shared helper.
 */
const path = require("node:path");

const MODULE_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/hidden_achievements.js",
);

let hiddenAchievements;

// Shared registry for `setupX()` calls. jsdom's `document` survives between
// tests and `vi.resetModules()` does not detach listeners a `setupX()` added to
// it, so a test that never reaches its award (and so never triggers the
// in-`award()` teardown) would otherwise leak `mouseover`/`click` handlers into
// the next test. Draining every registered teardown in `afterEach` keeps
// `document` clean regardless of whether the test awarded.
let teardownRegistry;

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  window.history.pushState({}, "", "/");
  teardownRegistry = {};

  // Free globals the script reaches for without declaring them.
  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: async () => [] }));

  hiddenAchievements = require(MODULE_PATH);
});

afterEach(() => {
  Object.values(teardownRegistry).forEach((fn) => {
    if (typeof fn === "function") fn();
  });
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("award() — session dedupe guard", () => {
  it("fires the frontend-event POST once, then no-ops on repeat", () => {
    const { award } = hiddenAchievements;

    award("frontend-x", {});
    award("frontend-x", {});
    award("frontend-x", {});

    expect(sessionStorage.getItem("awarded_frontend-x")).toBe("1");
    const posts = globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({ event_slug: "frontend-x" });
    expect(posts[0][1].headers["X-CSRFToken"]).toBe("test-token");
  });

  it("runs the slug's teardown exactly once, on the first award", () => {
    const { award } = hiddenAchievements;
    const teardown = vi.fn();

    award("frontend-y", { "frontend-y": teardown });
    award("frontend-y", { "frontend-y": teardown });

    expect(teardown).toHaveBeenCalledTimes(1);
  });

  it("treats a pre-existing sessionStorage marker as already-awarded", () => {
    const { award } = hiddenAchievements;
    sessionStorage.setItem("awarded_frontend-z", "1");

    award("frontend-z", {});

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("setupRecenzentTotalny() — 3s hover dwell across 20 cards", () => {
  // The reason option C beats E2E: `vi.useFakeTimers()` collapses the dwell
  // windows to nothing. The idle timer (#282 A6) and combo window (#282 B5)
  // will be tested with this same pattern.
  it("awards once after 20 cards each complete a 3s dwell", () => {
    vi.useFakeTimers();
    const cards = [];
    for (let i = 0; i < 20; i += 1) {
      const card = document.createElement("div");
      card.className = "card suchar-card";
      document.body.appendChild(card);
      cards.push(card);
    }

    hiddenAchievements.setupRecenzentTotalny(teardownRegistry);

    cards.forEach((card) => {
      card.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();

    vi.advanceTimersByTime(3000);

    const posts = globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({
      event_slug: "frontend-recenzent-totalny",
    });
  });

  it("does not award while fewer than 20 cards have finished their dwell", () => {
    vi.useFakeTimers();
    for (let i = 0; i < 19; i += 1) {
      const card = document.createElement("div");
      card.className = "card suchar-card";
      document.body.appendChild(card);
    }

    hiddenAchievements.setupRecenzentTotalny(teardownRegistry);
    document.querySelectorAll(".suchar-card").forEach((card) => {
      card.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    vi.advanceTimersByTime(10000);

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("setupStluczonaMysz() — repeated clicks on one suchar's vote buttons", () => {
  function buildVoteButton() {
    document.body.innerHTML = `<button class="btn-vote" data-suchar-id="7">funny</button>`;
    return document.querySelector(".btn-vote");
  }

  it("awards on the 5th click of the same suchar id, not before", () => {
    const btn = buildVoteButton();
    hiddenAchievements.setupStluczonaMysz(teardownRegistry);

    for (let i = 0; i < 4; i += 1) {
      btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    }
    expect(globalThis.fetch).not.toHaveBeenCalled();

    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const posts = globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({
      event_slug: "frontend-stluczona-mysz",
    });
  });

  it("counts each suchar id separately", () => {
    document.body.innerHTML = `
      <button class="btn-vote" data-suchar-id="1">a</button>
      <button class="btn-vote" data-suchar-id="2">b</button>
    `;
    hiddenAchievements.setupStluczonaMysz(teardownRegistry);

    document.querySelectorAll(".btn-vote").forEach((btn) => {
      for (let i = 0; i < 4; i += 1) {
        btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      }
    });

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("getOwnedSlugs()", () => {
  it("returns the parsed slug list on a 2xx response", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => ["frontend-odkrywca"] }),
    );

    await expect(hiddenAchievements.getOwnedSlugs()).resolves.toEqual([
      "frontend-odkrywca",
    ]);
  });

  it("returns [] on a non-ok response", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: async () => ["x"] }));

    await expect(hiddenAchievements.getOwnedSlugs()).resolves.toEqual([]);
  });

  it("returns [] when fetch rejects", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("offline")));

    await expect(hiddenAchievements.getOwnedSlugs()).resolves.toEqual([]);
  });
});

describe("setupNiecierpliwy() — short-submit counter", () => {
  function buildForm() {
    document.body.innerHTML = `
      <form id="f"><textarea id="id_text"></textarea></form>
    `;
    return document.getElementById("f");
  }

  it("awards only on the 3rd short submit and clears the counter", () => {
    const { setupNiecierpliwy } = hiddenAchievements;
    const form = buildForm();
    setupNiecierpliwy(teardownRegistry);

    for (let i = 0; i < 2; i += 1) {
      form.dispatchEvent(new Event("submit"));
    }
    expect(sessionStorage.getItem("niecierpliwy_count")).toBe("2");
    expect(globalThis.fetch).not.toHaveBeenCalled();

    form.dispatchEvent(new Event("submit"));

    expect(sessionStorage.getItem("niecierpliwy_count")).toBeNull();
    const posts = globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({
      event_slug: "frontend-niecierpliwy",
    });
  });

  it("does not count a submit once the textarea has 10+ trimmed chars", () => {
    const { setupNiecierpliwy } = hiddenAchievements;
    const form = buildForm();
    setupNiecierpliwy(teardownRegistry);

    document.getElementById("id_text").value = "   this is clearly long enough   ";
    form.dispatchEvent(new Event("submit"));

    expect(sessionStorage.getItem("niecierpliwy_count")).toBeNull();
  });
});

describe("setupOdkrywca() — cross-session visit counter (localStorage)", () => {
  it("accumulates visits across module reloads and awards on the 5th", () => {
    window.history.pushState({}, "", "/achievements/");

    for (let visit = 1; visit <= 4; visit += 1) {
      vi.resetModules();
      require(MODULE_PATH).setupOdkrywca(teardownRegistry);
      expect(localStorage.getItem("odkrywca_visits")).toBe(String(visit));
    }
    expect(globalThis.fetch).not.toHaveBeenCalled();

    vi.resetModules();
    require(MODULE_PATH).setupOdkrywca(teardownRegistry);

    expect(localStorage.getItem("odkrywca_visits")).toBeNull();
    const posts = globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({ event_slug: "frontend-odkrywca" });
  });

  it("ignores pages that are not the achievements list", () => {
    window.history.pushState({}, "", "/achievements/inbox");
    hiddenAchievements.setupOdkrywca(teardownRegistry);
    expect(localStorage.getItem("odkrywca_visits")).toBeNull();
  });
});

describe("setupZbieraczSucharow() — page-view counter with vote reset", () => {
  it("awards after 5 counted /suchary views", () => {
    window.history.pushState({}, "", "/suchary/");
    for (let i = 0; i < 4; i += 1) {
      vi.resetModules();
      require(MODULE_PATH).setupZbieraczSucharow(teardownRegistry);
    }
    expect(sessionStorage.getItem("zbieracz_pages")).toBe("4");

    vi.resetModules();
    require(MODULE_PATH).setupZbieraczSucharow(teardownRegistry);

    expect(sessionStorage.getItem("zbieracz_pages")).toBeNull();
    const posts = globalThis.fetch.mock.calls.filter(
      ([url]) => url === "/api/achievements/frontend-event",
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({
      event_slug: "frontend-zbieracz-sucharow",
    });
  });

  it("resets the counter when a vote button is clicked", () => {
    window.history.pushState({}, "", "/suchary/");
    document.body.innerHTML = `<button class="btn-vote">vote</button>`;

    hiddenAchievements.setupZbieraczSucharow(teardownRegistry);
    expect(sessionStorage.getItem("zbieracz_pages")).toBe("1");

    document.querySelector(".btn-vote").dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    expect(sessionStorage.getItem("zbieracz_pages")).toBe("0");
  });
});
