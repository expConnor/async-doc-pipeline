# Setup CLI Design

**Date:** 2026-07-31

## Goal

This is the first of three planned subsystems supporting extreme-load testing of the pipeline (the other two — a load generator and a monitoring/observability layer — are separate, later designs). This subsystem gives a fresh clone of the repo a clean, one-command path from `git clone` to "ready to hammer with load": apply migrations, and provision one or many accounts with API keys.

In scope:

- `cli/` — a Typer-based Python CLI holding the actual logic (account creation, batch provisioning, running migrations).
- `Makefile` — the front-door interface. Every target is a thin wrapper that shells out to `poetry run python -m cli.main ...`. This is the only interface a new clone needs to discover (`make help`).
- Single account creation (`account create`), replacing the ad hoc `local/create_account.py` script.
- Bulk account creation (`account create-batch --count N --out <path>`) for provisioning many API keys at once, since simulating extreme load means many concurrent simulated clients, not one.
- Environment bootstrap (`setup`): runs Alembic migrations programmatically and creates one default account, so a fresh clone is fully usable after one command.

Out of scope (explicit non-goals):

- Documents and jobs stay out of this CLI entirely. Those already have API endpoints (`POST /documents`, `POST /documents/{id}/process`, `GET /jobs/{id}`) and will be driven through Postman instead.
- `local/create_document.py`, `local/upload_file.py`, `local/process_document.py` are untouched by this work. Whether to retire them in favor of Postman is a separate decision (see Open Questions).
- The load generator and monitoring/observability subsystems. Referenced here only as context for why bulk account provisioning matters.
- MinIO bucket creation — already handled automatically by the `createbuckets` service in `docker-compose.yml`; `setup` does not need to touch storage.

## Design Decisions

### 1. Makefile front door, Typer CLI underneath

Considered three shapes: pure Makefile (bash/psql for everything), pure Typer CLI (`poetry run python -m cli.main ...` as the only interface), and this hybrid.

Pure Makefile breaks down for batch account provisioning — looping N times, hashing each key, and inserting rows via SQLAlchemy is real program logic that's fragile to express in bash. Pure Typer works but means the very first command a reviewer runs after cloning is `poetry run python -m cli.main setup`, which is more to type and more to explain than a portfolio project's first impression should require.

The hybrid keeps the polished, zero-explanation surface (`make setup`, `make seed COUNT=50`) as the front door, with `make help` self-documenting every target via the standard `target: ## description` grep convention. The actual logic — DB writes, hashing, migration invocation — lives in real, independently-runnable Python under `cli/`, not in Makefile recipes.

### 2. Command surface: `account create`, `account create-batch`, and a top-level `setup`

`account` is a Typer sub-app (a "noun") because there are multiple account operations. `setup` is a top-level command, not nested under a noun — it's a single bootstrap action, not an operation on a resource.

`cli/main.py` wires it together:

```python
import typer

from cli.commands import account, bootstrap

app = typer.Typer(help="Admin/dev CLI for doc-pipeline.")
app.add_typer(account.app, name="account")
app.command("setup")(bootstrap.setup)
```

### 3. Bulk key output goes to a file, not stdout

`account create-batch --count N --out accounts.csv` writes `account_id,api_key` rows to a CSV. Only a summary ("created 50 accounts, wrote accounts.csv") prints to the terminal. Two reasons: dumping 50+ raw API keys to a terminal is bad practice (secrets in scrollback/history), and a future load generator needs a file it can read many keys from programmatically, not something to scrape off stdout.

Default `--out` path: `accounts.csv` in the current working directory. `--count` must be a positive integer; Typer rejects non-positive values with a usage error before touching the DB.

### 4. Migrations run via Alembic's Python API, not a subprocess

`setup` calls Alembic's `command.upgrade(config, "head")` directly (in-process), not `subprocess.run(["alembic", "upgrade", "head"])`. In-process means Alembic's own exceptions propagate naturally with Python tracebacks, no shell quoting/escaping concerns, and no assumption that an `alembic` binary is on `PATH` inside whatever environment `cli/` runs in — only that `alembic` is an installed dependency (it already is, see `pyproject.toml`'s main dependency group).

### 5. `package-mode = false` stays as-is

No console-script entry point. `cli/` is invoked as `poetry run python -m cli.main <command>` — the Makefile is what hides this from a first-time user, so there's no need to change how Poetry packages the project just for a nicer bare command name.

## Components

```
cli/
├── main.py                 # Typer root app; wires account + setup
└── commands/
    ├── account.py           # `account create`, `account create-batch`
    └── bootstrap.py         # `setup` (migrations + default account)

Makefile                     # setup, seed, migrate, help targets
```

### `cli/commands/account.py`

- `create()` — ported directly from `local/create_account.py`: generates a key with `secrets.token_urlsafe(32)`, hashes with `hashlib.sha256(...).hexdigest()` (matching `api/services/account.py:18` exactly), inserts one `Account` row via `shared.core.config.get_settings()` + SQLAlchemy async session, prints the account id and raw key once.
- `create_batch(count: int, out: Path = Path("accounts.csv"))` — same generation/hashing logic in a loop, bulk-inserts, writes results to the CSV at `out`, prints a one-line summary.

### `cli/commands/bootstrap.py`

- `setup()` — runs `alembic.command.upgrade(cfg, "head")` against an `alembic.config.Config` pointed at the repo's `alembic.ini`, then calls the same account-creation function `account.py` exposes, so `make setup` leaves you with a ready DB and one usable API key.

### `Makefile`

```makefile
.PHONY: setup seed migrate help

setup:       ## Bootstrap a fresh clone: migrate + create default account
	poetry run python -m cli.main setup

seed:        ## Bulk-create accounts. Usage: make seed COUNT=50
	poetry run python -m cli.main account create-batch --count $(COUNT)

migrate:     ## Apply Alembic migrations only (setup already includes this)
	poetry run python -m cli.main migrate

help:        ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "%-15s %s\n", $$1, $$2}'
```

`migrate` as a standalone target implies `cli.main` needs a bare `migrate` command in addition to `setup` (so it can be run independently, e.g. after pulling new migrations without wanting a new account). This is a small addition to `bootstrap.py`: expose the migration step as its own Typer command, and have `setup` call it internally rather than duplicating the Alembic invocation.

## Phases

**Phase 1 — CLI foundation + single account creation.** Add `typer` to `pyproject.toml`. Create `cli/main.py` and `cli/commands/account.py` with `create()` only, ported from `local/create_account.py`. Confirms the Typer wiring and `python -m cli.main` invocation work end to end before building anything on top.

**Phase 2 — Mass account provisioning.** Add `create_batch()` to `cli/commands/account.py` and wire it into `cli/main.py`.

**Phase 3 — Environment bootstrap.** Add `cli/commands/bootstrap.py` with a standalone `migrate` command and a `setup` command that calls `migrate` then `account.create`. Wire both into `cli/main.py`.

**Phase 4 — Makefile front door.** Add the `Makefile` with `setup`, `seed`, `migrate`, `help` targets, each delegating to the corresponding `cli.main` command.

## Error Handling

No new exception hierarchy — this is dev/ops tooling, not request-handling code, so it doesn't need to fit `shared/core/exceptions.py`'s `AppException` hierarchy. Failures surface directly:

- Migration failure in `setup`/`migrate`: Alembic's own exception propagates with its traceback; the command exits non-zero. No swallowing.
- `create_batch` with `--count <= 0`: rejected by Typer as a usage error before any DB connection is opened.
- DB connection failure (e.g., forgetting `POSTGRES_HOST=localhost` when running outside Docker): the raw `asyncpg`/SQLAlchemy connection error surfaces as-is. Not worth wrapping for a local dev tool.

## Testing

No inline tests during implementation, consistent with deferring test-writing to the end of the project. Each phase gets a manual smoke check instead: Phase 1/2 — run the command, confirm the DB row(s) and/or CSV file. Phase 3 — run `setup` against a fresh empty database, confirm migrations apply and an account is created. Phase 4 — run each `make` target from a clean shell.

## Open Questions

- Whether to retire `local/create_document.py` / `upload_file.py` / `process_document.py` now that Postman covers that interaction, or leave them alongside this CLI. Deferred — not blocking this work.
- Whether `create_batch`'s CSV should include a header row (`account_id,api_key`) — small enough to decide during implementation.

## Future Work

- **Load generator** — a separate tool to drive concurrent traffic against the pipeline using the bulk-provisioned accounts from `account create-batch`. Own design.
- **Monitoring/observability** — dashboards/metrics for queue depth, job latency, failure rates, worker throughput under load. Own design. (Connor's own notes in `docs/setup.md` already sketch the four Golden Signals to track: p99 latency, RPS/queue throughput, DLQ+5xx+failure-rate errors, queue-growth+CPU+RDS-connection saturation.)
- **Console-script entry point** — if `package-mode` ever changes for unrelated reasons, revisit giving the CLI a bare installed command name instead of `python -m cli.main`.
