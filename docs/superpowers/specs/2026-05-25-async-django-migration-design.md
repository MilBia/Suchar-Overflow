# Async Django Migration Design

**Date:** 2026-05-25
**Status:** Approved
**Scope:** Full async conversion — ASGI server, async views, async middleware, drop django-rq worker, in-process scheduler, Django 6.0 upgrade

---

## Goals

1. **Simplify infrastructure** — remove the `rqworker` Docker service, `rqscheduler` process, and Redis job queue usage.
2. **Better concurrency** — SSE connections and email dispatch no longer block threads; the server handles more concurrent requests.
3. **Modern stack** — async Django 6.0 on uvicorn, in-process APScheduler, no separate worker process.

---

## Architecture Overview

### What changes

| Layer | Before | After |
|---|---|---|
| Entry point | `config/wsgi.py` + gunicorn | `config/asgi.py` + gunicorn + UvicornWorker |
| Views | sync class-based | `async def get/post` |
| Middleware | sync | `async def __call__` |
| Email dispatch | RQ enqueue → worker process | async `on_commit` + `sync_to_async` thread |
| Scheduled job | rq-scheduler + rqworker | APScheduler `BackgroundScheduler` in-process |
| SSE stream | sync generator | async generator |
| ORM in views | `queryset.get()`, `.filter()` | `aget()`, `afilter()`, `aupdate()` |
| Achievement engine | sync (signal-driven) | unchanged — Django signals are always sync |
| Docker services | django + rqworker + redis | django + redis |

### What does NOT change

- Signals and the achievement engine — no modification needed
- Redis — stays as the cache backend (`CACHES`); removed only as job queue
- Database driver — `psycopg[c]` (psycopg3) already supports async ORM in Django 5.x+
- All models, migrations, templates, JS, CSS

---

## Section 1: Django 6.0 Upgrade

Django 6.0 (current stable: 6.0.6) is adopted alongside the async migration.

### Features used

**`AsyncPaginator` / `AsyncPage`** — Django 6.0 async-native pagination. Used in `SucharListView`, `MyAchievementsView`, and `AchievementListView` inside async `get()` overrides.

**`ContentSecurityPolicyMiddleware`** — built-in CSP support added to the middleware stack with a baseline `SECURE_CSP` policy.

**Background Tasks framework** — noted but not adopted. The only included backends (`ImmediateBackend`, `DummyBackend`) are not suited for fire-and-forget email. Revisit if the project needs durable task queuing in the future.

### Breaking changes handled on upgrade

| Change | Project impact |
|---|---|
| Python 3.12+ required | running 3.13 ✓ |
| `DEFAULT_AUTO_FIELD` defaults to `BigAutoField` | already set explicitly in `base.py` ✓ |
| psycopg minimum 3.1.12 | running 3.3.2 ✓ |
| `EmailMessage.message()` returns `email.message.EmailMessage` | project uses `send_mail()` only, no custom subclassing ✓ |
| `as_sql()` must return tuple params | no custom ORM expressions ✓ |

---

## Section 2: ASGI Server & Infrastructure

### New file: `config/asgi.py`

```python
import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "suchar_overflow"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
```

### Settings

Add to `base.py` alongside the existing `WSGI_APPLICATION`:

```python
ASGI_APPLICATION = "config.asgi.application"
```

### Start scripts

**`compose/local/django/start`:**
```bash
python manage.py migrate
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --reload
```

**`compose/production/django/start`:**
```bash
python /app/manage.py migrate --noinput
python /app/manage.py collectstatic --noinput
python /app/manage.py compress --force
exec gunicorn config.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:5000 \
  --chdir /app
```

Gunicorn stays as process manager (graceful restarts, SIGTERM handling). Only the worker class changes from default sync to `UvicornWorker`.

### Docker Compose

Remove `rqworker` service from `docker-compose.local.yml` and the production equivalent. Delete `compose/local/django/start-rqworker` and `compose/production/django/start-rqworker`.

Redis service stays — still used for cache.

---

## Section 3: Async Views

### CBV async rules

Django 4.1+ supports async handlers in class-based views. The rule for this project:

- **Override `get()` and `post()` directly** — do all ORM work there using async methods.
- **Do not rely on inherited sync helpers** (`get_queryset`, `get_context_data`, `get_object`, `form_valid`) — they are called synchronously by the parent class and do not chain with async handlers.
- **Use `AsyncPaginator`** (Django 6.0) for any paginated list views.

### Pattern 1 — Pure `View` subclasses

`ActivateAccountView`, `EmailChangeConfirmView`, `EmailChangeRevokeView`: make each handler `async def`, swap ORM for async variants. `View.as_view()` detects the async handler automatically.

```python
class ActivateAccountView(View):
    async def get(self, request, token):
        try:
            activation = await ActivationToken.objects.select_related("user").aget(token=token)
        except ActivationToken.DoesNotExist:
            return render(request, "registration/activation_failed.html")
        ...
```

### Pattern 2 — Generic CBVs (ListView, DetailView, CreateView, etc.)

Override `get()` and `post()` directly; use `AsyncPaginator` where pagination is needed.

```python
class SucharListView(View):
    template_name = "suchary/list.html"

    async def get(self, request, *args, **kwargs):
        qs = Suchar.objects.select_related("author").order_by("-created_at")
        paginator = AsyncPaginator(qs, per_page=20)
        page = await paginator.apage(request.GET.get("page", 1))
        return render(request, self.template_name, {"page_obj": page})
```

### Pattern 3 — SSE stream

```python
@login_required
async def achievement_stream(request):
    async def event_stream(user_pk):
        cache_key = f"achievements_pending:{user_pk}"
        if await cache.aget(cache_key):
            yield "data: new\n\n"
        else:
            yield "retry: 10000\n\n"
        await asyncio.sleep(0)

    response = StreamingHttpResponse(
        event_stream(request.user.pk),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
```

`cache.aget()` is the async method provided by `django-redis`.
`@login_required` supports async FBVs natively since Django 5.1.

### Auth mixin

`LoginRequiredMixin` has a sync `dispatch()` that doesn't chain correctly with async handlers. Define once in `suchar_overflow/users/mixins.py` (new file, imported by all apps that need it):

```python
class AsyncLoginRequiredMixin(LoginRequiredMixin):
    async def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return await super().dispatch(request, *args, **kwargs)
```

All views currently using `LoginRequiredMixin` swap to `AsyncLoginRequiredMixin`. Same pattern for `UserPassesTestMixin` on `SucharUpdateView`.

### Stats views exception

`LeaderboardView` and its two helper functions (`get_daily_activity_data`, `get_all_time_activity_data`) use complex aggregation chains. These are wrapped with `sync_to_async` rather than fully rewritten — they are read-only analytics queries not on the hot path.

### Full view migration table

| App | View | Handler(s) | Notable async ORM |
|---|---|---|---|
| achievements | `achievement_stream` | FBV | `cache.aget()` |
| achievements | `MyAchievementsView` | `get()` | `aupdate()`, `async for` |
| achievements | `AchievementListView` | `get()` | `async for`, `AsyncPaginator` |
| users | `UserDetailView` | `get()` | `aget()` |
| users | `UserUpdateView` | `get()`, `post()` | `aget()`, `asave()` |
| users | `SignupView` | `post()` | `acreate()` |
| users | `ActivateAccountView` | `get()` | `aget()` |
| users | `EmailChangeInitiateView` | `get()`, `post()` | `aget()` |
| users | `EmailChangeConfirmView` | `get()` | `aget()`, `aupdate()` |
| users | `EmailChangeRevokeView` | `get()` | `aget()`, `adelete()` |
| suchary | `SucharListView` | `get()` | `async for`, `AsyncPaginator` |
| suchary | `SucharCreateView` | `get()`, `post()` | `acreate()` |
| suchary | `SucharUpdateView` | `get()`, `post()` | `aget()`, `asave()` |
| stats | `LeaderboardView` | `get()` | `sync_to_async` wrappers |

---

## Section 4: Async Middleware

All Django built-in middleware and WhiteNoise are already `async_capable` since Django 4.1 / WhiteNoise 5.x. No changes needed for them.

### `AchievementNotificationMiddleware`

```python
class AchievementNotificationMiddleware:
    async_capable = True
    sync_capable = False

    def __init__(self, get_response):
        self.get_response = get_response

    _BYPASS_PATHS = ("/api/", "/achievements/stream/")

    async def __call__(self, request):
        if any(request.path.startswith(p) for p in self._BYPASS_PATHS):
            return await self.get_response(request)

        if request.user.is_authenticated:
            cache_key = _CACHE_KEY.format(user_pk=request.user.pk)
            await cache.adelete(cache_key)

        return await self.get_response(request)
```

`cache.adelete()` is provided by `django-redis` with no extra dependency.

### Django 6.0 CSP middleware

Add `ContentSecurityPolicyMiddleware` after `SecurityMiddleware` (verify exact module path against Django 6.0 docs during implementation — likely `django.middleware.security.ContentSecurityPolicyMiddleware`):

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.security.ContentSecurityPolicyMiddleware",  # verify path
    "whitenoise.middleware.WhiteNoiseMiddleware",
    ...
    "suchar_overflow.achievements.middleware.AchievementNotificationMiddleware",
    ...
]
```

Baseline policy in `base.py`:

```python
from django.utils.csp import CSP

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],  # CSS custom properties require this
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],  # covers the SSE endpoint
    "font-src": [CSP.SELF],
}
```

`CSP.UNSAFE_INLINE` on `style-src` is required for CSS custom properties. Tighten with nonces later if needed.

---

## Section 5: Email Dispatch — Replacing RQ

### Mechanism

Django 5.1+ async `on_commit`: passing a coroutine function as callback causes Django to schedule it as `asyncio.create_task()` after the transaction commits. Combined with `sync_to_async`, this gives fire-and-forget email dispatch with no separate process.

```python
from asgiref.sync import sync_to_async
from .tasks import send_activation_email

async def post(self, request, *args, **kwargs):
    ...
    async def _send():
        await sync_to_async(send_activation_email, thread_sensitive=False)(
            user_pk, host, token, protocol
        )
    transaction.on_commit(_send)
    return redirect(self.success_url)
```

`thread_sensitive=False` places the SMTP call in Django's thread pool rather than the main thread — correct for long-running I/O.

### What changes in `users/views.py`

Replace in both `SignupView.post()` and `EmailChangeInitiateView.post()`:

```python
# REMOVE
transaction.on_commit(
    lambda: django_rq.enqueue(send_activation_email, user_pk, host, token, protocol)
)

# ADD
async def _send():
    await sync_to_async(send_activation_email, thread_sensitive=False)(
        user_pk, host, token, protocol
    )
transaction.on_commit(_send)
```

### `tasks.py` unchanged

`suchar_overflow/users/tasks.py` keeps its two sync functions as-is — they continue to own the email logic. The import in `views.py` drops `django_rq` and adds `sync_to_async`:

```python
# REMOVE
import django_rq

# ADD
from asgiref.sync import sync_to_async
```

---

## Section 6: Scheduled Jobs — Replacing rq-scheduler

### Why `django-apscheduler` over bare APScheduler

Multiple gunicorn workers each start their own `BackgroundScheduler` via `AppConfig.ready()`. `django-apscheduler`'s `DjangoJobStore` persists job state in the database and uses `SELECT FOR UPDATE` to ensure only one worker executes each scheduled run.

`award_best_suchar` uses `get_or_create` and is idempotent — but DB-level deduplication is the correct guarantee.

### Why `BackgroundScheduler` not `AsyncIOScheduler`

`AppConfig.ready()` fires before uvicorn's event loop starts. `BackgroundScheduler` starts cleanly from `ready()` in its own OS thread. `award_best_suchar` is sync (ORM queries only), so a background thread is the right fit.

### Dependencies

```toml
# ADD
"apscheduler>=3.10,<4"      # pin to 3.x stable API
"django-apscheduler>=0.7"
```

APScheduler 4.x is a full API rewrite — pin to 3.x.

### `INSTALLED_APPS`

```python
# ADD to THIRD_PARTY_APPS in base.py
"django_apscheduler",
```

Run `manage.py migrate` once to create `DjangoJob` and `DjangoJobExecution` tables (visible in Django admin).

### `AchievementsConfig.ready()`

```python
import sys
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

_NO_SCHEDULER = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "compress", "check", "shell", "createsuperuser",
})


class AchievementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "suchar_overflow.achievements"
    verbose_name = _("Achievements")

    def ready(self):
        import suchar_overflow.achievements.signals  # noqa: F401, PLC0415

        if "pytest" in sys.modules:
            return
        if len(sys.argv) > 1 and sys.argv[1] in _NO_SCHEDULER:
            return

        self._start_scheduler()

    @staticmethod
    def _start_scheduler():
        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore

        from suchar_overflow.achievements.tasks import award_best_suchar

        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_jobstore(DjangoJobStore(), "default")
        scheduler.add_job(
            award_best_suchar,
            "cron",
            args=["month"],
            day=1,
            hour=0,
            minute=5,
            id="award-best-suchar-month",
            replace_existing=True,
            jobstore="default",
        )
        scheduler.start()
```

All imports inside `_start_scheduler` are deferred to avoid circular import issues at module load time.

### Files deleted

| Path | Reason |
|---|---|
| `compose/local/django/start-rqworker` | rqworker container removed |
| `compose/production/django/start-rqworker` | rqworker container removed |
| `suchar_overflow/achievements/management/commands/register_scheduled_jobs.py` | replaced by `AppConfig.ready()` |

---

## Section 7: Test Strategy

### Async client

All view tests move from `client` to `async_client` (pytest-django 4.5+, already at 4.11.1) and from sync `def` to `async def`. No new dependencies required.

```python
# Before
@pytest.mark.django_db
def test_signup_get_renders_form(client):
    response = client.get(reverse("users:signup"))
    assert response.status_code == HTTPStatus.OK

# After
@pytest.mark.django_db
async def test_signup_get_renders_form(async_client):
    response = await async_client.get(reverse("users:signup"))
    assert response.status_code == HTTPStatus.OK
```

### Email dispatch tests

The `sync_rq` autouse fixture in `test_signup_and_email.py` is deleted. Email dispatch tests mock the task function and drain the event loop:

```python
@pytest.mark.django_db(transaction=True)
async def test_signup_sends_activation_email(async_client):
    with patch("suchar_overflow.users.tasks.send_activation_email") as mock_send:
        await async_client.post(reverse("users:signup"), {...})
        await asyncio.sleep(0)  # let on_commit schedule the task
        await asyncio.sleep(0)  # let sync_to_async thread complete
        assert mock_send.called
```

`@pytest.mark.django_db(transaction=True)` stays — `on_commit` still requires a real transaction commit to fire.

Tests that previously checked `mail.outbox` now assert on the mock call with the correct arguments, which is more precise.

### Settings cleanup

Remove the entire `RQ_QUEUES` block from `config/settings/test.py`.

### Scheduler tests

The two `register_scheduled_jobs` command tests in `test_tasks.py` are deleted alongside the command. The `"pytest" in sys.modules` guard in `AppConfig.ready()` prevents the scheduler from starting during test runs. All other `test_tasks.py` tests (`award_best_suchar` function tests) are unchanged — they call the sync function directly.

### SSE tests

```python
@pytest.mark.django_db
async def test_achievement_stream_no_pending(async_client, django_user_model):
    user = await django_user_model.objects.acreate_user(username="u", password="pw")  # noqa: S106
    await async_client.aforce_login(user)
    response = await async_client.get(reverse("achievements:stream"))
    content = b"".join([chunk async for chunk in response.streaming_content])
    assert b"retry:" in content
```

### What does NOT change

- `@pytest.mark.django_db` marker on all tests
- `--reuse-db` flag — `django-apscheduler` tables are created on `migrate` and rebuilt with `--create-db` normally
- All `test_tasks.py` task function tests
- All E2E Playwright tests

---

## Section 8: Dependency Changeset

### `pyproject.toml` — production dependencies

```toml
# ADD
"django==6.0.6",
"uvicorn[standard]>=0.34",
"apscheduler>=3.10,<4",
"django-apscheduler>=0.7",

# REMOVE
# "django==5.2.10"
# "django-rq==3.0.0"
# "rq-scheduler>=0.13"
```

`uvicorn[standard]` includes `watchfiles` (hot reload), `httptools`, and `uvloop` on Linux (faster event loop and HTTP parser).

`gunicorn` stays as the production process manager.

Dev dependencies are unchanged. `werkzeug[watchdog]` stays — used by `django-extensions` for `shell_plus` and other tooling.

### `INSTALLED_APPS` diff

```python
# ADD to THIRD_PARTY_APPS in base.py
"django_apscheduler",

# REMOVE from THIRD_PARTY_APPS
"django_rq",
```

### Settings diff

```python
# REMOVE from base.py
_rq_queue: dict = {"URL": REDIS_URL}
if REDIS_SSL:
    _rq_queue["SSL_CERT_REQS"] = None
RQ_QUEUES = {"default": _rq_queue}

# REMOVE from test.py
RQ_QUEUES = {"default": {"HOST": "localhost", ...}}

# ADD to base.py
ASGI_APPLICATION = "config.asgi.application"

# ADD to base.py
from django.utils.csp import CSP
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "font-src": [CSP.SELF],
}
```

### Net changeset summary

| | Package | Reason |
|---|---|---|
| + | `django 6.0.6` | version upgrade |
| + | `uvicorn[standard]` | ASGI server |
| + | `apscheduler>=3.10,<4` | in-process scheduler |
| + | `django-apscheduler>=0.7` | Django ORM job store, deduplication |
| − | `django-rq` | replaced by async `on_commit` |
| − | `rq-scheduler` | replaced by APScheduler |

Net result: same count of production dependencies. The `rqworker` Docker service is removed entirely. Redis stays only as the cache backend.
