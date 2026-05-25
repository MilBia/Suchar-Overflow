# Async Django Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Suchar Overflow from a sync WSGI Django 5.2 app with an RQ worker to a fully async ASGI Django 6.0 app with an in-process APScheduler, removing the rqworker Docker container.

**Architecture:** All views become `async def` handlers; `AchievementNotificationMiddleware` becomes fully async; email tasks fire via `transaction.on_commit` + `sync_to_async` thread; the monthly `award_best_suchar` job runs inside the web process via `django-apscheduler`'s `BackgroundScheduler`. The ASGI server stack is gunicorn + `UvicornWorker` in production, plain `uvicorn --reload` in dev.

**Tech Stack:** Django 6.0, uvicorn[standard], gunicorn + UvicornWorker, apscheduler 3.x, django-apscheduler, asgiref (sync_to_async), psycopg[c] (already async-capable), django-redis (already async-capable)

**Spec:** `docs/superpowers/specs/2026-05-25-async-django-migration-design.md`

---

## File Map

### New files
| Path | Purpose |
|---|---|
| `config/asgi.py` | ASGI entry point |
| `suchar_overflow/users/mixins.py` | `AsyncLoginRequiredMixin`, `AsyncUserPassesTestMixin` |

### Modified files
| Path | What changes |
|---|---|
| `pyproject.toml` | Add django 6.0, uvicorn, apscheduler, django-apscheduler; later remove django-rq, rq-scheduler |
| `config/settings/base.py` | ASGI_APPLICATION, SECURE_CSP, CSP middleware, remove RQ_QUEUES, swap INSTALLED_APPS |
| `config/settings/test.py` | Remove RQ_QUEUES block |
| `compose/local/django/start` | uvicorn command |
| `compose/production/django/start` | gunicorn + UvicornWorker |
| `docker-compose.local.yml` | Remove rqworker service |
| `docker-compose.production.yml` | Remove rqworker service |
| `suchar_overflow/achievements/middleware.py` | Async `__call__`, `async_capable = True` |
| `suchar_overflow/achievements/apps.py` | `_start_scheduler()` in `ready()` |
| `suchar_overflow/achievements/views.py` | Async handlers, async SSE generator |
| `suchar_overflow/achievements/tests/test_middleware.py` | `async_client`, `async def` |
| `suchar_overflow/achievements/tests/test_stream.py` | `async_client`, `async def` |
| `suchar_overflow/achievements/tests/test_views.py` | `async_client`, `async def` |
| `suchar_overflow/users/views.py` | Async handlers, remove `django_rq` import |
| `suchar_overflow/users/tests/test_signup_and_email.py` | Remove `sync_rq` fixture, async client |
| `suchar_overflow/users/tests/test_views_extra.py` | `async_client`, `async def` |
| `suchar_overflow/suchary/views.py` | Async handlers, `AsyncPaginator` |
| `suchar_overflow/stats/views.py` | `sync_to_async` wrapper on `get_context_data` |

### Deleted files
| Path | Reason |
|---|---|
| `compose/local/django/start-rqworker` | rqworker container removed |
| `compose/production/django/start-rqworker` | rqworker container removed |
| `suchar_overflow/achievements/management/commands/register_scheduled_jobs.py` | replaced by `AppConfig.ready()` |

---

## Task 1: Upgrade Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update pyproject.toml dependencies**

In `pyproject.toml`, under `[project] → dependencies`, make these changes:

```toml
dependencies = [
    "argon2-cffi==25.1.0",
    "django==6.0.6",                      # was 5.2.10
    "django-environ==0.12.0",
    "django-redis==6.0.0",
    "gunicorn==23.0.0",
    "hiredis==3.3.0",
    "pillow==12.1.0",
    "psycopg[c]==3.3.2",
    "python-slugify==8.0.4",
    "whitenoise==6.11.0",
    "django-ninja==1.5.3",
    "django-compressor==4.5.1",
    "rcssmin==1.1.2",
    "rjsmin==1.2.2",
    "redis==5.2.1",
    "django-rq==3.0.0",                   # keep for now — removed in Task 13
    "openai>=1.0.0",
    "polib>=1.2.0",
    "rq-scheduler>=0.13",                 # keep for now — removed in Task 13
    "django-modeltranslation>=0.20.3",
    "uvicorn[standard]>=0.34",            # NEW
    "apscheduler>=3.10,<4",               # NEW
    "django-apscheduler>=0.7",            # NEW
]
```

- [ ] **Step 2: Regenerate lock file and rebuild Docker image**

```bash
uv lock
just build
```

Expected: `uv lock` completes without errors; `just build` rebuilds the image with the new packages.

- [ ] **Step 3: Run tests to verify Django 6.0 compatibility**

```bash
just test
```

Expected: all existing tests pass. If `DEFAULT_AUTO_FIELD` warnings appear, they are already handled (`base.py` has `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: upgrade to Django 6.0, add uvicorn and APScheduler deps"
```

---

## Task 2: ASGI Entry Point and Start Scripts

**Files:**
- Create: `config/asgi.py`
- Modify: `compose/local/django/start`
- Modify: `compose/production/django/start`

- [ ] **Step 1: Create `config/asgi.py`**

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

- [ ] **Step 2: Update local dev start script**

Replace the full content of `compose/local/django/start`:

```bash
#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset


python manage.py migrate
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 3: Update production start script**

Replace the full content of `compose/production/django/start`:

```bash
#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

python /app/manage.py migrate --noinput
python /app/manage.py collectstatic --noinput
python /app/manage.py compress --force

exec gunicorn config.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:5000 \
  --chdir /app
```

- [ ] **Step 4: Verify the server starts under uvicorn**

```bash
just build
docker-compose -f docker-compose.local.yml up django
```

Expected: log line containing `Started server process` from uvicorn, app reachable on `http://localhost:8000`.

- [ ] **Step 5: Commit**

```bash
git add config/asgi.py compose/local/django/start compose/production/django/start
git commit -m "feat: add ASGI entry point and switch start scripts to uvicorn"
```

---

## Task 3: Settings — ASGI, CSP, and Installed Apps

**Files:**
- Modify: `config/settings/base.py`
- Modify: `config/settings/test.py`

- [ ] **Step 1: Add `ASGI_APPLICATION` to `base.py`**

In `base.py`, immediately after the `WSGI_APPLICATION` line (~line 90):

```python
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"
# https://docs.djangoproject.com/en/dev/ref/settings/#asgi-application
ASGI_APPLICATION = "config.asgi.application"
```

- [ ] **Step 2: Swap `INSTALLED_APPS` — replace `django_rq` with `django_apscheduler`**

In `base.py`, find the `THIRD_PARTY_APPS` list (~line 121) and replace:

```python
THIRD_PARTY_APPS = [
    "django_apscheduler",
    "compressor",
]
```

- [ ] **Step 3: Add CSP middleware and `SECURE_CSP` setting to `base.py`**

In `base.py`, find the `MIDDLEWARE` list (~line 187). Add the CSP line after `SecurityMiddleware`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.security.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "suchar_overflow.achievements.middleware.AchievementNotificationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

Then add `SECURE_CSP` near the bottom of `base.py` (before `# Your stuff`):

```python
# CSP
# ------------------------------------------------------------------------------
from django.utils.csp import CSP  # noqa: E402

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "font-src": [CSP.SELF],
}
```

- [ ] **Step 4: Remove `RQ_QUEUES` from `test.py`**

In `config/settings/test.py`, delete the entire RQ block at the bottom:

```python
# DELETE this block entirely:
# RQ
# ------------------------------------------------------------------------------
# Re-declare queues without USE_REDIS_CACHE so tests don't need Redis.
# django_rq.enqueue is patched to run synchronously in tests that need it.
RQ_QUEUES = {
    "default": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 0,
        "ASYNC": False,
    },
}
```

- [ ] **Step 5: Run migration for `django_apscheduler` tables**

```bash
docker-compose -f docker-compose.local.yml exec -T django bash -c \
  "cd /app && python manage.py migrate"
```

Expected: two new tables created — `django_apscheduler_djangojob` and `django_apscheduler_djangojobexecution`.

- [ ] **Step 6: Run tests**

```bash
just test
```

Expected: all tests pass. The CSP middleware and ASGI_APPLICATION setting have no impact on the test runner.

- [ ] **Step 7: Commit**

```bash
git add config/settings/base.py config/settings/test.py
git commit -m "feat: add ASGI_APPLICATION, CSP middleware, swap django_rq for django_apscheduler"
```

---

## Task 4: `AsyncLoginRequiredMixin` and `AsyncUserPassesTestMixin`

**Files:**
- Create: `suchar_overflow/users/mixins.py`
- Create: `suchar_overflow/users/tests/test_mixins.py`

- [ ] **Step 1: Write failing tests**

Create `suchar_overflow/users/tests/test_mixins.py`:

```python
"""Tests for async auth mixins."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import AsyncRequestFactory
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin

User = get_user_model()


class _SimpleAsyncView(AsyncLoginRequiredMixin, View):
    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


class _PassesTestView(AsyncUserPassesTestMixin, View):
    async def test_func(self):
        return self.request.user.username == "allowed"

    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


@pytest.mark.django_db
async def test_async_login_required_redirects_anonymous(async_client):
    response = await async_client.get("/fake-path/")
    # The mixin itself — tested via direct dispatch below
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = type("Anon", (), {"is_authenticated": False})()
    view = _SimpleAsyncView.as_view()
    response = await view(request)
    assert response.status_code == HTTPStatus.FOUND


@pytest.mark.django_db
async def test_async_login_required_allows_authenticated(async_client, django_user_model):
    user = await django_user_model.objects.acreate_user(
        username="u",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _SimpleAsyncView.as_view()
    response = await view(request)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
async def test_async_user_passes_test_blocks_failing_user(django_user_model):
    user = await django_user_model.objects.acreate_user(
        username="blocked",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _PassesTestView.as_view()
    response = await view(request)
    assert response.status_code == HTTPStatus.FOUND  # redirect to login


@pytest.mark.django_db
async def test_async_user_passes_test_allows_passing_user(django_user_model):
    user = await django_user_model.objects.acreate_user(
        username="allowed",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _PassesTestView.as_view()
    response = await view(request)
    assert response.status_code == HTTPStatus.OK
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
just test suchar_overflow/users/tests/test_mixins.py
```

Expected: `ImportError` — `AsyncLoginRequiredMixin` does not exist yet.

- [ ] **Step 3: Create `suchar_overflow/users/mixins.py`**

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin


class AsyncLoginRequiredMixin(LoginRequiredMixin):
    """LoginRequiredMixin that works with async view handlers."""

    async def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return await super().dispatch(request, *args, **kwargs)


class AsyncUserPassesTestMixin(UserPassesTestMixin):
    """UserPassesTestMixin that works with async view handlers and async test_func."""

    async def dispatch(self, request, *args, **kwargs):
        if not await self.test_func():
            return self.handle_no_permission()
        return await super().dispatch(request, *args, **kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
just test suchar_overflow/users/tests/test_mixins.py
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add suchar_overflow/users/mixins.py suchar_overflow/users/tests/test_mixins.py
git commit -m "feat: add AsyncLoginRequiredMixin and AsyncUserPassesTestMixin"
```

---

## Task 5: Async `AchievementNotificationMiddleware`

**Files:**
- Modify: `suchar_overflow/achievements/middleware.py`
- Modify: `suchar_overflow/achievements/tests/test_middleware.py`

- [ ] **Step 1: Write a failing test for the async attribute**

Add at the top of `suchar_overflow/achievements/tests/test_middleware.py` (after the imports):

```python
from suchar_overflow.achievements.middleware import AchievementNotificationMiddleware


def test_middleware_is_async_capable():
    assert AchievementNotificationMiddleware.async_capable is True
    assert AchievementNotificationMiddleware.sync_capable is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
just test suchar_overflow/achievements/tests/test_middleware.py::test_middleware_is_async_capable
```

Expected: `AttributeError` — `async_capable` not defined.

- [ ] **Step 3: Rewrite `achievements/middleware.py`**

Replace the full file content:

```python
from django.core.cache import cache

_CACHE_KEY = "achievements_pending:{user_pk}"


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

- [ ] **Step 4: Update all tests in `test_middleware.py` to use `async_client`**

Replace the full content of `suchar_overflow/achievements/tests/test_middleware.py`:

```python
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.urls import reverse

from suchar_overflow.achievements.middleware import AchievementNotificationMiddleware
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()


def test_middleware_is_async_capable():
    assert AchievementNotificationMiddleware.async_capable is True
    assert AchievementNotificationMiddleware.sync_capable is False


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(slug="test-ach", name="Test Achievement"):
    achievement, _ = Achievement.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "description": "A test achievement.",
            "icon_content": "<svg></svg>",
            "category": "LIFETIME",
            "event_type": "SUCHAR_POSTED",
            "metric": "COUNT_SUCHAR",
            "threshold": 1,
        },
    )
    return achievement


def _set_pending_flag(user):
    cache.set(f"achievements_pending:{user.pk}", value=True, timeout=60)


@pytest.mark.django_db
async def test_unseen_achievement_produces_no_toast(async_client):
    user = make_user("winner")
    achievement = make_achievement()
    UserAchievement.objects.create(user=user, achievement=achievement, is_seen=False)
    _set_pending_flag(user)

    await async_client.aforce_login(user)
    response = await async_client.get(reverse("suchary:list"), follow=True)

    texts = [str(m) for m in get_messages(response.wsgi_request)]
    assert not any("Test Achievement" in t for t in texts)


@pytest.mark.django_db
async def test_middleware_does_not_mark_achievement_as_seen(async_client):
    user = make_user("winner")
    achievement = make_achievement()
    ua = UserAchievement.objects.create(
        user=user,
        achievement=achievement,
        is_seen=False,
    )
    _set_pending_flag(user)

    await async_client.aforce_login(user)
    await async_client.get(reverse("suchary:list"))

    ua.refresh_from_db()
    assert ua.is_seen is False


@pytest.mark.django_db
async def test_seen_achievement_produces_no_message(async_client):
    user = make_user("winner")
    achievement = make_achievement()
    UserAchievement.objects.create(user=user, achievement=achievement, is_seen=True)

    await async_client.aforce_login(user)
    response = await async_client.get(reverse("suchary:list"), follow=True)

    messages = list(get_messages(response.wsgi_request))
    texts = [str(m) for m in messages]
    assert not any("Test Achievement" in t for t in texts)


@pytest.mark.django_db
async def test_unauthenticated_user_gets_no_messages(async_client):
    response = await async_client.get(reverse("suchary:list"), follow=True)
    assert response.status_code == HTTPStatus.OK
    messages = list(get_messages(response.wsgi_request))
    assert all("Achievement Unlocked" not in str(m) for m in messages)


@pytest.mark.django_db
async def test_cache_flag_cleared_after_middleware_runs(async_client):
    user = make_user("winner")
    achievement = make_achievement()
    UserAchievement.objects.create(user=user, achievement=achievement, is_seen=False)
    _set_pending_flag(user)

    await async_client.aforce_login(user)
    await async_client.get(reverse("suchary:list"))

    assert cache.get(f"achievements_pending:{user.pk}") is None


@pytest.mark.django_db
async def test_no_delivery_when_no_cache_flag(async_client):
    user = make_user("winner")
    achievement = make_achievement()
    UserAchievement.objects.create(user=user, achievement=achievement, is_seen=False)

    await async_client.aforce_login(user)
    response = await async_client.get(reverse("suchary:list"), follow=True)

    assert not UserAchievement.objects.filter(user=user, is_seen=True).exists()
    texts = [str(m) for m in get_messages(response.wsgi_request)]
    assert not any("Test Achievement" in t for t in texts)
```

- [ ] **Step 5: Run all middleware tests**

```bash
just test suchar_overflow/achievements/tests/test_middleware.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/achievements/middleware.py \
        suchar_overflow/achievements/tests/test_middleware.py
git commit -m "feat: convert AchievementNotificationMiddleware to async"
```

---

## Task 6: Async Achievements Views

**Files:**
- Modify: `suchar_overflow/achievements/views.py`
- Modify: `suchar_overflow/achievements/tests/test_stream.py`
- Modify: `suchar_overflow/achievements/tests/test_views.py`

- [ ] **Step 1: Update `test_stream.py` to use `async_client`**

Replace the full content of `suchar_overflow/achievements/tests/test_stream.py`:

```python
"""Tests for the achievement SSE stream endpoint."""

import asyncio
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

User = get_user_model()

STREAM_URL = "achievements:stream"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


@pytest.mark.django_db
async def test_stream_requires_login(async_client):
    response = await async_client.get(reverse(STREAM_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
async def test_stream_content_type_is_event_stream(async_client):
    user = make_user("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert "text/event-stream" in response.get("Content-Type", "")


@pytest.mark.django_db
async def test_stream_sets_cache_control_no_cache(async_client):
    user = make_user("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert response.get("Cache-Control") == "no-cache"


@pytest.mark.django_db
async def test_stream_sets_x_accel_buffering_no(async_client):
    user = make_user("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert response.get("X-Accel-Buffering") == "no"


@pytest.mark.django_db
async def test_stream_sends_retry_when_no_pending(async_client):
    user = make_user("u1")
    await async_client.aforce_login(user)
    await cache.adelete(f"achievements_pending:{user.pk}")

    response = await async_client.get(reverse(STREAM_URL))
    content = b"".join([c async for c in response.streaming_content]).decode()
    assert "retry:" in content


@pytest.mark.django_db
async def test_stream_sends_data_new_when_pending(async_client):
    user = make_user("u1")
    await async_client.aforce_login(user)
    await cache.aset(f"achievements_pending:{user.pk}", True, timeout=60)

    response = await async_client.get(reverse(STREAM_URL))
    content = b"".join([c async for c in response.streaming_content]).decode()
    assert "data: new" in content


@pytest.mark.django_db
async def test_stream_does_not_send_data_without_cache_flag(async_client):
    user = make_user("u1")
    await async_client.aforce_login(user)
    await cache.adelete(f"achievements_pending:{user.pk}")

    response = await async_client.get(reverse(STREAM_URL))
    content = b"".join([c async for c in response.streaming_content]).decode()
    assert "data: new" not in content
```

- [ ] **Step 2: Update `test_views.py` to use `async_client`**

Replace the full content of `suchar_overflow/achievements/tests/test_views.py`:

```python
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()

ACHIEVEMENT_LIST_URL = "achievements:list"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(slug, name="Achievement", *, is_secret=False, theme="", tier=Achievement.Tier.NONE):
    return Achievement.objects.create(
        slug=slug,
        name=name,
        description="A test achievement.",
        icon_content="<svg></svg>",
        category="LIFETIME",
        event_type="SUCHAR_POSTED",
        metric="COUNT_SUCHAR",
        threshold=1,
        is_secret=is_secret,
        theme=theme,
        tier=tier,
    )


@pytest.mark.django_db
async def test_achievement_list_requires_login(async_client):
    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
async def test_achievement_list_renders_for_authenticated_user(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
async def test_achievement_list_shows_all_non_grouped_achievements(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    make_achievement("ach-1", name="Achievement One")
    make_achievement("ach-2", name="Achievement Two")

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    achs = response.context["achievements"]
    names = [a.name for a in achs]
    assert "Achievement One" in names
    assert "Achievement Two" in names


@pytest.mark.django_db
async def test_user_achievements_set_in_context(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    ach = make_achievement("ach-1")
    UserAchievement.objects.create(user=user, achievement=ach)

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert ach.pk in response.context["user_achievements"]


@pytest.mark.django_db
async def test_unearned_achievement_not_in_user_achievements(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    ach = make_achievement("ach-1")

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert ach.pk not in response.context["user_achievements"]


@pytest.mark.django_db
async def test_series_first_locked_achievement_is_visible(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)

    ach_bronze = make_achievement("series-bronze", name="Bronze", theme="Programming", tier=Achievement.Tier.BRONZE)
    make_achievement("series-silver", name="Silver", theme="Programming", tier=Achievement.Tier.SILVER)

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    ids = [a.id for a in response.context["achievements"]]
    assert ach_bronze.id in ids


@pytest.mark.django_db
async def test_series_locked_second_tier_hidden_until_first_earned(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)

    make_achievement("series-bronze", name="Bronze", theme="Programming", tier=Achievement.Tier.BRONZE)
    ach_silver = make_achievement("series-silver", name="Silver", theme="Programming", tier=Achievement.Tier.SILVER)

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    ids = [a.id for a in response.context["achievements"]]
    assert ach_silver.id not in ids


@pytest.mark.django_db
async def test_series_second_tier_visible_after_first_earned(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)

    ach_bronze = make_achievement("series-bronze", name="Bronze", theme="Programming", tier=Achievement.Tier.BRONZE)
    ach_silver = make_achievement("series-silver", name="Silver", theme="Programming", tier=Achievement.Tier.SILVER)
    UserAchievement.objects.create(user=user, achievement=ach_bronze)

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    ids = [a.id for a in response.context["achievements"]]
    assert ach_silver.id in ids


@pytest.mark.django_db
async def test_achievement_list_user_has_no_earned_achievements(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.OK
    assert response.context["user_achievements"] == set()
```

- [ ] **Step 3: Run updated tests to confirm they pass with existing sync views**

```bash
just test suchar_overflow/achievements/tests/test_stream.py suchar_overflow/achievements/tests/test_views.py
```

Expected: all pass (ASGI serves sync views in thread pool).

- [ ] **Step 4: Rewrite `achievements/views.py` with async handlers**

Replace the full content of `suchar_overflow/achievements/views.py`:

```python
import asyncio

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin

from .models import Achievement
from .models import UserAchievement


@login_required
async def achievement_stream(request):
    """SSE endpoint: checks once for pending achievements, sets retry interval, closes."""

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


class MyAchievementsView(AsyncLoginRequiredMixin, View):
    template_name = "achievements/mine.html"

    async def get(self, request, *args, **kwargs):
        await UserAchievement.objects.filter(
            user=request.user,
            is_seen=False,
        ).aupdate(is_seen=True)

        user_achievements = [
            ua
            async for ua in UserAchievement.objects.filter(user=request.user)
            .select_related("achievement")
            .order_by("-awarded_at")
        ]
        return render(request, self.template_name, {"user_achievements": user_achievements})


class AchievementListView(AsyncLoginRequiredMixin, View):
    template_name = "achievements/list.html"

    async def get(self, request, *args, **kwargs):
        user_achs = {
            pk
            async for pk in UserAchievement.objects.filter(
                user=request.user,
            ).values_list("achievement_id", flat=True)
        }

        all_achs = [a async for a in Achievement.objects.all().order_by("theme", "tier", "id")]
        visible_achs = []
        grouped: dict[tuple[str, str], list[Achievement]] = {}

        for ach in all_achs:
            if ach.theme and ach.tier != Achievement.Tier.NONE:
                key = (ach.theme, ach.metric)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(ach)
            else:
                visible_achs.append(ach)

        for series in grouped.values():
            for ach in series:
                visible_achs.append(ach)
                if ach.id not in user_achs:
                    break

        visible_achs.sort(key=lambda x: (x.theme or "", x.tier, x.id))

        return render(
            request,
            self.template_name,
            {"achievements": visible_achs, "user_achievements": user_achs},
        )
```

- [ ] **Step 5: Run all achievement tests**

```bash
just test suchar_overflow/achievements/tests/test_stream.py \
          suchar_overflow/achievements/tests/test_views.py \
          suchar_overflow/achievements/tests/test_middleware.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/achievements/views.py \
        suchar_overflow/achievements/tests/test_stream.py \
        suchar_overflow/achievements/tests/test_views.py
git commit -m "feat: convert achievements views to async"
```

---

## Task 7: Async Users Views — Simple `View` Subclasses

**Files:**
- Modify: `suchar_overflow/users/views.py` (ActivateAccountView, EmailChangeDoneView, EmailChangeConfirmView, EmailChangeRevokeView)
- Modify: `suchar_overflow/users/tests/test_views_extra.py`

- [ ] **Step 1: Update `test_views_extra.py` to use `async_client`**

Read the current file, then convert all `def test_*` to `async def test_*` and all `client.*` calls to `await async_client.*`. Change the fixture signature from `client` to `async_client`. Also change `client.force_login` to `await async_client.aforce_login`. Make sure every test function is `async def`.

The key pattern for the entire file:
```python
# Before
@pytest.mark.django_db
def test_something(client):
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == HTTPStatus.OK

# After
@pytest.mark.django_db
async def test_something(async_client):
    await async_client.aforce_login(user)
    response = await async_client.get(url)
    assert response.status_code == HTTPStatus.OK
```

Apply this pattern to every test in `test_views_extra.py`.

- [ ] **Step 2: Run updated tests to confirm they still pass**

```bash
just test suchar_overflow/users/tests/test_views_extra.py
```

Expected: all pass (sync views work under ASGI).

- [ ] **Step 3: Convert `ActivateAccountView` in `users/views.py` to async**

Find `class ActivateAccountView` and replace its `get` method:

```python
class ActivateAccountView(View):
    async def get(self, request, token):
        try:
            activation = await ActivationToken.objects.select_related("user").aget(
                token=token,
            )
        except ActivationToken.DoesNotExist:
            return render(request, "registration/activation_failed.html")

        if not activation.is_valid():
            await activation.adelete()
            return render(request, "registration/activation_failed.html")

        user = activation.user
        user.is_active = True
        await user.asave()
        await activation.adelete()
        return render(request, "registration/activation_complete.html")
```

- [ ] **Step 4: Convert `EmailChangeDoneView` to async**

```python
class EmailChangeDoneView(AsyncLoginRequiredMixin, View):
    async def get(self, request, *args, **kwargs):
        return render(request, "users/email_change_done.html")
```

- [ ] **Step 5: Convert `EmailChangeConfirmView` to async**

Find `class EmailChangeConfirmView` and replace its `get` method (preserving all current business logic):

```python
class EmailChangeConfirmView(AsyncLoginRequiredMixin, View):
    async def get(self, request, token):
        try:
            email_request = await EmailChangeRequest.objects.aget(
                verification_token=token,
            )
        except EmailChangeRequest.DoesNotExist:
            return render(request, "users/email_change_failed.html")

        if email_request.status != EmailChangeRequest.Status.PENDING:
            return render(request, "users/email_change_failed.html")

        if email_request.is_expired():
            email_request.status = EmailChangeRequest.Status.REVOKED
            await email_request.asave()
            return render(request, "users/email_change_failed.html")

        if await User.objects.filter(email=email_request.new_email).aexists():
            return render(request, "users/email_change_failed.html")

        user = await User.objects.aget(pk=email_request.user_id)
        user.email = email_request.new_email
        await user.asave()
        email_request.status = EmailChangeRequest.Status.VERIFIED
        await email_request.asave()
        return render(request, "users/email_change_done.html")
```

- [ ] **Step 6: Convert `EmailChangeRevokeView` to async**

```python
class EmailChangeRevokeView(AsyncLoginRequiredMixin, View):
    async def get(self, request, token):
        try:
            email_request = await EmailChangeRequest.objects.aget(
                revocation_token=token,
            )
        except EmailChangeRequest.DoesNotExist:
            return render(request, "users/email_change_failed.html")

        if email_request.status == EmailChangeRequest.Status.VERIFIED:
            user = await User.objects.aget(pk=email_request.user_id)
            user.email = email_request.old_email
            await user.asave()

        email_request.status = EmailChangeRequest.Status.REVOKED
        await email_request.asave()
        return render(request, "users/email_change_done.html")
```

Add `from suchar_overflow.users.mixins import AsyncLoginRequiredMixin` to `users/views.py` imports and remove `LoginRequiredMixin` import if it's no longer used by the remaining sync views (check first — `UserDetailView`, `UserUpdateView`, `UserRedirectView` still use `LoginRequiredMixin` or will be converted in Task 9).

- [ ] **Step 7: Run tests**

```bash
just test suchar_overflow/users/tests/test_signup_and_email.py \
          suchar_overflow/users/tests/test_views_extra.py
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add suchar_overflow/users/views.py \
        suchar_overflow/users/tests/test_views_extra.py
git commit -m "feat: convert ActivateAccount and EmailChange views to async"
```

---

## Task 8: Async Email Dispatch — SignupView and EmailChangeInitiateView

**Files:**
- Modify: `suchar_overflow/users/views.py` (SignupView, EmailChangeInitiateView)
- Modify: `suchar_overflow/users/tests/test_signup_and_email.py`

- [ ] **Step 1: Rewrite `test_signup_and_email.py` — remove `sync_rq`, switch to `async_client`**

Replace the full content of `suchar_overflow/users/tests/test_signup_and_email.py`:

```python
"""
Tests for user signup, account activation, and email-change flows.
"""

import asyncio
import datetime
import uuid
from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.users.models import ActivationToken
from suchar_overflow.users.models import EmailChangeRequest

User = get_user_model()


def make_user(username, email=None, password="password", *, is_active=True):  # noqa: S107
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password=password,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# SignupView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
async def test_signup_get_renders_form(async_client):
    response = await async_client.get(reverse("users:signup"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
async def test_signup_creates_inactive_user(async_client):
    response = await async_client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.FOUND
    user = await User.objects.aget(username="newuser")
    assert not user.is_active


@pytest.mark.django_db
async def test_signup_creates_activation_token(async_client):
    await async_client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    user = await User.objects.aget(username="newuser")
    assert await ActivationToken.objects.filter(user=user).aexists()


@pytest.mark.django_db(transaction=True)
async def test_signup_sends_activation_email(async_client):
    with patch("suchar_overflow.users.tasks.send_activation_email") as mock_send:
        await async_client.post(
            reverse("users:signup"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "Str0ngP@ssword!",
                "password2": "Str0ngP@ssword!",
            },
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert mock_send.called
        call_args = mock_send.call_args[0]
        assert "newuser@example.com" not in call_args  # pk passed, not email directly


@pytest.mark.django_db
async def test_signup_redirects_to_done_page(async_client):
    response = await async_client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.FOUND
    assert response["Location"] == reverse("users:signup_done")


@pytest.mark.django_db
async def test_signup_duplicate_username_shows_error(async_client):
    make_user("existing")
    response = await async_client.post(
        reverse("users:signup"),
        {
            "username": "existing",
            "email": "other@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.OK
    assert await User.objects.filter(username="existing").acount() == 1


@pytest.mark.django_db
async def test_signup_duplicate_email_shows_error(async_client):
    make_user("existing", email="taken@example.com")
    response = await async_client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "taken@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.OK
    assert not await User.objects.filter(username="newuser").aexists()


# ---------------------------------------------------------------------------
# ActivateAccountView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
async def test_activate_valid_token_activates_user(async_client):
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)
    response = await async_client.get(
        reverse("users:activate", kwargs={"token": token.token}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert user.is_active


@pytest.mark.django_db
async def test_activate_valid_token_is_deleted_after_use(async_client):
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)
    await async_client.get(reverse("users:activate", kwargs={"token": token.token}))
    assert not await ActivationToken.objects.filter(pk=token.pk).aexists()


@pytest.mark.django_db
async def test_activate_invalid_token_does_not_activate(async_client):
    user = make_user("inactive", is_active=False)
    response = await async_client.get(
        reverse("users:activate", kwargs={"token": uuid.uuid4()}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert not user.is_active


@pytest.mark.django_db
async def test_activate_expired_token_does_not_activate(async_client):
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)
    await ActivationToken.objects.filter(pk=token.pk).aupdate(
        created_at=timezone.now() - datetime.timedelta(hours=73),
    )
    response = await async_client.get(
        reverse("users:activate", kwargs={"token": token.token}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert not user.is_active
    assert not await ActivationToken.objects.filter(pk=token.pk).aexists()


# ---------------------------------------------------------------------------
# EmailChangeInitiateView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
async def test_email_change_initiate_requires_login(async_client):
    response = await async_client.get(reverse("users:email_change_initiate"))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
async def test_email_change_initiate_get_renders_form(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse("users:email_change_initiate"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db(transaction=True)
async def test_email_change_creates_request_and_sends_emails(async_client):
    user = make_user("user1", email="old@example.com")
    await async_client.aforce_login(user)

    with patch("suchar_overflow.users.tasks.send_email_change_emails") as mock_send:
        response = await async_client.post(
            reverse("users:email_change_initiate"),
            {"email": "new@example.com"},
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert response.status_code == HTTPStatus.FOUND
    assert await EmailChangeRequest.objects.filter(
        user=user,
        new_email="new@example.com",
    ).aexists()
    assert mock_send.called
    call_args = mock_send.call_args[0]
    assert "old@example.com" in call_args
    assert "new@example.com" in call_args


@pytest.mark.django_db
async def test_email_change_rejects_already_taken_email(async_client):
    make_user("other", email="taken@example.com")
    user = make_user("user1", email="mine@example.com")
    await async_client.aforce_login(user)

    response = await async_client.post(
        reverse("users:email_change_initiate"),
        {"email": "taken@example.com"},
    )
    assert response.status_code == HTTPStatus.OK
    assert not await EmailChangeRequest.objects.filter(user=user).aexists()


# ---------------------------------------------------------------------------
# EmailChangeConfirmView / EmailChangeRevokeView tests unchanged below
# (keeping existing test logic, converted to async)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
async def test_email_change_confirm_success(async_client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_verify", kwargs={"token": str(email_req.verification_token)}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert user.email == "new@example.com"
    await email_req.arefresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.VERIFIED


@pytest.mark.django_db
async def test_email_change_confirm_expired_token(async_client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    await EmailChangeRequest.objects.filter(pk=email_req.pk).aupdate(
        created_at=timezone.now() - datetime.timedelta(hours=25),
    )
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_verify", kwargs={"token": str(email_req.verification_token)}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert user.email == "old@example.com"
    await email_req.arefresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.REVOKED


@pytest.mark.django_db
async def test_email_change_confirm_already_used_token(async_client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
        status=EmailChangeRequest.Status.VERIFIED,
    )
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_verify", kwargs={"token": str(email_req.verification_token)}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert user.email == "old@example.com"


@pytest.mark.django_db
async def test_email_change_confirm_invalid_token(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_verify", kwargs={"token": str(uuid.uuid4())}),
    )
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
async def test_email_change_confirm_rejects_duplicate_email(async_client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    make_user("other", email="new@example.com")
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_verify", kwargs={"token": str(email_req.verification_token)}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert user.email == "old@example.com"


@pytest.mark.django_db
async def test_email_change_revoke_pending_cancels(async_client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
        status=EmailChangeRequest.Status.PENDING,
    )
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_revoke", kwargs={"token": str(email_req.revocation_token)}),
    )
    assert response.status_code == HTTPStatus.OK
    await email_req.arefresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.REVOKED
    await user.arefresh_from_db()
    assert user.email == "old@example.com"


@pytest.mark.django_db
async def test_email_change_revoke_verified_undoes_change(async_client):
    user = make_user("user1", email="new@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
        status=EmailChangeRequest.Status.VERIFIED,
    )
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_revoke", kwargs={"token": str(email_req.revocation_token)}),
    )
    assert response.status_code == HTTPStatus.OK
    await user.arefresh_from_db()
    assert user.email == "old@example.com"
    await email_req.arefresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.REVOKED


@pytest.mark.django_db
async def test_email_change_revoke_invalid_token_is_graceful(async_client):
    user = make_user("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(
        reverse("users:email_change_revoke", kwargs={"token": str(uuid.uuid4())}),
    )
    assert response.status_code == HTTPStatus.OK
```

- [ ] **Step 2: Run tests to verify they pass with existing sync views**

```bash
just test suchar_overflow/users/tests/test_signup_and_email.py
```

Expected: all pass.

- [ ] **Step 3: Convert `SignupView` in `users/views.py` to async with `on_commit` email dispatch**

Replace the import block at the top of `users/views.py` — remove `import django_rq`, add `sync_to_async`:

```python
import asyncio
import datetime

from asgiref.sync import sync_to_async
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models.functions import TruncDay
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import RedirectView
from django.views.generic import UpdateView
from django.views.generic.edit import CreateView

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.models import User

from .forms import EmailChangeForm
from .forms import UserCreationForm
from .models import ActivationToken
from .models import EmailChangeRequest
from .tasks import send_activation_email
from .tasks import send_email_change_emails
```

Then replace `SignupView`:

```python
class SignupView(View):
    template_name = "registration/signup.html"
    success_url = reverse_lazy("users:signup_done")

    async def get(self, request, *args, **kwargs):
        form = UserCreationForm()
        return render(request, self.template_name, {"form": form})

    async def post(self, request, *args, **kwargs):
        form = UserCreationForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        user = form.save(commit=False)
        user.is_active = False
        await sync_to_async(user.save)()

        activation = await ActivationToken.objects.acreate(user=user)
        user_pk = user.pk
        host = request.get_host()
        token = str(activation.token)
        protocol = "https" if request.is_secure() else "http"

        async def _send():
            await sync_to_async(send_activation_email, thread_sensitive=False)(
                user_pk, host, token, protocol
            )

        transaction.on_commit(_send)
        return redirect(self.success_url)
```

- [ ] **Step 4: Convert `EmailChangeInitiateView` to async**

Replace `EmailChangeInitiateView`:

```python
class EmailChangeInitiateView(AsyncLoginRequiredMixin, View):
    template_name = "users/email_change_form.html"
    success_url = reverse_lazy("users:email_change_done")

    async def get(self, request, *args, **kwargs):
        form = EmailChangeForm()
        return render(request, self.template_name, {"form": form})

    async def post(self, request, *args, **kwargs):
        form = EmailChangeForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        new_email = form.cleaned_data["email"]
        user = request.user

        email_request = await EmailChangeRequest.objects.acreate(
            user=user,
            new_email=new_email,
            old_email=user.email,
        )

        current_site = request.get_host()
        protocol = "https" if request.is_secure() else "http"

        verify_url = reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_request.verification_token)},
        )
        revoke_url = reverse(
            "users:email_change_revoke",
            kwargs={"token": str(email_request.revocation_token)},
        )

        user_pk = user.pk
        old_email = user.email
        verify_full = f"{protocol}://{current_site}{verify_url}"
        revoke_full = f"{protocol}://{current_site}{revoke_url}"

        async def _send():
            await sync_to_async(send_email_change_emails, thread_sensitive=False)(
                user_pk, old_email, new_email, verify_full, revoke_full
            )

        transaction.on_commit(_send)
        return redirect(self.success_url)
```

- [ ] **Step 5: Run all email-related tests**

```bash
just test suchar_overflow/users/tests/test_signup_and_email.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/users/views.py \
        suchar_overflow/users/tests/test_signup_and_email.py
git commit -m "feat: convert signup and email-change views to async, replace RQ with on_commit"
```

---

## Task 9: Async Users Views — Profile Views

**Files:**
- Modify: `suchar_overflow/users/views.py` (UserDetailView, UserUpdateView, UserRedirectView)
- Modify: `suchar_overflow/users/tests/test_views.py`

- [ ] **Step 1: Convert `UserDetailView` to async**

In `users/views.py`, replace `UserDetailView`:

```python
class UserDetailView(AsyncLoginRequiredMixin, View):
    template_name = "users/user_detail.html"

    async def get(self, request, username, *args, **kwargs):
        profile_user = await User.objects.aget(username=username)
        now = timezone.now()

        latest_suchary = [
            s
            async for s in profile_user.suchary.filter(published_at__lte=now)
            .annotate(
                score=Count("votes"),
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
            .order_by("-created_at")[:5]
        ]

        context = {
            "object": profile_user,
            "latest_suchary": latest_suchary,
        }

        if request.user == profile_user:
            context["scheduled_suchary"] = [
                s
                async for s in profile_user.suchary.filter(
                    published_at__gt=now,
                ).order_by("published_at")
            ]

        stats = await profile_user.suchary.aaggregate(
            total_score=Count("votes"),
            funny_score=Count("votes", filter=Q(votes__is_funny=True)),
            dry_score=Count("votes", filter=Q(votes__is_dry=True)),
        )
        context.update(stats)

        return render(request, self.template_name, context)
```

- [ ] **Step 2: Convert `UserUpdateView` to async**

```python
class UserUpdateView(AsyncLoginRequiredMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None) -> User:
        assert self.request.user.is_authenticated
        return self.request.user

    async def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = form_class(instance=request.user)
        return render(request, self.get_template_names()[0], {"form": form, "object": request.user})

    async def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = form_class(request.POST, instance=request.user)
        if not form.is_valid():
            return render(request, self.get_template_names()[0], {"form": form, "object": request.user})
        await sync_to_async(form.save)()
        return redirect(self.get_success_url())
```

- [ ] **Step 3: Convert `UserRedirectView` to async**

```python
class UserRedirectView(AsyncLoginRequiredMixin, View):
    async def get(self, request, *args, **kwargs):
        return redirect(reverse("users:detail", kwargs={"username": request.user.username}))
```

- [ ] **Step 4: Update `test_views.py` — convert HTTP-level tests to async**

In `suchar_overflow/users/tests/test_views.py`, the `TestUserUpdateView` and `TestUserDetailView` classes use `RequestFactory` to test internal helpers (`get_success_url`, `get_object`). These stay sync — they do not go through the HTTP stack and work unchanged.

Any test functions at module level that use `client` (e.g. `test_user_detail_view`, `test_user_redirect_view`) must be converted:

```python
# Before
@pytest.mark.django_db
def test_user_redirect_view(client, user):
    client.force_login(user)
    response = client.get(reverse("users:redirect"))
    assert response.status_code == HTTPStatus.FOUND

# After
@pytest.mark.django_db
async def test_user_redirect_view(async_client, user):
    await async_client.aforce_login(user)
    response = await async_client.get(reverse("users:redirect"))
    assert response.status_code == HTTPStatus.FOUND
```

Apply this same `async def` + `async_client` + `aforce_login` pattern to every top-level test function in `test_views.py` that uses `client`. Do not change `RequestFactory`-based class methods.

- [ ] **Step 5: Run tests**

```bash
just test suchar_overflow/users/tests/
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/users/views.py \
        suchar_overflow/users/tests/test_views.py
git commit -m "feat: convert UserDetailView, UserUpdateView, UserRedirectView to async"
```

---

## Task 10: Async Suchary Views

**Files:**
- Modify: `suchar_overflow/suchary/views.py`

- [ ] **Step 1: Rewrite `suchary/views.py` with async handlers**

Replace the full content of `suchar_overflow/suchary/views.py`:

```python
import asyncio

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.paginator import InvalidPage
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin

from .forms import SucharForm
from .models import Suchar
from .models import Vote

_PER_PAGE = 10


class SucharListView(View):
    template_name = "suchary/suchar_list.html"

    async def get(self, request, *args, **kwargs):
        from django.core.paginator import AsyncPaginator  # noqa: PLC0415

        qs = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .filter(published_at__lte=timezone.now())
            .annotate(
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
        )

        if request.user.is_authenticated:
            qs = qs.annotate(
                user_is_funny=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=request.user,
                    ).values("is_funny")[:1],
                ),
                user_is_dry=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=request.user,
                    ).values("is_dry")[:1],
                ),
            )

        sort = request.GET.get("sort")
        if sort == "top":
            qs = qs.order_by("-funny_count", "-dry_count", "-created_at")
        else:
            qs = qs.order_by("-created_at")

        q = request.GET.get("q")
        if q:
            qs = qs.filter(Q(text__icontains=q) | Q(tags__name__icontains=q)).distinct()

        tag = request.GET.get("tag")
        if tag:
            qs = qs.filter(tags__slug=tag)

        author = request.GET.get("author")
        if author:
            qs = qs.filter(author__username=author)

        paginator = AsyncPaginator(qs, per_page=_PER_PAGE)
        try:
            page = await paginator.apage(request.GET.get("page", 1))
        except InvalidPage as exc:
            raise Http404 from exc

        return render(
            request,
            self.template_name,
            {"page_obj": page, "suchary": page.object_list},
        )


class SucharCreateView(AsyncLoginRequiredMixin, View):
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"form": SucharForm()})

    async def post(self, request, *args, **kwargs):
        form = SucharForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        suchar = form.save(commit=False)
        suchar.author = request.user
        await sync_to_async(suchar.save)()
        return redirect(self.success_url)


class SucharUpdateView(AsyncLoginRequiredMixin, AsyncUserPassesTestMixin, View):
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def _get_suchar(self, pk):
        try:
            return await Suchar.objects.select_related("author").aget(pk=pk)
        except Suchar.DoesNotExist as exc:
            raise Http404 from exc

    async def test_func(self):
        suchar = await self._get_suchar(self.kwargs["pk"])
        return suchar.author == self.request.user and not suchar.is_published

    async def handle_no_permission(self):
        suchar = await self._get_suchar(self.kwargs["pk"])
        if suchar.author == self.request.user and suchar.is_published:
            return render(self.request, "suchary/edit_too_late.html", status=403)
        return super().handle_no_permission()

    async def get(self, request, pk, *args, **kwargs):
        suchar = await self._get_suchar(pk)
        return render(request, self.template_name, {"form": SucharForm(instance=suchar)})

    async def post(self, request, pk, *args, **kwargs):
        suchar = await self._get_suchar(pk)
        form = SucharForm(request.POST, instance=suchar)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        await sync_to_async(form.save)()
        return redirect(self.success_url)


@login_required
async def vote_suchar(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        suchar = await Suchar.objects.aget(pk=pk)
    except Suchar.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    vote_type = request.POST.get("vote_type")
    if vote_type not in ["funny", "dry"]:
        return JsonResponse({"error": "Invalid vote type"}, status=400)

    vote, _ = await Vote.objects.aget_or_create(user=request.user, suchar=suchar)

    if vote_type == "funny":
        vote.is_funny = not vote.is_funny
    elif vote_type == "dry":
        vote.is_dry = not vote.is_dry

    if not vote.is_funny and not vote.is_dry:
        await vote.adelete()
    else:
        await sync_to_async(vote.save)()

    return redirect("suchary:list")
```

- [ ] **Step 2: Run the full test suite**

```bash
just test
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add suchar_overflow/suchary/views.py
git commit -m "feat: convert suchary views to async with AsyncPaginator"
```

---

## Task 11: Async Stats View

**Files:**
- Modify: `suchar_overflow/stats/views.py`

- [ ] **Step 1: Wrap `LeaderboardView.get_context_data` with `sync_to_async`**

The two helper functions (`get_daily_activity_data`, `get_all_time_activity_data`) and the heavy annotation queries in `get_context_data` are complex sync ORM chains. Rather than rewriting every annotation, wrap the whole context-building function.

Replace `class LeaderboardView` at the bottom of `stats/views.py`:

```python
from asgiref.sync import sync_to_async  # noqa: E402
from django.views import View  # noqa: E402


class LeaderboardView(View):
    template_name = "stats/leaderboard.html"

    async def get(self, request, *args, **kwargs):
        context = await sync_to_async(self._build_context)()
        return render(request, self.template_name, context)

    def _build_context(self):
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        top_authors_overall = list(
            User.objects.annotate(
                total_score=Count("suchary__votes"),
                funny_score=Count("suchary__votes", filter=Q(suchary__votes__is_funny=True)),
                dry_score=Count("suchary__votes", filter=Q(suchary__votes__is_dry=True)),
                suchar_count=Count("suchary", distinct=True),
            )
            .exclude(total_score=0)
            .order_by("-total_score")[:10]
        )

        top_authors_funny = list(
            User.objects.annotate(
                funny_score=Count("suchary__votes", filter=Q(suchary__votes__is_funny=True)),
                suchar_count=Count("suchary", distinct=True),
            )
            .exclude(funny_score=0)
            .order_by("-funny_score")[:10]
        )

        top_authors_dry = list(
            User.objects.annotate(
                dry_score=Count("suchary__votes", filter=Q(suchary__votes__is_dry=True)),
                suchar_count=Count("suchary", distinct=True),
            )
            .exclude(dry_score=0)
            .order_by("-dry_score")[:10]
        )

        top_suchars_overall = list(
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                score=Count("votes"),
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
            .exclude(score=0)
            .order_by("-score")[:10]
        )

        top_suchars_funny = list(
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                score=Count("votes"),
            )
            .exclude(funny_count=0)
            .order_by("-funny_count")[:10]
        )

        top_suchars_dry = list(
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
                score=Count("votes"),
            )
            .exclude(dry_count=0)
            .order_by("-dry_count")[:10]
        )

        chart_datasets = {
            "7": get_daily_activity_data(start_of_today, now, 7),
            "30": get_daily_activity_data(start_of_today, now, 30),
            "90": get_daily_activity_data(start_of_today, now, 90),
            "all": get_all_time_activity_data(start_of_today, now),
        }

        return {
            "top_authors_overall": top_authors_overall,
            "top_authors_funny": top_authors_funny,
            "top_authors_dry": top_authors_dry,
            "top_suchars_overall": top_suchars_overall,
            "top_suchars_funny": top_suchars_funny,
            "top_suchars_dry": top_suchars_dry,
            "chart_datasets": json.dumps(chart_datasets),
        }
```

- [ ] **Step 2: Run all tests**

```bash
just test
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add suchar_overflow/stats/views.py
git commit -m "feat: convert LeaderboardView to async via sync_to_async wrapper"
```

---

## Task 12: APScheduler — Replace `register_scheduled_jobs`

**Files:**
- Modify: `suchar_overflow/achievements/apps.py`
- Modify: `suchar_overflow/achievements/tests/test_tasks.py`
- Delete: `suchar_overflow/achievements/management/commands/register_scheduled_jobs.py`

- [ ] **Step 1: Remove the two `register_scheduled_jobs` tests from `test_tasks.py`**

In `suchar_overflow/achievements/tests/test_tasks.py`, delete from `# register_scheduled_jobs management command` heading to the end of the file (the two tests `test_register_scheduled_jobs_registers_cron_job` and `test_register_scheduled_jobs_is_idempotent`).

- [ ] **Step 2: Run tasks tests to verify remaining tests still pass**

```bash
just test suchar_overflow/achievements/tests/test_tasks.py
```

Expected: the four remaining task tests pass.

- [ ] **Step 3: Update `AchievementsConfig` in `achievements/apps.py`**

Replace the full content of `suchar_overflow/achievements/apps.py`:

```python
import sys

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

_NO_SCHEDULER = frozenset({
    "migrate",
    "makemigrations",
    "collectstatic",
    "compress",
    "check",
    "shell",
    "createsuperuser",
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
        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: PLC0415
        from django_apscheduler.jobstores import DjangoJobStore  # noqa: PLC0415

        from suchar_overflow.achievements.tasks import award_best_suchar  # noqa: PLC0415

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

- [ ] **Step 4: Delete the management command**

```bash
rm suchar_overflow/achievements/management/commands/register_scheduled_jobs.py
```

- [ ] **Step 5: Run all tests**

```bash
just test
```

Expected: all tests pass. The scheduler does not start during pytest (guarded by `"pytest" in sys.modules`).

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/achievements/apps.py \
        suchar_overflow/achievements/tests/test_tasks.py
git rm suchar_overflow/achievements/management/commands/register_scheduled_jobs.py
git commit -m "feat: replace rq-scheduler with in-process APScheduler via AppConfig.ready()"
```

---

## Task 13: Remove Django-RQ Entirely

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/settings/base.py` (remove RQ_QUEUES block)
- Modify: `docker-compose.local.yml`
- Modify: `docker-compose.production.yml`
- Delete: `compose/local/django/start-rqworker`
- Delete: `compose/production/django/start-rqworker`

- [ ] **Step 1: Remove `django-rq` and `rq-scheduler` from `pyproject.toml`**

In `pyproject.toml` under `[project] → dependencies`, remove:

```toml
# DELETE these two lines:
"django-rq==3.0.0",
"rq-scheduler>=0.13",
```

- [ ] **Step 2: Remove `RQ_QUEUES` block from `base.py`**

In `config/settings/base.py`, find and delete:

```python
_rq_queue: dict = {"URL": REDIS_URL}
if REDIS_SSL:
    _rq_queue["SSL_CERT_REQS"] = None

RQ_QUEUES = {"default": _rq_queue}
```

- [ ] **Step 3: Remove `rqworker` from `docker-compose.local.yml`**

Delete the entire `rqworker` service block:

```yaml
# DELETE this block:
  rqworker:
    <<: *django
    image: suchar_overflow_local_rqworker
    container_name: suchar_overflow_local_rqworker
    depends_on:
      - postgres
      - redis
    ports: []
    command: /start-rqworker
```

- [ ] **Step 4: Remove `rqworker` from `docker-compose.production.yml`**

Delete the entire `rqworker` service block:

```yaml
# DELETE this block:
  rqworker:
    <<: *django
    image: suchar_overflow_production_rqworker
    depends_on:
      - postgres
      - redis
    command: /start-rqworker
```

- [ ] **Step 5: Delete start-rqworker scripts**

```bash
rm compose/local/django/start-rqworker
rm compose/production/django/start-rqworker
```

- [ ] **Step 6: Regenerate lock file and rebuild**

```bash
uv lock
just build
```

- [ ] **Step 7: Run all tests**

```bash
just test
```

Expected: all tests pass. No imports of `django_rq` remain in non-test application code.

- [ ] **Step 8: Run pre-commit**

```bash
pre-commit run --all-files
pre-commit run --all-files
```

Expected: both runs pass cleanly (second run confirms no auto-fix regressions).

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock config/settings/base.py \
        docker-compose.local.yml docker-compose.production.yml
git rm compose/local/django/start-rqworker \
       compose/production/django/start-rqworker
git commit -m "chore: remove django-rq, rq-scheduler, and rqworker Docker service"
```

---

## Task 14: Final Verification

- [ ] **Step 1: Run the full unit test suite**

```bash
just test
```

Expected: all tests pass, zero failures.

- [ ] **Step 2: Run E2E tests**

```bash
just test-e2e
```

Expected: all Playwright tests pass against the uvicorn-served app.

- [ ] **Step 3: Verify no remaining `django_rq` references in application code**

```bash
grep -r "django_rq" suchar_overflow/ --include="*.py" | grep -v __pycache__ | grep -v test
```

Expected: no output.

- [ ] **Step 4: Verify all views are async**

```bash
grep -rn "def get\|def post\|def dispatch" suchar_overflow/ --include="*.py" \
  | grep -v "async def" | grep -v __pycache__ | grep -v test | grep -v migrations \
  | grep -v "def get_success_url\|def get_object\|def get_redirect_url\|def get_form_class\|def get_template_names\|def _build_context\|def _get_suchar"
```

Expected: only sync helper methods remain (no HTTP handlers are sync).

- [ ] **Step 5: Final pre-commit run**

```bash
pre-commit run --all-files
pre-commit run --all-files
```

Expected: both runs clean.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: async Django migration complete — final verification"
```
