from __future__ import annotations

import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def test_decoder_falls_back_to_nested_recovery_gribs_when_edge_summary_has_no_pm_rows(tmp_path):
    mod = _load_module()
    gfas_dir = tmp_path / "CAM-GFAS (ADS)"
    gfas_dir.mkdir(parents=True, exist_ok=True)
    (gfas_dir / "_grib_edge_summary.csv").write_text(
        "file;shortName_1;shortName_L;minDate;message_count\n"
        "other_2015.grib;tp;tp;20150101;1\n",
        encoding="utf-8",
    )
    nested = gfas_dir / "_global_official_2015_2024"
    nested.mkdir(parents=True, exist_ok=True)
    for year in range(2015, 2025):
        (nested / f"GFAS_PM2P5FIRE_{year}_GLOBAL_OFFICIAL.grib").write_bytes(b"grib")

    rows = mod._load_gfas_pm_summary_rows(gfas_dir)

    years = [r["minDate"][:4] for r in rows]
    assert years == [str(y) for y in range(2015, 2025)]
    assert all("GLOBAL_OFFICIAL" in r["file"] for r in rows)
    assert all(r["message_count"] == "93" for r in rows)
