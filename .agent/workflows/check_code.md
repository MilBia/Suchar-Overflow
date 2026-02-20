---
description: Run pre-commit checks to ensure code quality and style before committing.
---

1. Run pre-commit on all files using local environment:
// turbo
   ```bash
   uv run pre-commit run --all-files
   ```
   *(Fallback: if fails, use `docker compose -f docker-compose.local.yml run --rm django pre-commit run --all-files`)*

2. If there are failures, review the changes. Many hooks (like ruff) will auto-fix issues.
3. If manual fixes are required, apply them and re-run the command to verify.
