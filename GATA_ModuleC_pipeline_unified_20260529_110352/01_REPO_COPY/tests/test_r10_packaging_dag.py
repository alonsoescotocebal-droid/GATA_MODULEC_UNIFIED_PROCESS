from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


def _load_pipeline_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def _payload_root(tmp_path: Path) -> tuple[Path, Path, object]:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    qa = root / "qa"
    qa.mkdir(parents=True)
    artifact = qa / "source_runtime_provenance.tsv"
    artifact.write_text("metric\tvalue\ncheckout\tclean\n", encoding="utf-8")
    report = mod.Report(qa / "report.txt")
    return root, artifact, report


def _build_payload(mod, root: Path, artifact: Path, report) -> tuple[Path, Path, Path]:
    return mod.build_manifest_and_zip([artifact], root / "deliverables_step9", report)


def _write_gate(root: Path, final_value: str = "PASS", final_status: str = "PASS") -> None:
    rows = [
        ["capsule_exists", "1", "PASS", ""],
        ["capsule_readable", "1", "PASS", ""],
        ["expected_members_present", "1", "PASS", ""],
        ["forbidden_massive_payload", "0", "PASS", ""],
        ["internal_manifest_valid", "1", "PASS", ""],
        ["external_sha_sidecar_matches", "1", "PASS", ""],
        ["AUDIT_CAPSULE_GATE", final_value, final_status, ""],
    ]
    text = "metric\tvalue\tstatus\tdetail\n" + "\n".join("\t".join(row) for row in rows) + "\n"
    gate = root / "qa" / "audit_capsule_gate.tsv"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(text, encoding="utf-8")


def test_payload_collection_excludes_post_packaging_gate(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    decision = root / "deliverables_step9" / "runtime_scientific_closure_decision.md"
    outputs = {path.as_posix() for path in mod.collect_final_outputs(root, decision)}

    assert (root / "qa" / "audit_capsule_gate.tsv").as_posix() not in outputs


def test_payload_manifest_builds_without_capsule_gate(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root, artifact, report = _payload_root(tmp_path)

    manifest, sha, package = _build_payload(mod, root, artifact, report)

    assert manifest.is_file()
    assert sha.is_file()
    assert package.is_file()
    assert not (root / "qa" / "audit_capsule_gate.tsv").exists()


def test_final_capsule_requires_completed_payload_evidence(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    (root / "qa").mkdir(parents=True)

    with pytest.raises(mod.StageError, match="requires completed payload packaging"):
        mod.create_r10_final_audit_capsule(root, mod.Report(root / "qa" / "report.txt"))


def test_capsule_is_created_after_payload_and_writes_gate(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root, artifact, report = _payload_root(tmp_path)
    _build_payload(mod, root, artifact, report)
    manifest_before = hashlib.sha256((root / "deliverables_step9" / "final_manifest.json").read_bytes()).hexdigest()

    capsule = mod.create_r10_final_audit_capsule(root, report)

    assert capsule.is_file()
    assert (root / "qa" / "audit_capsule_gate.tsv").is_file()
    assert hashlib.sha256((root / "deliverables_step9" / "final_manifest.json").read_bytes()).hexdigest() == manifest_before


def test_final_closure_fails_when_gate_is_missing(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    (root / "qa").mkdir(parents=True)

    with pytest.raises(mod.StageError, match="gate missing"):
        mod.validate_audit_capsule_gate(root, mod.Report(root / "qa" / "report.txt"))


def test_final_closure_fails_when_gate_is_not_pass(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    _write_gate(root, final_value="FAIL", final_status="FAIL")

    with pytest.raises(mod.StageError, match="non-PASS metrics"):
        mod.validate_audit_capsule_gate(root, mod.Report(root / "qa" / "report.txt"))


def test_final_closure_accepts_complete_capsule_gate(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    _write_gate(root)

    mod.validate_audit_capsule_gate(root, mod.Report(root / "qa" / "report.txt"))


def test_packaging_source_has_one_payload_build_and_post_packaging_validation() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8")

    assert text.count("build_manifest_and_zip(outputs, deliver_dir, report)") == 1
    assert text.index("build_manifest_and_zip(outputs, deliver_dir, report)") < text.index(
        "create_r10_final_audit_capsule(output_root, report)"
    )
    assert text.index("create_r10_final_audit_capsule(output_root, report)") < text.index(
        "validate_audit_capsule_gate(output_root, report)"
    )


def test_collect_final_outputs_still_exposes_missing_scientific_artifacts(tmp_path: Path) -> None:
    mod = _load_pipeline_module()
    root = tmp_path / "runtime"
    decision = root / "deliverables_step9" / "runtime_scientific_closure_decision.md"
    outputs = mod.collect_final_outputs(root, decision)

    missing_scientific = root / "qa" / "inputs_resolved.json"
    assert missing_scientific in outputs
    with pytest.raises(mod.StageError, match="Output missing before manifest"):
        mod.build_manifest_and_zip(outputs, root / "deliverables_step9", mod.Report(root / "qa" / "report.txt"))


def test_payload_manifest_is_not_rebuilt_after_audit_envelope() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8")
    section = text[text.index("def complete_post_smoke_runtime("):text.index("def main()")]

    assert section.count("build_manifest_and_zip(outputs, deliver_dir, report)") == 1
    assert "AUDIT_ENVELOPE_CLOSURE PASS" in section
