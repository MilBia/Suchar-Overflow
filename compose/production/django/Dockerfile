
# uv from its own pinned image, Python from the official one — see the note in
# compose/local/django/Dockerfile (#431: astral's python3.14-bookworm tag froze at
# 3.14.2). Both stages then share the same interpreter the bytecode is built for,
# and the same Debian release (glibc) the venv's C extensions are built against —
# keep both FROM lines on one tag (#437, tests/test_python_runtime.py).
FROM ghcr.io/astral-sh/uv:0.12.21 AS uv

FROM docker.io/python:3.14-slim-trixie AS python-build-stage
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

ARG APP_HOME=/app

WORKDIR ${APP_HOME}

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  # psycopg dependencies
  libpq-dev


# Requirements are installed here to ensure they will be cached.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . ${APP_HOME}

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev

# Python 'run' stage
FROM docker.io/python:3.14-slim-trixie AS python-run-stage

ARG APP_HOME=/app

WORKDIR ${APP_HOME}

RUN addgroup --system django \
  && adduser --system --ingroup django django


# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
  # psycopg dependencies
  libpq-dev \
  # Translations dependencies
  gettext \
  # entrypoint
  wait-for-it \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*


COPY --chown=django:django ./compose/base/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint


COPY --chown=django:django ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

# Copy the application from the builder
COPY --from=python-build-stage --chown=django:django ${APP_HOME} ${APP_HOME}

# WORKDIR (/app) is created root-owned by the WORKDIR instruction above; the build
# stage's COPY --chown only owns the *copied* tree, not /app itself. django must
# own /app so `start` can create STATIC_ROOT (/app/staticfiles, absent from the
# image) and the compress cache at runtime. Pre-create both runtime-writable dirs
# in the same layer so they land django-owned too — media/ especially, since its
# named volume (docker-compose.production.yml) seeds ownership from this dir.
RUN mkdir -p ${APP_HOME}/suchar_overflow/media ${APP_HOME}/staticfiles \
  && chown django:django ${APP_HOME} ${APP_HOME}/suchar_overflow/media ${APP_HOME}/staticfiles

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

USER django

# --ignore=.venv: compilemessages walks every `locale` dir under cwd, including
# the installed packages' own (already compiled) catalogs in /app/.venv.
# Settings import needs DATABASE_URL present (even empty, so base.py doesn't
# fall back to POSTGRES_*) and REDIS_URL set (no default since #453); neither is
# connected to here.
RUN DATABASE_URL="" \
  REDIS_URL="" \
  DJANGO_SETTINGS_MODULE="config.settings.test" \
  python manage.py compilemessages --ignore=.venv

ENTRYPOINT ["/entrypoint"]
