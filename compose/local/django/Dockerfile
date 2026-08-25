# define an alias for the specific python version used in this file.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS python

# Python build stage
FROM python AS python-build-stage

ARG APP_HOME=/app

WORKDIR ${APP_HOME}

# we need to move the virtualenv outside of the $APP_HOME directory because it will be overriden by the docker compose mount
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_HTTP_TIMEOUT=120

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  # psycopg dependencies
  libpq-dev \
  gettext \
  wait-for-it

# Requirements are installed here to ensure they will be cached.
# The bind mount target must be a bare path ("uv.lock"), not "uv.lock:rw" —
# BuildKit mounts the file at the literal path "uv.lock:rw" instead, so uv
# never actually saw a lockfile here and silently free-resolved (floating)
# versions instead of using the pinned ones (compose/production/django/Dockerfile
# already uses the bare-path form and does not have this bug). Harmless as long
# as nothing downstream depended on this step's resolved versions, but the
# Playwright install below now does — hence --locked, so a lock/pyproject
# mismatch fails the build loudly instead of silently floating.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project

# devcontainer dependencies and utils
# Installed unconditionally (not gated on VS Code Devcontainers use) because this
# Dockerfile is shared between plain `docker compose` local dev and the devcontainer —
# splitting it into two images isn't worth the added maintenance for a local-only image.
#
# Placed before COPY . ${APP_HOME} (and everything below it, including the Playwright
# install) so that changes to application source code don't invalidate these layers —
# none of them depend on the source tree, only on pyproject.toml/uv.lock, which are
# already pulled in above via bind mounts for `uv sync --no-install-project`.
RUN apt-get update && apt-get install --no-install-recommends -y \
  sudo git bash-completion nano ssh

# Create devcontainer user and add it to sudoers
RUN groupadd --gid 1000 dev-user \
  && useradd --uid 1000 --gid dev-user --shell /bin/bash --create-home dev-user \
  && echo dev-user ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/dev-user \
  && chmod 0440 /etc/sudoers.d/dev-user

ENV PATH="${APP_HOME}/.venv/bin:$PATH"
ENV PYTHONPATH="${APP_HOME}/.venv/lib/python3.14/site-packages"

# Install Playwright Chromium binary for E2E tests.
# --with-deps installs the required system libraries (libnss, libatk, etc.)
# Allow failure so the image builds when CDN is unreachable (e.g. restricted build networks).
# Invoked directly (not via `uv run`) because pyproject.toml/uv.lock aren't in the
# build context at this point (COPY . ${APP_HOME} hasn't run yet) — the playwright
# package itself is already installed into .venv by `uv sync --no-install-project`
# above (it's in the default "dev" dependency group), so the venv's bin (now first
# on PATH) is enough to resolve the CLI.
RUN playwright install --with-deps chromium || echo "Playwright browser install skipped (network unavailable)"

COPY . ${APP_HOME}

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

ENTRYPOINT ["/entrypoint"]
