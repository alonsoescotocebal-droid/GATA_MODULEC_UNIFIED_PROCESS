from pathlib import Path


def test_wrb_no_admin_unit_only_fallback():
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL' / 'step7_matriz_causal.py').read_text(encoding='utf-8')
    assert 'Contexto edafico territorial (WRB) sobre unidad territorial completa' not in text
    assert 'admin_unit ? annual_burned_area' not in text
    assert 'WRB_STATUS_NOT_APPLICABLE_ZERO_BURN' in text
    assert 'WRB_STATUS_BLOCKED_MISSING' in text
