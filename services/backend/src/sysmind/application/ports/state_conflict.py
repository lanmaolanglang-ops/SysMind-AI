from __future__ import annotations

from collections.abc import Sequence


class StateConflict(RuntimeError):
    """The persisted aggregate no longer has the expected source status.

    Raised when a compare-and-set status transition loses a race (for example
    ``complete`` vs ``cancel``). Exactly one competitor may write a terminal
    status; the loser must observe this conflict instead of overwriting it.
    """

    def __init__(
        self,
        record_id: str,
        *,
        expected: Sequence[str],
        actual: str | None = None,
    ) -> None:
        self.record_id = record_id
        self.expected = tuple(expected)
        self.actual = actual
        super().__init__(
            f"State conflict for {record_id}: expected one of {self.expected}, actual {actual!r}"
        )
