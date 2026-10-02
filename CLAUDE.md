# CLAUDE.md — Agent rules for Suchar Overflow

## Project overview

Django 6.1 web app (joke aggregator). Backend: Python 3.14, PostgreSQL, Redis.
Frontend: Django templates (DjangoTemplates backend), vanilla JS, CSS custom properties.
Package manager: `uv`. Local dev and CI both run inside Docker Compose.
Compose services: `django`, `worker` and `cron` (RQ, same image — see Background jobs), `postgres`, `redis`, `mailpit` (catches outgoing dev email at
`localhost:8025`), `node` (webpack-dev-server on `localhost:3000`, see Frontend pipeline).
`compose/base/` holds what both stacks share (`django/entrypoint`, `healthcheck`, `worker`, `cron`, the `postgres/` image and
its `maintenance/` backup scripts); `compose/local/` and `compose/production/` hold only their
own Django `Dockerfile`/`start` plus Traefik/nginx (#456). Every `FROM` and pulled `image:`
names its registry (`docker.io/…`, `ghcr.io/…`), because podman doesn't assume Docker Hub;
`tests/test_compose_images.py` guards that. Postgres, Redis and Mailpit have healthchecks and
`django` waits for `service_healthy`. Django itself has none yet. Redis snapshots to a
named `/data` volume (`--save 60 1`).
Local Django apps: `suchar_overflow.users`, `suchar_overflow.suchary`,
`suchar_overflow.stats`, `suchar_overflow.achievements`, and `suchar_overflow.utils`
(#455: cross-cutting code — error handlers, middleware, context processors, logging,
DB-connection helpers, shared API schemas; no models). Model-level translations
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

# Direct docker compose equivalent
# Note: justfile and CI use `run --rm` (fresh container), not `exec` (existing one).
docker compose -f docker-compose.local.yml run --rm django python -m pytest ...
```

Credentials are in `.envs/.local/.postgres`. The compose service is named `django`.

`DATABASE_URL` is not in `.envs/.local/*`. `/entrypoint` exports it from `POSTGRES_*`
(unconditionally — it overwrites a `DATABASE_URL` passed with `run -e`, so pair that with
`--entrypoint ""`), and when it is absent (`docker compose exec` skips the ENTRYPOINT) `base.py` builds the
same URL-encoded DSN from `POSTGRES_*` itself (#453). So a plain
`docker compose -f docker-compose.local.yml exec django python manage.py …` works in a
running container; `just exec <cmd>` (e.g. `just exec python manage.py showmigrations`),
`just shell` (`shell_plus`) and `just bash` are shortcuts for it and need `just up`.
`just manage` (`run --rm`, no TTY required) is the one to use from scripts. Queue state:
`just exec python manage.py rqstats` (needs `just up`); `just logs worker cron` follows the RQ services. The #404
workaround (a `/etc/bash.bashrc` snippet sourcing the entrypoint) is gone.

The dev server (`compose/local/django/start`, copied into the image — edit it, then
`just build`) runs `uvicorn --reload --timeout-graceful-shutdown 3`. Keep the bound:
uvicorn's default is none, and each open `/achievements/stream/` SSE never finishes,
so a reload with a tab open used to hang the server until a container restart (#403;
`tests/test_local_dev_server.py` guards it). The `ERROR: Cancel N running task(s),
timeout graceful shutdown exceeded` line such a reload now logs is that expected
cancellation, not a fault. If the dev server hangs anyway, `curl -m 5
localhost:8000/` from the host (the image has no `curl`) tells server from browser
(6-connection HTTP/1.1 limit: one SSE per visible tab or one hidden < 30 s; pages
in bfcache no longer hold one, #428), and `just dump-stacks` (SIGUSR1 →
`faulthandler`, registered in `local.py`) prints every worker thread's stack to
`just logs`.

A hang with **no** reload in the log (#426) was an event-loop deadlock in asgiref
< 3.12: a client disconnecting while a sync-only middleware (it was
`WhiteNoiseMiddleware`) was still running made `ThreadSensitiveContext.__aexit__` join its thread on the loop that
thread was waiting for. Its stack dump reads main thread in `__aexit__` → `shutdown`
→ `join`, a worker in the sync middleware's `run_until_future`. The
`asgiref>=3.12.1` floor in `pyproject.toml` fixes it (production's
`UvicornWorker` runs the same stack); `tests/test_asgiref_disconnect_deadlock.py`
guards it with a Django-free asyncio script — keep the floor even though asgiref is
otherwise only a Django transitive. WhiteNoise itself is gone (#463): production's
`MIDDLEWARE` has no sync-only class, and `tests/test_static_serving.py` fails if one
returns (so the deadlock can't reappear through a new middleware either).

**Static files (#463).** Nothing in the Django process serves `/static/`. In production
`collectstatic --noinput --clear` (`compose/production/django/start`) writes
`STATIC_ROOT` (`/app/staticfiles`, `ManifestStaticFilesStorage`) into the
`production_django_static` volume — rw in `django`, `:ro` in `nginx`, which serves
`/static/` next to `/media/` (Traefik's `web-static-router` and `web-media-router` both
point at the `nginx` service). `compose/production/nginx/default.conf` gives names
ending in `.<12 hex>.<ext>` (the manifest storage's and webpack's `[contenthash]` with
`hashDigestLength: 12`) `Cache-Control: public, max-age=31536000, immutable`, everything else one hour,
turns on `gzip` and `gzip_static` (kept, but nothing writes `.gz` files any more — the webpack bundles
are built in the image, see _Frontend pipeline_ — so `gzip on` compresses everything on the fly).
The regex location is quoted — nginx reads an unquoted `{12}` as a block. `collectstatic`
runs with `--clear` (there is no production yet, so nothing to keep): each start wipes
the volume and rebuilds it, so it never accumulates files of past builds. The price: a
browser holding a page from the previous build can 404 on its old hashed CSS/JS until it
reloads. Drop `--clear` if that starts to matter once the site is live. Locally `config/asgi.py` wraps the app in
`ASGIStaticFilesHandler` only while `DEBUG` is on (uvicorn serves no static files);
`live_server` in E2E serves its own statics.

**`/healthz/` (#457).** `suchar_overflow/utils/views.py:healthz` is an async,
`never_cache` view answering `{"database": "ok"|"error", "cache": "ok"|"error"}` with 200
or 503 (details only in the log). The database check is `SELECT 1` wrapped in
`releases_db_connections`; the cache check is `PING` on the **raw** `django_redis`
connection, never `cache.get` — `IGNORE_EXCEPTIONS` would swallow an outage and always
report ok. Checks live in `HEALTH_CHECKS` (`database`, `cache`, and `queue` since #460).
`SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]` in production. The `django` container's
healthcheck is `compose/base/django/healthcheck` (stdlib Python — the image has no
`curl`; `/healthcheck <port>`): it sends `Host` = first `DJANGO_ALLOWED_HOSTS` entry
(`localhost` if unset/`*`; a bare `localhost` would raise `DisallowedHost` and mail the
admins on every probe) plus `X-Forwarded-Proto: https`, and counts any 3xx as failure.
Traefik and nginx `depends_on: django: service_healthy`. Tests use LocMem, so
`get_redis_connection` is patched there; `tests/test_healthz.py` also drives
`ASGIHandler` to prove a series of probes leaves no open connection.

**API conventions (#458).** `config/api.py`'s `SucharOverflowAPI` names every operation
`<router tag>_<function>` (`reverse("api:suchary_vote_suchar")`), so each `Router` must
carry `tags=[...]` — `tests/test_api_conventions.py` lists every operation and fails when a
new one is missing. **Authentication (#459):** `NinjaAPI(auth=[ApiToken(), django_auth])` — a
`Authorization: Bearer <token>` (`users.AuthToken`, one per user, issued only in the admin; only the
SHA-256 digest is stored and the clear text shows once in an admin message; an inactive user's token is
rejected) or the Django session (CSRF-checked). Endpoints inherit that default, so don't add
`auth=django_auth` per route; a public one needs an explicit `auth=None` (`GET /api/suchary/tags`).
`GET /api/users/me` returns `{"username"}`. Test with the `api_client` fixture
(`suchar_overflow/conftest.py`, `enforce_csrf_checks=True`). `/api/docs` follows `API_ENABLE_DOCS` (env `DJANGO_API_ENABLE_DOCS`, bare name as a one-release fallback, default on — switch it off
in production); `PermissionDenied` becomes a 403 `{"message": ...}`.

Worker RSS that climbs under load and never comes back (#431) was CPython 3.14.2's
incremental cycle collector, reverted in 3.14.5. Each ASGI request leaves its request
graph in a reference cycle, and that collector fell behind them (135 → 270 MB over 8
load rounds on 3.14.2, flat ~101 MB on 3.14.7). The image was stuck there because
astral's `uv:python3.14-bookworm-slim` tag stopped moving, so both Dockerfiles now
take Python from the official `docker.io/python:3.14-slim-trixie` (Debian 13, #437) and copy
`uv` in from a pinned `ghcr.io/astral-sh/uv:<version>` stage. All three `FROM
docker.io/python:` lines (local; production build and run) must name the same tag, so the
venv is never built against a different glibc than the one that runs it.
`tests/test_python_runtime.py` checks that statically, and in the local/CI image it
also fails on a pre-3.14.5 interpreter or a Debian release that doesn't match the
tag. The fix is `just build --pull` (`just prod-build --pull` for production),
because a plain build reuses the cached base.

A frozen official tag (docker-library stops rebuilding a Debian variant, as astral
did) is caught by `.github/workflows/base-image-freshness.yml` (#445). Every Monday,
and on `workflow_dispatch`, it runs `scripts/check_base_image_freshness.py`, which
pulls the tag the production Dockerfile names and compares its `Created` and
`PYTHON_VERSION` with endoflife.date's `latest` for the cycle. The tag counts as stale
when the image is more than 42 days old, or when it lags a 3.14.x that has been out
for more than 7 days. Exit 1 means stale; exit 2 means the check itself couldn't run,
which is never a silent pass; the pull and the API call are retried once first, so a
single network blip doesn't alert. On failure the workflow opens one issue titled
"Obraz bazowy python wygląda na zamrożony (#445)", or comments on it if it is already
open. A manual run with the `force_stale` input (limit 0 days) exercises that path on
a healthy image and marks the issue text as a drill. A PR that touches the script, the
workflow or the production Django Dockerfile it parses runs the check report-only. It
needs the network, so it is not in `just test`; only its pure logic is
(`tests/test_base_image_freshness.py`). Dependabot never
proposes a Python bump for the floating `3.14-slim-trixie` tag (minor/major are
ignored and the tag has no patch part), so its `docker-python` group PRs are in
practice uv bumps only. Residual blind spot: GitHub disables scheduled workflows after
~60 days without repository activity; re-enable it in the Actions tab after a quiet
spell. To check by hand, run `./scripts/check_base_image_freshness.py` on the host
(needs Docker). When it reports a frozen tag, switch every stage to the next Debian
codename at once. When the next Debian becomes stable, move then rather than waiting
for the freeze. `compose/base/postgres/Dockerfile` pins the codename the same way
(`docker.io/postgres:18-trixie`, #456); move it in the same change.

Locally, django-debug-toolbar with `SHOW_TEMPLATE_CONTEXT = True` still pushes a
worker to a ~1.3 GB high-water mark under a request flood: about 9 MB per stored
request, with the freed memory held by malloc. It is bounded and kept on purpose;
don't read it as a leak.

`just test-e2e` passes `--override-ini="addopts=..."`, which fully replaces `addopts`
(defined in `pyproject.toml`) instead of extending it, so `--reuse-db` must be repeated
explicitly in the override (see issue #214) — otherwise the E2E run drops and rebuilds
the test DB from scratch even though the unit-test step in the same CI job already built
an identical schema moments earlier, and the _next_ unit-test run after E2E pays for
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
`just test-e2e --create-db`. The recipe pins the E2E dir via pytest's `-o testpaths`
(honoured only when the command line names no path), so bare flags like that keep the
default without scanning the whole repo; to target one file, name it explicitly and it
overrides the default: `just test-e2e tests/e2e/test_konami_easter_egg.py` (see #361).

### Unit tests vs E2E tests — critical distinction

There are two separate test suites that **must never be run together with the same settings**:

| Suite            | Marker             | Settings               | Command         |
| ---------------- | ------------------ | ---------------------- | --------------- |
| Unit/integration | _(no marker)_      | `config.settings.test` | `just test`     |
| Playwright E2E   | `@pytest.mark.e2e` | `config.settings.e2e`  | `just test-e2e` |

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

The `ruff` and `djLint` hook `rev`s must equal the `==` pins in `pyproject.toml`'s
`dev` group — bump both together (and `django-upgrade`'s `--target-version` with
Django's minor). `tests/test_precommit_hook_versions.py` fails on drift (#451),
including a `--target-version` that isn't the Django minor in `[project.dependencies]`.
Dependabot bumps the pins but never the hook revs, so its `lint-tools` group PR
(ruff + djLint, split from the `python` group so it can't block other bumps) is red
until you push a commit to that PR with the matching `rev`
(`pre-commit autoupdate --repo <url>` bumps to the latest tag, so check it equals the pin).

## Test patterns

- All tests use `@pytest.mark.django_db`.
- pytest config: `--ds=config.settings.test --reuse-db --import-mode=importlib`
- `--reuse-db` keeps the DB between runs; pass `--create-db` to rebuild from scratch.
- The test settings (`config/settings/test.py`) use `locmem` cache (no Redis needed;
  local and production use Redis — see Settings architecture)
  and `WEBPACK_LOADER` is swapped for `FakeWebpackLoader` (no built bundles needed, see _Frontend pipeline_).
- **Email sending (#461)**: views queue `send_activation_email` and the two email-change jobs
  (`send_email_change_verify_email` / `send_email_change_notify_email`, one job per message so a retry
  never repeats the other send) through `enqueue_email` (`users/tasks.py`, `sync_to_async` in the async views), so a request
  sends nothing. The autouse `rq_queue` fixture (root `conftest.py`) mocks `django_rq.get_queue`:
  assert on `rq_queue.enqueue.call_args` (task, args, `language=`, `retry=`), then call
  `run_enqueued_jobs(rq_queue)` (`suchar_overflow/conftest.py`) to execute the jobs and read
  `mail.outbox`. Call a task directly, with `language=`, to test its rendering.
- **Migration-seeded achievements**: the DB has real Achievement rows from data
  migrations (e.g. "First Suchar", "Królowa/Król Sucharów"). Tests that create
  `Suchar` or `Vote` objects will trigger the achievement engine and award these.
  When asserting `UserAchievement` state, always filter by the specific achievement
  being tested, never assert on all `UserAchievement` for a user. Similarly, a
  `SchedulerRun(job_id="award-best-suchar-year")` row is baseline data seeded by
  migration `0015_seed_yearly_scheduler_run` (see Background jobs below) —
  tests exercising `award_best_suchar_year_if_due` must delete or `update_or_create`
  it first rather than assuming no marker exists.
- **Streaming responses**: the only streaming endpoint is the SSE stream, whose
  generator never completes. Do **not** use `b"".join(response.streaming_content)`
  — it hangs. Use `async for chunk in response.streaming_content` + `break`
  (see `achievements/tests/test_stream.py`).
- **Template language**: templates render in Polish (LANGUAGE_CODE = "pl").
  Don't assert on English strings in rendered HTML content.

## JS tests (Vitest)

`just test` has no JS coverage. Client-side logic in `webpack/src/js/`
— sequence matchers, key buffers, idle/combo timers, `sessionStorage`/`localStorage`
dedupe — is unit-tested with **Vitest + jsdom** (issue #281, option C: pure logic
here, Playwright E2E for the integration path — audio, the real
`POST /api/achievements/frontend-event`, toasts, CSP).

- **Why Vitest and not more E2E**: the logic that needs the most coverage is
  time-window logic (idle timers, combo windows, the 3s hover dwell). `vi.useFakeTimers()` / `vi.advanceTimersByTime()` makes it deterministic and instant;
  `page.clock` against a real browser + a `transaction=True` DB per test does not.
- **npm's role.** Vitest is a dev-only runner, like pytest — it ships nothing. npm itself is no
  longer limited to test tooling: since #465 it is also the source of the runtime libraries (`chart.js`,
  `flatpickr`) and of the webpack toolchain (see _Frontend pipeline_ and _JS libraries from npm_).
- **Run it**: `just test-js` (or `npm test`). Runs on the **host**, not in a
  container — like `pre-commit`, no Django/DB dependency, Node is not in the Django
  image. Needs Node (`.nvmrc`) + a one-off `npm ci`. Config: `vitest.config.mjs`
  (`include` is `tests/js/**/*.test.js`; `.mjs` because `package.json` is `"type": "commonjs"`,
  and webpack carries a `type: 'javascript/auto'` rule for `.js` so it accepts the `import` syntax).
  Tests live in `tests/js/` — inert to pytest, kept out of `tests/e2e/`.
- **CI**: a dedicated `js-tests` job (`actions/setup-node` + `npm ci` + `npm test`),
  parallel to `linter`/`pytest`, no Docker. `package-lock.json` is committed and CI
  uses `npm ci`. Dependabot tracks the `npm` ecosystem (`.github/dependabot.yml`).
- **No JS coverage gate.** `fail_under = 90` stays Python-only; the two suites'
  coverage is never combined (deliberate, issue #180).
- **Modules are ES modules; tests `import` them.** Every file under `webpack/src/js/` is an ES module
  with named exports, so a test just `import`s what it needs — no export tail, no `require()`. Keep the
  `window.__*Ready` flags, `window.easterEggs`, `window.showToast`, `window.getCsrfToken` and
  `window.EE_AUDIO`: E2E and the templates read them, even where no production code does. A module's
  `_resetForTests()` is a **named export** (not attached to `window.easterEggs`).
- **jsdom gotchas**: importing a module registers its `DOMContentLoaded`
  listener but jsdom is already past `load`, so init never runs — test the exported
  helpers, not init. Stub `globalThis.fetch` per test for any path that awards; the CSRF token comes from
  a `<meta name="csrf-token">` in `document.head` (`csrf.js` reads the DOM), not from a stubbed global.
  Mock the toast with `vi.mock('../../webpack/src/js/toast.js', () => ({ showToast: vi.fn() }))`. Clear
  `sessionStorage`/`localStorage` and reset `document.body.innerHTML` in `beforeEach`.
- **Module state survives between tests.** `vi.resetModules()` + `await import()` re-evaluates a module, but a
  statically imported one lives as a single instance per test file, so mutable module-level state (e.g.
  `easter_eggs.js`'s in-memory dedupe `Set`, its audio cache) is reset by the exported `_resetForTests()`;
  `beforeEach` in _both_ `tests/js/easter_eggs.test.js` and `tests/js/hidden_achievements.test.js` calls it.
  New modules with module-level mutable state should follow the same pattern.
- **`vi.resetModules()` does not detach listeners** a `setupX()` added to `document` or `window` — they
  accumulate across tests in a file. It's harmless where the handler is idempotent
  (`hidden_achievements.js`'s storage writes, `easter_eggs.js`'s own `DOMContentLoaded`) but the key-buffer /
  combo handlers an easter egg attaches to `document` (or `tumbleweed.js`'s activity listeners on `window`)
  are not — such a test must call `window.easterEggs.teardownAll()` (the module's own detach) in
  `afterEach` so the next test starts clean.
- **SCSS imports only in entry files.** Modules that Vitest imports never import a stylesheet (Vitest does
  not process SCSS); the page entries under `webpack/src/js/pages/` do.
- **Entry/chunk guard**: `tests/js/webpack_entries.test.js` — see _Frontend pipeline_.

## Code style — ruff rules in force

Active rule sets include: F, E, W, C90, I, N, UP, S, B, SLF, PL (covers PLC/PLE/PLR/PLW),
DJ, ANN, ARG, and many more. Only `S101`, `RUF012`, `SIM102` are globally ignored — the
rules below are all active.
Key rules that trip agents up:

<!-- prettier-ignore -->
| Rule | What it catches | How to fix |
|------|----------------|-----------|
| `SLF001` | Private member access (`_attr`) | Add `# noqa: SLF001` in tests that must poke private state |
| `PLC0415` | `import` inside a function | Move all imports to the top of the file. Exception: `*/apps.py` has a per-file-ignore for `PLC0415` — `AppConfig.ready()` methods (e.g. `AchievementsConfig`) may import inline. |
| `N806` | Uppercase variable in function (`User = ...`) | Use `user_model = get_user_model()` |
| `S106` | Hardcoded password string | Per-file-ignored in tests and `conftest.py` (`[tool.ruff.lint.per-file-ignores]`) — no `noqa` needed there; outside tests, fix it |
| `PLR2004` | Magic value comparison | Per-file-ignored in tests and `conftest.py` — write plain numeric assertions; outside tests, name the constant or add `# noqa: PLR2004` |
| `E501` | Line > 120 chars | Shorten comments/docstrings; use `# noqa: E501` only as last resort |
| `ARG001`/`ARG002`/`ARG003` | Unused function/method/classmethod argument | If genuinely removable (e.g. unused `*args, **kwargs` on a Django CBV method whose URL has no captured groups), delete it. If the name/position is mandated by a framework contract you don't control (Django signal receivers — dispatched by keyword, so the param name literally can't change; `ModelAdmin`/`ModelForm` overrides; polymorphic interfaces like `AchievementRule.evaluate`), add `# noqa: ARG00x` rather than renaming. For a pytest fixture used only for its side effect (never referenced in the test body), prefer `@pytest.mark.usefixtures("fixture_name")` over accepting-and-ignoring the parameter — it removes the violation and the dead parameter together. Never rename a pytest fixture parameter to silence this — fixtures are injected by exact parameter name. |
| `ANN001`/`ANN201`/etc. | Missing type annotation | See "Type annotations (ANN)" below — this codebase has real gotchas around *when* an annotation-only import can go under `TYPE_CHECKING`. |
| `ANN401` | Explicit `Any` in a signature | Legitimate for genuinely dynamic boundaries (Django management command `**options`, from argparse) — add `# noqa: ANN401` rather than mistyping as `object` and fighting mypy. |
| `FBT001`/`FBT002` | Boolean positional argument | Fires the moment a previously-untyped bool param gets annotated. If the name/position is framework-mandated (`ModelForm.save(commit=...)`, factory_boy `post_generation` hooks, signal receivers' `created`), add `# noqa: FBT001`/`FBT002` — don't reorder to keyword-only unless you also control every call site. |

`ruff format` enforces 120-char line width and import sorting (`force-single-line = true`).
Everything ruff and djLint don't format (JS, CSS, YAML, JSON, Markdown) goes through the
`prettier` pre-commit hook (#452): 120 columns, 4-space indent (Markdown 2, so nested list
blocks don't shift, and code inside Markdown fences is left as written), single quotes — options in `.prettierrc.json`, excluded paths
(templates, vendored `*.min.*`, lockfiles, `locale/`, `.devcontainer/devcontainer.json`,
and `.agent/workflows/` — prettier would fold its `// turbo` step annotations into the
preceding list item) in `.prettierignore`. The prettier version is pinned twice — the
hook's `additional_dependencies` and `package.json` `devDependencies` (so Dependabot's
`npm` ecosystem bumps it) — and `tests/test_precommit_hook_versions.py` keeps the two equal;
a Dependabot prettier PR needs the hook pin bumped in the same PR. Tables too wide to
pad (the ruff rules table below) sit under `<!-- prettier-ignore -->`. The one-off
repo-wide reformat is listed in `.git-blame-ignore-revs`; run
`git config blame.ignoreRevsFile .git-blame-ignore-revs` once per clone so `git blame`
skips it.
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
  are _not_ affected and can use `TYPE_CHECKING` freely.
- **Every django-ninja `@router.get/post/...` endpoint function**, in every parameter
  _and_ the return type. Ninja calls `inspect.signature()`/`get_type_hints()` on the
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

**Environment variables** (#453): environment-dependent settings come from env vars
prefixed `DJANGO_` (`DJANGO_ADMINS`, `DJANGO_EMAIL_*`, `DJANGO_STATIC_ROOT`, …), plus
`REDIS_URL`, `DATABASE_URL` / `POSTGRES_*`. `SECRET_KEY` (outside `test.py`) and
`REDIS_URL` have no default in code — local values are in `.envs/.local/.django`, so a
settings import outside compose (e.g. a hand-built `docker run` or build step) must set
them. In settings, `DATABASE_URL` wins when present, even empty (the production image's
build-time `compilemessages` relies on that); only when it is absent does `base.py` read
`POSTGRES_*`. A process started through `/entrypoint` always gets the entrypoint's
`POSTGRES_*` DSN, though (see "Running commands"). `base.py` also loads `.envs/.secrets`
(gitignored) when it exists; the OS environment wins over it, and `.env` (with
`DJANGO_READ_DOT_ENV_FILE`) over it too (`read_env` only `setdefault`s). `.dockerignore`
excludes `.envs/`, so the production image never contains it; production compose passes it
as an optional `env_file` (`required: false`) listed **first**, so `.envs/.production/.django` and
`.postgres` override it — the same precedence as `base.py`'s. Local compose deliberately
has no such entry: the bind mount already exposes the file to `base.py`, and a value compose
put in the environment would shadow a later edit of it until the container is recreated. `ADMINS` strips whitespace and drops blank
entries (a `" "` left by a trailing comma made every `mail_admins` send raise, silently).
`MAILERS` lives in `base.py` only; legacy `EMAIL_*` names are read as a fallback for one
release (CHANGELOG) — drop that fallback afterwards. An empty `DJANGO_EMAIL_*`/`EMAIL_*`
counts as unset there, unlike `DATABASE_URL`'s presence rule — keep the two apart.
Tests for this load a fresh copy of `base.py` from `tmp_path`
(`tests/test_env_settings.py`) instead of reloading the live module. Tests of
`production.py` go through `load_production_settings()` in `tests/settings_loader.py`
(stubbed env + `importlib.reload`) rather than a per-file copy of that helper.

**Critical**: Python module-level code in `base.py` runs at import time.
A setting like `X = not DEBUG` in `base.py` evaluates immediately
using `base.py`'s own `DEBUG`, **not** the child file's overridden value.

Rules:

- `base.py` always has the safest/most conservative default.
- Environment-specific overrides live entirely in `local.py`, `test.py`, or `production.py`.
- Never use expressions that reference sibling settings in `base.py` defaults
  (e.g. `X = not DEBUG`) if child files need a different value.

`CACHES` is defined once, in `base.py` (#454): django-redis on `REDIS_URL`, with
`IGNORE_EXCEPTIONS` (a Redis outage degrades to cache misses, not 500s) and
`ssl_cert_reqs: None` for a `rediss://` URL. `local.py` and `production.py` inherit
it, so the dev server shares the Redis container's cache (the SSE/toast flags behave
as in production and survive a dev-server restart); only `test.py` (and so `e2e.py`,
whose `live_server` runs in the same process) swaps in LocMem. `local.py` also lists
the template loaders explicitly (`APP_DIRS = False`, no `cached.Loader`): Django
resets the cached loader through `runserver`'s autoreload signal, which uvicorn never
sends, and uvicorn's `--reload` ignores `*.html`, so an edited template otherwise
kept rendering the old version until a restart. `tests/test_cache_settings.py`
guards both.

`CONN_MAX_AGE` is `0` in `base.py` and is the default in `production.py` (#430). Under ASGI
every request runs its sync code in its own `ThreadSensitiveContext` thread, so a
persistent connection outlives the request. Idle connections then pile up, one per
thread, until Postgres answers `too many clients already` (measured: 92 idle → 500s at
`60`; 11 and no errors at `0`). Django's docs: "When using ASGI, persistent connections
should be disabled". The env override remains, but don't raise it. If connection
reuse is ever needed, use psycopg's pool (`OPTIONS["pool"]`, needs the `pool` extra,
`max_size` below `max_connections`). Django refuses to combine that with a non-zero
`CONN_MAX_AGE` anyway, though only lazily, on first use. That is why the guard in
`tests/test_db_connection_settings.py` checks `CONN_MAX_AGE == 0` alone, with no
pool exemption.

Every dotted path the settings name as a string — `MIDDLEWARE`, the template
`context_processors`, and the `LOGGING` handler/filter/formatter `class`/`()` keys — is
imported by `tests/test_settings_import_paths.py` for both the test settings and
`config.settings.production` (#455). Ruff and mypy never read these strings, and some
(`mail_admins`) only resolve in production, so a module move that misses one fails there
first; keep the test green when moving code into or out of `suchar_overflow.utils`.

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
funny-vote count (`community_funny` — a third `Count(... FILTER ...)` on the _same_
`suchar.votes.aggregate(...)`, so no extra query; `~Q(user_id=suchar.author_id)`
excludes the author's own vote) is `>= 1` _and_ `mark_suchar_toast_sent`
returns `True`. Excluding the author means a self-vote first no longer permanently
eats the toast — the next genuine community vote still fires it. The count test
is `>= 1`, **not** `== 1` (the literal "0 → 1 transition"): `community_funny` is
recounted with an unlocked aggregate after every vote, so two non-authors
funny-voting near-simultaneously can each see the other's INSERT already
committed (`community_funny == 2`) and an `== 1` test would fire for neither
(#334). With `>= 1` both qualify on the count and the single-winner `cache.add`
latch (`mark_suchar_toast_sent`) still makes it exactly-once — no
`select_for_update` on the vote path. The one cost: after a Redis flush a suchar
that already carries community funny votes can fire one late toast; acceptable
for a best-effort UI-delight cue.
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
the loop still only _reads_ both keys (never clears them); the browser
(`app.js`) branches on `event.data` (`new` → `GET /api/achievements/unseen`;
`toast` → `GET /api/achievements/toast`) and each fetch clears its own key. Two
guards keep the toast single-surface: `handleFirstFunnyToast` bails if
`document.visibilityState === 'hidden'` (a background tab must not consume the
shared key out from under the visible one) and holds an in-flight flag (the loop
re-emits `data: toast` every 2 s until the fetch clears the key). Keep this scope
tight — one flag, one canned toast, no per-message payload in the cache; anything
richer belongs behind its own endpoint, not a wider SSE protocol.

**Client lifecycle (#428).** Each open stream is one long-lived connection, and the
HTTP/1.1 dev server gets only 6 per host from the browser (production's Traefik
negotiates HTTP/2 on 443, where the limit doesn't apply — config-based, not measured),
so `app.js` holds a stream only while the page is shown: a tab hidden for
`HIDDEN_STREAM_CLOSE_DELAY_MS` (30 s) closes it and reopens on return, and `pagehide`
closes it on the way into the bfcache, because Chromium keeps a bfcache'd
page's `EventSource` connected (each link click in one tab used to park another
stream, ~5 clicks hung the next navigation) and a frozen page never runs the hidden
timer. Closing loses nothing — the pending flags live in the cache and the reopened
stream re-reads them. On restore Chromium fires `visibilitychange` (visible) before
the persisted `pageshow`, so the visible branch reconnects and `pageshow` is only the
fallback (a no-op behind `!es`); the hidden branch arms no timer when `es` is already
`null`. Never add an `unload` listener (it disables bfcache). Guarded by
`tests/e2e/test_sse_bfcache.py`, which launches its own full-Chromium browser
(`channel="chromium"`) without Playwright's default `--disable-back-forward-cache`
(the headless shell refuses bfcache: `BackForwardCacheDisabledForDelegate`) and
fakes `EventSource`; a restore fires no `load`, so it uses
`go_back(wait_until="commit")`. It is parametrized: the second run suppresses
`visibilitychange`, so the `pageshow` fallback is exercised too.

**No pinned Postgres connection (#434).** The request's sync work (`auser()`, the
session lookup) opens a connection in its per-request `ThreadSensitiveContext`
thread. Only `request_finished` releases it, when the stream ends, so each open
tab held one idle connection (measured 1/5/10 for 1/5/10 streams). The loop reads
only the cache, so `event_stream()` calls `_release_db_connections()` as its
**first** step, via thread-sensitive `sync_to_async` in that same thread. It is
not called in the view body. The middleware response phase runs after the view
returns, and a session save there reopens the connection: with
`SESSION_SAVE_EVERY_REQUEST` a view-level close still left 5/10 connections, while
the generator close left 0. `achievements/tests/test_stream.py` guards both placements twice. The
`test_open_stream_releases_db_connection*` tests go through `AsyncClient`, which has
no per-request thread, so everything shares one executor thread. For that reason
`test_open_streams_release_db_connections_under_asgi_handler` drives
`get_asgi_application()` directly. It records every connection opened while the
streams are served via `connection_created` and does not count `pg_stat_activity`,
because other connections to the test DB would skew that count.

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
(its bool return _is_ the "was one pending?" check) and returns the translated
first-funny-vote 🥁 toast (`ToastResponseSchema`: `{"toast": {"title", "body"}}` or
`{"toast": null}`); the text is `gettext`-ed here so it lands in the _author's_
language, not the voter's (issue #292).

`webpack/src/js/features/hidden_achievements.js` sets `window.__hiddenAchievementsReady =
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
below. A child whose _trigger_ must listen on every page (e.g. `konami.js`, #283)
still gets its own `import` in `webpack/src/js/project.js` (the global `project` entry),
right after `easter_eggs.js`; that is expected, not a violation (it ends up in the one
global bundle). It exposes
`window.easterEggs` with:
`awardFrontendAchievement(slug)` / `alreadyAwarded(slug)` / `markAwarded(slug)` /
`award(slug)` (the session-dedupe + `POST /api/achievements/frontend-event` that
`hidden_achievements.js` used to carry its own copy of — it now delegates here);
`isMuted()` / `setMuted(bool)` (localStorage `ee_muted`, **default muted** — sound
only plays after an explicit `ee_muted === "0"` opt-in); `playSound(name)`;
`reducedJuice()` / `withJuice(fn)` (the single `prefers-reduced-motion` gate);
`registerTeardown(key, fn)` / `teardownAll()`.

- **It IS imported by the global `project` entry** (`webpack/src/js/project.js`), after `./app.js`
  (deliberate — children need `showToast`/`getCsrfToken`, which `app.js` publishes as
  `window.showToast`/`window.getCsrfToken` and which also live in `toast.js`/`csrf.js` that modules import
  directly; and being global means it runs before every page entry, since those have `dependOn:
'project'`, so `hidden_achievements.js` can rely on `window.easterEggs`). Nothing in the bundles reads
  `window.easterEggs` — modules import `easter_eggs.js` itself; the facade is for E2E and the console.
- **Sound**: `rimshot.wav` / `dust.wav` in `suchar_overflow/static/audio/`,
  regenerate with `just gen-audio` (`scripts/generate_easter_egg_audio.py`). They
  are **original CC0** works synthesised from the stdlib alone — no external
  encoder, so it runs anywhere, and plain 16-bit mono WAV is byte-deterministic
  (a Vorbis/Opus re-encode is not), so a no-op run leaves `git diff` clean. Both
  files together are ~42 kB. See `static/audio/AUDIO_CREDITS.txt`; unlike
  any npm package's licence there is no upstream and no drift-guard test. A bundle
  can't resolve `{% static %}`, so `base.html` emits a small nonce'd
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

- **An ES module** imported by `webpack/src/js/project.js` right after `easter_eggs.js`; its helpers
  (`rand`, `STYLE_ID`, `SVG_NS`, `keyBuffer`, …) are module-scoped, and the test-facing functions
  (`handleKeydown`, `_resetForTests`, …) are named exports.
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
- Terser (webpack's minifier) preserves the non-ASCII toast string (emoji,
  `…`, Polish diacritics) — verified against the production
  `npm run build` bundle, not just `just test`.

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
- **An ES module**, like `konami.js` (own scope for `rand`, `STYLE_ID`, `makeMote`, …; test-facing
  functions are named exports), imported by `project.js` right after `konami.js`.
- **The key buffer is a bounded string with an idle-clear timer.** Only printable
  single-character `e.key` values extend it (`Shift`/`ArrowLeft`/… are inert and
  don't break a phrase); it is sliced to the longest phrase's length each
  keystroke, and a `setTimeout(…, 2000)` re-armed on every key wipes it after a
  typing pause so "sucha" now + "r" later can't combine. `handleKeydown` also
  drops form-field targets (`INPUT`/`TEXTAREA`/`SELECT`/`isContentEditable`) and
  `ctrl/alt/meta` chords, exactly like konami.
- **`prefers-reduced-motion` (or jsdom, no `matchMedia`) → the toast only** — no
  overlay is appended and no `<style>` is injected. This is _different_ from
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
- Terser (webpack's minifier) preserves the non-ASCII toast string (the 🥁
  emoji) — verified against the production
  `npm run build` bundle, not just `just test`.

### "spin the logo" easter egg (`features/logo_spin.js`)

Issue #285, umbrella #278 — the **third** group-A child on the #282 foundation.
Mash the navbar logo 7× in quick succession → a short 360° logo spin (unless
`prefers-reduced-motion`) and a toast with a random "meta-suchar" about dryness /
the site. `window.__logoSpinReady` is its init-complete signal — the E2E test
waits on it. Same shape as `konami.js` / `badumtss.js`: an ES module imported by
`project.js` right after `badumtss.js`.

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
  7 w oknie 3 s".** Each click within `CHAIN_MS` (3 s) of the _previous_ one bumps
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
  only — NOT part of any bundle** (a bundle can't run `{% trans %}`, so the translated text lives in
  the template and the module reads it by `id`). It is _not_ the `json_script` filter —
  `base.html` has no view to build a context list — so each line is a `{% trans %}`
  string piped through `|escapejs` (a non-executable `type="application/json"`
  block is not subject to CSP `script-src`, so no nonce, matching the existing
  `json_script` usages). `tests/test_logo_spin_pool.py` guards that it renders
  valid JSON. The msgids are **Polish**
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

### Developer console easter egg (`features/console_egg.js`)

Issue #287, umbrella #278 — the **lightest** group-A child. On `DOMContentLoaded`
for a logged-in user it emits **one** styled `console.log("%c…\n%c…", artStyle,
textStyle)` in the devtools console: an ASCII wordmark (a nod to the cracker
stack) plus a short Polish wink and the repo URL. `window.__consoleEggReady` is
its init-complete signal — the E2E test waits on it before reading the captured
console output.

- **The absolute minimum of an egg — no achievement, no `frontend-ee-` slug, no
  network, no DOM, no audio, no animation.** It does **not** consume
  `window.easterEggs` at all (no reduced-motion gate, no `award`, no
  `playSound`), so it registers nothing with `registerTeardown()` and bundle
  import order past `app.js` is irrelevant to it. The Vitest suite asserts no
  `fetch`.
- **CSP:** `console.log` only — no `eval`, no inline `<script>`, nothing the CSP
  middleware has to allow.
- **An ES module** like `konami.js` / `badumtss.js` / `logo_spin.js` (its constants — `ART`, `TEXT`,
  `SESSION_KEY`, `REPO_URL`, the two style strings — are module-scoped), imported by `project.js`
  right after `logo_spin.js`.
- **"No spam" = once per browser session.** The latch is
  `sessionStorage['ee_console_shown']`, with an in-memory `shownThisPage`
  fallback set _before_ the `sessionStorage.setItem` so a storage failure
  (private mode / blocked cookies) still dedupes within the page. It **replays**
  in a new session (new tab / browser) — it is not a permanent one-shot.
- **Auth-gated** on `document.body.dataset.userIsAuthenticated === 'true'`, like
  the rest of group A — the greeting is aimed at contributors. An anonymous
  visitor still downloads the script (it is in the global bundle) but it stays
  silent; the E2E suite covers that.
- `ART` is a `String[]` joined with `'\n'`, deliberately backslash-free: a
  trailing `\` inside a single-quoted line would escape the closing quote.
- Terser (webpack's minifier) preserves the non-ASCII payload (the 😉 emoji,
  the Polish diacritics in the wordmark and the wink) — verified against the production
  `npm run build` bundle, not just `just test`.
- Its test-only export exposes `_resetForTests()` (clears `shownThisPage` **and**
  the `sessionStorage` key) for the `beforeEach`/`afterEach` in
  `tests/js/console_egg.test.js`, per "JS tests (Vitest)" above.

### Tumbleweed easter egg (`features/tumbleweed.js`)

Issue #288, umbrella #278 — the group-A child triggered by _absence_ of input.
On `/suchary` (any sub-page) for a logged-in user, 120 s with no `scroll` /
`mousemove` / `keydown` rolls a tumbleweed SVG across the lower screen edge with
the caption "cisza… aż tak sucho?", then it clears itself after ~4.4 s. It
**replays** on every fresh 120 s of stillness once the cooldown is up.
`window.__tumbleweedReady` is its init-complete signal — the E2E test waits on it
before advancing the fake clock. Same shape as the sibling eggs: an ES module
imported by `project.js` right after `console_egg.js`.

- **Pure delight — no achievement, no `frontend-ee-` slug, no network, no
  sound.** It consumes only `easterEggs.reducedJuice()` (via `registerTeardown`)
  and `window.showToast`. The Vitest suite asserts `fetch` and `easterEggs.award`
  are never called.
- **The trigger is a 120 s idle `setTimeout`, not a keydown match.** Passive
  (`{passive: true}`, per #288) `scroll` / `mousemove` / `keydown` / `pointerdown`
  listeners on `window` (`pointerdown` for a touch/pen tap — a phone reader never
  fires `mousemove`) all funnel into `handleActivity`, which is throttled to one
  re-arm per `ACTIVITY_THROTTLE_MS` (1 s — a 1 kHz mouse must not thrash the
  timer) → `armIdleTimer()`, which clears-and-resets the pending timer.
  `initTumbleweed` **only attaches and arms when `location.pathname` is `/suchary`
  or starts with `/suchary/`** (exact-or-slash, so a `/suchary-archiwum/` sibling
  route would never count) _and_ the body is authenticated — the app does full
  page reloads, so there is no per-navigation re-check to do; `onIdle` re-checks
  the path anyway before firing.
- **`onIdle` bails while the tab is backgrounded** (`document.visibilityState`
  `'hidden'`): CSS animations are frozen there, so a roll would burn the 5 min
  cooldown on something nobody sees (same reasoning as `app.js`'s
  first-funny-toast visibility guard). It re-arms and re-checks on the next idle
  window. `lastFireAt()` also rejects a _future_ stored timestamp — a system
  clock wound back by NTP/DST would otherwise make `Date.now() - last` negative
  and wedge the cooldown on for hours.
- **Cooldown is a `sessionStorage` timestamp (`ee_tumbleweed_last`), 5 minutes**,
  so the list's paginated reloads can't let it re-fire every 2 minutes. When
  `onIdle` finds itself still inside the cooldown it re-arms for **exactly the
  remaining cooldown** (`cooldownRemaining()`), not another full `IDLE_MS` — so
  the tumbleweed reappears promptly for a viewer who stays idle, rather than up
  to 2 minutes late. Any activity in the meantime re-arms the full idle wait.
- **`prefers-reduced-motion` (or jsdom, no `matchMedia`) → the caption as a
  `window.showToast(CAPTION, '🌾', 'info')`, and nothing else** — no overlay, no
  `<style>` injected. This differs from `konami.js` (which still renders a
  motion-free static scatter): here the caption _is_ the payload, so a toast
  carries it. A user-approved widening of #288's bare "pominięcie animacji" (the
  issue says only "skip the animation").
- **The tumbleweed SVG is authored in JS (`createElementNS`)** — a stroked ring
  plus jittered chords, one warm tan tone readable on both themes (like
  `badumtss.js`'s dust). No `id` on any particle; only the injected
  `<style id="ee-tumbleweed-style">` (two `@keyframes` — the wrapper's cross-screen
  `translateX` roll and the SVG's `rotate` spin) carries one. Inline styles are
  set property-by-property, not via `cssText` (jsdom drops custom props /
  shorthands set that way). The overlay is `div.ee-tumbleweed-overlay` (a class,
  not an id — replays can leave more than one mid-flight) and is removed by a
  `setTimeout` after `OVERLAY_LIFETIME_MS`.
- **E2E uses `page.clock` — the first user of it in `tests/e2e/`.**
  `page.clock.install()` before `goto`, then `page.clock.fast_forward(121_000)`
  to skip the 120 s idle without the suite waiting two real minutes (issue #288 →
  #281). The `_IDLE_JUMP_MS = 121_000` value is load-bearing: `fast_forward`
  fires _every_ timer due in the window, so the jump must land **past** the
  120 s idle threshold but **before** `fire + OVERLAY_LIFETIME_MS` (~124.4 s) or
  the same call also runs the removal timer and the overlay is gone before the
  assertion. The removal itself is covered by a second `fast_forward(10_000)`.
- Its `scroll`/`mousemove`/`keydown` handlers are on `window` and the idle
  timer + `activityHandler` ref are module-level mutable state, so — per "JS tests
  (Vitest)" above — `tests/js/tumbleweed.test.js` calls
  `tumbleweed._resetForTests()` (aliased to `teardownTumbleweed` — detaches the
  listeners, clears the idle + removal timers, removes overlays and the `<style>`,
  clears `ee_tumbleweed_last`) each `beforeEach`/`afterEach`, and
  `easter_eggs.js`'s `teardownAll()` also reaches it (registers via
  `registerTeardown('tumbleweed')`).
- Terser (webpack's minifier) preserves the non-ASCII caption (the `…`
  ellipsis, Polish diacritics) — verified against the production
  `npm run build` bundle, not just `just test`.

### "Niezdecydowany" / theme-spam easter egg (`features/theme_spam.js`)

Issue #289, umbrella #278 — the group-A child triggered by mashing the theme
toggle itself. 10 clicks on `#theme-toggle` within a 5 s window shows a
"Zdecyduj się 🙃" toast, a quick 360° spin of the toggle icon (unless
`prefers-reduced-motion`), and the hidden `frontend-ee-niezdecydowany`
achievement — `frontend-ee-niezdecydowany` in `VALID_FRONTEND_SLUGS`, seeded by
migration `0021_niezdecydowany_achievement_data`. It **replays** on every fresh
burst of 10 (like konami / badumtss / logo_spin — deliberately not one-shot).
`window.__themeSpamReady`
is its init-complete signal — the E2E test waits on it before clicking. Same
shape as the sibling eggs: an ES module imported by `project.js` right after
`tumbleweed.js`.

- **The trigger is a `click` listener directly on `#theme-toggle`, not a
  `MutationObserver` on `data-theme`.** `app.js` calls
  `setTheme(currentTheme)` unconditionally on every page load, which would be
  a built-in false positive for an attribute observer — the click listener has
  no such problem.
- **The click buffer lives in memory, not `sessionStorage`.** Unlike
  `logo_spin.js` (whose logo is an `<a>` that navigates and wipes memory,
  forcing a sessionStorage chain), `#theme-toggle` is a plain `<button>` — no
  reload — so state survives in memory exactly like konami's key buffer.
  Don't port logo_spin's chain/grace-period machinery here; it solves a
  problem this egg doesn't have.
- **A sliding window of the last 10 click timestamps, not an idle-clearing
  counter.** `handleToggleClick` pushes `Date.now()` and shifts the oldest
  entry off once the buffer exceeds 10 — self-cleaning, no idle timer needed
  (unlike `badumtss.js`'s typed-phrase buffer). It fires when the buffer holds
  exactly 10 timestamps spanning ≤ 5000 ms, then clears itself so a replay
  needs a fresh 10.
- **The egg never calls `setTheme` and never touches `localStorage.theme` or
  the theme cookie** — it only counts clicks on a button `app.js`'s own
  listener already owns. This is what makes #289's "motyw kończy w stanie z
  ostatniego kliknięcia (bez psucia preferencji)" true by construction; both
  Vitest and the E2E test assert it explicitly rather than trusting the
  absence of a call.
- **The spin is a `.ee-toggle-spin` class on `#theme-toggle` itself** (not a
  separate overlay), driven by a `@keyframes ee-toggle-spin` + rule block
  injected once as `<style id="ee-theme-spam-style">` — copied from
  `logo_spin.js`'s `.ee-logo-spin` mechanics (CSP `style-src` has
  `'unsafe-inline'`; the class is stripped ~80 ms after the 600 ms animation;
  the `<style>` also carries a nested
  `@media (prefers-reduced-motion: reduce){…animation:none}` as defence in
  depth, since the JS gate already skips the whole branch).
  `prefers-reduced-motion` (or jsdom, no `matchMedia`) → the toast + award
  only, no spin, no `<style>` injected.
- The achievement icon is Bootstrap Icons' `bi-yin-yang` (half light, half
  dark) — fetched from the upstream SVG, not hand-typed path data (konami's
  `bi-controller` migration is the precedent: reconstructing path data from
  memory renders wrong and nothing catches it).
- Its `click` handler is on `#theme-toggle` and the timestamp buffer is
  module-level mutable state, so — per "JS tests (Vitest)" above —
  `tests/js/theme_spam.test.js` calls `themeSpam._resetForTests()` (aliased to
  `teardownThemeSpam` — detaches the listener, clears the spin timers, strips
  the class, removes the `<style>`, clears the buffer) each
  `beforeEach`/`afterEach`, and `easter_eggs.js`'s `teardownAll()` also reaches
  it (registers via `registerTeardown('themeSpam')`). Most of its Vitest
  suite drives the exported `handleToggleClick()` directly (like konami's
  `handleKeydown`) rather than dispatching DOM `click` events, since the real
  listener only exists after the module's own `DOMContentLoaded` init runs;
  the wiring tests (attach/detach, authed/anonymous gating) dispatch real
  `click` events on the button instead, to actually exercise that listener.
- Terser (webpack's minifier) preserves the non-ASCII toast string (the
  🙃 emoji, Polish diacritics) — verified against the production
  `npm run build` bundle, not just `just test`.

### "Archeolog" / scroll-to-bottom easter egg (`features/archeolog.js`)

Issue #290, umbrella #278 — the sixth and last group-A child on the #282
foundation, and (with konami.js / theme_spam.js) one of the three that award
a real hidden achievement rather than pure delight. Scrolling to the bottom
of the _last_ page of `/suchary` (any sub-page) for a logged-in user shows a
"Dotarłeś do dna. Sucharów. Gratulacje." toast and awards the hidden
`frontend-ee-archeolog` achievement (`frontend-ee-archeolog` in
`VALID_FRONTEND_SLUGS`, seeded by migration
`0022_archeolog_achievement_data`) — but only once the list has grown to at
least `MIN_TOTAL_PAGES` (5) pages, a deliberate widening of the issue's
literal trigger: without a floor, a brand-new deployment with barely any
suchary would hand this out for scrolling past an almost-empty page, which
defeats the point of "reaching the bottom" meaning anything. It fires at
most once per session — not a replaying egg like konami/badumtss/logo_spin/
theme_spam, since there is nothing to replay until a full reload puts you
back near the top of a list this long. `window.__archeologReady` is its
init-complete signal — the E2E test waits on it before scrolling. Same
shape as the sibling eggs: an ES module imported by `project.js` right
after `theme_spam.js`.

- **"Last page" and "total pages" are both read structurally from
  `.pagination`, never from the (translated) "Next" label text.** The
  trailing `<li>` (the "Next" slot in `suchar_list.html`'s Previous / page
  numbers / Next layout) has no `<a>` — and carries the `.disabled` class,
  checked as a second, redundant signal for the same fact — when there is no
  next page; the active page's number (`.page-item.active .page-link`,
  never elided by `paginator.get_elided_page_range()`) doubles as the total
  page count, since it's only read once "no next page" is already
  confirmed.
- **The `scroll` listener is a leading-edge throttle with a trailing check,
  not a plain leading-edge throttle.** A single discrete jump to the bottom
  (an `End` keypress, or a gesture that stops moving right at the edge) can
  fire its only `scroll` event inside the throttle window, with no further
  event to re-check on — a plain leading-edge throttle would then silently
  miss that arrival for the rest of the page load. `handleScroll` schedules
  one trailing `setTimeout` for the remainder of the window in that case, so
  the geometry still gets checked once even when no more `scroll` events do.
  The elapsed-time comparison treats a negative delta (system clock wound
  backward mid-session — NTP/DST) as "due now" rather than getting stuck
  waiting out a window that will never elapse — same guard shape as
  `tumbleweed.js`'s `lastFireAt()` / `theme_spam.js`'s click-window check,
  kept on `Date.now()` (not `performance.now()`) for consistency with those.
- **`isNearBottom()` reads `Math.max` of `document.documentElement
.scrollHeight` and `document.body.scrollHeight`**, not just the former —
  belt-and-suspenders in the same spirit as `tumbleweed.js`'s
  `isDocumentHidden()` checking both `visibilityState` and `hidden`, even
  though a standards-mode document (Django always renders a doctype) makes
  the two heights agree in practice.
- **No animation, so nothing for `prefers-reduced-motion` to gate** — the
  effect is `window.showToast` and nothing else, unlike the other
  award-granting siblings (konami's confetti rain, theme-spam's icon spin).
- Its `scroll` handler is on `window` and the throttle timestamp / pending
  trailing timer / settled flag are module-level mutable state, so — per "JS
  tests (Vitest)" above — `tests/js/archeolog.test.js` calls
  `archeolog._resetForTests()` (aliased to `teardownArcheolog` — detaches
  the listener, clears the pending trailing timer, resets the throttle and
  settled state) each `beforeEach`/`afterEach`, and `easter_eggs.js`'s
  `teardownAll()` also reaches it (registers via
  `registerTeardown('archeolog')`).

### "Publika Rozgrzana" / combo easter egg (`features/publika_rozgrzana.js`)

Issue #296, umbrella **#279** (jokes woven into mechanics — _not_ #278, though
it reuses the #282 foundation and the `frontend-ee-` slug prefix). Casting 10
"funny" votes in a row (no "dry" vote between, no un-vote) within 60 s on
`/suchary` (any sub-page) for a logged-in user grows a small floating
combo-meter and, on the 10th, shows a toast titled "Publika Rozgrzana" (the 🔥
is in the toast body, `TOAST_BODY`) and awards
the hidden `frontend-ee-publika-rozgrzana` achievement (`frontend-ee-publika-rozgrzana`
in `VALID_FRONTEND_SLUGS`, seeded by migration
`0023_publika_rozgrzana_achievement_data`). It **replays** on every fresh run
of 10 (like konami / badumtss / logo_spin / theme_spam); `easterEggs.award`
still POSTs once per session. `window.__publikaRozgrzanaReady` is its
init-complete signal — the E2E test waits on it before voting. Same shape as
the sibling eggs: an ES module imported by `project.js` right after
`archeolog.js`.

- **The `click` listener is delegated on `document` in the CAPTURE phase**
  (`{capture: true}`), not bubble. `voting.js` also delegates a `click`
  listener on `document` (bubble) and does an optimistic
  `btn.classList.toggle('active')` synchronously in its handler. A capture
  listener on `document` always runs before any bubble listener on `document`
  regardless of which script's `DOMContentLoaded` registered first, so
  `willActivate(btn)` (`!btn.classList.contains('active')`) reliably reads the
  **pre-toggle** state — the same `!wasActive` `voting.js` computes for itself.
  Registering bubble here would make the read depend on load order and, if it
  ever lost the race, silently invert every funny vote into an un-vote. Never
  `preventDefault` — the vote must still go through. A Vitest test wires the
  real `voting.js` _first_, then this module, and dispatches a real `click` to
  guard the ordering.
- **The chain lives in `sessionStorage`** (`ee_publika_combo`, JSON
  `{count, firstAt}`), **not memory** — a deliberate deviation from #296's
  literal "stan w pamięci strony". The list paginates with full page reloads
  and shows 10 suchary per page, so an in-memory counter could only ever be
  built on a single page where all 10 are unvoted-by-you; a returning user
  whose recent list is already voted, or the last page (<10 items), could
  never earn it. `logo_spin.js` hit the same "state must survive navigation"
  wall and CLAUDE.md documents that deviation too.
- **The 60 s window is measured from the chain's `firstAt`, and the reset is
  authoritative + LAZY**: `readChain()` returns `null` for a chain that is
  absent, malformed, `>= 60 s` old, _or_ has a `firstAt` in the future (system
  clock wound back — NTP/DST, same guard shape as `theme_spam.js` /
  `tumbleweed.js`), so the next funny click after expiry just starts a fresh
  chain at `count = 1`. A visual-only `setTimeout` additionally hides the
  meter for a user who simply stopped clicking; on a fresh page load a live
  chain re-arms that timer to its _remaining_ window, not a fresh 60 s (cf.
  `tumbleweed.js`'s `cooldownRemaining()`).
- **Reset conditions**: any `.btn-vote[data-vote-type="dry"]` click (either
  direction), and UN-voting a funny (a funny click on an already-`.active`
  button). `handleVoteClick` gates on `data-vote-type` being `funny`/`dry`,
  not just `.btn-vote` — `suchar_form.html` has disabled `.btn-vote` preview
  buttons with no `data-vote-type`.
- **The combo-meter is a floating `<div id="ee-publika-meter">`** built in JS
  (`createElement` / `textContent`, never `innerHTML`), styled inline
  property-by-property (jsdom's CSSOM drops custom props set via `cssText`)
  from the project's theme-aware custom properties (`_variables.scss`) with
  literal fallbacks — **no Bootstrap classes**, unlike the surrounding
  `suchar_list.html` markup. The 10th funny vote runs `resetCombo()` (which
  removes the meter) _before_ `firePublikaRozgrzana()`, so the meter is gone
  by the time the toast shows — the E2E asserts the count mid-run, not after.
- **`prefers-reduced-motion` (or jsdom, no `matchMedia`) → the meter and its
  count still render; only the per-increment pulse is skipped** and the
  `<style id="ee-publika-style">` (`@keyframes` for the pulse) is not
  injected. Different from `konami.js` (motion-free static scatter) and
  `tumbleweed.js` (caption-only toast): here the meter _is_ the payload and it
  is not itself an animation.
- Its `click` handler is on `document` (capture) and the chain / expiry timer
  are module-level + `sessionStorage` state, so — per "JS tests (Vitest)"
  above — `tests/js/publika_rozgrzana.test.js` calls
  `publika._resetForTests()` (aliased to `teardownPublikaRozgrzana` —
  detaches the capture listener, clears the expiry + pulse timers, removes the
  meter and the `<style>`, clears `ee_publika_combo`) each
  `beforeEach`/`afterEach`, and `easter_eggs.js`'s `teardownAll()` also
  reaches it (registers via `registerTeardown('publikaRozgrzana')`).
- Terser (webpack's minifier) preserves the non-ASCII toast string (the 🔥
  emoji, `„…”` quotes, Polish diacritics) — verify against the production
  `npm run build` bundle, not just `just test`.

### Time zones — service zone `Europe/Warsaw` (#405) + visitor zone for I/O (#410)

`TIME_ZONE = "Europe/Warsaw"` (`base.py`) with `USE_TZ = True`: the DB stores UTC.
On top of that, `suchar_overflow/utils/middleware.py:user_timezone_middleware` (after
`LocaleMiddleware`, sync + async) wraps each request in `timezone.override(zone)`
for the zone in the `user_tz` cookie, which `webpack/src/js/timezone.js` (the first
import of the global `project` entry; runs for **anonymous** visitors
too — no auth gate) writes from `Intl.DateTimeFormat().resolvedOptions().timeZone`.
Only exact keys from `zoneinfo.available_timezones()` are accepted (cached once per
process); a missing/unknown/garbage cookie leaves `TIME_ZONE` in effect. The first
page load renders in the service zone and sets the cookie; later requests use it.
No profile field — cookie only.

**The rule: the active (current) zone may only change input parsing and display.**

- _Follows the visitor's zone:_ `SucharForm.published_at` (a naive value is read in
  the current zone) and template `|date` output. Nothing else.
- _Always the service zone, explicitly:_ every day/hour/period computation —
  `NightOwlRule`, `StreakLoginRule`, `compute_period_range`, `due_*_run_at`, the
  `localdate()` defaults in `award_best_suchar` / `award_periodic`, the leaderboard
  context (cached for **all** visitors — whoever warms it must not set its zone) and
  the profile's 30-day chart + heatmap. Use `timezone.get_default_timezone()`:
  pass it as `tzinfo=` to `TruncDay`/`TruncMonth`/`ExtractHour`, as the zone
  argument to `localdate()`/`localtime()`/`make_aware()`, and wrap `.dates()` (no
  `tzinfo` argument) in `timezone.override(get_default_timezone())` **around its
  evaluation**. A Trunc without `tzinfo` resolves the zone when the SQL is
  compiled, not when the expression is built, so an override around a lazily
  evaluated queryset is not enough. Never read the ambient `get_current_timezone()`
  / bare `localdate()` in computation code — inside a request that is the visitor's.
- Python-side `.date()` / `.replace(hour=0)` on `timezone.now()` is the **UTC** date
  (wrong between 22:00/23:00 and 24:00 UTC) — use `localdate(..., service_tz)`.
- The contest jobs fire at 00:05 _service-local_: `rq.cron` itself runs in UTC, so
  `achievements/cron.py` checks hourly at :05 and `award_best_suchar_*_if_due` /
  `due_*_run_at` convert `now` to the service zone before reconstructing the fire time
  (see Background jobs). 00:05 never falls in a DST gap/overlap (the switch is at
  02:00/03:00). A `SchedulerRun` marker written by the pre-#405 UTC cron (1st, 00:05Z)
  is _after_ the new local fire time, so no spurious catch-up.
- Tests: build naive wall-clock strings / "local hours" from `timezone.localtime()`,
  not `timezone.now()`. Boundary tests (`achievements/tests/test_timezone.py`) use
  timestamps in the 22:00–24:00 UTC window — the only one where a UTC-day bug shows —
  and the invariance tests run each computation under
  `timezone.override(ZoneInfo("America/New_York"))`, where New York and Warsaw
  disagree about the hour/day. Cookie/middleware behaviour: `tests/test_user_timezone.py`;
  E2E pins `timezone_id="Europe/Warsaw"` in `browser_context_args` so no test depends
  on the host zone (`tests/e2e/test_user_timezone.py` opens its own New York
  context). A form value in a DST gap/overlap (02:30 on a switch day) is a field
  `ValidationError`, not a 500.
- **Edit form rendered in one zone, submitted in another.** A first visit renders
  in the service zone and only then does `timezone.js` set the cookie (or the
  browser zone changes — travel), so the POST is parsed in a different zone than
  the GET rendered. `suchar_form.html` therefore carries a hidden
  `published_at_tz` (the zone it rendered in); `SucharForm._unchanged_published_at`
  keeps the instance's own `published_at` when the posted string equals the
  rendered one in that (validated) zone. A value the user re-typed is parsed in the
  active zone — they typed it on the browser's clock. Without this a text-only edit
  would silently move the publication by the offset difference.
- The scheduling input's value and that hidden zone come from
  `SucharForm.published_at_input_value()` / `published_at_input_tz()`, not from
  `{{ form.published_at.value|date }}` in the template: on an invalid-POST re-render
  `value()` is the raw posted string and `|date` turns it into `""`, which made
  `suchar_form.js` untick and disable the schedule — the next save published the
  suchar immediately. A re-render echoes the _posted_ `published_at_tz`, not the
  active zone. The add form renders the input **empty** (no model-default "now"),
  so the JS treats any future value as scheduled (`> now`, no 5-minute buffer — the
  buffer hid the schedule of a suchar due within it on its edit form).
- `timezone.js` is the first script of the shared global bundle: its `document.cookie`
  access is wrapped in `try/catch` (a `SecurityError` with cookies blocked would
  otherwise stop every script after it).

### Background jobs — RQ worker + `cron` service (#460, #461, #462)

Work outside the request runs in two extra compose services built from the Django image
(`worker`, `cron`; local and production): **`worker`** (`compose/base/django/worker`:
`rqworker --with-scheduler default` — `--with-scheduler` is what makes `Retry(interval=…)`
and `enqueue_in` fire) and **`cron`** (`compose/base/django/cron`: `achievements_catch_up`,
then `exec manage.py rqcron suchar_overflow.achievements.cron`). **Run exactly one `cron`
instance** — a second one enqueues every periodic job twice. Web workers start no scheduler
(`AchievementsConfig.ready()` only wires signals), so `WEB_CONCURRENCY > 1` is safe. This
reversed the old "Django-RQ removed, APScheduler in-process" decision of #159: APScheduler
ran in every gunicorn worker and duplicated its jobs.

- **Queue**: `django-rq` (+ `rq`), pinned. `RQ_QUEUES["default"]` points at `REDIS_QUEUE_URL`
  — its **own Redis database** (`/1`; defaults to `REDIS_URL` with path `/1`), so a cache flush
  cannot delete pending jobs; `DEFAULT_TIMEOUT = 300`. Always reach it as
  `django_rq.get_queue(settings.RQ_QUEUE_NAME)` through the module attribute: the autouse
  `rq_queue` fixture in the root `conftest.py` patches `django_rq.get_queue`, so unit tests need
  no Redis and assert on `rq_queue.enqueue` (`run_enqueued_jobs(rq_queue)` in
  `suchar_overflow/conftest.py` executes what was queued). The dashboard is at
  `/<ADMIN_URL>django-rq/` (linked from the admin index). django-rq closes DB connections
  before RQ forks per job (`reset_db_connections`); verified: no idle `pg_stat_activity` rows
  after a burst of jobs that touch the DB (`award_publication_achievements`).
- **Healthchecks**: `manage.py rq_healthcheck` (worker: every queue has a registered worker;
  `--cron`: a `CronScheduler` heartbeat younger than `--max-age`, default 150 s) and `/healthz/`'s
  `queue` check (PING on the queue's connection). Local `just up` after pulling this change needs
  `docker compose up -d --renew-anon-volumes`: the anonymous `/app/.venv` volume of the old
  `django` container still lacks `django_rq`. The worker does not autoreload — restart it after
  editing a task. RQ's scheduler (retry intervals, `enqueue_in`) starts with the worker only if it
  can take the `rq:scheduler-lock:default` lock; a clean restart releases it, but after a hard kill
  the stale lock lasts ~70 s and the worker then retries only at its 10-minute maintenance tick, so
  a retry can lag that long (the per-minute cron jobs are plain queue entries, unaffected).
- **Failures**: `RQ_EXCEPTION_HANDLERS` → `utils/rq_handlers.py:mail_admins_on_final_failure`
  logs to `django.rq` (a child of `django`, so production's `mail_admins` mails it) only once a
  job has no retries left (`job.should_retry` false). `rq.worker` has its own console handler and
  does not propagate; at INFO it logs ~4 lines per run of the per-minute sweep, `rq.cron` is
  `WARNING`.
- **Emails (#461)**: `users/tasks.py:enqueue_email(task, *args)` queues `send_activation_email` /
  the email-change jobs with `Retry(max=3, interval=[10, 60, 300])`, only after the token /
  `EmailChangeRequest` rows are saved; the job gets only a PK and plain values plus `language`
  (the requester's), and renders inside `translation.override(language)` because the worker has
  no request. An SMTP error no longer 500s the request.
- **Cron time zone**: `rq.cron` evaluates cron strings in **UTC** (`rq.utils.now()`) and has no
  zone parameter, while the contests roll over at 00:05 `Europe/Warsaw` (#405), whose UTC offset
  changes with DST. So `achievements/cron.py` registers `award-best-suchar-month` / `-year` as
  `"5 * * * *"` (hourly at :05 — every Warsaw offset is a whole hour) calling
  `award_best_suchar_month_if_due` / `_year_if_due`: when the service-local fire time has passed
  and its `SchedulerRun` marker was never written, award it with `reference_date` = the due
  fire's own date − 1 day; otherwise do nothing. The first check after 00:05 local on the 1st is
  therefore the fire, and the same function is the catch-up for a fire missed while `cron` was
  down (#169). `award-publication-achievements` (#389/#402) is `"* * * * *"`. Every job carries
  a `ttl` (50 min hourly, 2 min per-minute) so a stopped worker never builds a backlog — they
  are idempotent and the sweep overlaps 15 min, so a dropped run is harmless.
  `achievements/tests/test_cron.py` pins the three registrations and that the hourly check hits minute 5
  of the Polish clock in both CET and CEST.
- **Catch-up**: `manage.py achievements_catch_up` runs the two `*_if_due` functions and
  `award_publication_achievements` once, each in its own `try/except`, before `rqcron` starts
  (a transient DB error must not stop the others or the scheduler).
- `SchedulerRun` (`achievements/models.py`) is the marker table — one row per job id, visible
  read-only in the admin. `award_best_suchar` rewrites its own; only the most recent missed
  period is caught up per job, a brand-new deployment with no row triggers one harmless catch-up
  for the previous complete month.

The yearly job doesn't get that free pass: it shipped together with its catch-up (#168), and
`award_periodic` — the manual command — never wrote a `SchedulerRun` marker (it calls
`award_winners` directly). Without a marker the first deploy would retroactively award the
whole previous calendar year at once. Migration `0015_seed_yearly_scheduler_run` seeds a
`SchedulerRun(job_id="award-best-suchar-year")` row to suppress that one-time award; it is
baseline data in every test (like the migration-seeded `Achievement` rows — see Test patterns),
so tests delete or `update_or_create` it before asserting on `SchedulerRun` state.

`award_publication_achievements` (#389) walks every suchar whose `published_at` crossed
`(SchedulerRun.ran_at - PUBLICATION_CATCHUP_OVERLAP, now]`, re-runs the engine for its author
(iterating suchary in `published_at, id` order and passing `instance=suchar` — `NightOwlRule`
returns `None` without a `Suchar` instance), and rewrites its own marker. A downtime gap is
covered automatically (the window opens at the last `ran_at`); on the **first** run, with no
marker, only `PUBLICATION_CATCHUP_FLOOR` (1h) is swept, so **no seed migration** is needed
(unlike `0015`). `PUBLICATION_CATCHUP_OVERLAP` (15 min — 3x the form's skew allowance) overlaps
each run with the previous one: `SucharForm.clean_published_at` accepts a `published_at` up to
5 min in the past and a transaction can commit just after `now` is sampled — either can leave a
just-published suchar's `published_at` _before_ the last `ran_at`, and a bare
`published_at__gt=last_ran_at` would drop it forever. The per-suchar `check_achievements` call
is wrapped in `try/except` + `logger.exception`: one poison record must not abort the loop
before the marker is rewritten. **Cadence is every minute (#402)**: hourly made an author whose
_first_ suchar was scheduled wait up to ~1h for "First Suchar" (read as "never awarded"); a
one-off job per suchar was rejected (views would need to reach the scheduler, edits of
`published_at` would need reschedule/remove, and the sweep is the restart safety net anyway).
Don't narrow the queryset with a `published_at__gt=F("created_at")`-style "only scheduled
ones" filter: editing a scheduled suchar can move its `published_at` up to 5 min into the past
without any `SUCHAR_POSTED` event, and this job is the only thing that then catches it.
Idempotent — the engine skips owned achievements — and closes stale ORM connections on exit
like `award_best_suchar` (skipped inside an atomic block).

### Content Security Policy

Django 6.0's `django.middleware.csp.ContentSecurityPolicyMiddleware` is enabled in
`MIDDLEWARE` (`config/settings/base.py`), configured via `SECURE_CSP` in the same file.
`script-src` requires `CSP.NONCE` — inline `<script>` blocks need the nonce Django
injects. `style-src` allows `unsafe-inline` for CSS custom properties. There is no
third-party CDN allowlisted anywhere in `SECURE_CSP` — Chart.js and
flatpickr come from npm and are bundled by webpack, and fonts (Inter, Fira Code) are
self-hosted via `webpack/src/scss/_fonts.scss`; none of them load from `cdn.jsdelivr.net` or
Google Fonts.
If you add inline `<script>` tags to a template, they must use the nonce or they will
be blocked in browsers that enforce CSP.

### JS libraries from npm

`chart.js` (`chart.js/auto`, imported by the `leaderboard` and `user_detail` entries) and `flatpickr`
(JS and its CSS, imported by the `suchar_form` entry) are `devDependencies` in `package.json`, bundled by
webpack — nothing is vendored under `static/` any more (#468; the hand-vendored `chart.umd.min.js`,
`flatpickr.min.js`/`.min.css`, `flatpickr.LICENSE.txt` and their drift/sourcemap tests are gone). The
Dependabot `npm` ecosystem (`.github/dependabot.yml`) now opens version PRs for them; to check by hand run
`npm outdated`. The versions are pinned in `package.json`/`package-lock.json` (Chart.js 4.5.1,
flatpickr 4.6.13 at the move).

- **Licences (#251).** Terser drops ordinary comments, and flatpickr's ES build has no licence banner it
  would keep, so `webpack/licenses-plugin.js` (production config only) writes `licenses.txt` next to the
  bundles — name, version and full licence text of every bundled npm package — served as
  `/static/webpack_bundles/licenses.txt`. `tests/js/webpack_entries.test.js` asserts it contains flatpickr's
  and Chart.js's MIT text; there is no manual lockstep file to refresh.
- **Source maps (#249).** Production's manifest storage fails `collectstatic` on a `sourceMappingURL` that
  points at a missing file. `tests/test_static_sourcemaps.py` checks that nothing hand-written under
  `static/` carries one and, when a build exists, that every reference inside the bundles resolves
  (skipped without a build).
- **After bumping a version**: check the upstream changelog for breaking changes in the APIs the project
  uses, run `just build-js`, run the E2E suite (charts on `/stats/leaderboard/` and profile pages,
  flatpickr on the suchar form) — `tests/e2e/test_clean_console.py` also fails on console errors and CSP
  violations on every page. A green `just test` alone is not evidence the bump works.

### Async views

Most view classes are async (`async def get/post`, `AsyncLoginRequiredMixin` from
`suchar_overflow.users.mixins`) — not just the email-sending code path. When adding a
new class-based view, check a neighboring view in the same app first; the async
pattern (via `sync_to_async`/`request.auser()`/`aupdate()`/`async for`) is the norm,
not the exception.

### Frontend pipeline — webpack (#465–#469)

A webpack 5 build (Babel, Sass, PostCSS) produces the bundles `django-webpack-loader`
puts in the templates: `{% load webpack_loader %}` + `{% render_bundle '<entry>' 'js' attrs='defer' %}` /
`{% render_bundle '<entry>' 'css' %}`. This reversed the old "no JS build step" rule (#177) and replaced
django-compressor, rjsmin/rcssmin and the vendored libraries entirely (#466 toolchain, #467 SCSS, #468 JS
as ES modules + npm libraries, #469 compressor removed: no `{% compress %}`, `COMPRESS_*`, `compressor` in
`INSTALLED_APPS`/`STATICFILES_FINDERS`, `compress --force` in the production `start`, or
`django-compressor`/`rcssmin`/`rjsmin` in the dependencies).

- **Layout.** Configs in `webpack/` (`common`, `dev`, `prod`, `postcss`; CommonJS, like the rest of
  `package.json`, which is `"type": "commonjs"`), `babel.config.js` at the root, sources under
  `webpack/src/` — deliberately **not** under `suchar_overflow/static/`, which `collectstatic` copies
  wholesale. Output: `suchar_overflow/static/webpack_bundles/` (`js/[name].[contenthash].js`,
  `css/[name].[contenthash].css`, 12 hex digits after a dot — the shape nginx marks `immutable`) plus
  `webpack-stats.json` in the repo root. Both are gitignored **and** in `.dockerignore`, so a stale
  host build can never reach an image. `package.json`/`package-lock.json` are in the build context
  (the `node` image and the `client-builder` stage run `npm ci` from them); `node_modules/` is not.
- **Entries and shared chunks.** `optimization.runtimeChunk: 'single'` + `splitChunks: {chunks: 'all'}` +
  `dependOn: 'project'` on every page entry: one runtime for every entry, so a page that renders the global
  `project` entry **and** a page entry never instantiates a module twice (two `EventSource`s, a split
  dedupe `Set`…). Without `dependOn` webpack copies small shared modules into each entry (negative
  control: `easter_eggs.js` then lands in 2 chunks — a separate dedupe `Set`, a separate teardown
  registry); `tests/js/webpack_entries.test.js` builds the prod config into a tmp dir and counts the chunks
  holding each module. The loader's
  `SKIP_COMMON_CHUNKS = True` drops the chunks a second `render_bundle` would repeat; that needs
  `request` in the template context, hence `base.html`'s first call passes `skip_common_chunks=False`
  (nothing to skip, and the 500 page renders without a request). `tests/test_webpack_toolchain.py`
  pins it.
- **Entries (#468).** The global `project` entry (`webpack/src/js/project.js`) imports, in this order,
  `./timezone.js` (first: sets the `user_tz` cookie, `document.cookie` in `try/catch` so blocked cookies
  don't stop the rest), `./app.js` (the old `project.js`: theme, navbar, dropdowns, modals, tooltips, the SSE
  client, the bell; publishes `window.getCsrfToken` and `window.showToast`), `./features/easter_eggs.js`,
  then `konami`, `badumtss`, `logo_spin`, `console_egg`, `tumbleweed`, `theme_spam`, `archeolog`,
  `publika_rozgrzana`. Import order **is** initialisation order and the order `DOMContentLoaded`
  listeners register in; `webpack_entries.test.js` pins it. `csrf.js` (`getCsrfToken`) and `toast.js`
  (`showToast`) are separate modules other modules import directly. Page entries, all `dependOn: 'project'`:
  `hidden_achievements`, `voting` (both in `features/`), `leaderboard` and `user_detail` (Chart.js),
  `suchar_form` (flatpickr + its CSS), and the CSS-only `achievements` and `dashboard`.
- **Contracts that stay.** `window.easterEggs` (a facade — nothing in the bundles reads it), `window.showToast`,
  `window.getCsrfToken` (E2E reads them), the `window.__*Ready` flags (E2E), `window.EE_AUDIO`, and
  `_resetForTests` as a named module export. The IIFE wrappers and the guarded
  `if (typeof module !== 'undefined' && module.exports)` tails are gone: every module has its own scope.
- **Templates.** Always pass the extension to `render_bundle` — `'js'` (with `attrs='defer'`) **or**
  `'css'` (see _Styles_ for why). Keep `{{ block.super }}` as the **first** line of an overridden
  `{% block javascript %}`/`{% block css %}`: it already renders base's tags, and the page's own
  tags must come after them. `{% block javascript %}` lives in `<head>`, so every page script needs `defer`.
  Data islands (`json_script`, `#ee-logo-suchary`, the nonce'd inline `window.EE_AUDIO` map) stay in the
  templates, outside the bundles: a bundle can't run `{% trans %}`/`{% static %}`, and the page entry
  reads the island by `id`. `tests/test_webpack_toolchain.py` renders every page and asserts each entry's
  CSS/JS appears once, with `defer`, after `project`, and that the islands are in place.
- **URLs.** webpack-bundle-tracker writes `publicPath` (`/static/webpack_bundles/…`) into the stats, and
  the loader uses it as-is — it does not go through `staticfiles_storage`. So the unhashed-by-Django
  names are what pages reference; production's `collectstatic` still hashes copies, harmlessly.
  `IGNORE` hides `.map`/hot-update files from `render_bundle`.
- **Settings.** `base.py` has `WEBPACK_LOADER` (`CACHE: True`, absolute `STATS_FILE`); `local.py` turns
  the cache off; `test.py` swaps in `FakeWebpackLoader` (one placeholder tag, no stats file needed);
  `e2e.py` restores the real loader, so **E2E needs built bundles**: `just build-js` (host, needs
  `npm ci` once; CI does both before the pytest steps). `just test-e2e` refuses to start without
  `webpack-stats.json`. Each layer copies the dict instead of mutating `base`'s (the settings-layer
  rule above).
- **Dev.** `just up` starts the `node` service: `http://localhost:3000` proxies everything to
  `django:8000` (Host/Origin stay `localhost:3000`, so `ALLOWED_HOSTS`/CSRF see the browser's address)
  with live reload on template and source changes; `:8000` keeps working because the dev build is
  also **written to disk** (`devMiddleware.writeToDisk`) where Django's static handler finds it. Dev
  `devtool` is `cheap-module-source-map`, never `eval*` — the CSP has no `'unsafe-eval'`. `compress: false` keeps the dev server from buffering the SSE stream. The client's socket URL is
  `auto://0.0.0.0:0/ws` (the page's own origin), so on `:8000` it fails once and gives up — a console
  line, not a CSP violation. After a `package.json` change: `just build` and
  `docker compose up -d --renew-anon-volumes` (the `node_modules` volume is anonymous). Without
  the `node` service no `webpack-stats.json` exists and every page 500s. **Don't run `just build-js` (a
  production build on the host) and the `node` service at once** (the recipe refuses while the container runs): both write the same output directory,
  and the dev server doesn't re-emit files it believes it already wrote — after `just build-js` run
  `docker compose restart node`.
- **Production.** `compose/production/django/Dockerfile` has a `client-builder` stage
  (`docker.io/node:<major of .nvmrc>-trixie-slim`; `npm ci` **before** anything sets `NODE_ENV`, or
  webpack — a devDependency — would be skipped) whose bundles and stats file are copied into the
  build stage; `collectstatic` then picks the bundles up. The bundles are built in the image, not at
  container start: `compose/production/django/start` runs `migrate` and `collectstatic --noinput --clear`
  (the `--clear` rebuilds the volume from the image each start). Terser minifies, keeping emoji and
  Polish diacritics (check with the production bundle, not only `just test`). Prod devtool is `source-map` with real
  `.map` files next to the bundles, so no `sourceMappingURL` dangles (#249 — manifest storage fails
  hard on that). `tests/test_static_sourcemaps.py` covers it (see _JS libraries from npm_);
  `tests/test_manifest_static_storage.py` also checks that every asset in `webpack-stats.json` exists after
  a real `collectstatic` (skipped without a build).
- **Styles (#467).** The global stylesheet is `webpack/src/scss/project.scss`: an ordered list of `@use`
  lines (fonts → core → components → `_site.scss`, the old `project.css`) that **is** the cascade order,
  exactly as the `<link>` order in the old compressor block was — `utilities` and
  `components/forms` carry comments that depend on it; a new global module goes in at the right position,
  not at the end. The partials are plain CSS (a valid SCSS subset); `@use`, never the deprecated
  `@import`. Variables stay CSS custom properties (`_variables.scss`) so the light/dark theme switches at
  runtime. Page sheets (`scss/pages/*.scss`) are **not** in it: each page has an entry
  (`webpack/src/js/pages/<name>.js` imports its scss — `achievements`, `dashboard` = the old
  `profile.css`, `leaderboard`, `suchar_form`, which also imports flatpickr's CSS from npm first) and the
  template renders `{% render_bundle '<entry>' 'css' %}` after `{{ block.super }}`, so the page's
  equal-specificity `!important` rules still win on order (#250). Always pass an extension to
  `render_bundle` for CSS (`'css'`) **and** JS (`'js'`): a call without one renders both, and a second
  copy of `project.css` landing after the page sheet silently flips the cascade (it did, once —
  E2E `test_dashboard_chrome` caught it). `fonts` are written `url('/static/fonts/…')` and css-loader is
  told to leave `/static/` URLs alone (nginx/collectstatic serve them, the manifest storage hashes them).
  postcss-preset-env (`last 2 versions`) adds `-webkit-` prefixes, logical-property fallbacks and
  `@supports` wrappers around `color-mix()`; `rgb(from …)` passes through. `tests/test_scss_sources.py`
  guards the `@use` order, that every partial is used once and the font paths;
  `tests/test_webpack_toolchain.py` that every page renders its entry's CSS once, after the global one.
- **Deliberate limits.** `publicPath` (`/static/webpack_bundles/`) and the font URLs (`/static/fonts/`) are
  written as literals, and the tests `removeprefix(STATIC_URL)`: changing `STATIC_URL` (a CDN) means changing
  `webpack/common.config.js` and `_fonts.scss` with it. Production ships real `.map` files (public
  `sourcesContent`, `immutable` in nginx) — fine for an open-source repo, but a decision, not an accident.
- **Guards.** The Node tag in both Dockerfiles and `engines.node` follow `.nvmrc`'s major
  (`tests/test_webpack_toolchain.py`); `compose/local/node/` is on Dependabot's docker list.
  `tests/e2e/test_clean_console.py` loads every page and fails on console errors and CSP violations (its
  `ConsoleMessage` handler annotation must be a real import, not under `TYPE_CHECKING` — Playwright
  inspects the annotation).

### Achievement engine

`AchievementEngine.check_achievements(user, event_type, instance=None)` looks up
`Achievement` rows by `event_type`, skips `PERIODIC` category, skips already-owned.
The engine only ever _awards_ — it never revokes an achievement whose metric later
drops back below the threshold.

**The three suchar-authoring rules gate on `published_at`.** `SucharCountRule`
(`COUNT_SUCHAR`), `StreakLoginRule` (`STREAK_LOGIN`) and `NightOwlRule` (`NIGHT_OWL`)
all filter `Suchar.objects.filter(... published_at__lte=timezone.now())` (`__lte`, per
#388 / the rest of the codebase), and `NightOwlRule`'s instance guard also requires
`instance.published_at <= now`. Without this, creating a _scheduled_ (future
`published_at`) suchar fires the engine via `post_save(created=True)` and awards a
`COUNT_SUCHAR`/streak/night-owl tier that shows on the author's public profile before
the suchar itself is visible (#389). Nothing fires the engine when a scheduled suchar's
`published_at` merely passes, so `award_publication_achievements`
(`achievements/tasks.py`, scheduled every minute — see Background jobs) re-runs the
engine for every suchar that crossed into visibility since its last `SchedulerRun`,
bounding the award lag to ~1 min (#402). `EditCountRule`, `PolarizerRule`, `SumScoreRule` and
`DryMasterRule` are deliberately **not** gated: editing is only possible before
publication ("Recydywa" is earned entirely on scheduled suchary by design), and the
vote-driven rules already can't latch pre-publication (`_maybe_mark_overdried`'s lower
bound; votes on an unpublished suchar 404 per #331).

The same #389 leak in the tag-autocomplete endpoint (`suchary/api.py:list_tags`,
`GET /api/suchary/tags` — anonymous-reachable) is fixed the same way: it now returns
only tags with `Exists(Suchar.objects.filter(tags=OuterRef("pk"),
published_at__lte=now))` (`Exists`, not `.filter(...).distinct()` — no join fan-out,
cf. #241/#196), ordered by `name` for a stable 10-row slice. Trade-off: a user editing
their own scheduled suchar loses autocomplete for a tag that exists _only_ on that
suchar. Tag reuse-by-name is unaffected — `SucharForm._save_tags` resolves tags by
slug via its own `Tag.objects.filter(slug__in=...)` + `bulk_create`, independent of
the suggestion endpoint. `tests/e2e/test_tag_autocomplete.py` fixtures therefore
attach a published suchar to each tag they create (a bare `Tag.objects.create` is now
invisible to the endpoint).

Two triggers feed it for votes (see `suchar_overflow/achievements/signals.py`,
`_award_vote_achievements`):

- **`post_save` of `Suchar` (SUCHAR_POSTED) and `Vote` (VOTE_CAST for voter,
  VOTE_RECEIVED for suchar author), `created=True` only.** The vote endpoint sets
  `is_funny`/`is_dry` via `Vote.objects.get_or_create(defaults=...)` so this first
  `post_save` already sees the final flag state — reverting that to a post-insert flag
  flip silently reintroduces #247 (the first funny/dry vote counted one vote late,
  because the flip's `save()` fires no signal).
- **`vote_changed`** (a plain `django.dispatch.Signal` defined in
  `suchar_overflow/suchary/signals.py`, sent _only_ from `vote_suchar` in
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

Rules split into `AchievementRule.compute_value(user, instance)` (the _threshold-
independent_ metric value, or `None` when the rule can't be met at all — note that
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
concrete rules ever declare the _same_ metric, `register_rules()` raises
`ImproperlyConfigured` naming both classes (issue #266) instead of letting the second
silently overwrite the first in `_rules`; the check runs inside the one-shot
`if cls._rules:` idempotency guard, so it fires on the first `register_rules()` call.

Metric → what it evaluates:

- `COUNT_SUCHAR` → _published_ suchary authored by user (scheduled ones don't count
  until they go live — #389)
- `COUNT_VOTE_FUNNY` → funny votes **cast by** user (voter perspective)
- `COUNT_VOTE_DRY` → dry votes **cast by** user (voter perspective — same
  `user.suchar_votes` accessor as `COUNT_VOTE_FUNNY`, _not_ votes received)
- `COUNT_VOTE_CAST` → all votes cast by user
- `SUM_SCORE` → net score of votes received on user's suchary (author perspective)
- `POLARIZER` → custom rule: the highest `funny_count` (which, by the `funny ==
dry` filter, equals `dry_count` — i.e. half the votes on that suchar, not
  `funny + dry`) among the user's perfectly-split suchary, compared against the
  threshold — equivalent to the old `funny_count__gte=threshold` + `.exists()`,
  but threshold-free so it runs once
- `STREAK_LOGIN` → consecutive days with at least one _published_ suchar posted
- `NIGHT_OWL` → _published_ suchar created between 00:00–04:00 local time
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

Notable non-obvious dependencies already in use: `django-rq` / `rq`
(job queue and cron, see Background jobs), `django-webpack-loader` (renders the webpack
bundles, see Frontend pipeline; the JS/CSS toolchain and libraries are npm's, not `uv`'s), `django-ninja` (the `/api/`
router), `django-modeltranslation` (model-field translation for `Achievement`, distinct
from the template-level `i18n` used elsewhere).

## Templates and static files

- Templates: `suchar_overflow/templates/` — Django template engine (`DjangoTemplates`)
  with `{% load webpack_loader %}`, `{% load static %}` and
  `{% load i18n %}` where needed.
- CSS: SCSS under `webpack/src/scss/` (global partials + `pages/`) — uses CSS custom properties (`_variables.scss`).
- JS: ES modules under `webpack/src/js/` — `project.js` (global entry), `app.js` (main), `features/` and `pages/` (see _Frontend pipeline_).
- djlint enforces template formatting. After editing templates, run `pre-commit` to
  auto-format. djlint max line length for templates is 120 chars, indent 4 spaces.
- **`{# … #}` comments are single-line only.** Django's lexer does not span newlines
  for that form, so a multi-line `{# … #}` is emitted into the page verbatim (it bit
  `base.html`'s `EE_AUDIO` block — #310, from #282, fixed with #284). Use
  `{% comment %} … {% endcomment %}` for anything multi-line. Don't put a literal
  `{% comment %}` / `{% endcomment %}` / `{# #}` token _inside_ a `{% comment %}`
  block either — djlint miscounts the nesting and de-indents the rest of the file.
- Every `{% static %}` path must exist. Production's manifest storage raises on a
  missing one at render time, and because the 500 page also extends `base.html`,
  a stale reference there turns every page into a 500 (#436: `og:image` pointed
  at a deleted `favicon.ico`). Dev/test storage never checks.
  `tests/test_manifest_static_storage.py` renders the pages after a real
  `collectstatic` into `ManifestStaticFilesStorage`. `og:image` gets its origin
  in `base.html`, so an `og_image` block override supplies only the path. The
  default is `images/og-image.png`, a 1200×630 card, because link previews don't
  render SVG. Regenerate it with `just gen-og-image` (#440): it runs Chromium in
  the container so the self-hosted fonts render, and its output is not
  byte-deterministic, so re-run only on a design change.
- `handler500` is `suchar_overflow.utils.views.server_error` (#442): it renders the
  themed `500.html` and, if that raises, logs it and serves a static page. Keep
  that `try/except`. Under ASGI, an exception escaping `handler500` means no
  response and so no `request_finished`. `close_old_connections` then never runs,
  and the request's connection stays open in its dead per-request thread until
  cyclic GC finds it; an idle worker never does. Measured: 50 → 50 after 5 s idle.
  `tests/test_handler500_db_connection.py` drives `ASGIHandler` directly to guard it.
- `handler400`/`403`/`404` are `suchar_overflow.utils.views` wrappers of Django's defaults,
  and every handler goes through `suchar_overflow.utils.db.releases_db_connections`
  (#447). Under ASGI, Django calls the error handlers, and `log_response` for every
  response >= 400, via `sync_to_async(thread_sensitive=False)`. They run in a
  loop-executor thread (`asyncio_N`) that `request_finished` never cleans up. The
  403/404 pages read `request.user` through context processors, and the admin email
  report reads it too. The connection that read opens was never closed. Nothing
  health-checked it either, so after a Postgres restart every error page served from
  that thread was a 500. The wrapper calls `close_if_unusable_or_obsolete()` on
  entry and exit, and skips atomic blocks. Production's `mail_admins` is
  `suchar_overflow.utils.log.AdminEmailHandler`, whose `emit` is wrapped the same way. It
  sits on the `django` logger. `base.py` clears the handlers Django's
  `DEFAULT_LOGGING` leaves there (`disable_existing_loggers=False` keeps them). That
  stock `AdminEmailHandler` had doubled every admin email and bypassed the wrapper.
  Keep the `"django": {"handlers": []}` entry in base. A new `handler*`, or an error
  path that runs in the executor, needs the wrapper.
  `tests/test_error_handler_db_connections.py` (`ASGIHandler` + the thread name
  that opened each connection) and `tests/test_logging_settings.py` guard this.
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
   `just test` — only a separate blocking CI job (`.github/workflows/ci.yml`, the
   `mypy` job) — so a type error passes every local gate above and only fails the
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
- Commit messages: imperative mood, explain _why_ not _what_.
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
  own CI job — see the mypy note above). Check `gh pr checks`; if a job fails,
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

Splitting the _current_ issue is a different case and needs no confirmation. If
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
