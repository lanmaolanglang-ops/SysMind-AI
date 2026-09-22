from __future__ import annotations

from collections.abc import Collection, Sequence


def allowed_source_statuses(
    *,
    target_status: str,
    non_terminal: Collection[str],
    terminal: Collection[str],
    expected: Sequence[str] | None,
) -> tuple[str, ...]:
    """Source statuses a compare-and-set write may transition from.

    - Explicit ``expected`` wins (strict CAS).
    - A terminal target only accepts non-terminal sources plus the same status
      (idempotent rewrite), so two different terminal statuses cannot overwrite
      each other.
    - A non-terminal target never revives a terminal row.
    """
    if expected is not None:
        return tuple(expected)
    if target_status in terminal:
        return (*tuple(non_terminal), target_status)
    return tuple(non_terminal)
