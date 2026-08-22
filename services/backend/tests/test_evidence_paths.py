from sysmind.reports.evidence import evidence_path_exists


def test_evidence_path_subset_requires_existing_fields_and_bounded_arrays() -> None:
    value = {"network": {"adapters": [{"up": True}]}}

    assert evidence_path_exists(value, "$.network.adapters[0].up")
    assert not evidence_path_exists(value, "$.network.adapters[1].up")
    assert not evidence_path_exists(value, "$.network.missing")
    assert not evidence_path_exists(value, "$.__class__.__mro__")
    assert not evidence_path_exists(value, "$[lambda:1]")
