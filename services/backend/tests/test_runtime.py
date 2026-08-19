import pytest

from sysmind.runtime.server import bind_loopback


def test_random_port_is_bound_on_loopback() -> None:
    listener = bind_loopback(0)
    try:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        listener.close()


def test_port_conflict_fails_without_fallback_to_public_interface() -> None:
    first = bind_loopback(0)
    try:
        port = int(first.getsockname()[1])
        with pytest.raises(OSError):
            bind_loopback(port)
    finally:
        first.close()
