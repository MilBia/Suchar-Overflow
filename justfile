export COMPOSE_FILE := "docker-compose.local.yml"

## Just does not yet manage signals for subprocesses reliably, which can lead to unexpected behavior.
## Exercise caution before expanding its usage in production environments.
## For more information, see https://github.com/casey/just/issues/2473 .


# Default command to list all available commands.
default:
    @just --list

# build: Build python image.
build *args:
    @echo "Building python image..."
    @docker compose build {{args}}

# up: Start up containers.
up:
    @echo "Starting up containers..."
    @docker compose up -d --remove-orphans

# down: Stop containers.
down:
    @echo "Stopping containers..."
    @docker compose down

# prune: Remove containers and their volumes.
prune *args:
    @echo "Killing containers and removing volumes..."
    @docker compose down -v {{args}}

# logs: View container logs
logs *args:
    @docker compose logs -f {{args}}

# manage: Executes `manage.py` command.
manage +args:
    @docker compose run --rm django python ./manage.py {{args}}

# test: Run pytest inside the Django container.
test *args:
    @docker compose run --rm django pytest {{args}}

# test-e2e: Run Playwright E2E tests inside the Django container.
# Requires the DB to be up (`just up` first).
test-e2e *args:
    @docker compose run --rm django pytest \
        --override-ini="addopts=--ds=config.settings.e2e --import-mode=importlib" \
        -m e2e \
        tests/e2e/ {{args}}

# test-all: Run unit tests then E2E tests sequentially.
test-all:
    @just test
    @just test-e2e

# fill-translations: Fill empty .po translation strings using a local AI model.
# Example: just fill-translations --url http://localhost:11434/v1 --model translategemma --language pl
fill-translations *args:
    @docker compose run --rm django python ./manage.py fill_translations {{args}}

# ---------- Production ----------

# prod-build: Build production images.
prod-build *args:
    @echo "Building production images..."
    @docker compose -f docker-compose.production.yml build {{args}}

# prod-up: Start production containers.
prod-up:
    @echo "Starting production containers..."
    @docker compose -f docker-compose.production.yml up -d --remove-orphans

# prod-down: Stop production containers.
prod-down:
    @echo "Stopping production containers..."
    @docker compose -f docker-compose.production.yml down

# prod-logs: View production container logs.
prod-logs *args:
    @docker compose -f docker-compose.production.yml logs -f {{args}}

# prod-manage: Executes `manage.py` command in production.
prod-manage +args:
    @docker compose -f docker-compose.production.yml run --rm django python ./manage.py {{args}}
