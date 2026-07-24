from __future__ import annotations

from pathlib import Path


def test_pipeline_rebuilds_and_verifies_final_package_after_step9_refresh():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = repo_root / "pipeline" / "moduleC_pipeline_v2.py"
    text = pipeline.read_text(encoding="utf-8", errors="replace")

    assert text.count("build_manifest_and_zip(outputs, deliver_dir, report)") == 1
    assert "QA gate decision (final)" in text
    final_build_idx = text.rfind("build_manifest_and_zip(outputs, deliver_dir, report)")
    assert 'report.log("END v2 PASS")' not in text[final_build_idx:]
