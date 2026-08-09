# Project Rules & Skills

`CLAUDE.md` at the repo root is the source of truth for commands, workflow steps,
and code style rules. This file only adds `.agent/`-specific reminders that aren't
already spelled out there.

## General Guidelines
- **Environment**: ALWAYS use the local `.venv` for pre-commit, but run the
  *application* and *tests* in Docker (see CLAUDE.md "Running commands").
- **Docker**: The source of truth for the running application is Docker Compose
  (`docker-compose.local.yml`). Commands run outside a `just` recipe need the
  explicit `-f docker-compose.local.yml` flag — `just` sets `COMPOSE_FILE` for you,
  a bare shell does not.
- **Pre-commit**: NEVER commit code without running `pre-commit run --all-files` and
  resolving all errors (see CLAUDE.md "Running pre-commit").

## Execution Rules
1. **Running Server**:
   - Use `just up` (or `docker compose -f docker-compose.local.yml up -d
     --remove-orphans`) to start.
   - Use `just logs` (or `docker compose -f docker-compose.local.yml logs -f`) to
     monitor.
   - Do NOT run `python manage.py runserver` locally; use Docker.

2. **Running Tests**:
   - See CLAUDE.md "Running commands": `just test` for unit/integration tests,
     `just test-e2e` for Playwright. Never run plain `pytest` with no `-m` filter —
     it collects E2E tests under the wrong settings and fails with CSRF errors.

3. **Dependency Management**:
   - See CLAUDE.md "Dependency management" (`uv add`, `uv lock`, `uv sync`,
     `just build`).

4. **Code Style**:
   - See CLAUDE.md "Code style — ruff rules in force".

## Common commands map
- Start: `just up`
- Stop: `just down`
- Build: `just build`
- Logs: `just logs`
- Backend Shell: `docker compose -f docker-compose.local.yml run --rm django python manage.py shell`
- DB Access: `docker compose -f docker-compose.local.yml run --rm postgres psql ...`
  (credentials in `.envs/.local/.postgres`)
