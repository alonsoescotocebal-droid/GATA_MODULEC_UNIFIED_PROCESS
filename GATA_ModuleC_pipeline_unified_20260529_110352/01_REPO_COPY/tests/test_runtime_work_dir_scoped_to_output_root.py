from pathlib import Path


def test_runtime_work_dir_is_scoped_to_output_root():
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / 'pipeline' / 'moduleC_pipeline_v2.py').read_text(encoding='utf-8')
    assert 'work_dir = out_dir / "_runtime_work"' in text
    assert 'work_dir = modulec_root / "02_work"' not in text
