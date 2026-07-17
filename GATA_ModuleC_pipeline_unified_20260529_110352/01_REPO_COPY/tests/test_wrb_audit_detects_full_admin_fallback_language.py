from pathlib import Path
import sys


def test_wrb_audit_detects_full_admin_fallback_language(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    out = tmp_path
    tables = out / 'tables'
    qa = out / 'qa'
    tables.mkdir()
    qa.mkdir()
    (tables / 'wrb_context_nuts3.csv').write_text('unit_id;dominant_wrb_class;dominant_wrb_share;top_wrb_classes;wrb_context_note;wrb_source;wrb_missing_flag;wrb_method;wrb_coverage_status;wrb_not_applicable_flag\nU1;Cambisols;1.0;Cambisols:1.0;Contexto sobre unidad territorial completa; sin interseccion quemada;src;0;BURNED_AREA_WRB_OVERLAY;PASS_BURNED_AREA_WRB_OVERLAY;0\n', encoding='utf-8')
    (tables / 'wrb_context_municipio.csv').write_text('unit_id;dominant_wrb_class;dominant_wrb_share;top_wrb_classes;wrb_context_note;wrb_source;wrb_missing_flag;wrb_method;wrb_coverage_status;wrb_not_applicable_flag\n', encoding='utf-8')
    step7.write_wrb_method_consistency_audit(out, tables / 'wrb_context_nuts3.csv', tables / 'wrb_context_municipio.csv')
    rows = step7.read_csv_rows(qa / 'wrb_method_consistency_audit.tsv')[1]
    metric = {r['metric']: r for r in rows}
    assert metric['wrb_admin_unit_only_rows']['status'] == 'HOLD'