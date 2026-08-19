from collections.abc import Callable


class ShutdownController:
    def __init__(self, callback: Callable[[], None] | None = None) -> None:
        self._callback = callback
        self.requested = False

    def set_callback(self, callback: Callable[[], None]) -> None:
        self._callback = callback

    def request_shutdown(self) -> None:
        self.requested = True
        if self._callback is not None:
            self._callback()

