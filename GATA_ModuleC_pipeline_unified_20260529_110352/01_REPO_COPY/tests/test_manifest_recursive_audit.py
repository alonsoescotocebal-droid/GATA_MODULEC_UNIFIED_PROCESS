from __future__ import annotations

from pathlib import Path


def test_step9_emits_recursive_manifest_audit():
    repo_root = Path(__file__).resolve().parents[1]
    step9 = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1"
    text = step9.read_text(encoding="utf-8", errors="replace")

    assert "Get-ChildItem -Recurse -File $bundleDir" in text
    assert "final_manifest_recursive_audit.tsv" in text
    assert "final_manifest.json" in text
