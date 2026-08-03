import json
import subprocess

import pytest
from pipeline import docker


def _fake_completed(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr=""
    )


def test_run_failure_surfaces_stderr_in_message(mocker):
    mocker.patch(
        "pipeline.docker.subprocess.run",
        side_effect=subprocess.CalledProcessError(
            1, ["docker", "kill", "x"], output="", stderr="No such container: x"
        ),
    )

    with pytest.raises(RuntimeError, match="No such container: x"):
        docker.kill("x")


def test_worker_containers_lists_replicas(mocker):
    run = mocker.patch(
        "pipeline.docker.subprocess.run",
        return_value=_fake_completed(
            "doc-pipeline-worker-1\ndoc-pipeline-worker-2\n"
        ),
    )

    names = docker.worker_containers()

    assert names == ["doc-pipeline-worker-1", "doc-pipeline-worker-2"]
    run.assert_called_once_with(
        ["docker", "compose", "ps", "--format", "{{.Name}}", "worker"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_kill_sends_sigkill(mocker):
    run = mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed()
    )

    docker.kill("doc-pipeline-worker-1")

    run.assert_called_once_with(
        ["docker", "kill", "-s", "SIGKILL", "doc-pipeline-worker-1"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_stop_uses_timeout(mocker):
    run = mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed()
    )

    docker.stop("doc-pipeline-worker-1", timeout=90)

    run.assert_called_once_with(
        ["docker", "stop", "-t", "90", "doc-pipeline-worker-1"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_scale_workers(mocker):
    run = mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed()
    )

    docker.scale_workers(3)

    run.assert_called_once_with(
        ["docker", "compose", "up", "-d", "--scale", "worker=3"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_disconnect_and_connect(mocker):
    run = mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed()
    )

    docker.disconnect("doc-pipeline-postgres")
    docker.connect("doc-pipeline-postgres")

    assert run.call_args_list[0].args[0] == [
        "docker",
        "network",
        "disconnect",
        "doc-pipeline_default",
        "doc-pipeline-postgres",
    ]
    assert run.call_args_list[1].args[0] == [
        "docker",
        "network",
        "connect",
        "doc-pipeline_default",
        "doc-pipeline-postgres",
    ]


def test_queue_depth_and_unacked_count_parse_json(mocker):
    payload = json.dumps(
        [{"name": "jobs", "messages": 5, "messages_unacknowledged": 2}]
    )
    mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed(payload)
    )

    assert docker.queue_depth() == 5
    assert docker.unacked_count() == 2


def test_queue_depth_returns_zero_for_missing_queue(mocker):
    mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed("[]")
    )

    assert docker.queue_depth() == 0


def test_container_state_parses_inspect_output(mocker):
    payload = json.dumps(
        [
            {
                "State": {
                    "Running": True,
                    "StartedAt": "2026-08-03T10:00:00Z",
                    "ExitCode": 0,
                },
                "RestartCount": 1,
            }
        ]
    )
    mocker.patch(
        "pipeline.docker.subprocess.run", return_value=_fake_completed(payload)
    )

    state = docker.container_state("doc-pipeline-worker-1")

    assert state.running is True
    assert state.started_at == "2026-08-03T10:00:00Z"
    assert state.restart_count == 1
    assert state.exit_code == 0
