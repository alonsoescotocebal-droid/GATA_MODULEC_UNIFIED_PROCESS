from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DECISION_PASS = "STRUCTURAL_SMOKERUN_PASS"
DECISION_BLOCKED = "BLOCKED_STRUCTURAL_PROVENANCE"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT).strip()


def is_subpath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only structural Module C smokerun.")
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--code-root", required=True)
    ap.add_argument("--modulec-data-root", required=True)
    ap.add_argument("--incendios-root", required=True)
    ap.add_argument("--gfas-root", required=True)
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--semantic-contract", required=True)
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    code = Path(args.code_root).resolve()
    data = Path(args.modulec_data_root).resolve()
    incendios = Path(args.incendios_root).resolve()
    gfas = Path(args.gfas_root).resolve()
    runtime = Path(args.runtime_root).resolve()
    config = code / "config" / "module_c_canonical_paths.json"
    environment = repo / ".codex" / "environments" / "environment.toml"
    semantic = Path(args.semantic_contract).resolve()

    if runtime.exists():
        raise SystemExit(f"{DECISION_BLOCKED}: output root already exists: {runtime}")
    cfg = json.loads(config.read_text(encoding="utf-8-sig"))
    expected_start = cfg["EXPECTED_START_SHA"]
    observed_head = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain=v1")
    branch = git(repo, "branch", "--show-current")
    checks = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append((name, "PASS" if ok else "BLOCKED", detail))

    check("GIT_TOPLEVEL", repo == Path(cfg["EXPECTED_GIT_TOPLEVEL"]).resolve(), str(repo))
    start_ok = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", expected_start, observed_head]).returncode == 0
    check("HEAD_LINEAGE", start_ok, f"{observed_head} descendant of {expected_start}")
    check("BRANCH", branch == cfg["EXPECTED_BRANCH"], f"{branch} expected {cfg['EXPECTED_BRANCH']}")
    check("TREE_CLEAN", status == "", status or "clean")
    check("ENVIRONMENT_INERT", environment.read_text(encoding="utf-8").count('script = ""') >= 4, str(environment))
    check("CODE_ROOT", code == Path(cfg["EXPECTED_REPO_ROOT"]).resolve(), str(code))
    check("DATA_ROOT", data.exists() and is_subpath(data, Path(cfg["DATA_ROOT_ALLOWED_PREFIX"])), str(data))
    check("INCENDIOS_ROOT", incendios.exists() and is_subpath(incendios, Path(cfg["DATA_ROOT_ALLOWED_PREFIXES"][-1])), str(incendios))
    check("GFAS_EFFECTIVE_ROOT", gfas.exists() and is_subpath(gfas, data), str(gfas))
    check("RUNTIME_ROOT", is_subpath(runtime, Path(cfg["OUTPUT_ROOT_ALLOWED_PREFIX"])), str(runtime))
    check("SEMANTIC_CONTRACT", semantic.exists(), str(semantic))
    check("NO_RESUME", True, "structural smokerun has no resume mode")
    check("NO_SCIENTIFIC_RUNTIME", True, "does not import or invoke moduleC_pipeline_v2.py")

    runtime.mkdir(parents=True)
    qa = runtime / "qa"
    qa.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    with (qa / "structural_smokerun_checks.tsv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(("check_id", "status", "detail"))
        writer.writerows(checks)
    provenance = {
        "runtime_kind": "STRUCTURAL_SMOKERUN_ONLY",
        "decision": DECISION_PASS if all(row[1] == "PASS" for row in checks) else DECISION_BLOCKED,
        "repo_root": str(repo),
        "code_root": str(code),
        "head": observed_head,
        "branch": branch,
        "runtime_root": str(runtime),
        "modulec_data_root": str(data),
        "incendios_root": str(incendios),
        "gfas_effective_root": str(gfas),
        "semantic_contract": str(semantic),
        "semantic_contract_sha256": sha256(semantic),
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "scientific_runtime_started": False,
    }
    (qa / "source_runtime_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (runtime / "STRUCTURAL_SMOKERUN_DECISION.txt").write_text(provenance["decision"] + "\n", encoding="utf-8")
    if provenance["decision"] != DECISION_PASS:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
