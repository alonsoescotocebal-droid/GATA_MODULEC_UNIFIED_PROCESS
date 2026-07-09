from __future__ import annotations

from pathlib import Path


def test_population_smoke_burden_proxy_columns_are_wired_in_runtime_outputs():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")
    step7 = (repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(
        encoding="utf-8", errors="replace"
    )

    for token in (
        "population_total",
        "population_exposed_assumed",
        "exposure_fraction_assumption",
        "population_smoke_burden_proxy",
        "population_smoke_burden_proxy_mean_2015_2024",
    ):
        assert token in pipeline
        assert token in step7
