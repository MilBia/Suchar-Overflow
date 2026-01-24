# Project Rules & Skills

## General Guidelines
- **Environment**: ALWAYS use the local `.venv` for Python context and tool execution where possible, but run the *application* and *tests* in Docker.
- **Docker**: The source of truth for the running application is Docker Compose (`docker-compose.local.yml`).
- **Pre-commit**: NEVER commit code without running `pre-commit run --all-files` and resolving all errors.

## Execution Rules
1. **Running Server**:
   - Use `docker compose up -d` to start.
   - Use `docker compose logs -f` to monitor.
   - Do NOT run `python manage.py runserver` locally; use Docker.

2. **Running Tests**:
   - Use `docker compose run --rm django pytest`.
   - Do NOT run `pytest` locally unless strictly necessary for quick debugging of non-DB logic, but final verification MUST be in Docker.

3. **Dependency Management**:
   - Project uses `uv`.
   - If adding requirements, update `pyproject.toml` and potentially rebuild the docker image (`docker compose build`).

4. **Code Style**:
   - Enforced by `ruff` and `djlint` via pre-commit.
   - Run `pre-commit run --all-files` frequently.

## Common commands map
- Start: `docker compose up -d --remove-orphans`
- Stop: `docker compose down`
- Build: `docker compose build`
- Logs: `docker compose logs -f`
- Backend Shell: `docker compose run --rm django python manage.py shell`
- DB Access: `docker compose run --rm postgres psql ...` (or check docker compose for creds)
