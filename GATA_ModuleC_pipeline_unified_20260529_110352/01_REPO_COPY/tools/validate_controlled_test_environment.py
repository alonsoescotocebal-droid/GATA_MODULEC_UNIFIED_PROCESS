from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_LOCK_SHA256 = "810510d6d9014bc8b6952ccb2ad81e46ef1d7639646a653959e0f6cbe43882a0"
EXPECTED_PYTEST = "9.1.1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def validate(repo_root: Path, code_root: Path) -> dict[str, Any]:
    repo_root, code_root = repo_root.resolve(), code_root.resolve()
    lock = code_root / "config" / "requirements-test.lock"
    policy_path = code_root / "config" / "test_tooling_policy.json"
    environment = repo_root / ".codex" / "environments" / "environment.toml"
    codex_config = repo_root / ".codex" / "config.toml"
    tool_root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "project-tools" / "GATA_MODULEC_UNIFIED_PROCESS" / "py314-pytest911"
    tool_python = tool_root / "Scripts" / "python.exe"
    failures: list[str] = []

    for path in (environment, codex_config, lock):
        rel = path.relative_to(repo_root).as_posix()
        rc, _out, err = git(repo_root, "ls-files", "--error-unmatch", rel)
        if rc:
            failures.append(f"untracked:{rel}:{err}")
        rc, status, _err = git(repo_root, "status", "--short", "--", rel)
        if rc or status:
            failures.append(f"modified:{rel}:{status}")
    if not lock.exists() or sha256(lock) != EXPECTED_LOCK_SHA256:
        failures.append("lock_sha256")
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
        if policy.get("persistent_tooling_parent") != "%LOCALAPPDATA%\\OpenAI\\Codex\\project-tools\\GATA_MODULEC_UNIFIED_PROCESS":
            failures.append("persistent_tooling_parent")
        if policy.get("resolution_staging_parent") != "03_RUNTIMES":
            failures.append("resolution_staging_parent")
    except Exception as exc:
        policy = {}
        failures.append(f"policy:{exc}")
    if not environment.exists():
        failures.append("environment_missing")
        environment_text = ""
    else:
        environment_text = environment.read_text(encoding="utf-8")
    setup_text = environment_text.split("[cleanup.win32]", 1)[0]
    cleanup_text = environment_text.split("[cleanup.win32]", 1)[1].split("[[actions]]", 1)[0] if "[cleanup.win32]" in environment_text else ""
    required_tokens = ("requirements-test.lock", "--require-hashes", "--only-binary=:all:", "https://pypi.org/simple", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTHONDONTWRITEBYTECODE")
    missing_tokens = [token for token in required_tokens if token not in environment_text]
    if missing_tokens:
        failures.append("environment_tokens:" + ",".join(missing_tokens))
    if "GATA_PROJECT_TEST_ENVIRONMENT_READY" not in setup_text and "GATA_PROJECT_TEST_ENVIRONMENT_PASS" not in environment_text:
        failures.append("controlled_environment_marker")
    if "moduleC_pipeline_v2.py" in setup_text or "moduleC_pipeline_v2.py" in cleanup_text:
        failures.append("scientific_pipeline_in_setup")
    if "Remove-Item" in cleanup_text:
        failures.append("destructive_cleanup")
    if not tool_python.exists():
        failures.append("tool_python_missing")
        python_version = pytest_version = pytest_path = pip_check = "NOT_AVAILABLE"
    else:
        probe_env = os.environ.copy()
        probe_env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONHASHSEED": "0"})
        probe = subprocess.run([str(tool_python), "-B", "-c", "import pathlib,sys,pytest; print(sys.version); print(pytest.__version__); print(pathlib.Path(pytest.__file__).resolve())"], capture_output=True, text=True, env=probe_env, encoding="utf-8", errors="replace")
        fields = (probe.stdout.strip().splitlines() if probe.stdout else [])
        python_version = fields[0] if fields else "NOT_AVAILABLE"
        pytest_version = fields[1] if len(fields) > 1 else "NOT_AVAILABLE"
        pytest_path = fields[2] if len(fields) > 2 else "NOT_AVAILABLE"
        check_proc = subprocess.run([str(tool_python), "-B", "-m", "pip", "check"], capture_output=True, text=True, env=probe_env, encoding="utf-8", errors="replace")
        pip_check = "PASS" if check_proc.returncode == 0 and "No broken requirements found" in check_proc.stdout else "BLOCKED"
        if not python_version.startswith("3.14."):
            failures.append("python_version")
        if pytest_version != EXPECTED_PYTEST:
            failures.append("pytest_version")
        if not pytest_path.lower().startswith(str(tool_root).lower()):
            failures.append("pytest_path")
        if pip_check != "PASS":
            failures.append("pip_check")
    result = {"status": "PASS" if not failures else "BLOCKED", "failures": failures, "base_python": r"C:\Python314\python.exe", "base_python_version": "3.14.x", "test_python": str(tool_python), "python_version": python_version, "pytest_version": pytest_version, "pytest_path": pytest_path, "tool_root": str(tool_root), "lock_path": str(lock), "lock_sha256": sha256(lock) if lock.exists() else "MISSING", "pip_check": pip_check, "plugins_autoload": "disabled", "bytecode": "disabled", "pytest_cache": "disabled", "download_performed_this_phase": "false", "installation_performed_this_phase": "false", "scientific_runtime_started": "false"}
    return result


if __name__ == "__main__":
    import sys
    result = validate(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)
