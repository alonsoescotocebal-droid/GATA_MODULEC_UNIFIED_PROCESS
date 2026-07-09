from __future__ import annotations

from pathlib import Path


def test_step7_audit_declares_no_numeric_change_contract():
    repo_root = Path(__file__).resolve().parents[1]
    step7 = (repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "NO_NUMERIC_CHANGE_TO_POPULATION_SMOKE_BURDEN_PROXY_PERSON_HOURS" in step7
    assert "population_smoke_burden_proxy_equals_expo_person_hours" in step7
    assert "population_smoke_burden_proxy_equals_smoke_hours_times_population_total" in step7

