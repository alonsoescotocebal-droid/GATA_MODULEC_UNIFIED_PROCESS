from __future__ import annotations

from pathlib import Path


def test_step9_emits_recursive_manifest_audit():
    repo_root = Path(__file__).resolve().parents[1]
    step9 = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1"
    text = step9.read_text(encoding="utf-8", errors="replace")

    assert "Get-ChildItem -Recurse -File $bundleDir" in text
    assert "final_manifest_recursive_audit.tsv" in text
    assert "final_manifest.json" in text
    assert "& $R6KRefreshScript -OutputRoot $modcOut" in text
    assert r"ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\03_outputs" not in text



def test_step9_uses_current_required_artifacts_contract():
    repo_root = Path(__file__).resolve().parents[1]
    step9 = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1"
    text = step9.read_text(encoding="utf-8", errors="replace")

    assert r"brief\deliverables_step8\ModuleC_STEP8_BRIEF_CAUSAL_deliverables.zip" in text
    assert r"qa\iech_reporting_reframe_audit.tsv" in text
    assert r"qa\iech_reporting_semantics_audit.tsv" in text
    assert r"qa\smoke_route_hypothesis_test.md" not in text
    assert r"qa\gfas_pm2p5fire_portugal_xyz.csv" not in text



def test_r6k_refresh_tracks_current_portuguese_aq_anchor_contract():
    repo_root = Path(__file__).resolve().parents[1]
    r6k = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "r6k_refresh_runtime_closure_decision.ps1"
    text = r6k.read_text(encoding="utf-8", errors="replace")

    assert "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_AND_POPULATION_BURDEN_SEMANTICS" in text
    assert "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL" in text
    assert "TIER_2_LOCAL_SMOKE_PROXY_VALIDATED_BY_AQ" in text
    assert "LOCAL_AQ_ANCHORED_PROXY" in text
    assert "population_smoke_burden_proxy" in text
    assert "OPERATIONAL_TERRITORIAL_SMOKE_DAY_BURDEN_PROXY" in text
    assert "population_smoke_day_burden_proxy_formula: smoke_days * population_total" in text
    assert r"qa\portuguese_aq_validation_gate.tsv" in text
    assert "GO_WITH_LOCAL_AQ_ANCHOR_AND_LOW_N_DIRECTIONAL_CONCORDANCE" not in text
    assert "LOCAL_AQ_LOW_N_DIRECTIONAL_CONCORDANCE_ALLOWED" not in text
    assert "local_aq_dataset_inventory.tsv" not in text



def test_step9_refreshes_r6k_before_manifest_packaging():
    repo_root = Path(__file__).resolve().parents[1]
    step9 = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1"
    text = step9.read_text(encoding="utf-8", errors="replace")

    assert text.index("& $R6KRefreshScript -OutputRoot $modcOut") < text.index('$manifestPath = Join-Path $outDir "final_manifest.json"')
    assert "$staleStep9Meta = @(" in text
    assert r"qa\global_audit_status_scan.tsv" in text
    assert r"qa\global_audit_status_scan.md" in text
    assert r"qa\r6k_runtime_closure_refresh_audit.tsv" in text

