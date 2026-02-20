---
name: run_tests_in_docker
description: How to correctly run the test suite in the Docker container
---

# Running Tests

When instructed to run tests for this project, always use the Docker container. This ensures environment consistency and access to the required services (like the database).

## Basic Command

The standard command to execute the test suite is:

```bash
docker compose -f docker-compose.local.yml run --rm django pytest
```

## Running Specific Tests

To run specific tests, files, or pass additional flags (like `-s` for stdout, or `-v` for verbose), simply append them to the base command:

```bash
# Run a specific test file
docker compose -f docker-compose.local.yml run --rm django pytest path/to/test_file.py

# Run a specific class or method
docker compose -f docker-compose.local.yml run --rm django pytest path/to/test_file.py::TestClass::test_method

# Run with verbose output and print statements
docker compose -f docker-compose.local.yml run --rm django pytest -v -s
```

## Core Rules
1. **Always use Docker:** Final verification and general test execution MUST happen inside the Docker environment.
2. **Avoid local execution:** Do not run `pytest` locally (e.g., via `.venv`) unless it is a very specific, isolated unit test that requires zero database interaction (and even then, prefer Docker to avoid confusion).
3. **No prompts:** Do not ask the user for permission or confirmation on how to run tests; simply execute the Docker command above.
