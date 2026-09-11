from __future__ import annotations

import pytest

from sysmind.domain.platform_inspection import ServiceAssessment, ServiceInfo, StartupAssessment


def _startup(**overrides: object) -> StartupAssessment:
    payload: dict[str, object] = {
        "items": (),
        "item_count": 0,
        "high_impact_count": 0,
        "observations": (),
        "unknown_signature_count": 0,
    }
    payload.update(overrides)
    return StartupAssessment(**payload)  # type: ignore[arg-type]


def test_startup_assessment_counts_match_the_items() -> None:
    assessment = _startup(items=(), item_count=0)
    assert assessment.item_count == len(assessment.items)


def test_startup_assessment_rejects_item_count_drift() -> None:
    with pytest.raises(ValueError, match="item_count"):
        _startup(item_count=3)


def test_startup_assessment_rejects_out_of_range_subset_counts() -> None:
    with pytest.raises(ValueError, match="high_impact_count"):
        _startup(items=(), item_count=0, high_impact_count=1)
    with pytest.raises(ValueError, match="unknown_signature_count"):
        _startup(item_count=0, unknown_signature_count=-1)


def _service(**overrides: object) -> ServiceAssessment:
    payload: dict[str, object] = {
        "services": (),
        "service_count": 0,
        "stopped_automatic_count": 0,
        "observations": (),
    }
    payload.update(overrides)
    return ServiceAssessment(**payload)  # type: ignore[arg-type]


def test_service_assessment_rejects_count_drift() -> None:
    service = ServiceInfo("svc", "Service", "running", "automatic", None, None)
    with pytest.raises(ValueError, match="service_count"):
        _service(services=(service,), service_count=0)
    with pytest.raises(ValueError, match="stopped_automatic_count"):
        _service(services=(service,), service_count=1, stopped_automatic_count=2)
