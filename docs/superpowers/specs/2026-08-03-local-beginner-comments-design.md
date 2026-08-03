# Beginner-facing comments for local/

## Purpose

`local/` (the smoke test + chaos/failure-injection harness built per
`2026-08-02-failure-mode-diagnosis-harness-design.md`) is already small and
well-factored — 9 files, ~400 lines, one clear responsibility per file. The
problem isn't size or structure, it's that the code leans on intermediate
Python mechanics and infra concepts with little to no explanation, and
Connor is a beginner (per `CLAUDE.md`: no concept, however basic, should be
assumed familiar).

This is a documentation-only pass: add comments that teach, change nothing
about behavior or structure.

## Scope

All 9 Python files under `local/`:

- `pipeline/client.py`
- `pipeline/docker.py`
- `pipeline/jobs.py`
- `pipeline/fixtures.py`
- `scenarios/base.py`
- `scenarios/worker_kill.py`
- `scenarios/__init__.py`
- `smoke.py`
- `chaos.py`

Out of scope: `README.md`, any logic change, renames, new files, or
restructuring.

## What gets explained

Two categories, since almost every file mixes both:

**1. Python language mechanics** — intermediate features used without
comment today:

- `async`/`await`, and why a given function needs to be async
- `async with` / `__aenter__` / `__aexit__` — what a context manager is,
  why `PipelineClient` uses one (guarantees the socket patch and the httpx
  clients get cleaned up even if something raises)
- `@dataclass(frozen=True)` — what it generates (`__init__`, `__repr__`,
  `__eq__`), what "frozen" buys you
- Type hints like `str | None`, `Callable[[ScenarioContext],
  Awaitable[Report]]`
- `assert self._api is not None` — this is satisfying the type checker
  (telling it "trust me, `__aenter__` already set this"), not runtime
  input validation
- Monkeypatching (`socket.getaddrinfo = _patched_getaddrinfo`) — what
  "patching a stdlib function at runtime" means and why it's reversible
- `subprocess.run(..., check=True)` and `raise X(...) from e` exception
  chaining

**2. Domain/infra concepts** the code assumes:

- Presigned S3 URLs (the existing detailed comment in `client.py` on the
  MinIO hostname patch is already good — leave it as-is)
- SIGKILL vs SIGTERM, `docker kill` vs `docker stop`
- Idempotency drop and the SQL compare-and-swap update (what "atomic" buys
  you here)
- Why job state is read via raw `psql` in the postgres container instead
  of the HTTP API
- RabbitMQ queue depth / unacked count, and what `rabbitmqctl list_queues`
  is reading

## Approach

Comments go directly above the line or block they explain, in each file,
at the point the concept first appears. Existing docstrings and the
detailed MinIO-patch comment in `client.py` stay untouched — the gap is
everywhere *else* a concept shows up with zero explanation, e.g.:

- `scenarios/__init__.py`'s `Callable[[ScenarioContext],
  Awaitable[Report]]` type alias
- `docker.py`'s `_run` subprocess wrapper and every thin wrapper function
  around it
- `jobs.py`'s `_run_query`'s embedded shell script (`sh -c` expanding env
  vars inside the container)
- `base.py`'s `ScenarioContext` dataclass bundling a `PipelineClient` and
  three modules

No file's actual code changes — only comments are added. This keeps the
diff trivial to review (pure additions) and there's no risk of behavior
regressions, so no test changes are needed.

## Out of scope

- Restructuring, renaming, or reducing the file/module count
- Touching `README.md` or the design doc it references
- Any change to program behavior
