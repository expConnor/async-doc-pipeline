# Setup CLI Design

**Date:** 2026-07-31

## Goal

This is the first of three planned subsystems supporting extreme-load testing of the pipeline (the other two — a load generator and a monitoring/observability layer — are separate, later designs). This subsystem gives a fresh clone of the repo a clean, one-command path from `git clone` to "ready to hammer with load": install dependencies, create `.env`, start the Docker stack, apply migrations, and provision one or many accounts with API keys. The only tools a new clone needs installed beforehand are Poetry, Docker, and `make`.

Since the Makefile is meant to be the one front door a new clone discovers everything through, it also picks up the general dev-workflow commands (test, lint, format, git hooks) that the project already relies on but nothing currently wires together in one place.

In scope:

- `cli/` — a Typer-based Python CLI holding the actual logic (account creation, running migrations).
- `Makefile` — the front-door interface, and the only one a new clone needs to discover (`make help`). Targets with real logic are thin wrappers around `poetry run python -m cli.main ...`; the rest are single existing shell commands kept in the Makefile on purpose (see Design Decision 6).
- One account-creation command, `account create --count N` (default `N=1`), replacing the ad hoc `local/create_account.py` script and covering both the single-account and bulk-provisioning cases with a single implementation. Bulk provisioning matters because simulating extreme load means many concurrent simulated clients, not one.
- A one-line fix to `.env.example` (and the local `.env`): `POSTGRES_HOST` changes from `postgres` to `localhost`, so host-side Python can reach the database at all. Currently the only line in that file not written from the host's point of view (see Design Decision 8).
- Environment bootstrap (`make setup`): installs Poetry dependencies, creates `.env` from `.env.example` if absent, starts the Docker stack and waits for it to become healthy, runs Alembic migrations programmatically, creates one default account (`count=1`), and installs the git hook — so a fresh clone is fully usable after one command (see Design Decision 9).
- Environment wipe (`make nuke`): a pure Makefile target (no Python) that deletes `local/accounts.csv` and runs `docker compose down -v` followed by `docker compose up -d --wait`, so repeated load-test cycles have a one-command way back to an empty, freshly-started stack.
- General dev-workflow targets (`make test`, `make lint`, `make format`): thin wrappers around the project's existing tools — `pytest` (already a dev dependency, configured with `testpaths = ["tests"]` in `pyproject.toml`) and the `ruff check .` / `ruff format .` commands CLAUDE.md documents.
- Git hook installation as part of `make setup`: `.pre-commit-config.yaml` is already tracked, but `pre-commit` isn't a project dependency and nothing runs `pre-commit install` on a fresh clone, so the hook currently never gets wired up for anyone but the original author.

Out of scope (explicit non-goals):

- Documents and jobs stay out of this CLI entirely. Those already have API endpoints (`POST /documents`, `POST /documents/{id}/process`, `GET /jobs/{id}`) and will be driven through Postman instead.
- `local/create_document.py`, `local/upload_file.py`, `local/process_document.py` are untouched by this work. Whether to retire them in favor of Postman is a separate decision (see Open Questions). `local/create_account.py` is different — it is deleted in Phase 1, since `account create` fully supersedes it.
- The load generator and monitoring/observability subsystems. Referenced here only as context for why bulk account provisioning matters.
- MinIO bucket creation — already handled automatically by the `createbuckets` service in `docker-compose.yml`; `setup` does not need to touch storage.
- A DB-only reset command (truncating tables in-process) was considered and dropped: `docker compose down -v` already wipes Postgres/MinIO/RabbitMQ volumes in one shot, so a separate Python/SQL reset path would just be a worse version of a command that already exists. `make nuke` does not re-run `setup` afterward — it stops once the containers are back up and healthy, leaving an empty unmigrated DB; running `make setup` again is a deliberate separate step.

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

**Constraint this imposes: every CLI command stays synchronous, and each async piece gets its own `asyncio.run()`.**

An *event loop* is the scheduler that executes `async` code; `asyncio.run(coro)` starts a loop, runs one coroutine to completion, then shuts the loop down. Python raises `RuntimeError: asyncio.run() cannot be called from a running event loop` if you call it while a loop is already running on that thread.

That matters here because `command.upgrade()` works by importing and executing `shared/migrations/env.py`, and the last line of that file is already `asyncio.run(run_migrations_online())` (`shared/migrations/env.py:36`). So `command.upgrade()` is a synchronous call that starts its own event loop internally. Meanwhile `_create_accounts()` must be `async`, because it writes through an async SQLAlchemy session.

Writing `setup()` the obvious way — `async def setup(): migrate(); await _create_accounts(...)` — therefore crashes: by the time `command.upgrade()` runs, a loop is already active, and `env.py`'s `asyncio.run` raises. The correct shape:

- `migrate()` and `setup()` are plain `def`, not `async def`.
- `setup()` calls `command.upgrade()` first (which opens and closes its own loop), and *then* calls `asyncio.run(_create_accounts(...))` as a separate, second loop.
- The `account create` Typer command is likewise a plain `def` wrapping `asyncio.run(_create_accounts(...))` — Typer commands are synchronous and Typer will not await a coroutine for you.

Ordering is load-bearing: migrations must fully finish (loop opened *and* closed) before the account loop starts, which the sequential-sync structure gives for free.

### 5. `package-mode = false` stays as-is

No console-script entry point. `cli/` is invoked as `poetry run python -m cli.main <command>` — the Makefile is what hides this from a first-time user, so there's no need to change how Poetry packages the project just for a nicer bare command name.

### 6. `nuke` is Make-only — no corresponding Typer/Python command

The dividing line for what gets a Python layer: real program logic goes in `cli/`, single existing shell commands stay in the Makefile. `migrate`, `account create`, and the DB half of `setup` earn Python because they have actual logic — hashing, bulk insert, Alembic API calls. `nuke` has none: deleting a local file and cycling `docker compose` are two shell one-liners with no loop, no hashing, no DB session, so a `cli.main nuke` layer would be pure indirection around commands that are already this simple and this discoverable.

The same rule explains the other Makefile-only lines: `pre-commit install` (Design Decision 7), `poetry install`, `cp -n .env.example .env`, `docker compose up -d --wait` (Design Decision 9), and the `test`/`lint`/`format` wrappers around `pytest` and `ruff`. None of them have logic to express; `poetry install` additionally *cannot* live in `cli/`, since it's what makes running project Python possible in the first place.

Naming: `setup` (not `bootstrap`) for the "get this project into a usable state" command, and `nuke` for the destructive wipe. `setup` matches the closest common precedent (Rails' `bin/setup` — migrate + seed a fresh DB) and reads as the broader, more complete operation; `bootstrap`, where it's used in Makefile conventions elsewhere, usually refers to something narrower like installing dependencies. `nuke` is an established colloquialism for "destroy and start clean," and — unlike a blander name like `clean` or `reset` — it reads as appropriately alarming for a command that deletes local data and Docker volumes.

### 7. `pre-commit` becomes a Poetry dev dependency; `pre-commit install` runs from `make setup`

Two distinct problems, easy to conflate: whether the `pre-commit` *tool* is available at all, and whether git is actually wired to call it. `poetry install` only solves the first — it makes `pre-commit` an importable/runnable package inside the project's virtualenv, exactly like `ruff` or `pytest` already are. It does nothing to git.

Making git call it requires running `pre-commit install`, which writes a script into `.git/hooks/pre-commit`. That directory is part of `.git/`, which is never copied by `git clone` — every fresh clone starts with git's empty default hook stubs regardless of what's configured in the tracked `.pre-commit-config.yaml`. So this step can't be skipped or inferred; it has to run explicitly, once, per clone.

Since every other command in this Makefile is invoked as `poetry run ...`, `pre-commit` has to be a Poetry dependency for `poetry run pre-commit install` to resolve at all — `poetry run` only finds executables inside the project's own virtualenv, not ones installed globally via `pipx`/Homebrew (a more common setup for `pre-commit` elsewhere, but inconsistent with how this Makefile treats every other dev tool). `setup` runs it as a second shell line, not through `cli.main`, for the same reason `nuke`'s operations stay in the Makefile (Design Decision 6): it's a single existing command with no logic to express in Python.

### 8. `.env` describes the host, so `POSTGRES_HOST` becomes `localhost`

`.env.example:3` currently sets `POSTGRES_HOST=postgres`. That value is a *Docker network hostname*: Compose puts every service on a private virtual network and registers each one under its service name, so a process inside the `api` or `worker` container can dial `postgres:5432` and Docker resolves it. A process running directly on the host has no such resolver — `postgres` is not a real DNS name there. On the host, Postgres is reachable at `localhost:${POSTGRES_PORT}`, because `docker-compose.yml:56` publishes the port.

`make` targets invoke the CLI as `poetry run python -m cli.main ...`, which runs on the host. Both things `setup` does are DB writes — Alembic builds its engine from `settings.database_url` (`shared/migrations/env.py:28`), and `_create_accounts` opens an async session from the same settings — so with `.env` as shipped, *both fail to resolve the hostname on every fresh clone*. This is not an edge case to document; it's the guaranteed default outcome, and it would make `make setup` fail 100% of the time.

**Fix: change the line to `POSTGRES_HOST=localhost` in both `.env.example` and any existing local `.env`.** No Makefile override, no wrapper — one line, at the root cause.

This is safe because nothing that needs `postgres` actually reads the value from `.env`:

- `api` and `worker` hardcode `POSTGRES_HOST: postgres` in their compose `environment:` blocks (`docker-compose.yml:9`, `:30`), and in Compose an `environment:` entry takes precedence over `env_file:`. Those containers are unaffected.
- The `postgres` container does load `.env`, but the `postgres:16` image never reads `POSTGRES_HOST` — it uses only `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD`, and its healthcheck (`pg_isready -d $POSTGRES_DB -U $POSTGRES_USER`) connects over a local Unix socket with no host at all.
- `rabbitmq`, `minio`, and `createbuckets` never reference the variable.

So the only consumer is host-side Python — `local/*.py` today, `cli/` from here on — reading `.env` through pydantic-settings' `env_file=".env"` (`shared/core/settings/base.py:16`).

Framed correctly, this isn't a new convention being introduced; it's an existing inconsistency being corrected. `.env.example` is *already* written from the host's point of view for the other two services: `RABBITMQ_HOST=localhost` (line 11) and `S3_ENDPOINT_URL=http://localhost:9000` (line 20), each overridden to `rabbitmq` / `http://minio:9000` in the same compose `environment:` blocks. `POSTGRES_HOST` was the one line not following that pattern, which is precisely why host-side scripts needed a manual override to work. Fixing it makes the file internally consistent: **`.env` holds host-facing values; `docker-compose.yml` overrides them with in-network names for the containerized services.** Production is unaffected — `infrastructure/stacks/compute_stack.py:78` sets `POSTGRES_HOST` from the live RDS endpoint and never consults `.env.example`.

The alternative considered was running the CLI *inside* the stack (`docker compose run --rm api python -m cli.main ...`), which would make `postgres` resolve with no `.env` change at all. Rejected because it costs more than it looks: `docker-compose.yml:17-19` mounts only `./shared` and `./api` into the `api` container, so `cli/` wouldn't exist inside it — that path additionally needs a `./cli` volume mount, `typer` installed into the api image, and a container start per command. It also leaves the `.env` inconsistency in place for every other host-side script.

### 9. `setup` bootstraps the whole environment, not just the database

For the Goal's "one command from `git clone`" claim to be literally true, `setup` has to cover everything between a bare clone and a working stack — not just migrations. A bare clone has no `.env` (only `.env.example` is tracked), no installed virtualenv, and no running containers, so a database-only `setup` would still leave three undocumented manual steps in front of it.

So `make setup` runs, in order:

1. `poetry install` — creates the virtualenv every later `poetry run` depends on. This is the reason `setup` must be a Makefile target rather than a `cli.main` command: it's what makes running Python possible in the first place, so it cannot itself be written in project Python.
2. `cp -n .env.example .env` — `-n` means "no clobber": copy only if the destination doesn't exist, so re-running `setup` never overwrites real local secrets.
3. `docker compose up -d --wait` — see Design Decision 10 for why `--wait`.
4. `poetry run python -m cli.main setup` — migrations + one default account.
5. `poetry run pre-commit install` — the git hook (Design Decision 7).

Prerequisites therefore reduce to Poetry, Docker, and `make`. Steps 1–3 and 5 are shell one-liners with no logic worth expressing in Python, consistent with Design Decision 6; only step 4 has real logic.

### 10. `docker compose up` always uses `--wait`

`docker compose up -d` returns as soon as containers are *created*, not when the services inside them are ready to accept connections. Postgres takes several seconds to initialize. Without a wait, `setup`'s migration step races the database and intermittently fails with a connection error — and `make nuke && make setup`, the core load-test reset cycle, hits this race every time.

`--wait` blocks until each service's healthcheck reports healthy. The healthchecks already exist (`docker-compose.yml:57-60` for Postgres; `worker` already gates on `condition: service_healthy`), so this costs nothing new — it just reuses readiness signals the compose file already defines. Both `setup` and `nuke` use it.

## Components

```
cli/
├── main.py                 # Typer root app; wires account + setup
└── commands/
    ├── account.py           # `account create --count N`
    └── bootstrap.py         # `setup`, `migrate`

Makefile                     # setup, seed, migrate, nuke, test, lint, format, help targets
```

### `cli/commands/account.py`

- `async def _create_accounts(count: int, out: Path) -> None` — the one implementation. Loops `count` times generating a key with `secrets.token_urlsafe(32)` and hashing with `hashlib.sha256(...).hexdigest()` (matching `api/services/account.py:18` exactly), bulk-inserts the `Account` rows via `shared.core.config.get_settings()` + SQLAlchemy async session, then appends `account_id,api_key` rows to `out` (writing the header first only if the file is new — see Design Decision 3). Prints a one-line summary, not the keys themselves.

  **IDs come from the database, so the rows must be flushed before the CSV can be written.** `Account.id` is `mapped_column(primary_key=True, autoincrement=True)` (`shared/infrastructure/models.py:19`) — Postgres assigns it, not Python, so `account.id` is `None` until the INSERT actually reaches the server. Either `await session.flush()` (sends the INSERTs and populates the IDs while keeping the transaction open) or commit before reading them; pair with `expire_on_commit=False` on the sessionmaker so attribute access after commit doesn't trigger a reload, exactly as `local/create_account.py` does today. Only after the IDs are populated can the `account_id,api_key` pairs be written out.
- `def create(count: int = 1, out: Path = Path("local/accounts.csv"))` — the Typer command (`account create`). Synchronous; wraps `asyncio.run(_create_accounts(count, out))` (Design Decision 4).
- `bootstrap.py`'s `setup()` calls the same `_create_accounts` coroutine via its own `asyncio.run(...)` — same function, not a subprocess or recursive CLI invocation.

### `cli/commands/bootstrap.py`

- `def migrate()` — runs `alembic.command.upgrade(cfg, "head")` against an `alembic.config.Config` pointed at the repo's `alembic.ini`. Exposed as its own Typer command (`migrate`) so it can be run standalone after pulling new migrations. Plain `def`, never `async def` — it starts its own event loop internally by way of `env.py` (Design Decision 4).
- `def setup()` — calls `migrate()` first, and only after it returns calls `asyncio.run(account._create_accounts(count=1, out=Path("local/accounts.csv")))`. Two sequential, non-overlapping event loops; `setup` itself stays synchronous. Leaves you with a migrated DB and one usable API key.

### `Makefile`

```makefile
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
```

## Phases

**Phase 0 — fix `POSTGRES_HOST`.** Change `POSTGRES_HOST=postgres` to `POSTGRES_HOST=localhost` in `.env.example` and in the local `.env` (Design Decision 8). One line, but it gates every later phase: nothing host-side can reach the database until it's done. Verify by running the existing `local/create_account.py` with no environment override — it should now succeed on its own.

**Phase 1 — CLI foundation + account creation.** Add `typer` and `pre-commit` to `pyproject.toml`. Create `cli/main.py` and `cli/commands/account.py` with the async `_create_accounts()` and the synchronous `create --count N` command wrapping it in `asyncio.run(...)`, ported and generalized from `local/create_account.py`. Delete `local/create_account.py` once `account create` is confirmed working — it is fully superseded. Confirms the Typer wiring, the flush-then-write ID handling, the append-to-CSV behavior, and `python -m cli.main` invocation all work before building anything on top.

**Phase 2 — Environment bootstrap.** Add `cli/commands/bootstrap.py` with `migrate()` and `setup()`, both plain synchronous functions (`setup()` calls `migrate()`, then `asyncio.run(account._create_accounts(count=1, ...))` — Design Decision 4). Wire both into `cli/main.py`.

**Phase 3 — Makefile front door.** Add the `Makefile` with the `COUNT ?= 1` default, the full `setup` target (deps → `.env` → `docker compose up -d --wait` → `cli.main setup` → `pre-commit install`), plus `seed`, `migrate`, `test`, `lint`, `format`, `help` (each delegating to the corresponding `cli.main` command or existing tool) and `nuke` (pure shell, no `cli.main` involvement).

## Error Handling

No new exception hierarchy — this is dev/ops tooling, not request-handling code, so it doesn't need to fit `shared/core/exceptions.py`'s `AppException` hierarchy. Failures surface directly:

- Migration failure in `setup`/`migrate`: Alembic's own exception propagates with its traceback; the command exits non-zero. No swallowing.
- `account create` with `--count <= 0`: rejected by Typer as a usage error before any DB connection is opened.
- DB connection failure: the raw `asyncpg`/SQLAlchemy connection error surfaces as-is. Not worth wrapping for a local dev tool. Note that the two predictable causes of this are now designed out rather than left to the user — hostname resolution by the `.env` fix (Design Decision 8) and startup races by `--wait` (Design Decision 10) — so a connection error here means something genuinely unexpected, not a missing incantation.
- A `make` recipe line exiting non-zero aborts the target and the remaining lines do not run. This is the wanted behavior for `setup`: if `docker compose up -d --wait` times out on an unhealthy service, `setup` stops there rather than running migrations against a database that isn't up.

## Testing

No inline tests during implementation, consistent with deferring test-writing to the end of the project. Each phase gets a manual smoke check instead:

- **Phase 0** — with the stack already up, run `python local/create_account.py` with no `POSTGRES_HOST=` prefix and confirm it connects. Then run `docker compose up -d --wait` and confirm `api` and `worker` still reach the DB (check their logs for connection errors), proving the `environment:` override still wins over the changed `.env`.
- **Phase 1** — run `account create` and `account create --count 5`; confirm the DB rows exist, that the `account_id` values written to CSV match the real primary keys (catches a missing flush, which would otherwise write empty or `None` IDs), and that `local/accounts.csv` has a single header with the right number of appended rows across both runs.
- **Phase 2** — run `setup` against a fresh empty database and confirm migrations apply and one account is appended. Specifically confirm no `RuntimeError: asyncio.run() cannot be called from a running event loop` — that error means the sync/async structure in Design Decision 4 was not followed.
- **Phase 3** — the real test is a genuinely cold start: clone into a fresh directory with no `.env` and no virtualenv, run `make setup` alone, and confirm it ends with a running stack, a migrated DB, one row in `local/accounts.csv`, and a working hook at `.git/hooks/pre-commit`. Then confirm `make setup` is safe to re-run (does not clobber `.env`), `make nuke` followed immediately by `make setup` completes without a connection race, bare `make seed` creates exactly one account while `make seed COUNT=50` creates fifty, and `make test` / `make lint` / `make format` / `make help` each run without error.

## Open Questions

- Whether to retire `local/create_document.py` / `upload_file.py` / `process_document.py` now that Postman covers that interaction, or leave them alongside this CLI. Deferred — not blocking this work.

## Future Work

- **Load generator** — a separate tool to drive concurrent traffic against the pipeline using the pool of accounts accumulated in `local/accounts.csv`. Own design.
- **Monitoring/observability** — dashboards/metrics for queue depth, job latency, failure rates, worker throughput under load. Own design. (Connor's own notes in `docs/setup.md` already sketch the four Golden Signals to track: p99 latency, RPS/queue throughput, DLQ+5xx+failure-rate errors, queue-growth+CPU+RDS-connection saturation.)
- **Console-script entry point** — if `package-mode` ever changes for unrelated reasons, revisit giving the CLI a bare installed command name instead of `python -m cli.main`.
