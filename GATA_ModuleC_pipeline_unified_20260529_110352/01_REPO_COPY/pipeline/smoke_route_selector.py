from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


ROUTE_PRIORITY = [
    "v1_moduleA_validated",
    "v0_gfas_era5_real",
    "BLOCKED_DECODER_REQUIRED",
    "v0_parquet_proxy_degraded",
    "NO-GO_SMOKE_ROUTE",
]

MODULEA_HINT_KEYS: Sequence[str] = (
    "smoke_v1_modulea",
    "smoke_modulea_catalog",
    "smoke_catalog_v1",
    "smoke_catalog",
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

    gfas_dir = modulec_datos / "CAM-GFAS (ADS)"
    gfas_gribs = sorted(gfas_dir.glob("*.grib")) if gfas_dir.exists() else []
    gfas_total_bytes = sum(int(p.stat().st_size) for p in gfas_gribs) if gfas_gribs else 0

    era5_candidates = sorted(modulec_datos.glob("*ERA5*.zip"))
    era5_zip = era5_candidates[0] if era5_candidates else None

    parquet_candidates = [
        modulec_datos / "ParquetFiles 2017.zip",
        modulec_datos / "ParquetFiles 2022.zip",
    ]
    parquet_existing = [p for p in parquet_candidates if p.exists()]

    return {
        "smoke_csv_input": str(smoke_csv_path) if smoke_csv_path else "",
        "modulea_validated": modulea_validated_path is not None,
        "modulea_catalog_path": str(modulea_validated_path) if modulea_validated_path else "",
        "gfas_dir": str(gfas_dir) if gfas_dir.exists() else "",
        "gfas_exists": gfas_dir.exists(),
        "gfas_grib_count": len(gfas_gribs),
        "gfas_total_bytes": int(gfas_total_bytes),
        "era5_zip": str(era5_zip) if era5_zip else "",
        "era5_exists": era5_zip is not None and era5_zip.exists(),
        "parquet_zip_count": len(parquet_existing),
        "parquet_zip_paths": [str(p) for p in parquet_existing],
    }


def select_smoke_route(sources: Dict[str, object], decoder_available: bool = False) -> Dict[str, object]:
    modulea_ok = bool(sources.get("modulea_validated"))
    gfas_ok = bool(sources.get("gfas_exists")) and int(sources.get("gfas_grib_count") or 0) > 0
    era5_ok = bool(sources.get("era5_exists"))
    parquet_ok = int(sources.get("parquet_zip_count") or 0) > 0

    result = {
        "route_priority_order": ">".join(ROUTE_PRIORITY),
        "route_selected": "",
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

    if gfas_ok and era5_ok:
        if decoder_available:
            result.update(
                {
                    "route_selected": "v0_gfas_era5_real",
                    "smoke_route_status": "SCIENTIFIC_PRIMARY_REAL",
                    "smoke_route_decision": "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
                    "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                    "iech_decision": "IECH_ROUTE_REAL_SMOKE",
                    "causal_matrix_decision": "PENDING_DOWNSTREAM_VALIDATION",
                    "brief_decision": "PENDING_DOWNSTREAM_VALIDATION",
                    "final_scientific_decision": "PENDING_DOWNSTREAM_GATES",
                    "reason": "GFAS + ERA5 detected and decoder is available.",
                    "allowed_use": "scientific_route",
                    "forbidden_use": "",
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
                "reason": "GFAS and ERA5 exist but no robust decoder is wired in runtime.",
                "operational_fallback_route": "v0_parquet_proxy_degraded" if parquet_ok else "",
                "allowed_use": "diagnostic_only" if parquet_ok else "",
                "forbidden_use": "IECH final cientifico, matriz causal final, brief final, GO",
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
    if sources.get("modulea_catalog_path"):
        paths["smoke_modulea_catalog"] = str(sources.get("modulea_catalog_path"))
    payload["paths"] = paths

    meta["smoke_route_mode"] = str(decision.get("route_selected", ""))
    meta["smoke_route_selected"] = str(decision.get("route_selected", ""))
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
    meta["smoke_route_detected_sources"] = {
        "modulea_validated": bool(sources.get("modulea_validated")),
        "modulea_catalog_path": str(sources.get("modulea_catalog_path", "")),
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
