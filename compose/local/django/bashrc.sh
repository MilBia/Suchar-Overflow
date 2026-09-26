
# --- Suchar Overflow: DATABASE_URL for interactive `docker exec` shells (#404) ---
# DATABASE_URL is assembled from POSTGRES_* by /entrypoint, which only runs for the
# container's main process and `docker compose run` — `docker exec ... bash` skips
# it, so every manage.py command in such a shell died with ImproperlyConfigured.
# Debian's /etc/bash.bashrc returns early for non-interactive shells, so this only
# covers interactive ones; `docker exec ... python manage.py` (no shell) still needs
# `just shell` / `just bash` / `just manage`.
#
# The DSN is computed in a child bash rather than by `source /entrypoint` here:
# the entrypoint enables errexit/nounset/pipefail, and any failure under errexit
# during shell startup would kill the interactive shell. Reusing the entrypoint
# (its BASH_SOURCE gate skips the blocking wait-for-it part when sourced) keeps the
# credential URL-encoding in one place. An empty result is not exported — an empty
# DATABASE_URL fails more confusingly than a missing one.
if [ -z "${DATABASE_URL:-}" ] && [ -n "${POSTGRES_HOST:-}" ] && [ -r /entrypoint ]; then
    _suchar_dsn="$(bash -c 'source /entrypoint && printf %s "${DATABASE_URL}"' 2>/dev/null)"
    if [ -n "${_suchar_dsn}" ]; then
        export DATABASE_URL="${_suchar_dsn}"
        export POSTGRES_USER="${POSTGRES_USER:-postgres}"
    fi
    unset _suchar_dsn
fi
