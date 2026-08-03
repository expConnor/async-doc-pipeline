# local/

Tools for exercising the doc-pipeline stack against a real `docker compose`
environment: an end-to-end smoke test, and a failure-injection ("chaos")
harness used to find out what the pipeline actually does when things go
wrong. See
`docs/superpowers/specs/2026-08-02-failure-mode-diagnosis-harness-design.md`
for the full design and the reasoning behind it.

## Entry points

- `make run COUNT=N` — smoke test: submits N documents end-to-end concurrently
  and reports pass/fail. Runs `local/smoke.py`.
- `make chaos SCENARIO=<name>` — runs one failure-injection scenario against
  the live stack and prints a plain-text report. Bare `make chaos` lists
  available scenarios. Runs `local/chaos.py`.

Both require the stack to be running (`docker compose up -d --wait`) and at
least one seeded account in `local/accounts.csv` (`make seed`).

## Package layout

- `pipeline/` — shared toolkit with no scenario knowledge: `client.py` talks
  HTTP to the API and knows nothing about Docker; `jobs.py` reads job/artifact
  state from Postgres via `psql` and knows nothing about scenarios;
  `docker.py` injects faults via the Docker CLI and `rabbitmqctl` and knows
  nothing about jobs; `fixtures.py` generates PDFs on demand.
- `scenarios/` — one module per failure mode, registered by name in
  `scenarios/__init__.py`. Scenarios compose the three `pipeline/` primitives
  and own no primitives of their own.

## Scenarios

| name | question |
|---|---|
| `worker-kill` | does redelivery + idempotency recover a hard-killed worker's job? |
| `shutdown-compare` | does SIGTERM let an in-flight job finish where SIGKILL doesn't? |
| `rabbitmq-restart` | does the worker reconnect, and what happens to the in-flight message? |
| `postgres-drop` | does the worker survive a DB outage mid-job? |
| `backpressure` | does the API reject at exactly `backpressure_threshold`? |
| `corrupt-pdf` | does a malformed PDF crash the worker process, or just fail the job? |
| `max-attempts` | does retry exhaustion cleanly reach terminal `FAILED`? |
| `redelivery-race` | does the compare-and-swap prevent a job being claimed twice? |
| `storage-down` | what happens when S3/MinIO is unreachable before the fetch, or during the upload? |
| `slow-pdf` | is there any per-job timeout, and is a wedged worker's capacity ever reclaimed? |
| `double-process` | what happens when the same document is processed twice concurrently? |
| `backlog-recovery` | does a backlog queued while workers are down drain cleanly once they're back? |

Only `worker-kill` is implemented so far. The rest are fully specified in the
design doc and are added one per session — see "Adding a scenario" below.

## Adding a scenario

1. Read that scenario's spec in the design doc — what's claimed, how to
   inject the fault, what to record, and what's expected.
2. Create `local/scenarios/<name>.py` (use underscores for hyphenated names,
   e.g. `redelivery_race.py` for `redelivery-race`) implementing:

   ```python
   async def run(ctx: ScenarioContext) -> Report: ...
   ```

3. Register it in `local/scenarios/__init__.py`:

   ```python
   from .<name> import run as <name>_run

   SCENARIOS: dict[str, ScenarioFn] = {
       ...,
       "<name>": <name>_run,
   }
   ```

4. Write no assertions. The scenario records observations via
   `Report.record(event, detail)` and a free-text `Report.summary`; a human
   judges the result against the design doc's *Claimed* / *Expected* sections
   for that scenario — several are expected to fail today, and asserting
   would just encode today's guesses as requirements.
5. Every mutating call in `pipeline/docker.py` must be undone by the scenario
   in a `finally` (reconnect networks, unpause containers, rescale workers
   back to 3) so the stack is clean for the next scenario.
6. Run it: `make chaos SCENARIO=<name>`. Confirm the stack recovered
   (`docker compose ps` shows the expected containers running).
7. Add the finding to the round's write-up: what was claimed, what was
   observed, whether that's a gap.
