/**
 * Unit tests for the "Publika Rozgrzana" combo easter egg in
 * suchar_overflow/static/js/features/publika_rozgrzana.js (issue #296).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so most tests drive the exported helpers directly.
 *
 * The real `features/easter_eggs.js` is wired in first so `window.easterEggs`
 * (the session-deduped award + reduced-motion gate this egg delegates to)
 * behaves for real. `vi.resetModules()` does not re-run a required CJS module,
 * so both modules expose `_resetForTests()` for the per-test cleanup — the
 * egg's also clears the `sessionStorage` chain key.
 */
const path = require("node:path");

const PUBLIKA_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/publika_rozgrzana.js",
);
const EASTER_EGGS_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/easter_eggs.js",
);
const VOTING_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/voting.js",
);

const SLUG = "frontend-ee-publika-rozgrzana";
const STORAGE_KEY = "ee_publika_combo";
const METER_ID = "ee-publika-meter";
const STYLE_ID = "ee-publika-style";
const THRESHOLD = 10;
const WINDOW_MS = 60000;

let publika;

function frontendEventPosts() {
  return globalThis.fetch.mock.calls.filter(
    ([url]) => url === "/api/achievements/frontend-event",
  );
}

/** Put jsdom's `location.pathname` where the test needs it. */
function setPath(pathname) {
  window.history.pushState({}, "", pathname);
}

/** A single `.btn-vote` button, funny or dry, optionally already `.active`. */
function makeVoteButton(voteType, { active = false } = {}) {
  const btn = document.createElement("button");
  btn.className = "btn btn-vote btn-sm";
  btn.dataset.sucharId = "1";
  btn.dataset.voteType = voteType;
  if (active) btn.classList.add("active");
  const count = document.createElement("span");
  count.className = "vote-count";
  count.textContent = "0";
  btn.appendChild(count);
  document.body.appendChild(btn);
  return btn;
}

/** Drive the exported handler directly (like konami.test.js calls handleKeydown). */
function fireVote(btn) {
  publika.handleVoteClick({ target: btn });
}

/** The meter's "n/10" text, or null when the meter isn't in the DOM. */
function meterText() {
  const el = document.getElementById(METER_ID);
  return el ? el.querySelector(".ee-publika-count").textContent : null;
}

function readStoredChain() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  return raw ? JSON.parse(raw) : null;
}

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  document.head.querySelector(`#${STYLE_ID}`)?.remove();
  delete document.body.dataset.userIsAuthenticated;
  delete window.__publikaRozgrzanaReady;
  setPath("/suchary");

  globalThis.getCsrfToken = vi.fn(() => "test-token");
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => ({}) }),
  );
  window.showToast = vi.fn();
  delete window.EE_AUDIO;
  delete window.matchMedia; // jsdom: absence => reducedJuice() === true

  require(EASTER_EGGS_PATH);
  window.easterEggs._resetForTests();

  publika = require(PUBLIKA_PATH);
  publika._resetForTests();
});

afterEach(() => {
  window.easterEggs.teardownAll();
  publika._resetForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("path gate — isOnSucharyPath", () => {
  it("is true on /suchary and its sub-pages", () => {
    setPath("/suchary");
    expect(publika.isOnSucharyPath()).toBe(true);
    setPath("/suchary/");
    expect(publika.isOnSucharyPath()).toBe(true);
    setPath("/suchary/?page=3");
    expect(publika.isOnSucharyPath()).toBe(true);
  });

  it("is false elsewhere, including a sibling route", () => {
    setPath("/");
    expect(publika.isOnSucharyPath()).toBe(false);
    setPath("/suchary-archiwum/");
    expect(publika.isOnSucharyPath()).toBe(false);
  });
});

describe("chain building — handleVoteClick", () => {
  it("increments the meter on each added funny vote", () => {
    for (let i = 1; i <= 3; i += 1) fireVote(makeVoteButton("funny"));

    expect(meterText()).toBe("3/10");
    expect(readStoredChain().count).toBe(3);
  });

  it("keeps `firstAt` fixed across the run (the 60 s window is from the first)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 1, 12, 0, 0));

    fireVote(makeVoteButton("funny"));
    const firstAt = readStoredChain().firstAt;

    vi.advanceTimersByTime(5000);
    fireVote(makeVoteButton("funny"));

    expect(readStoredChain().firstAt).toBe(firstAt);
    expect(readStoredChain().count).toBe(2);
  });

  it("fires at the 10th: toast + award POST, then clears the chain", () => {
    for (let i = 0; i < THRESHOLD; i += 1) fireVote(makeVoteButton("funny"));

    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(window.showToast.mock.calls[0][1]).toBe("Publika Rozgrzana");
    expect(frontendEventPosts()).toHaveLength(1);
    expect(JSON.parse(frontendEventPosts()[0][1].body)).toEqual({
      event_slug: SLUG,
    });
    expect(readStoredChain()).toBeNull();
    expect(document.getElementById(METER_ID)).toBeNull();
  });

  it("does nothing at 9 (below the threshold)", () => {
    for (let i = 0; i < THRESHOLD - 1; i += 1) fireVote(makeVoteButton("funny"));

    expect(window.showToast).not.toHaveBeenCalled();
    expect(meterText()).toBe("9/10");
  });

  it("replays on a fresh run of 10, but POSTs the award only once", () => {
    for (let i = 0; i < THRESHOLD; i += 1) fireVote(makeVoteButton("funny"));
    for (let i = 0; i < THRESHOLD; i += 1) fireVote(makeVoteButton("funny"));

    expect(window.showToast).toHaveBeenCalledTimes(2);
    expect(frontendEventPosts()).toHaveLength(1); // easterEggs.award sessionStorage dedupe
  });
});

describe("reset conditions", () => {
  it("a dry vote breaks the run", () => {
    fireVote(makeVoteButton("funny"));
    fireVote(makeVoteButton("funny"));
    expect(readStoredChain().count).toBe(2);

    fireVote(makeVoteButton("dry"));

    expect(readStoredChain()).toBeNull();
    expect(document.getElementById(METER_ID)).toBeNull();
  });

  it("removing a dry vote also breaks the run", () => {
    fireVote(makeVoteButton("funny"));
    fireVote(makeVoteButton("dry", { active: true })); // un-voting dry

    expect(readStoredChain()).toBeNull();
  });

  it("un-voting a funny (clicking an already-active funny) breaks the run", () => {
    fireVote(makeVoteButton("funny"));
    fireVote(makeVoteButton("funny"));

    fireVote(makeVoteButton("funny", { active: true })); // removing a funny vote

    expect(readStoredChain()).toBeNull();
    expect(document.getElementById(METER_ID)).toBeNull();
  });

  it("a click on a non-vote button is ignored", () => {
    fireVote(makeVoteButton("funny"));
    const other = document.createElement("button");
    other.className = "btn";
    fireVote({ target: other });
    expect(readStoredChain().count).toBe(1);
  });

  it("a `.btn-vote` with no funny/dry data-vote-type is ignored", () => {
    fireVote(makeVoteButton("funny"));
    fireVote(makeVoteButton("weird"));
    expect(readStoredChain().count).toBe(1);
  });
});

describe("60 s window", () => {
  it("a run spread past 60 s never reaches 10 — the chain restarts", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 1, 12, 0, 0));

    for (let i = 0; i < THRESHOLD - 1; i += 1) {
      fireVote(makeVoteButton("funny"));
      vi.advanceTimersByTime(7000); // 9 * 7s = 63s total
    }
    fireVote(makeVoteButton("funny"));

    expect(window.showToast).not.toHaveBeenCalled();
    // The last click landed after the window elapsed → a brand-new chain.
    expect(readStoredChain().count).toBe(1);
  });

  it("10 within the window still fires (fake-clock canary)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 1, 12, 0, 0));

    for (let i = 0; i < THRESHOLD; i += 1) {
      fireVote(makeVoteButton("funny"));
      vi.advanceTimersByTime(4000); // 9 * 4s = 36s, inside 60s
    }

    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(frontendEventPosts()).toHaveLength(1);
  });

  it("the visual expiry timer hides the meter + clears the chain after the window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 1, 12, 0, 0));

    fireVote(makeVoteButton("funny"));
    fireVote(makeVoteButton("funny"));
    expect(meterText()).toBe("2/10");

    vi.advanceTimersByTime(WINDOW_MS);

    expect(document.getElementById(METER_ID)).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("readChain rejects a chain whose firstAt is in the future (clock wound back)", () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ count: 4, firstAt: Date.now() + 5000 }),
    );
    expect(publika.readChain()).toBeNull();
  });

  it("readChain tolerates a malformed stored value", () => {
    sessionStorage.setItem(STORAGE_KEY, "{not json");
    expect(() => publika.readChain()).not.toThrow();
    expect(publika.readChain()).toBeNull();
  });

  it("readChain rejects a forged / garbled count (non-integer, <= 0, or >= 10)", () => {
    const firstAt = Date.now();
    for (const count of [0, -3, 2.5, THRESHOLD, THRESHOLD + 50, "9", NaN]) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ count, firstAt }));
      expect(publika.readChain()).toBeNull();
    }
    // A well-formed mid-run value is still accepted.
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ count: 9, firstAt }));
    expect(publika.readChain()).toEqual({ count: 9, firstAt });
  });
});

describe("prefers-reduced-motion", () => {
  it("full-motion: injects the pulse @keyframes and pulses the meter", () => {
    window.matchMedia = vi.fn((q) => ({ matches: false, media: q }));

    fireVote(makeVoteButton("funny"));

    expect(document.getElementById(STYLE_ID)).toBeTruthy();
    expect(document.getElementById(METER_ID).classList.contains("ee-publika-pulse")).toBe(
      true,
    );
  });

  it("reduced motion (matchMedia absent): meter + count still show, no @keyframes", () => {
    fireVote(makeVoteButton("funny"));
    fireVote(makeVoteButton("funny"));

    expect(meterText()).toBe("2/10");
    expect(document.getElementById(STYLE_ID)).toBeNull();
    expect(
      document.getElementById(METER_ID).classList.contains("ee-publika-pulse"),
    ).toBe(false);
  });

  it("reduced motion (matchMedia reports reduce): same, and the 10th still awards", () => {
    window.matchMedia = vi.fn((q) => ({ matches: true, media: q }));

    for (let i = 0; i < THRESHOLD; i += 1) fireVote(makeVoteButton("funny"));

    expect(document.getElementById(STYLE_ID)).toBeNull();
    expect(window.showToast).toHaveBeenCalledTimes(1);
    expect(frontendEventPosts()).toHaveLength(1);
  });
});

describe("capture-phase ordering vs voting.js", () => {
  it("reads the pre-toggle button state even though voting.js also delegates on document", () => {
    // Wire the REAL voting.js first (its bubble-phase `document` listener),
    // then publika's capture-phase listener — registered LAST, yet a capture
    // listener on `document` still runs before any bubble listener on
    // `document`. If publika ever regressed to bubble, being last it would see
    // voting.js's optimistic `.active` toggle already applied and treat the
    // click as an un-vote → the meter would never appear.
    require(VOTING_PATH);
    document.dispatchEvent(new Event("DOMContentLoaded"));

    document.body.dataset.userIsAuthenticated = "true";
    publika.initPublikaRozgrzana();

    const controls = document.createElement("div");
    controls.className = "voting-controls";
    controls.innerHTML = `
      <span>__CSRF__</span>
      <button type="button" data-suchar-id="1" data-vote-type="funny"
              class="btn btn-vote"><span class="vote-count">0</span></button>
      <button type="button" data-suchar-id="1" data-vote-type="dry"
              class="btn btn-vote"><span class="vote-count">0</span></button>
    `;
    document.body.appendChild(controls);
    const funnyBtn = controls.querySelector('[data-vote-type="funny"]');

    funnyBtn.querySelector(".vote-count").dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    expect(meterText()).toBe("1/10");
    expect(readStoredChain().count).toBe(1);
  });
});

describe("teardown / init", () => {
  it("teardownPublikaRozgrzana detaches the listener, drops the meter and the chain", () => {
    document.body.dataset.userIsAuthenticated = "true";
    publika.initPublikaRozgrzana();

    const btn = makeVoteButton("funny");
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(meterText()).toBe("1/10");

    publika.teardownPublikaRozgrzana();

    expect(document.getElementById(METER_ID)).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();

    makeVoteButton("funny").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById(METER_ID)).toBeNull(); // listener gone
  });

  it("DOMContentLoaded wires the listener for an authed /suchary body and flips the ready flag", () => {
    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__publikaRozgrzanaReady).toBe(true);

    makeVoteButton("funny").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(meterText()).toBe("1/10");
  });

  it("does not wire the listener for an anonymous body", () => {
    document.body.dataset.userIsAuthenticated = "false";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__publikaRozgrzanaReady).toBe(true);
    makeVoteButton("funny").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById(METER_ID)).toBeNull();
  });

  it("does not wire the listener off /suchary", () => {
    setPath("/");
    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    makeVoteButton("funny").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById(METER_ID)).toBeNull();
  });

  it("resumes a live chain from sessionStorage on load — meter shows the carried count", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 1, 12, 0, 0));
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ count: 6, firstAt: Date.now() - 10000 }),
    );

    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(meterText()).toBe("6/10");

    // Expiry timer re-armed to the REMAINING window (~50 s), not a fresh 60 s.
    vi.advanceTimersByTime(WINDOW_MS - 10000);
    expect(document.getElementById(METER_ID)).toBeNull();
  });

  it("clears an already-expired chain on load without showing a meter", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 1, 12, 0, 0));
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ count: 4, firstAt: Date.now() - (WINDOW_MS + 1000) }),
    );

    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(document.getElementById(METER_ID)).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
