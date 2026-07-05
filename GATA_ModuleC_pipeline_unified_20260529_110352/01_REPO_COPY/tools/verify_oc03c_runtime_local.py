from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


REQUIRED_SMOKE_NUMBERS = {
    "daily_rows": "24180",
    "unique_dates": "930",
    "unique_years": "10",
    "unique_units": "26",
    "homogeneous_years": "0",
}

FORBIDDEN_SMOKE_TOKENS = {
    "flat_single_anchor",
    "interpolated_from_anchors",
    "extrapolated_from_anchors",
}

REQUIRED_RUNTIME_ARTIFACTS = [
    "qa/oc03_base_smoke_contract_gate.tsv",
    "qa/oc03c_base_smoke_contract_gate.tsv",
    "qa/portuguese_aq_validation_gate.tsv",
    "qa/gfas_era5_vs_portuguese_aq_concordance.tsv",
    "qa/portuguese_aq_claim_disposition.md",
    "deliverables_step9/runtime_scientific_closure_decision.md",
    "deliverables_step9/final_manifest.json",
    "deliverables_step9/final_sha256_checkpoints.txt",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_tsv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader)


def summarize_gate_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"exists": False}
    text = read_text(path)
    rows = parse_tsv_rows(path)
    result: Dict[str, object] = {
        "exists": True,
        "path": str(path),
        "row_count": len(rows),
        "contains_pass": "PASS" in text,
        "contains_hold": "HOLD" in text,
        "contains_no_go": "NO-GO" in text or "NO_GO" in text,
        "contains_portuguese": "PORTUGUESE" in text,
        "text_head": text[:2000],
    }
    if rows:
        result["first_row"] = rows[0]
    return result


def summarize_text_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"exists": False}
    text = read_text(path)
    return {
        "exists": True,
        "path": str(path),
        "size": path.stat().st_size,
        "contains_hold": "HOLD" in text,
        "contains_no_go": "NO-GO" in text or "NO_GO" in text,
        "text_head": text[:4000],
    }


def summarize_json_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"exists": False}
    text = read_text(path)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "exists": True,
            "path": str(path),
            "json_error": str(exc),
            "text_head": text[:4000],
        }
    return {
        "exists": True,
        "path": str(path),
        "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        "payload": payload,
    }


def summarize_sha_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"exists": False}
    lines = [line.strip() for line in read_text(path).splitlines() if line.strip()]
    return {
        "exists": True,
        "path": str(path),
        "line_count": len(lines),
        "lines_head": lines[:20],
    }


def verify_smoke_gate(path: Path) -> Dict[str, object]:
    summary = summarize_gate_file(path)
    if not summary.get("exists"):
        return summary
    text = read_text(path)
    checks = {}
    for key, expected in REQUIRED_SMOKE_NUMBERS.items():
        checks[key] = expected in text
    checks["years_2015_2024_present"] = "2015" in text and "2024" in text
    checks["forbidden_smoke_tokens_absent"] = not any(
        token in text for token in FORBIDDEN_SMOKE_TOKENS
    )
    summary["smoke_checks"] = checks
    summary["smoke_checks_all_pass"] = all(checks.values())
    return summary


def collect_summary(runtime_dir: Path) -> Dict[str, object]:
    qa_dir = runtime_dir / "qa"
    step9_dir = runtime_dir / "deliverables_step9"

    smoke_gate = verify_smoke_gate(qa_dir / "oc03_base_smoke_contract_gate.tsv")
    smoke_gate_alias = summarize_gate_file(qa_dir / "oc03c_base_smoke_contract_gate.tsv")
    aq_gate = summarize_gate_file(qa_dir / "portuguese_aq_validation_gate.tsv")
    concordance = summarize_gate_file(qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv")
    claim = summarize_text_file(qa_dir / "portuguese_aq_claim_disposition.md")
    closure = summarize_text_file(step9_dir / "runtime_scientific_closure_decision.md")
    manifest = summarize_json_file(step9_dir / "final_manifest.json")
    sha_file = summarize_sha_file(step9_dir / "final_sha256_checkpoints.txt")

    required_artifacts = {}
    for rel in REQUIRED_RUNTIME_ARTIFACTS:
        required_artifacts[rel] = (runtime_dir / rel).exists()

    return {
        "runtime_dir": str(runtime_dir),
        "required_artifacts": required_artifacts,
        "smoke_gate": smoke_gate,
        "smoke_gate_alias": smoke_gate_alias,
        "aq_gate": aq_gate,
        "concordance": concordance,
        "claim_disposition": claim,
        "scientific_closure": closure,
        "final_manifest": manifest,
        "final_sha256": sha_file,
    }


def write_outputs(runtime_dir: Path, summary: Dict[str, object]) -> None:
    qa_dir = runtime_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    json_path = qa_dir / "oc03c_runtime_local_verification_summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    md_lines = [
        "# OC03C Runtime Local Verification",
        "",
        f"runtime_dir: `{runtime_dir}`",
        "",
        "## Required Artifacts",
    ]
    for rel, exists in summary["required_artifacts"].items():
        md_lines.append(f"- {'FOUND' if exists else 'MISSING'} `{rel}`")

    smoke_gate = summary["smoke_gate"]
    md_lines.extend(
        [
            "",
            "## Smoke Gate",
            f"- exists: `{smoke_gate.get('exists')}`",
            f"- smoke_checks_all_pass: `{smoke_gate.get('smoke_checks_all_pass')}`",
        ]
    )
    for key, value in smoke_gate.get("smoke_checks", {}).items():
        md_lines.append(f"- {key}: `{value}`")

    aq_gate = summary["aq_gate"]
    md_lines.extend(
        [
            "",
            "## AQ Gate",
            f"- exists: `{aq_gate.get('exists')}`",
            f"- contains_pass: `{aq_gate.get('contains_pass')}`",
            f"- contains_hold: `{aq_gate.get('contains_hold')}`",
            f"- contains_no_go: `{aq_gate.get('contains_no_go')}`",
        ]
    )

    closure = summary["scientific_closure"]
    md_lines.extend(
        [
            "",
            "## Scientific Closure",
            f"- exists: `{closure.get('exists')}`",
            f"- contains_hold: `{closure.get('contains_hold')}`",
            f"- contains_no_go: `{closure.get('contains_no_go')}`",
        ]
    )

    md_lines.extend(
        [
            "",
            "## Notes",
            "- This file is a local convenience summary only.",
            "- Final GO/NO-GO must still be based on direct reading of the underlying runtime artifacts.",
        ]
    )

    md_path = qa_dir / "oc03c_runtime_local_verification_summary.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read OC03/OC03C runtime artifacts locally and write a local summary."
    )
    parser.add_argument("runtime_dir", help="Active runtime directory under 03_RUNTIMES")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir).resolve()
    if not runtime_dir.exists():
        raise SystemExit(f"Runtime directory not found: {runtime_dir}")

    summary = collect_summary(runtime_dir)
    write_outputs(runtime_dir, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
