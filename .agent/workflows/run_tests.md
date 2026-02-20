---
description: Run tests inside the Docker container to ensure environment consistency.
---

1. Run all tests using pytest inside the django container:
// turbo
   ```bash
   docker compose -f docker-compose.local.yml run --rm django pytest
   ```

2. To run specific tests, append the path:
   ```bash
   docker compose -f docker-compose.local.yml run --rm django pytest path/to/test.py
   ```
