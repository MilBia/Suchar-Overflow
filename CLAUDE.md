# CLAUDE.md — Agent rules for Suchar Overflow

## Project overview

Django 5.2 web app (joke aggregator). Backend: Python 3.13, PostgreSQL, Redis.
Frontend: Jinja2 templates, vanilla JS, CSS custom properties.
Package manager: `uv`. Local dev and CI both run inside Docker Compose.

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

# Direct docker-compose equivalent (when DATABASE_URL must be explicit)
docker-compose -f docker-compose.local.yml exec -T django bash -c \
  "export DATABASE_URL=postgres://USER:PASS@postgres:5432/suchar_overflow && \
   cd /app && python -m pytest ..."
```

Credentials are in `.envs/.local/.postgres`. The compose service is named `django`.

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
- **Django RQ**: tests that trigger `django_rq.enqueue` must mock it:
  ```python
  with patch("suchar_overflow.users.views.django_rq.enqueue"):
      client.post(...)
  ```
  `RQ_QUEUES` in test settings has `ASYNC: False` but still needs a Redis connection
  for `enqueue_call` — patching is required to avoid `ConnectionError`.
- **Migration-seeded achievements**: the DB has real Achievement rows from data
  migrations (e.g. "First Suchar", "Królowa/Król Sucharów"). Tests that create
  `Suchar` or `Vote` objects will trigger the achievement engine and award these.
  When asserting `UserAchievement` state, always filter by the specific achievement
  being tested, never assert on all `UserAchievement` for a user.
- **Streaming responses**: `StreamingHttpResponse` is evaluated lazily.
  Consume with `b"".join(response.streaming_content)` in tests.
- **Template language**: templates render in Polish (LANGUAGE_CODE = "pl").
  Don't assert on English strings in rendered HTML content.

## Code style — ruff rules in force

Active rule sets include: F, E, W, C90, I, N, UP, S, B, SLF, PLC, PL, DJ, and many more.
Key rules that trip agents up:

| Rule | What it catches | How to fix |
|------|----------------|-----------|
| `SLF001` | Private member access (`_attr`) | Add `# noqa: SLF001` in tests that must poke private state |
| `PLC0415` | `import` inside a function | Move all imports to the top of the file |
| `N806` | Uppercase variable in function (`User = ...`) | Use `user_model = get_user_model()` |
| `S106` | Hardcoded password string | Add `# noqa: S106` on test fixture passwords |
| `PLR2004` | Magic value comparison | Add `# noqa: PLR2004` on numeric assertions in tests |
| `E501` | Line > 88 chars | Shorten comments/docstrings; use `# noqa: E501` only as last resort |

`ruff format` enforces 88-char line width and import sorting (`force-single-line = true`).

## Settings architecture — do not break this

Settings layer: `base.py` → `local.py` / `test.py` / `production.py`

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

### Middleware — `AchievementNotificationMiddleware`

Runs on every non-API, non-stream request. Skipped paths: `/api/` and `/achievements/stream/`.
If you add new API-style or streaming endpoints, add them to `_BYPASS_PATHS` in the middleware.

### SSE stream (`/achievements/stream/`)

Single-shot SSE: yields one event then closes; browser auto-reconnects after `retry:` interval.
The endpoint is intentionally excluded from the notification middleware so the middleware
doesn't clear the cache before the generator can read it.

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
- `COUNT_VOTE_DRY` → dry votes **received on** user's suchary (author perspective)
- `COUNT_VOTE_CAST` → all votes cast by user
- `SUM_SCORE` → net score of votes received on user's suchary (author perspective)
- `POLARIZER` → custom rule: suchar where funny == dry >= threshold
- `STREAK_LOGIN` → consecutive days with at least one suchar posted
- `NIGHT_OWL` → suchar created between 00:00–04:00 local time

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

## Templates and static files

- Templates: `suchar_overflow/templates/` — Jinja2 via `django.template.backends.jinja2`
  with `{% load compress %}` and `{% load i18n %}` where needed.
- CSS: `suchar_overflow/static/css/` — uses CSS custom properties (`variables.css`).
- JS: `suchar_overflow/static/js/project.js` (main) + `js/features/` (split features).
- djlint enforces template formatting. After editing templates, run `pre-commit` to
  auto-format. djlint max line length for templates is 119 chars.
- Never use `innerHTML` with untrusted data. Use `createElement`/`textContent` or
  `appendChild` for dynamic DOM construction.

## Pull requests and git

- Branch from `main`; target `main` for PRs.
- Commit messages: imperative mood, explain *why* not *what*.
- Never force-push `main`.
- Run `pre-commit run --all-files` and `just test` before proposing a commit.
