# -*- coding: utf-8 -*-
"""
MODULE C - SMOKE DATABASE YEAR COVERAGE AUDIT
READ ONLY.
This script does not patch code, does not modify input data, and does not run the Module C pipeline.
"""

import argparse
import csv
import datetime as _dt
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

try:
    import pandas as _pd
except Exception:
    _pd = None

try:
    from osgeo import gdal as _gdal
except Exception:
    _gdal = None

SMOKE_KEYWORDS = [
    "gfas", "cams", "ads", "pm2p5", "pm2.5", "pm25", "frp", "wildfire", "fire radiative",
    "era5", "10u", "10v", "u10", "v10", "parquet", "eea", "qualar", "airquality",
    "air_quality", "poluente", "pollutant", "smoke", "humo", "particulate"
]

ARCHIVE_EXTS = {".zip"}
GRID_EXTS = {".grib", ".grb", ".grb2", ".nc", ".netcdf", ".tif", ".tiff"}
TABLE_EXTS = {".csv", ".tsv", ".txt", ".json", ".parquet"}


def safe_text(x):
    if x is None:
        return ""
    return str(x).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)


def write_tsv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: safe_text(r.get(k, "")) for k in fieldnames})


def read_delimited(path):
    p = Path(path)
    if not p.exists():
        return []
    data = p.read_bytes()
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    delim = ";"
    if "\t" in sample and sample.count("\t") >= sample.count(";"):
        delim = "\t"
    elif "," in sample and sample.count(",") > sample.count(";"):
        delim = ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def extract_year_tokens(s, years):
    s = str(s)
    found = []
    for y in years:
        if re.search(r"(?<!\d)" + re.escape(str(y)) + r"(?!\d)", s):
            found.append(str(y))
    return sorted(set(found))


def is_relevant(path_str):
    s = path_str.lower()
    if any(k in s for k in SMOKE_KEYWORDS):
        return True
    ext = Path(path_str).suffix.lower()
    if ext in {".grib", ".grb", ".grb2", ".nc", ".netcdf", ".parquet"}:
        return True
    return False


def scan_data_root(data_root, years):
    rows = []
    root = Path(data_root)
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip common cache dirs only; do not skip data folders.
        dirnames[:] = [d for d in dirnames if d.lower() not in {".git", "__pycache__"}]
        for name in filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root)) if p.exists() else str(p)
            if not is_relevant(str(p)):
                continue
            try:
                st = p.stat()
                size = st.st_size
                mtime = _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
            except Exception:
                size = ""
                mtime = ""
            years_in_path = extract_year_tokens(str(p), years)
            lower = str(p).lower()
            kind = "OTHER"
            if "gfas" in lower or "cams" in lower or p.suffix.lower() in {".grib", ".grb", ".grb2"}:
                kind = "GFAS_OR_GRIB_CANDIDATE"
            elif "era5" in lower or "10u" in lower or "10v" in lower or "u10" in lower or "v10" in lower:
                kind = "ERA5_WIND_CANDIDATE"
            elif "eea" in lower or "qualar" in lower or "parquet" in lower or "airquality" in lower:
                kind = "AQ_STATION_OR_PARQUET_CANDIDATE"
            rows.append({
                "path": str(p),
                "relative_path": rel,
                "extension": p.suffix.lower(),
                "kind_guess": kind,
                "size_bytes": size,
                "modified_time": mtime,
                "years_in_path": ",".join(years_in_path),
                "name": name,
            })
    return rows


def scan_archives(data_rows, years, max_members_per_archive=5000):
    rows = []
    for r in data_rows:
        p = Path(r["path"])
        if p.suffix.lower() not in ARCHIVE_EXTS:
            continue
        try:
            with zipfile.ZipFile(p, "r") as z:
                infos = z.infolist()
                total = len(infos)
                for idx, info in enumerate(infos[:max_members_per_archive]):
                    years_member = extract_year_tokens(info.filename, years)
                    lower = info.filename.lower()
                    relevant_member = any(k in lower for k in SMOKE_KEYWORDS) or Path(info.filename).suffix.lower() in GRID_EXTS.union(TABLE_EXTS)
                    if not relevant_member and not years_member:
                        continue
                    rows.append({
                        "archive_path": str(p),
                        "archive_size_bytes": r.get("size_bytes", ""),
                        "archive_member_count_total": total,
                        "member_index": idx,
                        "member_name": info.filename,
                        "member_extension": Path(info.filename).suffix.lower(),
                        "member_size_bytes": info.file_size,
                        "years_in_member_name": ",".join(years_member),
                        "member_relevance_guess": "RELEVANT" if relevant_member else "YEAR_TOKEN_ONLY",
                    })
                if total > max_members_per_archive:
                    rows.append({
                        "archive_path": str(p),
                        "archive_size_bytes": r.get("size_bytes", ""),
                        "archive_member_count_total": total,
                        "member_index": "TRUNCATED",
                        "member_name": f"Only first {max_members_per_archive} members inspected",
                        "member_extension": "",
                        "member_size_bytes": "",
                        "years_in_member_name": "",
                        "member_relevance_guess": "TRUNCATED",
                    })
        except Exception as e:
            rows.append({
                "archive_path": str(p),
                "archive_size_bytes": r.get("size_bytes", ""),
                "archive_member_count_total": "ERROR",
                "member_index": "ERROR",
                "member_name": safe_text(e),
                "member_extension": "",
                "member_size_bytes": "",
                "years_in_member_name": "",
                "member_relevance_guess": "ERROR",
            })
    return rows


def inspect_parquet_files(data_rows, years, deep=False, max_files=200):
    rows = []
    count = 0
    if not deep:
        return rows
    if _pd is None:
        rows.append({"path": "PANDAS_NOT_AVAILABLE", "status": "SKIPPED", "detail": "pandas/pyarrow not available"})
        return rows
    for r in data_rows:
        p = Path(r["path"])
        if p.suffix.lower() != ".parquet":
            continue
        count += 1
        if count > max_files:
            rows.append({"path": "PARQUET_SCAN_TRUNCATED", "status": "TRUNCATED", "detail": f"max_files={max_files}"})
            break
        try:
            df = _pd.read_parquet(p)
            cols = list(map(str, df.columns))
            date_cols = [c for c in cols if any(k in c.lower() for k in ["date", "datetime", "time", "sampling"])]
            pollutant_cols = [c for c in cols if any(k in c.lower() for k in ["pollut", "pm2", "pm10", "o3", "no2", "so2", "co"])]
            detected_years = set(extract_year_tokens(str(p), years))
            for c in date_cols[:5]:
                try:
                    dt = _pd.to_datetime(df[c], errors="coerce")
                    vals = sorted(set(str(int(y)) for y in dt.dt.year.dropna().unique() if int(y) in years))
                    detected_years.update(vals)
                except Exception:
                    pass
            rows.append({
                "path": str(p),
                "status": "PASS_READ_PARQUET",
                "rows": len(df),
                "columns": ",".join(cols[:80]),
                "date_columns_guess": ",".join(date_cols),
                "pollutant_columns_guess": ",".join(pollutant_cols),
                "years_detected": ",".join(sorted(detected_years)),
                "detail": "",
            })
        except Exception as e:
            rows.append({
                "path": str(p),
                "status": "FAIL_READ_PARQUET",
                "rows": "",
                "columns": "",
                "date_columns_guess": "",
                "pollutant_columns_guess": "",
                "years_detected": ",".join(extract_year_tokens(str(p), years)),
                "detail": safe_text(e),
            })
    return rows


def inspect_grib_files(data_rows, years, deep=False, max_grib_files=100, max_subdatasets=500):
    rows = []
    if not deep:
        return rows
    if _gdal is None:
        rows.append({"path": "GDAL_NOT_AVAILABLE", "status": "SKIPPED", "detail": "osgeo.gdal not available; run with python-qgis-ltr.bat or install GDAL"})
        return rows
    gribs = [Path(r["path"]) for r in data_rows if Path(r["path"]).suffix.lower() in {".grib", ".grb", ".grb2"}]
    for idx, p in enumerate(gribs[:max_grib_files]):
        try:
            ds = _gdal.Open(str(p))
            if ds is None:
                rows.append({"path": str(p), "status": "FAIL_GDAL_OPEN", "detail": "gdal.Open returned None"})
                continue
            file_md = ds.GetMetadata() or {}
            subdatasets = ds.GetSubDatasets() or []
            base_years = set(extract_year_tokens(str(p), years))
            for k, v in file_md.items():
                base_years.update(extract_year_tokens(f"{k}={v}", years))
            rows.append({
                "path": str(p),
                "status": "PASS_GDAL_OPEN",
                "subdataset_count": len(subdatasets),
                "subdataset_index": "FILE",
                "short_name": file_md.get("GRIB_SHORT_NAME") or file_md.get("GRIB_ELEMENT") or "",
                "units": file_md.get("GRIB_UNIT") or file_md.get("GRIB_UNIT_NAME") or "",
                "validity_date": file_md.get("GRIB_VALIDITY_DATE") or file_md.get("GRIB_REF_TIME") or "",
                "year_detected": ",".join(sorted(base_years)),
                "description": safe_text(file_md)[:1000],
                "detail": "",
            })
            # Inspect subdataset metadata. This usually reads metadata, not full raster values.
            for sidx, (sd_name, sd_desc) in enumerate(subdatasets[:max_subdatasets]):
                desc_l = sd_desc.lower()
                # Keep PM2.5/fire/FRP-related subdatasets and any subdataset mentioning requested years.
                if not ("pm2" in desc_l or "pm2p5" in desc_l or "frp" in desc_l or "fire" in desc_l or any(str(y) in sd_desc for y in years)):
                    continue
                try:
                    sds = _gdal.Open(sd_name)
                    smd = sds.GetMetadata() if sds else {}
                except Exception:
                    smd = {}
                detected = set(extract_year_tokens(sd_desc, years))
                for k, v in (smd or {}).items():
                    detected.update(extract_year_tokens(f"{k}={v}", years))
                validity = (smd or {}).get("GRIB_VALIDITY_DATE") or (smd or {}).get("GRIB_REF_TIME") or ""
                if validity:
                    detected.update(extract_year_tokens(validity, years))
                rows.append({
                    "path": str(p),
                    "status": "PASS_SUBDATASET_METADATA",
                    "subdataset_count": len(subdatasets),
                    "subdataset_index": sidx,
                    "short_name": (smd or {}).get("GRIB_SHORT_NAME") or (smd or {}).get("GRIB_ELEMENT") or "",
                    "units": (smd or {}).get("GRIB_UNIT") or (smd or {}).get("GRIB_UNIT_NAME") or "",
                    "validity_date": validity,
                    "year_detected": ",".join(sorted(detected)),
                    "description": safe_text(sd_desc)[:1000],
                    "detail": "",
                })
        except Exception as e:
            rows.append({"path": str(p), "status": "ERROR", "detail": safe_text(e)})
    if len(gribs) > max_grib_files:
        rows.append({"path": "GRIB_SCAN_TRUNCATED", "status": "TRUNCATED", "detail": f"{len(gribs)} GRIB files found; inspected {max_grib_files}"})
    return rows


def find_latest_output_root(data_root):
    # Conservative discovery: only nearby known runtime roots and exact 03_outputs dirs.
    candidates = []
    roots_to_check = []
    data_path = Path(data_root)
    # Typical sibling under Module C.
    try:
        module_c_root = data_path.parent
        roots_to_check.append(module_c_root / "RUNTIMES_MANUALES")
        roots_to_check.append(module_c_root)
    except Exception:
        pass
    # Known unified local runtime root, if present.
    roots_to_check.append(Path("D:/GATA_MODULEC_UNIFIED_PROCESS"))
    for root in roots_to_check:
        if not root.exists():
            continue
        try:
            for p in root.rglob("03_outputs"):
                if p.is_dir():
                    try:
                        st = p.stat()
                        candidates.append((st.st_mtime, str(p)))
                    except Exception:
                        candidates.append((0, str(p)))
        except Exception:
            continue
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]


def read_runtime_output(output_root, years):
    out = Path(output_root) if output_root else None
    result = {
        "message_inventory": [],
        "daily_summary": [],
        "score_daily": [],
        "smoke_days_unit": [],
        "smoke_route_audit": [],
        "inputs_resolved": {},
        "found": False,
    }
    if not out or not out.exists():
        return result
    result["found"] = True
    paths = {
        "message_inventory": out / "qa" / "gfas_pm2p5fire_message_inventory.tsv",
        "daily_summary": out / "qa" / "gfas_pm2p5fire_portugal_daily_summary.csv",
        "score_daily": out / "tables" / "smoke_day_score_nuts3_daily.csv",
        "smoke_days_unit": out / "tables" / "smoke_days_unit_2015_2024.csv",
        "smoke_route_audit": out / "qa" / "smoke_route_audit.tsv",
    }
    for key, p in paths.items():
        result[key] = read_delimited(p)
    inp = out / "qa" / "inputs_resolved.json"
    if inp.exists():
        try:
            result["inputs_resolved"] = json.loads(inp.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            result["inputs_resolved"] = {"READ_ERROR": safe_text(e)}
    return result


def summarize_runtime_by_year(runtime, years):
    rows = []
    msg_years = {}
    for r in runtime.get("message_inventory", []):
        y = str(r.get("year_hint") or "")
        status = str(r.get("status") or "")
        if y:
            msg_years.setdefault(y, []).append(status)
    daily_years = {}
    for r in runtime.get("daily_summary", []):
        y = str(r.get("year") or "")
        if y:
            daily_years.setdefault(y, []).append(r)
    score_years = {}
    for r in runtime.get("score_daily", []):
        y = str(r.get("year") or "")
        if y:
            score_years.setdefault(y, []).append(r)
    annual_years = {}
    for r in runtime.get("smoke_days_unit", []):
        y = str(r.get("year") or "")
        if y:
            annual_years.setdefault(y, []).append(r)
    route_years = {}
    for r in runtime.get("smoke_route_audit", []):
        y = str(r.get("year") or "")
        if y:
            route_years.setdefault(y, []).append(r)

    for y in years:
        ys = str(y)
        annual_rows = annual_years.get(ys, [])
        methods = sorted(set(str(r.get("smoke_method") or "") for r in annual_rows if r.get("smoke_method") is not None))
        smoke_vals = []
        for r in annual_rows:
            try:
                smoke_vals.append(float(str(r.get("smoke_days", "")).replace(",", ".")))
            except Exception:
                pass
        unique_vals = sorted(set(smoke_vals))
        route_rows = route_years.get(ys, [])
        route_methods = sorted(set(str(r.get("method") or "") for r in route_rows if r.get("method") is not None))
        rows.append({
            "year": ys,
            "runtime_message_inventory_rows": len(msg_years.get(ys, [])),
            "runtime_message_inventory_statuses": ",".join(sorted(set(msg_years.get(ys, [])))),
            "runtime_gfas_daily_summary_rows": len(daily_years.get(ys, [])),
            "runtime_score_daily_rows": len(score_years.get(ys, [])),
            "runtime_score_daily_unit_count": len(set(r.get("unit_id", "") for r in score_years.get(ys, []))),
            "runtime_annual_smoke_rows": len(annual_rows),
            "runtime_annual_smoke_unique_values": len(unique_vals),
            "runtime_annual_smoke_min": min(smoke_vals) if smoke_vals else "",
            "runtime_annual_smoke_max": max(smoke_vals) if smoke_vals else "",
            "runtime_annual_methods": ",".join(methods),
            "runtime_route_methods": ",".join(route_methods),
        })
    return rows


def summarize_data_by_year(data_rows, archive_rows, grib_rows, parquet_rows, years):
    rows = []
    for y in years:
        ys = str(y)
        file_path_hits = [r for r in data_rows if ys in str(r.get("years_in_path", "")).split(",")]
        archive_hits = [r for r in archive_rows if ys in str(r.get("years_in_member_name", "")).split(",")]
        grib_hits = [r for r in grib_rows if ys in str(r.get("year_detected", "")).split(",")]
        parquet_hits = [r for r in parquet_rows if ys in str(r.get("years_detected", "")).split(",")]
        gfas_hits = [r for r in file_path_hits if "GFAS" in r.get("kind_guess", "") or "GRIB" in r.get("kind_guess", "")]
        era5_hits = [r for r in file_path_hits if "ERA5" in r.get("kind_guess", "")]
        aq_hits = [r for r in file_path_hits if "AQ" in r.get("kind_guess", "") or "PARQUET" in r.get("kind_guess", "")]
        rows.append({
            "year": ys,
            "data_files_with_year_in_path": len(file_path_hits),
            "data_gfas_or_grib_files_with_year_in_path": len(gfas_hits),
            "data_era5_files_with_year_in_path": len(era5_hits),
            "data_aq_or_parquet_files_with_year_in_path": len(aq_hits),
            "zip_members_with_year": len(archive_hits),
            "deep_grib_metadata_hits": len(grib_hits),
            "deep_parquet_year_hits": len(parquet_hits),
            "example_data_paths": " | ".join([r.get("relative_path") or r.get("path") for r in file_path_hits[:5]]),
            "example_archive_members": " | ".join([r.get("member_name") for r in archive_hits[:5]]),
            "example_grib_metadata": " | ".join([Path(r.get("path", "")).name + ":" + str(r.get("short_name", "")) + ":" + str(r.get("validity_date", "")) for r in grib_hits[:5]]),
            "example_parquet": " | ".join([Path(r.get("path", "")).name for r in parquet_hits[:5]]),
        })
    return rows


def scan_repo_code(repo_root, years, max_hits=5000):
    rows = []
    root = Path(repo_root)
    if not root.exists():
        return [{"path": "MISSING_REPO", "line": "", "keyword": "", "text": f"RepoRoot not found: {repo_root}"}]
    keywords = ["gfas", "pm2p5", "pm2.5", "frp", "smoke", "humo", "era5", "parquet", "smoke_route", "direct_year", "interpolated_from_anchors", "extrapolated_from_anchors", "inputs_resolved"]
    for p in root.rglob("*"):
        if len(rows) >= max_hits:
            break
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".py", ".md", ".txt", ".ps1", ".json", ".tsv", ".csv"}:
            continue
        if any(part.lower() in {".git", "__pycache__", ".venv", "venv"} for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            hit_keys = [k for k in keywords if k in low]
            if not hit_keys:
                continue
            rows.append({
                "path": str(p.relative_to(root)),
                "line": i,
                "keyword": ",".join(hit_keys),
                "text": line.strip()[:1000],
            })
            if len(rows) >= max_hits:
                break
    return rows


def build_decision_rows(years, data_summary, runtime_summary):
    by_data = {str(r["year"]): r for r in data_summary}
    by_run = {str(r["year"]): r for r in runtime_summary}
    rows = []
    for y in years:
        ys = str(y)
        d = by_data.get(ys, {})
        r = by_run.get(ys, {})
        data_evidence = (
            int(d.get("data_files_with_year_in_path") or 0) > 0 or
            int(d.get("zip_members_with_year") or 0) > 0 or
            int(d.get("deep_grib_metadata_hits") or 0) > 0 or
            int(d.get("deep_parquet_year_hits") or 0) > 0
        )
        direct_runtime = (
            int(r.get("runtime_message_inventory_rows") or 0) > 0 or
            int(r.get("runtime_gfas_daily_summary_rows") or 0) > 0 or
            "direct_year" in str(r.get("runtime_annual_methods", "")) or
            "direct_year" in str(r.get("runtime_route_methods", ""))
        )
        reconstructed = (
            "interpolated" in str(r.get("runtime_annual_methods", "")).lower() or
            "extrapolated" in str(r.get("runtime_annual_methods", "")).lower() or
            "interpolated" in str(r.get("runtime_route_methods", "")).lower() or
            "extrapolated" in str(r.get("runtime_route_methods", "")).lower()
        )
        zero_homogeneous = False
        try:
            zero_homogeneous = int(r.get("runtime_annual_smoke_rows") or 0) > 0 and int(r.get("runtime_annual_smoke_unique_values") or 0) == 1 and float(r.get("runtime_annual_smoke_max") or 0) == 0.0
        except Exception:
            zero_homogeneous = False

        if direct_runtime:
            decision = "PASS_CONSUMED_AS_DIRECT_YEAR_EVIDENCE"
            action = "Keep as direct smoke evidence, but still verify daily coverage completeness."
        elif data_evidence and reconstructed:
            decision = "DATA_PRESENT_OR_INDEXED_BUT_RUNTIME_RECONSTRUCTED_ONLY"
            action = "Investigate consumer/decoder/indexing: local database shows some year evidence but runtime did not consume it directly."
        elif data_evidence and not direct_runtime:
            decision = "DATA_PRESENT_OR_INDEXED_BUT_NOT_CONSUMED"
            action = "Likely consumption/indexing/decoder failure. Locate matching source file and patch producer only after direct proof."
        elif reconstructed:
            decision = "NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY"
            action = "Treat as invalid for direct historical smoke. Recover/download direct data for this year."
        else:
            decision = "NO_LOCAL_YEAR_EVIDENCE_FOUND"
            action = "Treat as absent from local database or not discoverable by audit. Recover/download direct data for this year."
        if zero_homogeneous and not direct_runtime:
            decision = decision + "__ALL_ZERO_HOMOGENEOUS_OUTPUT"
            action = action + " Do not interpret zero as no smoke; it is missing/invalid evidence until proven otherwise."
        rows.append({
            "year": ys,
            "decision": decision,
            "data_evidence_found": data_evidence,
            "runtime_direct_evidence": direct_runtime,
            "runtime_reconstructed": reconstructed,
            "runtime_all_zero_homogeneous": zero_homogeneous,
            "recommended_action": action,
            "data_summary": safe_text(d),
            "runtime_summary": safe_text(r),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--output-root", default="")
    ap.add_argument("--audit-root", required=True)
    ap.add_argument("--years", required=True)
    ap.add_argument("--deep-grib", action="store_true")
    ap.add_argument("--deep-parquet", action="store_true")
    args = ap.parse_args()

    years = [int(x.strip()) for x in args.years.split(",") if x.strip()]
    audit_root = Path(args.audit_root)
    ensure_dir(audit_root)

    output_root = args.output_root.strip()
    if not output_root:
        output_root = find_latest_output_root(args.data_root)

    context = {
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
        "mode": "READ_ONLY_NO_PATCH_NO_COMMIT_NO_RUNTIME_MUTATION",
        "repo_root": args.repo_root,
        "data_root": args.data_root,
        "output_root_used": output_root,
        "required_years": ",".join(str(y) for y in years),
        "deep_grib": args.deep_grib,
        "deep_parquet": args.deep_parquet,
        "python_executable": sys.executable,
        "gdal_available": bool(_gdal),
        "pandas_available": bool(_pd),
    }
    (audit_root / "00_run_context.json").write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")

    data_rows = scan_data_root(args.data_root, years)
    write_tsv(audit_root / "01_data_root_smoke_inventory.tsv", data_rows, [
        "path", "relative_path", "extension", "kind_guess", "size_bytes", "modified_time", "years_in_path", "name"
    ])

    archive_rows = scan_archives(data_rows, years)
    write_tsv(audit_root / "02_archive_member_inventory.tsv", archive_rows, [
        "archive_path", "archive_size_bytes", "archive_member_count_total", "member_index", "member_name", "member_extension", "member_size_bytes", "years_in_member_name", "member_relevance_guess"
    ])

    grib_rows = inspect_grib_files(data_rows, years, deep=args.deep_grib)
    write_tsv(audit_root / "03_gfas_grib_metadata_inventory.tsv", grib_rows, [
        "path", "status", "subdataset_count", "subdataset_index", "short_name", "units", "validity_date", "year_detected", "description", "detail"
    ])

    parquet_rows = inspect_parquet_files(data_rows, years, deep=args.deep_parquet)
    write_tsv(audit_root / "04_parquet_aq_inventory.tsv", parquet_rows, [
        "path", "status", "rows", "columns", "date_columns_guess", "pollutant_columns_guess", "years_detected", "detail"
    ])

    runtime = read_runtime_output(output_root, years) if output_root else {"found": False}
    runtime_summary = summarize_runtime_by_year(runtime, years)
    write_tsv(audit_root / "05_runtime_smoke_coverage_by_year.tsv", runtime_summary, [
        "year", "runtime_message_inventory_rows", "runtime_message_inventory_statuses", "runtime_gfas_daily_summary_rows", "runtime_score_daily_rows", "runtime_score_daily_unit_count", "runtime_annual_smoke_rows", "runtime_annual_smoke_unique_values", "runtime_annual_smoke_min", "runtime_annual_smoke_max", "runtime_annual_methods", "runtime_route_methods"
    ])

    data_summary = summarize_data_by_year(data_rows, archive_rows, grib_rows, parquet_rows, years)
    write_tsv(audit_root / "06_local_database_year_evidence.tsv", data_summary, [
        "year", "data_files_with_year_in_path", "data_gfas_or_grib_files_with_year_in_path", "data_era5_files_with_year_in_path", "data_aq_or_parquet_files_with_year_in_path", "zip_members_with_year", "deep_grib_metadata_hits", "deep_parquet_year_hits", "example_data_paths", "example_archive_members", "example_grib_metadata", "example_parquet"
    ])

    code_rows = scan_repo_code(args.repo_root, years)
    write_tsv(audit_root / "07_pipeline_code_smoke_references.tsv", code_rows, [
        "path", "line", "keyword", "text"
    ])

    decision_rows = build_decision_rows(years, data_summary, runtime_summary)
    write_tsv(audit_root / "08_FINAL_year_coverage_decision.tsv", decision_rows, [
        "year", "decision", "data_evidence_found", "runtime_direct_evidence", "runtime_reconstructed", "runtime_all_zero_homogeneous", "recommended_action", "data_summary", "runtime_summary"
    ])

    # Copy key runtime flags, if present, into JSON for easy reading.
    key_flags = {}
    if runtime.get("found"):
        inp = runtime.get("inputs_resolved") or {}
        for k in ["smoke_route_status", "smoke_route_decision", "smoke_route_reason", "required_decoder", "smoke_route_contract_correction", "smoke_route_contract_correction_status", "smoke_route_contract_correction_basis"]:
            if k in inp:
                key_flags[k] = inp[k]
    (audit_root / "09_runtime_key_smoke_flags.json").write_text(json.dumps(key_flags, indent=2, ensure_ascii=False), encoding="utf-8")

    # Final Markdown report.
    direct_years = [r["year"] for r in decision_rows if r["runtime_direct_evidence"]]
    reconstructed_years = [r["year"] for r in decision_rows if r["runtime_reconstructed"] and not r["runtime_direct_evidence"]]
    absent_or_unconsumed = [r["year"] for r in decision_rows if not r["runtime_direct_evidence"]]

    md = []
    md.append("# MODULE C â€” Smoke database year coverage audit\n")
    md.append("## Scope\n")
    md.append("This audit is READ ONLY. It does not patch code, mutate input data, run the pipeline, commit, reset, or clean git state.\n")
    md.append("## Inputs\n")
    md.append(f"- RepoRoot: `{args.repo_root}`\n")
    md.append(f"- DataRoot: `{args.data_root}`\n")
    md.append(f"- OutputRoot used: `{output_root}`\n")
    md.append(f"- Required years: `{','.join(str(y) for y in years)}`\n")
    md.append(f"- DeepGrib: `{args.deep_grib}`\n")
    md.append(f"- DeepParquet: `{args.deep_parquet}`\n")
    md.append(f"- GDAL available: `{bool(_gdal)}`\n")
    md.append(f"- pandas available: `{bool(_pd)}`\n")
    md.append("\n## Runtime smoke route flags\n")
    if key_flags:
        for k, v in key_flags.items():
            md.append(f"- `{k}` = `{safe_text(v)}`\n")
    else:
        md.append("- No runtime smoke flags were read. Provide -OutputRoot to inspect a specific runtime.\n")
    md.append("\n## Direct evidence summary\n")
    md.append(f"- Years consumed by runtime as direct evidence: `{','.join(direct_years) if direct_years else 'NONE'}`\n")
    md.append(f"- Years reconstructed/interpolated/extrapolated without direct runtime evidence: `{','.join(reconstructed_years) if reconstructed_years else 'NONE'}`\n")
    md.append(f"- Years not consumed as direct runtime evidence: `{','.join(absent_or_unconsumed) if absent_or_unconsumed else 'NONE'}`\n")
    md.append("\n## Year decisions\n")
    md.append("| year | decision | action |\n|---:|---|---|\n")
    for r in decision_rows:
        md.append(f"| {r['year']} | `{r['decision']}` | {safe_text(r['recommended_action'])} |\n")
    md.append("\n## Interpretation rule\n")
    md.append("- If `DATA_PRESENT_OR_INDEXED_BUT_NOT_CONSUMED` appears, the local database likely contains a year-linked source but the pipeline did not consume it as direct smoke evidence. Investigate decoder/indexing/selector code.\n")
    md.append("- If `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` appears, the runtime output for that year is not a valid historical direct smoke observation. It is interpolation/extrapolation and must not feed final IECH as direct evidence.\n")
    md.append("- If `ALL_ZERO_HOMOGENEOUS_OUTPUT` appears, zero must be treated as missing/invalid until direct year decoding proves otherwise. It is not evidence of no smoke.\n")
    md.append("\n## Output files\n")
    for fn in [
        "01_data_root_smoke_inventory.tsv", "02_archive_member_inventory.tsv", "03_gfas_grib_metadata_inventory.tsv", "04_parquet_aq_inventory.tsv", "05_runtime_smoke_coverage_by_year.tsv", "06_local_database_year_evidence.tsv", "07_pipeline_code_smoke_references.tsv", "08_FINAL_year_coverage_decision.tsv", "09_runtime_key_smoke_flags.json"
    ]:
        md.append(f"- `{fn}`\n")
    md.append("\n## Final rule\n")
    md.append("A year is valid for historical smoke only if it has direct, year-specific source evidence and the runtime consumes it as direct evidence. Interpolation/extrapolation from anchor years is not acceptable for final IECH closure unless explicitly declared as non-final proxy reconstruction.\n")
    (audit_root / "10_FINAL_SMOKE_DATABASE_YEAR_COVERAGE_AUDIT.md").write_text("".join(md), encoding="utf-8")

    print("AUDIT_ROOT=" + str(audit_root))
    print("OUTPUT_ROOT_USED=" + str(output_root))
    print("FINAL_DECISION_TSV=" + str(audit_root / "08_FINAL_year_coverage_decision.tsv"))
    print("FINAL_REPORT_MD=" + str(audit_root / "10_FINAL_SMOKE_DATABASE_YEAR_COVERAGE_AUDIT.md"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
