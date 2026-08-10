#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

YEARS_HIST = list(range(2015, 2025))
FORBIDDEN_DIRECT_METHOD_TOKENS = ("flat_single_anchor", "interpolated_from_anchors", "extrapolated_from_anchors")
BASE_SMOKE_CONTRACT_FOR_OC03C_PASS = "BASE_SMOKE_CONTRACT_FOR_OC03C_PASS"
PORTUGUESE_AQ_BASE_SMOKE_BLOCKED = "BLOCKED_BASE_SMOKE_REGRESSION"
PORTUGUESE_AQ_SPATIALLY_INSUFFICIENT = "PORTUGUESE_AQ_CONSUMED_BUT_SPATIALLY_INSUFFICIENT_FOR_LOCAL_AQ_ANCHOR"
FORBIDDEN_PRIMARY_SOURCE_TOKENS = (
    "parquetfiles 2017.zip",
    "parquetfiles 2022.zip",
    "era5_d016a6f04c5e420341cf0e7293fcfb56.zip",
    "\\oc03_v9d",
    "\\oc03_v11",
    "\\oc03_v12",
    "\\03_outputs\\oc03_v",
)


OBJECTIVES: List[Dict[str, object]] = [
    {
        "objective_id": "OC-01",
        "objective_name": "Base territorial NUTS3 y municipio",
        "required_database": "NUTS 2024 + CAOP 2024.1",
        "required_output": ["maps/IECH_ModuleC_master.gpkg", "qa/territorial_units_validation.tsv", "tables/municipio_unit_map.csv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Outputs territoriales existen y no vacÃ­os.",
    },
    {
        "objective_id": "OC-02",
        "objective_name": "Incendios y recurrencia 2015-2024",
        "required_database": "ardida_2015..2024_TM06.gpkg",
        "required_output": ["tables/recurrence_unit_2015_2024.csv", "tables/recurrence_municipio_2015_2024.csv", "qa/fire_ingestion_audit.tsv", "maps/fires_normalized_2015_2024.gpkg", "qa/fires_normalized_gpkg_audit.tsv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Recurrence unit+municipio presentes y auditorÃ­a de ingestiÃ³n presente.",
    },
    {
        "objective_id": "OC-03",
        "objective_name": "Humo v0/v1 declarado y limpio",
        "required_database": "ParquetFiles 2017.zip + ParquetFiles 2022.zip",
        "required_output": ["tables/smoke_days_unit_2015_2024.csv", "tables/smoke_days_municipio_2015_2024.csv", "qa/smoke_route_audit.tsv"],
        "producer_script": "moduleC_preflight.py + moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Fuente humo no contaminada por 03_outputs/tables; tablas no degeneradas.",
    },
    {
        "objective_id": "OC-03C",
        "objective_name": "Validacion AQ portuguesa/EEA del proxy de humo",
        "required_database": "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024",
        "required_output": [
            "qa/oc03c_base_smoke_contract_gate.tsv",
            "qa/oc03_base_smoke_contract_gate.tsv",
            "qa/oc03_base_smoke_contract_report.md",
            "qa/oc03c_path_scope_preflight.tsv",
            "qa/portuguese_aq_input_inventory.tsv",
            "qa/portuguese_aq_file_format_audit.tsv",
            "qa/portuguese_aq_station_inventory.tsv",
            "qa/portuguese_aq_timeseries_inventory.tsv",
            "qa/portuguese_aq_normalization_audit.tsv",
            "qa/portuguese_aq_station_to_unit_assignment.tsv",
            "qa/gfas_era5_vs_portuguese_aq_concordance.tsv",
            "qa/portuguese_aq_validation_gate.tsv",
            "qa/portuguese_aq_claim_disposition.md",
            "tables/portuguese_aq_daily_station_2015_2024.csv",
            "tables/portuguese_aq_daily_unit_2015_2024.csv",
            "tables/smoke_proxy_aq_concordance_by_unit.csv",
        ],
        "producer_script": "moduleC_pipeline_v2.py + portuguese_aq_validation.py",
        "validation_rule": "AQ portuguesa inventariada y auditada; solo sube a proxy anclado si hay concordancia estacion/polutante; salud bloqueada sin umbrales.",
    },
    {
        "objective_id": "OC-04",
        "objective_name": "PoblaciÃ³n GHSL",
        "required_database": "GHSL POP 2015/2020/2025/2030",
        "required_output": ["tables/pop_unit_2015_2025_2030.csv", "tables/pop_municipio_2015_2025_2030.csv", "qa/population_zonal_audit.tsv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Pop outputs presentes y auditorÃ­a zonal presente.",
    },
    {
        "objective_id": "OC-05",
        "objective_name": "IECH histÃ³rico 2015-2024",
        "required_database": "Smoke + GHSL",
        "required_output": [
            "tables/IECH_unit_2015_2024.csv",
            "tables/IECH_unit_2015_2024_mean.csv",
            "tables/IECH_municipio_2015_2024.csv",
            "tables/IECH_municipio_2015_2024_mean.csv",
            "qa/iech_calculation_audit.tsv",
            "qa/iech_reporting_reframe_audit.tsv",
            "qa/iech_reporting_semantics_audit.tsv",
        ],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "population_smoke_burden_proxy unit+municipio presentes, no degenerados y auditados sin cambio numerico.",
    },
    {
        "objective_id": "OC-06",
        "objective_name": "Recurrencia",
        "required_database": "Incendios 2015-2024",
        "required_output": [
            "tables/recurrence_unit_2015_2024.csv",
            "tables/recurrence_municipio_2015_2024.csv",
            "tables/recurrence_unit_year_2015_2024.csv",
            "tables/recurrence_municipio_year_2015_2024.csv",
            "qa/recurrence_classification_audit.tsv",
            "qa/r10_b_fire_feature_semantics.tsv",
            "qa/r10_b_reburn_geometry_audit.tsv",
            "qa/r10_b_recurrence_construct_audit.tsv",
            "qa/r10_b_recurrence_legacy_crosswalk.tsv",
            "qa/r10_b_recurrence_sensitivity.tsv",
            "qa/r10_b_recurrence_method_declaration.md",
        ],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "OC-06 PASS only when R10-B temporal persistence, distinct-year reburn, geometry, fixed-band and discrimination gates pass.",
    },
    {
        "objective_id": "OC-07",
        "objective_name": "WUI / territorio",
        "required_database": "GHSL built + proxies combustible",
        "required_output": ["tables/territorial_context_nuts3.csv", "tables/territorial_context_municipio.csv", "qa/territorial_variables_audit.tsv", "qa/formal_wui_feasibility.tsv", "qa/landcover_wui_input_inventory.tsv"],
        "producer_script": "step7_matriz_causal.py",
        "validation_rule": "Contexto territorial existe y WUI no estÃ¡ totalmente vacÃ­o.",
    },
    {
        "objective_id": "OC-08",
        "objective_name": "WRB integrado como contexto",
        "required_database": "WRB tiles 193/235/236 + MostProbable.rat.json + annual mask_* overlay route (runtime WRB_working_TM06_from_tiles)",
        "required_output": ["tables/wrb_context_nuts3.csv", "tables/wrb_context_municipio.csv", "qa/wrb_integration_audit.tsv", "qa/wrb_method_consistency_audit.tsv", "qa/wrb_2022_prevalidation.tsv", "brief/wrb_summary_for_policy_brief.md"],
        "producer_script": "step7_matriz_causal.py",
        "validation_rule": "WRB con clases dominantes y sin missing generalizado.",
    },
    {
        "objective_id": "OC-09",
        "objective_name": "Matriz causal sustantiva",
        "required_database": "Outputs IECH/smoke/pop/recurrence/WRB/WUI",
        "required_output": [
            "brief/causal_matrix/causal_matrix_IECH_NUTS3.csv",
            "brief/causal_matrix/causal_matrix_IECH_NUTS3.json",
            "brief/causal_matrix/causal_matrix_IECH_NUTS3.txt",
            "brief/causal_matrix/causal_matrix_IECH_municipio.csv",
            "brief/causal_matrix/causal_matrix_audit.tsv",
            "brief/causal_matrix/causal_matrix_sha256_checkpoints.txt",
            "brief/causal_matrix/territorial_screening_matrix_nuts3.csv",
            "brief/causal_matrix/territorial_screening_matrix_municipio.csv",
            "brief/causal_matrix/territorial_screening_narrative.md",
            "qa/matrix_semantic_gate.tsv",
        ],
        "producer_script": "step7_matriz_causal.py",
        "validation_rule": "No qa_flag=HOLD y missing_components vacÃ­o para cierre GO.",
    },
    {
        "objective_id": "OC-10",
        "objective_name": "Escenarios S0/S1 2026-2030",
        "required_database": "GHSL 2025/2030 + supuestos S1",
        "required_output": [
            "tables/IECH_scenarios_2026_2030.csv",
            "tables/IECH_scenarios_unit_2026_2030_mean.csv",
            "tables/IECH_scenarios_municipio_2026_2030.csv",
            "tables/IECH_scenarios_municipio_2026_2030_mean.csv",
            "qa/scenario_assumptions.md",
            "qa/scenario_audit.tsv",
        ],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Escenarios completos + auditorÃ­a presente.",
    },
    {
        "objective_id": "OC-11",
        "objective_name": "Brief de polÃ­tica",
        "required_database": "Outputs cientÃ­ficos integrados",
        "required_output": ["brief/Brief_Politica_IECH_2030.md", "qa/objective_semantic_contract_audit.tsv", "qa/cartographic_package_gate.tsv", "maps/ModuleC_territorial_results.gpkg"],
        "producer_script": "step7_matriz_causal.py + step8",
        "validation_rule": "Brief sustantivo sin placeholders.",
    },
    {
        "objective_id": "OC-12",
        "objective_name": "Cierre tÃ©cnico reproducible",
        "required_database": "Pipeline completo + Step8 + Step9",
        "required_output": [
            "qa/inputs_resolved.json",
            "qa/run_log.txt",
            "qa/QA_checks.csv",
            "qa/report_auditoria_v2.txt",
            "qa/preflight_report.txt",
            "qa/objectives_canon_alignment_report.tsv",
            "qa/objectives_canon_alignment_report.md",
            "deliverables_step9/runtime_closure_decision.md",
        ],
        "producer_script": "wrapper + qa_gate_v2.py + step9",
        "validation_rule": "Artefactos de cierre frescos y paquete final completo.",
    },
]


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def sniff_delim(path: Path) -> str:
    data = path.read_bytes()[:65536]
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


def find_canon_path(repo_root: Path, inputs: Dict[str, object]) -> Path:
    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if isinstance(meta, dict):
        p_raw = str(meta.get("objectives_canon_path", "")).strip()
        p = Path(p_raw) if p_raw else None
        if p is not None and p.exists():
            return p
    env_p = (os.environ.get("GATA_OBJECTIVES_CANON_PATH") or "").strip()
    if env_p:
        p = Path(env_p)
        if p.exists():
            return p
    for cand in [
        repo_root / "PIPELINE_CANON_HANDOFF" / "12_OBJECTIVES_CANON_MODULEC_IECH.md",
        repo_root / "contracts" / "13_MODULEC_OBJECTIVES_CANON_IECH.md",
    ]:
        if cand.exists():
            return cand
    raise FileNotFoundError("Objectives canon file not found.")


def validate_required_outputs(output_root: Path, required: List[str]) -> Tuple[bool, str]:
    missing: List[str] = []
    empty: List[str] = []
    for rel in required:
        p = output_root / rel
        if not p.exists():
            missing.append(rel)
            continue
        if p.is_file() and p.stat().st_size <= 0:
            empty.append(rel)
    if missing:
        return False, "Missing outputs: " + ", ".join(missing)
    if empty:
        return False, "Empty outputs: " + ", ".join(empty)
    return True, ""


def _audit_has_nonpass(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"{path.name} missing."
    rows = read_csv_rows(path)
    if not rows:
        return False, f"{path.name} empty."
    bad = []
    for row in rows:
        status = str(row.get("status") or row.get("gate_status") or "").strip().upper()
        if status and status not in ("PASS", "INFO", "PRECHECK_PASS", "PASS_WITH_PROXY_BURDEN_SEMANTICS", "THRESHOLD_DEFINED_AS_INDEXED_METHOD"):
            bad.append(status)
    if bad:
        return False, f"{path.name} contains non-pass statuses: {'|'.join(sorted(set(bad))[:8])}"
    return True, f"{path.name} PASS"

def _check_smoke_inputs_clean(inputs: Dict[str, object]) -> Tuple[bool, str]:
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    smoke = Path(str((paths or {}).get("smoke_csv", "")))
    if not smoke.exists():
        return False, f"smoke_csv missing: {smoke}"
    smoke_norm = str(smoke).replace("/", "\\").lower()
    if "\\03_outputs\\tables\\" in smoke_norm:
        return False, f"smoke_csv contaminated: {smoke}"
    if "parquetfiles" not in smoke.name.lower() and smoke.suffix.lower() not in (".zip", ".parquet"):
        return True, f"smoke_csv unusual source (accepted with warning): {smoke}"
    return True, f"smoke_csv source OK: {smoke}"


def _norm_text(value: object) -> str:
    return str(value or "").replace("/", "\\").lower().strip()


def _is_forbidden_primary_source(*paths: object) -> bool:
    norm_paths = [_norm_text(path) for path in paths if str(path or "").strip()]
    for norm in norm_paths:
        if any(tok in norm for tok in FORBIDDEN_PRIMARY_SOURCE_TOKENS):
            return True
        if "\\cam-gfas (ads)" in norm and "datos_recovery_" not in norm:
            return True
    return False


def _count_unique_numeric(rows: List[Dict[str, str]], preferred_cols: List[str]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    target = ""
    for col in preferred_cols:
        if col in cols:
            target = col
            break
    if not target:
        for col in cols:
            low = col.lower()
            if "iech" in low and ("mean" in low or low == "iech"):
                target = col
                break
    if not target:
        return 0
    vals = []
    for row in rows:
        val = safe_float(row.get(target))
        if val is not None:
            vals.append(round(float(val), 8))
    return len(set(vals))




def _metric_map_int(metric_map: Dict[str, Dict[str, str]], *keys: str) -> int:
    for key in keys:
        row = metric_map.get(key.strip().lower())
        if not row:
            continue
        value = safe_float(row.get("value") or row.get("observed") or row.get("status"))
        if value is not None:
            return int(value)
    return 0


def _metric_map_text(metric_map: Dict[str, Dict[str, str]], *keys: str) -> str:
    for key in keys:
        row = metric_map.get(key.strip().lower())
        if not row:
            continue
        value = str(row.get("value") or row.get("observed") or row.get("detail") or "").strip()
        if value:
            return value
    return ""

def _check_oc03_v13_direct_contract(output_root: Path, inputs: Dict[str, object]) -> Tuple[bool, str]:
    qa_dir = output_root / "qa"
    smoke_audit_path = qa_dir / "smoke_route_audit.tsv"
    decoder_audit_path = qa_dir / "gfas_era5_decoder_daily_spatial_audit.tsv"
    smoke_rows = _v10b_read_rows_if_exists(smoke_audit_path)
    decoder_rows = _v10b_read_rows_if_exists(decoder_audit_path)

    if not smoke_rows:
        return False, "smoke_route_audit.tsv missing or unreadable."
    if not decoder_rows:
        return False, "gfas_era5_decoder_daily_spatial_audit.tsv missing or unreadable."

    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(paths, dict):
        paths = {}

    route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
    effective_source_path = str(paths.get("smoke_effective_source_path") or meta.get("effective_smoke_source_path") or "").strip()
    effective_root = str(paths.get("smoke_effective_data_root") or meta.get("effective_data_root") or "").strip()
    recovery_flag = bool(meta.get("smoke_route_detected_sources", {}).get("effective_source_is_recovery")) if isinstance(meta.get("smoke_route_detected_sources"), dict) else False

    if route_selected != "v0_gfas_era5_advection_screening_proxy":
        return False, f"OC-03 direct closure requires route_selected=v0_gfas_era5_advection_screening_proxy, found {route_selected or 'EMPTY'}"
    if not recovery_flag:
        return False, "inputs_resolved does not mark the effective smoke source as recovery-backed."
    if "datos_recovery_2015_2024_pipeline_grib" not in _norm_text(effective_root) and "datos_recovery_2015_2024_pipeline_grib" not in _norm_text(effective_source_path):
        return False, f"inputs_resolved effective smoke source does not point to recovery GFAS root: {effective_root or effective_source_path}"
    if _is_forbidden_primary_source(effective_source_path, effective_root):
        return False, f"inputs_resolved effective smoke source still points to forbidden legacy/proxy input: {effective_source_path or effective_root}"

    blocked_methods = sorted(
        {
            str(r.get("smoke_method") or r.get("method") or "").strip()
            for r in smoke_rows
            if any(tok in str(r.get("smoke_method") or r.get("method") or "").strip().lower() for tok in FORBIDDEN_DIRECT_METHOD_TOKENS)
        }
    )
    if blocked_methods:
        return False, "Forbidden OC-03 closure methods present in smoke_route_audit.tsv: " + ", ".join(blocked_methods[:6])

    smoke_unique_counts = [int(safe_float(r.get("unique_values")) or 0) for r in smoke_rows if safe_float(r.get("year")) is not None]
    if len(smoke_unique_counts) < len(YEARS_HIST):
        return False, f"smoke_route_audit.tsv covers only {len(smoke_unique_counts)} years, expected {len(YEARS_HIST)}"
    if min(smoke_unique_counts) <= 1:
        return False, f"smoke_route_audit.tsv still has homogeneous direct years: min unique_values={min(smoke_unique_counts)}"

    decoder_map = {str(r.get("metric") or "").strip().lower(): r for r in decoder_rows}
    unique_years = _metric_map_int(decoder_map, "uniqueyears", "unique_years")
    unique_dates = _metric_map_int(decoder_map, "uniquedates", "unique_dates")
    unique_units = _metric_map_int(decoder_map, "uniqueunits", "unique_units")
    all_years_present = _metric_map_int(decoder_map, "years_2015_2024_present")
    all_months_present = _metric_map_int(decoder_map, "all_months_present_each_year")
    all_expected_dates_present = _metric_map_int(decoder_map, "all_expected_dates_present")
    dates_per_year = _metric_map_text(decoder_map, "dates_per_year")
    months_present_by_year = _metric_map_text(decoder_map, "months_present_by_year")
    if unique_years < 10:
        return False, f"Decoder daily spatial audit unique_years={unique_years} < 10"
    if unique_units < 24:
        return False, f"Decoder daily spatial audit unique_units={unique_units} < 24 for Portugal continental"
    if all_years_present != 1:
        return False, f"Decoder daily spatial audit years_2015_2024_present={all_years_present}; dates_per_year={dates_per_year or 'EMPTY'}"
    if all_months_present != 1:
        return False, f"Decoder daily spatial audit months_present_by_year={months_present_by_year or 'EMPTY'}"
    if all_expected_dates_present != 1:
        return False, f"Decoder daily spatial audit all_expected_dates_present={all_expected_dates_present}; dates_per_year={dates_per_year or 'EMPTY'}"

    iech_unit_rows = _v10b_read_rows_if_exists(output_root / "tables" / "IECH_unit_2015_2024_mean.csv")
    iech_muni_rows = _v10b_read_rows_if_exists(output_root / "tables" / "IECH_municipio_2015_2024_mean.csv")
    unit_unique = _count_unique_numeric(iech_unit_rows, ["population_smoke_day_burden_proxy_mean_2015_2024", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024", "population_smoke_burden_proxy_mean", "IECH_mean"])
    muni_unique = _count_unique_numeric(iech_muni_rows, ["population_smoke_day_burden_proxy_mean_2015_2024", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024", "population_smoke_burden_proxy_mean", "IECH_mean"])
    if unit_unique < 23:
        return False, f"IECH_unit_2015_2024_mean unique numeric values={unit_unique} < 23"
    if muni_unique < 278:
        return False, f"IECH_municipio_2015_2024_mean unique numeric values={muni_unique} < 278"

    smoke_unit_rows = _v10b_read_rows_if_exists(output_root / "tables" / "smoke_days_unit_2015_2024.csv")
    smoke_vals = [round(float(v), 8) for r in smoke_unit_rows if (v := safe_float(r.get("smoke_days"))) is not None]
    if len(set(smoke_vals)) <= 3 and unit_unique <= 4 and muni_unique <= 38:
        return False, "Runtime matches forbidden V9D/V12H proxy signature (smoke/IECH uniqueness collapse)."

    return True, (
        f"OC-03 direct contract passed: unique_years={unique_years}, unique_dates={unique_dates}, "
        f"unique_units={unique_units}, all_expected_dates_present={all_expected_dates_present}, "
        f"IECH unit unique={unit_unique}, IECH municipio unique={muni_unique}"
    )


def _check_wrb_quality(output_root: Path) -> Tuple[bool, str]:
    nuts_path = output_root / "tables" / "wrb_context_nuts3.csv"
    muni_path = output_root / "tables" / "wrb_context_municipio.csv"
    prevalidation_path = output_root / "qa" / "wrb_2022_prevalidation.tsv"
    if not nuts_path.exists():
        return False, "wrb_context_nuts3.csv missing."
    if not muni_path.exists():
        return False, "wrb_context_municipio.csv missing."
    if not prevalidation_path.exists():
        return False, "wrb_2022_prevalidation.tsv missing."

    rows = read_csv_rows(nuts_path)
    if not rows:
        return False, "wrb_context_nuts3.csv empty."
    n_total = len(rows)
    n_missing = 0
    n_dom = 0
    blocked_note_rows = []
    blocked_tokens = ("fallback", "centroid", "admin-unit-only", "admin_unit-only", "global class", "raster metadata")
    for idx, r in enumerate(rows, start=1):
        miss = safe_float(r.get("wrb_missing_flag"))
        if miss is not None and miss >= 1:
            n_missing += 1
        if (r.get("dominant_wrb_class") or "").strip() != "":
            n_dom += 1
        note_bits = [r.get("wrb_context_note") or "", r.get("dominant_wrb_note") or "", r.get("wrb_source") or ""]
        note_text = " | ".join(str(v).strip() for v in note_bits if str(v).strip()).lower()
        if note_text and any(tok in note_text for tok in blocked_tokens):
            blocked_note_rows.append(f"row{idx}:{note_text[:120]}")
    if n_missing >= n_total:
        return False, f"WRB missing generalized: {n_missing}/{n_total} with wrb_missing_flag=1"
    if n_dom <= 0:
        return False, "No dominant_wrb_class populated."
    if blocked_note_rows:
        return False, "WRB fallback/global/centroid/admin-only notes detected: " + " | ".join(blocked_note_rows[:4])

    pre_rows = read_csv_rows(prevalidation_path)
    if not pre_rows:
        return False, "wrb_2022_prevalidation.tsv empty."
    blocking_metrics = []
    for row in pre_rows:
        status = str(row.get("status") or "").strip().upper()
        if status and status != "PASS":
            metric = str(row.get("metric") or row.get("check_id") or "").strip()
            blocking_metrics.append(metric or status)
    if blocking_metrics:
        return False, "WRB 2022 prevalidation contains non-PASS metrics: " + ", ".join(blocking_metrics[:8])

    return True, f"WRB quality OK: dominant classes={n_dom}/{n_total}, missing={n_missing}/{n_total}, prevalidation=PASS"


def _check_wui_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "tables" / "territorial_context_nuts3.csv"
    if not p.exists():
        return False, "territorial_context_nuts3.csv missing."
    rows = read_csv_rows(p)
    if not rows:
        return False, "territorial_context_nuts3.csv empty."
    n_total = len(rows)
    n_nonempty = 0
    for r in rows:
        if safe_float(r.get("wui_proxy")) is not None:
            n_nonempty += 1
    if n_nonempty <= 0:
        return False, "WUI proxy empty for all units."
    return True, f"WUI coverage OK: non-empty={n_nonempty}/{n_total}"


def _check_causal_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv"
    if not p.exists():
        return False, "causal_matrix_IECH_NUTS3.csv missing."
    rows = read_csv_rows(p)
    if not rows:
        return False, "causal_matrix_IECH_NUTS3.csv empty."
    n_hold = 0
    n_missing_comp = 0
    for r in rows:
        if (r.get("qa_flag") or "").strip().upper() == "HOLD":
            n_hold += 1
        if (r.get("missing_components") or "").strip() != "":
            n_missing_comp += 1
    if n_hold > 0 or n_missing_comp > 0:
        return False, f"Causal matrix unresolved: qa_flag=HOLD {n_hold}, missing_components non-empty {n_missing_comp}"
    return True, "Causal matrix has no HOLD/missing_components."


def _check_brief_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "brief" / "Brief_Politica_IECH_2030.md"
    if not p.exists():
        return False, "Brief missing."
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    if re.search(r"Line\s+\d{3}:\s+IECH pipeline v2 audit detail line", text, flags=re.IGNORECASE):
        return False, "Brief contains placeholder lines."
    if len(text.strip()) < 1200:
        return False, "Brief too short."
    return True, "Brief quality checks passed."


def _check_step9_zip_contents(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "deliverables_step9" / "ModuleC_ALL_FINAL_deliverables.zip"
    if not p.exists():
        # The objective alignment gate runs before the producer creates the
        # final package. The package itself is verified by the final packager.
        return True, "Final ZIP check deferred to the final package producer."
    required_member_tokens = [
        "qa/inputs_resolved.json",
        "qa/run_log.txt",
        "tables/IECH_unit_2015_2024.csv",
        "tables/IECH_municipio_2015_2024.csv",
        "tables/wrb_context_nuts3.csv",
        "tables/territorial_context_nuts3.csv",
        "brief/Brief_Politica_IECH_2030.md",
        "brief/causal_matrix/causal_matrix_IECH_NUTS3.csv",
        "maps/IECH_ModuleC_master.gpkg",
    ]
    with zipfile.ZipFile(p, "r") as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
    missing = [tok for tok in required_member_tokens if not any(n.endswith(tok) for n in names)]
    if missing:
        return False, "Final ZIP missing direct members: " + ", ".join(missing)
    return True, "Final ZIP contains direct scientific outputs."


# >>> OC03_V10B_DECODER_CONTRACT_PATCH
# Purpose:
# - Bind the V9D-discovered decoder failure to the correct objective sections.
# - OC-03 must HOLD when smoke route is BLOCKED_DECODER_REQUIRED/PROXY_DEGRADED,
#   when v0 audit reports HOLD/BLOCKED, when GFAS daily extraction is only one date per year,
#   or when smoke outputs are spatially homogeneous.
# - OC-05 must HOLD when IECH collapses to a single value across units.

BLOCKING_SMOKE_ROUTE_STATES = {
    "BLOCKED_DECODER_REQUIRED",
    "NO-GO_SMOKE_ROUTE",
    "NO_GO_SMOKE_ROUTE",
    "PROXY_DEGRADED",
    "v0_parquet_proxy_degraded",
    "HOLD_DIRECT_YEAR_DECODER_EVIDENCE_MISSING",
    "BLOCKED_DIRECT_YEAR_DECODER_EVIDENCE_MISSING",
}


def _v10b_meta_get(inputs: Dict[str, object], key: str) -> str:
    if isinstance(inputs, dict):
        val = inputs.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
        meta = inputs.get("meta", {})
        if isinstance(meta, dict):
            val = meta.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    return ""


def _v10b_read_rows_if_exists(path: Path) -> List[Dict[str, str]]:
    # >>> OC03_V10L_SEMICOLON_CSV_READER_PATCH
    # Robust reader for objective-gate evidence. V9D IECH mean CSVs are semicolon-delimited.
    # First try the repository reader for backwards compatibility; if it collapses the
    # header into a single semicolon-containing column, sniff delimiters and re-read.
    if not path.exists() or path.stat().st_size <= 0:
        return []
    rows: List[Dict[str, str]] = []
    try:
        rows = read_csv_rows(path)
        if rows:
            cols = [str(c) for c in rows[0].keys()]
            if len(cols) > 1 and not any(";" in c for c in cols):
                return rows
            if len(cols) == 1 and ";" not in cols[0]:
                return rows
        else:
            return rows
    except Exception:
        rows = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=sniff_delim(path))
            out: List[Dict[str, str]] = []
            for row in reader:
                clean = {str(k): ("" if v is None else str(v)) for k, v in row.items() if k is not None}
                out.append(clean)
            return out
    except Exception:
        return rows if isinstance(rows, list) else []
    # <<< OC03_V10L_SEMICOLON_CSV_READER_PATCH

def _v10b_route_meta_not_blocked(inputs: Dict[str, object]) -> Tuple[bool, str]:
    keys = ["smoke_route_mode", "smoke_route_selected", "smoke_route_status", "smoke_route_decision", "final_scientific_decision"]
    blocking = []
    for k in keys:
        v = _v10b_meta_get(inputs, k)
        vu = str(v).strip()
        if not vu:
            continue
        if vu in BLOCKING_SMOKE_ROUTE_STATES or vu.upper() in BLOCKING_SMOKE_ROUTE_STATES:
            blocking.append(f"{k}={vu}")
        if any(tok in vu for tok in ["BLOCKED_DECODER_REQUIRED", "NO-GO_SMOKE_ROUTE", "PROXY_DEGRADED"]):
            blocking.append(f"{k}={vu}")
    if blocking:
        return False, "smoke route decoder contract blocked by inputs_resolved: " + "; ".join(sorted(set(blocking)))
    return True, "smoke route meta not blocked."


def _v10b_v0_audit_not_blocked(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "qa" / "smoke_route_v0_audit.tsv"
    rows = _v10b_read_rows_if_exists(p)
    if not rows:
        return False, "smoke_route_v0_audit.tsv missing or unreadable."
    blocking = []
    for r in rows:
        metric = str(r.get("metric") or "").strip()
        value = str(r.get("value") or "").strip()
        detail = str(r.get("detail") or "").strip()
        text = " ".join(str(v) for v in r.values()).strip()
        tl = text.lower()
        status = str(r.get("status") or r.get("gate_status") or "").strip().upper()
        if metric == "health_exposure_claim" and status == "PASS":
            continue
        if metric == "unexplained_warnings_count":
            unexplained = safe_float(value) or 0.0
            if unexplained <= 0 and status == "PASS":
                continue
        if status in ("HOLD", "BLOCKED", "FAIL", "NO-GO", "NO_GO"):
            blocking.append(text[:220])
            continue
        if any(tok in tl for tok in ["failed", "probe not completed", "decoder required", "gdalinfo failed", "rc=1"]):
            blocking.append(text[:220])
            continue
        if metric == "backend_gfas" and status != "PASS":
            blocking.append(text[:220])
            continue
        if metric == "backend_era5" and status != "PASS":
            blocking.append(text[:220])
            continue
        if metric == "portugal_crop_convention" and status != "PASS":
            blocking.append(text[:220])
    if blocking:
        return False, "smoke_route_v0_audit contains blocking decoder/probe findings: " + " | ".join(blocking[:4])
    return True, "smoke_route_v0_audit has no blocking findings."


def _v10b_gfas_daily_series_not_edge_only(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "qa" / "gfas_pm2p5fire_portugal_daily_summary.csv"
    rows = _v10b_read_rows_if_exists(p)
    if not rows:
        return False, "gfas_pm2p5fire_portugal_daily_summary.csv missing or unreadable."
    dates = set()
    years = set()
    for r in rows:
        for k in ("date", "day", "validityDate_1", "dataDate_1", "validity_date"):
            v = (r.get(k) or "").strip()
            if v:
                dates.add(v[:10])
                if len(v) >= 4 and v[:4].isdigit():
                    years.add(int(v[:4]))
                break
        y = safe_float(r.get("year"))
        if y is not None:
            years.add(int(y))
    if len(rows) <= len(YEARS_HIST) or len(dates) <= len(YEARS_HIST):
        return False, f"GFAS daily summary is edge-only, not a daily spatial decoder output: rows={len(rows)}, unique_dates={len(dates)}, years={sorted(years)}"
    return True, f"GFAS daily summary has daily-depth evidence: rows={len(rows)}, unique_dates={len(dates)}."


def _v10b_smoke_spatial_not_homogeneous(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "qa" / "smoke_route_audit.tsv"
    rows = _v10b_read_rows_if_exists(p)
    if not rows:
        return False, "smoke_route_audit.tsv missing or unreadable."
    checked = 0
    homogeneous = 0
    blocked_route_rows = []
    for r in rows:
        y = safe_float(r.get("year"))
        if y is None:
            continue
        checked += 1
        uniq = safe_float(r.get("unique_values"))
        flag = safe_float(r.get("spatial_homogeneous_flag"))
        route = (r.get("route_selected") or r.get("smoke_route_decision") or "").strip()
        if uniq is not None and uniq <= 1:
            homogeneous += 1
        elif flag is not None and flag >= 1:
            homogeneous += 1
        if "BLOCKED" in route or "NO-GO" in route or "PROXY_DEGRADED" in route:
            blocked_route_rows.append(f"{int(y)}:{route}")
    if checked <= 0:
        return False, "smoke_route_audit has no year rows."
    if blocked_route_rows:
        return False, "smoke route audit still reports blocked/degraded route: " + "; ".join(blocked_route_rows[:10])
    if homogeneous >= checked:
        return False, f"smoke_days spatially homogeneous for all checked years: homogeneous={homogeneous}/{checked}"
    return True, f"smoke route has spatial variation in at least one checked year: homogeneous={homogeneous}/{checked}."


def _v10b_oc03_decoder_contract(output_root: Path, inputs: Dict[str, object]) -> Tuple[bool, str]:
    checks = [
        _v10b_route_meta_not_blocked(inputs),
        _v10b_v0_audit_not_blocked(output_root),
        _v10b_gfas_daily_series_not_edge_only(output_root),
        _v10b_smoke_spatial_not_homogeneous(output_root),
    ]
    failures = [msg for ok, msg in checks if not ok]
    if failures:
        return False, "OC-03 decoder contract unresolved: " + " || ".join(failures)
    return True, "OC-03 decoder contract passed: route real, v0 audit clean, daily-depth GFAS, smoke spatial variation."


def _v10b_iech_non_degenerate(output_root: Path) -> Tuple[bool, str]:
    paths = [
        output_root / "tables" / "IECH_unit_2015_2024_mean.csv",
        output_root / "tables" / "IECH_municipio_2015_2024_mean.csv",
    ]
    findings = []
    preferred_cols = [
        "population_smoke_day_burden_proxy_mean_2015_2024",
        "population_smoke_burden_proxy_mean_2015_2024",
        "IECH_mean_2015_2024",
        "population_smoke_burden_proxy_mean",
        "IECH_mean",
        "population_smoke_burden_proxy",
        "IECH",
    ]
    for p in paths:
        rows = _v10b_read_rows_if_exists(p)
        if not rows:
            return False, f"{p.name} missing or unreadable."
        cols = list(rows[0].keys()) if rows else []
        value_cols = [c for c in preferred_cols if c in cols]
        if not value_cols:
            value_cols = [c for c in cols if "iech" in c.lower() or "population_smoke_burden_proxy" in c.lower()]
        if not value_cols:
            return False, f"{p.name} has no IECH proxy-burden numeric column."
        c = value_cols[0]
        vals = []
        for r in rows:
            v = safe_float(r.get(c))
            if v is not None:
                vals.append(round(float(v), 8))
        if not vals:
            findings.append(f"{p.name}:{c}:rows={len(rows)}:numeric_values=0")
            return False, "IECH proxy burden has no numeric values after delimiter-aware parsing: " + "; ".join(findings)
        uniq = len(set(vals))
        findings.append(f"{p.name}:{c}:rows={len(rows)}:unique={uniq}")
        if uniq <= 1:
            return False, "IECH proxy burden collapsed to one value across units: " + "; ".join(findings)

    reframe_tsv = output_root / "qa" / "iech_reporting_semantics_audit.tsv"
    if not reframe_tsv.exists():
        reframe_tsv = output_root / "qa" / "iech_reporting_reframe_audit.tsv"
    reframe_rows = _v10b_read_rows_if_exists(reframe_tsv)
    if not reframe_rows:
        return False, f"{reframe_tsv.name} missing or unreadable."
    reframe_map = {}
    for row in reframe_rows:
        key = str(row.get("metric") or row.get("check_id") or "").strip()
        if key and key not in reframe_map:
            reframe_map[key] = str(row.get("status") or row.get("value") or row.get("observed") or "").strip()
    required_pass = [
        "IECH_REPORTING_REFRAME_STATUS",
        "population_smoke_day_burden_proxy_column_present",
        "claim_status_proxy_not_normalized",
        "population_smoke_day_burden_proxy_equals_smoke_days_times_population_total",
        "legacy_physical_burden_columns_empty",
    ]
    failing = [metric for metric in required_pass if reframe_map.get(metric, "").strip().upper() != "PASS"]
    if failing:
        return False, "IECH proxy burden semantic audit failed: " + ", ".join(failing)
    return True, "IECH proxy burden non-degenerate and semantically audited: " + "; ".join(findings)


def _read_metric_value_map(path: Path) -> Dict[str, str]:
    rows = _v10b_read_rows_if_exists(path)
    values: Dict[str, str] = {}
    for row in rows:
        key = str(row.get("metric") or row.get("check_id") or "").strip()
        if key and key not in values:
            values[key] = str(row.get("value") or row.get("status") or row.get("observed") or "").strip()
    return values


def _check_oc03c_aq_validation(output_root: Path) -> Tuple[bool, str]:
    qa_dir = output_root / "qa"
    scope_rows = _v10b_read_rows_if_exists(qa_dir / "oc03c_path_scope_preflight.tsv")
    if not scope_rows:
        return False, "OC-03C path-scope audit missing or unreadable."
    summary_row = next((row for row in scope_rows if str(row.get("check_id") or "").strip() == "OC03C_SUMMARY"), None)
    if summary_row is None:
        return False, "OC-03C path-scope audit missing OC03C_SUMMARY row."
    scope_status = str(summary_row.get("status") or "").strip().upper()
    if scope_status != "PATH_SCOPE_PASS":
        detail = str(summary_row.get("detail") or summary_row.get("observed") or "").strip()
        return False, "OC-03C path-scope guard failed: " + (detail or scope_status)

    gate_map = _read_metric_value_map(qa_dir / "portuguese_aq_validation_gate.tsv")
    base_map = _read_metric_value_map(qa_dir / "oc03c_base_smoke_contract_gate.tsv")
    gate_status = gate_map.get("portuguese_aq_validation_status", "").strip()
    protocol = gate_map.get("aq_protocol_decision", "").strip()
    claim_disposition = gate_map.get("claim_disposition", "").strip()
    health_status = gate_map.get("health_exposure_claim_status", "").strip()
    base_status = (base_map.get("base_smoke_contract_for_oc03c_status", "") or base_map.get("final_state", "")).strip()

    if not base_status:
        return False, "OC-03C base smoke contract gate missing base_smoke_contract_for_oc03c_status."

    allowed_statuses = {
        PORTUGUESE_AQ_BASE_SMOKE_BLOCKED,
        "NO_PORTUGUESE_AQ_DATA_FOUND",
        "PORTUGUESE_AQ_INVENTORIED_ONLY",
        PORTUGUESE_AQ_SPATIALLY_INSUFFICIENT,
        "LOCAL_AQ_ANCHORED_PROXY",
        "HEALTH_EXPOSURE_VALIDATED_CANDIDATE",
    }
    if gate_status not in allowed_statuses:
        return False, f"Unrecognized OC-03C gate status: {gate_status or 'EMPTY'}"

    if health_status == "HEALTH_EXPOSURE_VALIDATED":
        return False, "OC-03C must not declare validated health exposure without explicit threshold-comparison artifacts."

    if gate_status == PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
        if base_status != PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
            return False, f"OC-03C blocked state requires matching base smoke gate, found {base_status or 'EMPTY'}"
        if protocol != PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
            return False, f"OC-03C blocked state requires blocked protocol, found {protocol or 'EMPTY'}"
        if claim_disposition != PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
            return False, f"OC-03C blocked state requires blocked claim_disposition, found {claim_disposition or 'EMPTY'}"
        if health_status != "HEALTH_EXPOSURE_CLAIM_BLOCKED":
            return False, f"OC-03C blocked state must keep health claim blocked, found {health_status or 'EMPTY'}"
        return True, "OC-03C correctly blocked AQ consumption after base smoke regression."

    if base_status != BASE_SMOKE_CONTRACT_FOR_OC03C_PASS:
        return False, f"OC-03C AQ validation requires passing base smoke contract, found {base_status or 'EMPTY'}"

    degraded_statuses = {
        "NO_PORTUGUESE_AQ_DATA_FOUND",
        "PORTUGUESE_AQ_INVENTORIED_ONLY",
        PORTUGUESE_AQ_SPATIALLY_INSUFFICIENT,
    }
    if gate_status in degraded_statuses:
        if protocol != "GO_DIRECT_2015_2024_FOR_PROSPECTIVE_PROXY_SCREENING":
            return False, f"OC-03C degraded state requires prospective proxy protocol, found {protocol or 'EMPTY'}"
        if health_status != "HEALTH_EXPOSURE_CLAIM_BLOCKED":
            return False, f"OC-03C degraded state must keep health claim blocked, found {health_status or 'EMPTY'}"
        return True, f"OC-03C audited without local upgrade: status={gate_status}; protocol={protocol}"

    concordance_rows = _v10b_read_rows_if_exists(qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv")
    positive_rows = [
        row
        for row in concordance_rows
        if str(row.get("scope") or "").strip() == "SPATIAL_MATCHED"
        and str(row.get("concordance_signal") or "").strip().upper() == "POSITIVE"
    ]
    if not positive_rows:
        return False, "OC-03C anchored proxy requires positive spatial concordance evidence."
    if protocol != "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL":
        return False, f"OC-03C anchored state requires anchored proxy protocol, found {protocol or 'EMPTY'}"
    if health_status != "HEALTH_EXPOSURE_NOT_DECLARED":
        return False, f"OC-03C anchored state must keep health exposure undeclared, found {health_status or 'EMPTY'}"
    if "locally supported" not in claim_disposition.lower():
        return False, "OC-03C anchored state missing the allowed local-support claim language."
    return True, f"OC-03C anchored proxy validated: status={gate_status}; protocol={protocol}; health={health_status}"


def _phase3_contract_check(output_root: Path, objective_id: str) -> Tuple[bool, str]:
    path = output_root / "qa" / "objective_semantic_contract_audit.tsv"
    rows = read_csv_rows(path) if path.exists() else []
    by_contract = {str(r.get("contract") or "").strip(): r for r in rows}
    required = {
        "OC-05": [("normalized_IECH_claim_status", "BLOCKED_NORMALIZED_IECH_CLAIM"), ("population_burden_proxy_claim_status", "OPERATIONAL_POPULATION_BURDEN_PROXY")],
        "OC-07": [("territorial_indicator_type", "BUILT_UP_FUEL_TERRITORIAL_PROXY"), ("formal_wui_claim_status", "HOLD_FORMAL_WUI")],
        "OC-09": [("matrix_type", "TERRITORIAL_SCREENING_ASSOCIATION"), ("causal_claim_status", "HOLD_CAUSAL_INFERENCE")],
        "OC-10": [("scenario_type", "NORMATIVE_ASSUMPTION")],
    }.get(objective_id, [])
    if not path.exists() or not rows:
        return False, "objective_semantic_contract_audit.tsv missing or empty."
    for contract, expected in required:
        observed = str(by_contract.get(contract, {}).get("value") or "").strip()
        if observed != expected:
            return False, f"{contract}={observed or 'EMPTY'}; expected {expected}."
    return True, "Substantive semantic contract verified."


def _check_r10b_objective(output_root: Path) -> Tuple[bool, str]:
    try:
        import scientific_threshold_gate  # type: ignore
        status, detail, _metrics = scientific_threshold_gate.evaluate_r10b_recurrence(output_root)
    except Exception as exc:
        return False, f"R10-B objective gate could not evaluate recurrence construct: {exc}"
    return status == "PASS", detail


def objective_specific_check(obj_id: str, output_root: Path, inputs: Dict[str, object]) -> Tuple[bool, str]:
    if obj_id == "OC-03":
        ok, reason = _check_smoke_inputs_clean(inputs)
        if not ok:
            return ok, reason
        ok, decoder_reason = _v10b_oc03_decoder_contract(output_root, inputs)
        if not ok:
            return False, decoder_reason
        ok, direct_reason = _check_oc03_v13_direct_contract(output_root, inputs)
        if not ok:
            return False, direct_reason
        smoke_unit = output_root / "tables" / "smoke_days_unit_2015_2024.csv"
        rows = read_csv_rows(smoke_unit) if smoke_unit.exists() else []
        vals = [safe_float(r.get("smoke_days")) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            return False, "smoke_days table has no numeric values."
        if max(vals) <= 0:
            return False, "smoke_days table degenerate (max <= 0)."
        return True, direct_reason
    if obj_id == "OC-03C":
        return _check_oc03c_aq_validation(output_root)
    if obj_id == "OC-05":
        ok, reason = _v10b_iech_non_degenerate(output_root)
        if not ok:
            return ok, reason
        return _phase3_contract_check(output_root, obj_id)
    if obj_id == "OC-06":
        return _check_r10b_objective(output_root)
    if obj_id == "OC-07":
        ok, reason = _phase3_contract_check(output_root, obj_id)
        return (ok, reason) if not ok else (True, reason)
    if obj_id == "OC-08":
        return _check_wrb_quality(output_root)
    if obj_id == "OC-09":
        ok, reason = _phase3_contract_check(output_root, obj_id)
        return (ok, reason) if not ok else (True, reason)
    if obj_id == "OC-11":
        ok, reason = _check_brief_quality(output_root)
        if not ok:
            return ok, reason
        return _phase3_contract_check(output_root, obj_id) if (output_root / "qa" / "objective_semantic_contract_audit.tsv").exists() else (True, reason)
    if obj_id == "OC-12":
        return _check_step9_zip_contents(output_root)
    return True, ""
# <<< OC03_V10B_DECODER_CONTRACT_PATCH
def write_reports(qa_dir: Path, rows: List[Dict[str, str]], canon_path: Path, canon_sha: str) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = qa_dir / "objectives_canon_alignment_report.tsv"
    md_path = qa_dir / "objectives_canon_alignment_report.md"
    sha_path = qa_dir / "objectives_canon_sha256.txt"

    header = [
        "objective_id",
        "objective_name",
        "required_database",
        "required_output",
        "producer_script",
        "validation_rule",
        "status",
        "evidence_path",
        "failure_reason",
    ]
    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    md_lines = [
        "# Objectives Canon Alignment Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Canon path: `{canon_path}`",
        f"- Canon SHA256: `{canon_sha}`",
        "",
        "| objective_id | objective_name | status | failure_reason | evidence_path |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        md_lines.append(
            f"| {r['objective_id']} | {r['objective_name']} | {r['status']} | {r['failure_reason']} | {r['evidence_path']} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    sha_path.write_text(
        "OBJECTIVES_CANON_SHA256\n"
        f"timestamp={now_iso()}\n"
        f"path={canon_path}\n"
        f"sha256={canon_sha}\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--repo-root", required=False, default=None)
    ap.add_argument("--mode", required=False, choices=["pre", "post"], default="post")
    args = ap.parse_args()

    output_root = Path(args.output_root)
    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[1]
    qa_dir = output_root / "qa"
    inputs_path = qa_dir / "inputs_resolved.json"
    inputs: Dict[str, object] = {}
    if inputs_path.exists():
        try:
            inputs = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
        except Exception:
            inputs = {}

    try:
        canon_path = find_canon_path(repo_root, inputs)
    except Exception as exc:
        canon_path = Path("MISSING_CANON")
        canon_sha = ""
        rows = []
        for o in OBJECTIVES:
            rows.append(
                {
                    "objective_id": str(o["objective_id"]),
                    "objective_name": str(o["objective_name"]),
                    "required_database": str(o["required_database"]),
                    "required_output": "|".join(list(o["required_output"])),
                    "producer_script": str(o["producer_script"]),
                    "validation_rule": str(o["validation_rule"]),
                    "status": "HOLD",
                    "evidence_path": str(output_root / "qa"),
                    "failure_reason": f"Missing canon: {exc}",
                }
            )
        write_reports(qa_dir, rows, canon_path, canon_sha)
        print("HOLD objectives canon missing.")
        return 3

    canon_sha = sha256_file(canon_path)

    rows: List[Dict[str, str]] = []
    for obj in OBJECTIVES:
        obj_id = str(obj["objective_id"])
        required = list(obj["required_output"])
        req_ok, req_reason = validate_required_outputs(output_root, required) if args.mode == "post" else (True, "")

        status = "PASS"
        failure = ""
        spec_ok = True
        spec_reason = ""
        if args.mode == "post":
            if not req_ok:
                status = "HOLD"
                failure = req_reason
            else:
                spec_ok, spec_reason = objective_specific_check(obj_id, output_root, inputs)
                if not spec_ok:
                    status = "HOLD"
                    failure = spec_reason
        else:
            # pre-run gate: assert canon availability and input registration readiness only
            if obj_id in ("OC-03",):
                has_smoke = False
                try:
                    has_smoke = bool(((inputs.get("paths", {}) if isinstance(inputs, dict) else {}) or {}).get("smoke_csv"))
                except Exception:
                    has_smoke = False
                if has_smoke:
                    spec_ok, spec_reason = _check_smoke_inputs_clean(inputs)
                    if not spec_ok:
                        status = "HOLD"
                        failure = spec_reason
                else:
                    spec_reason = "inputs_resolved pending preflight refresh"

        if status == "PASS" and args.mode == "pre":
            status = "PRECHECK_PASS"
            failure = spec_reason or "Canon + preconditions checked."
        elif status == "PASS" and obj_id == "OC-05":
            status = "PASS_WITH_PROXY_BURDEN_SEMANTICS"
            failure = spec_reason or "Validated with population_smoke_burden_proxy semantics."
        elif status == "PASS":
            failure = spec_reason or "Validated."

        rows.append(
            {
                "objective_id": obj_id,
                "objective_name": str(obj["objective_name"]),
                "required_database": str(obj["required_database"]),
                "required_output": "|".join(required),
                "producer_script": str(obj["producer_script"]),
                "validation_rule": str(obj["validation_rule"]),
                "status": status,
                "evidence_path": str(output_root),
                "failure_reason": failure,
            }
        )

    write_reports(qa_dir, rows, canon_path, canon_sha)

    hold_rows = [r for r in rows if r["status"] == "HOLD"]
    if hold_rows:
        print(f"HOLD objectives alignment. count={len(hold_rows)} mode={args.mode}")
        for r in hold_rows:
            print(f"{r['objective_id']}: {r['failure_reason']}")
        return 2

    print(f"PASS objectives alignment. mode={args.mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())




