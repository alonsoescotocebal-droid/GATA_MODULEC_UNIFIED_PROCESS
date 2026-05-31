#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

STATE_PATH_SCOPE_PASS = "PATH_SCOPE_PASS"
STATE_BLOCKED_PATH_DESYNC = "BLOCKED_PATH_DESYNC"
STATE_BLOCKED_FORBIDDEN_CODE_ROOT = "BLOCKED_FORBIDDEN_CODE_ROOT"
STATE_BLOCKED_REPO_ROOT_MISMATCH = "BLOCKED_REPO_ROOT_MISMATCH"
STATE_BLOCKED_BRANCH_MISMATCH = "BLOCKED_BRANCH_MISMATCH"
STATE_BLOCKED_BASE_SHA_MISMATCH = "BLOCKED_BASE_SHA_MISMATCH"
STATE_BLOCKED_DIRTY_TREE_BEFORE_BASELINE = "BLOCKED_DIRTY_TREE_BEFORE_BASELINE"
STATE_BLOCKED_DATA_ROOT_MISSING = "BLOCKED_DATA_ROOT_MISSING"
STATE_BLOCKED_OUTPUT_ROOT_PARENT_MISSING = "BLOCKED_OUTPUT_ROOT_PARENT_MISSING"
STATE_BLOCKED_OUTPUT_ROOT_INSIDE_REPO = "BLOCKED_OUTPUT_ROOT_INSIDE_REPO"
STATE_BLOCKED_CODE_WRITE_OUTSIDE_GITHUB_REPO = "BLOCKED_CODE_WRITE_OUTSIDE_GITHUB_REPO"


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def norm_path(p: Path) -> str:
    try:
        resolved = p.resolve()
    except Exception:
        resolved = Path(os.path.abspath(str(p)))
    return os.path.normcase(os.path.normpath(str(resolved)))


def is_same_or_subpath(path: Path, prefix: Path) -> bool:
    n_path = norm_path(path)
    n_prefix = norm_path(prefix)
    return n_path == n_prefix or n_path.startswith(n_prefix + os.sep)


def run_git(repo_root: Path, args: List[str]) -> Tuple[int, str, str]:
    git_candidates = [
        shutil.which("git"),
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
    ]
    git_bin = None
    for cand in git_candidates:
        if cand and Path(cand).exists():
            git_bin = cand
            break
    if git_bin is None:
        git_bin = "git"
    try:
        proc = subprocess.run(
            [git_bin, "-C", str(repo_root)] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 127, "", str(exc)


def write_report(output_root: Path, rows: List[Dict[str, str]]) -> None:
    qa_dir = output_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_path = qa_dir / "path_scope_guard_report.tsv"
    with report_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "check_id",
                "status",
                "observed",
                "expected",
                "detail",
            ],
            delimiter="\t",
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)


def load_config(config_path: Path) -> Dict[str, str]:
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    required = [
        "EXPECTED_REPO_ROOT",
        "EXPECTED_BRANCH",
        "EXPECTED_BASE_SHA",
        "FORBIDDEN_CODE_ROOT",
        "DATA_ROOT_ALLOWED_PREFIX",
        "OUTPUT_ROOT_ALLOWED_PREFIX",
    ]
    missing = [k for k in required if not str(payload.get(k, "")).strip()]
    if missing:
        raise RuntimeError("Missing keys in canonical path config: " + ", ".join(missing))
    return {k: str(payload[k]).strip() for k in required}


def evaluate(
    repo_root: Path,
    pipeline_root: Path,
    data_root: Path,
    output_root: Path,
    cfg: Dict[str, str],
    enforce_clean_tree: bool = True,
) -> Tuple[str, List[Dict[str, str]]]:
    rows: List[Dict[str, str]] = []
    blockers: List[str] = []

    def add(check_id: str, status: str, observed: str, expected: str, detail: str, counts_as_blocker: bool = True) -> None:
        rows.append(
            {
                "timestamp": now_iso(),
                "check_id": check_id,
                "status": status,
                "observed": observed,
                "expected": expected,
                "detail": detail,
            }
        )
        if status.startswith("BLOCKED_") and counts_as_blocker:
            blockers.append(status)

    expected_repo_root = Path(cfg["EXPECTED_REPO_ROOT"])
    expected_branch = cfg["EXPECTED_BRANCH"]
    expected_base_sha = cfg["EXPECTED_BASE_SHA"]
    forbidden_code_root = Path(cfg["FORBIDDEN_CODE_ROOT"])
    data_prefix = Path(cfg["DATA_ROOT_ALLOWED_PREFIX"])
    output_prefix = Path(cfg["OUTPUT_ROOT_ALLOWED_PREFIX"])

    if is_same_or_subpath(pipeline_root, forbidden_code_root):
        add(
            "C001_forbidden_code_root",
            STATE_BLOCKED_FORBIDDEN_CODE_ROOT,
            str(pipeline_root),
            str(forbidden_code_root),
            "Runner path is inside forbidden lateral code root.",
        )
    else:
        add(
            "C001_forbidden_code_root",
            "PASS",
            str(pipeline_root),
            f"not under {forbidden_code_root}",
            "Runner path is not inside forbidden lateral code root.",
        )

    if norm_path(repo_root) != norm_path(expected_repo_root):
        add(
            "C002_repo_root",
            STATE_BLOCKED_REPO_ROOT_MISMATCH,
            str(repo_root),
            str(expected_repo_root),
            "Repo root must match canonical repository.",
        )
    else:
        add(
            "C002_repo_root",
            "PASS",
            str(repo_root),
            str(expected_repo_root),
            "Repo root matches canonical repository.",
        )

    if not is_same_or_subpath(pipeline_root, repo_root):
        add(
            "C003_code_write_scope",
            STATE_BLOCKED_CODE_WRITE_OUTSIDE_GITHUB_REPO,
            str(pipeline_root),
            str(repo_root),
            "Pipeline root is outside canonical repo scope.",
        )
    else:
        add(
            "C003_code_write_scope",
            "PASS",
            str(pipeline_root),
            str(repo_root),
            "Pipeline root is inside canonical repo scope.",
        )

    rc, branch, err = run_git(repo_root, ["branch", "--show-current"])
    if rc != 0:
        add(
            "G001_branch",
            STATE_BLOCKED_BRANCH_MISMATCH,
            f"git error: {err}",
            expected_branch,
            "Could not read git branch.",
        )
    elif branch != expected_branch:
        add("G001_branch", STATE_BLOCKED_BRANCH_MISMATCH, branch, expected_branch, "Branch mismatch.")
    else:
        add("G001_branch", "PASS", branch, expected_branch, "Branch matches canonical branch.")

    rc, head, err = run_git(repo_root, ["rev-parse", "HEAD"])
    if rc != 0:
        add(
            "G002_base_sha",
            STATE_BLOCKED_BASE_SHA_MISMATCH,
            f"git error: {err}",
            expected_base_sha,
            "Could not read HEAD.",
        )
    else:
        rc_anc, _out, _err = run_git(repo_root, ["merge-base", "--is-ancestor", expected_base_sha, head])
        if rc_anc != 0:
            add(
                "G002_base_sha",
                STATE_BLOCKED_BASE_SHA_MISMATCH,
                head,
                expected_base_sha,
                "HEAD is not descendant of expected base SHA.",
            )
        else:
            add(
                "G002_base_sha",
                "PASS",
                head,
                f"descendant of {expected_base_sha}",
                "HEAD lineage includes expected base SHA.",
            )

    rc, status_short, err = run_git(repo_root, ["status", "--short"])
    if rc != 0:
        add(
            "G003_dirty_tree",
            STATE_BLOCKED_DIRTY_TREE_BEFORE_BASELINE,
            f"git error: {err}",
            "clean working tree",
            "Could not read git status.",
        )
    elif status_short.strip() != "":
        if enforce_clean_tree:
            add(
                "G003_dirty_tree",
                STATE_BLOCKED_DIRTY_TREE_BEFORE_BASELINE,
                status_short.replace("\n", " | "),
                "clean working tree",
                "Working tree must be clean before baseline gate.",
                counts_as_blocker=True,
            )
        else:
            add(
                "G003_dirty_tree",
                STATE_BLOCKED_DIRTY_TREE_BEFORE_BASELINE,
                status_short.replace("\n", " | "),
                "clean working tree",
                "Dirty tree reported as diagnostic only (non-blocking by caller policy).",
                counts_as_blocker=False,
            )
    else:
        add("G003_dirty_tree", "PASS", "clean", "clean", "Working tree is clean.")

    if not data_root.exists():
        add(
            "P001_data_root_exists",
            STATE_BLOCKED_DATA_ROOT_MISSING,
            str(data_root),
            f"existing path under {data_prefix}",
            "Data root is missing.",
        )
    elif not is_same_or_subpath(data_root, data_prefix):
        add(
            "P001_data_root_exists",
            STATE_BLOCKED_PATH_DESYNC,
            str(data_root),
            str(data_prefix),
            "Data root is outside allowed prefix.",
        )
    else:
        add(
            "P001_data_root_exists",
            "PASS",
            str(data_root),
            str(data_prefix),
            "Data root exists under allowed prefix.",
        )

    output_parent = output_root.parent
    if not output_parent.exists():
        add(
            "P002_output_parent",
            STATE_BLOCKED_OUTPUT_ROOT_PARENT_MISSING,
            str(output_parent),
            f"existing parent under {output_prefix}",
            "Output root parent does not exist.",
        )
    elif is_same_or_subpath(output_root, repo_root):
        add(
            "P002_output_parent",
            STATE_BLOCKED_OUTPUT_ROOT_INSIDE_REPO,
            str(output_root),
            "outside repository",
            "Output root cannot be inside canonical repo.",
        )
    elif not is_same_or_subpath(output_root, output_prefix):
        add(
            "P002_output_parent",
            STATE_BLOCKED_PATH_DESYNC,
            str(output_root),
            str(output_prefix),
            "Output root is outside allowed prefix.",
        )
    else:
        add(
            "P002_output_parent",
            "PASS",
            str(output_root),
            str(output_prefix),
            "Output root parent exists and path is under allowed prefix.",
        )

    if blockers:
        overall = STATE_BLOCKED_PATH_DESYNC
        detail = " | ".join(dict.fromkeys(blockers))
    else:
        overall = STATE_PATH_SCOPE_PASS
        detail = "All path scope checks passed."

    add("SUMMARY_path_scope_decision", overall, overall, STATE_PATH_SCOPE_PASS, detail)
    return overall, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--pipeline-root", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--config-path", required=False, default=None)
    ap.add_argument("--enforce-clean-tree", required=False, default="1")
    args = ap.parse_args()

    repo_root = Path(args.repo_root)
    pipeline_root = Path(args.pipeline_root)
    data_root = Path(args.data_root)
    output_root = Path(args.output_root)

    enforce_clean_tree = str(args.enforce_clean_tree).strip().lower() not in ("0", "false", "no")

    if args.config_path:
        config_path = Path(args.config_path)
    else:
        config_path = repo_root / "config" / "module_c_canonical_paths.json"

    if not config_path.exists():
        print(f"[NO-GO] Missing canonical config: {config_path}")
        return 2

    try:
        cfg = load_config(config_path)
        overall, rows = evaluate(repo_root, pipeline_root, data_root, output_root, cfg, enforce_clean_tree=enforce_clean_tree)
        write_report(output_root, rows)
        print(overall)
        if overall != STATE_PATH_SCOPE_PASS:
            return 2
        return 0
    except Exception as exc:
        print(f"[NO-GO] path_scope_guard exception: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
