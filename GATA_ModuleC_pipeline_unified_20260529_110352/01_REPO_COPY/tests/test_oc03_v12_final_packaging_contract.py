from __future__ import annotations

from pathlib import Path


def test_pipeline_rebuilds_and_verifies_final_package_after_step9_refresh():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = repo_root / "pipeline" / "moduleC_pipeline_v2.py"
    text = pipeline.read_text(encoding="utf-8", errors="replace")

    assert text.count("build_manifest_and_zip(outputs, deliver_dir, report)") == 1
    assert text.index("build_manifest_and_zip(outputs, deliver_dir, report)") < text.index(
        "create_r10_final_audit_capsule(output_root, report)"
    )
    assert "validate_audit_capsule_gate(output_root, report)" in text
    assert "QA gate decision (final)" in text
    payload_build_idx = text.index("build_manifest_and_zip(outputs, deliver_dir, report)")
    assert 'report.log("END v2 PASS")' not in text[payload_build_idx:]
