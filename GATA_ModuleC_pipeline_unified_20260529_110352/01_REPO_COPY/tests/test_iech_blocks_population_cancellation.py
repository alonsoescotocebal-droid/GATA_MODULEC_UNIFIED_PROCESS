from __future__ import annotations

import sys
from pathlib import Path


def test_population_smoke_burden_proxy_equals_expo_person_hours(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    iech_csv = tmp_path / "IECH_unit_2015_2024.csv"
    iech_csv.write_text(
        "unit_id;year;smoke_hours_equiv;population_total;expo_person_hours;population_smoke_burden_proxy;claim_status\n"
        "U1;2015;240;100;24000;24000;OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH\n"
        "U2;2015;480;200;96000;96000;OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH\n",
        encoding="utf-8",
    )
    status, obs = gate.evaluate_population_cancellation(iech_csv)
    assert status == "OPERATIONAL_POPULATION_SMOKE_BURDEN_PROXY"
    assert "equals expo_person_hours" in obs


def test_population_smoke_burden_proxy_blocks_if_collapsed_to_smoke_hours(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    iech_csv = tmp_path / "IECH_unit_2015_2024.csv"
    iech_csv.write_text(
        "unit_id;year;smoke_hours_equiv;population_total;expo_person_hours;population_smoke_burden_proxy\n"
        "U1;2015;240;100;24000;240\n"
        "U2;2015;480;200;96000;480\n",
        encoding="utf-8",
    )
    status, obs = gate.evaluate_population_cancellation(iech_csv)
    assert status == "BLOCKED_POPULATION_EXPOSURE_CLAIM"
    assert "equals smoke_hours_equiv" in obs
