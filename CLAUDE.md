# CLAUDE.md — Agent rules for Suchar Overflow

## Project overview

Django 6.1 web app (joke aggregator). Backend: Python 3.14, PostgreSQL, Redis.
Frontend: Django templates (DjangoTemplates backend), vanilla JS, CSS custom properties.
Package manager: `uv`. Local dev and CI both run inside Docker Compose.
Compose services: `django`, `postgres`, `redis`, `mailpit` (catches outgoing dev email at
`localhost:8025`).
Local Django apps: `suchar_overflow.users`, `suchar_overflow.suchary`,
`suchar_overflow.stats`, `suchar_overflow.achievements`. Model-level translations
(`django-modeltranslation`, `MODELTRANSLATION_LANGUAGES = ("pl", "en")`) are separate
from the `i18n`/`LANGUAGE_CODE` template-rendering language noted in Test patterns.

## Running commands

**Never** run Django management commands or pytest directly in the local `.venv`.
The local `.venv` does not have a `DATABASE_URL` set and `uv sync` may fail.
Always use the Docker container:

```bash
# Preferred — use justfile shortcuts
just test                        # run unit tests (excludes E2E)
just test-e2e                    # run Playwright E2E tests only
just test-all                    # unit tests then E2E sequentially
just test suchar_overflow/achievements/tests/test_engine.py  # targeted

# Direct docker compose equivalent (when DATABASE_URL must be explicit)
# Note: justfile and CI use `run --rm` (fresh container), not `exec` (existing one).
docker compose -f docker-compose.local.yml run --rm django bash -c \
  "export DATABASE_URL=postgres://USER:PASS@postgres:5432/suchar_overflow && \
   cd /app && python -m pytest ..."
```

Credentials are in `.envs/.local/.postgres`. The compose service is named `django`.

`just test-e2e` passes `--override-ini="addopts=..."`, which fully replaces `addopts`
(defined in `pyproject.toml`) instead of extending it, so `--reuse-db` must be repeated
explicitly in the override (see issue #214) — otherwise the E2E run drops and rebuilds
the test DB from scratch even though the unit-test step in the same CI job already built
an identical schema moments earlier, and the *next* unit-test run after E2E pays for
rebuilding it again (measured locally: unit suite ~10s with an existing DB vs. ~15s
immediately after a no-`--reuse-db` E2E run had dropped it). This is safe despite the
migration-seeded-data flush artifact described in "Migration-seeded achievements" below:
every E2E test already uses `@pytest.mark.django_db(transaction=True)` (needed because
Playwright drives the app from a separate process/thread), which truncates all tables on
teardown regardless of `--reuse-db`, so E2E tests already cannot rely on unfixtured
migration-seeded rows surviving between tests — only ones they (re)create themselves,
e.g. via `get_or_create` (see `frontend_achievements` in
`tests/e2e/test_hidden_achievements.py`). Verified empirically (issue #214): confirmed
via `SELECT oid, datname FROM pg_database WHERE datname='test_suchar_overflow'` that the
DB object (same OID) is genuinely reused, not silently dropped/recreated; running the
unit suite to flush seed data, then the E2E suite five consecutive times against that
same reused, already-flushed DB, still passed 31/31 every time. If you change a
migration and need a fresh E2E schema, pass `--create-db` through the recipe's `*args`:
`just test-e2e --create-db`.

### Unit tests vs E2E tests — critical distinction

There are two separate test suites that **must never be run together with the same settings**:

| Suite | Marker | Settings | Command |
|-------|--------|----------|---------|
| Unit/integration | *(no marker)* | `config.settings.test` | `just test` |
| Playwright E2E | `@pytest.mark.e2e` | `config.settings.e2e` | `just test-e2e` |

`config.settings.e2e` extends `test` but adds `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
for `127.0.0.1`/`localhost` (needed because Playwright POSTs trigger CSRF Origin checks).

The CI workflow runs them as separate steps with `-m "not e2e"` and `-m e2e` respectively.
**Never** run plain `pytest` (no `-m` filter) — it will collect E2E tests under the wrong
settings and fail with CSRF errors or missing browser fixtures.

### Coverage — unit suite only, blocking in CI

CI wraps the unit-test step in `coverage run` (config lives in `pyproject.toml`
under `[tool.coverage.run]`/`[tool.coverage.report]`), then runs `coverage report`
and `coverage xml`, uploading `coverage.xml` as an artifact alongside the junit
reports. `[tool.coverage.report] fail_under = 90` makes a coverage regression fail
the build even when every test passes — check locally with `just coverage` before
pushing, since neither `just test` nor `pre-commit` enforce this gate.

E2E tests are **not** instrumented and coverage from the two suites is never
combined — Playwright's E2E profile doesn't map cleanly onto the same
statement/template counts as the unit suite, so combining without a separate check
was deliberately skipped (issue #180).

`[tool.coverage.run] core = "ctrace"` is required, not incidental: Python 3.12+
switched coverage's default core to `sysmon`, which silently drops
`django_coverage_plugin`'s template file tracer (only a `CoverageWarning`, no
error) — measured coverage without `core = "ctrace"` was 88% counting Python
statements only, vs. 92% with template lines included. Do not remove this setting
when touching the coverage config.

## Running pre-commit

Pre-commit runs in the **local `.venv`**, not inside the container:

```bash
pre-commit run --all-files
```

It auto-fixes some issues on first run (ruff, ruff-format, djlint).
Always run a second time after auto-fixes to confirm all hooks pass.

## Test patterns

- All tests use `@pytest.mark.django_db`.
- pytest config: `--ds=config.settings.test --reuse-db --import-mode=importlib`
- `--reuse-db` keeps the DB between runs; pass `--create-db` to rebuild from scratch.
- The test settings (`config/settings/test.py`) use `locmem` cache (no Redis needed)
  and `COMPRESS_ENABLED = False` (no compressor).
- **Email sending**: views call `send_activation_email` / `send_email_change_emails`
  via `sync_to_async`. These functions call `django.core.mail.send_mail` directly.
  In tests, mock at the send_mail level or the task function level:
  ```python
  with patch("suchar_overflow.users.views.send_activation_email"):
      await client.post(...)
  ```
- **Migration-seeded achievements**: the DB has real Achievement rows from data
  migrations (e.g. "First Suchar", "Królowa/Król Sucharów"). Tests that create
  `Suchar` or `Vote` objects will trigger the achievement engine and award these.
  When asserting `UserAchievement` state, always filter by the specific achievement
  being tested, never assert on all `UserAchievement` for a user. Similarly, a
  `SchedulerRun(job_id="award-best-suchar-year")` row is baseline data seeded by
  migration `0015_seed_yearly_scheduler_run` (see Background scheduling below) —
  tests exercising `_catch_up_missed_yearly_run` must delete or `update_or_create`
  it first rather than assuming no marker exists.
- **Streaming responses**: the only streaming endpoint is the SSE stream, whose
  generator never completes. Do **not** use `b"".join(response.streaming_content)`
  — it hangs. Use `async for chunk in response.streaming_content` + `break`
  (see `achievements/tests/test_stream.py`).
- **Template language**: templates render in Polish (LANGUAGE_CODE = "pl").
  Don't assert on English strings in rendered HTML content.

## JS tests (Vitest)

`just test` has no JS coverage. Client-side logic in `suchar_overflow/static/js/`
— sequence matchers, key buffers, idle/combo timers, `sessionStorage`/`localStorage`
dedupe — is unit-tested with **Vitest + jsdom** (issue #281, option C: pure logic
here, Playwright E2E for the integration path — audio, the real
`POST /api/achievements/frontend-event`, toasts, CSP).

- **Why Vitest and not more E2E**: the logic that needs the most coverage is
  time-window logic (idle timers, combo windows, the 3s hover dwell). `vi.useFake
  Timers()` / `vi.advanceTimersByTime()` makes it deterministic and instant;
  `page.clock` against a real browser + a `transaction=True` DB per test does not.
- **Not a build step.** Vitest is a dev-only runner in the same category as pytest
  — it never transforms, bundles, or ships anything. The "no JS build step" rule
  (see *Vendored JS libraries* / *Content Security Policy*) is unaffected: npm for
  vendoring or bundling runtime assets stays rejected; npm as a test runner is the
  accepted, separate case.
- **Run it**: `just test-js` (or `npm test`). Runs on the **host**, not in a
  container — like `pre-commit`, no Django/DB dependency, Node is not in the Django
  image. Needs Node (`.nvmrc`) + a one-off `npm ci`. Config: `vitest.config.mjs`
  (`.mjs` because `package.json` is `"type": "commonjs"` so `.test.js` files can
  `require()` the plain scripts under test). Tests live in `tests/js/` — inert to
  pytest, kept out of `tests/e2e/`.
- **CI**: a dedicated `js-tests` job (`actions/setup-node` + `npm ci` + `npm test`),
  parallel to `linter`/`pytest`, no Docker. `package-lock.json` is committed and CI
  uses `npm ci`. Dependabot tracks the `npm` ecosystem (`.github/dependabot.yml`).
- **No JS coverage gate.** `fail_under = 90` stays Python-only; the two suites'
  coverage is never combined (deliberate, issue #180).
- **Reaching a classic script from a test**: the files under `static/js/` are
  classic `<script>`s concatenated inside `{% compress js %}` — adding `export` is
  a bundle-breaking SyntaxError. Instead, append a guarded CommonJS tail:
  `if (typeof module !== "undefined" && module.exports) { module.exports = {...} }`.
  `module` is undefined in the browser, so it is inert there and survives `rjsmin`.
  It is **not** dead code (like `window.__hiddenAchievementsReady`) — don't strip it
  in a JS sweep. `hidden_achievements.js` is the reference; `easter_eggs.js` (#282)
  follows the same pattern. Don't restructure a `{% compress js %}` block *to reach
  a script from a test* — the CJS tail is what makes that unnecessary;
  `tests/test_compressed_page_assets.py` guards that the served bundle stays a valid
  classic script. (Adding a genuinely global module to `base.html`'s block for a
  product reason, as #282 did with `easter_eggs.js`, is a different thing and is
  fine — same-block scripts still concatenate to one bundle.)
- **jsdom gotchas**: `require()` of a script registers its `DOMContentLoaded`
  listener but jsdom is already past `load`, so init never runs — test the exported
  helpers, not init. Stub `globalThis.getCsrfToken` and `globalThis.fetch` per test
  for any path that awards. Clear `sessionStorage`/`localStorage` and reset
  `document.body.innerHTML` in `beforeEach`. **`vi.resetModules()` does not detach
  listeners a `setupX()` added to `document`** — they accumulate across tests in a
  file. It's harmless where the handler is idempotent (`hidden_achievements.js`'s
  storage writes, `easter_eggs.js`'s own `DOMContentLoaded`) but the key-buffer /
  combo handlers a #283+ easter egg attaches to `document` are not — such a test
  must call `window.easterEggs.teardownAll()` (the module's own detach) in
  `afterEach` so the next test starts clean.
- **`vi.resetModules()` also does not re-run a CJS module reached via
  `require()`** — so a module's mutable module-level state (e.g. `easter_eggs.js`'s
  in-memory dedupe `Set`, its audio cache) survives between tests too.
  `easter_eggs.js` exposes `_resetForTests()` (attached only in the CJS tail,
  never on the browser `window.easterEggs`) which clears all of it; `beforeEach`
  in *both* `tests/js/easter_eggs.test.js` and `tests/js/hidden_achievements.test.js`
  calls it right after the `require`. New modules with module-level mutable state
  should follow the same pattern.

## Code style — ruff rules in force

Active rule sets include: F, E, W, C90, I, N, UP, S, B, SLF, PL (covers PLC/PLE/PLR/PLW),
DJ, ANN, ARG, and many more. Only `S101`, `RUF012`, `SIM102` are globally ignored — the
rules below are all active.
Key rules that trip agents up:

| Rule | What it catches | How to fix |
|------|----------------|-----------|
| `SLF001` | Private member access (`_attr`) | Add `# noqa: SLF001` in tests that must poke private state |
| `PLC0415` | `import` inside a function | Move all imports to the top of the file. Exception: `*/apps.py` has a per-file-ignore for `PLC0415` — `AppConfig.ready()` methods (e.g. `AchievementsConfig`) may import inline. |
| `N806` | Uppercase variable in function (`User = ...`) | Use `user_model = get_user_model()` |
| `S106` | Hardcoded password string | Add `# noqa: S106` on test fixture passwords |
| `PLR2004` | Magic value comparison | Add `# noqa: PLR2004` on numeric assertions in tests |
| `E501` | Line > 88 chars | Shorten comments/docstrings; use `# noqa: E501` only as last resort |
| `ARG001`/`ARG002`/`ARG003` | Unused function/method/classmethod argument | If genuinely removable (e.g. unused `*args, **kwargs` on a Django CBV method whose URL has no captured groups), delete it. If the name/position is mandated by a framework contract you don't control (Django signal receivers — dispatched by keyword, so the param name literally can't change; `ModelAdmin`/`ModelForm` overrides; polymorphic interfaces like `AchievementRule.evaluate`), add `# noqa: ARG00x` rather than renaming. For a pytest fixture used only for its side effect (never referenced in the test body), prefer `@pytest.mark.usefixtures("fixture_name")` over accepting-and-ignoring the parameter — it removes the violation and the dead parameter together. Never rename a pytest fixture parameter to silence this — fixtures are injected by exact parameter name. |
| `ANN001`/`ANN201`/etc. | Missing type annotation | See "Type annotations (ANN)" below — this codebase has real gotchas around *when* an annotation-only import can go under `TYPE_CHECKING`. |
| `ANN401` | Explicit `Any` in a signature | Legitimate for genuinely dynamic boundaries (Django management command `**options`, from argparse) — add `# noqa: ANN401` rather than mistyping as `object` and fighting mypy. |
| `FBT001`/`FBT002` | Boolean positional argument | Fires the moment a previously-untyped bool param gets annotated. If the name/position is framework-mandated (`ModelForm.save(commit=...)`, factory_boy `post_generation` hooks, signal receivers' `created`), add `# noqa: FBT001`/`FBT002` — don't reorder to keyword-only unless you also control every call site. |

`ruff format` enforces 88-char line width and import sorting (`force-single-line = true`).
When combining a `# type: ignore[code]` with a `# noqa: CODE` on the same line, the
`type: ignore` must come first — mypy only recognizes it as the leading comment.

### Type annotations (ANN) — TYPE_CHECKING guard rules

Python 3.14 (PEP 649) defers annotation evaluation by default, so an import used only in
a type annotation is normally safe to put under `if TYPE_CHECKING:` — this works even for
local variable annotations (`x: dict[str, Any] = {}`), which are never evaluated at
runtime at all. This project does **not** use `from __future__ import annotations`; stay
consistent with that (PEP 649 already gives the same benefit without it).

There are exactly two situations where an annotation-only import must stay a **real**
top-level import (with `# noqa: TC002`/`TC003` to satisfy the `TC` rule set), because
something reads the annotation at runtime, not just at type-check time:

- **`django.views.generic.View.dispatch()` overrides.** `View.as_view()` copies
  `cls.dispatch.__annotations__` at class-creation time, which forces the (otherwise
  lazy) annotation to resolve immediately. Only `suchar_overflow/users/mixins.py`
  overrides `dispatch()` in this codebase — regular `get`/`post`/etc. method overrides
  are *not* affected and can use `TYPE_CHECKING` freely.
- **Every django-ninja `@router.get/post/...` endpoint function**, in every parameter
  *and* the return type. Ninja calls `inspect.signature()`/`get_type_hints()` on the
  whole function at request-handling time; a `NameError` on a TYPE_CHECKING-only name
  only surfaces when the endpoint is actually hit (ruff and mypy won't catch it — write
  or run a test that hits the endpoint).

When `request.user` / `request.auser()` is accessed on a view/endpoint that's guarded by
`AsyncLoginRequiredMixin` or ninja's `auth=django_auth`, django-stubs still types it as
`User | AnonymousUser`. Narrow it explicitly rather than suppressing the error:
```python
user = await request.auser()
# AsyncLoginRequiredMixin already rejects anonymous requests.
assert isinstance(user, User)
```
(`assert` is fine here — `S101` is globally ignored, and production does not run with
`python -O`, so this is a real runtime guard, not just a mypy hint.)

## Settings architecture — do not break this

Settings layer: `base.py` → `local.py` / `test.py` / `production.py`, with `test.py` →
`e2e.py` as a further override (`e2e.py` extends `test.py` and adds `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, `CSRF_COOKIE_HTTPONLY = False`, and `DJANGO_ALLOW_ASYNC_UNSAFE`
for Playwright).

**Critical**: Python module-level code in `base.py` runs at import time.
A setting like `COMPRESS_ENABLED = not DEBUG` in `base.py` evaluates immediately
using `base.py`'s own `DEBUG`, **not** the child file's overridden value.

Rules:
- `base.py` always has the safest/most conservative default.
- Environment-specific overrides live entirely in `local.py`, `test.py`, or `production.py`.
- Never use expressions that reference sibling settings in `base.py` defaults
  (e.g. `X = not DEBUG`) if child files need a different value.

Current safe defaults in `base.py`:
- `COMPRESS_ENABLED = False` — production.py sets `True`
- `COMPRESS_OFFLINE = False` — production.py sets `True`

## Architecture notes

### Achievement notifications — no middleware, cache + polling

There is **no** `AchievementNotificationMiddleware` (it was removed — see
`0d5f6c5 Fix async achievement notifications and CSRF errors` — to stop the middleware
from clearing the cache before the SSE generator could read it). The current flow:
`AchievementEngine` sets cache key `achievements_pending:{user.pk}` when it awards an
achievement; `suchar_overflow/achievements/api.py` (`GET /api/achievements/unseen`, a
django-ninja endpoint) reads and clears that key when the frontend fetches it (triggered by the SSE
event — see below). Both that key and the bell-badge key `achievements_bell:{user.pk}`
are built by helpers in `suchar_overflow/achievements/cache.py` (`pending_cache_key`,
`bell_cache_key`) — that module is the single source for the key formats and for
`invalidate_bell_cache`; nothing should re-derive an `achievements_*:{pk}` string by
hand, and the signal/API layers import from there, not from `context_processors.py`.

`cache.py` also owns two more unrelated keys for the first-funny-vote 🥁 toast
(issue #292, umbrella #279 — pure UI delight, **no** achievement and no bell row):
`toast_pending:{user.pk}` (`toast_cache_key` / `set_pending_toast`), the one-shot
SSE-delivery flag, and `toast_sent_suchar:{suchar.pk}`
(`suchar_toast_sent_cache_key` / `mark_suchar_toast_sent`), a per-suchar
"already fired" latch (`cache.add`, 30-day TTL) so un-voting and re-voting a suchar
back through 0 → 1 does not keep re-toasting its author.
`suchary/api.py:vote_suchar` sets `toast_pending` when a suchar's **community**
funny-vote count (`community_funny` — a third `Count(... FILTER ...)` on the *same*
`suchar.votes.aggregate(...)`, so no extra query; `~Q(user_id=suchar.author_id)`
excludes the author's own vote) crosses `0 → 1` *and* `mark_suchar_toast_sent`
returns `True`. Excluding the author means a self-vote first no longer permanently
eats the toast — the next genuine community vote still fires it.
`GET /api/achievements/toast` clears `toast_pending` with a single
`cache.delete` whose return value doubles as the "was one pending?" check
(atomic — two racing fetches can't both return a payload).

### SSE stream (`/achievements/stream/`)

`suchar_overflow/achievements/views.py:achievement_stream` is a **long-lived polling
loop**, not single-shot: it yields an initial `retry: 5000\n\n`, then loops
`while True`, checking `achievements_pending:{user.pk}` (via `pending_cache_key`, see
above) every 2 seconds and yielding `data: new\n\n` when set; it only ends on
`asyncio.CancelledError` (client disconnect).

The loop also carries a **second, deliberately minimal** signal (issue #292, umbrella
#279): if `toast_pending:{user.pk}` (`toast_cache_key`) is set it additionally yields
`data: toast\n\n` on the same default event. This is the first-funny-vote 🥁 toast —
the loop still only *reads* both keys (never clears them); the browser
(`project.js`) branches on `event.data` (`new` → `GET /api/achievements/unseen`;
`toast` → `GET /api/achievements/toast`) and each fetch clears its own key. Two
guards keep the toast single-surface: `handleFirstFunnyToast` bails if
`document.visibilityState === 'hidden'` (a background tab must not consume the
shared key out from under the visible one) and holds an in-flight flag (the loop
re-emits `data: toast` every 2 s until the fetch clears the key). Keep this scope
tight — one flag, one canned toast, no per-message payload in the cache; anything
richer belongs behind its own endpoint, not a wider SSE protocol.

Because the generator never completes on its own, the general test advice
"consume with `b"".join(response.streaming_content)`" (see Test patterns above)
**does not apply to this endpoint** — it would hang. Tests instead iterate
`async for chunk in response.streaming_content` and `break` once they've seen what
they need (see `achievements/tests/test_stream.py`).

### Achievement API (`django-ninja`)

`suchar_overflow/achievements/api.py` exposes a `Router` mounted at `/api/` in
`config/urls.py`: `GET /achievements/unseen`, `POST /achievements/mark-seen`,
`GET /achievements/frontend-owned`, `POST /achievements/frontend-event` (the last is
how the frontend awards `FRONTEND_EVENT`-metric achievements for client-only actions,
gated by an allowlist of slugs in `VALID_FRONTEND_SLUGS`), and `GET
/achievements/toast` — pops `toast_pending:{pk}` with one atomic `cache.delete`
(its bool return *is* the "was one pending?" check) and returns the translated
first-funny-vote 🥁 toast (`ToastResponseSchema`: `{"toast": {"title", "body"}}` or
`{"toast": null}`); the text is `gettext`-ed here so it lands in the *author's*
language, not the voter's (issue #292).

`static/js/features/hidden_achievements.js` sets `window.__hiddenAchievementsReady =
true` at the end of its `DOMContentLoaded` handler — this looks like a no-op (no
production code reads it) but `tests/e2e/test_hidden_achievements.py` waits on it
instead of `wait_for_load_state("networkidle")`, because the achievement listeners
are only attached after an awaited `GET /achievements/frontend-owned` that the `load`
event isn't synced with (issue #221). Don't delete it as dead code in a JS cleanup.

### Easter-egg foundation (`features/easter_eggs.js`)

Issue #282, umbrella #278 (group A "delight" easter eggs). This module is the
shared groundwork; the child issues (#283+) each add one easter egg on top.
"Wire nothing global themselves" means a child adds **no new helper to
`window.easterEggs`** and no new global data blob — it consumes the surface
below. A child whose *trigger* must listen on every page (e.g. `konami.js`, #283)
still gets its own `<script>` in `base.html`'s global `{% compress js %}` block,
right after `easter_eggs.js`; that is expected, not a violation (same-block
scripts concatenate to one bundle, so `BASE_JS_BUNDLES` stays `1`). It exposes
`window.easterEggs` with:
`awardFrontendAchievement(slug)` / `alreadyAwarded(slug)` / `markAwarded(slug)` /
`award(slug)` (the session-dedupe + `POST /api/achievements/frontend-event` that
`hidden_achievements.js` used to carry its own copy of — it now delegates here);
`isMuted()` / `setMuted(bool)` (localStorage `ee_muted`, **default muted** — sound
only plays after an explicit `ee_muted === "0"` opt-in); `playSound(name)`;
`reducedJuice()` / `withJuice(fn)` (the single `prefers-reduced-motion` gate);
`registerTeardown(key, fn)` / `teardownAll()`.

- **It IS in `base.html`'s global `{% compress js %}` block**, after `project.js`
  (deliberate — children need `window.getCsrfToken`/`window.showToast`, and being
  global means it loads before every per-page bundle, so `hidden_achievements.js`
  can rely on `window.easterEggs`). Same-block scripts concatenate into one output
  file, so `BASE_JS_BUNDLES` in `tests/test_compressed_page_assets.py` stays `1`.
- **Sound**: `rimshot.wav` / `dust.wav` in `suchar_overflow/static/audio/`,
  regenerate with `just gen-audio` (`scripts/generate_easter_egg_audio.py`). They
  are **original CC0** works synthesised from the stdlib alone — no external
  encoder, so it runs anywhere, and plain 16-bit mono WAV is byte-deterministic
  (a Vorbis/Opus re-encode is not), so a no-op run leaves `git diff` clean. Both
  files together are ~42 kB. See `static/audio/AUDIO_CREDITS.txt`; unlike
  `flatpickr.LICENSE.txt` there is no upstream and no drift-guard test. A classic
  script can't resolve `{% static %}`, so `base.html` emits a small nonce'd
  `window.EE_AUDIO` map of the hashed URLs, for authenticated users only.
- `window.__easterEggsReady` is the same kind of init-complete signal as
  `window.__hiddenAchievementsReady`. No child needs it as a sync point yet, so
  `tests/js/easter_eggs.test.js` is currently its only reader (asserted there) —
  not dead code.

### Konami easter egg (`features/konami.js`)

Issue #283, umbrella #278 — the **first** group-A child on the #282 foundation,
and the first live `frontend-ee-` slug (`frontend-ee-konami` in
`VALID_FRONTEND_SLUGS`, seeded by migration `0020_konami_achievement_data`).
Detects `↑ ↑ ↓ ↓ ← → ← → B A` on any page for a logged-in user; on every correct
entry (it **replays**, deliberately — not one-shot) it fires a cracker overlay,
a wink toast, and `window.easterEggs.award('frontend-ee-konami')` (which POSTs
once per session via the sessionStorage dedupe). `window.__konamiReady` is its
init-complete signal — the E2E test waits on it before pressing keys.

- **The whole file is an IIFE.** Unlike `easter_eggs.js` / `project.js` (which
  also dump names at bundle top level but predate this and mostly namespace via
  `window.*`), `konami.js` keeps its many generic helpers (`rand`, `STYLE_ID`,
  `SVG_NS`, `keyBuffer`, …) private — a top-level `const` collision with a future
  group-A egg (#284+) sharing the same global `{% compress js %}` block is a
  bundle-wide `SyntaxError`, not a localised bug. The guarded CJS export tail
  lives *inside* the IIFE (closures still see `module`).
- **The key matcher is a fixed-length sliding window, not a rolling index.** A
  hand-rolled state machine desyncs on the repeated `↑ ↑` prefix: an odd run of
  `ArrowUp` before the real code (`↑ ↑ ↑ ↓ …`) leaves the index pointing at the
  wrong step and the egg never fires. `konami.js` keeps the last
  `SEQUENCE.length` keys and compares the buffer — O(1), immune to any junk or
  repeated prefix. `handleKeydown` also drops chords with `ctrlKey/altKey/metaKey`
  (browser/OS shortcuts like Ctrl+A, Alt+←) so they can't poison the buffer.
- **Particles are authored in JS (`makeCrackerEl()` — `createElementNS`), never
  cloned from `svgs/icon-cracker-stack.svg`.** That file's body is
  `<defs><g id="cracker-stack">` + `<use href="#cracker-stack">`; N copies in one
  document collide on the `id` and every `<use>` resolves the first. The rain
  particles carry no `id` and no `<use>`.
- **Inline styles are set property-by-property (`el.style.foo = …` /
  `el.style.setProperty('--ee-dx', …)`), not via `el.style.cssText`.** jsdom's
  CSSOM silently drops CSS custom properties (and some shorthands) assigned
  through `cssText`, so a `cssText` particle style passes in a real browser but
  the Vitest assertions on `--ee-dx` / `animationName` fail. The `@keyframes`
  block is injected once as a `<style id="ee-konami-style">` — CSP `style-src`
  has `'unsafe-inline'`, which covers both it and the inline `style=` attrs.
- The reduced-motion branch (`easterEggs.reducedJuice()` true — also the jsdom
  default, since it has no `matchMedia`) renders a **motion-free static scatter**
  (16 crackers, no `<style>` injected); the full branch is the ~42-particle
  falling downpour. Vitest tests must stub `window.matchMedia` to exercise the
  full branch.
- Its `keydown` handler is on `document` and its match buffer is module-level
  mutable state, so — per "JS tests (Vitest)" above — `tests/js/konami.test.js`
  calls `konami._resetForTests()` (its own detach + buffer reset, aliased to
  `teardownKonami`) each `beforeEach`/`afterEach`, and `easter_eggs.js`'s
  `teardownAll()` also reaches it (it registers via `registerTeardown('konami')`).
- rjsmin (in `{% compress js %}`) preserves the non-ASCII toast string (emoji,
  `…`, Polish diacritics) — verified against the production-storage
  `collectstatic` + `compress --force` bundle, not just `just test`.

### "ba dum tss" / dust easter egg (`features/badumtss.js`)

Issue #284, umbrella #278 — the **second** group-A child on the #282 foundation,
the sibling of `konami.js`. Types `suchar`, `badumtss`, or `ba dum tss` (matched
as literal suffixes of a rolling key buffer) on any page for a logged-in user;
on every match (it **replays**, like konami — not one-shot) it shows a
`🥁 / ba dum tss` toast and, unless `prefers-reduced-motion`, a ~24-mote
falling-dust overlay. `window.__baDumTssReady` is its init-complete signal — the
E2E test waits on it before typing.

- **Pure delight — no achievement, no `frontend-ee-` slug, no network.** It does
  not touch `VALID_FRONTEND_SLUGS`, `POST /api/achievements/frontend-event`, or
  `window.easterEggs.award`; the Vitest suite asserts `fetch` is never called.
  It consumes only `easterEggs.reducedJuice()` and `easterEggs.playSound`
  (the muted-by-default `rimshot` cue — `EE_AUDIO.rimshot` already exists from
  #282, no new audio file).
- **The whole file is an IIFE**, same reason as `konami.js`: its generic helpers
  (`rand`, `STYLE_ID`, `makeMote`, …) must not collide at bundle top level with
  konami's or a future #285+ egg's. The guarded CJS export tail lives inside the
  IIFE. It is in `base.html`'s global `{% compress js %}` block right after
  `konami.js` — same-block concatenation, so `BASE_JS_BUNDLES` stays `1`.
- **The key buffer is a bounded string with an idle-clear timer.** Only printable
  single-character `e.key` values extend it (`Shift`/`ArrowLeft`/… are inert and
  don't break a phrase); it is sliced to the longest phrase's length each
  keystroke, and a `setTimeout(…, 2000)` re-armed on every key wipes it after a
  typing pause so "sucha" now + "r" later can't combine. `handleKeydown` also
  drops form-field targets (`INPUT`/`TEXTAREA`/`SELECT`/`isContentEditable`) and
  `ctrl/alt/meta` chords, exactly like konami.
- **`prefers-reduced-motion` (or jsdom, no `matchMedia`) → the toast only** — no
  overlay is appended and no `<style>` is injected. This is *different* from
  `konami.js`, which still renders a motion-free static scatter; #284's issue
  says "sam toast".
- **Dust motes are plain `<div>`s** built in JS with styles set
  property-by-property (jsdom's CSSOM drops `--ee-dx` set via `cssText`). The
  drift `@keyframes` is injected once as `<style id="ee-badumtss-style">`; CSP
  `style-src` has `'unsafe-inline'`. The overlay is `div.ee-dust-overlay`
  (a class, not an id — replays leave several in the DOM at once) and is removed
  after ~2.2 s.
- Its `keydown` handler is on `document` and its buffer/timer are module-level
  mutable state, so — per "JS tests (Vitest)" above — `tests/js/badumtss.test.js`
  calls `badumtss._resetForTests()` (its own detach + buffer reset, aliased to
  `teardownBaDumTss`) each `beforeEach`/`afterEach`, and `easter_eggs.js`'s
  `teardownAll()` also reaches it (it registers via `registerTeardown('badumtss')`).
- rjsmin (in `{% compress js %}`) preserves the non-ASCII toast string (the 🥁
  emoji) — verified against the production-storage `collectstatic` +
  `compress --force` bundle, not just `just test`.

### "spin the logo" easter egg (`features/logo_spin.js`)

Issue #285, umbrella #278 — the **third** group-A child on the #282 foundation.
Mash the navbar logo 7× in quick succession → a short 360° logo spin (unless
`prefers-reduced-motion`) and a toast with a random "meta-suchar" about dryness /
the site. `window.__logoSpinReady` is its init-complete signal — the E2E test
waits on it. Same shape as `konami.js` / `badumtss.js`: whole file is an IIFE
(no top-level `const` collisions in the shared bundle), guarded CJS export tail
inside the IIFE, in `base.html`'s global `{% compress js %}` block right after
`badumtss.js` (so `BASE_JS_BUNDLES` stays `1`).

- **Pure delight — no achievement, no `frontend-ee-` slug, no network.** It does
  not touch `VALID_FRONTEND_SLUGS` / `POST /api/achievements/frontend-event` /
  `window.easterEggs.award`; the Vitest suite asserts `fetch` and `award` are
  never called. It consumes only `easterEggs.reducedJuice()` and
  `window.showToast`.
- **The count lives in `sessionStorage`, not memory — the logo is an
  `<a href="{% url 'home' %}">` and #285 requires the click to still navigate
  home**, so `preventDefault` is out and every click reloads the page, wiping any
  in-memory counter. `handleLogoClick` only records a "chain" (`{count, last}`
  under `ee_logo_clicks`); the effect fires from **`checkAndFire()`, run once per
  page load, on the load that follows the 7th click** — never from the click
  handler itself. It replays on every fresh burst of 7 (deliberately not
  one-shot, like konami / badumtss).
- **"Chain" semantics, a deliberate deviation from the issue's literal "wszystkie
  7 w oknie 3 s".** Each click within `CHAIN_MS` (3 s) of the *previous* one bumps
  `count`; a longer gap restarts the chain. A strict single 3 s window is
  unreproducible here: 7 clicks means 7 full page loads, which do not fit one 3 s
  window on a CI runner. The rolling per-gap window does (one home-page load is
  well under 3 s). `checkAndFire` (run on the load after the 7th click) discards a
  completed chain whose last click is older than `CHAIN_MS + RELOAD_GRACE_MS`
  (~7 s) — the extra slack is for the reload the 7th click itself triggered, so a
  genuine mash isn't lost on a slow connection; past that it's "mashed, then
  wandered off and navigated later → forgotten".
- **The spin is a `.ee-logo-spin` class on `.navbar-brand`** driven by a
  `@keyframes ee-logo-spin` + rule block injected once as
  `<style id="ee-logo-spin-style">` (CSP `style-src` has `'unsafe-inline'`); the
  class is stripped ~80 ms after the 600 ms animation. The `<style>` also carries
  a nested `@media (prefers-reduced-motion: reduce){…animation:none}` as defence
  in depth — the JS gate (`easterEggs.reducedJuice()`, jsdom-default true) already
  skips the whole branch.
- **The meta-suchar pool is a hand-authored `<script id="ee-logo-suchary"
  type="application/json">` data island in `base.html`, for authenticated users
  only — NOT inside `{% compress js %}`** (its translated text must not be
  minified into the bundle; a no-`src` `<script>` inside the block would also
  lose its `id` to `JsCompressor`). It is *not* the `json_script` filter —
  `base.html` has no view to build a context list — so each line is a `{% trans %}`
  string piped through `|escapejs` (a non-executable `type="application/json"`
  block is not subject to CSP `script-src`, so no nonce, matching the existing
  `json_script` usages). `tests/test_logo_spin_pool.py` guards that it renders
  valid JSON and survives `COMPRESS_ENABLED = True`. The msgids are **Polish**
  (unlike the English msgids elsewhere in `base.html`) — they render correctly
  against a stale catalog, and the sibling eggs' toast text is untranslated
  Polish in JS anyway; the `en` catalog entries land with the standing
  `chore(i18n)` regen (per #240). Keep any pool string free of a literal `%` —
  `makemessages` flags `3%`/`40%` as `#, python-format`, which trips
  `msgfmt --check-format` when that regen is landed (write "3 procent").
- Its `click` handler is on `.navbar-brand` and the chain is `sessionStorage`
  state, so — per "JS tests (Vitest)" above — `tests/js/logo_spin.test.js` calls
  `logoSpin._resetForTests()` (aliased to `teardownLogoSpin` — detaches, removes
  the `<style>`, strips the class, clears `ee_logo_clicks`) each
  `beforeEach`/`afterEach`, and `easter_eggs.js`'s `teardownAll()` also reaches it
  (registers via `registerTeardown('logoSpin')`).

### Background scheduling — APScheduler, not Django-RQ

Django-RQ has been removed entirely. `AchievementsConfig.ready()`
(`suchar_overflow/achievements/apps.py`) starts an in-process `BackgroundScheduler`
(raw `apscheduler` 3.x, default in-memory jobstore — `django-apscheduler` was dropped,
see issue #159: semi-abandoned, no declared Django 6.x support) on a plain thread,
scheduling `award_best_suchar` as two cron jobs: `award-best-suchar-month` (day=1,
00:05 UTC) and `award-best-suchar-year` (month=1, day=1, 00:05 UTC — see #168). The
scheduler is skipped under pytest and for management commands in `_NO_SCHEDULER`
(`migrate`, `makemigrations`, `collectstatic`, `compress`, `check`, `shell`,
`createsuperuser`) to avoid starting duplicate/unwanted schedulers. Since the
jobstore is in-memory (no DB persistence across restarts), `award_best_suchar`
records its own last-run marker in the `SchedulerRun` model
(`achievements/models.py`), visible read-only in the admin — one row per job id.

Because the jobstore only knows about *future* fire times, a process restart alone
does not catch up a cron fire that was due while the process was down (see #169).
`AchievementsConfig._catch_up_missed_monthly_run()` and
`_catch_up_missed_yearly_run()` cover this, one per job: on every scheduler start
each compares `SchedulerRun.ran_at` for its job id against the most recent due fire
time (`due_monthly_run_at()` / `due_yearly_run_at()` in `achievements/tasks.py`) and,
if that fire was never recorded, calls `award_best_suchar(period, reference_date=...)`
synchronously before `scheduler.start()` — `reference_date` is the missed fire's own
date, not "yesterday" relative to whatever day the process happens to restart
(`award_best_suchar` defaults `reference_date` to yesterday only when the caller
omits it, which is what the normal cron path does). Each catch-up runs in its own
`try/except` in `_start_scheduler` so a failure in one (e.g. a transient DB error)
never blocks the other catch-up or the recurring jobs from being registered.
Idempotent — `award_best_suchar` itself updates `SchedulerRun.ran_at`, so later
restarts within the same period don't re-trigger it. Only the single most recent
missed period is caught up per job — a gap spanning multiple months/years still
permanently loses the older ones; a brand-new deployment with no `SchedulerRun` row
yet also triggers one harmless catch-up run for the previous complete month.

The yearly job doesn't get that same free pass: unlike the monthly job (which was
already live before catch-up existed), the yearly job and its catch-up shipped
together (#168), and `award_periodic` — the pre-existing manual command — never
wrote a `SchedulerRun` marker (it calls `award_winners` directly, not
`award_best_suchar`). Without a marker, the first deploy's catch-up would
retroactively award the entire previous calendar year to whoever led it, the moment
the process started. Migration `0015_seed_yearly_scheduler_run` seeds a
`SchedulerRun(job_id="award-best-suchar-year")` row at migrate time specifically to
suppress that one-time retroactive award — the first *real* automatic yearly award
lands at the next actual Jan 1 cron fire. This seeded row is baseline data present
in every test (like the migration-seeded `Achievement` rows — see Test patterns
below), which is why several `achievements/tests/test_apps.py` /
`achievements/tests/test_models.py` tests delete or `update_or_create` it before
asserting on `SchedulerRun` state.

### Content Security Policy

Django 6.0's `django.middleware.csp.ContentSecurityPolicyMiddleware` is enabled in
`MIDDLEWARE` (`config/settings/base.py`), configured via `SECURE_CSP` in the same file.
`script-src` requires `CSP.NONCE` — inline `<script>` blocks need the nonce Django
injects. `style-src` allows `unsafe-inline` for CSS custom properties. There is no
third-party CDN allowlisted anywhere in `SECURE_CSP` — `chart.umd.min.js` and
`flatpickr` are vendored under `static/js/`, and fonts (Inter, Fira Code) are
self-hosted via `static/css/fonts.css`; none of them load from `cdn.jsdelivr.net` or
Google Fonts.
If you add inline `<script>` tags to a template, they must use the nonce or they will
be blocked in browsers that enforce CSP.

### Vendored JS libraries — no Dependabot coverage

`chart.umd.min.js` and `flatpickr.min.js` under `static/js/` are hand-vendored, not
managed by any package manager — `.github/dependabot.yml` only tracks `uv`, `docker`,
`docker-compose`, and `github-actions`, so neither Dependabot nor any bot notices when
a newer release ships (see issue #177). Adding a `package.json` + npm *to manage or
bundle these vendored runtime assets* was considered and rejected — it would require
introducing a JS build step the project deliberately doesn't have (see Content
Security Policy above), for two files that don't need one. (This is narrower than it
used to read: a `package.json` does now exist, but only for the **dev-only Vitest
test runner** — see *JS tests (Vitest)* above. That runner never touches served
assets, so it is not the build step this paragraph rejects.)

Instead: **check manually, roughly each time you touch this area or do a periodic
dependency review** (see #176-style project reviews). To check current vs. latest:

```bash
head -5 suchar_overflow/static/js/chart.umd.min.js   # vendored version, in the banner comment
curl -s https://registry.npmjs.org/chart.js/latest | grep -o '"version":"[^"]*"'
head -1 suchar_overflow/static/js/flatpickr.min.js   # whole file is 2 lines — line 2 is the minified bundle, head -1 only
curl -s https://registry.npmjs.org/flatpickr/latest | grep -o '"version":"[^"]*"'
```

To refresh a vendored file, pull the same jsdelivr npm build the existing file came
from (do not hand-edit the version banner — regenerate it):

```bash
curl -sSfL -o suchar_overflow/static/js/chart.umd.min.js \
  https://cdn.jsdelivr.net/npm/chart.js@<version>/dist/chart.umd.min.js
curl -sSfL -o suchar_overflow/static/js/flatpickr.min.js \
  https://cdn.jsdelivr.net/npm/flatpickr@<version>/dist/flatpickr.min.js
```

**Then strip any trailing `//# sourceMappingURL=...` line** from every vendored
file you just pulled (`.js` *and* `.css`) — the jsdelivr `dist/` builds end with
one, but the `.map` file is deliberately *not* vendored (see below), and
production's `CompressedManifestStaticFilesStorage`
(`config/settings/production.py`) hard-fails `collectstatic` when a
`sourceMappingURL` points at a missing file (issue #249) — `set -o errexit` in
`compose/production/django/start` then stops the container before
`compress --force` ever runs:

```bash
sed -i -E \
  -e 's|//# ?sourceMappingURL=[^[:space:]]*||' \
  -e 's|/\*# ?sourceMappingURL=[^*]*\*/||' \
  suchar_overflow/static/js/chart.umd.min.js \
  suchar_overflow/static/js/flatpickr.min.js \
  suchar_overflow/static/css/pages/flatpickr.min.css
```

(Covers both the JS `//# sourceMappingURL=` and the CSS `/*# sourceMappingURL=... */`
banner forms. It deletes only the comment, not the whole line — the vendored bundles
are 1–2 lines, so a blanket `sed '/.../d'` would nuke the bundle if a CDN ever appended
the banner to the code line instead of putting it on its own. As of the last refresh
only `chart.umd.min.js` actually carried one; running it against a file with none is a
harmless no-op.)

Vendoring the `.map` instead was rejected: it is a large file nobody debugs
into, and it adds another no-Dependabot artifact to keep in sync by hand. The
rule is **no `sourceMappingURL` reference in any vendored asset** —
`tests/test_vendored_static_no_sourcemap.py` is the regression guard, and
verifying `collectstatic --noinput` under production `STORAGES` in the container
is the belt-and-braces check (`DJANGO_SETTINGS_MODULE=config.settings.production`
plus dummy `DJANGO_SECRET_KEY`/`DJANGO_ADMIN_URL`/`DJANGO_ALLOWED_HOSTS`/
`DATABASE_URL`/`REDIS_URL`, then `python manage.py collectstatic --noinput --clear`).

Flatpickr also vendors a stylesheet at `suchar_overflow/static/css/pages/flatpickr.min.css`
— when bumping `flatpickr.min.js`, refresh the CSS from the same release too
(`https://cdn.jsdelivr.net/npm/flatpickr@<version>/dist/flatpickr.min.css`), or the JS
and CSS builds can drift out of sync.

`suchar_overflow/static/js/flatpickr.LICENSE.txt` carries flatpickr's MIT notice
and **must be refreshed in lockstep with `flatpickr.min.js`** (its first line is a
`flatpickr v<version>` marker; `tests/test_vendored_flatpickr_license.py` fails the
build if it drifts from the bundle's banner). It exists because `flatpickr.min.js`
now passes through `RJSMinFilter` (`COMPRESS_JS_FILTERS`), which keeps only bang
comments (`/*!`) — flatpickr's banner is a plain `/*` comment, so it is stripped
from the served `/static/CACHE/` bundle and the licence text would otherwise appear
in nothing production serves (issue #251). `collectstatic` ships the `.txt` next to
the bundle at `/static/js/flatpickr.LICENSE.txt`. Chart.js needs no such file — its
banner is `/*!`, which `rjsmin` preserves. Grab the text from the matching tag:
`curl -sSfL https://raw.githubusercontent.com/flatpickr/flatpickr/v<version>/LICENSE.md`
— but paste it *below* the file's existing header (the `flatpickr v<version>` marker
line plus the short explanatory block above the `---` rule), don't `curl` straight over
the file: that header is local, not upstream, and the version-marker test reads its
first line.

After swapping either file, check the upstream changelog for breaking changes in the
APIs this project actually uses, then manually verify in a browser (console clean, no
CSP violations) — `just test` has no JS test coverage, so a green suite is not
evidence the swap works. Chart.js usage: line/bar/doughnut charts on
`/stats/leaderboard/` and user profile pages. Flatpickr usage: check
`static/js/` for `flatpickr(` call sites before assuming defaults are unaffected.

### Async views

Most view classes are async (`async def get/post`, `AsyncLoginRequiredMixin` from
`suchar_overflow.users.mixins`) — not just the email-sending code path. When adding a
new class-based view, check a neighboring view in the same app first; the async
pattern (via `sync_to_async`/`request.auser()`/`aupdate()`/`async for`) is the norm,
not the exception.

### Django Compressor

`{% compress css %}` / `{% compress js %}` tags in `base.html` are transparent when
`COMPRESS_ENABLED = False` (dev/test). Only active in production after `manage.py compress --force`
runs (handled automatically in `compose/production/django/start`).

**Never use CSS `@import` for a project module** (issue #204). `COMPRESS_CSS_FILTERS`
(`CssAbsoluteFilter` + `RCSSMinFilter`) neither resolves nor inlines a bare
`@import 'x.css'` — `CssAbsoluteFilter` only rewrites `url(...)` / `src="..."`, so the
directive is copied into `/static/CACHE/css/output.<hash>.css` verbatim. Two problems:

- **It defeats the compressor.** Instead of the single minified bundle the
  `{% compress %}` block exists to produce, the browser gets that bundle *plus* ~22
  extra render-blocking requests it can only discover sequentially (it must fetch and
  parse the bundle before it sees the `@import`s). That is the #204 regression — the
  compressor stops doing the one thing it was switched on for.
- **Whether those copied `@import`s even resolve in production is incidental.**
  `production.py` sets `STORAGES["staticfiles"]` to a
  `CompressedManifestStaticFilesStorage`, and `compose/production/django/start` runs
  `collectstatic` *before* `compress --force`; Django's `HashedFilesMixin` rewrites
  `@import 'x.css'` → `@import url("x.<hash>.css")`, which `CssAbsoluteFilter` then
  *does* absolutise — so today's production bundle's imports happen to point at real
  files. Switch to any non-manifest `STORAGES`, or set `COMPRESS_ENABLED = True` in any
  other settings profile, and all ~22 turn into `/static/CACHE/css/<module>.css` → HTTP
  404. Invisible in dev/test because compression is off there.

`manage.py compress --force` is **not** a gate for this — it reports success on the
broken state too (confirmed on `main` during the #237 review). Exactly two unit tests
run with `COMPRESS_ENABLED = True`, and nothing else in the suite does:
`tests/test_compressed_css.py` asserts the `base.html` bundle has no `@import`, has
absolutised `url(...)` refs, and preserves the cascade order (writing into the gitignored
`staticfiles/CACHE/` via compressor's own storage); `tests/test_compressed_page_assets.py`
(#205) covers the page-specific blocks — see below. Both run on the default non-manifest
storage, so they guard "no `@import` in the bundle", not any particular production
render. Stylesheet composition therefore lives in the templates:

- One `{% compress %}` block = one output file, and **position inside the block is the
  cascade order**. `base.html`'s css block lists the ~21 global modules in the canonical
  order fonts → core → components → `project.css`; `utilities.css` and
  `components/forms.css` carry comments that depend on it. A new global module gets a
  `<link>` at the right position there. There is no `pages/` stage in the global block
  anymore — `pages/leaderboard.css` and `pages/profile.css` moved to page-specific
  blocks in #250 (`stats/leaderboard.html` and `users/base_dashboard.html`
  respectively; `base_dashboard.html` covers `user_detail`/`user_form`/
  `password_change_form`, since its sidebar uses `.dashboard-card`/`.sticky-sidebar`).
  Both load *after* the global bundle, so their equal-specificity `!important` rules
  (`.rank-*` vs `utilities.css`, `.sticky-sidebar` vs `layout.css`) still win on order.
  `.stats-text-sm` was shared by the leaderboard partial and `user_detail.html`, so it
  moved to `project.css` (still last in the global bundle) rather than either
  page sheet; `.sticky-preview` moved from `profile.css` to `pages/suchar_form.css`,
  its only consumer.
- A page template keeps `{{ block.super }}` **outside** any `{% compress %}` tag — it
  already expands to base's finished `<link ... CACHE/css/output.<hash>.css>`, and
  re-feeding a compressed output through the compressor is wrong — then opens its
  **own** `{% compress css %}` block for its page-specific sheets, a second output file.
  Don't try to merge page sheets into base's block. `base_dashboard.html` needs its own
  `{% load compress %}` — `{% load %}` does not inherit from `base.html`.
- Vendored, already-minified sheets (`pages/flatpickr.min.css`) are fine inside a block.

Page-specific `<script>` blocks (issue #205) follow that same "own block,
`{{ block.super }}` stays outside" rule, and add two JS-only ones. All three break only
under `COMPRESS_OFFLINE = True` (production; dev/test never notice):

- **`{{ block.super }}` inside your own `{% compress %}` block → `OfflineGenerationError`
  on *every* request.** Offline generation renders the block without the real parent
  context, so the runtime hash misses the offline manifest. Keep `{{ block.super }}`
  above the new block. (Verified as a negative control while implementing #205.)
- **Never put `json_script` output inside a `{% compress js %}` block.** `JsCompressor`
  treats any `<script>` without `src` as an inline hunk, minifies it into the bundle —
  the `id="..."` that `getElementById` needs is gone — and its per-request content
  guarantees an offline hash mismatch. `stats/leaderboard.html` and
  `users/user_detail.html` therefore use two compress blocks with the `json_script`
  calls between them.
- **`defer` must survive, and all `<script>`s in one block must share their attributes.**
  `{% block javascript %}` lives in `<head>`, so every page script needs `defer`;
  compressor emits a single `<script>` tag per block and does keep the attribute.

Also remember `{% load compress %}` in each page template — `{% load %}` does not inherit
from `base.html`. `tests/test_compressed_page_assets.py` is the regression guard for the
page-specific blocks. Most of it renders with `COMPRESS_ENABLED = True` (online),
asserting no raw `/static/` asset survives, that compressor's generated `<script>` tags
keep `defer`, and that the `json_script` ids are intact. One test
(`test_pages_render_under_offline_compression`) additionally builds the offline manifest
with `compress --force` and renders every page under `COMPRESS_OFFLINE = True`, so the
`{{ block.super }}` rule has a guard too — `compress --force` alone reports success on
the broken state, the `OfflineGenerationError` only fires at render time.

### Achievement engine

`AchievementEngine.check_achievements(user, event_type, instance=None)` looks up
`Achievement` rows by `event_type`, skips `PERIODIC` category, skips already-owned.
The engine only ever *awards* — it never revokes an achievement whose metric later
drops back below the threshold.

Two triggers feed it for votes (see `suchar_overflow/achievements/signals.py`,
`_award_vote_achievements`):

- **`post_save` of `Suchar` (SUCHAR_POSTED) and `Vote` (VOTE_CAST for voter,
  VOTE_RECEIVED for suchar author), `created=True` only.** The vote endpoint sets
  `is_funny`/`is_dry` via `Vote.objects.get_or_create(defaults=...)` so this first
  `post_save` already sees the final flag state — reverting that to a post-insert flag
  flip silently reintroduces #247 (the first funny/dry vote counted one vote late,
  because the flip's `save()` fires no signal).
- **`vote_changed`** (a plain `django.dispatch.Signal` defined in
  `suchar_overflow/suchary/signals.py`, sent *only* from `vote_suchar` in
  `suchary/api.py`, received in `achievements/signals.py`). Covers the toggle and
  removal paths — an existing `Vote` saved with `created=False`, or `delete()`d — where
  no `post_save(created=True)` fires. It re-runs the engine for voter and author on the
  final state, so a threshold newly crossed by a toggle (e.g. removing a dry vote raises
  the author's `SUM_SCORE`) is awarded immediately instead of lagging a vote (#247,
  direction 3). It is **not** a `post_delete` receiver on `Vote` on purpose:
  `Vote.suchar` and `Vote.user` are both `on_delete=CASCADE`, so a model signal would
  also fire mid-cascade when a Suchar or User is deleted — including
  `UserAchievement.objects.create()` for a user being deleted. A bare model-level
  `Vote.save()` (outside the endpoint) still does not re-check.

Rules split into `AchievementRule.compute_value(user, instance)` (the *threshold-
independent* metric value, or `None` when the rule can't be met at all — note that
`None` is not `0`, which would still satisfy `threshold=0`) and `evaluate()`, which
only compares that value with a threshold. `check_achievements` calls `compute_value`
**once per metric** and reuses the result for every candidate tier of that metric
(issue #200 — before that, a user sitting on N unearned tiers of one series re-ran the
same `.count()` N times inside the synchronous `post_save` path). Consequences for new
rules: implement `compute_value`, not `evaluate` (the engine never calls an overridden
`evaluate`), and keep it threshold-independent. `register_rules()` walks the whole
`AchievementRule` subclass tree (`_all_subclasses()`, issue #246), so an intermediate
base class grouping shared code between concrete rules is fine — give that base
`metric = None` (the engine skips it) and only the concrete rules a real metric. If two
concrete rules ever declare the *same* metric, `register_rules()` raises
`ImproperlyConfigured` naming both classes (issue #266) instead of letting the second
silently overwrite the first in `_rules`; the check runs inside the one-shot
`if cls._rules:` idempotency guard, so it fires on the first `register_rules()` call.

Metric → what it evaluates:
- `COUNT_SUCHAR` → suchary authored by user
- `COUNT_VOTE_FUNNY` → funny votes **cast by** user (voter perspective)
- `COUNT_VOTE_DRY` → dry votes **cast by** user (voter perspective — same
  `user.suchar_votes` accessor as `COUNT_VOTE_FUNNY`, *not* votes received)
- `COUNT_VOTE_CAST` → all votes cast by user
- `SUM_SCORE` → net score of votes received on user's suchary (author perspective)
- `POLARIZER` → custom rule: the highest `funny_count` (which, by the `funny ==
  dry` filter, equals `dry_count` — i.e. half the votes on that suchar, not
  `funny + dry`) among the user's perfectly-split suchary, compared against the
  threshold — equivalent to the old `funny_count__gte=threshold` + `.exists()`,
  but threshold-free so it runs once
- `STREAK_LOGIN` → consecutive days with at least one suchar posted
- `NIGHT_OWL` → suchar created between 00:00–04:00 local time
- `FRONTEND_EVENT` → not evaluated by a rule in `engine.py`; awarded directly by
  `POST /api/achievements/frontend-event` for client-only actions (e.g. UI interactions
  with no server-side signal)

Achievements also have a `Tier` (`NONE/BRONZE/SILVER/GOLD/PLATINUM/DIAMOND`,
`Achievement.Tier`) used to build tiered series (e.g. multiple thresholds of the same
metric/theme, such as "Królowa/Król Sucharów"). `AchievementListView` only reveals the
next unearned tier of each series to the user.

## Dependency management

Use `uv` for all dependency changes:

```bash
uv add <package>         # add to [project.dependencies]
uv add --dev <package>   # add to [dependency-groups].dev
uv lock                  # regenerate uv.lock
uv sync                  # install (run inside container or with venv active)
```

After adding dependencies, rebuild the Docker image before running tests in the container:
```bash
just build
```

Notable non-obvious dependencies already in use: `apscheduler`
(in-process job scheduling, see Architecture notes), `django-ninja` (the `/api/`
router), `django-modeltranslation` (model-field translation for `Achievement`, distinct
from the template-level `i18n` used elsewhere).

## Templates and static files

- Templates: `suchar_overflow/templates/` — Django template engine (`DjangoTemplates`)
  with `{% load compress %}`, `{% load static %}` and `{% load i18n %}` where needed.
- CSS: `suchar_overflow/static/css/` — uses CSS custom properties (`variables.css`).
- JS: `suchar_overflow/static/js/project.js` (main) + `js/features/` (split features).
- djlint enforces template formatting. After editing templates, run `pre-commit` to
  auto-format. djlint max line length for templates is 119 chars.
- **`{# … #}` comments are single-line only.** Django's lexer does not span newlines
  for that form, so a multi-line `{# … #}` is emitted into the page verbatim (it bit
  `base.html`'s `EE_AUDIO` block — #310, from #282, fixed with #284). Use
  `{% comment %} … {% endcomment %}` for anything multi-line. Don't put a literal
  `{% comment %}` / `{% endcomment %}` / `{# #}` token *inside* a `{% comment %}`
  block either — djlint miscounts the nesting and de-indents the rest of the file.
- Never use `innerHTML` with untrusted data. Use `createElement`/`textContent` or
  `appendChild` for dynamic DOM construction.

## Workflow — mandatory steps after every task

After completing **any** task (feature, fix, refactor):

1. Run `pre-commit run --all-files` (in the local `.venv`, **not** inside the container).
   Pre-commit auto-fixes some issues on first run — always run a **second time** to confirm
   all hooks pass cleanly.
2. Run `just test` (inside the Docker container). Fix all failures before considering the
   task done. Do not skip or comment out failing tests.
3. If you changed any model, run
   `docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations --check`.
   CI blocks the build on this — a model change without a matching migration will pass
   `just test` locally but fail CI.
4. If you changed any `.py` file, run mypy. It is **not** in `pre-commit` or
   `just test` — only a separate blocking CI step (`.github/workflows/ci.yml`,
   "Run mypy") — so a type error passes every local gate above and only fails the
   build:
   `docker compose -f docker-compose.local.yml run --rm django python -m mypy .`
   (or scope it to the changed files).

All steps are **blocking** — do not propose a commit or mark a task complete until they
all pass with no errors.

## Tests for new functionality

Whenever you add a new feature, view, model method, signal handler, or any non-trivial
logic, you **must** write tests for it in the same PR/commit. Tests go in the `tests/`
directory of the relevant app (e.g. `suchar_overflow/achievements/tests/`). Follow the
existing patterns in those files.

## Planning artifacts (`docs/superpowers/`)

Plans and specs written via `superpowers:writing-plans` / `superpowers:brainstorming`
live in `docs/superpowers/plans/` and `docs/superpowers/specs/`. Once the work they
describe is merged to `main` and its outcome is documented elsewhere (this file, code
comments, or the PR itself), delete the plan/spec file(s) — as part of that PR or a
small follow-up. Don't keep them around as historical artifacts; they go stale and
duplicate what's already documented. Git doesn't track empty directories, so
`docs/superpowers/` may simply be absent from the tree between planning sessions —
that's expected, not a regression.

## Pull requests and git

- Branch from `main`; target `main` for PRs. Name branches `<type>/<slug>`,
  where `<type>` is `feat`, `fix`, `docs`, or `release`.
- Commit messages: imperative mood, explain *why* not *what*.
- Never force-push `main`.
- Run `pre-commit run --all-files` and `just test` before proposing a commit.
- Always branch from the current `main`, never from another unmerged branch. If
  another open PR already touches the same files, still implement against `main`
  — a purely textual merge conflict is resolved when that PR is integrated and is
  not a reason to hold off. The one exception is a genuine functional dependency:
  the change can only be done correctly (or without duplicating work) on top of
  code that exists solely in an unmerged PR — then don't implement it, just note
  "waiting on PR #N" and stop.
- After opening a PR, own its CI result. A green local `pre-commit` / `just test`
  does not guarantee green CI (different Docker cache state, and mypy runs as its
  own CI step — see the mypy note above). Check `gh pr checks`; if a job fails,
  read the logs, fix on the same branch, push, and re-check until green — unless
  the failure has a documented out-of-scope cause (e.g. an unrelated flaky test),
  which you call out in the PR rather than chasing.

### Working from a GitHub issue

When a task starts from a GitHub issue (the user gives you an issue number or link):

1. Run `gh issue view <number>` to read the full issue body and comments —
   don't work from the title alone.
2. Branch from `main` using `<type>/<issue-number>-<slug>`, e.g.
   `fix/42-vote-count-bug` or `feat/58-add-dark-mode`. Non-issue-driven work
   keeps using the plain `<type>/<slug>` convention above — nothing changes
   there.
3. Implement and test as usual (see "Workflow — mandatory steps after every
   task").
4. Open the PR with `Closes #<issue-number>` in the description, so the issue
   auto-closes when the PR merges to `main`. Every issue-linked PR closes its
   issue — there is no "reference only" mode.

If you find a problem unrelated to the current issue while working (e.g. an
unrelated bug), you may propose opening a new issue with `gh issue create`,
but always ask for explicit confirmation first — never create an issue
unprompted.

Splitting the *current* issue is a different case and needs no confirmation. If
part of the issue's own scope is better done in its own PR (the diff is too large
for one review, or one part is independent in risk/mechanics from the rest), you
may create a new issue for the carved-out part yourself — referencing the parent
issue if the original had one — then comment the original explaining the split
and the new number, and finish only the remaining part. This standing
authorization covers only dividing the scope of the task you were given, not a
problem discovered on the side (which still needs confirmation, as above).

### Orchestrated multi-issue processing (alternative to single-task work)

The default is one task at a time. As an explicitly requested alternative, a
long-lived orchestrator can work a queue of open issues, dispatching one fresh,
single-use subagent per issue (each starts on a high-capability model — Opus —
and may spawn its own subagents). The orchestrator never waits for a human or a
merge inside the loop —
it moves to the next issue as soon as the subagent finishes. Merging the
resulting PRs (including resolving conflicts between PRs built in parallel off the
same `main`) is a separate process outside the loop, and code review of those PRs
is left to the human — the loop only creates PRs.

Before each dispatch, re-check the live state (`gh issue list --state open`,
`gh pr list --state open`) — an issue may have been closed by hand or picked up
elsewhere since the queue was drawn up. If subagents share one workspace rather
than a worktree each, confirm it is clean and back on `main` (`git status`,
`git switch main`) before the next branch is cut.

Each dispatched subagent ends its issue one of three ways:

- **Nothing to do** — the issue's condition hasn't occurred yet, the feature
  already exists, or (for an umbrella issue) not all child issues are closed.
  Comment on the issue explaining why. Close it if it was a one-off that is
  genuinely no longer relevant; leave it open with a status comment if it's a
  watch/tracker or an umbrella with open children. This conclusion must come from
  real verification (the actual upstream release state, the actual child-issue
  states), never an assumption — the quality gates still apply.
- **Blocked by an unmerged PR** — only when correct, non-duplicate work genuinely
  requires code that exists solely in another unmerged PR (not a mere textual
  conflict — see the PR rules above). Leave a "waiting on PR #N" comment and stop,
  without opening a PR.
- **Work to do** — branch from the current `main` as
  `<type>/<issue-number>-<slug>`, implement, write tests, run the full mandatory
  workflow, and open a PR with `Closes #<number>` — even if another still-open PR
  touches the same files. The subagent owns its PR to green CI before handing back
  control (see the CI-ownership rule above).

Umbrella / tracker issues have no technical scope of their own — they are just a
checklist of child issues. The assigned subagent checks every child: all closed →
close the umbrella with a summary comment; otherwise → short progress comment,
no close. A pure "watch" tracker (e.g. an upstream release) is the same shape:
verify the real status, comment, and touch code only if the tracked condition has
actually been met.

**Queue ordering**, most important criterion first:

1. Real logic bugs before optimizations — wrong output shown to users outranks a
   speed-up.
2. Foundational changes before follow-ups that depend on them (an index, or a
   compressor-loading fix, that a later issue only extends).
3. Backend before frontend — backend changes here carry `assertNumQueries` /
   regression unit coverage the pipeline verifies automatically, while most
   frontend work needs manual browser verification (`just test` has no JS/CSS
   coverage), so backend-first builds a tested history before the
   harder-to-verify PRs.
4. Simple, well-isolated fixes before ones needing a design decision — the latter
   get more room once the simpler items in the same group have gone through
   cleanly.
5. Grab-bag / sweep tasks after the targeted fixes that already touched some of
   the same files.
6. Umbrella / tracker issues last in their group — closed only once all children
   really are closed.
