---
description: Run tests inside the Docker container to ensure environment consistency.
---

1. Run the unit/integration suite (excludes E2E) inside the django container:
// turbo
   ```bash
   just test
   ```
   Never run plain `pytest` without a `-m` marker filter — see CLAUDE.md's
   "Unit tests vs E2E tests" section for why that collects E2E tests under the
   wrong settings and fails with CSRF/fixture errors.

2. To run specific tests, append the path:
   ```bash
   just test path/to/test.py
   ```

3. To run the Playwright E2E suite instead, use `just test-e2e` (separate settings,
   see CLAUDE.md).
