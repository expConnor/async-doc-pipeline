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


# Every other function in this file is a thin wrapper that builds a command
# (a list of strings — the program name plus its arguments, exactly as you'd
# type them in a terminal) and hands it to this one helper. Centralizing the
# actual subprocess call here means every wrapper below gets the same error
# handling for free, instead of repeating a try/except in each one.
def _run(cmd: list[str]) -> str:
    try:
        # subprocess.run launches `cmd` as a real OS process and waits for it
        # to finish — this is Python running a shell command exactly as if
        # you'd typed it yourself. `capture_output=True` collects its stdout
        # and stderr instead of printing them to the terminal; `text=True`
        # decodes that output as a str instead of raw bytes; `check=True`
        # makes it raise `CalledProcessError` if the command exits non-zero
        # (i.e. failed) rather than silently returning.
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        # `raise NewException(...) from e` is "exception chaining": it raises
        # a new, more specific error but keeps `e` attached as the documented
        # cause, so a traceback shows both "this is what went wrong" (the
        # RuntimeError with the command and stderr) and "here's the low-level
        # error that triggered it" (the CalledProcessError), instead of losing
        # the original.
        raise RuntimeError(
            f"command {cmd} failed (exit {e.returncode}): {e.stderr}"
        ) from e
    return result.stdout


def worker_containers() -> list[str]:
    out = _run(["docker", "compose", "ps", "--format", "{{.Name}}", "worker"])
    # `_run` returns one big string; `.splitlines()` breaks it into a list of
    # lines (one per container name here). The `if line.strip()` filter drops
    # any blank lines — `.strip()` removes surrounding whitespace, so a line
    # that's empty or just whitespace evaluates to an empty string, which
    # Python treats as falsy.
    return [line for line in out.splitlines() if line.strip()]


# SIGKILL is a Unix signal that terminates a process immediately, with no
# chance for it to clean up (no "finally" blocks run, no in-flight work
# finishes) — the OS just ends it. This is deliberately the harshest possible
# fault to inject: it simulates a worker disappearing mid-job with zero
# warning, which is what scenario 1 (worker-kill) is testing recovery from.
def kill(container: str) -> None:
    _run(["docker", "kill", "-s", "SIGKILL", container])


# `docker stop` sends SIGTERM first (a polite "please shut down" signal a
# process can catch and react to — see worker/main.py's handling of it),
# then waits up to `timeout` seconds before escalating to SIGKILL if the
# process hasn't exited on its own. This is the "graceful shutdown" path,
# in contrast to kill()'s immediate SIGKILL.
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


# docker-compose.yml's worker service sets `deploy.replicas: 3` as its
# steady-state replica count. Scenarios that scale workers up or down (e.g.
# worker-kill, which kills one to simulate a crash) need that same number
# to restore the stack afterward — reading it here via `docker compose
# config` (which resolves the compose file, including any ${VAR}
# interpolation, and prints it back as JSON) means the replica count has
# exactly one place it's defined, docker-compose.yml itself, instead of
# also being duplicated as a literal in scenario code that could drift out
# of sync with it.
def configured_worker_replicas() -> int:
    out = _run(["docker", "compose", "config", "--format", "json"])
    data = json.loads(out)
    return int(data["services"]["worker"]["deploy"]["replicas"])


# Every container in the compose stack (api, postgres, rabbitmq, minio,
# workers) is attached to the same Docker network so they can reach each
# other by service name. disconnect() rips a container off that network
# without stopping it — the process keeps running, but every request it
# makes to another container now fails, simulating a network outage rather
# than a crash. connect() reattaches it, restoring communication.
def disconnect(container: str) -> None:
    _run(["docker", "network", "disconnect", _NETWORK, container])


def connect(container: str) -> None:
    _run(["docker", "network", "connect", _NETWORK, container])


def logs(service: str, since: str = "1m") -> str:
    return _run(["docker", "compose", "logs", "--since", since, service])


# rabbitmqctl is RabbitMQ's own command-line admin tool, run here inside the
# rabbitmq container via `docker compose exec`. "Queue depth" (`messages`) is
# how many messages are sitting in the queue waiting to be picked up by a
# worker; "unacknowledged" (`messages_unacknowledged`) is how many have been
# handed to a worker but not yet confirmed processed (acked) — the queue
# still holds onto them in case that worker dies before finishing, so it can
# redeliver them to someone else.
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
