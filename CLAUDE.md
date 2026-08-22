# CLAUDE.md — Agent rules for Suchar Overflow

## Project overview

Django 6.0 web app (joke aggregator). Backend: Python 3.14, PostgreSQL, Redis.
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
(defined in `pyproject.toml`) instead of extending it — the E2E run does **not** get
`--reuse-db`.

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
  being tested, never assert on all `UserAchievement` for a user.
- **Streaming responses**: the only streaming endpoint is the SSE stream, whose
  generator never completes. Do **not** use `b"".join(response.streaming_content)`
  — it hangs. Use `async for chunk in response.streaming_content` + `break`
  (see `achievements/tests/test_stream.py`).
- **Template language**: templates render in Polish (LANGUAGE_CODE = "pl").
  Don't assert on English strings in rendered HTML content.

## Code style — ruff rules in force

Active rule sets include: F, E, W, C90, I, N, UP, S, B, SLF, PL (covers PLC/PLE/PLR/PLW),
DJ, and many more. Only `S101`, `RUF012`, `SIM102` are globally ignored — the rules below
are all active.
Key rules that trip agents up:

| Rule | What it catches | How to fix |
|------|----------------|-----------|
| `SLF001` | Private member access (`_attr`) | Add `# noqa: SLF001` in tests that must poke private state |
| `PLC0415` | `import` inside a function | Move all imports to the top of the file. Exception: `*/apps.py` has a per-file-ignore for `PLC0415` — `AppConfig.ready()` methods (e.g. `AchievementsConfig`) may import inline. |
| `N806` | Uppercase variable in function (`User = ...`) | Use `user_model = get_user_model()` |
| `S106` | Hardcoded password string | Add `# noqa: S106` on test fixture passwords |
| `PLR2004` | Magic value comparison | Add `# noqa: PLR2004` on numeric assertions in tests |
| `E501` | Line > 88 chars | Shorten comments/docstrings; use `# noqa: E501` only as last resort |

`ruff format` enforces 88-char line width and import sorting (`force-single-line = true`).

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
scheduling `award_best_suchar` as a monthly cron job. The scheduler is skipped under
pytest and for management commands in `_NO_SCHEDULER` (`migrate`, `makemigrations`,
`collectstatic`, `compress`, `check`, `shell`, `createsuperuser`) to avoid starting
duplicate/unwanted schedulers. Since the jobstore is in-memory (no DB persistence
across restarts), `award_best_suchar` records its own last-run marker in the
`SchedulerRun` model (`achievements/models.py`), visible read-only in the admin.

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

Metric → what it evaluates:
- `COUNT_SUCHAR` → suchary authored by user
- `COUNT_VOTE_FUNNY` → funny votes **cast by** user (voter perspective)
- `COUNT_VOTE_DRY` → dry votes **cast by** user (voter perspective — same
  `user.suchar_votes` accessor as `COUNT_VOTE_FUNNY`, *not* votes received)
- `COUNT_VOTE_CAST` → all votes cast by user
- `SUM_SCORE` → net score of votes received on user's suchary (author perspective)
- `POLARIZER` → custom rule: suchar where funny == dry >= threshold
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
