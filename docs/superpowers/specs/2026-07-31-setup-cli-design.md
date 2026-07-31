# Setup CLI Design

**Date:** 2026-07-31

## Goal

This is the first of three planned subsystems supporting extreme-load testing of the pipeline (the other two — a load generator and a monitoring/observability layer — are separate, later designs). This subsystem gives a fresh clone of the repo a clean, one-command path from `git clone` to "ready to hammer with load": apply migrations, and provision one or many accounts with API keys.

In scope:

- `cli/` — a Typer-based Python CLI holding the actual logic (account creation, running migrations).
- `Makefile` — the front-door interface. Every target is a thin wrapper that shells out to `poetry run python -m cli.main ...`. This is the only interface a new clone needs to discover (`make help`).
- One account-creation command, `account create --count N` (default `N=1`), replacing the ad hoc `local/create_account.py` script and covering both the single-account and bulk-provisioning cases with a single implementation. Bulk provisioning matters because simulating extreme load means many concurrent simulated clients, not one.
- Environment bootstrap (`setup`): runs Alembic migrations programmatically and creates one default account (`count=1`), so a fresh clone is fully usable after one command.
- Environment wipe (`make nuke`): a pure Makefile target (no Python) that deletes `local/accounts.csv` and runs `docker compose down -v && docker compose up -d`, so repeated load-test cycles have a one-command way back to an empty, freshly-started stack.

Out of scope (explicit non-goals):

- Documents and jobs stay out of this CLI entirely. Those already have API endpoints (`POST /documents`, `POST /documents/{id}/process`, `GET /jobs/{id}`) and will be driven through Postman instead.
- `local/create_document.py`, `local/upload_file.py`, `local/process_document.py` are untouched by this work. Whether to retire them in favor of Postman is a separate decision (see Open Questions).
- The load generator and monitoring/observability subsystems. Referenced here only as context for why bulk account provisioning matters.
- MinIO bucket creation — already handled automatically by the `createbuckets` service in `docker-compose.yml`; `setup` does not need to touch storage.
- A DB-only reset command (truncating tables in-process) was considered and dropped: `docker compose down -v` already wipes Postgres/MinIO/RabbitMQ volumes in one shot, so a separate Python/SQL reset path would just be a worse version of a command that already exists. `make nuke` does not re-run `setup` afterward — it stops right after the containers restart, leaving an empty unmigrated DB; running `make setup` again is a deliberate separate step.

## Design Decisions

### 1. Makefile front door, Typer CLI underneath

Considered three shapes: pure Makefile (bash/psql for everything), pure Typer CLI (`poetry run python -m cli.main ...` as the only interface), and this hybrid.

Pure Makefile breaks down for batch account provisioning — looping N times, hashing each key, and inserting rows via SQLAlchemy is real program logic that's fragile to express in bash. Pure Typer works but means the very first command a reviewer runs after cloning is `poetry run python -m cli.main setup`, which is more to type and more to explain than a portfolio project's first impression should require.

The hybrid keeps the polished, zero-explanation surface (`make setup`, `make seed COUNT=50`) as the front door, with `make help` self-documenting every target via the standard `target: ## description` grep convention. The actual logic — DB writes, hashing, migration invocation — lives in real, independently-runnable Python under `cli/`, not in Makefile recipes.

### 2. Command surface: one `account create --count N`, and a top-level `setup`

Originally scoped as two commands (`account create` for one account, `account create-batch` for many) — collapsed into one: `account create --count N`, defaulting to `N=1`. There's no meaningful difference between "create one account" and "create N accounts" other than the loop bound, so two commands would just mean two copies of the same hashing/insert logic to keep in sync. `setup` doesn't shell out to this command at all — it imports and calls the same underlying function directly with `count=1`, so there's exactly one code path for account creation, used by both entry points.

`account` is still a Typer sub-app (a "noun") in case other account operations show up later. `setup` is a top-level command, not nested under a noun — it's a single bootstrap action, not an operation on a resource.

`cli/main.py` wires it together:

```python
import typer

from cli.commands import account, bootstrap

app = typer.Typer(help="Admin/dev CLI for doc-pipeline.")
app.add_typer(account.app, name="account")
app.command("setup")(bootstrap.setup)
```

### 3. Key output goes to a file, and it's a running ledger (append, not overwrite)

`account create --count N --out local/accounts.csv` writes `account_id,api_key` rows to a CSV. Only a summary ("created N accounts, wrote to local/accounts.csv") prints to the terminal. Two reasons: dumping raw API keys to a terminal is bad practice (secrets in scrollback/history), and a future load generator needs a file it can read many keys from programmatically, not something to scrape off stdout.

`accounts.csv` accumulates across every invocation rather than being overwritten each time: `make setup` creates account #1 and writes it, and a later `make seed COUNT=50` appends 50 more rows on top rather than clobbering the file. Concretely: if `--out` doesn't exist yet, write the header row (`account_id,api_key`) then the new rows; if it already exists, open in append mode and write only the new data rows (no repeated header). This makes the file a cumulative record of every account this CLI has ever provisioned, which is what you want for a load-testing pool of keys built up over multiple setup/seed runs.

Default `--out` path: `local/accounts.csv`, not a repo-root path. `local/` is already fully gitignored (`.gitignore:61`), so this file — which holds raw API keys — can never accidentally get committed, matching how this repo already treats `.env` (real secrets gitignored, `.env.example` as the safe checked-in template). `--count` must be a positive integer; Typer rejects non-positive values with a usage error before touching the DB.

Since `accounts.csv` accumulates, it goes stale the moment the DB it describes is wiped (e.g. via `make nuke`) — the account IDs it lists no longer exist afterward. `make nuke` deletes the file for exactly this reason (see Design Decision 6), so a fresh `local/accounts.csv` is only ever in sync with a DB that's actually running.

### 4. Migrations run via Alembic's Python API, not a subprocess

`setup` calls Alembic's `command.upgrade(config, "head")` directly (in-process), not `subprocess.run(["alembic", "upgrade", "head"])`. In-process means Alembic's own exceptions propagate naturally with Python tracebacks, no shell quoting/escaping concerns, and no assumption that an `alembic` binary is on `PATH` inside whatever environment `cli/` runs in — only that `alembic` is an installed dependency (it already is, see `pyproject.toml`'s main dependency group).

### 5. `package-mode = false` stays as-is

No console-script entry point. `cli/` is invoked as `poetry run python -m cli.main <command>` — the Makefile is what hides this from a first-time user, so there's no need to change how Poetry packages the project just for a nicer bare command name.

### 6. `nuke` is Make-only — no corresponding Typer/Python command

Every other Makefile target wraps a `cli.main` command; `nuke` doesn't, on purpose. Its two operations — deleting a local file and cycling `docker compose` — are both already single shell commands with nothing worth expressing in Python (no loop, no hashing, no DB session). Adding a `cli.main nuke` layer here would just be indirection around commands that are already this simple and this discoverable. `setup`/`migrate`/`account create` earn a Python layer because they have real logic (hashing, bulk insert, Alembic API calls); `nuke` doesn't.

Naming: `setup` (not `bootstrap`) for the "get this project into a usable state" command, and `nuke` for the destructive wipe. `setup` matches the closest common precedent (Rails' `bin/setup` — migrate + seed a fresh DB) and reads as the broader, more complete operation; `bootstrap`, where it's used in Makefile conventions elsewhere, usually refers to something narrower like installing dependencies. `nuke` is an established colloquialism for "destroy and start clean," and — unlike a blander name like `clean` or `reset` — it reads as appropriately alarming for a command that deletes local data and Docker volumes.

## Components

```
cli/
├── main.py                 # Typer root app; wires account + setup
└── commands/
    ├── account.py           # `account create --count N`
    └── bootstrap.py         # `setup`, `migrate`

Makefile                     # setup, seed, migrate, nuke, help targets
```

### `cli/commands/account.py`

- `_create_accounts(count: int, out: Path) -> None` — the one implementation. Loops `count` times generating a key with `secrets.token_urlsafe(32)` and hashing with `hashlib.sha256(...).hexdigest()` (matching `api/services/account.py:18` exactly), bulk-inserts the `Account` rows via `shared.core.config.get_settings()` + SQLAlchemy async session, then appends `account_id,api_key` rows to `out` (writing the header first only if the file is new — see Design Decision 3). Prints a one-line summary, not the keys themselves.
- `create(count: int = 1, out: Path = Path("local/accounts.csv"))` — the Typer command (`account create`), a thin wrapper calling `_create_accounts`.
- `bootstrap.py`'s `setup()` calls `_create_accounts(count=1, out=Path("local/accounts.csv"))` directly — same function, not a subprocess or recursive CLI invocation.

### `cli/commands/bootstrap.py`

- `migrate()` — runs `alembic.command.upgrade(cfg, "head")` against an `alembic.config.Config` pointed at the repo's `alembic.ini`. Exposed as its own Typer command (`migrate`) so it can be run standalone after pulling new migrations.
- `setup()` — calls `migrate()` then `account._create_accounts(count=1, out=Path("local/accounts.csv"))`, so `make setup` leaves you with a migrated DB and one usable API key.

### `Makefile`

```makefile
.PHONY: setup seed migrate nuke help

setup:       ## Bootstrap a fresh clone (or post-nuke state): migrate + create default account
	poetry run python -m cli.main setup

seed:        ## Bulk-create accounts. Usage: make seed COUNT=50
	poetry run python -m cli.main account create --count $(COUNT)

migrate:     ## Apply Alembic migrations only (setup already includes this)
	poetry run python -m cli.main migrate

nuke:        ## Wipe local dev state: delete accounts.csv, destroy & restart Docker volumes fresh
	rm -f local/accounts.csv
	docker compose down -v
	docker compose up -d

help:        ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "%-15s %s\n", $$1, $$2}'
```

## Phases

**Phase 1 — CLI foundation + account creation.** Add `typer` to `pyproject.toml`. Create `cli/main.py` and `cli/commands/account.py` with `_create_accounts()` and the `create --count N` command, ported and generalized from `local/create_account.py`. Confirms the Typer wiring, the append-to-CSV behavior, and `python -m cli.main` invocation all work before building anything on top.

**Phase 2 — Environment bootstrap.** Add `cli/commands/bootstrap.py` with `migrate()` and `setup()` (calls `migrate()` then `account._create_accounts(count=1, ...)`). Wire both into `cli/main.py`.

**Phase 3 — Makefile front door.** Add the `Makefile` with `setup`, `seed`, `migrate`, `help` targets (each delegating to the corresponding `cli.main` command) and `nuke` (pure shell, no `cli.main` involvement).

## Error Handling

No new exception hierarchy — this is dev/ops tooling, not request-handling code, so it doesn't need to fit `shared/core/exceptions.py`'s `AppException` hierarchy. Failures surface directly:

- Migration failure in `setup`/`migrate`: Alembic's own exception propagates with its traceback; the command exits non-zero. No swallowing.
- `account create` with `--count <= 0`: rejected by Typer as a usage error before any DB connection is opened.
- DB connection failure (e.g., forgetting `POSTGRES_HOST=localhost` when running outside Docker): the raw `asyncpg`/SQLAlchemy connection error surfaces as-is. Not worth wrapping for a local dev tool.

## Testing

No inline tests during implementation, consistent with deferring test-writing to the end of the project. Each phase gets a manual smoke check instead: Phase 1 — run `account create` and `account create --count 5`, confirm the DB rows and that `local/accounts.csv` has a single header and the right number of appended rows across both runs. Phase 2 — run `setup` against a fresh empty database, confirm migrations apply and one account is appended to `local/accounts.csv`. Phase 3 — run each `make` target from a clean shell, including `make nuke` followed by `make setup` to confirm the full wipe-and-rebuild cycle works.

## Open Questions

- Whether to retire `local/create_document.py` / `upload_file.py` / `process_document.py` now that Postman covers that interaction, or leave them alongside this CLI. Deferred — not blocking this work.

## Future Work

- **Load generator** — a separate tool to drive concurrent traffic against the pipeline using the pool of accounts accumulated in `local/accounts.csv`. Own design.
- **Monitoring/observability** — dashboards/metrics for queue depth, job latency, failure rates, worker throughput under load. Own design. (Connor's own notes in `docs/setup.md` already sketch the four Golden Signals to track: p99 latency, RPS/queue throughput, DLQ+5xx+failure-rate errors, queue-growth+CPU+RDS-connection saturation.)
- **Console-script entry point** — if `package-mode` ever changes for unrelated reasons, revisit giving the CLI a bare installed command name instead of `python -m cli.main`.
