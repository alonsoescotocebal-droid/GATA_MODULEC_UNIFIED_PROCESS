from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTAINER = ROOT.parent
GIT_ROOT = CONTAINER.parent
LAUNCHER = CONTAINER / "02_LAUNCHERS" / "run_modulec_canonical.ps1"
GUARD = ROOT / "pipeline" / "path_scope_guard.py"
CONFIG = ROOT / "config" / "module_c_canonical_paths.json"
SEMANTIC_TSV = CONTAINER / "00_CANON" / "MODULE_C_OBJECTIVE_EXECUTION_CONTRACT.tsv"

PHASE1B_SCENARIOS = (
    "launcher_mode_preflight", "launcher_mode_smoke", "launcher_mode_full", "full_without_authorization",
    "full_with_authorization_deferred", "expected_head_valid", "expected_head_invalid", "branch_exact",
    "tree_clean", "git_toplevel_distinct", "pipeline_code_root_exact", "forbidden_code_root",
    "modulec_data_root", "portuguese_agencies_root", "recovery_root", "incendios_root", "gfas_effective_root",
    "data_root_missing", "data_root_outside_allowlist", "output_root_under_03_runtimes", "output_root_inside_repo",
    "output_root_preexisting", "resume_disabled", "environment_output_cleared", "environment_data_cleared",
    "environment_runtime_cleared", "environment_repo_cleared", "argparse_error_unpatched", "guard_cli_integration",
    "guard_typo_regression", "historical_ps_block", "historical_cmd_block", "root_tmp_block",
    "semantic_contract_ids", "semantic_contract_status", "producer_inventory", "provenance_inventory",
    "scientific_runtime_not_started",
)


def load_guard():
    spec = importlib.util.spec_from_file_location("phase1b_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_phase1b_scenario_matrix_has_required_coverage() -> None:
    assert len(PHASE1B_SCENARIOS) >= 37
    assert len(set(PHASE1B_SCENARIOS)) == len(PHASE1B_SCENARIOS)


def test_integral_launcher_contract_and_full_block() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "ValidateSet('Preflight','Smoke','Full')" in text
    for token in ("ExpectedHeadSha", "PortugueseAgenciesDataRoot", "Recovery20152024Root", "CanonicalConfig", "AllowFullRuntime", "path_scope_guard.py"):
        assert token in text
    assert "BLOCKED_FULL_RUNTIME_NOT_AUTHORIZED" in text
    assert "--mode ($Mode.ToLowerInvariant())" in text


def test_guard_contract_separates_git_and_code_roots() -> None:
    text = GUARD.read_text(encoding="utf-8")
    for token in ("--git-toplevel", "--pipeline-code-root", "--expected-head-sha", "--allow-resume", "data_prefixes"):
        assert token in text
    assert "data_prefix}" not in text


def test_missing_data_root_blocks_without_name_error() -> None:
    guard = load_guard()
    cfg = guard.load_config(CONFIG)
    output = ROOT / "_phase1b_test_output_not_created"
    state, rows = guard.evaluate(ROOT, ROOT / "pipeline", ROOT / "does-not-exist", output, cfg, enforce_clean_tree=False)
    assert state.startswith("BLOCKED_")
    assert any(row["check_id"] == "P001_data_root_exists" and row["status"].startswith("BLOCKED_") for row in rows)


def test_machine_contract_exact_rows_and_status() -> None:
    rows = list(csv.DictReader(SEMANTIC_TSV.open(encoding="utf-8-sig"), delimiter="\t"))
    assert {row["objective_id"] for row in rows} == {"OC-05", "OC-07", "OC-09", "MUNICIPAL_SIGNAL"}
    assert all(row["runtime_status"] == "UNVERIFIED_UNDER_CANONICAL_CLEAN_RUNTIME" for row in rows)


def test_argparse_monkeypatch_removed() -> None:
    text = (ROOT / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8-sig")
    assert "ArgumentParser.parse_args =" not in text
    assert "ArgumentParser.error =" not in text
    assert "_r7q_runtime_cli_contract_patch()" not in text.replace("def _r7q_runtime_cli_contract_patch():", "")


def test_historical_launchers_are_executable_blocks() -> None:
    paths = [
        ROOT / "pipeline" / "run_pipeline_v2.ps1",
        ROOT / "pipeline" / "run_pipeline_v2.cmd",
        ROOT / "run_full_oc03_oc03c_runtime.ps1",
        GIT_ROOT / "tmp_launch_modulec_runtime.ps1",
        GIT_ROOT / "tmp_launch_modulec_runtime_v2.ps1",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        assert "BLOCKED_NON_CANONICAL_LAUNCHER" in text
        assert "run_modulec_canonical.ps1" in text


def test_canonical_config_has_distinct_root_names() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    assert cfg["EXPECTED_GIT_TOPLEVEL"] == str(GIT_ROOT)
    assert cfg["EXPECTED_PIPELINE_CODE_ROOT"] == str(ROOT)
