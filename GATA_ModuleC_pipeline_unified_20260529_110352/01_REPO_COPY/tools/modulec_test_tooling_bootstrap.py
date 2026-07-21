#!/usr/bin/env python3
"""Offline-first, isolated pytest tooling bootstrap for Module C Phase 2A/2B."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODES = ("plan", "download", "install", "collect", "run", "verify", "resume")
NETWORK_MODES = {"download", "install"}
APPROVAL_PREFIX = "APPROVE_TEST_TOOLING_DOWNLOAD"
BLOCKED = "BLOCKED_TEST_TOOLING_BOOTSTRAP"
EXPECTED_BRANCH = "codex/wrb-source-route-repair-b9cb373d"
EXPECTED_START_SHA = "c8aede15846dab5dee0483411082b6c913243f4d"
ALLOWED_PACKAGES = (
    "pytest", "iniconfig", "packaging", "pluggy", "pygments", "colorama",
    "exceptiongroup", "tomli", "typing-extensions", "atomicwrites",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize(path: Path) -> Path:
    return Path(os.path.normcase(os.path.normpath(str(path.resolve()))))


def is_subpath(path: Path, parent: Path) -> bool:
    try:
        normalize(path).relative_to(normalize(parent))
        return True
    except ValueError:
        return False


def git(repo: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def select_pytest(version_info: tuple[int, int, int] | None = None) -> str:
    v = version_info or sys.version_info[:3]
    if v >= (3, 10, 0):
        return "9.1.1"
    if v >= (3, 9, 0):
        return "8.4.2"
    if v >= (3, 8, 0):
        return "8.3.5"
    if v >= (3, 7, 0):
        return "7.4.4"
    raise RuntimeError("BLOCKED_UNSUPPORTED_PYTHON_FOR_CANONICAL_PYTEST")


def runtime_parent(code_root: Path) -> Path:
    return code_root.resolve().parent / "03_RUNTIMES"


def validate_root(repo_root: Path, code_root: Path, bootstrap_root: Path) -> None:
    expected_parent = runtime_parent(code_root)
    if not is_subpath(bootstrap_root, expected_parent) or normalize(bootstrap_root) == normalize(expected_parent):
        raise RuntimeError("BLOCKED_BOOTSTRAP_ROOT_OUTSIDE_03_RUNTIMES")
    if is_subpath(bootstrap_root, code_root) or is_subpath(code_root, bootstrap_root):
        raise RuntimeError("BLOCKED_BOOTSTRAP_ROOT_CODE_ROOT_OVERLAP")


def baseline(repo_root: Path, code_root: Path, expected_head: str) -> dict[str, str]:
    rc, top, err = git(repo_root, "rev-parse", "--show-toplevel")
    if rc or normalize(Path(top)) != normalize(repo_root):
        raise RuntimeError("BLOCKED_TEST_TOOLING_BASELINE_MISMATCH: git top-level")
    rc, branch, err = git(repo_root, "branch", "--show-current")
    if rc or branch != EXPECTED_BRANCH:
        raise RuntimeError("BLOCKED_TEST_TOOLING_BASELINE_MISMATCH: branch")
    rc, head, err = git(repo_root, "rev-parse", "HEAD")
    if rc or head != expected_head:
        raise RuntimeError("BLOCKED_TEST_TOOLING_BASELINE_MISMATCH: HEAD")
    rc, status, err = git(repo_root, "status", "--short")
    if rc or status:
        raise RuntimeError("BLOCKED_TEST_TOOLING_BASELINE_MISMATCH: dirty tree")
    rc, _out, _err = git(repo_root, "merge-base", "--is-ancestor", EXPECTED_START_SHA, head)
    if rc:
        raise RuntimeError("BLOCKED_TEST_TOOLING_BASELINE_MISMATCH: start ancestry")
    env_path = repo_root / ".codex" / "environments" / "environment.toml"
    env_hash = sha256_file(env_path) if env_path.exists() else "MISSING"
    return {"repo_root": str(repo_root), "code_root": str(code_root), "branch": branch, "head": head, "git_status": "clean", "environment_toml_sha256": env_hash}


def environment_probe() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONHASHSEED"] = "0"
    proc = subprocess.run([sys.executable, "-B", "-m", "pytest", "--version"], capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    pytest_path = ""
    pytest_version = "NOT_AVAILABLE"
    try:
        import importlib.util
        spec = importlib.util.find_spec("pytest")
        pytest_path = str(spec.origin) if spec and spec.origin else ""
        if spec:
            module = __import__("pytest")
            pytest_version = str(getattr(module, "__version__", "UNKNOWN"))
    except Exception:
        pass
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "pip_version": probe_pip(env),
        "python_m_pytest_exit": str(proc.returncode),
        "python_m_pytest_stdout": proc.stdout.strip(),
        "python_m_pytest_stderr": proc.stderr.strip(),
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "user_site_enabled": str(site_enabled()),
        "PYTHONPATH": env.get("PYTHONPATH", ""),
        "PATH_relevant": os.environ.get("PATH", ""),
        "pytest_import_path": pytest_path,
        "pytest_version": pytest_version,
    }


def probe_pip(env: dict[str, str]) -> str:
    proc = subprocess.run([sys.executable, "-B", "-m", "pip", "--version"], capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    return (proc.stdout or proc.stderr).strip()


def site_enabled() -> bool:
    import site
    return bool(site.ENABLE_USER_SITE)


def targets(code_root: Path) -> list[str]:
    required = [
        "tests/test_structural_launcher_contract.py",
        "tests/test_phase1b_structural_completion.py",
        "tests/test_test_tooling_bootstrap_contract.py",
    ]
    for path in sorted((code_root / "tests").glob("test_*.py")):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace").lower()
        except OSError:
            continue
        if any(token in text for token in ("canonical launcher", "path_scope", "provenance", "semantic contract", "historical launcher")):
            rel = path.relative_to(code_root).as_posix()
            if rel not in required:
                required.append(rel)
    return required


def approval_text(checkpoint: dict[str, Any]) -> str:
    return "\n".join([
        APPROVAL_PREFIX,
        f"HEAD={checkpoint['head']}",
        f"PLAN_SHA256={checkpoint['plan_sha256']}",
        f"BOOTSTRAP_ROOT={checkpoint['bootstrap_root']}",
    ])


def read_approval(value: str) -> str:
    p = Path(value)
    return p.read_text(encoding="utf-8").strip() if p.exists() else value.strip()


def require_approval(args: argparse.Namespace, checkpoint: dict[str, Any]) -> None:
    if not args.approval_token:
        raise RuntimeError("BLOCKED_TEST_TOOLING_DOWNLOAD_APPROVAL_REQUIRED")
    if read_approval(args.approval_token) != approval_text(checkpoint):
        raise RuntimeError("BLOCKED_TEST_TOOLING_APPROVAL_TOKEN_MISMATCH")


def load_policy(path: Path) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8-sig"))
    if policy.get("allowed_packages") != list(ALLOWED_PACKAGES):
        raise RuntimeError("BLOCKED_TEST_TOOLING_POLICY_ALLOWLIST_MISMATCH")
    if not policy.get("only_binary") or policy.get("allow_source_distributions") or policy.get("allow_global_install") or policy.get("allow_user_install") or policy.get("allow_pip_upgrade") or policy.get("allow_plugins_autoload") or policy.get("write_bytecode") or policy.get("pytest_cache") != "disabled":
        raise RuntimeError("BLOCKED_TEST_TOOLING_POLICY_UNSAFE")
    return policy


def plan(args: argparse.Namespace, policy_path: Path) -> int:
    repo, code, root = map(lambda x: Path(x).resolve(), (args.repo_root, args.code_root, args.bootstrap_root))
    validate_root(repo, code, root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("BLOCKED_BOOTSTRAP_ROOT_NOT_EMPTY")
    base = baseline(repo, code, args.expected_head_sha)
    policy = load_policy(policy_path)
    probe = environment_probe()
    selected = select_pytest()
    selected_targets = targets(code)
    root.mkdir(parents=True, exist_ok=True)
    for name in ("checkpoint", "plan", "logs"):
        (root / name).mkdir()
    approved_rows = ["target\tsha256"] + [f"{target}\t{sha256_file(code / target)}" for target in selected_targets]
    (root / "plan" / "approved_targets.tsv").write_text("\n".join(approved_rows) + "\n", encoding="utf-8")
    (root / "plan" / "python_environment.tsv").write_text("field\tvalue\n" + "\n".join(f"{k}\t{v}" for k, v in probe.items()) + "\n", encoding="utf-8")
    (root / "plan" / "package_policy.tsv").write_text("package\tversion\n" + "\n".join(f"{p}\t{selected if p == 'pytest' else 'resolver-required'}" for p in policy["allowed_packages"]) + "\n", encoding="utf-8")
    plan_payload = {"schema": "MODULEC_TEST_TOOLING_DOWNLOAD_PLAN_V1", "phase": "AWAITING_DOWNLOAD_APPROVAL", "baseline": base, "bootstrap_root": str(root), "python": probe, "pytest_selected": selected, "allowed_packages": policy["allowed_packages"], "approved_targets": selected_targets, "scientific_runtime_allowed": False, "network_accessed": False, "download_authorized": False}
    plan_path = root / "plan" / "test_tooling_download_plan.json"
    write_json(plan_path, plan_payload)
    plan_hash = sha256_file(plan_path)
    (root / "plan" / "plan_sha256.txt").write_text(plan_hash + "\n", encoding="utf-8")
    (root / "plan" / "test_tooling_download_plan.md").write_text(
        "# Module C test tooling download plan\n\n"
        f"- phase: `{plan_payload['phase']}`\n"
        f"- bootstrap_root: `{root}`\n"
        f"- head: `{base['head']}`\n"
        f"- python: `{probe['python_executable']}` ({probe['python_version']})\n"
        f"- pytest: `{selected}`\n"
        "- network_accessed: `false`\n"
        "- download_authorized: `false`\n"
        f"- plan_sha256: `{plan_hash}`\n\n"
        "Download remains blocked until the exact approval token is supplied.\n",
        encoding="utf-8",
    )
    checkpoint = {"checkpoint_schema": "MODULEC_TEST_TOOLING_V1", "phase": "AWAITING_DOWNLOAD_APPROVAL", "repo_root": str(repo), "code_root": str(code), "branch": base["branch"], "head": base["head"], "git_status": "clean", "python_executable": probe["python_executable"], "python_version": probe["python_version"], "pytest_selected": selected, "bootstrap_root": str(root), "approved_targets_sha256": sha256_file(root / "plan" / "approved_targets.tsv"), "policy_sha256": sha256_file(policy_path), "plan_sha256": plan_hash, "scientific_runtime_allowed": False, "next_authorized_action": "DOWNLOAD_TEST_TOOLING_WHEELS"}
    checkpoint_path = Path(args.checkpoint).resolve()
    if checkpoint_path != root / "checkpoint" / "resume_checkpoint.json":
        raise RuntimeError("BLOCKED_CHECKPOINT_OUTSIDE_BOOTSTRAP_ROOT")
    write_json(checkpoint_path, checkpoint)
    token = approval_text(checkpoint)
    (root / "plan" / "approval_token.txt").write_text(token + "\n", encoding="utf-8")
    (root / "logs" / "plan_stdout.txt").write_text("TEST_TOOLING_DOWNLOAD_PLAN_READY\n" + token + "\n", encoding="utf-8")
    (root / "logs" / "plan_stderr.txt").write_text("", encoding="utf-8")
    return 0


def verify_checkpoint(args: argparse.Namespace, policy_path: Path) -> dict[str, Any]:
    checkpoint_path = Path(args.checkpoint).resolve()
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    repo, code, root = map(lambda x: Path(x).resolve(), (args.repo_root, args.code_root, args.bootstrap_root))
    validate_root(repo, code, root)
    if checkpoint.get("bootstrap_root") != str(root) or checkpoint.get("policy_sha256") != sha256_file(policy_path):
        raise RuntimeError("BLOCKED_RESUME_CHECKPOINT_MISMATCH")
    current = baseline(repo, code, args.expected_head_sha)
    if checkpoint.get("head") != current["head"] or checkpoint.get("branch") != current["branch"]:
        raise RuntimeError("BLOCKED_RESUME_CHECKPOINT_MISMATCH")
    return checkpoint


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=MODES)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--code-root", required=True)
    ap.add_argument("--bootstrap-root", required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--policy", default=None)
    ap.add_argument("--approval-token", default=None)
    args = ap.parse_args(argv)
    policy = Path(args.policy or (Path(args.code_root) / "config" / "test_tooling_policy.json")).resolve()
    try:
        load_policy(policy)
        if args.mode == "plan":
            return plan(args, policy)
        checkpoint = verify_checkpoint(args, policy)
        if args.mode in NETWORK_MODES:
            require_approval(args, checkpoint)
            raise RuntimeError("BLOCKED_TEST_TOOLING_DOWNLOAD_NOT_EXECUTED_IN_PHASE_2A")
        if args.mode == "resume":
            return 0
        raise RuntimeError("BLOCKED_PHASE_2A_ONLY_PLAN_MODE")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
