from __future__ import annotations

import sys
from pathlib import Path


def test_homogeneous_smoke_days_is_blocked(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    smoke_csv = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke_csv.write_text(
        "unit_id;year;smoke_days\n"
        "U1;2015;10\n"
        "U2;2015;10\n"
        "U1;2016;12\n"
        "U2;2016;12\n",
        encoding="utf-8",
    )
    status, obs, _counts = gate.evaluate_smoke_spatial(smoke_csv)
    assert status == "BLOCKED_SPATIAL_SMOKE_CLAIM"
    assert "<=1 unique smoke_days" in obs


def test_zero_vs_positive_direct_smoke_counts_are_treated_as_spatially_differentiated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    smoke_csv = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke_csv.write_text(
        "unit_id;year;smoke_days;smoke_method\n"
        "U1;2016;0;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U2;2016;3;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U3;2016;3;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n",
        encoding="utf-8",
    )

    status, obs, counts = gate.evaluate_smoke_spatial(smoke_csv)

    assert status == "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION"
    assert counts[2016] == 2
    assert "differentiation" in obs.lower()
