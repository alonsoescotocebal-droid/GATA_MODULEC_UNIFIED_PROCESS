#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def sniff_delim(path: Path) -> str:
    text = path.read_bytes()[:65536].decode("utf-8-sig", errors="replace")
    counts = {";": text.count(";"), ",": text.count(","), "\t": text.count("\t")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    delim = sniff_delim(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def safe_float(v: object):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "na", "none", "null"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().upper()


def write_tsv(path: Path, header: Iterable[str], rows: Iterable[Iterable[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(list(header))
        for row in rows:
            w.writerow(list(row))


def find_threshold_register(repo_root: Path) -> Path:
    candidates = [
        repo_root / "docs" / "canon" / "SCIENTIFIC_THRESHOLD_DECLARATION_REGISTER.md",
        repo_root / "docs" / "canon" / "SCIENTIFIC_THRESHOLD_DECLARATION_REGISTER_MODULE_C.md",
        repo_root / "PIPELINE_CANON_HANDOFF" / "SCIENTIFIC_THRESHOLD_DECLARATION_REGISTER_MODULE_C.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def evaluate_smoke_spatial(smoke_csv: Path) -> Tuple[str, str, Dict[int, int]]:
    if not smoke_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "smoke_days_unit_2015_2024.csv missing", {}
    rows = read_csv_rows(smoke_csv)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "smoke_days_unit_2015_2024.csv empty", {}
    by_year: Dict[int, set] = {}
    for r in rows:
        y = safe_float(r.get("year"))
        v = safe_float(r.get("smoke_days"))
        if y is None or v is None:
            continue
        by_year.setdefault(int(y), set()).add(round(v, 8))
    if not by_year:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No numeric year/smoke_days pairs", {}
    unique_counts = {y: len(vals) for y, vals in by_year.items()}
    blocked_years = [y for y, n in unique_counts.items() if n <= 1]
    if blocked_years:
        return (
            "BLOCKED_SPATIAL_SMOKE_CLAIM",
            "Years with <=1 unique smoke_days across units: " + ",".join(str(y) for y in sorted(blocked_years)),
            unique_counts,
        )
    return "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION", "Smoke spatial differentiation detected.", unique_counts


def evaluate_iech_ranking(iech_mean_csv: Path) -> Tuple[str, str, int]:
    if not iech_mean_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024_mean.csv missing", 0
    rows = read_csv_rows(iech_mean_csv)
    vals = []
    for r in rows:
        v = safe_float(r.get("IECH_mean_2015_2024"))
        if v is not None:
            vals.append(round(v, 8))
    n_unique = len(set(vals))
    if n_unique <= 1:
        return "BLOCKED_IECH_RANKING", f"IECH mean unique count={n_unique}", n_unique
    return "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION", f"IECH mean unique count={n_unique}", n_unique


def evaluate_health_claim_support(smoke_csv: Path) -> Tuple[str, str]:
    if not smoke_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "smoke table missing"
    rows = read_csv_rows(smoke_csv)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "smoke table empty"
    keys = {k.lower() for k in rows[0].keys()}
    health_cols = {
        "pm25_ugm3",
        "pm25_24h_ugm3",
        "pm25_annual_ugm3",
        "pm10_ugm3",
        "no2_ugm3",
        "o3_ugm3",
        "so2_ugm3",
        "co_mgm3",
    }
    if keys.intersection(health_cols):
        return "THRESHOLD_DEFINED_AS_OFFICIAL_HEALTH_STANDARD", "Pollutant concentration columns detected."
    return "BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM", "Proxy-only smoke table; pollutant concentration thresholds unavailable."


def evaluate_smoke_route_trace(inputs_json: Path) -> Tuple[str, str, str]:
    if not inputs_json.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "inputs_resolved.json missing", ""
    try:
        payload = json.loads(inputs_json.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", f"inputs_resolved.json parse error: {exc}", ""
    if not isinstance(payload, dict):
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "inputs_resolved.json is not an object", ""
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
    route_decision = str(meta.get("smoke_route_decision") or "").strip()
    if not route_selected:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "smoke_route_selected missing in inputs_resolved meta", ""

    if route_selected in ("v1_moduleA_validated", "v0_gfas_era5_real"):
        return (
            "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
            f"route_selected={route_selected}; route_decision={route_decision}",
            route_selected,
        )
    if route_selected == "BLOCKED_DECODER_REQUIRED":
        return (
            "BLOCKED_DECODER_REQUIRED",
            f"route_selected={route_selected}; route_decision={route_decision}",
            route_selected,
        )
    if route_selected == "v0_parquet_proxy_degraded":
        return (
            "BLOCKED_SPATIAL_SMOKE_CLAIM",
            f"route_selected={route_selected}; route_decision={route_decision}",
            route_selected,
        )
    if route_selected == "NO-GO_SMOKE_ROUTE":
        return (
            "BLOCKED_NO_GO_SMOKE_ROUTE",
            f"route_selected={route_selected}; route_decision={route_decision}",
            route_selected,
        )
    return (
        "BLOCKED_FOR_REQUIRED_VARIABLE",
        f"unrecognized route_selected={route_selected}; route_decision={route_decision}",
        route_selected,
    )


def evaluate_population_cancellation(iech_hist_csv: Path) -> Tuple[str, str]:
    if not iech_hist_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024.csv missing"
    rows = read_csv_rows(iech_hist_csv)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024.csv empty"

    comparable = 0
    equal_rows = 0
    for r in rows:
        iech = safe_float(r.get("IECH"))
        hours = safe_float(r.get("smoke_hours_equiv"))
        if iech is None or hours is None:
            continue
        comparable += 1
        if abs(iech - hours) <= 1e-9:
            equal_rows += 1
    if comparable == 0:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No comparable IECH/smoke_hours_equiv rows"
    if equal_rows == comparable:
        return "BLOCKED_POPULATION_EXPOSURE_CLAIM", f"IECH equals smoke_hours_equiv in {equal_rows}/{comparable} rows"
    return "THRESHOLD_DEFINED_AS_INDEXED_METHOD", f"IECH differs from smoke_hours_equiv in {comparable - equal_rows}/{comparable} rows"


def evaluate_warning_inventory(warning_tsv: Path) -> Tuple[str, str, int]:
    if not warning_tsv.exists():
        return "BLOCKED_UNEXPLAINED_WARNING", "warning_inventory.tsv missing", 1
    rows = read_csv_rows(warning_tsv)
    if not rows:
        return "BLOCKED_UNEXPLAINED_WARNING", "warning_inventory.tsv empty", 1
    blocked = 0
    for r in rows:
        status = (r.get("status") or "").strip().upper()
        explained = (r.get("explained") or "").strip().lower()
        if status == "BLOCKED" or explained in ("0", "false"):
            blocked += 1
    if blocked > 0:
        return "BLOCKED_UNEXPLAINED_WARNING", f"Unexplained or blocked warnings count={blocked}", blocked
    return "THRESHOLD_DEFINED_AS_INDEXED_METHOD", "All warnings are classified and explained.", 0


def evaluate_causal_matrix(causal_csv: Path) -> Tuple[str, str, Dict[str, int]]:
    metrics = {"rows": 0, "rows_hold": 0, "rows_missing_components": 0, "rows_threshold_blocked": 0, "has_threshold_gate_status": 0}
    if not causal_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "causal_matrix_IECH_NUTS3.csv missing", metrics
    rows = read_csv_rows(causal_csv)
    metrics["rows"] = len(rows)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "causal_matrix_IECH_NUTS3.csv empty", metrics
    hdr = {k.lower() for k in rows[0].keys()}
    has_threshold = "threshold_gate_status" in hdr
    metrics["has_threshold_gate_status"] = 1 if has_threshold else 0
    if not has_threshold:
        return "BLOCKED_FOR_THRESHOLD_DEFINITION", "threshold_gate_status column missing", metrics
    for r in rows:
        if (r.get("qa_flag") or "").strip().upper() == "HOLD":
            metrics["rows_hold"] += 1
        if (r.get("missing_components") or "").strip() != "":
            metrics["rows_missing_components"] += 1
        tgs = (r.get("threshold_gate_status") or "").strip().upper()
        if tgs.startswith("BLOCKED"):
            metrics["rows_threshold_blocked"] += 1
    if metrics["rows_hold"] > 0 or metrics["rows_missing_components"] > 0 or metrics["rows_threshold_blocked"] > 0:
        return "BLOCKED_FOR_CAUSAL_CLAIM", "Causal matrix has unresolved HOLD/missing/block rows", metrics
    return "THRESHOLD_DEFINED_AS_INDEXED_METHOD", "Causal matrix threshold column present with no blocked rows.", metrics


def audit_brief_claims(brief_path: Path, active_blocks: List[str]) -> List[Tuple[int, str, str, str]]:
    if not brief_path.exists():
        return [(0, "BRIEF_MISSING", "BLOCKED_FOR_REQUIRED_VARIABLE", "brief file missing")]
    text = brief_path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    forbidden_by_block = {
        "BLOCKED_SPATIAL_SMOKE_CLAIM": [r"smoke hotspot", r"spatially differentiated smoke exposure", r"most exposed by smoke"],
        "BLOCKED_IECH_RANKING": [r"highest iech", r"iech hotspot", r"elevated iech"],
        "BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM": [r"health exposure", r"epidemiological risk", r"sanitary exposure"],
        "BLOCKED_FOR_CAUSAL_CLAIM": [r"\bcauses\b", r"\bdrives\b", r"\bexplains\b"],
        "BLOCKED_WRB_ZONAL_CLAIM": [r"dominant soil by nuts3", r"wrb-driven priority"],
        "BLOCKED_VALIDATED_SCENARIO_CLAIM": [r"\bs1 predicts\b", r"validated prevention effect", r"expected reduction"],
    }
    hits: List[Tuple[int, str, str, str]] = []
    for block in active_blocks:
        pats = forbidden_by_block.get(block, [])
        for i, line in enumerate(lines, start=1):
            for pat in pats:
                if re.search(pat, line, flags=re.IGNORECASE):
                    hits.append((i, line.strip(), block, pat))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--repo-root", required=False, default=None)
    args = ap.parse_args()

    output_root = Path(args.output_root)
    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[1]
    qa_dir = output_root / "qa"
    deliver_dir = output_root / "deliverables_step9"
    qa_dir.mkdir(parents=True, exist_ok=True)
    deliver_dir.mkdir(parents=True, exist_ok=True)

    threshold_register = find_threshold_register(repo_root)
    smoke_csv = output_root / "tables" / "smoke_days_unit_2015_2024.csv"
    iech_hist_csv = output_root / "tables" / "IECH_unit_2015_2024.csv"
    iech_mean_csv = output_root / "tables" / "IECH_unit_2015_2024_mean.csv"
    causal_csv = output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv"
    brief_path = output_root / "brief" / "Brief_Politica_IECH_2030.md"
    inputs_json = output_root / "qa" / "inputs_resolved.json"
    warning_inventory = output_root / "qa" / "warning_inventory.tsv"

    gate_rows: List[Dict[str, str]] = []
    evidence_rows: List[List[object]] = []

    def add_gate(
        threshold_id: str,
        component: str,
        input_file_checked: str,
        variable_checked: str,
        observed_condition: str,
        threshold_rule: str,
        threshold_source_id: str,
        source_type: str,
        gate_status: str,
        allowed_claim: str,
        forbidden_claim: str,
        final_effect: str,
    ) -> None:
        gate_rows.append(
            {
                "threshold_id": threshold_id,
                "component": component,
                "input_file_checked": input_file_checked,
                "variable_checked": variable_checked,
                "observed_condition": observed_condition,
                "threshold_value_or_rule": threshold_rule,
                "threshold_source_id": threshold_source_id,
                "source_type": source_type,
                "gate_status": gate_status,
                "allowed_claim": allowed_claim,
                "forbidden_claim": forbidden_claim,
                "final_decision_effect": final_effect,
            }
        )

    def add_evidence(name: str, p: Path) -> None:
        exists = p.exists()
        size = p.stat().st_size if exists and p.is_file() else 0
        sha = sha256_file(p) if exists and p.is_file() else ""
        rows = 0
        if exists and p.suffix.lower() in (".csv", ".tsv"):
            try:
                rows = len(read_csv_rows(p))
            except Exception:
                rows = -1
        evidence_rows.append([name, str(p), exists, size, sha, rows])

    if threshold_register.exists():
        add_gate(
            "REG-001",
            "Threshold register integration",
            str(threshold_register),
            "threshold register presence",
            "register found",
            "Register must exist in canonical repo.",
            "SRC-CANON-REGISTER",
            "METHODOLOGICAL_GATE",
            "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
            "Scientific threshold contract is enforceable.",
            "Unregistered claims are forbidden.",
            "NONE",
        )
    else:
        add_gate(
            "REG-001",
            "Threshold register integration",
            str(threshold_register),
            "threshold register presence",
            "register missing",
            "Register must exist in canonical repo.",
            "SRC-CANON-REGISTER",
            "METHODOLOGICAL_GATE",
            "BLOCKED_FOR_THRESHOLD_DEFINITION",
            "None",
            "Scientific closure claim",
            "NO-GO_SCIENTIFIC_THRESHOLD",
        )

    route_status, route_obs, route_selected = evaluate_smoke_route_trace(inputs_json)
    add_gate(
        "SMOKE-ROUTE-001",
        "Smoke route selector priority",
        str(inputs_json),
        "meta.smoke_route_selected/meta.smoke_route_decision",
        route_obs,
        "priority=v1_moduleA_validated>v0_gfas_era5_real>BLOCKED_DECODER_REQUIRED>v0_parquet_proxy_degraded>NO-GO_SMOKE_ROUTE",
        "SRC-GATE-SMOKE-ROUTE",
        "METHODOLOGICAL_GATE",
        route_status,
        "Route-level traceability and explicit degraded/blocked state reporting.",
        "Scientific closure with degraded or blocked smoke route.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if route_status.startswith("BLOCKED") else "NONE",
    )

    smoke_status, smoke_obs, smoke_unique = evaluate_smoke_spatial(smoke_csv)
    add_gate(
        "SMOKE-011",
        "Smoke spatial differentiation",
        str(smoke_csv),
        "smoke_days by unit/year",
        smoke_obs,
        "count_unique(smoke_days across units by year) must be > 1",
        "SRC-GATE-SMOKE-SPATIAL",
        "METHODOLOGICAL_GATE",
        smoke_status,
        "Smoke proxy can be used as common baseline when blocked.",
        "Spatially differentiated smoke exposure claim when n_unique<=1.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if smoke_status.startswith("BLOCKED") else "NONE",
    )

    health_status, health_obs = evaluate_health_claim_support(smoke_csv)
    add_gate(
        "SMOKE-001",
        "Health exposure support",
        str(smoke_csv),
        "pollutant concentration columns",
        health_obs,
        "WHO/EPA/EU pollutant concentration threshold variables required.",
        "SRC-WHO-AQG-2021",
        "OFFICIAL_HEALTH_STANDARD",
        health_status,
        "Proxy-only smoke interpretation (non-health claim).",
        "Health/epidemiological exposure claims from proxy-only smoke data.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if health_status.startswith("BLOCKED") else "NONE",
    )

    pop_cancel_status, pop_cancel_obs = evaluate_population_cancellation(iech_hist_csv)
    add_gate(
        "IECH-POP-001",
        "Population exposure cancellation check",
        str(iech_hist_csv),
        "IECH vs smoke_hours_equiv",
        pop_cancel_obs,
        "IECH must not collapse to smoke_hours_equiv for all rows when used for exposure claim.",
        "SRC-GATE-IECH-POP-CANCEL",
        "METHODOLOGICAL_GATE",
        pop_cancel_status,
        "Operational proxy interpretation with explicit limitation.",
        "Population exposure differentiation claim when IECH fully cancels to smoke_hours_equiv.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if pop_cancel_status.startswith("BLOCKED") else "NONE",
    )

    warning_status, warning_obs, warning_blocked = evaluate_warning_inventory(warning_inventory)
    add_gate(
        "WARN-001",
        "Runtime warning classification gate",
        str(warning_inventory),
        "warning inventory status/explained",
        warning_obs,
        "No unexplained warning allowed in smoke route decoder evidence.",
        "SRC-GATE-WARNING-INVENTORY",
        "METHODOLOGICAL_GATE",
        warning_status,
        "Warnings may pass only if classified and reproducible values are verified.",
        "GO with unexplained warnings or silent suppression.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if warning_status.startswith("BLOCKED") else "NONE",
    )

    iech_status, iech_obs, _iech_unique = evaluate_iech_ranking(iech_mean_csv)
    add_gate(
        "IECH-003",
        "IECH ranking validity",
        str(iech_mean_csv),
        "IECH_mean_2015_2024",
        iech_obs,
        "count_unique(IECH_mean_2015_2024 across units) must be > 1 for ranking claims.",
        "SRC-GATE-IECH-RANKING",
        "METHODOLOGICAL_GATE",
        iech_status,
        "IECH common baseline claim when ranking is blocked.",
        "Highest/high IECH territorial ranking when n_unique<=1.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if iech_status.startswith("BLOCKED") else "NONE",
    )

    causal_status, causal_obs, causal_metrics = evaluate_causal_matrix(causal_csv)
    add_gate(
        "CAUSAL-001",
        "Causal matrix threshold contract",
        str(causal_csv),
        "qa_flag, missing_components, threshold_gate_status",
        causal_obs,
        "Causal matrix requires threshold_gate_status and no unresolved blocked rows.",
        "SRC-GATE-CAUSAL",
        "METHODOLOGICAL_GATE",
        causal_status,
        "Association/context wording with explicit limits.",
        "Causal closure claim while unresolved blocked drivers exist.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if causal_status.startswith("BLOCKED") else "NONE",
    )

    active_blocks = sorted({r["gate_status"] for r in gate_rows if r["gate_status"].startswith("BLOCKED")})
    brief_hits = audit_brief_claims(brief_path, active_blocks)

    add_evidence("threshold_register", threshold_register)
    add_evidence("inputs_resolved", inputs_json)
    add_evidence("smoke_table", smoke_csv)
    add_evidence("iech_hist_table", iech_hist_csv)
    add_evidence("iech_mean_table", iech_mean_csv)
    add_evidence("causal_matrix_csv", causal_csv)
    add_evidence("brief_md", brief_path)
    add_evidence("warning_inventory", warning_inventory)

    gate_header = [
        "threshold_id",
        "component",
        "input_file_checked",
        "variable_checked",
        "observed_condition",
        "threshold_value_or_rule",
        "threshold_source_id",
        "source_type",
        "gate_status",
        "allowed_claim",
        "forbidden_claim",
        "final_decision_effect",
    ]
    write_tsv(
        qa_dir / "scientific_validation_gate.tsv",
        gate_header,
        [[r[k] for k in gate_header] for r in gate_rows],
    )
    write_tsv(
        qa_dir / "scientific_claim_gate.tsv",
        gate_header,
        [[r[k] for k in gate_header] for r in gate_rows],
    )

    md_lines = [
        "# Scientific Validation Gate",
        "",
        f"- generated: {now_iso()}",
        f"- output_root: `{output_root}`",
        "",
        "| threshold_id | gate_status | final_decision_effect | observed_condition |",
        "|---|---|---|---|",
    ]
    for r in gate_rows:
        md_lines.append(
            f"| {r['threshold_id']} | {r['gate_status']} | {r['final_decision_effect']} | {r['observed_condition']} |"
        )
    (qa_dir / "scientific_validation_gate.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    write_tsv(
        qa_dir / "scientific_threshold_evidence_register.tsv",
        ["evidence_id", "path", "exists", "bytes", "sha256", "rows"],
        evidence_rows,
    )

    write_tsv(
        qa_dir / "causal_matrix_scientific_gate_audit.tsv",
        ["metric", "value", "status", "detail"],
        [
            ["rows", causal_metrics.get("rows", 0), "PASS" if causal_metrics.get("rows", 0) > 0 else "BLOCKED", "causal row count"],
            ["rows_hold", causal_metrics.get("rows_hold", 0), "BLOCKED" if causal_metrics.get("rows_hold", 0) > 0 else "PASS", "qa_flag HOLD rows"],
            [
                "rows_missing_components",
                causal_metrics.get("rows_missing_components", 0),
                "BLOCKED" if causal_metrics.get("rows_missing_components", 0) > 0 else "PASS",
                "rows with non-empty missing_components",
            ],
            [
                "has_threshold_gate_status",
                causal_metrics.get("has_threshold_gate_status", 0),
                "PASS" if causal_metrics.get("has_threshold_gate_status", 0) == 1 else "BLOCKED",
                "threshold_gate_status column exists",
            ],
            [
                "rows_threshold_blocked",
                causal_metrics.get("rows_threshold_blocked", 0),
                "BLOCKED" if causal_metrics.get("rows_threshold_blocked", 0) > 0 else "PASS",
                "rows where threshold_gate_status starts with BLOCKED",
            ],
            [
                "warning_inventory_blocked_rows",
                warning_blocked,
                "BLOCKED" if warning_blocked > 0 else "PASS",
                "warning_inventory rows marked as blocked/unexplained",
            ],
        ],
    )

    brief_audit_rows: List[List[object]] = []
    for line_no, line_text, block_status, pattern in brief_hits:
        brief_audit_rows.append([line_no, block_status, pattern, line_text, "BLOCKED_CLAIM"])
    if not brief_audit_rows:
        brief_audit_rows.append([0, "NONE", "", "No forbidden phrases detected for active blocks.", "PASS"])
    write_tsv(
        qa_dir / "brief_claim_scientific_gate_audit.tsv",
        ["line_no", "active_block_status", "matched_pattern", "line_text", "claim_status"],
        brief_audit_rows,
    )

    blocked_claim_rows: List[List[object]] = []
    for line_no, line_text, block_status, pattern in brief_hits:
        blocked_claim_rows.append(
            [
                "brief",
                block_status,
                pattern,
                str(brief_path),
                f"line={line_no}",
                "Replace with non-causal/proxy wording aligned to threshold status.",
            ]
        )
    if not blocked_claim_rows:
        blocked_claim_rows.append(["none", "NONE", "", "", "", "No blocked claim matches found."])
    write_tsv(
        qa_dir / "blocked_claims_register.tsv",
        ["claim_context", "gate_status", "matched_phrase_pattern", "source_file", "location", "recommended_rewrite"],
        blocked_claim_rows,
    )

    scientific_effects = [r["final_decision_effect"] for r in gate_rows]
    if "NO-GO_SCIENTIFIC_THRESHOLD" in scientific_effects:
        scientific_decision = "NO-GO_SCIENTIFIC_THRESHOLD"
    elif any(r["gate_status"].startswith("BLOCKED") for r in gate_rows):
        scientific_decision = "HOLD"
    else:
        scientific_decision = "GO"

    decision_lines = [
        "# Runtime Scientific Closure Decision",
        "",
        f"- timestamp: {now_iso()}",
        f"- output_root: \"{output_root}\"",
        f"- scientific_threshold_decision: **{scientific_decision}**",
        "",
        "## Active blocked states",
    ]
    if active_blocks:
        decision_lines.extend([f"- {b}" for b in active_blocks])
    else:
        decision_lines.append("- none")
    decision_lines.extend(
        [
            "",
            "## Contracts",
            "- scientific_validation_gate.tsv generated",
            "- scientific_claim_gate.tsv generated",
            "- scientific_threshold_evidence_register.tsv generated",
            "- blocked_claims_register.tsv generated",
            "- causal_matrix_scientific_gate_audit.tsv generated",
            "- brief_claim_scientific_gate_audit.tsv generated",
        ]
    )
    (deliver_dir / "runtime_scientific_closure_decision.md").write_text("\n".join(decision_lines) + "\n", encoding="utf-8")

    print(f"SCIENTIFIC_THRESHOLD_DECISION={scientific_decision}")
    # Decision may be NO-GO_SCIENTIFIC_THRESHOLD while operational closure remains analyzable.
    # Return non-zero only on execution failure, not on scientific decision state.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[NO-GO] scientific_threshold_gate exception: {exc}")
        sys.exit(2)
