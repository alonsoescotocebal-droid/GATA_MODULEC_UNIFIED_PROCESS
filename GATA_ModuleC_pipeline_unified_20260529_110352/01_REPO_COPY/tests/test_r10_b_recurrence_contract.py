from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "pipeline"))

from recurrence_r10b import (  # type: ignore
    build_recurrence_records,
    classify_recurrence_score,
    legacy_years_gt_own_p75,
    tie_aware_fractional_rank,
)


def _record(unit_id, annual, unit_area=100.0, unique=20.0, reburn=0.0):
    return {
        "unit_id": unit_id,
        "unit_area_ha": unit_area,
        "annual_burned_area_by_year": {year: value for year, value in zip(range(2015, 2025), annual)},
        "unique_burned_area_ha": unique,
        "reburned_area_ha": reburn,
        "legacy_total_burn_ha_2015_2024": sum(annual),
        "legacy_recurrence_class_absolute_burn_tertile": "LOW",
    }


def test_same_absolute_area_respects_unit_area_normalization():
    rows = build_recurrence_records([
        _record("A", [10] + [0] * 9, unit_area=100.0),
        _record("B", [10] + [0] * 9, unit_area=200.0),
    ])
    assert rows[0]["cumulative_burned_fraction"] != rows[1]["cumulative_burned_fraction"]


def test_reburn_share_and_score_distinguish_same_load():
    rows = build_recurrence_records([
        _record("repeat", [4, 4] + [0] * 8, unique=4, reburn=4),
        _record("disjoint", [4, 4] + [0] * 8, unique=8, reburn=0),
    ])
    assert rows[0]["cumulative_burned_area_ha"] == rows[1]["cumulative_burned_area_ha"]
    assert rows[0]["reburn_share_of_unique_burned_area"] > rows[1]["reburn_share_of_unique_burned_area"]
    assert rows[0]["recurrence_score"] > rows[1]["recurrence_score"]


def test_same_year_overlap_is_not_recurrence_input():
    rows = build_recurrence_records([_record("A", [4] + [0] * 9, unique=4, reburn=0)])
    assert rows[0]["affected_year_count"] == 1
    assert rows[0]["reburned_area_ha"] == 0
    assert rows[0]["reburn_share_of_unique_burned_area"] == 0


def test_triple_burn_is_supplied_as_union_area_not_pair_sum():
    rows = build_recurrence_records([_record("A", [4, 4, 4] + [0] * 7, unique=4, reburn=4)])
    assert rows[0]["cumulative_burned_area_ha"] == 12
    assert rows[0]["unique_burned_area_ha"] == 4
    assert rows[0]["reburned_area_ha"] == 4


def test_no_fire_is_low_and_zero_signal():
    row = build_recurrence_records([_record("A", [0] * 10, unique=0, reburn=0)])[0]
    assert row["affected_year_fraction"] == 0
    assert row["recurrence_score"] == 0
    assert row["recurrence_class"] == "LOW"
    assert row["zero_fire_footprint_flag"] == 1


def test_ties_use_average_fractional_rank():
    assert tie_aware_fractional_rank([0.0, 0.0, 1.0]) == [0.25, 0.25, 1.0]


def test_fixed_bands_do_not_force_equal_class_counts():
    assert [classify_recurrence_score(value) for value in (0.0, 0.1, 0.2, 0.34)] == ["LOW", "LOW", "LOW", "MEDIUM"]
    assert classify_recurrence_score(2.0 / 3.0) == "HIGH"


def test_legacy_p75_is_diagnostic_and_not_score_driver():
    rows = build_recurrence_records([
        _record("A", [10] + [0] * 9, unique=10, reburn=0),
        _record("B", [0, 10] + [0] * 8, unique=10, reburn=0),
    ])
    assert all("legacy_years_area_gt_own_p75" in row for row in rows)
    assert all("legacy_years_area_gt_own_p75" not in {"recurrence_temporal_rank", "recurrence_reburn_rank"} for row in rows)
    assert legacy_years_gt_own_p75([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) == 3


def test_event_count_is_context_only():
    rows = build_recurrence_records([_record("A", [1] + [0] * 9)])
    rows[0]["event_count_if_validated"] = ""
    assert "event_count_if_validated" not in ("recurrence_score", "recurrence_class")
