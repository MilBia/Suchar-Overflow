import { defineConfig } from "vitest/config";

// Dev-only test runner for plain browser JS under suchar_overflow/static/js/.
// jsdom gives DOM + storage APIs without a real browser; fake timers make the
// time-window logic (idle timers, combo windows, hover dwell) deterministic.
// This never touches served assets — see CLAUDE.md "JS tests (Vitest)".
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/js/**/*.test.js"],
    globals: true,
  },
});
