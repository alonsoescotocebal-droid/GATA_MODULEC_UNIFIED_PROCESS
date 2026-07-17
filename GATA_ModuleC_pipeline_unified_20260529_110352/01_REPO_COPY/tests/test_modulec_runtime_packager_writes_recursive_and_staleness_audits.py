from pathlib import Path
import sys
import json
import zipfile


def test_modulec_runtime_packager_writes_recursive_and_staleness_audits(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as mod  # type: ignore

    output_root = tmp_path / '03_outputs'
    qa = output_root / 'qa'
    qa.mkdir(parents=True)
    artifact = qa / 'source_runtime_provenance.tsv'
    artifact.write_text('k\tv\nrepo\ttest\n', encoding='utf-8')

    report = mod.Report(qa / 'report.txt')
    deliver = output_root / 'deliverables_step9'
    manifest_path, _sha_path, zip_path = mod.build_manifest_and_zip([artifact], deliver, report)

    recursive = deliver / 'final_manifest_recursive_audit.tsv'
    stale = deliver / 'final_bundle_staleness_audit.tsv'
    assert recursive.exists()
    assert stale.exists()

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    names = {row['name'] for row in manifest}
    assert 'qa/source_runtime_provenance.tsv' in names
    assert 'deliverables_step9/final_manifest_recursive_audit.tsv' in names
    assert 'deliverables_step9/final_bundle_staleness_audit.tsv' in names

    with zipfile.ZipFile(zip_path) as zf:
        zip_names = set(zf.namelist())
    assert 'deliverables_step9/final_manifest_recursive_audit.tsv' in zip_names
    assert 'deliverables_step9/final_bundle_staleness_audit.tsv' in zip_names
