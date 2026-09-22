from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sysmind.domain.diagnosis import DiagnosisToolCall, EvidenceReference, Finding
from sysmind.security.redaction import redact_structure

_PATH = re.compile(r"^\$(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)|(?:\[(?:0|[1-9]\d*)\]))*$")
_TOKEN = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9]\d*)\]")


def evidence_path_exists(value: object, path: str) -> bool:
    """Resolve the project's non-executable JSONPath subset and require a real field."""
    if not _PATH.fullmatch(path):
        return False
    current = value
    for match in _TOKEN.finditer(path):
        key, index = match.groups()
        if key is not None:
            if not isinstance(current, Mapping) or key not in current:
                return False
            current = current[key]
        else:
            if (
                not isinstance(current, Sequence)
                or isinstance(current, (str, bytes, bytearray))
                or int(index) >= len(current)
            ):
                return False
            current = current[int(index)]
    return True


def evidence_path_value(value: object, path: str) -> object:
    if not evidence_path_exists(value, path):
        raise ValueError("Evidence path does not exist.")
    current = value
    for match in _TOKEN.finditer(path):
        key, index = match.groups()
        current = current[key] if key is not None else current[int(index)]  # type: ignore[index]
    return current


@dataclass(frozen=True, slots=True)
class ComposedEvidence:
    tool_call_id: str
    tool_name: str
    tool_version: str
    key_fields: dict[str, object]
    raw_result_summary: dict[str, object]
    observed_at: str | None


class EvidenceComposer:
    """Fail-closed projection from deterministic findings to executed local evidence."""

    def compose(
        self,
        finding: Finding,
        calls: tuple[DiagnosisToolCall, ...],
    ) -> tuple[ComposedEvidence, ...]:
        return self.compose_references(finding.evidence, calls)

    def compose_references(
        self,
        references: tuple[EvidenceReference, ...],
        calls: tuple[DiagnosisToolCall, ...],
    ) -> tuple[ComposedEvidence, ...]:
        by_id = {call.id: call for call in calls if call.status == "completed"}
        grouped: dict[str, dict[str, object]] = {}
        for reference in references:
            call = by_id.get(reference.tool_call_id)
            if call is None or call.result is None:
                raise ValueError("Conclusion references a missing or failed tool call.")
            value = evidence_path_value(call.result, reference.field_path)
            if reference.field_path == "$":
                value = call.summary or {"result_available": True}
            elif isinstance(value, Mapping | Sequence) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                value = {"item_count": len(value)}
            grouped.setdefault(call.id, {})[reference.field_path] = value
        return tuple(
            ComposedEvidence(
                call_id,
                by_id[call_id].tool_name,
                by_id[call_id].tool_version,
                # User-visible evidence payloads are redacted before they reach the
                # markdown/JSON export surfaces; structure stays JSON-safe.
                {path: redact_structure(item) for path, item in key_fields.items()},
                redact_structure(by_id[call_id].summary or {}),  # type: ignore[arg-type]
                by_id[call_id].finished_at or by_id[call_id].started_at,
            )
            for call_id, key_fields in grouped.items()
        )
