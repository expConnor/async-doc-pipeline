.PHONY: setup seed migrate nuke test lint format help

# Default so bare `make seed` is valid, not a Typer usage error.
COUNT ?= 1

setup:       ## Bootstrap a fresh clone (or post-nuke state): deps, .env, stack, migrations, default account, git hooks
	poetry install
	cp -n .env.example .env
	docker compose up -d --wait
	poetry run python -m cli.main setup
	poetry run pre-commit install

seed:        ## Bulk-create accounts. Usage: make seed COUNT=50
	poetry run python -m cli.main account create --count $(COUNT)

migrate:     ## Apply Alembic migrations only (setup already includes this)
	poetry run python -m cli.main migrate

nuke:        ## Wipe local dev state: delete accounts.csv, destroy & restart Docker volumes fresh
	rm -f local/accounts.csv
	docker compose down -v
	docker compose up -d --wait

test:        ## Run the test suite
	poetry run pytest

lint:        ## Check code style
	poetry run ruff check .

format:      ## Auto-format code
	poetry run ruff format .

help:        ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "%-15s %s\n", $$1, $$2}'
