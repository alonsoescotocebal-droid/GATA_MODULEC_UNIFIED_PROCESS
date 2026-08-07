from __future__ import annotations

import sys
from pathlib import Path


def test_population_smoke_day_burden_uses_classified_days_and_population(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    iech_csv = tmp_path / "IECH_unit_2015_2024.csv"
    iech_csv.write_text(
        "unit_id;year;smoke_days;population_total;population_smoke_day_burden_proxy;claim_status\n"
        "U1;2015;2;100;200;OPERATIONAL_TERRITORIAL_SMOKE_DAY_BURDEN_PROXY\n"
        "U2;2015;3;200;600;OPERATIONAL_TERRITORIAL_SMOKE_DAY_BURDEN_PROXY\n",
        encoding="utf-8",
    )
    status, obs = gate.evaluate_population_cancellation(iech_csv)
    assert status == "OPERATIONAL_POPULATION_SMOKE_DAY_BURDEN_PROXY"
    assert "smoke_days*population_total" in obs


def test_population_smoke_day_burden_blocks_if_not_binary_day_times_population(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    iech_csv = tmp_path / "IECH_unit_2015_2024.csv"
    iech_csv.write_text(
        "unit_id;year;smoke_days;population_total;population_smoke_day_burden_proxy;legacy_expo_person_hours\n"
        "U1;2015;2;100;240;24000\n"
        "U2;2015;3;200;480;96000\n",
        encoding="utf-8",
    )
    status, obs = gate.evaluate_population_cancellation(iech_csv)
    assert status == "BLOCKED_LEGACY_PHYSICAL_BURDEN"
    assert "person-hour" in obs
