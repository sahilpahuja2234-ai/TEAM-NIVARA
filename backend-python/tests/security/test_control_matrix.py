"""Tests for the control matrix layer (no database needed)."""

import pytest

from app.security import control_matrix as cm
from app.security.scoring import CONTROL_DIMENSION_MAP, WEIGHTS


def test_matrix_is_in_sync_with_scoring():
    cm.validate_matrix()  # raises ValueError on drift


def test_every_scoring_control_is_in_matrix():
    assert set(cm.CONTROL_MATRIX) == set(CONTROL_DIMENSION_MAP)


def test_every_dimension_has_at_least_one_control():
    for dim in WEIGHTS:
        assert cm.controls_in_dimension(dim), f"{dim} has no controls"


def test_dimensions_follow_weight_order():
    assert cm.DIMENSIONS == tuple(WEIGHTS)


def test_dimension_of_known_and_unknown():
    assert cm.dimension_of("trivy_scan") == "supply_chain"
    assert cm.dimension_of("not_a_control") is None


def test_get_control_matrix_rows():
    rows = cm.get_control_matrix()
    assert len(rows) == len(CONTROL_DIMENSION_MAP)
    assert {"key", "dimension", "weight", "description", "max_score"} <= set(rows[0])
    assert all(r["max_score"] == 1.0 for r in rows)


def test_validate_matrix_detects_missing_description(monkeypatch):
    monkeypatch.delitem(cm.CONTROL_DESCRIPTIONS, "gitleaks")
    with pytest.raises(ValueError, match="gitleaks"):
        cm.validate_matrix()
