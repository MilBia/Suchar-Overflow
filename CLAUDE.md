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
event — see below).

### SSE stream (`/achievements/stream/`)

`suchar_overflow/achievements/views.py:achievement_stream` is a **long-lived polling
loop**, not single-shot: it yields an initial `retry: 5000\n\n`, then loops
`while True`, checking `achievements_pending:{user.pk}` every 2 seconds and yielding
`data: new\n\n` when set; it only ends on `asyncio.CancelledError` (client disconnect).
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
gated by an allowlist of slugs in `VALID_FRONTEND_SLUGS`).

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
a newer release ships (see issue #177). Adding a `package.json` + npm just for these
two files was considered and rejected — it would require introducing a JS build step
the project deliberately doesn't have (see Content Security Policy above), for two
files that don't need one.

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

Flatpickr also vendors a stylesheet at `suchar_overflow/static/css/pages/flatpickr.min.css`
— when bumping `flatpickr.min.js`, refresh the CSS from the same release too
(`https://cdn.jsdelivr.net/npm/flatpickr@<version>/dist/flatpickr.min.css`), or the JS
and CSS builds can drift out of sync.

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

### Achievement engine

`AchievementEngine.check_achievements(user, event_type, instance=None)` looks up
`Achievement` rows by `event_type`, skips `PERIODIC` category, skips already-owned.
Signals call it on `post_save` of `Suchar` (SUCHAR_POSTED) and `Vote` (VOTE_CAST for
voter, VOTE_RECEIVED for suchar author) only when `created=True`.

Rules split into `AchievementRule.compute_value(user, instance)` (the *threshold-
independent* metric value, or `None` when the rule can't be met at all — note that
`None` is not `0`, which would still satisfy `threshold=0`) and `evaluate()`, which
only compares that value with a threshold. `check_achievements` calls `compute_value`
**once per metric** and reuses the result for every candidate tier of that metric
(issue #200 — before that, a user sitting on N unearned tiers of one series re-ran the
same `.count()` N times inside the synchronous `post_save` path). Consequences for new
rules: implement `compute_value`, not `evaluate` (the engine never calls an overridden
`evaluate`), keep it threshold-independent, and keep the rule a **direct** subclass of
`AchievementRule` — `register_rules()` discovers rules via `__subclasses__()`, which
only sees one level, so an intermediate base class would silently orphan them.

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
