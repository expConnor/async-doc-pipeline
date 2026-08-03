"""Dispatch to a failure-injection scenario by name. Bare invocation lists
available scenarios rather than erroring, matching the Makefile convention
that bare targets are safe.
"""

import asyncio
import sys

from pipeline import docker as docker_module
from pipeline import fixtures as fixtures_module
from pipeline import jobs as jobs_module
from pipeline.client import PipelineClient
from scenarios import SCENARIOS
from scenarios.base import ScenarioContext


def _list_scenarios() -> None:
    print("available scenarios:")
    for name in sorted(SCENARIOS):
        print(f"  {name}")


async def _main(name: str | None) -> int:
    if name is None or name not in SCENARIOS:
        _list_scenarios()
        return 0 if name is None else 1

    async with PipelineClient() as client:
        # This is the one place a ScenarioContext actually gets built — every
        # scenario module receives the same live PipelineClient plus the
        # three pipeline/ modules imported at the top of this file (renamed
        # with `as ..._module` only to avoid clashing with the `docker` and
        # `jobs` parameter names used elsewhere).
        ctx = ScenarioContext(
            client=client,
            fixtures=fixtures_module,
            docker=docker_module,
            jobs=jobs_module,
        )
        # `SCENARIOS[name]` looks up the chosen scenario's `run` function by
        # its string name (e.g. "worker-kill") in the dict built in
        # scenarios/__init__.py, then calls it immediately with `(ctx)`.
        report = await SCENARIOS[name](ctx)

    print(report.render())
    return 0


if __name__ == "__main__":
    scenario_name = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(_main(scenario_name)))
