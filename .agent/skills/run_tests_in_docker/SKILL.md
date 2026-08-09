---
name: run_tests_in_docker
description: How to correctly run the test suite in the Docker container
---

# Running Tests

When instructed to run tests for this project, always use the Docker container. This ensures environment consistency and access to the required services (like the database).

See CLAUDE.md's "Running commands" section for the full explanation of why unit
tests and Playwright E2E tests are two separate suites that must never be run
together with the same settings — this file only covers the concrete commands.

## Basic Commands

```bash
just test        # unit/integration tests (excludes E2E)
just test-e2e     # Playwright E2E tests only
just test-all     # unit tests then E2E, sequentially
```

**Never** run plain `docker compose ... run --rm django pytest` with no `-m`
filter — it collects E2E tests under `config.settings.test` and fails with CSRF
errors or missing browser fixtures. If the docker compose invocation must be
explicit rather than going through `just`, always include the marker filter:

```bash
docker compose -f docker-compose.local.yml run --rm django pytest -m "not e2e"
```

## Running Specific Tests

To run specific tests, files, or pass additional flags (like `-s` for stdout, or
`-v` for verbose), append them to `just test`:

```bash
# Run a specific test file
just test path/to/test_file.py

# Run a specific class or method
just test path/to/test_file.py::TestClass::test_method

# Run with verbose output and print statements
just test -v -s
```

## Core Rules
1. **Always use Docker:** Final verification and general test execution MUST happen inside the Docker environment.
2. **Always filter by marker:** unit tests exclude `e2e`, E2E runs select only `e2e` — see CLAUDE.md.
3. **Avoid local execution:** Do not run `pytest` locally (e.g., via `.venv`) unless it is a very specific, isolated unit test that requires zero database interaction (and even then, prefer Docker to avoid confusion).
4. **No prompts:** Do not ask the user for permission or confirmation on how to run tests; simply execute the commands above.
