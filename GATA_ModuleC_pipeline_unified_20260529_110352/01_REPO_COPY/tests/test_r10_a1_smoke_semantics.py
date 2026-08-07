from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    module_path = repo_root / "pipeline" / "moduleC_pipeline_v2.py"
    spec = importlib.util.spec_from_file_location("moduleC_pipeline_v2_r10_a1", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_gate():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    module_path = repo_root / "pipeline" / "scientific_threshold_gate.py"
    spec = importlib.util.spec_from_file_location("scientific_threshold_gate_r10_a1", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Report:
    def log(self, _message: str) -> None:
        pass


def test_annual_smoke_days_are_binary_calendar_days_and_intensity_is_separate():
    mod = _load_module()
    rows = [
        {"unit_id": "U1", "year": 2020, "smoke_day_score": 50.0},
        {"unit_id": "U1", "year": 2020, "smoke_day_score": 100.0},
        {"unit_id": "U1", "year": 2020, "smoke_day_score": 200.0},
    ]

    finalized, annual, threshold = mod._finalize_unit_daily_scores(rows, _Report(), "r10-a1")

    assert threshold == 100.0
    assert [row["smoke_day_proxy"] for row in finalized] == [0, 1, 1]
    assert [row["normalized_smoke_intensity_proxy_daily"] for row in finalized] == [0.5, 1.0, 2.0]
    assert annual["U1"][2020]["smoke_days"] == 2.0
    assert annual["U1"][2020]["smoke_days_binary"] == 2.0
    assert annual["U1"][2020]["cumulative_normalized_smoke_intensity_proxy"] == 3.5
    assert annual["U1"][2020]["cumulative_normalized_smoke_intensity_proxy"] > annual["U1"][2020]["smoke_days"]


def test_positive_subthreshold_score_does_not_add_a_smoke_day():
    mod = _load_module()
    rows = [
        {"unit_id": "U1", "year": 2019, "smoke_day_score": 10.0},
        {"unit_id": "U1", "year": 2019, "smoke_day_score": 100.0},
    ]

    finalized, annual, _threshold = mod._finalize_unit_daily_scores(rows, _Report(), "r10-a1")

    assert finalized[0]["smoke_day_proxy"] == 0
    assert finalized[0]["normalized_smoke_intensity_proxy_daily"] == 0.1
    assert annual["U1"][2019]["smoke_days"] == 1.0


def test_population_smoke_day_burden_uses_binary_days_without_hours_conversion(tmp_path):
    mod = _load_module()
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "pop_unit_2015_2025_2030.csv").write_text(
        "unit_id;pop_2015_sum;pop_2020_sum;pop_2025_sum;pop_2030_sum\nU1;100;100;100;100\n",
        encoding="utf-8",
    )
    (tables / "recurrence_unit_2015_2024.csv").write_text("unit_id\nU1\n", encoding="utf-8")
    (tables / "smoke_days_unit_2015_2024.csv").write_text(
        "unit_id;year;smoke_days;normalized_smoke_intensity_proxy\n"
        + "\n".join(f"U1;{year};2;7.5" for year in range(2015, 2025))
        + "\n",
        encoding="utf-8",
    )

    hist_path, mean_path = mod.iech_compute(tables, _Report())
    hist_rows = mod.read_csv_rows(hist_path)[1]
    mean_rows = mod.read_csv_rows(mean_path)[1]

    assert hist_rows[0]["population_smoke_day_burden_proxy"] == "200.0"
    assert hist_rows[0]["population_smoke_day_burden_proxy_unit"] == "classified smoke-proxy person-days"
    assert hist_rows[0].get("population_smoke_burden_proxy") is None
    assert hist_rows[0].get("expo_person_hours") is None
    assert mean_rows[0]["population_smoke_day_burden_proxy_mean_2015_2024"] == "200.0"


def test_legacy_aliases_do_not_control_canonical_burden(tmp_path):
    mod = _load_module()
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "pop_unit_2015_2025_2030.csv").write_text(
        "unit_id;pop_2015_sum;pop_2020_sum;pop_2025_sum;pop_2030_sum\nU1;100;100;100;100\n",
        encoding="utf-8",
    )
    (tables / "recurrence_unit_2015_2024.csv").write_text("unit_id\nU1\n", encoding="utf-8")
    (tables / "smoke_days_unit_2015_2024.csv").write_text(
        "unit_id;year;smoke_days;smoke_hours_equiv;population_smoke_burden_proxy\n"
        + "\n".join(f"U1;{year};2;999;999999" for year in range(2015, 2025))
        + "\n",
        encoding="utf-8",
    )

    hist_path, _mean_path = mod.iech_compute(tables, _Report())
    hist_rows = mod.read_csv_rows(hist_path)[1]

    assert hist_rows[0]["population_smoke_day_burden_proxy"] == "200.0"
    assert hist_rows[0]["legacy_population_smoke_burden_proxy"] == ""


def test_canonical_smoke_days_respect_normal_and_leap_year_calendar_limits():
    mod = _load_module()
    for year, day_count in ((2019, 365), (2020, 366)):
        rows = [
            {"unit_id": "U1", "year": year, "smoke_day_score": 2.0}
            for _ in range(day_count)
        ]
        _finalized, annual, _threshold = mod._finalize_unit_daily_scores(rows, _Report(), "r10-a1")
        assert annual["U1"][year]["smoke_days"] <= day_count


def test_smoke_score_p80_is_not_an_upstream_control_for_canonical_outputs():
    mod = _load_module()
    base_rows = [
        {"unit_id": "U1", "year": 2020, "smoke_day_score": 10.0, "smoke_score_p80": 0.0},
        {"unit_id": "U1", "year": 2020, "smoke_day_score": 100.0, "smoke_score_p80": 999999.0},
    ]
    changed_rows = [dict(row, smoke_score_p80=123456789.0) for row in base_rows]
    _base_daily, base_annual, _base_threshold = mod._finalize_unit_daily_scores(base_rows, _Report(), "r10-a1")
    _changed_daily, changed_annual, _changed_threshold = mod._finalize_unit_daily_scores(changed_rows, _Report(), "r10-a1")
    assert changed_annual["U1"][2020]["smoke_days"] == base_annual["U1"][2020]["smoke_days"]
    assert changed_annual["U1"][2020]["cumulative_normalized_smoke_intensity_proxy"] == base_annual["U1"][2020]["cumulative_normalized_smoke_intensity_proxy"]
    source = (Path(__file__).resolve().parents[1] / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8")
    assert "population_smoke_day_burden_proxy=smoke_days*population_total" in source
    assert "smoke_score_p80 * 24" not in source


def test_era5_weighted_route_claim_is_blocked_when_score_does_not_use_era5():
    gate = _load_gate()
    assert gate.evaluate_era5_claims(False, "v0_gfas_era5_real")[0] == "BLOCKED_ERA5_MECHANISTIC_CLAIM"
