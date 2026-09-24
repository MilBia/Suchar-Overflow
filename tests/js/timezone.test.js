/**
 * Unit tests for suchar_overflow/static/js/timezone.js (issue #410): the
 * browser's IANA time zone is mirrored into the `user_tz` cookie, which
 * `suchar_overflow/middleware.py` activates for input parsing and display.
 *
 * Classic browser script reached through its guarded CommonJS tail (see
 * CLAUDE.md "JS tests (Vitest)"). `require()` runs the module body once, which
 * already syncs the cookie — every test clears cookies first and drives the
 * exported helpers directly. The module has no mutable module-level state, so
 * no `_resetForTests()` is needed.
 */
const path = require("node:path");

const TIMEZONE_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/timezone.js",
);

let tz;

function clearCookies() {
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0].trim();
    if (name) document.cookie = `${name}=; path=/; max-age=0`;
  }
}

function stubZone(zone) {
  vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => ({
    resolvedOptions: () => ({ timeZone: zone }),
  }));
}

beforeEach(() => {
  clearCookies();
  tz = require(TIMEZONE_PATH);
  clearCookies();
});

afterEach(() => {
  vi.restoreAllMocks();
  clearCookies();
});

describe("syncTimezoneCookie", () => {
  it("writes the browser zone when the cookie is absent", () => {
    stubZone("America/New_York");

    expect(tz.syncTimezoneCookie()).toBe(true);
    expect(tz.readCookie()).toBe("America/New_York");
  });

  it("keeps multi-segment zone names intact (no encoding round-trip)", () => {
    stubZone("America/Argentina/Buenos_Aires");

    tz.syncTimezoneCookie();

    expect(tz.readCookie()).toBe("America/Argentina/Buenos_Aires");
  });

  it("does not rewrite an unchanged cookie", () => {
    stubZone("Europe/Warsaw");
    tz.syncTimezoneCookie();

    expect(tz.syncTimezoneCookie()).toBe(false);
    expect(tz.readCookie()).toBe("Europe/Warsaw");
  });

  it("updates the cookie when the browser zone changed", () => {
    stubZone("Europe/Warsaw");
    tz.syncTimezoneCookie();
    vi.restoreAllMocks();
    stubZone("Asia/Tokyo");

    expect(tz.syncTimezoneCookie()).toBe(true);
    expect(tz.readCookie()).toBe("Asia/Tokyo");
  });

  it("leaves other cookies alone", () => {
    document.cookie = "csrftoken=abc; path=/";
    stubZone("Europe/Warsaw");

    tz.syncTimezoneCookie();

    expect(document.cookie).toContain("csrftoken=abc");
  });

  it("does nothing when Intl throws", () => {
    vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => {
      throw new Error("no Intl");
    });

    expect(tz.syncTimezoneCookie()).toBe(false);
    expect(tz.readCookie()).toBeNull();
  });

  it("does nothing when Intl reports no zone", () => {
    stubZone(undefined);

    expect(tz.syncTimezoneCookie()).toBe(false);
    expect(tz.readCookie()).toBeNull();
  });
});

describe("buildCookie", () => {
  it("is site-wide, long-lived and SameSite=Lax", () => {
    const cookie = tz.buildCookie("Europe/Warsaw", false);

    expect(cookie).toBe(
      "user_tz=Europe/Warsaw; path=/; max-age=31536000; SameSite=Lax",
    );
  });

  it("adds Secure on https pages", () => {
    expect(tz.buildCookie("Europe/Warsaw", true)).toMatch(/; Secure$/);
  });
});
