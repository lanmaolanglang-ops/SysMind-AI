import io
import json
import logging

from sysmind.observability.logging import JsonFormatter, log_event


def test_structured_log_has_required_fields_and_redacts_secrets() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("sysmind.test.redaction")
    original_handlers = list(logger.handlers)
    original_propagate = logger.propagate
    original_level = logger.level
    try:
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
    finally:
        # Restore the logger so this test never leaks a handler into the rest of the suite.
        logger.handlers = original_handlers
        logger.propagate = original_propagate
        logger.setLevel(original_level)

    payload = json.loads(stream.getvalue())
    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["component"] == "test"
    assert payload["event_type"] == "configuration_test"
    assert payload["correlation_id"] == "correlation-1"
    assert payload["context"]["api_key"] == "[REDACTED]"
    assert "must-not-appear" not in stream.getvalue()


def test_log_message_and_traceback_paths_are_redacted() -> None:
    """Free-form message/exception text must not leak user-profile paths."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("sysmind.test.redaction.paths")
    original_handlers = list(logger.handlers)
    original_propagate = logger.propagate
    original_level = logger.level
    # Build the path at runtime so the traceback's echoed source line does not itself
    # contain the literal (which would be a test artifact, not a redaction failure).
    account = "alice"
    user_path = f"C:\\Users\\{account}\\sysmind\\data.db"
    try:
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        try:
            raise RuntimeError(f"failed reading {user_path}")
        except RuntimeError:
            logger.info("could not load %s", user_path, exc_info=True)
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate
        logger.setLevel(original_level)

    output = stream.getvalue()
    assert account not in output
    assert "[REDACTED]" in output
