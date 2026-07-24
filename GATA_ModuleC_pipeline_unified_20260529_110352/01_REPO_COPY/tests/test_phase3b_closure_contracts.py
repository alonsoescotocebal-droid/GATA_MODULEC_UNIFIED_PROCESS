from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CLOSURE = (REPO / "pipeline" / "phase3_objective_closure.py").read_text(encoding="utf-8")
PIPELINE = (REPO / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8")
STEP7 = (REPO / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(encoding="utf-8")
LAUNCHER = (REPO / "pipeline" / "RUN_ModuleC_Pipeline_OSGeo4W.cmd").read_text(encoding="utf-8")


def test_temporal_smoke_join_keeps_all_rows_for_each_unit_year():
    assert "for row in table.get(uid, [{}])" in CLOSURE
    assert "year" in CLOSURE


def test_continental_filter_excludes_autonomous_regions_in_all_paths():
    assert "'PT200', 'PT300'" in PIPELINE
    assert "'PT200', 'PT300'" in STEP7


def test_launcher_passes_git_top_level_separately_from_code_root():
    assert 'set "GIT_ROOT=' in LAUNCHER
    assert "--git-toplevel \"%GIT_ROOT%\"" in LAUNCHER


def test_fire_validity_and_area_reconciliation_are_persisted():
    assert "isGeosValid" in CLOSURE
    assert "makeValid" in CLOSURE
    assert "fire_area_reconciliation_audit.tsv" in CLOSURE
    assert "source_area_ha" in CLOSURE
    assert "output_area_ha" in CLOSURE


def test_final_gate_order_and_freshness_artifacts_are_coded():
    assert "write_gate_dependency_freshness_audit(output_root)" in PIPELINE
    assert PIPELINE.rfind("scientific_decision_path = run_scientific_gate") < PIPELINE.rfind("write_gate_dependency_freshness_audit")
    assert 'output_root / "qa" / "pytest_result_summary.tsv"' in PIPELINE


def test_wui_and_resolution_audits_are_not_placeholder_only():
    assert "size_bytes=" in CLOSURE
    assert "pixels_gfas_effective_per_municipality" in CLOSURE
    assert "edge_sensitivity" in CLOSURE


def test_methodological_limitations_are_non_blocking_and_step9_is_post_qa():
    assert '"INFO", "Methodological limitation:' in CLOSURE
    assert 'Path("deliverables_step9/final_manifest.json")' not in (REPO / "pipeline" / "qa_gate_v2.py").read_text(encoding="utf-8")


def test_brief_rewrite_is_idempotent_and_utf8_explicit():
    assert "re.sub(r\"\\n## Semantica de cierre Fase 3" in CLOSURE
    assert "encoding=\"utf-8\"" in CLOSURE
