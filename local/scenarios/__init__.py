"""SCENARIOS registry: scenario name -> its async run(ctx) -> Report
callable. Each scenario is added as one module plus one entry here, added
incrementally, one per session — see local/README.md's "Adding a scenario"
checklist.
"""

from collections.abc import Awaitable, Callable

from .base import Report, ScenarioContext
from .worker_kill import run as worker_kill_run

ScenarioFn = Callable[[ScenarioContext], Awaitable[Report]]

SCENARIOS: dict[str, ScenarioFn] = {
    "worker-kill": worker_kill_run,
}
