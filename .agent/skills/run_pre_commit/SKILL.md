---
name: run_pre_commit
description: How to run pre-commit locally using .venv, recreating it if missing
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

## Step 2: Fallback — recreate the local `.venv`
`pre-commit` is never installed inside the Docker `django` image (it lives in the
`local-tools` uv dependency group, deliberately excluded from the container — see
issue #215). If the local `.venv` does NOT exist or is broken, do NOT get stuck or
ask the user what to do — automatically recreate it:

```bash
uv sync --only-group local-tools
```

Use `--only-group`, not `--group` — `--group` also syncs the `dev` default group
and `[project.dependencies]`, which fails on a host without PostgreSQL headers
(`psycopg-c` needs `pg_config`). Then run:

```bash
.venv/bin/pre-commit run --all-files
```

## Summary of Rules
- **Local `.venv` only:** `pre-commit` does not exist inside the Docker container — there is no Docker fallback.
- **Do not prompt the user:** Automatically recreate the `.venv` with `uv sync --only-group local-tools` if it is missing or broken.
- **Fix issues:** If `pre-commit` fails because of lint/format errors, automatically fix the files and re-run (twice, per CLAUDE.md).
