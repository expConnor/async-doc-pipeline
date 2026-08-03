"""Report dataclass and the ScenarioContext every scenario module receives.

No assertions live in scenario code: for several failure modes the correct
behaviour isn't known yet, and some are expected to misbehave. Scenarios
record observations; a human judges the result against the design doc's
Claimed/Expected sections for that scenario.

Convention: scenarios own their exceptions. `chaos.py`'s dispatcher only
has the `Report` a scenario's `run(ctx)` returns — if `run` lets an
exception propagate (e.g. a `RuntimeError` from a lookup helper, or a
`TimeoutError`/`CalledProcessError` from a `pipeline/` call), every event
recorded on the `Report` so far is lost and the operator sees a bare
traceback instead of the observation log this tool exists to produce.
Each scenario's `run(ctx)` should therefore construct its `Report` first,
wrap the rest of its body in `try`/`except`, and on any exception call
`report.record("scenario_error", str(e))`, set `report.summary` to note
the error, and return `report` instead of re-raising. This is still
observation, not a behavioural assertion — recording that something blew
up is the same category as recording any other event.
"""

from dataclasses import dataclass, field
from datetime import datetime
from types import ModuleType

from pipeline.client import PipelineClient


@dataclass
class Report:
    scenario: str
    events: list[tuple[datetime, str, str]] = field(default_factory=list)
    summary: str = ""

    def record(self, event: str, detail: str = "") -> None:
        self.events.append((datetime.now(), event, detail))

    def render(self) -> str:
        lines = [f"=== {self.scenario} ===", ""]
        for ts, event, detail in self.events:
            ts_str = ts.strftime("%H:%M:%S.%f")[:-3]
            line = f"[{ts_str}] {event}"
            if detail:
                line += f" — {detail}"
            lines.append(line)
        lines += ["", "--- summary ---", self.summary]
        return "\n".join(lines)


@dataclass
class ScenarioContext:
    client: PipelineClient
    fixtures: ModuleType
    docker: ModuleType
    jobs: ModuleType
