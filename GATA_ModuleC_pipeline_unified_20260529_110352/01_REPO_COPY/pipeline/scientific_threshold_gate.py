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

FORBIDDEN_DIRECT_METHOD_TOKENS = ("flat_single_anchor", "interpolated_from_anchors", "extrapolated_from_anchors")
MIN_OC03_DIRECT_UNIQUE_UNITS = 24
BASE_SMOKE_CONTRACT_FOR_OC03C_PASS = "BASE_SMOKE_CONTRACT_FOR_OC03C_PASS"
PORTUGUESE_AQ_BASE_SMOKE_BLOCKED = "BLOCKED_BASE_SMOKE_REGRESSION"
FORBIDDEN_PRIMARY_SOURCE_TOKENS = (
    "parquetfiles 2017.zip",
    "parquetfiles 2022.zip",
    "era5_d016a6f04c5e420341cf0e7293fcfb56.zip",
    "\\oc03_v9d",
    "\\oc03_v11",
    "\\oc03_v12",
    "\\03_outputs\\oc03_v",
)
IECH_PROXY_FINAL_DECISION = "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_AND_POPULATION_BURDEN_SEMANTICS"
IECH_PROXY_AQ_PROTOCOL = "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL"
IECH_PROXY_INDICATOR_NAME = "population_smoke_burden_proxy"
IECH_PROXY_INDICATOR_UNIT = "proxy person-hours"
IECH_PROXY_CLAIM_STATUS = "OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH"


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def sniff_delim(path: Path) -> str:
    text = path.read_bytes()[:65536].decode("utf-8-sig", errors="replace")
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


def _first_present_text(row: Dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_present_float(row: Dict[str, str], *keys: str):
    for key in keys:
        value = safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _norm_path_text(value: object) -> str:
    return str(value or "").replace("/", "\\").lower().strip()


def _is_forbidden_primary_source(*paths: object) -> bool:
    norm_paths = [_norm_path_text(path) for path in paths if str(path or "").strip()]
    for norm in norm_paths:
        if any(tok in norm for tok in FORBIDDEN_PRIMARY_SOURCE_TOKENS):
            return True
        if "\\cam-gfas (ads)" in norm and "datos_recovery_" not in norm:
            return True
    return False


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
    positive_signal_direct_years: set[int] = set()
    for r in rows:
        y = safe_float(r.get("year"))
        v = safe_float(r.get("smoke_days"))
        method = (r.get("smoke_method") or r.get("method") or "").strip().lower()
        if y is None or v is None:
            continue
        year_int = int(y)
        if ("direct_year" in method) or (not method):
            by_year.setdefault(year_int, set()).add(round(v, 8))
            if v > 0:
                positive_signal_direct_years.add(year_int)
    if not positive_signal_direct_years:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No direct-signal smoke years with positive smoke_days", {}
    unique_counts = {y: len(by_year.get(y, set())) for y in sorted(positive_signal_direct_years)}
    blocked_years = [y for y, n in unique_counts.items() if n <= 1]
    if blocked_years:
        return (
            "BLOCKED_SPATIAL_SMOKE_CLAIM",
            "Direct years with <=1 unique smoke_days across units: " + ",".join(str(y) for y in sorted(blocked_years)),
            unique_counts,
        )
    return "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION", "Direct-signal smoke spatial differentiation detected.", unique_counts


def evaluate_iech_ranking(iech_mean_csv: Path) -> Tuple[str, str, int]:
    if not iech_mean_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024_mean.csv missing", 0
    rows = read_csv_rows(iech_mean_csv)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024_mean.csv empty", 0
    column = ""
    for candidate in (
        "population_smoke_burden_proxy_mean_2015_2024",
        "IECH_mean_2015_2024",
        "population_smoke_burden_proxy_mean",
        "IECH_mean",
        IECH_PROXY_INDICATOR_NAME,
        "IECH",
    ):
        if candidate in rows[0]:
            column = candidate
            break
    if not column:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No IECH proxy-burden mean column found", 0
    vals = []
    for r in rows:
        v = safe_float(r.get(column))
        if v is not None:
            vals.append(round(v, 8))
    n_unique = len(set(vals))
    observed = f"{column} unique count={n_unique}"
    if n_unique <= 1:
        return "BLOCKED_IECH_RANKING", observed, n_unique
    return "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION", observed, n_unique


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


def evaluate_oc03c_base_smoke_contract(qa_dir: Path) -> Tuple[str, str, Dict[str, str]]:
    gate_path = qa_dir / "oc03c_base_smoke_contract_gate.tsv"
    if not gate_path.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "oc03c_base_smoke_contract_gate.tsv missing", {}
    rows = read_csv_rows(gate_path)
    gate_map = {str(row.get("metric") or "").strip(): str(row.get("value") or "").strip() for row in rows}
    status = (gate_map.get("base_smoke_contract_for_oc03c_status", "") or gate_map.get("final_state", "")).strip()
    if not status:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "base_smoke_contract_for_oc03c_status missing", gate_map
    observed = f"base_smoke_contract_for_oc03c_status={status}"
    return status, observed, gate_map


def evaluate_portuguese_aq_validation(qa_dir: Path) -> Tuple[str, str, Dict[str, str]]:
    gate_path = qa_dir / "portuguese_aq_validation_gate.tsv"
    if not gate_path.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "portuguese_aq_validation_gate.tsv missing", {}
    rows = read_csv_rows(gate_path)
    gate_map = {str(row.get("metric") or "").strip(): str(row.get("value") or "").strip() for row in rows}
    status = gate_map.get("portuguese_aq_validation_status", "").strip()
    protocol = gate_map.get("aq_protocol_decision", "").strip()
    claim_disposition = gate_map.get("claim_disposition", "").strip()
    health_status = gate_map.get("health_exposure_claim_status", "").strip()
    if not status:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "portuguese_aq_validation_status missing", gate_map
    observed = (
        f"portuguese_aq_validation_status={status}; "
        f"aq_protocol_decision={protocol or 'EMPTY'}; "
        f"claim_disposition={claim_disposition or 'EMPTY'}; "
        f"health_exposure_claim_status={health_status or 'EMPTY'}"
    )
    if health_status == "HEALTH_EXPOSURE_VALIDATED":
        return "BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM", observed, gate_map
    return status, observed, gate_map


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


def read_smoke_route_scope(inputs_json: Path) -> Dict[str, str]:
    if not inputs_json.exists():
        return {}
    try:
        payload = json.loads(inputs_json.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        return {}
    return {
        "reason": str(meta.get("smoke_route_reason") or "").strip(),
        "allowed_use": str(meta.get("smoke_route_allowed_use") or "").strip(),
        "forbidden_use": str(meta.get("smoke_route_forbidden_use") or "").strip(),
    }




def _metric_int_value(metric_map: Dict[str, Dict[str, str]], *keys: str) -> int:
    for key in keys:
        row = metric_map.get(key.strip().lower())
        if not row:
            continue
        value = safe_float(row.get("value") or row.get("observed") or row.get("status"))
        if value is not None:
            return int(value)
    return 0


def _metric_text_value(metric_map: Dict[str, Dict[str, str]], *keys: str) -> str:
    for key in keys:
        row = metric_map.get(key.strip().lower())
        if not row:
            continue
        value = str(row.get("value") or row.get("observed") or row.get("detail") or "").strip()
        if value:
            return value
    return ""

def evaluate_direct_decoder_contract(output_root: Path) -> Tuple[str, str]:
    inputs_json = output_root / "qa" / "inputs_resolved.json"
    decoder_audit = output_root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv"
    smoke_audit = output_root / "qa" / "smoke_route_audit.tsv"
    if not inputs_json.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "inputs_resolved.json missing"
    if not decoder_audit.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "gfas_era5_decoder_daily_spatial_audit.tsv missing"
    if not smoke_audit.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "smoke_route_audit.tsv missing"

    payload = json.loads(inputs_json.read_text(encoding="utf-8-sig"))
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    paths = payload.get("paths", {}) if isinstance(payload, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(paths, dict):
        paths = {}

    route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
    effective_root = str(paths.get("smoke_effective_data_root") or "").replace("/", "\\").lower()
    effective_path = str(paths.get("smoke_effective_source_path") or "").replace("/", "\\").lower()
    recovery_flag = bool(meta.get("smoke_route_detected_sources", {}).get("effective_source_is_recovery")) if isinstance(meta.get("smoke_route_detected_sources"), dict) else False

    if route_selected != "v0_gfas_era5_real":
        return "BLOCKED_DECODER_REQUIRED", f"route_selected={route_selected or 'EMPTY'}"
    if not recovery_flag or "datos_recovery_2015_2024_pipeline_grib" not in (effective_root + " " + effective_path):
        return "BLOCKED_FOR_REQUIRED_VARIABLE", f"effective recovery smoke root missing in inputs_resolved: {effective_root or effective_path}"
    if _is_forbidden_primary_source(effective_root, effective_path):
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", f"forbidden legacy primary smoke source detected: {effective_path or effective_root}"

    decoder_rows = read_csv_rows(decoder_audit)
    decoder_map = {str(r.get("metric") or "").strip().lower(): r for r in decoder_rows}
    unique_years = _metric_int_value(decoder_map, "uniqueyears", "unique_years")
    unique_dates = _metric_int_value(decoder_map, "uniquedates", "unique_dates")
    unique_units = _metric_int_value(decoder_map, "uniqueunits", "unique_units")
    all_years_present = _metric_int_value(decoder_map, "years_2015_2024_present")
    all_months_present = _metric_int_value(decoder_map, "all_months_present_each_year")
    all_expected_dates_present = _metric_int_value(decoder_map, "all_expected_dates_present")
    dates_per_year = _metric_text_value(decoder_map, "dates_per_year")
    months_present_by_year = _metric_text_value(decoder_map, "months_present_by_year")
    if unique_years < 10:
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", f"direct decoder depth insufficient: unique_years={unique_years}, unique_dates={unique_dates}"
    if unique_units < MIN_OC03_DIRECT_UNIQUE_UNITS:
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", f"direct decoder unit coverage insufficient: unique_units={unique_units}"
    if all_years_present != 1:
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", f"direct decoder missing required years: years_2015_2024_present={all_years_present}; dates_per_year={dates_per_year or 'EMPTY'}"
    if all_months_present != 1:
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", f"direct decoder missing months: months_present_by_year={months_present_by_year or 'EMPTY'}"
    if all_expected_dates_present != 1:
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", f"direct decoder missing expected annual dates: dates_per_year={dates_per_year or 'EMPTY'}"

    smoke_rows = read_csv_rows(smoke_audit)
    bad_methods = sorted(
        {
            str(r.get("smoke_method") or r.get("method") or "").strip()
            for r in smoke_rows
            if any(tok in str(r.get("smoke_method") or r.get("method") or "").strip().lower() for tok in FORBIDDEN_DIRECT_METHOD_TOKENS)
        }
    )
    if bad_methods:
        return "BLOCKED_SPATIAL_SMOKE_CLAIM", "forbidden direct smoke methods present: " + ", ".join(bad_methods[:6])

    return "THRESHOLD_DEFINED_AS_INDEXED_METHOD", (
        f"direct decoder depth passed: unique_years={unique_years}, unique_dates={unique_dates}, "
        f"unique_units={unique_units}, all_expected_dates_present={all_expected_dates_present}, dates_per_year={dates_per_year}, "
        f"months_present_by_year={months_present_by_year}"
    )


def evaluate_population_cancellation(iech_hist_csv: Path) -> Tuple[str, str]:
    if not iech_hist_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024.csv missing"
    rows = read_csv_rows(iech_hist_csv)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024.csv empty"

    comparable_proxy_vs_expo = 0
    equal_proxy_vs_expo = 0
    comparable_proxy_vs_hours = 0
    equal_proxy_vs_hours = 0
    proxy_claim_rows = 0
    for r in rows:
        proxy_value = _first_present_float(r, IECH_PROXY_INDICATOR_NAME, "IECH")
        expo_value = _first_present_float(r, "expo_person_hours")
        hours_value = _first_present_float(r, "smoke_hours_equiv")
        claim_status = _first_present_text(r, "claim_status")
        if claim_status == IECH_PROXY_CLAIM_STATUS:
            proxy_claim_rows += 1
        if proxy_value is not None and expo_value is not None:
            comparable_proxy_vs_expo += 1
            if abs(proxy_value - expo_value) <= 1e-9:
                equal_proxy_vs_expo += 1
        if proxy_value is not None and hours_value is not None:
            comparable_proxy_vs_hours += 1
            if abs(proxy_value - hours_value) <= 1e-9:
                equal_proxy_vs_hours += 1
    if comparable_proxy_vs_expo == 0 and comparable_proxy_vs_hours == 0:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No comparable IECH proxy-burden rows"
    if comparable_proxy_vs_hours > 0 and equal_proxy_vs_hours == comparable_proxy_vs_hours:
        return (
            "BLOCKED_POPULATION_EXPOSURE_CLAIM",
            f"{IECH_PROXY_INDICATOR_NAME} equals smoke_hours_equiv in {equal_proxy_vs_hours}/{comparable_proxy_vs_hours} rows",
        )
    if comparable_proxy_vs_expo > 0 and equal_proxy_vs_expo == comparable_proxy_vs_expo:
        claim_note = IECH_PROXY_CLAIM_STATUS if proxy_claim_rows > 0 else "claim_status not declared"
        return (
            "OPERATIONAL_POPULATION_SMOKE_BURDEN_PROXY",
            f"{IECH_PROXY_INDICATOR_NAME} equals expo_person_hours in {equal_proxy_vs_expo}/{comparable_proxy_vs_expo} rows; {claim_note}",
        )
    if comparable_proxy_vs_expo > 0:
        unequal_rows = comparable_proxy_vs_expo - equal_proxy_vs_expo
        return (
            "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
            f"{IECH_PROXY_INDICATOR_NAME} differs from expo_person_hours in {unequal_rows}/{comparable_proxy_vs_expo} rows",
        )
    unequal_rows = comparable_proxy_vs_hours - equal_proxy_vs_hours
    return (
        "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
        f"{IECH_PROXY_INDICATOR_NAME} differs from smoke_hours_equiv in {unequal_rows}/{comparable_proxy_vs_hours} rows",
    )


def evaluate_iech_proxy_semantics(reframe_audit_tsv: Path) -> Tuple[str, str]:
    if not reframe_audit_tsv.exists():
        return "BLOCKED_PROXY_BURDEN_SEMANTICS", f"{reframe_audit_tsv.name} missing"
    rows = read_csv_rows(reframe_audit_tsv)
    if not rows:
        return "BLOCKED_PROXY_BURDEN_SEMANTICS", f"{reframe_audit_tsv.name} empty"
    metric_map = {str(r.get("metric") or "").strip().lower(): r for r in rows if str(r.get("metric") or "").strip()}

    def metric_text(*keys: str) -> str:
        return _metric_text_value(metric_map, *keys)

    def metric_status(*keys: str) -> str:
        for key in keys:
            row = metric_map.get(key.strip().lower())
            if not row:
                continue
            value = str(row.get("status") or row.get("value") or row.get("observed") or "").strip()
            if value:
                return value
        return ""

    required_pass = [
        "IECH_REPORTING_REFRAME_STATUS",
        "population_smoke_burden_proxy_column_present",
        "population_total_column_present",
        "population_exposed_assumed_column_present",
        "exposure_fraction_assumption_all_1",
        "claim_status_proxy_not_normalized",
        "legacy_IECH_deprecated_if_present",
        "population_smoke_burden_proxy_equals_expo_person_hours",
        "population_smoke_burden_proxy_equals_smoke_hours_times_population_total",
    ]
    failed = [key for key in required_pass if metric_status(key).upper() != "PASS"]
    forbidden_normalized = int(safe_float(metric_text("forbidden_normalized_IECH_claims")) or 0)
    forbidden_health = int(safe_float(metric_text("forbidden_health_exposure_claims")) or 0)
    if failed or forbidden_normalized > 0 or forbidden_health > 0:
        detail = []
        if failed:
            detail.append("failed=" + ",".join(failed))
        detail.append(f"forbidden_normalized_IECH_claims={forbidden_normalized}")
        detail.append(f"forbidden_health_exposure_claims={forbidden_health}")
        return "BLOCKED_PROXY_BURDEN_SEMANTICS", "; ".join(detail)
    claim_status = metric_text("claim_status_proxy_not_normalized") or IECH_PROXY_CLAIM_STATUS
    return (
        "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
        f"{IECH_PROXY_INDICATOR_NAME} semantics verified; claim_status={claim_status}; exposure_fraction=1.0; population_exposed=population_total",
    )


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
        "BLOCKED_NORMALIZED_IECH_CLAIM": [
            r"normalized iech",
            r"per\s*capita iech",
            r"individual iech",
            r"individual smoke exposure",
            r"population exposed differs from total",
            r"exposure fraction\s*<\s*1",
        ],
    }
    scan_blocks = sorted(set(active_blocks) | {"BLOCKED_NORMALIZED_IECH_CLAIM"})
    hits: List[Tuple[int, str, str, str]] = []
    for block in scan_blocks:
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
    route_scope = read_smoke_route_scope(inputs_json)
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

    direct_contract_status, direct_contract_obs = evaluate_direct_decoder_contract(output_root)
    add_gate(
        "SMOKE-DIRECT-2015-2024",
        "Recovered GFAS/ERA5 direct closure contract",
        str(output_root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv"),
        "unique_years, unique_dates, smoke_method, effective recovery root",
        direct_contract_obs,
        "Requires route_selected=v0_gfas_era5_real, recovery root trace, unique_years>=10, unique_units>=24 for Portugal continental, all years 2015-2024, all 12 months per year, full expected annual date coverage, and no anchored/interpolated/extrapolated methods.",
        "SRC-GATE-SMOKE-DIRECT-2015-2024",
        "METHODOLOGICAL_GATE",
        direct_contract_status,
        "Direct recovered smoke closure for 2015-2024.",
        "Direct 2015-2024 smoke closure when recovered source or decoder depth is insufficient.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if direct_contract_status.startswith("BLOCKED") else "NONE",
    )

    oc03c_base_status, oc03c_base_obs, oc03c_base_gate = evaluate_oc03c_base_smoke_contract(qa_dir)
    add_gate(
        "BASE_SMOKE_CONTRACT_FOR_OC03C",
        "OC-03C base smoke runtime contract",
        str(qa_dir / "oc03c_base_smoke_contract_gate.tsv"),
        "daily_rows, unique_dates, unique_years, unique_units, homogeneous_years, years_2015_2024_present",
        oc03c_base_obs,
        "Portuguese AQ validation may proceed only when the validated 2015-2024 direct smoke runtime contract remains intact.",
        "SRC-GATE-OC03C-BASE-SMOKE",
        "METHODOLOGICAL_GATE",
        oc03c_base_status,
        "Portuguese AQ may be consumed only after the base smoke contract passes.",
        "Portuguese AQ consumption on a regressed smoke baseline.",
        "NONE",
    )

    portuguese_aq_status, portuguese_aq_obs, portuguese_aq_gate = evaluate_portuguese_aq_validation(qa_dir)
    add_gate(
        "OC03C-AQ-001",
        "Portuguese AQ validation overlay",
        str(qa_dir / "portuguese_aq_validation_gate.tsv"),
        "portuguese_aq_validation_status, aq_protocol_decision, claim_disposition, health_exposure_claim_status",
        portuguese_aq_obs,
        "OC-03C may upgrade only to a locally AQ-anchored proxy when direct station/pollutant concordance exists; health exposure stays blocked unless threshold comparisons are audited.",
        "SRC-GATE-OC03C-AQ",
        "LOCAL_VALIDATION_GATE",
        portuguese_aq_status,
        "A non-health local AQ support statement is allowed when concordance evidence exists.",
        "Health exposure or unsupported AQ-upgrade claims without audited thresholds.",
        "NONE",
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
        "NONE",
    )

    pop_cancel_status, pop_cancel_obs = evaluate_population_cancellation(iech_hist_csv)
    add_gate(
        "IECH-POP-001",
        "Population exposure cancellation check",
        str(iech_hist_csv),
        f"{IECH_PROXY_INDICATOR_NAME} vs expo_person_hours/smoke_hours_equiv",
        pop_cancel_obs,
        f"{IECH_PROXY_INDICATOR_NAME} may equal expo_person_hours but must not collapse to smoke_hours_equiv when used as a population burden proxy.",
        "SRC-GATE-IECH-POP-CANCEL",
        "METHODOLOGICAL_GATE",
        pop_cancel_status,
        "Operational proxy interpretation with explicit limitation.",
        "Population exposure differentiation claim when the proxy collapses to smoke_hours_equiv or is normalized as individual IECH.",
        "NONE",
    )

    iech_semantics_tsv = qa_dir / "iech_reporting_semantics_audit.tsv"
    if not iech_semantics_tsv.exists():
        iech_semantics_tsv = qa_dir / "iech_reporting_reframe_audit.tsv"
    iech_semantic_status, iech_semantic_obs = evaluate_iech_proxy_semantics(iech_semantics_tsv)
    add_gate(
        "IECH-SEM-001",
        "IECH proxy burden semantic scope",
        str(iech_semantics_tsv),
        "indicator_name, claim_status, population_exposed, exposure_fraction, forbidden normalized/health claims",
        iech_semantic_obs,
        "IECH reporting must remain a population_smoke_burden_proxy with population_exposed=population_total and exposure_fraction=1.0, while normalized/individual/health claims remain blocked.",
        "SRC-GATE-IECH-PROXY-BURDEN",
        "METHODOLOGICAL_GATE",
        iech_semantic_status,
        "Population smoke burden proxy semantics with explicit non-health limitation.",
        "Normalized IECH, individual exposure, differential exposed population, or health exposure claims.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if iech_semantic_status.startswith("BLOCKED") else "NONE",
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
        "population_smoke_burden_proxy_mean_2015_2024 / IECH_mean_2015_2024",
        iech_obs,
        "count_unique(population_smoke_burden_proxy_mean_2015_2024 across units) must be > 1 for ranking claims.",
        "SRC-GATE-IECH-RANKING",
        "METHODOLOGICAL_GATE",
        iech_status,
        "Population smoke burden proxy baseline claim when ranking is blocked.",
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
    add_evidence("portuguese_aq_validation_gate", qa_dir / "portuguese_aq_validation_gate.tsv")
    add_evidence("portuguese_aq_concordance", qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv")

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

    closure_rows = [r for r in gate_rows if r["final_decision_effect"] != "NONE"]
    scientific_effects = [r["final_decision_effect"] for r in closure_rows]
    if "NO-GO_SCIENTIFIC_THRESHOLD" in scientific_effects:
        scientific_decision = "NO-GO_SCIENTIFIC_THRESHOLD"
    elif any(r["gate_status"].startswith("BLOCKED") for r in closure_rows):
        scientific_decision = "HOLD"
    else:
        scientific_decision = "GO"

    aq_protocol_decision = portuguese_aq_gate.get("aq_protocol_decision") or "n/a"
    if scientific_decision == "GO" and aq_protocol_decision == IECH_PROXY_AQ_PROTOCOL:
        final_operational_decision = IECH_PROXY_FINAL_DECISION
    elif scientific_decision == "GO":
        final_operational_decision = aq_protocol_decision
    else:
        final_operational_decision = scientific_decision

    decision_lines = [
        "# Runtime Scientific Closure Decision",
        "",
        f"- timestamp: {now_iso()}",
        f"- output_root: \"{output_root}\"",
        f"- scientific_threshold_decision: **{scientific_decision}**",
        f"- final_operational_decision: **{final_operational_decision}**",
        f"- indicator_name: {IECH_PROXY_INDICATOR_NAME}",
        f"- indicator_unit: {IECH_PROXY_INDICATOR_UNIT}",
        f"- claim_status: {IECH_PROXY_CLAIM_STATUS}",
        "- population_smoke_burden_proxy_formula: smoke_hours_equiv * population_total",
        "- population_exposed_assumed: population_total",
        "- exposure_fraction_assumption: 1.0",
        "- normalized_IECH_individual_claim: BLOCKED",
        "- population_exposed_differential_claim: BLOCKED",
        "- proxy_population_burden_claim: ALLOWED",
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
            "## Smoke Route Scope",
            f"- reason: {route_scope.get('reason') or 'n/a'}",
            f"- allowed_use: {route_scope.get('allowed_use') or 'n/a'}",
            f"- forbidden_use: {route_scope.get('forbidden_use') or 'n/a'}",
            "",
            "## Portuguese AQ Validation",
            f"- base_smoke_contract_for_oc03c_status: {oc03c_base_gate.get('base_smoke_contract_for_oc03c_status') or oc03c_base_gate.get('final_state') or 'n/a'}",
            f"- portuguese_aq_validation_status: {portuguese_aq_gate.get('portuguese_aq_validation_status') or 'n/a'}",
            f"- aq_protocol_decision: {aq_protocol_decision}",
            f"- claim_disposition: {portuguese_aq_gate.get('claim_disposition') or 'n/a'}",
            f"- health_exposure_claim_status: {portuguese_aq_gate.get('health_exposure_claim_status') or 'n/a'}",
            "",
            "## IECH Proxy Burden Semantics",
            f"- semantic_gate_status: {iech_semantic_status}",
            f"- semantic_gate_observed: {iech_semantic_obs}",
            "- allowed_scope: population burden proxy only",
            "- blocked_scope: normalized IECH, individual exposure, differential exposed population, health exposure",
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




