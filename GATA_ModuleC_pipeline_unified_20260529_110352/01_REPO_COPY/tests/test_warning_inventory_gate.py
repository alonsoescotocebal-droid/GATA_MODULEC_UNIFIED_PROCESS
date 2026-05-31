from __future__ import annotations

import sys
from pathlib import Path


def test_warning_inventory_blocks_unexplained(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    p = tmp_path / "warning_inventory.tsv"
    p.write_text(
        "tool\tcontext\tclassification\texplained\timpact\tstatus\twarning_text\n"
        "gdal_translate\tGFAS_PM2P5_2022\tGENERIC_WARNING_UNCLASSIFIED\t0\tUNKNOWN\tBLOCKED\twarning test\n",
        encoding="utf-8",
    )
    status, obs, blocked = gate.evaluate_warning_inventory(p)
    assert status == "BLOCKED_UNEXPLAINED_WARNING"
    assert blocked == 1
    assert "count=1" in obs


def test_warning_inventory_passes_when_classified(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as gate  # type: ignore

    p = tmp_path / "warning_inventory.tsv"
    p.write_text(
        "tool\tcontext\tclassification\texplained\timpact\tstatus\twarning_text\n"
        "gdal_translate\tGFAS_PM2P5_2022\tGFAS_PACKING_WARNING_CLASSIFIED\t1\tLOW\tPASS\tnumPts * (numBits in a Group) ...\n",
        encoding="utf-8",
    )
    status, _obs, blocked = gate.evaluate_warning_inventory(p)
    assert status == "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
    assert blocked == 0
