from types import ModuleType

from pipeline.client import PipelineClient
from scenarios.base import Report, ScenarioContext


def test_report_records_events_in_order():
    report = Report(scenario="worker-kill")

    report.record("submitted", "document_id=abc")
    report.record("worker_killed")

    assert [e[1] for e in report.events] == ["submitted", "worker_killed"]
    assert report.events[0][2] == "document_id=abc"
    assert report.events[1][2] == ""


def test_report_render_includes_scenario_events_and_summary():
    report = Report(scenario="worker-kill")
    report.record("submitted", "document_id=abc")
    report.summary = "final_status=started"

    output = report.render()

    assert "worker-kill" in output
    assert "submitted" in output
    assert "document_id=abc" in output
    assert "final_status=started" in output


def test_scenario_context_bundles_primitives():
    fake_module = ModuleType("fake")
    ctx = ScenarioContext(
        client=PipelineClient(),
        fixtures=fake_module,
        docker=fake_module,
        jobs=fake_module,
    )

    assert isinstance(ctx.client, PipelineClient)
    assert ctx.fixtures is fake_module
