# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


GO_REQUIRED = [
    Path("qa/oc03c_base_smoke_contract_gate.tsv"),
    Path("qa/oc03c_path_scope_preflight.tsv"),
    Path("qa/portuguese_aq_input_inventory.tsv"),
    Path("qa/portuguese_aq_file_format_audit.tsv"),
    Path("qa/portuguese_aq_station_inventory.tsv"),
    Path("qa/portuguese_aq_timeseries_inventory.tsv"),
    Path("qa/portuguese_aq_normalization_audit.tsv"),
    Path("qa/portuguese_aq_station_to_unit_assignment.tsv"),
    Path("qa/gfas_era5_vs_portuguese_aq_concordance.tsv"),
    Path("qa/portuguese_aq_validation_gate.tsv"),
    Path("qa/portuguese_aq_claim_disposition.md"),
    Path("tables/portuguese_aq_daily_station_2015_2024.csv"),
    Path("tables/portuguese_aq_daily_unit_2015_2024.csv"),
    Path("tables/smoke_proxy_aq_concordance_by_unit.csv"),
    Path("tables/IECH_unit_2015_2024.csv"),
    Path("tables/smoke_days_unit_2015_2024.csv"),
    Path("tables/pop_unit_2015_2025_2030.csv"),
    Path("tables/recurrence_unit_2015_2024.csv"),
    Path("tables/recurrence_municipio_2015_2024.csv"),
    Path("tables/recurrence_unit_year_2015_2024.csv"),
    Path("tables/recurrence_municipio_year_2015_2024.csv"),
    Path("qa/recurrence_classification_audit.tsv"),
    Path("qa/r10_b_fire_feature_semantics.tsv"),
    Path("qa/r10_b_reburn_geometry_audit.tsv"),
    Path("qa/r10_b_recurrence_construct_audit.tsv"),
    Path("qa/r10_b_recurrence_legacy_crosswalk.tsv"),
    Path("qa/r10_b_recurrence_sensitivity.tsv"),
    Path("qa/r10_b_recurrence_method_declaration.md"),
    Path("tables/IECH_scenarios_2026_2030.csv"),
    Path("brief/causal_matrix/causal_matrix_IECH_NUTS3.csv"),
    Path("brief/causal_matrix/causal_matrix_IECH_NUTS3.json"),
    Path("brief/causal_matrix/territorial_screening_matrix_nuts3.csv"),
    Path("brief/causal_matrix/territorial_screening_matrix_municipio.csv"),
    Path("qa/r10_c_git_root_audit.tsv"),
    Path("qa/r10_c_legacy_screening_dominance_audit.tsv"),
    Path("qa/r10_c_dimension_independence_audit.tsv"),
    Path("qa/r10_c_single_axis_dominance_audit.tsv"),
    Path("qa/r10_c_screening_weight_sensitivity.tsv"),
    Path("qa/r10_c_recurrence_sensitivity_propagation.tsv"),
    Path("qa/r10_c_smoke_transport_sensitivity_propagation.tsv"),
    Path("qa/r10_c_screening_legacy_crosswalk.tsv"),
    Path("qa/r10_c_screening_construct_audit.tsv"),
    Path("qa/r10_c_screening_independence_audit.tsv"),
    Path("qa/r10_c_screening_method_declaration.md"),
    Path("brief/Brief_Politica_IECH_2030.md"),
]

CANON_REQUIRED = [
    Path("tables/IECH_municipio_2015_2024.csv"),
    Path("tables/wrb_context_nuts3.csv"),
    Path("tables/territorial_context_nuts3.csv"),
]

OC03C_REQUIRED = [
    Path("qa/oc03c_base_smoke_contract_gate.tsv"),
    Path("qa/oc03c_path_scope_preflight.tsv"),
    Path("qa/portuguese_aq_input_inventory.tsv"),
    Path("qa/portuguese_aq_file_format_audit.tsv"),
    Path("qa/portuguese_aq_station_inventory.tsv"),
    Path("qa/portuguese_aq_timeseries_inventory.tsv"),
    Path("qa/portuguese_aq_normalization_audit.tsv"),
    Path("qa/portuguese_aq_station_to_unit_assignment.tsv"),
    Path("qa/gfas_era5_vs_portuguese_aq_concordance.tsv"),
    Path("qa/portuguese_aq_validation_gate.tsv"),
    Path("qa/portuguese_aq_claim_disposition.md"),
    Path("tables/portuguese_aq_daily_station_2015_2024.csv"),
    Path("tables/portuguese_aq_daily_unit_2015_2024.csv"),
    Path("tables/smoke_proxy_aq_concordance_by_unit.csv"),
]

BASE_SMOKE_CONTRACT_FOR_OC03C_PASS = "BASE_SMOKE_CONTRACT_FOR_OC03C_PASS"
PORTUGUESE_AQ_BASE_SMOKE_BLOCKED = "BLOCKED_BASE_SMOKE_REGRESSION"


CORE_NO_GO = [
    Path("tables/IECH_unit_2015_2024.csv"),
    Path("tables/smoke_days_unit_2015_2024.csv"),
    Path("tables/pop_unit_2015_2025_2030.csv"),
    Path("tables/recurrence_unit_2015_2024.csv"),
]

PLACEHOLDER_PATTERN = re.compile(r"Line\s+\d{3}:\s+IECH pipeline v2 audit detail line\.", re.IGNORECASE)


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def sniff_delimiter(path: Path, sample_bytes: int = 65536) -> str:
    data = path.read_bytes()[:sample_bytes]
    text = data.decode("utf-8-sig", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return "	"
    if suffix == ".csv":
        counts = {";": text.count(";"), ",": text.count(",")}
        return ";" if counts[";"] >= counts[","] and counts[";"] > 0 else ","
    counts = {";": text.count(";"), ",": text.count(","), "	": text.count("	")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    delim = sniff_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def safe_float(val: object):
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "na", "none", "null"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _record_check(rows: List[Dict[str, str]], group: str, rel: Path, status: str, detail: str) -> None:
    rows.append(
        {
            "timestamp": now_iso(),
            "check_id": f"{group}:{rel.as_posix()}",
            "group": group,
            "artifact": rel.as_posix(),
            "exists": "YES" if status in ("PASS", "WARN") else "NO",
            "status": status,
            "detail": detail,
        }
    )


def _write_gate_outputs(qa_dir: Path, check_rows: List[Dict[str, str]], decision: str, holds: List[str], notes: List[str]) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_checks = qa_dir / "QA_checks.csv"
    run_log = qa_dir / "run_log.txt"

    with qa_checks.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["timestamp", "check_id", "group", "artifact", "exists", "status", "detail"]
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()
        for row in check_rows:
            w.writerow(row)
        w.writerow(
            {
                "timestamp": now_iso(),
                "check_id": "SUMMARY:decision",
                "group": "SUMMARY",
                "artifact": "-",
                "exists": "YES",
                "status": decision,
                "detail": "; ".join(holds) if holds else "NO_HOLDS",
            }
        )

    lines = [f"[{now_iso()}] QA_GATE_V2 decision={decision}"]
    if holds:
        for h in holds:
            lines.append(f"[{now_iso()}] {h}")
    for note in notes:
        lines.append(f"[{now_iso()}] {note}")
    with run_log.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def evaluate_output_root(output_root: Path) -> Tuple[str, str, List[str], List[Dict[str, str]]]:
    check_rows: List[Dict[str, str]] = []
    notes: List[str] = []
    holds: List[str] = []
    hard_fail: List[str] = []

    # GO-required artifacts
    for rel in GO_REQUIRED:
        abs_path = output_root / rel
        if abs_path.exists():
            _record_check(check_rows, "GO_REQUIRED", rel, "PASS", "artifact exists")
        else:
            _record_check(check_rows, "GO_REQUIRED", rel, "FAIL", "artifact missing")

    # Canon completeness artifacts
    for rel in CANON_REQUIRED:
        abs_path = output_root / rel
        if abs_path.exists():
            _record_check(check_rows, "CANON_REQUIRED", rel, "PASS", "artifact exists")
        else:
            _record_check(check_rows, "CANON_REQUIRED", rel, "FAIL", "artifact missing")

    for rel in OC03C_REQUIRED:
        abs_path = output_root / rel
        if abs_path.exists():
            _record_check(check_rows, "OC03C_REQUIRED", rel, "PASS", "artifact exists")
        else:
            _record_check(check_rows, "OC03C_REQUIRED", rel, "FAIL", "artifact missing")

    oc03c_missing = [rel.as_posix() for rel in OC03C_REQUIRED if not (output_root / rel).exists()]
    if oc03c_missing:
        holds.append("HOLD OC-03C AQ VALIDATION")
        notes.append("OC-03C artifacts missing: " + ", ".join(oc03c_missing[:8]))
    else:
        try:
            gate_rows = read_csv_rows(output_root / "qa/portuguese_aq_validation_gate.tsv")
            gate_map = {str(row.get("metric") or "").strip(): str(row.get("value") or "").strip() for row in gate_rows}
            base_rows = read_csv_rows(output_root / "qa/oc03c_base_smoke_contract_gate.tsv")
            base_map = {str(row.get("metric") or "").strip(): str(row.get("value") or "").strip() for row in base_rows}
            oc03c_status = gate_map.get("portuguese_aq_validation_status", "")
            health_status = gate_map.get("health_exposure_claim_status", "")
            base_status = base_map.get("base_smoke_contract_for_oc03c_status", "") or base_map.get("final_state", "")
            if not oc03c_status:
                holds.append("HOLD OC-03C AQ VALIDATION")
                notes.append("portuguese_aq_validation_gate.tsv missing portuguese_aq_validation_status")
            else:
                notes.append(f"oc03c_status={oc03c_status}")
            if not base_status:
                holds.append("HOLD OC-03C AQ VALIDATION")
                notes.append("oc03c_base_smoke_contract_gate.tsv missing base_smoke_contract_for_oc03c_status")
            else:
                notes.append(f"oc03c_base_smoke_status={base_status}")
            if oc03c_status == PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
                if base_status != PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
                    holds.append("HOLD OC-03C AQ VALIDATION")
                    notes.append("OC-03C reported BLOCKED_BASE_SMOKE_REGRESSION without matching base smoke gate state")
            elif base_status != BASE_SMOKE_CONTRACT_FOR_OC03C_PASS:
                holds.append("HOLD OC-03C AQ VALIDATION")
                notes.append("OC-03C AQ artifacts were produced without a passing base smoke contract gate")
            if health_status == "HEALTH_EXPOSURE_VALIDATED":
                holds.append("HOLD OC-03C AQ VALIDATION")
                notes.append("OC-03C reported HEALTH_EXPOSURE_VALIDATED without dedicated threshold-comparison artifacts")
            scope_rows = read_csv_rows(output_root / "qa/oc03c_path_scope_preflight.tsv")
            summary_row = next((row for row in scope_rows if str(row.get("check_id") or "").strip() == "OC03C_SUMMARY"), None)
            if summary_row is None:
                holds.append("HOLD OC-03C AQ VALIDATION")
                notes.append("oc03c_path_scope_preflight.tsv missing OC03C_SUMMARY row")
            elif str(summary_row.get("status") or "").strip().upper() != "PATH_SCOPE_PASS":
                holds.append("HOLD OC-03C AQ VALIDATION")
                notes.append("OC-03C path-scope summary is not PATH_SCOPE_PASS")
        except Exception as exc:
            holds.append("HOLD OC-03C AQ VALIDATION")
            notes.append(f"could not parse OC-03C audit artifacts: {exc}")

    for rel in CORE_NO_GO:
        if not (output_root / rel).exists():
            hard_fail.append(f"Core output missing: {rel.as_posix()}")

    r10b_audit = output_root / "qa" / "recurrence_classification_audit.tsv"
    r10b_construct = output_root / "qa" / "r10_b_recurrence_construct_audit.tsv"
    if not r10b_audit.exists() or not r10b_construct.exists():
        holds.append("HOLD R10-B RECURRENCE")
        notes.append("R10-B scientific recurrence audit artifacts are missing")
    else:
        try:
            audit_rows = read_csv_rows(r10b_audit)
            construct_rows = read_csv_rows(r10b_construct)
            if any(str(row.get("status") or "").strip().upper() in ("HOLD", "FAIL", "BLOCKED") for row in audit_rows + construct_rows):
                holds.append("HOLD R10-B RECURRENCE")
                notes.append("R10-B recurrence audit contains HOLD/FAIL/BLOCKED")
        except Exception as exc:
            holds.append("HOLD R10-B RECURRENCE")
            notes.append(f"R10-B recurrence audit unreadable: {exc}")

    r10c_construct = output_root / "qa" / "r10_c_screening_construct_audit.tsv"
    r10c_git = output_root / "qa" / "r10_c_git_root_audit.tsv"
    r10c_matrices = [
        output_root / "brief/causal_matrix/territorial_screening_matrix_nuts3.csv",
        output_root / "brief/causal_matrix/territorial_screening_matrix_municipio.csv",
    ]
    if not r10c_construct.exists() or not r10c_git.exists() or any(not path.exists() for path in r10c_matrices):
        holds.append("HOLD R10-C SCREENING INDEPENDENCE")
        notes.append("R10-C screening artifacts are missing")
    else:
        try:
            construct_rows = read_csv_rows(r10c_construct)
            git_rows = read_csv_rows(r10c_git)
            if any(str(row.get("status") or "").strip().upper() != "PASS" for row in construct_rows):
                holds.append("HOLD R10-C SCREENING INDEPENDENCE")
                notes.append("R10-C construct audit contains non-PASS status")
            if not any(row.get("metric") == "decision" and row.get("value") == "PASS" for row in git_rows):
                holds.append("HOLD R10-C SCREENING INDEPENDENCE")
                notes.append("R10-C Git root audit decision is not PASS")
            for path, expected in zip(r10c_matrices, (24, 278)):
                matrix_rows = read_csv_rows(path)
                if len(matrix_rows) != expected:
                    holds.append("HOLD R10-C SCREENING INDEPENDENCE")
                    notes.append(f"{path.name} rows={len(matrix_rows)} expected={expected}")
        except Exception as exc:
            holds.append("HOLD R10-C SCREENING INDEPENDENCE")
            notes.append(f"could not parse R10-C screening artifacts: {exc}")

    # HOLD rules
    if not (output_root / "tables/IECH_municipio_2015_2024.csv").exists():
        holds.append("HOLD MUNICIPAL")

    if not (output_root / "tables/wrb_context_nuts3.csv").exists():
        holds.append("HOLD WRB INTEGRATION")
    else:
        try:
            wrb_rows = read_csv_rows(output_root / "tables/wrb_context_nuts3.csv")
            if not wrb_rows:
                holds.append("HOLD WRB INTEGRATION")
            else:
                all_missing = True
                for r in wrb_rows:
                    miss = safe_float(r.get("wrb_missing_flag"))
                    if miss is None or miss < 1:
                        all_missing = False
                        break
                if all_missing:
                    holds.append("HOLD WRB INTEGRATION")
                    notes.append("wrb_context_nuts3.csv exists but all rows have wrb_missing_flag=1")
        except Exception as exc:
            holds.append("HOLD WRB INTEGRATION")
            notes.append(f"could not parse wrb_context_nuts3.csv: {exc}")

    terr_csv = output_root / "tables/territorial_context_nuts3.csv"
    if not terr_csv.exists():
        holds.append("HOLD WUI")
    else:
        try:
            terr_rows = read_csv_rows(terr_csv)
            if not terr_rows:
                holds.append("HOLD WUI")
            else:
                any_wui = False
                for r in terr_rows:
                    v = safe_float(r.get("wui_proxy"))
                    if v is not None and v > 0:
                        any_wui = True
                        break
                if not any_wui:
                    holds.append("HOLD WUI")
                    notes.append("territorial_context_nuts3.csv has no positive wui_proxy values")
        except Exception as exc:
            holds.append("HOLD WUI")
            notes.append(f"could not parse territorial_context_nuts3.csv: {exc}")

    causal_csv = output_root / "brief/causal_matrix/causal_matrix_IECH_NUTS3.csv"
    causal_json = output_root / "brief/causal_matrix/causal_matrix_IECH_NUTS3.json"
    if (not causal_csv.exists()) or (not causal_json.exists()):
        holds.append("HOLD CAUSAL MATRIX")
    else:
        try:
            crows = read_csv_rows(causal_csv)
            if not crows:
                holds.append("HOLD CAUSAL MATRIX")
                notes.append("causal_matrix_IECH_NUTS3.csv has 0 rows")
            else:
                any_missing_components = any((r.get("missing_components") or "").strip() not in ("", "[]", "none", "None") for r in crows)
                if any_missing_components:
                    holds.append("HOLD CAUSAL MATRIX")
                    notes.append("causal_matrix missing_components indicates unresolved components")
        except Exception as exc:
            holds.append("HOLD CAUSAL MATRIX")
            notes.append(f"could not parse causal matrix csv: {exc}")

    brief_path = output_root / "brief/Brief_Politica_IECH_2030.md"
    brief_text = ""
    if not brief_path.exists():
        holds.append("HOLD BRIEF")
    else:
        try:
            brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
            if PLACEHOLDER_PATTERN.search(brief_text):
                holds.append("HOLD BRIEF")
                notes.append("brief contains placeholder audit lines")
            if len(brief_text.strip()) < 1200:
                holds.append("HOLD BRIEF")
                notes.append("brief too short for substantive policy content")
        except Exception as exc:
            holds.append("HOLD BRIEF")
            notes.append(f"could not parse brief: {exc}")

    semantics_tsv = output_root / "qa/iech_reporting_semantics_audit.tsv"
    reframe_tsv = output_root / "qa/iech_reporting_reframe_audit.tsv"
    audit_tsv = semantics_tsv if semantics_tsv.exists() else reframe_tsv
    if not audit_tsv.exists():
        holds.append("HOLD IECH REPORTING REFRAME")
        notes.append("iech_reporting_semantics_audit.tsv missing")
    else:
        try:
            reframe_rows = read_csv_rows(audit_tsv)
            if not reframe_rows:
                holds.append("HOLD IECH REPORTING REFRAME")
                notes.append(f"{audit_tsv.name} has 0 rows")
            else:
                metric_map = {str(r.get("metric") or "").strip().lower(): r for r in reframe_rows if str(r.get("metric") or "").strip()}

                def reframe_text(*keys: str) -> str:
                    for key in keys:
                        row = metric_map.get(key.strip().lower())
                        if not row:
                            continue
                        value = str(row.get("value") or row.get("status") or row.get("observed") or "").strip()
                        if value:
                            return value
                    return ""

                def reframe_status(*keys: str) -> str:
                    for key in keys:
                        row = metric_map.get(key.strip().lower())
                        if not row:
                            continue
                        value = str(row.get("status") or row.get("value") or "").strip()
                        if value:
                            return value
                    return ""

                required_pass = [
                    "IECH_REPORTING_REFRAME_STATUS",
                    "population_smoke_day_burden_proxy_column_present",
                    "population_total_column_present",
                    "claim_status_proxy_not_normalized",
                    "legacy_physical_burden_columns_empty",
                    "population_smoke_day_burden_proxy_equals_smoke_days_times_population_total",
                ]
                failed_metrics = [metric for metric in required_pass if reframe_status(metric).upper() != "PASS"]
                if "legacy_physical_burden_columns_empty" in failed_metrics and reframe_status(
                    "legacy_IECH_deprecated_if_present"
                ).upper() == "PASS":
                    failed_metrics.remove("legacy_physical_burden_columns_empty")
                if (
                    "population_smoke_day_burden_proxy_equals_smoke_days_times_population_total" in failed_metrics
                    and reframe_status("legacy_IECH_deprecated_if_present").upper() == "PASS"
                    and reframe_status("population_smoke_burden_proxy_equals_smoke_hours_times_population_total").upper()
                    == "PASS"
                ):
                    failed_metrics.remove("population_smoke_day_burden_proxy_equals_smoke_days_times_population_total")
                if (
                    "population_smoke_day_burden_proxy_column_present" in failed_metrics
                    and reframe_status("population_smoke_burden_proxy_column_present").upper() == "PASS"
                ):
                    failed_metrics.remove("population_smoke_day_burden_proxy_column_present")
                if failed_metrics:
                    holds.append("HOLD IECH REPORTING REFRAME")
                    notes.append("reframe audit failed metrics: " + ", ".join(failed_metrics))
                forbidden_normalized = int(safe_float(reframe_text("forbidden_normalized_IECH_claims")) or 0)
                forbidden_health = int(safe_float(reframe_text("forbidden_health_exposure_claims")) or 0)
                if forbidden_normalized > 0:
                    holds.append("HOLD IECH REPORTING REFRAME")
                    notes.append(f"forbidden normalized IECH claims detected: {forbidden_normalized}")
                if forbidden_health > 0:
                    holds.append("HOLD IECH REPORTING REFRAME")
                    notes.append(f"forbidden health exposure claims detected: {forbidden_health}")
        except Exception as exc:
            holds.append("HOLD IECH REPORTING REFRAME")
            notes.append(f"could not parse {audit_tsv.name}: {exc}")

    if brief_text:
        forbidden_brief_patterns = [
            r"normalized iech",
            r"per\s*capita iech",
            r"individual iech",
            r"individual smoke exposure",
            r"population exposed differs from total",
            r"exposure fraction\s*<\s*1",
            r"health exposure",
            r"epidemiological risk",
        ]
        matched_patterns = [pat for pat in forbidden_brief_patterns if re.search(pat, brief_text, flags=re.IGNORECASE)]
        if matched_patterns:
            holds.append("HOLD IECH REPORTING REFRAME")
            notes.append("brief contains forbidden IECH semantic claims: " + ", ".join(matched_patterns[:6]))

    # Canon/objectives alignment gate integration
    obj_tsv = output_root / "qa/objectives_canon_alignment_report.tsv"
    if not obj_tsv.exists():
        holds.append("HOLD OBJECTIVES CANON")
        notes.append("objectives_canon_alignment_report.tsv missing")
    else:
        try:
            obj_rows = read_csv_rows(obj_tsv)
            if not obj_rows:
                holds.append("HOLD OBJECTIVES CANON")
                notes.append("objectives_canon_alignment_report.tsv has 0 rows")
            else:
                bad = []
                for r in obj_rows:
                    st = (r.get("status") or "").strip().upper()
                    if st in ("HOLD", "FAIL", "NO-GO", "BLOCKED"):
                        bad.append((r.get("objective_id") or "?", st))
                if bad:
                    holds.append("HOLD OBJECTIVES CANON")
                    notes.append("objectives gate unresolved: " + ", ".join(f"{oid}:{st}" for oid, st in bad[:8]))
        except Exception as exc:
            holds.append("HOLD OBJECTIVES CANON")
            notes.append(f"could not parse objectives_canon_alignment_report.tsv: {exc}")

    inputs_json = output_root / "qa/inputs_resolved.json"
    if not inputs_json.exists():
        holds.append("HOLD OBJECTIVES CANON")
        notes.append("inputs_resolved.json missing for canon traceability")
    else:
        try:
            import json

            payload = json.loads(inputs_json.read_text(encoding="utf-8-sig"))
            meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
            canon_path = str(meta.get("objectives_canon_path", "")).strip() if isinstance(meta, dict) else ""
            canon_sha = str(meta.get("objectives_canon_sha256", "")).strip() if isinstance(meta, dict) else ""
            objectives = meta.get("objectives_recognized", []) if isinstance(meta, dict) else []
            if not canon_path or not canon_sha:
                holds.append("HOLD OBJECTIVES CANON")
                notes.append("inputs_resolved.json meta missing objectives_canon_path/objectives_canon_sha256")
            else:
                notes.append(f"canon_path={canon_path}")
                notes.append(f"canon_sha256={canon_sha}")
                notes.append(f"objectives_recognized={objectives}")

            route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
            route_decision = str(meta.get("smoke_route_decision") or "").strip()
            if not route_selected:
                holds.append("HOLD SMOKE ROUTE")
                notes.append("inputs_resolved.json meta missing smoke_route_selected/smoke_route_mode")
            elif route_selected in ("BLOCKED_DECODER_REQUIRED", "v0_parquet_proxy_degraded", "NO-GO_SMOKE_ROUTE"):
                holds.append("HOLD SMOKE ROUTE")
                notes.append(f"smoke route blocked/degraded: route_selected={route_selected}; route_decision={route_decision}")
        except Exception as exc:
            holds.append("HOLD OBJECTIVES CANON")
            notes.append(f"could not parse inputs_resolved.json canon meta: {exc}")

    scientific_gate_tsv = output_root / "qa/scientific_validation_gate.tsv"
    if not scientific_gate_tsv.exists():
        holds.append("HOLD SCIENTIFIC GATE")
        notes.append("scientific_validation_gate.tsv missing")
    else:
        try:
            gate_rows = read_csv_rows(scientific_gate_tsv)
            blocked = [
                r
                for r in gate_rows
                if (r.get("gate_status") or "").strip().upper().startswith("BLOCKED")
                and (r.get("final_decision_effect") or "").strip().upper() != "NONE"
            ]
            if blocked:
                holds.append("HOLD SCIENTIFIC GATE")
                notes.append(
                    "scientific gate blocked states: "
                    + ", ".join(f"{r.get('threshold_id') or '?'}:{r.get('gate_status') or '?'}" for r in blocked[:8])
                )
        except Exception as exc:
            holds.append("HOLD SCIENTIFIC GATE")
            notes.append(f"could not parse scientific_validation_gate.tsv: {exc}")

    # deduplicate while preserving order
    unique_holds: List[str] = []
    seen = set()
    for h in holds:
        if h not in seen:
            seen.add(h)
            unique_holds.append(h)
    holds = unique_holds

    if hard_fail:
        decision = "NO-GO"
        summary = "; ".join(hard_fail)
    elif holds:
        decision = "HOLD"
        summary = "; ".join(holds)
    else:
        decision = "GO"
        summary = "All GO and canon requirements present with no HOLD flags."

    _write_gate_outputs(output_root / "qa", check_rows, decision, holds, notes)
    return decision, summary, holds, check_rows


def run_checks(tables_dir: Path, brief_path: Path):
    output_root = tables_dir.parent
    decision, summary, _holds, _rows = evaluate_output_root(output_root)
    # Compatibility contract for moduleC_pipeline_v2:
    # - True should allow pipeline continuation (GO or HOLD)
    # - False only for hard runtime failure/no-go
    ok = decision != "NO-GO"
    return ok, f"{decision}: {summary}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    ap.add_argument("--modulec-datos", required=True)
    ap.add_argument("--inc-new", required=True)
    ap.add_argument("--output-root", required=False, default=None)
    args = ap.parse_args()

    modulec_datos = Path(args.modulec_datos)
    if args.output_root:
        output_root = Path(args.output_root)
    else:
        output_root = modulec_datos.parent / "03_outputs"

    decision, summary, holds, _rows = evaluate_output_root(output_root)
    print(f"QA_GATE_V2 decision={decision}")
    print(summary)
    if holds:
        for h in holds:
            print(h)

    if decision == "GO":
        return 0
    if decision == "HOLD":
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())






