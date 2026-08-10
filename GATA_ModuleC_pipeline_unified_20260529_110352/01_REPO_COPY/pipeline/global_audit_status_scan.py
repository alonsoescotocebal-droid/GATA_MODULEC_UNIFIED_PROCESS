from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


STATUS_TOKENS = ("HOLD", "FAIL", "NO-GO", "BLOCKED")
TOKENS = STATUS_TOKENS + ("WARNING",)
STATUS_KEYS = {"status", "decision", "qa_flag"}
LIMIT_PAT = re.compile(r"limitacion|limitaci[oó]n|fallback|proxy|contextual", re.IGNORECASE)
TEXT_STATUS_PAT = re.compile(
    r"(?im)^\s*[-*]?\s*(?:status|decision|qa_flag)\s*[:=]\s*\*{0,2}\s*(HOLD|FAIL|NO-GO|BLOCKED)\b"
)
TEXT_DECISION_PAT = re.compile(r"(?im)\bDECISION\s*=\s*(HOLD|FAIL|NO-GO|BLOCKED)\b")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return path.read_text(errors="replace")


def _init_status_counts() -> Dict[str, int]:
    return {"HOLD": 0, "FAIL": 0, "NO-GO": 0, "BLOCKED": 0}


def _total_blockers(counts: Dict[str, int]) -> int:
    return counts["HOLD"] + counts["FAIL"] + counts["NO-GO"] + counts["BLOCKED"]


def _raw_token_counts(text: str) -> Dict[str, int]:
    upper = text.upper()
    return {k: upper.count(k) for k in TOKENS}


def _detect_delimiter(first_line: str) -> str:
    if "\t" in first_line:
        return "\t"
    semi = first_line.count(";")
    comma = first_line.count(",")
    return ";" if semi >= comma else ","


def _scan_tabular_statuses(path: Path, text: str) -> Tuple[Dict[str, int], str]:
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    counts = _init_status_counts()
    if not lines:
        return counts, "tabular_empty"

    delim = "\t" if path.suffix.lower() == ".tsv" else _detect_delimiter(lines[0])
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = [c for c in (reader.fieldnames or []) if c and c.strip().lower() in STATUS_KEYS]
    if not cols:
        return counts, "tabular_no_status_columns"

    for row in reader:
        for col in cols:
            token = (row.get(col) or "").strip().upper()
            if token in counts:
                counts[token] += 1
    return counts, "tabular_status_columns"


def _walk_json(obj: object) -> Iterable[Tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            if isinstance(v, (str, int, float, bool)) or v is None:
                yield key, "" if v is None else str(v)
            else:
                yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def _scan_json_statuses(text: str) -> Tuple[Dict[str, int], str]:
    counts = _init_status_counts()
    try:
        payload = json.loads(text)
    except Exception:
        return counts, "json_parse_error"

    for key, value in _walk_json(payload):
        if key.strip().lower() not in STATUS_KEYS:
            continue
        token = value.strip().upper()
        if token in counts:
            counts[token] += 1
    return counts, "json_status_keys"


def _scan_text_statuses(text: str) -> Tuple[Dict[str, int], str]:
    counts = _init_status_counts()
    for m in TEXT_STATUS_PAT.finditer(text):
        token = m.group(1).upper()
        if token in counts:
            counts[token] += 1
    for m in TEXT_DECISION_PAT.finditer(text):
        token = m.group(1).upper()
        if token in counts:
            counts[token] += 1
    return counts, "text_structured_status_lines"


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--output-root", required=True)
    args = p.parse_args()

    root = Path(args.output_root)
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    scan_paths = [root / "qa", root / "brief", root / "brief" / "causal_matrix", root / "deliverables_step9"]
    files: List[Path] = []
    for d in scan_paths:
        if d.exists():
            for f in d.rglob("*"):
                if f in (out_tsv, out_md):
                    continue
                if f.is_file() and f.suffix.lower() in (".tsv", ".csv", ".json", ".md", ".txt"):
                    files.append(f)
    files = sorted(set(files))

    out_tsv = qa_dir / "global_audit_status_scan.tsv"
    out_md = qa_dir / "global_audit_status_scan.md"

    rows = []
    total_blockers = 0
    total_historical_ignored = 0
    for f in files:
        text = read_text(f)
        raw_counts = _raw_token_counts(text)
        is_hist = f.name.lower() == "run_log.txt"

        if is_hist:
            active_counts = _init_status_counts()
            active_source = "historical_ignored"
        else:
            suffix = f.suffix.lower()
            if suffix in (".tsv", ".csv"):
                active_counts, active_source = _scan_tabular_statuses(f, text)
            elif suffix == ".json":
                active_counts, active_source = _scan_json_statuses(text)
            else:
                active_counts, active_source = _scan_text_statuses(text)

        active_blocker = _total_blockers(active_counts)
        total_blockers += active_blocker

        raw_blocker_mentions = raw_counts["HOLD"] + raw_counts["FAIL"] + raw_counts["NO-GO"] + raw_counts["BLOCKED"]
        historical_ignored = max(0, raw_blocker_mentions - active_blocker)
        total_historical_ignored += historical_ignored

        excerpt = " | ".join(text.splitlines()[:3])[:220]
        rows.append(
            {
                "file_path": str(f).replace("\\", "/"),
                "file_type": f.suffix.lower(),
                "is_active_artifact": 0 if is_hist else 1,
                "is_historical_log": 1 if is_hist else 0,
                "status_tokens_found": ",".join(k for k, v in raw_counts.items() if v > 0),
                "hold_count": active_counts["HOLD"],
                "fail_count": active_counts["FAIL"],
                "no_go_count": active_counts["NO-GO"],
                "blocked_count": active_counts["BLOCKED"],
                "warning_count": raw_counts["WARNING"],
                "methodological_limitation_count": len(LIMIT_PAT.findall(text)),
                "active_blocker_count": active_blocker,
                "historical_mentions_ignored": historical_ignored,
                "active_status_source": active_source,
                "evidence_excerpt": excerpt,
                "decision": "HOLD" if active_blocker > 0 else "PASS",
                "blocking_reason": "active structured status detected" if active_blocker > 0 else "",
            }
        )

    fieldnames = [
        "file_path",
        "file_type",
        "is_active_artifact",
        "is_historical_log",
        "status_tokens_found",
        "hold_count",
        "fail_count",
        "no_go_count",
        "blocked_count",
        "warning_count",
        "methodological_limitation_count",
        "active_blocker_count",
        "historical_mentions_ignored",
        "active_status_source",
        "evidence_excerpt",
        "decision",
        "blocking_reason",
    ]
    with out_tsv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    md = [
        "# Global Audit Status Scan",
        "",
        f"- files_scanned: {len(rows)}",
        f"- active_blockers: {total_blockers}",
        f"- historical_mentions_ignored: {total_historical_ignored}",
        "",
        "| file | decision | active_blockers | source | tokens |",
        "|---|---|---:|---|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['file_path']} | {r['decision']} | {r['active_blocker_count']} | "
            f"{r['active_status_source']} | {r['status_tokens_found']} |"
        )
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
