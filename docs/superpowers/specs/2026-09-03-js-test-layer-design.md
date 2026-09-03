# JS test layer for easter-eggs & frontend achievements (issue #281)

## Decision

**Option C (hybrid): Vitest + jsdom for pure logic, Playwright E2E for integration.**

Rationale — lead with the mechanism, not the speed: the test list in #281 is
dominated by *time windows* (idle timer A6, combo window B5, the 3s hover dwell in
`hidden_achievements.js`). `vi.useFakeTimers()` / `vi.advanceTimersByTime()` makes
those deterministic and instant; the same cases in Playwright need `page.clock`
gymnastics against a real browser and a `transaction=True` DB per test. Sequence
matchers (Konami, "suchar"/"ba dum tss" key buffers) are likewise pure string/array
logic with no DOM. E2E keeps the jobs it is actually good at: audio playback, the
real `POST /api/achievements/frontend-event`, toast rendering, CSP compliance.

Vitest is a **dev-only test runner**, in the same category as pytest — it never
transforms, bundles, or touches served assets. This does **not** reopen the
"no JS build step" rule (CSP section / issue #177): npm for *vendoring or bundling
runtime assets* stays rejected; npm as a *test runner* is accepted here.

## Scope of THIS PR

`easter_eggs.js` does not exist yet (#282 unstarted), so the Konami matcher, key
buffers, idle timer, combo counter and reduced-motion guard **have no code to
test**. This PR ships:

1. The runner + config + `just` recipe + CI job (infrastructure).
2. The **access convention** #282 will inherit (see below).
3. Real tests for the one bullet that has code today: **`sessionStorage` dedupe** —
   `award()` and the `parseInt` counter patterns in `hidden_achievements.js`,
   tested **in place, without extraction** (extraction is #282's scope; these tests
   then become its regression net).

Per-feature tests (matcher / key buffer / idle timer / combo) land with #282 and
its children as those features are built. The PR body and the issue comment say so
explicitly. PR still `Closes #281` (no reference-only mode).

## Access convention (durable — #282 inherits it)

`hidden_achievements.js` is a **classic script**, not a module: no `export`,
script-scope functions, a free `getCsrfToken` global from `project.js`, served
concatenated inside `{% compress js %}` and minified by `rjsmin`. Adding `export`
is a SyntaxError that takes down the whole bundle.

Mechanism: a **guarded CommonJS tail** appended to the file:

```js
/* Test-only export (Vitest/jsdom). No production reader — do not remove as dead
 * code (cf. window.__hiddenAchievementsReady). `module` is undefined in the
 * browser, so this is inert there and survives rjsmin. */
if (typeof module !== "undefined" && module.exports) {
    module.exports = { award, /* named counter helpers */ };
}
```

Constraints:
- **Nothing is added to or reordered inside any `{% compress js %}` block.** Load
  order and the offline-compress guards stay trivially satisfied.
- `tests/test_compressed_page_assets.py` (renders with `COMPRESS_ENABLED = True`)
  must stay green — it is the check that the served bundle is still a valid
  classic script.

## Infrastructure

| Item | Detail |
|------|--------|
| `package.json` | `"private": true`, devDeps `vitest` + `jsdom`, script `"test": "vitest run"` |
| `package-lock.json` | committed; CI uses `npm ci` |
| `vitest.config.js` | `environment: "jsdom"`, `include: ["tests/js/**/*.test.js"]` |
| Test dir | `tests/js/` — inert to pytest, kept out of `tests/e2e/` so the `-m e2e` override path is untouched |
| `just test-js` | `npx vitest run`, runs **locally** (first recipe not going through `docker compose`; one-line comment cites pre-commit as the "runs outside the container" precedent). Node is **not** added to the Django image. |
| CI | new job `js-tests` parallel to `linter` / `pytest`: `actions/setup-node@v4` (node from `.nvmrc` or pinned), `npm ci`, `npx vitest run`. No Docker. |
| `.github/dependabot.yml` | add an `npm` ecosystem entry (else same no-bot gap as #177) |
| Coverage | **no** JS coverage gate — `fail_under = 90` stays Python-only (deliberate, #180) |

## jsdom gotchas (for the tests)

- `require()` of `hidden_achievements.js` registers a `DOMContentLoaded` listener
  but jsdom is already past `load`, so init never runs — fine, we test the
  exported pure helpers, not init.
- Any path reaching `awardAchievement` needs `globalThis.getCsrfToken` and
  `globalThis.fetch` stubbed per test (both are free globals / unstubbed).
- `sessionStorage` / `localStorage` in jsdom are real but shared across a file —
  clear them in `beforeEach`.

## CLAUDE.md changes

1. New subsection "JS tests (Vitest)" — the decision note above, condensed, leading
   with the fake-timers rationale.
2. **Narrow** the existing passage (CSP / vendored-JS section, ~line 326) that says
   `package.json` + npm "was considered and rejected": scope that rejection to
   vendoring/bundling runtime assets; add that a dev-only test runner (#281) is a
   separate, accepted case. Grep for every place that reasoning appears.

## Verification

`pre-commit run --all-files` ×2 · `just test` · `just test-js` ·
`makemigrations --check` (no model change expected — skip if so) · `mypy` (no `.py`
change expected — skip if so) · `gh pr checks` until the new `js-tests` job is
actually green.

## Cleanup

Delete this spec file once CLAUDE.md carries the outcome — in this PR or a small
follow-up (planning-artifacts rule).
