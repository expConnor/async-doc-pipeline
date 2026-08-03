from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import chaos


async def test_no_scenario_name_lists_available(capsys):
    with patch.object(chaos, "SCENARIOS", {"worker-kill": AsyncMock()}):
        code = await chaos._main(None)

    out = capsys.readouterr().out
    assert "worker-kill" in out
    assert code == 0


async def test_unknown_scenario_name_lists_and_fails(capsys):
    with patch.object(chaos, "SCENARIOS", {"worker-kill": AsyncMock()}):
        code = await chaos._main("bogus")

    out = capsys.readouterr().out
    assert "worker-kill" in out
    assert code == 1


async def test_known_scenario_runs_and_prints_report(capsys):
    fake_report = SimpleNamespace(render=lambda: "REPORT TEXT")
    scenario_fn = AsyncMock(return_value=fake_report)

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with (
        patch.object(chaos, "SCENARIOS", {"worker-kill": scenario_fn}),
        patch.object(chaos, "PipelineClient", return_value=fake_client),
    ):
        code = await chaos._main("worker-kill")

    scenario_fn.assert_awaited_once()
    ctx = scenario_fn.await_args.args[0]
    assert ctx.client is fake_client
    assert ctx.docker is chaos.docker_module
    assert ctx.jobs is chaos.jobs_module
    assert ctx.fixtures is chaos.fixtures_module
    out = capsys.readouterr().out
    assert "REPORT TEXT" in out
    assert code == 0
