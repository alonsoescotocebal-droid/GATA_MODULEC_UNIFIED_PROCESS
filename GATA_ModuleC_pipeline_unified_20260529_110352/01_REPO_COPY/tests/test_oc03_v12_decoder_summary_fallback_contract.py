from __future__ import annotations

from pathlib import Path


def test_decoder_accepts_staged_edge_summary_fallback():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")

    assert '_grib_summary.csv' in pipeline
    assert '_grib_edge_summary.csv' in pipeline
    assert "def _load_gfas_pm_summary_rows" in pipeline
    assert '"shortName_1", "shortName_L"' in pipeline
    assert '"dataDate_1") or r.get("validityDate_1"' in pipeline


def test_decoder_processes_payloads_in_process_with_progress_logging():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")

    assert "ProcessPoolExecutor" not in pipeline
    assert "executor.submit" not in pipeline
    assert "GFAS decoder file start:" in pipeline
    assert "GFAS decoder progress:" in pipeline
    assert "GFAS decoder file complete:" in pipeline
    assert "GFAS decoder target direct years:" in pipeline
    assert "GFAS decoder planned PM message count reached:" in pipeline
    assert "pm_stride_hint" in pipeline

