---
name: run_pre_commit
description: How to run pre-commit locally using .venv or fallback to Docker
---

# Running pre-commit

When you need to run `pre-commit` (e.g., before committing code or to check formatting/linting), always follow these steps in order to ensure it runs correctly. Do not ask the user for reminders about this; this is your standard operating procedure.

## Step 1: Check for a local virtual environment (`.venv`)
First, verify if a local `.venv` directory exists in the project root.

## Step 2: Run using local `.venv` (Preferred)
If the `.venv` directory exists and has the `pre-commit` executable (e.g., `.venv/bin/pre-commit`), run it locally using the environment's executable:

```bash
.venv/bin/pre-commit run --all-files
```

Alternatively, if the project uses `uv` and it manages the environment, you can run:
```bash
uv run pre-commit run --all-files
```

## Step 3: Fallback to Docker
If the local `.venv` does NOT exist, is broken, or `pre-commit` is not installed locally, do NOT get stuck or ask the user what to do. Automatically fallback to running `pre-commit` inside the Docker container.

Project rules state that the application runs in Docker. You can run `pre-commit` using the `django` service (or the main application service defined in Docker Compose):

```bash
docker compose -f docker-compose.local.yml run --rm django pre-commit run --all-files
```
*(Adjust the service name from `django` if your `docker-compose.local.yml` uses a different name).*

## Summary of Rules
- **Speed first:** The local `.venv` is preferred because it is faster.
- **Guaranteed execution:** Docker is your guaranteed fallback. If `.venv` is missing, immediately use Docker.
- **Do not prompt the user:** Automatically switch to the Docker fallback if the local execution is impossible.
- **Fix issues:** If `pre-commit` fails because of lint/format errors, automatically fix the files and re-run.
