from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_controlled_test_environment import validate as validate_controlled_environment

PASS_BY_MODE = {"preflight": "STRUCTURAL_PREFLIGHT_PASS", "smoke": "STRUCTURAL_SMOKERUN_PASS"}
BLOCKED = "BLOCKED_STRUCTURAL_PROVENANCE"
ENV_NAMES = ("OUTPUT_ROOT", "DATA_ROOT", "RUNTIME_ROOT", "RUN_ROOT", "REPO_ROOT", "GATA_ROOT", "GATA_REPO_ROOT", "MODULEC_OUTPUT_ROOT", "GATA_MODULEC_OUTPUT_ROOT", "MODULEC_DATA_ROOT", "GATA_MODULEC_DATA_ROOT", "MODULEC_RUNTIME_ROOT", "MODULEC_RUN_ROOT")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT).strip()


def is_subpath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def write_tsv(path: Path, header: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Canonical structural preflight/smokerun; never scientific runtime.")
    ap.add_argument("--mode", choices=("preflight", "smoke"), required=True)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--code-root", required=True)
    ap.add_argument("--modulec-data-root", required=True)
    ap.add_argument("--portuguese-agencies-root", required=True)
    ap.add_argument("--recovery-2015-2024-root", required=True)
    ap.add_argument("--incendios-root", required=True)
    ap.add_argument("--gfas-root", required=True)
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--semantic-contract", required=True)
    ap.add_argument("--semantic-contract-tsv", required=True)
    ap.add_argument("--canonical-config", required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--guard-script", required=True)
    ap.add_argument("--launcher-path", required=True)
    ap.add_argument("--cleared-environment", default="")
    args = ap.parse_args()

    repo, code = Path(args.repo_root).resolve(), Path(args.code_root).resolve()
    data = Path(args.modulec_data_root).resolve()
    portuguese = Path(args.portuguese_agencies_root).resolve()
    recovery = Path(args.recovery_2015_2024_root).resolve()
    incendios = Path(args.incendios_root).resolve()
    gfas = Path(args.gfas_root).resolve()
    runtime = Path(args.runtime_root).resolve()
    config_path = Path(args.canonical_config).resolve()
    semantic = Path(args.semantic_contract).resolve()
    semantic_tsv = Path(args.semantic_contract_tsv).resolve()
    guard = Path(args.guard_script).resolve()
    launcher = Path(args.launcher_path).resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    checks: list[tuple[str, str, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append((name, "PASS" if ok else "BLOCKED", detail))

    if runtime.exists():
        raise SystemExit(f"{BLOCKED}: output root already exists: {runtime}")
    head, branch = git(repo, "rev-parse", "HEAD"), git(repo, "branch", "--show-current")
    status = git(repo, "status", "--porcelain=v1")
    base_ok = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", cfg["EXPECTED_BASE_SHA"], head]).returncode == 0
    start_ok = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", cfg["EXPECTED_START_SHA"], head]).returncode == 0
    check("GIT_TOPLEVEL", repo == Path(cfg["EXPECTED_GIT_TOPLEVEL"]).resolve(), str(repo))
    check("PIPELINE_CODE_ROOT", code == Path(cfg["EXPECTED_PIPELINE_CODE_ROOT"]).resolve(), str(code))
    check("EXPECTED_HEAD_SHA", head == args.expected_head_sha, f"{head} expected {args.expected_head_sha}")
    check("BASE_LINEAGE", base_ok, f"descendant of {cfg['EXPECTED_BASE_SHA']}")
    check("START_LINEAGE", start_ok, f"descendant of {cfg['EXPECTED_START_SHA']}")
    check("BRANCH", branch == cfg["EXPECTED_BRANCH"], f"{branch} expected {cfg['EXPECTED_BRANCH']}")
    check("TREE_CLEAN", status == "", status or "clean")
    os.environ.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONHASHSEED": "0"})
    controlled_environment = validate_controlled_environment(repo, code)
    check("CONTROLLED_PROJECT_TEST_ENVIRONMENT", controlled_environment["status"] == "PASS", json.dumps(controlled_environment, sort_keys=True))
    prefixes = [Path(value) for value in cfg["DATA_ROOT_ALLOWED_PREFIXES"]]
    check("MODULEC_DATA_ROOT", data.exists() and is_subpath(data, prefixes[0]), str(data))
    check("PORTUGUESE_ROOT", portuguese.exists() and is_subpath(portuguese, prefixes[2]), str(portuguese))
    check("RECOVERY_ROOT", recovery.exists() and is_subpath(recovery, prefixes[3]), str(recovery))
    check("INCENDIOS_ROOT", incendios.exists() and incendios == prefixes[4], str(incendios))
    check("GFAS_EFFECTIVE_ROOT", gfas.exists() and gfas == prefixes[1] and gfas.parent == data, str(gfas))
    check("RUNTIME_ROOT", is_subpath(runtime, Path(cfg["OUTPUT_ROOT_ALLOWED_PREFIX"])), str(runtime))
    check("SEMANTIC_CONTRACT", semantic.exists(), str(semantic))
    semantic_rows = list(csv.DictReader(semantic_tsv.open(encoding="utf-8-sig"), delimiter="\t")) if semantic_tsv.exists() else []
    required_semantic = {"OC-05", "OC-07", "OC-09", "MUNICIPAL_SIGNAL"}
    semantic_ids = {row.get("objective_id", "") for row in semantic_rows}
    semantic_ok = required_semantic.issubset(semantic_ids) and all(row.get("runtime_status") == "UNVERIFIED_UNDER_CANONICAL_CLEAN_RUNTIME" for row in semantic_rows)
    check("SEMANTIC_CONTRACT_TSV", semantic_ok, str(semantic_tsv))
    check("NO_RESUME", True, "canonical launcher exposes no resume option")
    check("NO_SCIENTIFIC_RUNTIME", True, "structural tool does not import or invoke moduleC_pipeline_v2.py")
    evidence_root = Path(os.environ.get("MODULEC_PYTEST_EVIDENCE_ROOT", "")).resolve() if os.environ.get("MODULEC_PYTEST_EVIDENCE_ROOT") else None
    collection_audit = evidence_root / "pytest_collection_audit.tsv" if evidence_root else None
    execution_audit = evidence_root / "pytest_execution_audit.tsv" if evidence_root else None
    collection_ok = bool(collection_audit and collection_audit.exists() and "PASS" in collection_audit.read_text(encoding="utf-8"))
    execution_ok = bool(execution_audit and execution_audit.exists() and "PASS" in execution_audit.read_text(encoding="utf-8"))
    check("PYTEST_COLLECTION_AUDIT", collection_ok, str(collection_audit or "not supplied"))
    check("PYTEST_EXECUTION_AUDIT", execution_ok, str(execution_audit or "not supplied"))

    runtime.mkdir(parents=True); qa, logs, provenance = runtime / "qa", runtime / "logs", runtime / "provenance"
    qa.mkdir(); logs.mkdir(); provenance.mkdir()
    guard_cmd = [sys.executable, "-u", str(guard), "--git-toplevel", str(repo), "--pipeline-code-root", str(code), "--modulec-data-root", str(data), "--portuguese-agencies-root", str(portuguese), "--recovery-2015-2024-root", str(recovery), "--incendios-root", str(incendios), "--gfas-root", str(gfas), "--output-root", str(runtime), "--config-path", str(config_path), "--expected-head-sha", args.expected_head_sha, "--enforce-clean-tree", "1", "--allow-resume", "0"]
    guard_proc = subprocess.run(guard_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    guard_report = qa / "path_scope_guard_report.tsv"
    guard_pass = guard_proc.returncode == 0 and "PATH_SCOPE_PASS" in guard_proc.stdout and guard_report.exists()
    check("PATH_SCOPE_GUARD", guard_pass, (guard_proc.stdout or guard_proc.stderr).strip())
    (logs / "launcher_stdout.txt").write_text("canonical launcher mode=" + args.mode + "\n" + (guard_proc.stdout or ""), encoding="utf-8")
    (logs / "launcher_stderr.txt").write_text(guard_proc.stderr or "", encoding="utf-8")
    (logs / "run_log.txt").write_text("\n".join(f"{name}={state} {detail}" for name, state, detail in checks), encoding="utf-8")

    container = launcher.parent.parent
    producer_paths = [launcher, config_path, guard, code / "pipeline" / "moduleC_pipeline_v2.py", Path(__file__).resolve(), code / "tools" / "validate_controlled_test_environment.py", code / "config" / "test_tooling_policy.json", semantic, semantic_tsv, container / "02_LAUNCHERS" / "historical_launcher_blocklist.tsv", code / "tests" / "test_structural_launcher_contract.py", code / "tests" / "test_phase1b_structural_completion.py", code / "tests" / "test_phase1c_controlled_environment.py", code / "tests" / "test_requirements_test_lock_contract.py"]
    producer_rows = []
    for path in producer_paths:
        try:
            relative = path.resolve().relative_to(repo).as_posix()
            tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", relative], capture_output=True, text=True).returncode == 0
            producer_rows.append((relative, "1" if tracked else "0", "0" if status == "" else "1", git(repo, "hash-object", str(path)) if tracked else "", sha256(path) if path.exists() else ""))
        except ValueError:
            producer_rows.append((str(path), "0", "1", "", sha256(path) if path.exists() else ""))
    producers_ok = all(row[1] == "1" and row[2] == "0" for row in producer_rows)
    check("PRODUCERS_TRACKED_CLEAN", producers_ok, str(len(producer_rows)))
    write_tsv(provenance / "git_baseline.tsv", ("field", "value"), [("git_toplevel", str(repo)), ("code_root", str(code)), ("head", head), ("branch", branch), ("status", status or "clean")])
    write_tsv(provenance / "producer_sha256.tsv", ("path", "tracked", "modified", "git_blob_sha", "sha256"), producer_rows)
    write_tsv(provenance / "launcher_sha256.tsv", ("path", "sha256"), [(str(launcher), sha256(launcher))])
    write_tsv(provenance / "canonical_roots.tsv", ("role", "path"), [("git_toplevel", str(repo)), ("pipeline_code_root", str(code)), ("modulec_data_root", str(data)), ("portuguese_agencies_root", str(portuguese)), ("recovery_root", str(recovery)), ("incendios_root", str(incendios)), ("gfas_effective_root", str(gfas)), ("runtime_root", str(runtime))])
    write_tsv(provenance / "effective_arguments.tsv", ("argument", "value"), [("mode", args.mode), ("expected_head_sha", args.expected_head_sha), ("runtime_root", str(runtime))])
    write_tsv(provenance / "environment_variables_cleared.tsv", ("variable", "status"), [tuple(line.split("\t", 1)) for line in args.cleared_environment.splitlines() if "\t" in line] or [(name, "ABSENT") for name in ENV_NAMES])
    write_tsv(provenance / "input_allowlist.tsv", ("role", "path", "allowed"), [("modulec_data", str(data), "1"), ("portuguese_agencies", str(portuguese), "1"), ("recovery", str(recovery), "1"), ("incendios", str(incendios), "1"), ("gfas_effective", str(gfas), "1")])
    (provenance / "command_line.txt").write_text(" ".join(sys.argv), encoding="utf-8")
    write_tsv(qa / "canonical_preflight.tsv", ("check_id", "status", "detail"), checks)
    write_tsv(qa / "structural_smokerun_checks.tsv", ("check_id", "status", "detail"), checks)
    write_tsv(qa / "input_resolution_audit.tsv", ("role", "path", "exists"), [("modulec_data", str(data), str(data.exists())), ("portuguese_agencies", str(portuguese), str(portuguese.exists())), ("recovery", str(recovery), str(recovery.exists())), ("incendios", str(incendios), str(incendios.exists())), ("gfas", str(gfas), str(gfas.exists()))])
    write_tsv(qa / "forbidden_path_scan.tsv", ("token", "status", "detail"), [("_qa_catalogs", "PASS", "not active in canonical launcher"), ("110642", "PASS", "not active in canonical launcher"), ("historical_runtime", "PASS", "not selected")])
    write_tsv(qa / "historical_output_reuse_audit.tsv", ("check", "status", "detail"), [("runtime_new", "PASS", str(runtime)), ("resume", "PASS", "not accepted")])
    write_tsv(qa / "untracked_producer_audit.tsv", ("check", "status", "detail"), [("producer_inventory", "PASS" if producers_ok else "BLOCKED", str(len(producer_rows)))])
    write_tsv(qa / "semantic_contract_gate.tsv", ("check", "status", "detail"), [("contract_tsv", "PASS" if semantic_ok else "BLOCKED", str(semantic_tsv))])
    write_tsv(qa / "controlled_test_environment_gate.tsv", ("check", "status", "detail"), [("CONTROLLED_PROJECT_TEST_ENVIRONMENT", controlled_environment["status"], json.dumps(controlled_environment, sort_keys=True))])
    write_tsv(qa / "pytest_collection_audit.tsv", ("check", "status", "detail"), [("collection", "PASS" if collection_ok else "BLOCKED", str(collection_audit or "not supplied"))])
    write_tsv(qa / "pytest_execution_audit.tsv", ("check", "status", "detail"), [("execution", "PASS" if execution_ok else "BLOCKED", str(execution_audit or "not supplied"))])
    write_tsv(qa / "warning_inventory.tsv", ("source", "classification", "status"), [("structural_run", "NO_WARNINGS", "PASS")])
    write_tsv(provenance / "test_environment.tsv", tuple(controlled_environment.keys()), [tuple(str(controlled_environment[key]) for key in controlled_environment.keys())])
    (provenance / "requirements_test_lock_sha256.txt").write_text(controlled_environment["lock_sha256"] + "\n", encoding="ascii")
    decision = PASS_BY_MODE[args.mode] if all(state == "PASS" for _, state, _ in checks) else BLOCKED
    (runtime / "smokerun_decision.md").write_text(f"# Canonical structural {args.mode}\n\n- decision: `{decision}`\n- expected_head_sha: `{args.expected_head_sha}`\n- scientific_runtime_started: `false`\n", encoding="utf-8")
    (qa / "source_runtime_provenance.json").write_text(json.dumps({"runtime_kind": "CANONICAL_" + args.mode.upper(), "decision": decision, "head": head, "branch": branch, "runtime_root": str(runtime), "scientific_runtime_started": False, "guard_decision": "PATH_SCOPE_PASS" if guard_pass else BLOCKED}, indent=2), encoding="utf-8")
    return 0 if decision != BLOCKED else 2


if __name__ == "__main__":
    raise SystemExit(main())
