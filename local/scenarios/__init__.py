"""SCENARIOS registry: scenario name -> its async run(ctx) -> Report
callable. Each scenario is added as one module plus one entry here, added
incrementally, one per session — see local/README.md's "Adding a scenario"
checklist.
"""

from collections.abc import Awaitable, Callable

from .base import Report, ScenarioContext
from .worker_kill import run as worker_kill_run

# This line doesn't run any code — it defines `ScenarioFn` as a name for a
# type, so it can be reused below instead of repeating the long type hint.
# `Callable[[ScenarioContext], Awaitable[Report]]` reads as: "a function that
# takes one ScenarioContext argument and returns something awaitable (i.e.
# it's an `async def`) that eventually produces a Report." Every scenario
# module's `run` function — see worker_kill.py's `async def run(ctx:
# ScenarioContext) -> Report` — matches this shape exactly, which is what
# lets chaos.py call `SCENARIOS[name](ctx)` the same way regardless of which
# scenario was picked.
ScenarioFn = Callable[[ScenarioContext], Awaitable[Report]]

SCENARIOS: dict[str, ScenarioFn] = {
    "worker-kill": worker_kill_run,
}
