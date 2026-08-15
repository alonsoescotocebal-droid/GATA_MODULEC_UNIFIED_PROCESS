#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import hashlib
import json
import math
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
IECH_PROXY_INDICATOR_NAME = "population_smoke_day_burden_proxy"
IECH_PROXY_INDICATOR_UNIT = "classified smoke-proxy person-days"
IECH_PROXY_CLAIM_STATUS = "OPERATIONAL_TERRITORIAL_SMOKE_DAY_BURDEN_PROXY"
R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI = False
FORMAL_WUI_HOLD = "HOLD_FORMAL_WUI"
FORMAL_WUI_DECISION = "FORMAL_WUI_NOT_SUPPORTED_BY_CURRENT_AUTHORIZED_INPUTS"
FORMAL_WUI_FORBIDDEN_CLAIMS = (
    "FORMAL_WUI",
    "INTERFACE_WUI",
    "INTERMIX_WUI",
    "WUI_RISK",
    "WUI_EXPOSURE",
    "WUI_CAUSAL_EFFECT",
)


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


def _read_wui_semantic_status(output_root: Path) -> Dict[str, object]:
    try:
        from .validate_modulec_objectives_canon import read_wui_semantic_status
    except ImportError:  # pragma: no cover - direct script execution
        from validate_modulec_objectives_canon import read_wui_semantic_status  # type: ignore
    return read_wui_semantic_status(output_root)


def evaluate_formal_wui(output_root: Path) -> Tuple[str, str, Dict[str, int]]:
    """Evaluate formal-WUI evidence without treating the territorial proxy as WUI."""
    status = _read_wui_semantic_status(output_root)
    metrics = {
        "built_spatial_layer_available": int(bool(status.get("territorial_proxy_available"))),
        "independent_vegetation_layer_available": int(status.get("independent_landcover_input_used", 0)),
        "building_vegetation_spatial_relation": int(status.get("building_vegetation_spatial_relation", 0)),
        "formal_wui_available": int(bool(status.get("formal_wui_available"))),
        "current_wui_proxy_fire_history_dependent": int(status.get("current_wui_proxy_fire_history_dependent", 0)),
    }
    if bool(status.get("formal_wui_available")):
        return "PASS", "Formal WUI evidence is complete.", metrics
    detail = (
        f"{FORMAL_WUI_HOLD}; {FORMAL_WUI_DECISION}; "
        "built-up/fuel territorial contextual proxy is allowed; final_effect=HOLD_OC07"
    )
    return "BLOCKED_FORMAL_WUI_CLAIM", detail, metrics


def evaluate_official_portuguese_interface(output_root: Path) -> Tuple[str, str, Dict[str, int]]:
    """Evaluate CIAE as an official Portuguese interface construct, not formal WUI."""
    gate = output_root / "qa" / "r10_d3_oc07_gate.tsv"
    nuts = output_root / "tables" / "official_portuguese_built_area_interface_nuts3.csv"
    muni = output_root / "tables" / "official_portuguese_built_area_interface_municipio.csv"
    metrics = {"gate_exists": int(gate.exists()), "nuts3_exists": int(nuts.exists()), "municipio_exists": int(muni.exists())}
    if not all(metrics.values()):
        return "BLOCKED_OFFICIAL_INTERFACE_EVIDENCE", "CIAE official interface output or gate is missing.", metrics
    text = gate.read_text(encoding="utf-8-sig", errors="replace")
    required = (
        "source_identity\t",
        "linear_geometry_epsg3763\t",
        "class_semantics\t",
        "nuts3_overlay\t",
        "municipio_overlay\t",
        "objective_status\tPASS_OFFICIAL_PORTUGUESE_BUILT_AREA_INTERFACE\tPASS",
        "formal_international_wui_claim\tBLOCKED_CLAIM_NOT_OBJECTIVE_FAILURE\tPASS",
    )
    missing = [token for token in required if token not in text]
    if missing:
        return "BLOCKED_OFFICIAL_INTERFACE_EVIDENCE", "CIAE OC-07 gate lacks required evidence: " + ",".join(missing), metrics
    return "PASS", "Official Portuguese built-area interface is fresh, independently QA-validated and kept separate from formal WUI.", metrics


def audit_formal_wui_claims(output_root: Path) -> Tuple[str, List[str]]:
    """Reject generated formal-WUI/risk claims while allowing explicit limitations."""
    targets = [
        output_root / "brief" / "Brief_Politica_IECH_2030.md",
        output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv",
        output_root / "brief" / "causal_matrix" / "territorial_screening_narrative.md",
    ]
    patterns = {
        "FORMAL_WUI": re.compile(r"\bformal\s+wui\s+(?:risk|exposure|causal|prioritization|score|index)\b", re.I),
        "INTERFACE_WUI": re.compile(r"\binterface\s+wui\b", re.I),
        "INTERMIX_WUI": re.compile(r"\bintermix\s+wui\b", re.I),
        "WUI_RISK": re.compile(r"\bwui\s+risk\b", re.I),
        "WUI_EXPOSURE": re.compile(r"\bwui\s+exposure\b", re.I),
        "WUI_CAUSAL_EFFECT": re.compile(r"\bwui\s+causal\s+effect\b", re.I),
    }
    hits: List[str] = []
    for path in targets:
        if not path.exists() or not path.is_file():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            for token, pattern in patterns.items():
                if pattern.search(line):
                    hits.append(f"{token}:{path.name}:line={line_no}")
    return ("BLOCKED_FORMAL_WUI_CLAIM" if hits else "PASS", hits)


def _objective_status(output_root: Path, objective_id: str) -> str:
    path = output_root / "qa" / "objectives_canon_alignment_report.tsv"
    if not path.exists():
        return "MISSING"
    for row in read_csv_rows(path):
        if str(row.get("objective_id") or "").strip() == objective_id:
            return str(row.get("status") or "").strip() or "EMPTY"
    return "MISSING"


def write_r10_d1_wui_artifacts(
    output_root: Path,
    wui_status: str,
    wui_detail: str,
    wui_metrics: Dict[str, int],
    claim_hits: List[str],
) -> None:
    qa = output_root / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    semantic_rows = [
        ["CURRENT_INDICATOR_TYPE", "BUILT_UP_FUEL_TERRITORIAL_PROXY", "PASS", "Current producer is a built-up x fire-history fuel territorial proxy."],
        ["BUILT_SPATIAL_LAYER_AVAILABLE", wui_metrics["built_spatial_layer_available"], "PASS" if wui_metrics["built_spatial_layer_available"] else "HOLD", "GHSL Built is the resolved built-up spatial component."],
        ["INDEPENDENT_VEGETATION_LAYER_AVAILABLE", wui_metrics["independent_vegetation_layer_available"], "PASS" if wui_metrics["independent_vegetation_layer_available"] else "HOLD", "Independent land-cover input required for formal WUI."],
        ["BUILDING_VEGETATION_SPATIAL_RELATION", wui_metrics["building_vegetation_spatial_relation"], "PASS" if wui_metrics["building_vegetation_spatial_relation"] else "HOLD", "Explicit interface/intermix relation required for formal WUI."],
        ["CURRENT_FORMAL_WUI", wui_metrics["formal_wui_available"], "PASS" if wui_metrics["formal_wui_available"] else "HOLD", "Formal WUI claim remains false/held with current inputs."],
        ["CURRENT_WUI_PROXY_FIRE_HISTORY_DEPENDENT", wui_metrics["current_wui_proxy_fire_history_dependent"], "INFO", "Forest/shrub proxy is derived from the ICNF/fire-recurrence route."],
        ["TERRITORIAL_PROXY_STATUS", "AVAILABLE_AS_CONTEXT", "PASS", "Proxy retained as a contextual territorial descriptor."],
        ["FORMAL_WUI_CLAIM_STATUS", FORMAL_WUI_HOLD, "HOLD", wui_detail],
        ["OC07_OBJECTIVE_STATUS", _objective_status(output_root, "OC-07"), "PASS" if _objective_status(output_root, "OC-07") == "PASS" else "HOLD", "OC-07 closes on the separate official Portuguese interface when its CIAE gate passes; formal WUI remains a blocked claim."],
        ["R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI", str(R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI).upper(), "PASS", "WUI is contextual and excluded from the canonical R10-C score."],
        ["DECISION", FORMAL_WUI_DECISION, "HOLD", "BUILT_UP_FUEL_TERRITORIAL_PROXY_RETAINED_AS_CONTEXT"],
    ]
    write_tsv(qa / "r10_d1_wui_semantic_audit.tsv", ["metric", "value", "status", "detail"], semantic_rows)
    gate_rows = [
        ["WUI_FORMAL_001", "formal_wui_available=FALSE", wui_status, wui_detail],
        ["WUI_CLAIM_001", "forbidden_claim_hits=" + str(len(claim_hits)), "BLOCKED_FORMAL_WUI_CLAIM" if claim_hits else "PASS", "Generated brief/matrix formal WUI claim audit."],
        ["OC07_EFFECT", "PASS_OFFICIAL_PORTUGUESE_BUILT_AREA_INTERFACE" if _objective_status(output_root, "OC-07") == "PASS" else "HOLD_OC07", "PASS" if _objective_status(output_root, "OC-07") == "PASS" else "HOLD", "Formal WUI remains a blocked claim and has no objective effect." if _objective_status(output_root, "OC-07") == "PASS" else FORMAL_WUI_DECISION],
        ["R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI", "FALSE", "PASS", "No WUI input to canonical R10-C score."],
    ]
    write_tsv(qa / "r10_d1_wui_gate_audit.tsv", ["metric", "value", "status", "detail"], gate_rows)
    declaration = "\n".join([
        "# R10-D1 WUI Method Declaration",
        "",
        "## Current indicator",
        "The current indicator is `BUILT_UP_FUEL_TERRITORIAL_PROXY`: a zonal GHSL Built-up sum multiplied by fire/recurrence-derived forest and shrub proxies.",
        "",
        "## What it is not",
        "It is not formal WUI, interface WUI, intermix WUI, WUI risk, WUI exposure, a WUI causal effect, or formal-WUI prioritization.",
        "",
        "## Current decision",
        f"`{FORMAL_WUI_DECISION}`. `formal_wui_claim_status=HOLD_FORMAL_WUI`.",
        "The proxy remains available only as `CONTEXTUAL_TERRITORIAL_DESCRIPTOR`.",
        "",
        "## Required future evidence",
        "A formal claim requires an independent vegetation/wildland spatial input, a built spatial component, a predeclared interface/intermix or equivalent spatial relation, a method declaration, and formal-WUI QA evidence.",
        "",
        "## Allowed claims",
        "Built-up/fuel territorial contextual proxy and bounded descriptive context.",
        "",
        "## Forbidden claims",
        "Formal WUI, interface WUI, intermix WUI, WUI risk, WUI exposure, WUI causal effect, and formal-WUI-based prioritization.",
        "",
        "## Next phase",
        "R10-D2 is required for formal-WUI input acquisition and method predeclaration. No new data are acquired in R10-D1.",
        "",
    ])
    (qa / "r10_d1_wui_method_declaration.md").write_text(declaration, encoding="utf-8")
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


def evaluate_r10_a1_smoke_temporal_contract(smoke_daily_csv: Path, smoke_annual_csv: Path) -> Tuple[str, str]:
    if not smoke_daily_csv.exists() or not smoke_annual_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "R10-A1 daily or annual smoke table missing"
    daily = read_csv_rows(smoke_daily_csv)
    annual = read_csv_rows(smoke_annual_csv)
    daily_counts: Dict[Tuple[str, int], float] = {}
    for row in daily:
        uid = str(row.get("unit_id") or "").strip()
        year = safe_float(row.get("year"))
        proxy = safe_float(row.get("smoke_day_proxy"))
        if not uid or year is None or proxy is None:
            continue
        key = (uid, int(year))
        daily_counts[key] = daily_counts.get(key, 0.0) + proxy
    bad_limit = 0
    bad_alias = 0
    checked = 0
    for row in annual:
        uid = str(row.get("unit_id") or "").strip()
        year = safe_float(row.get("year"))
        days = safe_float(row.get("smoke_days"))
        binary = safe_float(row.get("smoke_days_binary"))
        if not uid or year is None or days is None:
            continue
        checked += 1
        max_days = 366 if calendar.isleap(int(year)) else 365
        if days < 0 or days > max_days:
            bad_limit += 1
        if binary is not None and abs(days - binary) > 1e-9:
            bad_alias += 1
        expected = daily_counts.get((uid, int(year)))
        if expected is not None and abs(days - expected) > 1e-9:
            bad_alias += 1
    if bad_limit or bad_alias:
        return "BLOCKED_R10_A1_SMOKE_TEMPORAL", f"checked={checked}; limit_failures={bad_limit}; binary_or_daily_mismatches={bad_alias}"
    return "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION", f"checked={checked}; smoke_days binary calendar contract passed"


def evaluate_r10_a1_burden_contract(iech_hist_csv: Path) -> Tuple[str, str]:
    if not iech_hist_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "R10-A1 IECH table missing"
    rows = read_csv_rows(iech_hist_csv)
    checked = 0
    failures = 0
    physical_claims = 0
    for row in rows:
        burden = safe_float(row.get("population_smoke_day_burden_proxy"))
        days = safe_float(row.get("smoke_days"))
        population = _first_present_float(row, "population_total", "pop")
        if burden is None or days is None or population is None:
            continue
        checked += 1
        if abs(burden - (days * population)) > 1e-9:
            failures += 1
        if "person-hour" in str(row.get("indicator_unit") or "").lower() or row.get("expo_person_hours"):
            physical_claims += 1
    if checked == 0:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No canonical population smoke-day burden rows"
    if failures or physical_claims:
        return "BLOCKED_R10_A1_BURDEN_DIMENSION", f"checked={checked}; formula_failures={failures}; physical_claims={physical_claims}"
    return "OPERATIONAL_POPULATION_SMOKE_DAY_BURDEN_PROXY", f"checked={checked}; burden=smoke_days*population_total; no person-hours"


def evaluate_iech_ranking(iech_mean_csv: Path) -> Tuple[str, str, int]:
    if not iech_mean_csv.exists():
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024_mean.csv missing", 0
    rows = read_csv_rows(iech_mean_csv)
    if not rows:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "IECH_unit_2015_2024_mean.csv empty", 0
    column = ""
    for candidate in (
        "population_smoke_day_burden_proxy_mean_2015_2024",
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

    if route_selected in ("v1_moduleA_validated", "v0_gfas_era5_advection_screening_proxy"):
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

    if route_selected != "v0_gfas_era5_advection_screening_proxy":
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

    comparable = 0
    equal_formula = 0
    legacy_physical_rows = 0
    for r in rows:
        burden = _first_present_float(r, IECH_PROXY_INDICATOR_NAME)
        smoke_days = safe_float(r.get("smoke_days"))
        population = _first_present_float(r, "population_total", "pop")
        if _first_present_float(r, "expo_person_hours", "legacy_expo_person_hours") is not None:
            legacy_physical_rows += 1
        if burden is None or smoke_days is None or population is None:
            continue
        comparable += 1
        if abs(burden - (smoke_days * population)) <= 1e-9:
            equal_formula += 1
    if comparable == 0:
        return "BLOCKED_FOR_REQUIRED_VARIABLE", "No comparable IECH proxy-burden rows"
    if legacy_physical_rows:
        return "BLOCKED_LEGACY_PHYSICAL_BURDEN", f"Legacy person-hour columns present in {legacy_physical_rows} rows"
    if equal_formula == comparable:
        return "OPERATIONAL_POPULATION_SMOKE_DAY_BURDEN_PROXY", f"{IECH_PROXY_INDICATOR_NAME}=smoke_days*population_total in {comparable}/{comparable} rows"
    unequal_rows = comparable - equal_formula
    return (
        "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
        f"{IECH_PROXY_INDICATOR_NAME} differs from smoke_days*population_total in {unequal_rows}/{comparable} rows",
    )


def evaluate_era5_claims(era5_used_in_score: bool, route_name: str) -> Tuple[str, str]:
    """Block meteorological transport claims until R10-A2 wires ERA5 into the score."""
    route = str(route_name or "").strip().lower()
    if not era5_used_in_score and any(token in route for token in ("weighted", "upwind", "transport", "dispersion", "advection_screening_proxy")):
        return "BLOCKED_ERA5_MECHANISTIC_CLAIM", "ERA5 is QA-only and does not modify smoke_day_score."
    if not era5_used_in_score:
        return "ERA5_QA_ONLY", "ERA5 is read and validated but remains outside smoke_day_score."
    return "THRESHOLD_DEFINED_AS_INDEXED_METHOD", "ERA5 score integration is active under the R10-A2C operational proxy contract."


def evaluate_r10_a2_contract(qa_dir: Path) -> Tuple[str, str]:
    path = qa_dir / "r10_a2_transport_contract_audit.tsv"
    if not path.exists():
        return "BLOCKED_R10_A2_TRANSPORT_CONTRACT", f"{path.name} missing"
    rows = read_csv_rows(path)
    required = {
        "ERA5_READ",
        "ERA5_VALIDATED",
        "ERA5_USED_IN_SMOKE_SCORE",
        "UPWIND_WEIGHTING_IMPLEMENTED",
        "DISTANCE_WEIGHTING_IMPLEMENTED",
    }
    observed = {str(row.get("metric") or "").strip(): str(row.get("status") or "").strip().upper() for row in rows}
    missing = sorted(required.difference(observed))
    failed = sorted(metric for metric in required if observed.get(metric) != "PASS")
    if missing or failed:
        return "BLOCKED_R10_A2_TRANSPORT_CONTRACT", f"missing={','.join(missing)} failed={','.join(failed)}"
    return "PASS", "ERA5, upwind and distance implementation contract passed."


def evaluate_r10_a2_era5_effect(qa_dir: Path) -> Tuple[str, str]:
    path = qa_dir / "r10_a2_era5_effect_audit.tsv"
    if not path.exists():
        return "BLOCKED_ERA5_SCORE_INFLUENCE", f"{path.name} missing"
    rows = {str(row.get("metric") or "").strip(): row for row in read_csv_rows(path)}
    changed = safe_float(rows.get("fraction_unit_days_changed", {}).get("value"))
    if changed is None or changed <= 0.0:
        return "BLOCKED_ERA5_SCORE_INFLUENCE", f"fraction_unit_days_changed={changed}"
    return "PASS", f"fraction_unit_days_changed={changed}"


def evaluate_r10_a2c_multi_receptor(qa_dir: Path) -> Tuple[str, str]:
    path = qa_dir / "r10_a2c_multi_receptor_aggregation_audit.tsv"
    if not path.exists():
        return "BLOCKED_R10_A2C_MULTI_RECEPTOR", f"{path.name} missing"
    rows = {str(row.get("metric") or "").strip(): row for row in read_csv_rows(path)}
    implemented = str(rows.get("MULTI_RECEPTOR_AGGREGATION_IMPLEMENTED", {}).get("value") or "").upper()
    multi_days = safe_float(rows.get("unit_days_with_multiple_valid_receptors", {}).get("value")) or 0.0
    differs = safe_float(rows.get("unit_days_mean_differs_from_max", {}).get("value")) or 0.0
    if implemented != "TRUE" or multi_days <= 0.0 or differs <= 0.0:
        return "BLOCKED_R10_A2C_MULTI_RECEPTOR", f"implemented={implemented} multi_days={multi_days} differs={differs}"
    return "PASS", f"multi_receptor_unit_days={multi_days}; mean_differs_from_max={differs}"


def evaluate_r10_a2c_sensitivity(qa_dir: Path) -> Tuple[str, str]:
    path = qa_dir / "r10_a2_weight_sensitivity.tsv"
    if not path.exists():
        return "BLOCKED_R10_A2C_SENSITIVITY", f"{path.name} missing"
    rows = read_csv_rows(path)
    canonical = [
        row
        for row in rows
        if abs((safe_float(row.get("timescale_hours")) or 0.0) - 24.0) <= 1.0e-12
        and abs((safe_float(row.get("mean_weight")) or 0.0) - 0.75) <= 1.0e-12
        and abs((safe_float(row.get("max_weight")) or 0.0) - 0.25) <= 1.0e-12
    ]
    if len(rows) != 12 or len(canonical) != 1:
        return "BLOCKED_R10_A2C_SENSITIVITY", f"rows={len(rows)} canonical_rows={len(canonical)}"
    row = canonical[0]
    metrics = (
        safe_float(row.get("daily_score_spearman_to_canonical")),
        safe_float(row.get("annual_smoke_days_spearman_to_canonical")),
        safe_float(row.get("annual_burden_spearman_to_canonical")),
        safe_float(row.get("top5_units_overlap")),
        safe_float(row.get("top_quintile_units_overlap")),
    )
    if any(value is None or abs(float(value) - 1.0) > 1.0e-9 for value in metrics):
        return "BLOCKED_R10_A2C_SENSITIVITY", f"canonical_metrics={metrics}"
    return "PASS", "canonical 24h/75-25 sensitivity self-reproduction passed"


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
        "population_smoke_day_burden_proxy_column_present",
        "population_total_column_present",
        "claim_status_proxy_not_normalized",
        "legacy_physical_burden_columns_empty",
        "population_smoke_day_burden_proxy_equals_smoke_days_times_population_total",
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
        f"{IECH_PROXY_INDICATOR_NAME} semantics verified; claim_status={claim_status}; unit=classified smoke-proxy person-days; health exposure blocked",
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


def evaluate_r10b_recurrence(output_root: Path) -> Tuple[str, str, Dict[str, int]]:
    """Evaluate OC-06 from the R10-B construct, not row counts alone."""
    qa = output_root / "qa"
    tables = output_root / "tables"
    required = [
        qa / "r10_b_fire_feature_semantics.tsv",
        qa / "r10_b_reburn_geometry_audit.tsv",
        qa / "r10_b_recurrence_construct_audit.tsv",
        qa / "r10_b_recurrence_legacy_crosswalk.tsv",
        qa / "r10_b_recurrence_sensitivity.tsv",
        qa / "r10_b_recurrence_method_declaration.md",
        qa / "recurrence_classification_audit.tsv",
        tables / "recurrence_unit_2015_2024.csv",
        tables / "recurrence_municipio_2015_2024.csv",
        tables / "recurrence_unit_year_2015_2024.csv",
        tables / "recurrence_municipio_year_2015_2024.csv",
    ]
    metrics = {"unit_rows": 0, "municipal_rows": 0, "unit_year_rows": 0, "municipal_year_rows": 0, "score_unique": 0, "geometry_failures": 0}
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return "BLOCKED_R10_B_RECURRENCE_ARTIFACT_MISSING", "; ".join(missing), metrics

    unit = read_csv_rows(tables / "recurrence_unit_2015_2024.csv")
    muni = read_csv_rows(tables / "recurrence_municipio_2015_2024.csv")
    unit_year = read_csv_rows(tables / "recurrence_unit_year_2015_2024.csv")
    muni_year = read_csv_rows(tables / "recurrence_municipio_year_2015_2024.csv")
    metrics.update(unit_rows=len(unit), municipal_rows=len(muni), unit_year_rows=len(unit_year), municipal_year_rows=len(muni_year))
    if not unit or not muni or not unit_year or not muni_year:
        return "BLOCKED_R10_B_RECURRENCE_EMPTY", "one or more recurrence outputs are empty", metrics
    summary_columns = {"unit_area_ha", "affected_year_fraction", "unique_burned_fraction", "cumulative_burned_fraction", "reburned_area_fraction", "reburn_share_of_unique_burned_area", "recurrence_temporal_rank", "recurrence_reburn_rank", "recurrence_score", "recurrence_class", "legacy_years_area_gt_own_p75", "recurrence_method", "recurrence_claim_status"}
    annual_columns = {"unit_id", "year", "unit_area_ha", "annual_burned_area_ha", "annual_burned_fraction", "affected_year_flag", "polygon_count", "event_count_if_validated"}
    if not summary_columns.issubset(unit[0]) or not summary_columns.issubset(muni[0]):
        return "BLOCKED_R10_B_RECURRENCE_SCHEMA", "canonical recurrence summary columns missing", metrics
    if not annual_columns.issubset(unit_year[0]) or not annual_columns.issubset(muni_year[0]):
        return "BLOCKED_R10_B_RECURRENCE_ANNUAL_SCHEMA", "annual recurrence columns missing", metrics
    if len(unit) != 24 or len(unit_year) != 240:
        return "BLOCKED_R10_B_NUTS3_COVERAGE", f"NUTS3 summary/year rows={len(unit)}/{len(unit_year)} expected 24/240", metrics
    if len(muni) != 278 or len(muni_year) != 2780:
        return "BLOCKED_R10_B_MUNICIPAL_COVERAGE", f"municipal summary/year rows={len(muni)}/{len(muni_year)} expected 278/2780", metrics

    for label, source_rows in (("NUTS3", unit), ("MUNICIPIO", muni)):
        for row in source_rows:
            for column in ("affected_year_fraction", "unique_burned_fraction", "reburned_area_fraction", "reburn_share_of_unique_burned_area", "recurrence_score"):
                value = safe_float(row.get(column))
                if value is None or not math.isfinite(value) or value < 0.0 or value > 1.0:
                    return "BLOCKED_R10_B_RANGE", f"{label} {row.get('unit_id')} {column}={row.get(column)}", metrics
            score = float(row["recurrence_score"])
            expected_class = "LOW" if score < 1.0 / 3.0 else "MEDIUM" if score < 2.0 / 3.0 else "HIGH"
            if row.get("recurrence_class") != expected_class:
                return "BLOCKED_R10_B_FIXED_BANDS", f"{label} {row.get('unit_id')} score/class mismatch", metrics
            if "ANNUAL_DISSOLVE" not in row.get("recurrence_method", ""):
                return "BLOCKED_R10_B_METHOD", f"{label} method declaration missing annual dissolve", metrics
    scores = [round(float(row["recurrence_score"]), 12) for row in unit]
    metrics["score_unique"] = len(set(scores))
    if metrics["score_unique"] <= 1:
        return "BLOCKED_R10_B_RECURRENCE_CONSTRUCT_FAILED", "canonical NUTS3 score is non-discriminating", metrics
    geometry_rows = read_csv_rows(qa / "r10_b_reburn_geometry_audit.tsv")
    for row in geometry_rows:
        for field in ("geometry_failures", "negative_area_failures", "area_ordering_failures"):
            metrics["geometry_failures"] += int(safe_float(row.get(field)) or 0)
        if (row.get("status") or "").strip().upper() != "PASS":
            return "BLOCKED_R10_B_GEOMETRY", f"geometry audit status={row.get('status')}", metrics
    if metrics["geometry_failures"]:
        return "BLOCKED_R10_B_GEOMETRY", f"geometry failures={metrics['geometry_failures']}", metrics
    construct = read_csv_rows(qa / "r10_b_recurrence_construct_audit.tsv")
    if any((row.get("status") or "").strip().upper() == "HOLD" for row in construct):
        return "BLOCKED_R10_B_DISCRIMINATION", "construct audit contains HOLD", metrics
    method = (qa / "r10_b_recurrence_method_declaration.md").read_text(encoding="utf-8-sig", errors="replace").lower()
    required_terms = ("affected_year_fraction", "reburn_share_of_unique_burned_area", "tie-aware", "0.50", "epsg:3035", "legacy")
    missing_terms = [term for term in required_terms if term not in method]
    if missing_terms:
        return "BLOCKED_R10_B_METHOD", "method declaration missing: " + ",".join(missing_terms), metrics
    return "PASS", f"R10-B recurrence passed: NUTS3={len(unit)}, municipalities={len(muni)}, score_unique={metrics['score_unique']}, geometry_failures=0", metrics


def evaluate_r10c_screening(output_root: Path) -> Tuple[str, str, Dict[str, int]]:
    """Evaluate the independent R10-C burden/recurrence screening contract."""
    qa = output_root / "qa"
    matrix_dir = output_root / "brief" / "causal_matrix"
    required = [
        qa / name for name in (
            "r10_c_git_root_audit.tsv",
            "r10_c_legacy_screening_dominance_audit.tsv",
            "r10_c_dimension_independence_audit.tsv",
            "r10_c_single_axis_dominance_audit.tsv",
            "r10_c_screening_weight_sensitivity.tsv",
            "r10_c_recurrence_sensitivity_propagation.tsv",
            "r10_c_smoke_transport_sensitivity_propagation.tsv",
            "r10_c_screening_legacy_crosswalk.tsv",
            "r10_c_screening_construct_audit.tsv",
            "r10_c_screening_independence_audit.tsv",
            "r10_c_screening_method_declaration.md",
        )
    ] + [matrix_dir / name for name in ("territorial_screening_matrix_nuts3.csv", "territorial_screening_matrix_municipio.csv")]
    metrics = {"nuts3_rows": 0, "municipal_rows": 0, "core_failures": 0, "schema_failures": 0}
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return "BLOCKED_R10_C_SCREENING_ARTIFACT_MISSING", "; ".join(missing), metrics
    matrices = {
        "NUTS3": read_csv_rows(matrix_dir / "territorial_screening_matrix_nuts3.csv"),
        "MUNICIPIO": read_csv_rows(matrix_dir / "territorial_screening_matrix_municipio.csv"),
    }
    metrics["nuts3_rows"] = len(matrices["NUTS3"])
    metrics["municipal_rows"] = len(matrices["MUNICIPIO"])
    if len(matrices["NUTS3"]) != 24 or len(matrices["MUNICIPIO"]) != 278:
        return "BLOCKED_R10_C_SCREENING_COVERAGE", f"rows NUTS3/municipality={len(matrices['NUTS3'])}/{len(matrices['MUNICIPIO'])}; expected 24/278", metrics
    required_columns = {
        "unit_id", "unit_level", "population_smoke_day_burden_proxy_mean_2015_2024", "recurrence_score",
        "burden_priority_rank", "recurrence_priority_rank", "screening_priority_score", "burden_band", "recurrence_band",
        "screening_profile", "screening_method", "screening_claim_status", "screening_core_status", "contextual_completeness_status",
        "legacy_policy_priority", "legacy_burden_p80_flag", "smoke_signal_resolution", "recurrence_signal_resolution", "policy_priority", "downstream_status",
    }
    for level, rows in matrices.items():
        if not rows or not required_columns.issubset(rows[0]):
            metrics["schema_failures"] += 1
            return "BLOCKED_R10_C_SCREENING_SCHEMA", f"{level} matrix missing canonical R10-C columns", metrics
        claim = "REGIONAL_SMOKE_INFORMED_MUNICIPAL_SCREENING" if level == "MUNICIPIO" else "RELATIVE_TERRITORIAL_SCREENING_BURDEN_AND_WILDFIRE_RECURRENCE"
        for row in rows:
            burden = safe_float(row.get("population_smoke_day_burden_proxy_mean_2015_2024"))
            recurrence = safe_float(row.get("recurrence_score"))
            burden_rank = safe_float(row.get("burden_priority_rank"))
            recurrence_rank = safe_float(row.get("recurrence_priority_rank"))
            score = safe_float(row.get("screening_priority_score"))
            if burden is None or burden < 0 or recurrence is None or not 0 <= recurrence <= 1 or burden_rank is None or not 0 <= burden_rank <= 1 or recurrence_rank is None or not 0 <= recurrence_rank <= 1 or score is None or not 0 <= score <= 1:
                metrics["core_failures"] += 1
                return "BLOCKED_R10_C_SCREENING_RANGE", f"{level} {row.get('unit_id')} core range invalid", metrics
            expected_score = 0.50 * burden_rank + 0.50 * recurrence_rank
            if abs(score - expected_score) > 1e-12:
                metrics["core_failures"] += 1
                return "BLOCKED_R10_C_SCREENING_FORMULA", f"{level} {row.get('unit_id')} score is not 50/50 rank average", metrics
            expected_class = "MONITOR" if score < 1 / 3 else "MEDIUM_PRIORITY" if score < 2 / 3 else "HIGH_PRIORITY"
            if row.get("policy_priority") != expected_class or row.get("screening_claim_status") != claim or row.get("screening_core_status") != "PASS":
                metrics["core_failures"] += 1
                return "BLOCKED_R10_C_SCREENING_CLASS_OR_CLAIM", f"{level} {row.get('unit_id')} class/claim/core mismatch", metrics
            if level == "MUNICIPIO" and (row.get("smoke_signal_resolution") != "REGIONAL_NUTS3_SIGNAL_ALLOCATED_TO_MUNICIPALITY" or row.get("recurrence_signal_resolution") != "DIRECT_MUNICIPAL_FIRE_FOOTPRINT"):
                return "BLOCKED_R10_C_MUNICIPAL_RESOLUTION", f"municipal signal resolution mismatch for {row.get('unit_id')}", metrics
            if level == "NUTS3" and row.get("smoke_signal_resolution") != "DIRECT_NUTS3_SCREENING":
                return "BLOCKED_R10_C_NUTS3_RESOLUTION", f"NUTS3 signal resolution mismatch for {row.get('unit_id')}", metrics
            if "ATMOSPHERIC_RISK" in str(row.get("screening_claim_status") or ""):
                return "BLOCKED_R10_C_MUNICIPAL_CLAIM", f"forbidden atmospheric claim for {row.get('unit_id')}", metrics
    git_rows = read_csv_rows(qa / "r10_c_git_root_audit.tsv")
    git_decisions = [str(row.get("value") or "") for row in git_rows if row.get("metric") == "decision"]
    if git_decisions != ["PASS"]:
        return "BLOCKED_R10_C_GIT_ROOT_AUDIT", "r10_c_git_root_audit decision is not PASS", metrics
    construct_rows = read_csv_rows(qa / "r10_c_screening_construct_audit.tsv")
    if any(str(row.get("status") or "").upper() != "PASS" for row in construct_rows):
        return "BLOCKED_R10_C_SCREENING_CONSTRUCT", "construct audit contains non-PASS status", metrics
    construct_metrics = {str(row.get("metric") or ""): row for row in construct_rows}
    for metric in ("NUTS3_TEMPORAL_PERSISTENCE", "NUTS3_REBURN"):
        if metric not in construct_metrics:
            return "BLOCKED_R10_C_R10B_SATURATION_AUDIT", f"construct audit missing {metric}", metrics
    method = (qa / "r10_c_screening_method_declaration.md").read_text(encoding="utf-8-sig", errors="replace").lower()
    method_terms = ("population smoke-day burden", "r10-b recurrence score", "tie-aware", "0.50", "[0,1/3)", "no quotas", "wui", "wrb", "municipal")
    missing_terms = [term for term in method_terms if term not in method]
    if missing_terms:
        return "BLOCKED_R10_C_METHOD_DECLARATION", "method declaration missing: " + ",".join(missing_terms), metrics
    transport = read_csv_rows(qa / "r10_c_smoke_transport_sensitivity_propagation.tsv")
    transport_columns = {"variant_smoke_days_total", "variant_population_smoke_day_burden_proxy_mean", "variant_burden_rank_min", "variant_burden_rank_max", "variant_policy_priority_counts"}
    if not transport or not transport_columns.issubset(transport[0]):
        return "BLOCKED_R10_C_TRANSPORT_SCHEMA", "transport sensitivity missing variant propagation columns", metrics
    canonical_transport = [row for row in transport if row.get("variant") == "24h_75_25_CANONICAL"]
    if len(canonical_transport) != 2 or any(str(row.get("status") or "").upper() != "PASS" or int(float(row.get("units_changing_class") or 1)) != 0 for row in canonical_transport):
        return "BLOCKED_R10_C_TRANSPORT_SENSITIVITY", "canonical 24h/75-25 transport propagation did not reproduce screening", metrics
    recurrence = read_csv_rows(qa / "r10_c_recurrence_sensitivity_propagation.tsv")
    if not recurrence or any(str(row.get("status") or "PASS").upper() not in ("PASS", "") for row in recurrence):
        return "BLOCKED_R10_C_RECURRENCE_SENSITIVITY", "recurrence sensitivity propagation failed", metrics
    weights = read_csv_rows(qa / "r10_c_screening_weight_sensitivity.tsv")
    if not any(row.get("variant") == "50/50 canonical" and abs(float(row.get("burden_weight") or -1) - 0.5) < 1e-12 and abs(float(row.get("recurrence_weight") or -1) - 0.5) < 1e-12 for row in weights):
        return "BLOCKED_R10_C_WEIGHT_DECLARATION", "50/50 canonical row absent from weight sensitivity", metrics
    dimension = read_csv_rows(qa / "r10_c_screening_independence_audit.tsv")
    if not any(row.get("metric") == "burden_vs_recurrence_spearman" for row in dimension):
        return "BLOCKED_R10_C_DIMENSION_INDEPENDENCE", "burden/recurrence independence diagnostic absent", metrics
    baseline_rows = [row for row in dimension if row.get("metric") == "legacy_recurrence_only_class_agreement" and row.get("territorial_level") == "NUTS3"]
    if not baseline_rows or baseline_rows[0].get("value") in (None, "", "not supplied"):
        return "BLOCKED_R10_C_LEGACY_BASELINE", "legacy recurrence-only baseline is not explicit", metrics
    legacy_audit = read_csv_rows(qa / "r10_c_legacy_screening_dominance_audit.tsv")
    if not any(row.get("territorial_level") == "NUTS3" and row.get("metric") == "legacy_policy_rule" and all(row.get(key) not in (None, "") for key in ("high_priority_count", "medium_priority_count", "monitor_count")) for row in legacy_audit):
        return "BLOCKED_R10_C_LEGACY_COUNTS", "NUTS3 legacy priority counts are not explicitly reproduced", metrics
    return "PASS", f"R10-C screening passed: NUTS3=24, municipalities=278, core_failures=0", metrics


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

    r10b_status, r10b_observation, r10b_metrics = evaluate_r10b_recurrence(output_root)
    r10b_effect = "NONE" if r10b_status == "PASS" else "NO-GO_SCIENTIFIC_THRESHOLD"
    r10b_checks = [
        ("RECURRENCE_SOURCE_001", "ICNF footprint present and provenance valid"),
        ("RECURRENCE_AREA_001", "unit area normalization valid"),
        ("RECURRENCE_TEMPORAL_001", "affected-year frequency calculated"),
        ("RECURRENCE_SPATIAL_001", "reburn across distinct years calculated"),
        ("RECURRENCE_SPATIAL_002", "same-year polygon overlap cannot create reburn"),
        ("RECURRENCE_CLASS_001", "absolute hectares are not sole classifier"),
        ("RECURRENCE_CLASS_002", "fixed score bands applied"),
        ("RECURRENCE_DISCRIMINATION_001", "canonical score discriminates units"),
        ("RECURRENCE_LEGACY_001", "legacy own-p75 is not canonical input"),
        ("RECURRENCE_EVENT_001", "event semantics declared before event frequency use"),
        ("RECURRENCE_CLAIM_001", "HIGH recurrence is relative screening class"),
    ]
    for gate_id, rule in r10b_checks:
        add_gate(
            gate_id,
            "OC-06 R10-B wildfire recurrence",
            str(output_root / "qa" / "recurrence_classification_audit.tsv"),
            rule,
            r10b_observation,
            rule,
            "R10-B-SCIENTIFIC-CONTRACT",
            "SCIENTIFIC_CONSTRUCT_GATE",
            r10b_status,
            "Relative recurrence screening within the ICNF 2015-2024 dataset.",
            "Universal recurrence threshold, future probability, causal hazard, or unvalidated ignition frequency.",
            r10b_effect,
        )
    add_evidence("r10_b_recurrence_construct_audit", output_root / "qa" / "r10_b_recurrence_construct_audit.tsv")
    add_evidence("r10_b_recurrence_unit_summary", output_root / "tables" / "recurrence_unit_2015_2024.csv")
    add_evidence("r10_b_recurrence_municipal_summary", output_root / "tables" / "recurrence_municipio_2015_2024.csv")

    r10c_status, r10c_observation, r10c_metrics = evaluate_r10c_screening(output_root)
    r10c_effect = "NONE" if r10c_status == "PASS" else "NO-GO_SCIENTIFIC_THRESHOLD"
    r10c_checks = (
        ("SCREENING_GIT_001", "R10-C Git root and clean-tree audit"),
        ("SCREENING_INPUT_001", "population smoke-day burden is primary dimension A"),
        ("SCREENING_INPUT_002", "R10-B recurrence score is primary dimension B"),
        ("SCREENING_RANK_001", "burden ranks are tie-aware fractional ranks within level"),
        ("SCREENING_RANK_002", "recurrence ranks are tie-aware fractional ranks within level"),
        ("SCREENING_SCALE_001", "canonical score is normalized to [0,1]"),
        ("SCREENING_WEIGHT_001", "canonical weights are 0.50 burden and 0.50 recurrence"),
        ("SCREENING_CLASS_001", "fixed bands are [0,1/3), [1/3,2/3), [2/3,1]"),
        ("SCREENING_INDEPENDENCE_001", "dimension independence and single-axis diagnostics are present"),
        ("SCREENING_DOUBLECOUNT_001", "smoke-days and population are not double-counted in canonical score"),
        ("SCREENING_DOUBLECOUNT_002", "R10-B subcomponents, WUI, WRB, AQ and S1 are excluded from canonical score"),
        ("SCREENING_CONTEXT_001", "contextual incompleteness does not block core screening"),
        ("SCREENING_DOMINANCE_001", "legacy dominance is retained only as a crosswalk diagnostic"),
        ("SCREENING_SENSITIVITY_001", "recurrence and transport sensitivities propagate through screening"),
        ("SCREENING_MUNICIPAL_001", "municipal smoke claim is regional NUTS3 allocation"),
        ("SCREENING_CLAIM_001", "claim remains relative territorial screening, not risk or causality"),
    )
    for gate_id, rule in r10c_checks:
        add_gate(
            gate_id,
            "OC-09 R10-C independent two-dimensional screening",
            str(output_root / "qa" / "r10_c_screening_construct_audit.tsv"),
            rule,
            r10c_observation,
            rule,
            "R10-C-SCREENING-SCIENTIFIC-CONTRACT",
            "SCIENTIFIC_CONSTRUCT_GATE",
            r10c_status,
            "Relative burden-and-wildfire-recurrence territorial screening within the validated dataset.",
            "Risk, dose, health exposure, causal priority, regulatory priority, quota or intervention claims.",
            r10c_effect,
        )
    for name in (
        "r10_c_git_root_audit.tsv", "r10_c_legacy_screening_dominance_audit.tsv", "r10_c_dimension_independence_audit.tsv",
        "r10_c_single_axis_dominance_audit.tsv", "r10_c_screening_weight_sensitivity.tsv", "r10_c_recurrence_sensitivity_propagation.tsv",
        "r10_c_smoke_transport_sensitivity_propagation.tsv", "r10_c_screening_legacy_crosswalk.tsv", "r10_c_screening_construct_audit.tsv",
        "r10_c_screening_independence_audit.tsv", "r10_c_screening_method_declaration.md",
    ):
        add_evidence(f"r10_c_{name}", output_root / "qa" / name)

    wui_status, wui_observation, wui_metrics = evaluate_formal_wui(output_root)
    claim_audit_status, claim_hits = audit_formal_wui_claims(output_root)
    add_gate(
        "WUI_FORMAL_001",
        "OC-07 formal WUI claim",
        str(output_root / "tables" / "territorial_context_nuts3.csv"),
        "built spatial component + independent vegetation component + explicit spatial relation + method",
        wui_observation,
        "building_vegetation_spatial_relation=TRUE AND formal_wui_method implemented AND independent vegetation/wildland input resolved",
        "R10-D1-FORMAL-WUI-CONTRACT",
        "SCIENTIFIC_CONSTRUCT_GATE",
        wui_status,
        "BUILT_UP_FUEL_TERRITORIAL_PROXY as contextual territorial descriptor only.",
        "formal WUI, interface WUI, intermix WUI, WUI risk, WUI exposure, WUI causal effect, formal-WUI prioritization",
        "NONE",
    )
    add_gate(
        "WUI_CLAIM_001",
        "OC-07 generated claim audit",
        str(output_root / "brief" / "Brief_Politica_IECH_2030.md"),
        "forbidden formal-WUI claim patterns",
        f"hits={len(claim_hits)}",
        "Generated brief and screening matrix must not assert formal WUI/risk/exposure claims.",
        "R10-D1-CLAIM-CONTRACT",
        "SCIENTIFIC_CLAIM_GATE",
        claim_audit_status,
        "Contextual built-up/fuel proxy wording.",
        "Formal WUI/risk/exposure/causal claims.",
        "HOLD_OC07" if claim_hits else "NONE",
    )
    ciae_status, ciae_observation, ciae_metrics = evaluate_official_portuguese_interface(output_root)
    add_gate(
        "CIAE_INTERFACE_001",
        "OC-07 official Portuguese built-area interface construct",
        str(output_root / "tables" / "official_portuguese_built_area_interface_nuts3.csv"),
        "DGT CIAE 2018 exact source identity + linear EPSG:3763 geometry + classes + NUTS3 and municipality overlays",
        ciae_observation,
        "Fresh CIAE outputs and r10_d3_oc07_gate.tsv are all PASS; formal international WUI remains blocked.",
        "R10-D3-CIAE-OFFICIAL-INTERFACE-CONTRACT",
        "SCIENTIFIC_CONSTRUCT_GATE",
        ciae_status,
        "Official Portuguese built-area interface as a contextual territorial construct; no formal international WUI equivalence.",
        "Formal international WUI, WUI risk/exposure/causal effect, health exposure, arbitrary class-weighted score",
        "NONE" if ciae_status == "PASS" else "HOLD_OC07",
    )
    add_evidence("r10_d3_ciae_source_identity", output_root / "qa" / "r10_d3_ciae_source_identity.tsv")
    add_evidence("r10_d3_oc07_gate", output_root / "qa" / "r10_d3_oc07_gate.tsv")
    write_r10_d1_wui_artifacts(output_root, wui_status, wui_observation, wui_metrics, claim_hits)
    add_evidence("r10_d1_wui_semantic_audit", output_root / "qa" / "r10_d1_wui_semantic_audit.tsv")
    add_evidence("r10_d1_wui_gate_audit", output_root / "qa" / "r10_d1_wui_gate_audit.tsv")
    add_evidence("r10_d1_wui_method_declaration", output_root / "qa" / "r10_d1_wui_method_declaration.md")

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
        "priority=v1_moduleA_validated>v0_gfas_era5_advection_screening_proxy>BLOCKED_DECODER_REQUIRED>v0_parquet_proxy_degraded>NO-GO_SMOKE_ROUTE",
        "SRC-GATE-SMOKE-ROUTE",
        "METHODOLOGICAL_GATE",
        route_status,
        "Route-level traceability and explicit degraded/blocked state reporting.",
        "Scientific closure with degraded or blocked smoke route.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if route_status.startswith("BLOCKED") else "NONE",
    )

    route_meta = {}
    try:
        route_meta = json.loads(inputs_json.read_text(encoding="utf-8-sig")).get("meta", {})
    except Exception:
        route_meta = {}
    era5_route_name = str(route_meta.get("smoke_route_name") or route_selected)
    era5_used_in_score = bool(route_meta.get("ERA5_USED_IN_SMOKE_SCORE", False))
    era5_claim_status, era5_claim_obs = evaluate_era5_claims(era5_used_in_score, era5_route_name)
    add_gate(
        "ERA5_CLAIM_001",
        "ERA5 meteorological claim scope",
        str(inputs_json),
        "ERA5_READ/ERA5_USED_IN_SMOKE_SCORE/route_name",
        era5_claim_obs,
        "ERA5-weighted, upwind, transport and dispersion claims remain blocked while ERA5 is QA-only.",
        "SRC-GATE-ERA5-CLAIM-SCOPE",
        "CLAIM_GOVERNANCE",
        era5_claim_status,
        "GFAS + ERA5 advection-informed operational smoke proxy semantics.",
        "ERA5-weighted or upwind smoke claims before R10-A2.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if era5_claim_status.startswith("BLOCKED") else "NONE",
    )
    if era5_used_in_score:
        transport_status, transport_obs = evaluate_r10_a2_contract(qa_dir)
        add_gate(
            "ERA5_SCORE_001",
            "ERA5 numerically affects canonical smoke score",
            str(qa_dir / "r10_a2_transport_contract_audit.tsv"),
            "ERA5_USED_IN_SMOKE_SCORE",
            transport_obs,
            "ERA5 must be read, validated and mechanistically used in smoke_day_score.",
            "SRC-GATE-R10-A2-ERA5-SCORE",
            "SCIENTIFIC_CONSTRUCT",
            transport_status,
            "ERA5-informed operational smoke proxy.",
            "ERA5 nominally present while score remains GFAS-only.",
            "NO-GO_SCIENTIFIC_THRESHOLD" if transport_status.startswith("BLOCKED") else "NONE",
        )
        effect_status, effect_obs = evaluate_r10_a2_era5_effect(qa_dir)
        add_gate(
            "ERA5_SCORE_002",
            "Real-data ERA5 score influence",
            str(qa_dir / "r10_a2_era5_effect_audit.tsv"),
            "fraction_unit_days_changed",
            effect_obs,
            "fraction_unit_days_changed must be greater than zero on real data.",
            "SRC-GATE-R10-A2-ERA5-EFFECT",
            "SCIENTIFIC_CONSTRUCT",
            effect_status,
            "Canonical score changes numerically under ERA5-informed transport.",
            "Canonical score identical to GFAS-only reference for all unit-days.",
            "NO-GO_SCIENTIFIC_THRESHOLD" if effect_status.startswith("BLOCKED") else "NONE",
        )
        multi_status, multi_obs = evaluate_r10_a2c_multi_receptor(qa_dir)
        add_gate(
            "ERA5_SCORE_003",
            "A2C multi-receptor non-degeneration",
            str(qa_dir / "r10_a2c_multi_receptor_aggregation_audit.tsv"),
            "MULTI_RECEPTOR_AGGREGATION_IMPLEMENTED/unit_days_mean_differs_from_max",
            multi_obs,
            "Multiple valid receptors must be aggregated after source-to-receptor transport.",
            "SRC-GATE-R10-A2C-MULTI-RECEPTOR",
            "SCIENTIFIC_CONSTRUCT",
            multi_status,
            "Non-degenerate multireceptor ERA5 operational smoke proxy.",
            "Single-receptor collapse when multiple valid unit samples exist.",
            "NO-GO_SCIENTIFIC_THRESHOLD" if multi_status.startswith("BLOCKED") else "NONE",
        )
        sensitivity_status, sensitivity_obs = evaluate_r10_a2c_sensitivity(qa_dir)
        add_gate(
            "ERA5_SCORE_004",
            "A2C sensitivity canonical self-reproduction",
            str(qa_dir / "r10_a2_weight_sensitivity.tsv"),
            "24h/75-25 canonical self-reproduction",
            sensitivity_obs,
            "The sensitivity machinery must reproduce canonical daily, annual and burden rankings.",
            "SRC-GATE-R10-A2C-SENSITIVITY",
            "SCIENTIFIC_CONSTRUCT",
            sensitivity_status,
            "Mathematically exact source-level sensitivity with canonical self-reproduction.",
            "Approximate aggregate sensitivity or canonical self-mismatch.",
            "NO-GO_SCIENTIFIC_THRESHOLD" if sensitivity_status.startswith("BLOCKED") else "NONE",
        )
        for threshold_id, component, variable, detail, status in (
            ("UPWIND_GEOMETRY_001", "source-receptor upwind geometry", "UPWIND_WEIGHTING_IMPLEMENTED", "Upwind alignment affects source contribution.", transport_status),
            ("DISTANCE_TRANSPORT_001", "distance/travel-time attenuation", "DISTANCE_WEIGHTING_IMPLEMENTED", "Distance and transport time attenuate source contribution.", transport_status),
            ("ERA5_CLAIM_002", "GFAS+ERA5 route claim governance", "route_name/ERA5_USED_IN_SMOKE_SCORE", "Mechanistic advection claim is allowed only when ERA5 is used in the score.", "PASS" if era5_used_in_score else "BLOCKED_ERA5_MECHANISTIC_CLAIM"),
            ("TRANSPORT_SEMANTICS_001", "transport proxy semantic scope", "smoke_route_name", "Score remains an operational screening proxy, not concentration or dispersion output.", "PASS" if era5_used_in_score else "BLOCKED_TRANSPORT_SEMANTICS"),
        ):
            add_gate(
                threshold_id,
                component,
                str(qa_dir / "r10_a2_transport_contract_audit.tsv"),
                variable,
                detail,
                "R10-A2 transport construct must be implemented and explicitly scoped.",
                f"SRC-GATE-R10-A2-{threshold_id}",
                "SCIENTIFIC_CONSTRUCT",
                status,
                "Advection-informed operational smoke proxy with explicit limitations.",
                "Nominal ERA5, unattenuated distance, concentration, dose, health exposure, or dispersion claims.",
                "NO-GO_SCIENTIFIC_THRESHOLD" if str(status).startswith("BLOCKED") else "NONE",
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

    temporal_status, temporal_obs = evaluate_r10_a1_smoke_temporal_contract(
        output_root / "tables" / "smoke_day_score_nuts3_daily.csv",
        smoke_csv,
    )
    add_gate(
        "SMOKE_TEMPORAL_001",
        "Canonical smoke-day calendar bound",
        str(smoke_csv),
        "smoke_days <= calendar days and equals binary daily sum",
        temporal_obs,
        "Canonical smoke_days cannot exceed calendar days and must equal sum(smoke_day_proxy).",
        "SRC-GATE-R10-A1-SMOKE-TEMPORAL",
        "SCIENTIFIC_CONSTRUCT",
        temporal_status,
        "Smoke frequency is a binary classified-day count; continuous intensity is separate.",
        "Using cumulative normalized intensity as duration.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if temporal_status.startswith("BLOCKED") else "NONE",
    )
    add_gate(
        "SMOKE_TEMPORAL_002",
        "Annual smoke frequency versus continuous intensity",
        str(output_root / "tables" / "smoke_day_score_nuts3_daily.csv"),
        "smoke_days=SUM(smoke_day_proxy); cumulative_normalized_smoke_intensity_proxy separate",
        temporal_obs,
        "Sub-threshold positive score may increase cumulative intensity but cannot increment smoke_days.",
        "SRC-GATE-R10-A1-SMOKE-SEPARATION",
        "SCIENTIFIC_CONSTRUCT",
        temporal_status,
        "Binary classified smoke-day frequency plus separate continuous intensity proxy.",
        "Continuous intensity labelled as days, hours or person-hours.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if temporal_status.startswith("BLOCKED") else "NONE",
    )
    if era5_used_in_score:
        add_gate(
            "SMOKE_TEMPORAL_R10A2_001",
            "R10-A2 binary smoke-day semantics",
            str(smoke_csv),
            "smoke_days=SUM(smoke_day_proxy)",
            temporal_obs,
            "The new transport score may change classification but not the binary-day contract.",
            "SRC-GATE-R10-A2-SMOKE-TEMPORAL",
            "SCIENTIFIC_CONSTRUCT",
            temporal_status,
            "Binary classified smoke-day frequency remains canonical.",
            "Continuous intensity used as days, hours or person-hours.",
            "NO-GO_SCIENTIFIC_THRESHOLD" if temporal_status.startswith("BLOCKED") else "NONE",
        )

    direct_contract_status, direct_contract_obs = evaluate_direct_decoder_contract(output_root)
    add_gate(
        "SMOKE-DIRECT-2015-2024",
        "Recovered GFAS/ERA5 direct closure contract",
        str(output_root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv"),
        "unique_years, unique_dates, smoke_method, effective recovery root",
        direct_contract_obs,
        "Requires route_selected=v0_gfas_era5_advection_screening_proxy, recovery root trace, unique_years>=10, unique_units>=24 for Portugal continental, all years 2015-2024, all 12 months per year, full expected annual date coverage, and no anchored/interpolated/extrapolated methods.",
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
        f"{IECH_PROXY_INDICATOR_NAME} vs smoke_days/population_total",
        pop_cancel_obs,
        f"{IECH_PROXY_INDICATOR_NAME} must equal smoke_days*population_total and must not be interpreted as physical person-hours.",
        "SRC-GATE-IECH-POP-CANCEL",
        "METHODOLOGICAL_GATE",
        pop_cancel_status,
        "Operational proxy interpretation with explicit limitation.",
        "Physical person-hours, individual exposure, health exposure or epidemiological claims.",
        "NONE",
    )

    burden_status, burden_obs = evaluate_r10_a1_burden_contract(iech_hist_csv)
    add_gate(
        "BURDEN_DIMENSION_001",
        "Canonical population smoke-day burden",
        str(iech_hist_csv),
        "population_smoke_day_burden_proxy=smoke_days*population_total",
        burden_obs,
        "Canonical population burden cannot derive person-hours from cumulative intensity or multiply by 24.",
        "SRC-GATE-R10-A1-BURDEN",
        "SCIENTIFIC_CONSTRUCT",
        burden_status,
        "Classified smoke-proxy person-days; health and individual exposure remain blocked.",
        "Physical person-hours, dose, health exposure or individual exposure claims.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if burden_status.startswith("BLOCKED") else "NONE",
    )
    add_gate(
        "BURDEN_DIMENSION_002",
        "Population burden unit semantics",
        str(iech_hist_csv),
        "classified smoke-proxy person-days; no *24 conversion",
        burden_obs,
        "Canonical burden is smoke_days*population_total and cannot be physical person-hours or health exposure.",
        "SRC-GATE-R10-A1-BURDEN-UNIT",
        "SCIENTIFIC_CONSTRUCT",
        burden_status,
        "Classified smoke-proxy person-days only.",
        "Automatic *24 conversion, physical person-hours, dose or health exposure.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if burden_status.startswith("BLOCKED") else "NONE",
    )
    if era5_used_in_score:
        add_gate(
            "BURDEN_R10A2_001",
            "R10-A2 population smoke-day burden contract",
            str(iech_hist_csv),
            "population_smoke_day_burden_proxy=smoke_days*population_total",
            burden_obs,
            "Transport score changes smoke classification only; burden remains smoke-days times population.",
            "SRC-GATE-R10-A2-BURDEN",
            "SCIENTIFIC_CONSTRUCT",
            burden_status,
            "Classified smoke-proxy person-days only.",
            "Automatic *24 conversion, physical person-hours, dose or health exposure.",
            "NO-GO_SCIENTIFIC_THRESHOLD" if burden_status.startswith("BLOCKED") else "NONE",
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
        "IECH reporting must remain population_smoke_day_burden_proxy=smoke_days*population_total with classified smoke-proxy person-days semantics; normalized/individual/health claims remain blocked.",
        "SRC-GATE-IECH-PROXY-BURDEN",
        "METHODOLOGICAL_GATE",
        iech_semantic_status,
        "Population smoke burden proxy semantics with explicit non-health limitation.",
        "Normalized IECH, individual exposure, differential exposed population, or health exposure claims.",
        "NO-GO_SCIENTIFIC_THRESHOLD" if iech_semantic_status.startswith("BLOCKED") else "NONE",
    )
    add_gate(
        "SMOKE_SEMANTIC_001",
        "Smoke intensity semantic separation",
        str(iech_semantics_tsv),
        "normalized_smoke_intensity_proxy_daily/cumulative_normalized_smoke_intensity_proxy",
        iech_semantic_obs,
        "Continuous intensity remains separate from binary smoke-day frequency and population burden.",
        "SRC-GATE-R10-A1-SMOKE-SEMANTICS",
        "SCIENTIFIC_CONSTRUCT",
        iech_semantic_status,
        "Continuous intensity is a dimensionless proxy and not temporal exposure.",
        "Intensity labelled as days, hours or person-hours.",
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
        "population_smoke_day_burden_proxy_mean_2015_2024",
        iech_obs,
        "count_unique(population_smoke_day_burden_proxy_mean_2015_2024 across units) must be > 1 for ranking claims.",
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

    r10b_rows = [r for r in gate_rows if str(r.get("threshold_id", "")).startswith("RECURRENCE_")]
    r10b_pass = bool(r10b_rows) and all(
        str(row.get("gate_status", "")).upper() == "PASS"
        and str(row.get("final_decision_effect", "")) == "NONE"
        for row in r10b_rows
    )
    r10c_pass = r10c_status == "PASS"

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
        f"- R10_B_RECURRENCE_DECISION: **{'R10_B_RECURRENCE_PASS' if r10b_pass else 'R10_B_RECURRENCE_NOT_CLOSED'}**",
        f"- R10_C_SCREENING_DECISION: **{'R10_C_SCREENING_INDEPENDENCE_PASS' if r10c_pass else r10c_status}**",
        f"- OC_09: **{'PASS' if r10c_pass else 'HOLD'}**",
        f"- WUI_FORMAL_001: **{wui_status}**",
        f"- CIAE_INTERFACE_001: **{ciae_status}**",
        f"- OC_07: **{'PASS_OFFICIAL_PORTUGUESE_BUILT_AREA_INTERFACE' if ciae_status == 'PASS' else 'HOLD'}**",
        f"- FORMAL_WUI_DECISION: **{FORMAL_WUI_DECISION}**",
        "- TERRITORIAL_PROXY_STATUS: **AVAILABLE_AS_CONTEXT**",
        f"- R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI: **{str(R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI).upper()}**",
        "- MODULE_C_FINAL_SCIENTIFIC_GO: PROHIBITED_WHILE_DOWNSTREAM_HOLDS_OPEN",
        f"- indicator_name: {IECH_PROXY_INDICATOR_NAME}",
        f"- indicator_unit: {IECH_PROXY_INDICATOR_UNIT}",
        f"- claim_status: {IECH_PROXY_CLAIM_STATUS}",
        "- population_smoke_day_burden_proxy_formula: smoke_days * population_total",
        "- population_smoke_day_burden_proxy_unit: classified smoke-proxy person-days",
        "- physical person-hours and health exposure claims: BLOCKED",
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
            "## Known downstream scientific holds",
            "- OC-07 FORMAL_WUI",
            *([] if r10c_pass else ["- R10-C SCREENING_INDEPENDENCE"]),
            "- R10-D FORMAL_WUI",
            "- R10-E AQ_TIER_REVIEW",
            "- R10-F S1_TARGET_SELECTION",
            "- MUNICIPAL_DIRECT_SMOKE",
            "- WRB_METADATA",
            "- LEGAL_2026",
            "- FINAL_BRIEF",
            "- R10-FINAL",
        ]
    )
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




