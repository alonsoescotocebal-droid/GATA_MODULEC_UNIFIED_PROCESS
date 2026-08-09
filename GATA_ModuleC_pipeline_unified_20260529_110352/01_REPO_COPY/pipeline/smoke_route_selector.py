from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


ROUTE_PRIORITY = [
    "v0_gfas_era5_advection_screening_proxy",
    "v1_moduleA_validated",
    "BLOCKED_DECODER_REQUIRED",
    "v0_parquet_proxy_degraded",
    "NO-GO_SMOKE_ROUTE",
]
R10_A1_ROUTE_NAME = "v0_gfas_direct_emission_proxy_era5_qa_only"
R10_A2_ROUTE_NAME = "v0_gfas_era5_advection_screening_proxy"

MODULEA_HINT_KEYS: Sequence[str] = (
    "smoke_v1_modulea",
    "smoke_modulea_catalog",
    "smoke_catalog_v1",
    "smoke_catalog",
)

RECOVERY_ROOT_ENV_KEYS: Sequence[str] = (
    "MODULEC_OC03_GFAS_ERA5_RECOVERY_ROOT",
    "MODULEC_OC03_ALLOWED_DATA_ROOTS",
)

ORIGINAL_ROOT_ENV_KEYS: Sequence[str] = (
    "MODULEC_OC03_ORIGINAL_DATOS_ROOT",
    "GATA_EXTERNAL_DATOS_MODC",
    "MODULEC_DATA_ROOT",
    "GATA_MODULEC_DATA_ROOT",
    "DATA_ROOT",
)

RECOVERY_ROOT_NAMES: Sequence[str] = (
    "Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
    "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024",
    "Datos_RECOVERY_2015_2024",
    "Datos_RECOVERY_ERA5_2015_2024_R10A2",
)

FORBIDDEN_PRIMARY_SOURCE_TOKENS: Sequence[str] = (
    "parquetfiles 2017.zip",
    "parquetfiles 2022.zip",
    "era5_d016a6f04c5e420341cf0e7293fcfb56.zip",
    "\\oc03_v9d",
    "\\oc03_v11",
    "\\oc03_v12",
    "\\03_outputs\\oc03_v",
)


def _safe_csv_header(path: Path) -> List[str]:
    try:
        data = path.read_bytes()[:65536].decode("utf-8-sig", errors="replace")
        delim = ";" if data.count(";") >= data.count(",") else ","
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter=delim)
            header = next(reader, [])
        return [str(h).strip().lower() for h in header]
    except Exception:
        return []


def _is_modulea_smoke_catalog(path: Path) -> bool:
    if not path.exists() or path.suffix.lower() not in (".csv", ".tsv"):
        return False
    header = _safe_csv_header(path)
    if not header:
        return False
    has_year = "year" in header
    has_smoke = "smoke_days" in header or "smoke_hours" in header
    has_unit = any(k in header for k in ("unit_id", "nuts_id", "municipio_id"))
    return has_year and has_smoke and has_unit


def _norm(path_value: Path) -> str:
    return str(path_value).replace("/", "\\").lower()


def _parse_path_list(raw: object) -> List[Path]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        vals = [str(v).strip() for v in raw if str(v).strip()]
    else:
        vals = []
        text = str(raw).strip()
        if not text:
            return []
        for part in text.replace("\n", ";").split(";"):
            p = part.strip().strip('"')
            if p:
                vals.append(p)
    return [Path(v) for v in vals]


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for path in paths:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _env_paths(keys: Sequence[str]) -> List[Path]:
    out: List[Path] = []
    for key in keys:
        out.extend(_parse_path_list(os.environ.get(key)))
    return out


def _looks_like_recovery_root(path_value: Path, original_root: Path) -> bool:
    norm = _norm(path_value)
    if any(name.lower() in norm for name in RECOVERY_ROOT_NAMES):
        return True
    if original_root and original_root.exists():
        return not _norm(path_value).startswith(_norm(original_root))
    return False


def _is_forbidden_primary_source(path_value: Path, original_root: Path) -> bool:
    norm = _norm(path_value)
    if any(tok in norm for tok in FORBIDDEN_PRIMARY_SOURCE_TOKENS):
        return True
    root_norm = _norm(original_root) if original_root else ""
    if root_norm and (norm == root_norm or norm.startswith(root_norm + "\\")):
        if "\\cam-gfas (ads)" in norm or "\\era5_d016a6f04c5e420341cf0e7293fcfb56.zip" in norm:
            return True
    return False


def _candidate_data_roots(modulec_datos: Path, inputs: Dict[str, object]) -> List[Path]:
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if not isinstance(paths, dict):
        paths = {}
    if not isinstance(meta, dict):
        meta = {}

    roots: List[Path] = [modulec_datos]
    roots.extend(_env_paths(RECOVERY_ROOT_ENV_KEYS))
    roots.extend(_env_paths(ORIGINAL_ROOT_ENV_KEYS))
    roots.extend(_parse_path_list(paths.get("smoke_data_roots")))
    roots.extend(_parse_path_list(meta.get("smoke_data_roots")))

    parent = modulec_datos.parent
    for name in RECOVERY_ROOT_NAMES:
        roots.append(parent / name)
        roots.append(modulec_datos / name)
    roots.append(parent / "Datos")
    return [p for p in _dedupe_paths(roots) if str(p).strip()]


def _detect_gfas_dir(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    direct_gribs = [p for p in sorted(root.glob("*.grib")) if "pm2p5fire" in p.name.lower()]
    if direct_gribs:
        return root
    if (root / "_grib_summary.csv").exists() or (root / "_grib_edge_summary.csv").exists():
        return root
    legacy_child = root / "CAM-GFAS (ADS)"
    if legacy_child.exists():
        return legacy_child
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        child_gribs = [p for p in sorted(child.rglob("*.grib")) if "pm2p5fire" in p.name.lower()]
        if child_gribs or (child / "_grib_summary.csv").exists() or (child / "_grib_edge_summary.csv").exists():
            return child
    return None


def _detect_era5_zip(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    matches = sorted(root.glob("*ERA5*.zip"))
    if matches:
        return matches[0]
    nested_matches = sorted(root.rglob("*ERA5*.zip"))
    if nested_matches:
        return nested_matches[0]
    grib_dirs = sorted(
        {path.parent for path in root.rglob("*ERA5*.grib") if path.is_file()},
        key=lambda path: (0 if path.name.lower() == "validated" else 1, str(path).lower()),
    )
    return grib_dirs[0] if grib_dirs else None


def detect_smoke_sources(modulec_datos: Path, inputs: Dict[str, object]) -> Dict[str, object]:
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    if not isinstance(paths, dict):
        paths = {}

    smoke_csv_raw = str(paths.get("smoke_csv", "")).strip()
    smoke_csv_path = Path(smoke_csv_raw) if smoke_csv_raw else None

    modulea_candidates: List[Path] = []
    for k in MODULEA_HINT_KEYS:
        p = str(paths.get(k, "")).strip()
        if p:
            modulea_candidates.append(Path(p))
    smoke_root = modulec_datos / "01_std" / "smoke"
    if smoke_root.exists():
        for p in sorted(smoke_root.rglob("*.csv")):
            modulea_candidates.append(p)

    modulea_seen = set()
    modulea_validated_path: Optional[Path] = None
    for cand in modulea_candidates:
        c = cand.resolve() if cand.exists() else cand
        if str(c) in modulea_seen:
            continue
        modulea_seen.add(str(c))
        if smoke_csv_path is not None and cand.exists():
            # The parquet proxy path must not be interpreted as v1.
            if "parquetfiles" in _norm(cand):
                continue
        if _is_modulea_smoke_catalog(cand):
            modulea_validated_path = cand
            break

    original_root = _parse_path_list(os.environ.get("MODULEC_OC03_ORIGINAL_DATOS_ROOT"))
    original_datos_root = original_root[0] if original_root else modulec_datos

    candidate_roots = _candidate_data_roots(modulec_datos, inputs)
    root_rows: List[Dict[str, object]] = []
    effective_root: Optional[Path] = None
    effective_gfas_dir: Optional[Path] = None
    effective_era5_zip: Optional[Path] = None

    for root in candidate_roots:
        gfas_dir = _detect_gfas_dir(root)
        era5_zip = _detect_era5_zip(root)
        gfas_gribs = sorted(gfas_dir.rglob("*.grib")) if gfas_dir is not None and gfas_dir.exists() else []
        row = {
            "root": str(root),
            "recovery_root": _looks_like_recovery_root(root, original_datos_root),
            "gfas_dir": str(gfas_dir) if gfas_dir else "",
            "gfas_grib_count": len(gfas_gribs),
            "era5_zip": str(era5_zip) if era5_zip else "",
            "has_complete_pair": bool(gfas_gribs) and era5_zip is not None and era5_zip.exists(),
        }
        root_rows.append(row)
        if effective_root is None and bool(row["has_complete_pair"]) and bool(row["recovery_root"]):
            effective_root = root
            effective_gfas_dir = gfas_dir
            effective_era5_zip = era5_zip

    if effective_root is None:
        for row in root_rows:
            if bool(row["has_complete_pair"]):
                effective_root = Path(str(row["root"]))
                effective_gfas_dir = Path(str(row["gfas_dir"])) if str(row["gfas_dir"]).strip() else None
                effective_era5_zip = Path(str(row["era5_zip"])) if str(row["era5_zip"]).strip() else None
                break

    # R10-A2B stores recovered ERA5 separately from the existing recovered GFAS root.
    # Pair only those two recovered roots; never mix a non-recovery source into this route.
    if effective_root is None:
        recovery_gfas_row = next(
            (row for row in root_rows if row["recovery_root"] and str(row["gfas_dir"]).strip()),
            None,
        )
        recovery_era5_row = next(
            (row for row in root_rows if row["recovery_root"] and str(row["era5_zip"]).strip()),
            None,
        )
        if recovery_gfas_row is not None and recovery_era5_row is not None:
            effective_root = Path(str(recovery_gfas_row["root"]))
            effective_gfas_dir = Path(str(recovery_gfas_row["gfas_dir"]))
            effective_era5_zip = Path(str(recovery_era5_row["era5_zip"]))

    preferred_r10_a2_era5 = next(
        (
            row
            for row in root_rows
            if row["recovery_root"]
            and Path(str(row["root"])).name.lower() == "datos_recovery_era5_2015_2024_r10a2"
            and str(row["era5_zip"]).strip()
        ),
        None,
    )
    if preferred_r10_a2_era5 is not None:
        recovery_gfas_row = next(
            (row for row in root_rows if row["recovery_root"] and str(row["gfas_dir"]).strip()),
            None,
        )
        if recovery_gfas_row is not None:
            effective_root = Path(str(recovery_gfas_row["root"]))
            effective_gfas_dir = Path(str(recovery_gfas_row["gfas_dir"]))
            effective_era5_zip = Path(str(preferred_r10_a2_era5["era5_zip"]))

    gfas_gribs = sorted(effective_gfas_dir.rglob("*.grib")) if effective_gfas_dir is not None and effective_gfas_dir.exists() else []
    gfas_total_bytes = sum(int(p.stat().st_size) for p in gfas_gribs) if gfas_gribs else 0

    parquet_roots = _dedupe_paths([modulec_datos, original_datos_root] + candidate_roots)
    parquet_candidates: List[Path] = []
    for root in parquet_roots:
        parquet_candidates.extend(
            [
                root / "ParquetFiles 2017.zip",
                root / "ParquetFiles 2022.zip",
            ]
        )
    parquet_existing = [p for p in parquet_candidates if p.exists()]

    effective_smoke_source_path = effective_gfas_dir or effective_era5_zip or modulea_validated_path or smoke_csv_path
    effective_source_is_recovery = bool(effective_root) and _looks_like_recovery_root(effective_root, original_datos_root)
    forbidden_primary_source = (
        _is_forbidden_primary_source(effective_smoke_source_path, original_datos_root)
        if effective_smoke_source_path and not effective_source_is_recovery
        else False
    )

    return {
        "smoke_csv_input": str(smoke_csv_path) if smoke_csv_path else "",
        "modulea_validated": modulea_validated_path is not None,
        "modulea_catalog_path": str(modulea_validated_path) if modulea_validated_path else "",
        "candidate_data_roots": [str(p) for p in candidate_roots],
        "candidate_source_rows": root_rows,
        "original_datos_root": str(original_datos_root),
        "effective_data_root": str(effective_root) if effective_root else "",
        "effective_source_is_recovery": effective_source_is_recovery,
        "effective_smoke_source_path": str(effective_smoke_source_path) if effective_smoke_source_path else "",
        "forbidden_primary_source": forbidden_primary_source,
        "gfas_dir": str(effective_gfas_dir) if effective_gfas_dir is not None and effective_gfas_dir.exists() else "",
        "gfas_exists": effective_gfas_dir is not None and effective_gfas_dir.exists(),
        "gfas_grib_count": len(gfas_gribs),
        "gfas_total_bytes": int(gfas_total_bytes),
        "era5_zip": str(effective_era5_zip) if effective_era5_zip else "",
        "era5_exists": effective_era5_zip is not None and effective_era5_zip.exists(),
        "parquet_zip_count": len(parquet_existing),
        "parquet_zip_paths": [str(p) for p in _dedupe_paths(parquet_existing)],
    }


def select_smoke_route(sources: Dict[str, object], decoder_available: bool = False) -> Dict[str, object]:
    modulea_ok = bool(sources.get("modulea_validated"))
    gfas_ok = bool(sources.get("gfas_exists")) and int(sources.get("gfas_grib_count") or 0) > 0
    era5_ok = bool(sources.get("era5_exists"))
    parquet_ok = int(sources.get("parquet_zip_count") or 0) > 0
    recovery_ok = bool(sources.get("effective_source_is_recovery"))
    forbidden_primary = bool(sources.get("forbidden_primary_source"))
    effective_source = str(sources.get("effective_smoke_source_path") or "").strip()
    source_root = str(sources.get("effective_data_root") or "").strip()

    result = {
        "route_priority_order": ">".join(ROUTE_PRIORITY),
        "route_selected": "",
        "route_name": "",
        "smoke_route_status": "",
        "smoke_route_decision": "",
        "health_exposure_claim": "",
        "iech_decision": "",
        "causal_matrix_decision": "",
        "brief_decision": "",
        "final_scientific_decision": "",
        "required_decoder": "",
        "required_inputs": "",
        "reason": "",
        "operational_fallback_route": "",
        "allowed_use": "",
        "forbidden_use": "",
    }

    if gfas_ok and era5_ok:
        if forbidden_primary:
            result.update(
                {
                    "route_selected": "NO-GO_SMOKE_ROUTE",
                    "smoke_route_status": "BLOCKED",
                    "smoke_route_decision": "BLOCKED_FORBIDDEN_PRIMARY_SMOKE_SOURCE",
                    "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                    "iech_decision": "NO-GO_IECH",
                    "causal_matrix_decision": "NO-GO_CAUSAL_MATRIX",
                    "brief_decision": "NO-GO_BRIEF",
                    "final_scientific_decision": "NO-GO_SCIENTIFIC_THRESHOLD",
                    "reason": f"Forbidden primary smoke source detected: {effective_source}",
                    "allowed_use": "",
                    "forbidden_use": "All closure claims",
                }
            )
            return result
        if not recovery_ok:
            result.update(
                {
                    "route_selected": "BLOCKED_DECODER_REQUIRED",
                    "smoke_route_status": "BLOCKED",
                    "smoke_route_decision": "BLOCKED_NON_RECOVERY_SMOKE_SOURCE",
                    "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                    "iech_decision": "IECH_OPERATIONAL_PROXY_ONLY",
                    "causal_matrix_decision": "HOLD_OR_NO_GO",
                    "brief_decision": "HOLD_OR_NO_GO",
                    "final_scientific_decision": "NO-GO_SCIENTIFIC_THRESHOLD",
                    "required_decoder": "GFAS_GRIB_TO_DAILY_PT_GRID",
                    "required_inputs": "Recovered GFAS/ERA5 2015-2024 roots",
                    "reason": f"GFAS/ERA5 pair detected outside recovery roots: {source_root or effective_source}",
                    "operational_fallback_route": "v1_moduleA_validated" if modulea_ok else ("v0_parquet_proxy_degraded" if parquet_ok else ""),
                    "allowed_use": "diagnostic_only",
                    "forbidden_use": "Direct 2015-2024 closure, IECH final cientifico, GO",
                }
            )
            return result
        if decoder_available:
            result.update(
                {
                    "route_selected": R10_A2_ROUTE_NAME,
                    "route_name": R10_A2_ROUTE_NAME,
                    "smoke_route_status": "SCIENTIFIC_PRIMARY_REAL",
                    "smoke_route_decision": "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
                    "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                    "iech_decision": "IECH_ROUTE_REAL_SMOKE",
                    "causal_matrix_decision": "PENDING_DOWNSTREAM_VALIDATION",
                    "brief_decision": "PENDING_DOWNSTREAM_VALIDATION",
                    "final_scientific_decision": "PENDING_DOWNSTREAM_GATES",
                    "reason": f"Recovered GFAS + ERA5 detected under {source_root} and decoder is available.",
                    "allowed_use": "GFAS + ERA5 advection-informed operational smoke proxy",
                    "forbidden_use": "ambient PM2.5 concentration, health exposure, dose, epidemiological IECH, GO",
                }
            )
            return result

        result.update(
            {
                "route_selected": "BLOCKED_DECODER_REQUIRED",
                "smoke_route_status": "PROXY_DEGRADED" if parquet_ok else "BLOCKED",
                "smoke_route_decision": "BLOCKED_DECODER_REQUIRED",
                "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                "iech_decision": "IECH_OPERATIONAL_PROXY_ONLY",
                "causal_matrix_decision": "HOLD_OR_NO_GO",
                "brief_decision": "HOLD_OR_NO_GO",
                "final_scientific_decision": "NO-GO_SCIENTIFIC_THRESHOLD",
                "required_decoder": "GFAS_GRIB_TO_DAILY_PT_GRID",
                "required_inputs": "GFAS + ERA5 u10/v10",
                "reason": f"Recovered GFAS and ERA5 exist under {source_root} but no robust decoder is wired in runtime.",
                "operational_fallback_route": "v1_moduleA_validated" if modulea_ok else ("v0_parquet_proxy_degraded" if parquet_ok else ""),
                "allowed_use": "diagnostic_only" if parquet_ok else "",
                "forbidden_use": "IECH final cientifico, matriz causal final, brief final, GO",
            }
        )
        return result

    if modulea_ok:
        result.update(
            {
                "route_selected": "v1_moduleA_validated",
                "smoke_route_status": "SCIENTIFIC_PRIMARY",
                "smoke_route_decision": "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
                "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                "iech_decision": "IECH_ROUTE_VALIDATED_UPSTREAM",
                "causal_matrix_decision": "PENDING_DOWNSTREAM_VALIDATION",
                "brief_decision": "PENDING_DOWNSTREAM_VALIDATION",
                "final_scientific_decision": "PENDING_DOWNSTREAM_GATES",
                "reason": "Validated module A smoke catalog available.",
                "allowed_use": "scientific_route",
                "forbidden_use": "",
            }
        )
        return result

    if parquet_ok:
        result.update(
            {
                "route_selected": "v0_parquet_proxy_degraded",
                "smoke_route_status": "PROXY_DEGRADED",
                "smoke_route_decision": "BLOCKED_SPATIAL_SMOKE_CLAIM",
                "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                "iech_decision": "IECH_OPERATIONAL_PROXY_ONLY",
                "causal_matrix_decision": "HOLD_OR_NO_GO",
                "brief_decision": "HOLD_OR_NO_GO",
                "final_scientific_decision": "NO-GO_SCIENTIFIC_THRESHOLD",
                "reason": "Only parquet proxy route is available.",
                "allowed_use": "diagnostic_only",
                "forbidden_use": "IECH final cientifico, matriz causal final, brief final, GO",
            }
        )
        return result

    result.update(
        {
            "route_selected": "NO-GO_SMOKE_ROUTE",
            "smoke_route_status": "BLOCKED",
            "smoke_route_decision": "NO-GO_SMOKE_ROUTE",
            "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
            "iech_decision": "NO-GO_IECH",
            "causal_matrix_decision": "NO-GO_CAUSAL_MATRIX",
            "brief_decision": "NO-GO_BRIEF",
            "final_scientific_decision": "NO-GO_SCIENTIFIC_THRESHOLD",
            "reason": "No smoke route available.",
            "allowed_use": "",
            "forbidden_use": "All closure claims",
        }
    )
    return result


def apply_route_meta(inputs: Dict[str, object], sources: Dict[str, object], decision: Dict[str, object]) -> Dict[str, object]:
    payload = dict(inputs) if isinstance(inputs, dict) else {}
    paths = dict(payload.get("paths", {})) if isinstance(payload.get("paths", {}), dict) else {}
    meta = dict(payload.get("meta", {})) if isinstance(payload.get("meta", {}), dict) else {}

    paths["smoke_gfas_dir"] = str(sources.get("gfas_dir", ""))
    paths["smoke_era5_zip"] = str(sources.get("era5_zip", ""))
    paths["smoke_effective_data_root"] = str(sources.get("effective_data_root", ""))
    paths["smoke_effective_source_path"] = str(sources.get("effective_smoke_source_path", ""))
    paths["smoke_original_datos_root"] = str(sources.get("original_datos_root", ""))
    if sources.get("modulea_catalog_path"):
        paths["smoke_modulea_catalog"] = str(sources.get("modulea_catalog_path"))
    payload["paths"] = paths

    meta["smoke_route_mode"] = str(decision.get("route_selected", ""))
    meta["smoke_route_selected"] = str(decision.get("route_selected", ""))
    meta["smoke_route_name"] = str(decision.get("route_name", ""))
    meta["smoke_route_status"] = str(decision.get("smoke_route_status", ""))
    meta["smoke_route_decision"] = str(decision.get("smoke_route_decision", ""))
    meta["health_exposure_claim"] = str(decision.get("health_exposure_claim", ""))
    meta["iech_decision"] = str(decision.get("iech_decision", ""))
    meta["causal_matrix_decision"] = str(decision.get("causal_matrix_decision", ""))
    meta["brief_decision"] = str(decision.get("brief_decision", ""))
    meta["final_scientific_decision"] = str(decision.get("final_scientific_decision", ""))
    meta["required_decoder"] = str(decision.get("required_decoder", ""))
    meta["required_inputs"] = str(decision.get("required_inputs", ""))
    meta["smoke_route_reason"] = str(decision.get("reason", ""))
    meta["smoke_route_operational_fallback"] = str(decision.get("operational_fallback_route", ""))
    meta["smoke_route_allowed_use"] = str(decision.get("allowed_use", ""))
    meta["smoke_route_forbidden_use"] = str(decision.get("forbidden_use", ""))
    meta["ERA5_READ"] = bool(decision.get("ERA5_READ", False))
    meta["ERA5_VALIDATED"] = bool(decision.get("ERA5_VALIDATED", False))
    meta["ERA5_USED_IN_SMOKE_SCORE"] = bool(decision.get("ERA5_USED_IN_SMOKE_SCORE", False))
    meta["UPWIND_WEIGHTING_IMPLEMENTED"] = bool(decision.get("UPWIND_WEIGHTING_IMPLEMENTED", False))
    meta["DISTANCE_WEIGHTING_IMPLEMENTED"] = bool(decision.get("DISTANCE_WEIGHTING_IMPLEMENTED", False))
    meta["smoke_route_detected_sources"] = {
        "modulea_validated": bool(sources.get("modulea_validated")),
        "modulea_catalog_path": str(sources.get("modulea_catalog_path", "")),
        "candidate_data_roots": list(sources.get("candidate_data_roots", [])),
        "candidate_source_rows": list(sources.get("candidate_source_rows", [])),
        "original_datos_root": str(sources.get("original_datos_root", "")),
        "effective_data_root": str(sources.get("effective_data_root", "")),
        "effective_source_is_recovery": bool(sources.get("effective_source_is_recovery")),
        "effective_smoke_source_path": str(sources.get("effective_smoke_source_path", "")),
        "forbidden_primary_source": bool(sources.get("forbidden_primary_source")),
        "gfas_dir": str(sources.get("gfas_dir", "")),
        "gfas_grib_count": int(sources.get("gfas_grib_count") or 0),
        "gfas_total_bytes": int(sources.get("gfas_total_bytes") or 0),
        "era5_zip": str(sources.get("era5_zip", "")),
        "era5_exists": bool(sources.get("era5_exists")),
        "parquet_zip_count": int(sources.get("parquet_zip_count") or 0),
        "parquet_zip_paths": list(sources.get("parquet_zip_paths", [])),
    }
    payload["meta"] = meta
    return payload
