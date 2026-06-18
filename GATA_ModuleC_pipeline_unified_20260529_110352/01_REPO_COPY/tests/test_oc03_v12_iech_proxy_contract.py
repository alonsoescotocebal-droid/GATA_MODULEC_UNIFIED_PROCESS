from __future__ import annotations

from pathlib import Path


def test_iech_proxy_keeps_population_weighting_without_dividing_it_away():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")
    step7 = (repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(encoding="utf-8", errors="replace")

    assert "iech = expo" in pipeline
    assert "iech0 = expo0" in pipeline
    assert "iech1 = expo1" in pipeline
    assert "IECH=smoke_days*24*pop_interp(2015,2020,2025);proxy_person_hours" in pipeline
    assert "iech = expo" in step7
    assert "iech0 = expo0" in step7
    assert "iech1 = expo1" in step7
    assert "persona-horas de exposicion" in step7
