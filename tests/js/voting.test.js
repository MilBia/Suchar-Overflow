/**
 * Unit tests for the busy-state helper in
 * suchar_overflow/static/js/features/voting.js (issue #298).
 *
 * The file is a classic browser script; its guarded CommonJS tail exposes
 * `setVotingBusy` to Vitest (inert in the browser — see the file and CLAUDE.md
 * "JS tests (Vitest)"). `require()` runs the module body, which only registers a
 * `DOMContentLoaded` listener jsdom is already past, so init never runs — we
 * test the exported helper directly.
 */
const path = require("node:path");

const MODULE_PATH = path.resolve(
  __dirname,
  "../../suchar_overflow/static/js/features/voting.js",
);

let setVotingBusy;

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = "";
  ({ setVotingBusy } = require(MODULE_PATH));
});

function makeContainer() {
  const el = document.createElement("div");
  el.className = "voting-controls";
  document.body.appendChild(el);
  return el;
}

describe("setVotingBusy", () => {
  it("adds the .loading class and a visually-hidden role=status node when busy", () => {
    const container = makeContainer();

    setVotingBusy(container, true);

    expect(container.classList.contains("loading")).toBe(true);
    const status = container.querySelector(".vote-status");
    expect(status).not.toBeNull();
    expect(status.getAttribute("role")).toBe("status");
    expect(status.classList.contains("visually-hidden")).toBe(true);
    expect(status.textContent.trim().length).toBeGreaterThan(0);
  });

  it("removes the class and the status node when no longer busy", () => {
    const container = makeContainer();
    setVotingBusy(container, true);

    setVotingBusy(container, false);

    expect(container.classList.contains("loading")).toBe(false);
    expect(container.querySelector(".vote-status")).toBeNull();
  });

  it("does not stack multiple status nodes across repeated busy calls", () => {
    const container = makeContainer();

    setVotingBusy(container, true);
    setVotingBusy(container, true);

    expect(container.querySelectorAll(".vote-status")).toHaveLength(1);
  });

  it("is a no-op turning off an already-idle container", () => {
    const container = makeContainer();

    expect(() => setVotingBusy(container, false)).not.toThrow();
    expect(container.querySelector(".vote-status")).toBeNull();
  });
});
