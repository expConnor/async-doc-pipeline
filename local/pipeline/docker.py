"""Thin, explicit wrappers over the Docker CLI and rabbitmqctl. Covers every
fault injection the chaos scenarios need so no scenario shells out on its
own. Every mutating call here is reversible; scenarios are responsible for
restoring the stack (reconnect, unpause, rescale) in a finally.
"""

import json
import subprocess
from dataclasses import dataclass

_NETWORK = "doc-pipeline_default"


@dataclass(frozen=True)
class ContainerState:
    running: bool
    started_at: str | None
    restart_count: int
    exit_code: int | None


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"command {cmd} failed (exit {e.returncode}): {e.stderr}"
        ) from e
    return result.stdout


def worker_containers() -> list[str]:
    out = _run(["docker", "compose", "ps", "--format", "{{.Name}}", "worker"])
    return [line for line in out.splitlines() if line.strip()]


def kill(container: str) -> None:
    _run(["docker", "kill", "-s", "SIGKILL", container])


def stop(container: str, timeout: int = 10) -> None:
    _run(["docker", "stop", "-t", str(timeout), container])


def start(container: str) -> None:
    _run(["docker", "start", container])


def restart(container: str, timeout: int = 10) -> None:
    _run(["docker", "restart", "-t", str(timeout), container])


def pause(container: str) -> None:
    _run(["docker", "pause", container])


def unpause(container: str) -> None:
    _run(["docker", "unpause", container])


def scale_workers(n: int) -> None:
    _run(["docker", "compose", "up", "-d", "--scale", f"worker={n}"])


def disconnect(container: str) -> None:
    _run(["docker", "network", "disconnect", _NETWORK, container])


def connect(container: str) -> None:
    _run(["docker", "network", "connect", _NETWORK, container])


def logs(service: str, since: str = "1m") -> str:
    return _run(["docker", "compose", "logs", "--since", since, service])


def _list_queues() -> list[dict]:
    out = _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "rabbitmq",
            "rabbitmqctl",
            "list_queues",
            "name",
            "messages",
            "messages_unacknowledged",
            "--formatter",
            "json",
        ]
    )
    return json.loads(out)


def queue_depth(queue: str = "jobs") -> int:
    for row in _list_queues():
        if row["name"] == queue:
            return int(row["messages"])
    return 0


def unacked_count(queue: str = "jobs") -> int:
    for row in _list_queues():
        if row["name"] == queue:
            return int(row["messages_unacknowledged"])
    return 0


def container_state(container: str) -> ContainerState:
    out = _run(["docker", "inspect", container])
    data = json.loads(out)[0]
    state = data["State"]
    return ContainerState(
        running=state["Running"],
        started_at=state.get("StartedAt"),
        restart_count=data.get("RestartCount", 0),
        exit_code=state.get("ExitCode"),
    )
