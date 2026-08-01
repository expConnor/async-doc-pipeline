import json
import uuid
from io import StringIO

import structlog

from shared.core.logging import setup_logging


def test_json_logging_serializes_uuid_as_plain_string(monkeypatch):
    """UUID fields in JSON logs should serialize as plain strings."""
    output = StringIO()

    # Configure logging to json format and capture output
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "info")

    setup_logging(log_format="json", log_level="info")

    # Temporarily redirect structlog's output to our StringIO
    def capturing_print(*args, **kwargs):
        if args:
            output.write(str(args[0]) + "\n")

    monkeypatch.setattr("builtins.print", capturing_print)

    # Log a message with a UUID context variable
    test_uuid = uuid.UUID("018f4a2b-7c3d-4a1e-8b1e-2a9f5c6d4e01")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(job_id=test_uuid)

    logger = structlog.get_logger()
    logger.info("test_event", document_id=test_uuid)

    # Parse the logged JSON and verify UUID fields are plain strings
    log_line = output.getvalue().strip()
    log_data = json.loads(log_line)

    # Both context-bound and inline UUIDs should be plain strings
    assert log_data["job_id"] == str(test_uuid)
    assert log_data["document_id"] == str(test_uuid)
    # Ensure it's not a repr() wrapped string
    assert "UUID(" not in log_data["job_id"]
    assert "UUID(" not in log_data["document_id"]
