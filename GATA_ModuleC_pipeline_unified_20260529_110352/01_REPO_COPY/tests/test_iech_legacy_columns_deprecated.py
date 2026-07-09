from __future__ import annotations

from pathlib import Path


def test_legacy_iech_columns_are_explicitly_deprecated_but_preserved_for_compatibility():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")
    step7 = (repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "legacy_IECH_label_deprecated" in pipeline
    assert "legacy_IECH_deprecated_if_present" in step7
    assert '"IECH"' in pipeline
