from __future__ import annotations

from pathlib import Path


def test_iech_proxy_keeps_population_weighting_without_dividing_it_away():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")
    step7 = (repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(encoding="utf-8", errors="replace")

    assert "iech = expo" in pipeline
    assert "iech0 = expo0" in pipeline
    assert "iech1 = expo1" in pipeline
    assert "population_smoke_burden_proxy" in pipeline
    assert "OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH" in pipeline
    assert "population_smoke_burden_proxy = `smoke_days * 24 * population_total`" in step7
    assert "population_exposed_assumed = population_total" in step7
    assert "exposure_fraction_assumption = 1.0" in step7
