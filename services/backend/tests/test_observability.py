import io
import json
import logging

from sysmind.observability.logging import JsonFormatter, log_event


def test_structured_log_has_required_fields_and_redacts_secrets() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("sysmind.test.redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    log_event(
        logger,
        logging.INFO,
        "Provider configuration updated",
        component="test",
        event_type="configuration_test",
        correlation_id="correlation-1",
        api_key="must-not-appear",
        safe_value="visible",
    )

    payload = json.loads(stream.getvalue())
    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["component"] == "test"
    assert payload["event_type"] == "configuration_test"
    assert payload["correlation_id"] == "correlation-1"
    assert payload["context"]["api_key"] == "[REDACTED]"
    assert "must-not-appear" not in stream.getvalue()

