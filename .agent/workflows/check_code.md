---
description: Run pre-commit checks to ensure code quality and style before committing.
---

Per CLAUDE.md's "Running pre-commit" section, pre-commit runs in the local `.venv`,
not inside Docker.

1. Run pre-commit on all files using the local environment:
// turbo
   ```bash
   .venv/bin/pre-commit run --all-files
   ```
   *(Fallback if `.venv` is missing or broken — see `run_pre_commit` skill: recreate it with `uv sync --only-group local-tools`, then rerun the command above. `pre-commit` is not installed inside the Docker container.)*

2. If there are failures, review the changes. Many hooks (like ruff) will auto-fix issues.
3. If manual fixes are required, apply them and re-run the command to verify — per
   CLAUDE.md, always run a second time to confirm all hooks pass cleanly.
