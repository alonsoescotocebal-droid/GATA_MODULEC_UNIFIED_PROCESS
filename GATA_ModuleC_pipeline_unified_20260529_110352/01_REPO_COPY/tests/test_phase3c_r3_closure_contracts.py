from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import moduleC_pipeline_v2 as pipeline


def test_provenance_contains_git_and_runtime_contract_fields(tmp_path):
    pipeline._write_launcher_provenance(
        tmp_path,
        type("Args", (), {"modulec_datos": "D:/data", "inc_new": "D:/fires", "resume_post_smoke": False})(),
        "2026-07-26T12:00:00",
    )
    pipeline._persist_launcher_exit_code(tmp_path, 0)
    pipeline.write_source_runtime_provenance(tmp_path)
    header = (tmp_path / "qa" / "source_runtime_provenance.tsv").read_text(encoding="utf-8").splitlines()[0]
    for field in ("repo_root", "branch", "HEAD_SHA", "launcher_path", "launcher_start", "launcher_end", "GFAS_root", "ERA5_root", "GHSL_roots", "resume", "network", "installations", "Python", "pytest_environment"):
        assert field in header


def test_launcher_exit_code_is_persisted(tmp_path):
    pipeline._persist_launcher_exit_code(tmp_path, 0)
    assert (tmp_path / "provenance" / "launcher_exit_code.txt").read_text() == "0\n"


def test_r3_static_contracts_require_step9_provenance_and_comparison():
    repo = Path(__file__).resolve().parents[1]
    module = (repo / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8-sig")
    step9 = (repo / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1").read_text(encoding="utf-8-sig")
    assert "provenance_runtime_window_audit.tsv" in module
    assert "launcher_exit_code.txt" in module
    assert "qa\\source_runtime_provenance.tsv" in step9
    assert "phase3c_vs_phase3b_comparison.tsv" in module
