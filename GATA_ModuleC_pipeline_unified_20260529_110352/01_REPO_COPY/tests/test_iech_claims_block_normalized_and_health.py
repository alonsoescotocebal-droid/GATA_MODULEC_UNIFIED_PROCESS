from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_gate_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "pipeline" / "scientific_threshold_gate.py"
    spec = importlib.util.spec_from_file_location("scientific_threshold_gate", str(mod_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_brief_claim_audit_blocks_normalized_and_health_claims(tmp_path):
    mod = _load_gate_module()
    brief = tmp_path / "Brief_Politica_IECH_2030.md"
    brief.write_text(
        "Normalized IECH is reported here.\n"
        "This brief also claims health exposure.\n",
        encoding="utf-8",
    )

    hits = mod.audit_brief_claims(brief, ["BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM"])

    assert any(hit[2] == "BLOCKED_NORMALIZED_IECH_CLAIM" for hit in hits)
    assert any(hit[2] == "BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM" for hit in hits)


def test_semantic_audit_blocks_forbidden_normalized_claim_counts(tmp_path):
    mod = _load_gate_module()
    audit_tsv = tmp_path / "iech_reporting_reframe_audit.tsv"
    audit_tsv.write_text(
        "metric\tvalue\tstatus\tdetail\n"
        "IECH_REPORTING_REFRAME_STATUS\tPASS\tPASS\t\n"
        "population_smoke_day_burden_proxy_column_present\t1\tPASS\t\n"
        "population_total_column_present\t1\tPASS\t\n"
        "claim_status_proxy_not_normalized\tOPERATIONAL_TERRITORIAL_SMOKE_DAY_BURDEN_PROXY\tPASS\t\n"
        "legacy_physical_burden_columns_empty\t1\tPASS\t\n"
        "population_smoke_day_burden_proxy_equals_smoke_days_times_population_total\t1\tPASS\t\n"
        "forbidden_normalized_IECH_claims\t1\tPASS\t\n"
        "forbidden_health_exposure_claims\t0\tPASS\t\n",
        encoding="utf-8",
    )

    status, obs = mod.evaluate_iech_proxy_semantics(audit_tsv)

    assert status == "BLOCKED_PROXY_BURDEN_SEMANTICS"
    assert "forbidden_normalized_IECH_claims=1" in obs
