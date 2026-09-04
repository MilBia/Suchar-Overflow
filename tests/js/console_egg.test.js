/**
 * Unit tests for the developer console easter egg in
 * suchar_overflow/static/js/features/console_egg.js (issue #287).
 *
 * Classic browser script; its guarded CommonJS tail (inside the file's IIFE)
 * exposes the helpers to Vitest — inert in the browser, see the file and
 * CLAUDE.md "JS tests (Vitest)". `require()` runs the module body, which
 * registers a `DOMContentLoaded` listener that does not fire here (jsdom is
 * past `load`), so most tests drive the exported helpers directly.
 *
 * `vi.resetModules()` does not re-run a required CJS module, so the module
 * exposes `_resetForTests()` for the per-test cleanup (it also clears the
 * sessionStorage dedupe key).
 *
 * This egg is pure delight: no achievement, no slug, no network, no DOM, no
 * sound. It only emits one styled `console.log` per browser session.
 */
const path = require("node:path");

const CONSOLE_EGG_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/console_egg.js",
);

const SESSION_KEY = "ee_console_shown";
const REPO_URL = "https://github.com/MilBia/Suchar-Overflow";

let consoleEgg;
let logSpy;

/** The full text console.log was called with, arguments joined. */
function loggedText() {
  return logSpy.mock.calls.map((call) => call.join(" ")).join("\n");
}

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = "";
  delete document.body.dataset.userIsAuthenticated;
  delete window.__consoleEggReady;

  logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

  consoleEgg = require(CONSOLE_EGG_PATH);
  consoleEgg._resetForTests();
});

afterEach(() => {
  consoleEgg._resetForTests();
  vi.restoreAllMocks();
});

describe("logConsoleEgg", () => {
  it("emits exactly one console.log on the first call", () => {
    expect(consoleEgg.logConsoleEgg()).toBe(true);
    expect(logSpy).toHaveBeenCalledTimes(1);
  });

  it("uses a %c-styled call (a style string per %c segment)", () => {
    consoleEgg.logConsoleEgg();
    const [format, ...styles] = logSpy.mock.calls[0];
    expect(format.startsWith("%c")).toBe(true);
    const segments = format.split("%c").length - 1;
    expect(styles).toHaveLength(segments);
    styles.forEach((style) => expect(typeof style).toBe("string"));
  });

  it("includes the repo invite, a wink and the wordmark", () => {
    consoleEgg.logConsoleEgg();
    const text = loggedText();
    expect(text).toContain(REPO_URL);
    expect(text).toContain("😉");
    expect(text).toContain("Suchar Overflow");
  });

  it("keeps the Polish text with its diacritics intact", () => {
    consoleEgg.logConsoleEgg();
    expect(loggedText()).toMatch(/[ąćęłńóśźż]/);
  });

  it("is a one-shot per session: the second call is a no-op", () => {
    expect(consoleEgg.logConsoleEgg()).toBe(true);
    logSpy.mockClear();

    expect(consoleEgg.logConsoleEgg()).toBe(false);
    expect(logSpy).not.toHaveBeenCalled();
  });

  it("stays quiet when the session flag is already set (e.g. a prior page load)", () => {
    // beforeEach's _resetForTests() already cleared the in-memory flag, so the
    // sessionStorage read is the only thing that can suppress the log here.
    sessionStorage.setItem(SESSION_KEY, "1");

    expect(consoleEgg.logConsoleEgg()).toBe(false);
    expect(logSpy).not.toHaveBeenCalled();
  });

  it("records the session flag so the next page load stays quiet", () => {
    consoleEgg.logConsoleEgg();
    expect(sessionStorage.getItem(SESSION_KEY)).toBe("1");
  });

  it("_resetForTests re-arms it", () => {
    consoleEgg.logConsoleEgg();
    consoleEgg._resetForTests();
    logSpy.mockClear();

    expect(consoleEgg.logConsoleEgg()).toBe(true);
    expect(logSpy).toHaveBeenCalledTimes(1);
  });

  it("swallows an error thrown by console.log itself but stays latched", () => {
    logSpy.mockImplementation(() => {
      throw new Error("a console proxy that rejects styled logging");
    });

    expect(consoleEgg.logConsoleEgg()).toBe(true);
    expect(logSpy).toHaveBeenCalledTimes(1);
    // markShown() ran before the throw, so the session is still latched.
    expect(consoleEgg.logConsoleEgg()).toBe(false);
    expect(logSpy).toHaveBeenCalledTimes(1);
  });
});

describe("storage failure", () => {
  it("still logs once and does not throw when sessionStorage.getItem throws", () => {
    const getItem = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("storage blocked");
      });
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("storage blocked");
      });

    expect(() => consoleEgg.logConsoleEgg()).not.toThrow();
    expect(logSpy).toHaveBeenCalledTimes(1);

    // In-memory fallback still dedupes within the page.
    expect(consoleEgg.logConsoleEgg()).toBe(false);
    expect(logSpy).toHaveBeenCalledTimes(1);

    getItem.mockRestore();
    setItem.mockRestore();
  });

  it("dedupes via the in-memory flag when getItem works but setItem throws (quota)", () => {
    const getItem = vi
      .spyOn(Storage.prototype, "getItem")
      .mockReturnValue(null);
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        const err = new Error("QuotaExceededError");
        err.name = "QuotaExceededError";
        throw err;
      });

    expect(consoleEgg.logConsoleEgg()).toBe(true);
    expect(logSpy).toHaveBeenCalledTimes(1);

    // Nothing was persisted (getItem still returns null), so only the in-memory
    // shownThisPage flag keeps the second call quiet.
    expect(consoleEgg.logConsoleEgg()).toBe(false);
    expect(logSpy).toHaveBeenCalledTimes(1);

    getItem.mockRestore();
    setItem.mockRestore();
  });
});

describe("initConsoleEgg — auth gate", () => {
  it("logs for an authenticated body", () => {
    document.body.dataset.userIsAuthenticated = "true";
    consoleEgg.initConsoleEgg();
    expect(logSpy).toHaveBeenCalledTimes(1);
  });

  it("stays silent for an anonymous body", () => {
    document.body.dataset.userIsAuthenticated = "false";
    consoleEgg.initConsoleEgg();
    expect(logSpy).not.toHaveBeenCalled();
  });

  it("stays silent when the flag is missing entirely", () => {
    consoleEgg.initConsoleEgg();
    expect(logSpy).not.toHaveBeenCalled();
  });
});

describe("DOMContentLoaded init", () => {
  it("flips __consoleEggReady and logs for an authed body", () => {
    document.body.dataset.userIsAuthenticated = "true";
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__consoleEggReady).toBe(true);
    expect(loggedText()).toContain(REPO_URL);
  });

  it("flips __consoleEggReady but stays silent for an anonymous body", () => {
    document.body.dataset.userIsAuthenticated = "false";
    logSpy.mockClear();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(window.__consoleEggReady).toBe(true);
    expect(logSpy).not.toHaveBeenCalled();
  });
});
