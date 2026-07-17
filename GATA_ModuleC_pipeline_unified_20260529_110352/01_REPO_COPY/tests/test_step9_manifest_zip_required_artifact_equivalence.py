from pathlib import Path


def test_step9_manifest_zip_required_artifact_equivalence():
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP9_FINAL_MASTER_PACK' / 'run_step9_final_master_pack.ps1').read_text(encoding='utf-8')
    for token in (
        'qa\\source_runtime_provenance.tsv',
        'qa\\iech_aggregate_consistency_audit.tsv',
        'qa\\scenario_aggregate_consistency_audit.tsv',
        'qa\\wrb_method_consistency_audit.tsv',
    ):
        assert token in text