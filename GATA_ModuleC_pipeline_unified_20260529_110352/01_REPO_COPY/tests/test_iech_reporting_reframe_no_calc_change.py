from __future__ import annotations

from pathlib import Path


def test_step7_audit_declares_r10_a1_person_day_contract():
    repo_root = Path(__file__).resolve().parents[1]
    step7 = (repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "R10_A1_CANONICAL_BURDEN" in step7
    assert "population_smoke_day_burden_proxy_equals_smoke_days_times_population_total" in step7
    assert "classified smoke-proxy person-days" in step7

