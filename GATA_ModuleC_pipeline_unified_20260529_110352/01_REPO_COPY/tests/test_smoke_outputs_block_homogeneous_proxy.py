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
