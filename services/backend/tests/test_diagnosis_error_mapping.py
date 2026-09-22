from __future__ import annotations

from sysmind.diagnosis.coordinator import _planner_stop_reason


def test_plan_budget_maps_to_budget_exceeded() -> None:
    assert _planner_stop_reason("plan_budget_exceeded") == "budget_exceeded"


def test_unsafe_or_invalid_plan_fails_closed_as_risk_limit() -> None:
    assert _planner_stop_reason("risk_limit_reached") == "risk_limit_reached"
    assert _planner_stop_reason("invalid_plan") == "risk_limit_reached"
    assert _planner_stop_reason("policy_denied") == "risk_limit_reached"


def test_provider_protocol_error_is_not_risk_limit() -> None:
    assert _planner_stop_reason("provider_protocol_error") == "internal_error"
    assert _planner_stop_reason("provider_error") == "internal_error"
