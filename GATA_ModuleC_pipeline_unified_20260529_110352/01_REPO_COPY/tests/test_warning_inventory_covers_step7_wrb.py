from pathlib import Path
import sys


def test_warning_inventory_covers_step7_wrb(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as pipe  # type: ignore

    qa = tmp_path / 'qa'
    qa.mkdir()
    (qa / 'step7_matriz_causal_stderr.txt').write_text('ERROR 1: Failed to compute statistics, no valid pixels found in sampling\n', encoding='utf-8')
    (qa / 'step7_matriz_causal_stdout.txt').write_text('', encoding='utf-8')
    (qa / 'run_log.txt').write_text('', encoding='utf-8')
    (qa / 'report_auditoria_v2.txt').write_text('', encoding='utf-8')
    pipe.refresh_warning_inventory_from_runtime_logs(tmp_path)
    rows = pipe.read_csv_rows(qa / 'warning_inventory.tsv')[1]
    assert any(r['context'] == 'STEP7_STDERR' for r in rows)
    assert any(r['classification'] == 'EXPECTED_NONBLOCKING_ZERO_BURN_MASK' for r in rows)


def test_warning_inventory_classifies_known_step7_nonblocking_warnings(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as pipe  # type: ignore

    qa = tmp_path / 'qa'
    qa.mkdir()
    (qa / 'step7_matriz_causal_stderr.txt').write_text(
        '\n'.join([
            'Warning 1: unable to open database file: this file is a WAL-enabled database. It cannot be opened because it is presumably read-only or in a read-only directory. Retrying with IMMUTABLE=YES open option',
            'C:\\OSGEO4~1\\apps\\qgis-ltr\\python\\plugins\\processing\\algs\\qgis\\StatisticsByCategories.py:125: DeprecationWarning: QgsProcessingAlgorithm.parameterAsFields() is deprecated',
        ]),
        encoding='utf-8',
    )
    (qa / 'step7_matriz_causal_stdout.txt').write_text('', encoding='utf-8')
    (qa / 'run_log.txt').write_text('', encoding='utf-8')
    (qa / 'report_auditoria_v2.txt').write_text('', encoding='utf-8')

    pipe.refresh_warning_inventory_from_runtime_logs(tmp_path)
    rows = pipe.read_csv_rows(qa / 'warning_inventory.tsv')[1]
    assert all(r['status'] == 'PASS' for r in rows)
    assert all(r['classification'] == 'WARN_CLASSIFIED_NONBLOCKING' for r in rows)
