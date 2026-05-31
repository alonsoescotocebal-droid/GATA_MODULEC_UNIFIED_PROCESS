from __future__ import annotations

import sys
from pathlib import Path


def test_iech_cancellation_is_blocked(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    iech_csv = tmp_path / "IECH_unit_2015_2024.csv"
    iech_csv.write_text(
        "unit_id;year;smoke_days;smoke_hours_equiv;pop;expo_person_hours;IECH\n"
        "U1;2015;10;240;100;24000;240\n"
        "U2;2015;20;480;200;96000;480\n",
        encoding="utf-8",
    )
    status, obs = gate.evaluate_population_cancellation(iech_csv)
    assert status == "BLOCKED_POPULATION_EXPOSURE_CLAIM"
    assert "IECH equals smoke_hours_equiv" in obs
