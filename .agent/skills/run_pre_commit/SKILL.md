---
name: run_pre_commit
description: How to run pre-commit locally using .venv or fallback to Docker
---

# Running pre-commit

CLAUDE.md's "Running pre-commit" section is the source of truth: pre-commit runs in
the local `.venv`, not inside the Docker container — run
`pre-commit run --all-files`, then run it a second time to confirm all hooks pass
after auto-fixes. This file only adds the `.agent`-specific fallback procedure below.

## Step 1: Check for a local virtual environment (`.venv`)
Verify a local `.venv` directory exists in the project root with the `pre-commit`
executable (e.g., `.venv/bin/pre-commit`), then run:

```bash
.venv/bin/pre-commit run --all-files
```

## Step 2: Fallback to Docker
If the local `.venv` does NOT exist or is broken, do NOT get stuck or ask the user
what to do — automatically fall back to running `pre-commit` inside the Docker
`django` service:

```bash
docker compose -f docker-compose.local.yml run --rm django pre-commit run --all-files
```

## Summary of Rules
- **Speed first:** The local `.venv` is preferred because it is faster.
- **Guaranteed execution:** Docker is your guaranteed fallback. If `.venv` is missing, immediately use Docker.
- **Do not prompt the user:** Automatically switch to the Docker fallback if the local execution is impossible.
- **Fix issues:** If `pre-commit` fails because of lint/format errors, automatically fix the files and re-run (twice, per CLAUDE.md).
