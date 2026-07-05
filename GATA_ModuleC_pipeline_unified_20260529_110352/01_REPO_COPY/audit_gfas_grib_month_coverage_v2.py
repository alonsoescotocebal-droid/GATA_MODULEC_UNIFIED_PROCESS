#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
audit_gfas_grib_month_coverage_v2.py

Audita cobertura mensual/anual GFAS PM2P5FIRE 2015-2024.

Diferencias frente a v1:
- No se rompe si --grib-ls apunta a una ruta inexistente.
- Detecta y rechaza placeholders como RUTA_COMPLETA_A\grib_ls.exe.
- Si no existe grib_ls, intenta fallback con GDAL/osgeo.gdal.
- No lee valores raster; solo metadatos de mensajes/bandas.

Uso con ecCodes si existe grib_ls:
python audit_gfas_grib_month_coverage_v2.py --grib-ls "C:\...\grib_ls.exe" --roots ... --runtime-output ... --out ...

Uso sin grib_ls, recomendado con QGIS/GDAL:
call "C:\OSGeo4W64\bin\python-qgis-ltr.bat" "audit_gfas_grib_month_coverage_v2.py" --roots ... --runtime-output ... --out ...
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Optional


YEARS = list(range(2015, 2025))
GRIB_EXTS = {".grib", ".grb", ".grib2", ".grb2"}
GFAS_HINTS = ("GFAS", "PM2P5FIRE", "CAMS-GFAS", "CAM-GFAS", "gfas", "pm2p5fire")


def norm_path(p: Path) -> str:
    try:
        return str(p.resolve())
    except Exception:
        return str(p)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def is_placeholder_path(s: str) -> bool:
    if not s:
        return False
    low = s.lower()
    return any(tok in low for tok in ["ruta_completa", "path_to", "complete_path", "xxx", "placeholder"])


def find_executable(name: str) -> Optional[str]:
    hit = shutil.which(name)
    if hit:
        return hit

    user = os.environ.get("USERNAME", "")
    userprofile = os.environ.get("USERPROFILE", "")
    candidates = [
        Path(r"C:\OSGeo4W64\bin") / name,
        Path(r"C:\OSGeo4W\bin") / name,
        Path(r"C:\ProgramData\miniforge3\Library\bin") / name,
        Path(r"C:\ProgramData\miniforge3\envs\gribtools\Library\bin") / name,
        Path(r"C:\ProgramData\Miniforge3\Library\bin") / name,
        Path(r"C:\ProgramData\Miniforge3\envs\gribtools\Library\bin") / name,
    ]

    if userprofile:
        candidates += [
            Path(userprofile) / "miniforge3" / "Library" / "bin" / name,
            Path(userprofile) / "miniforge3" / "envs" / "gribtools" / "Library" / "bin" / name,
            Path(userprofile) / "mambaforge" / "Library" / "bin" / name,
            Path(userprofile) / "mambaforge" / "envs" / "gribtools" / "Library" / "bin" / name,
            Path(userprofile) / "anaconda3" / "Library" / "bin" / name,
            Path(userprofile) / "anaconda3" / "envs" / "gribtools" / "Library" / "bin" / name,
            Path(userprofile) / "miniconda3" / "Library" / "bin" / name,
            Path(userprofile) / "miniconda3" / "envs" / "gribtools" / "Library" / "bin" / name,
        ]

    if user:
        candidates += [
            Path(r"C:\Users") / user / "miniforge3" / "envs" / "gribtools" / "Library" / "bin" / name,
            Path(r"C:\Users") / user / "miniforge3" / "Library" / "bin" / name,
        ]

    expanded = []
    for c in candidates:
        expanded.append(c)
        if os.name == "nt" and not str(c).lower().endswith(".exe"):
            expanded.append(c.with_suffix(".exe"))

    for c in expanded:
        if c.exists():
            return str(c)
    return None


def expected_min_days(year: int, month: int) -> int:
    return min(calendar.monthrange(year, month)[1], 29)


def parse_yyyymmdd(token: str) -> Optional[str]:
    token = re.sub(r"\D", "", str(token))
    if len(token) < 8:
        return None
    try:
        d = dt.date(int(token[:4]), int(token[4:6]), int(token[6:8]))
    except Exception:
        return None
    if d.year in YEARS:
        return d.isoformat()
    return None


def infer_year_from_path(path: Path) -> Optional[int]:
    years = [int(y) for y in re.findall(r"(20[12]\d)", str(path))]
    years = [y for y in years if y in YEARS]
    return years[-1] if years else None


def is_gfas_candidate(path: Path) -> bool:
    text = str(path)
    return path.suffix.lower() in GRIB_EXTS and any(h in text for h in GFAS_HINTS)


def inventory_gribs(roots: list[Path]) -> list[Path]:
    out = []
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and is_gfas_candidate(p):
                key = str(p).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(p)
    return sorted(out, key=lambda p: str(p).lower())


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def extract_dates_from_grib_ls(grib_ls: str, path: Path, timeout: int) -> tuple[set[str], str, str, list[str]]:
    if not grib_ls or is_placeholder_path(grib_ls) or not Path(grib_ls).exists():
        return set(), "NO_VALID_GRIB_LS", f"Invalid grib_ls path: {grib_ls}", []

    cmd = [
        grib_ls,
        "-p",
        "shortName,name,paramId,dataDate,dataTime,validityDate,validityTime",
        str(path),
    ]
    try:
        cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except Exception as e:
        return set(), "GRIB_LS_EXEC_ERROR", str(e), []

    dates = set()
    samples = []
    for line in cp.stdout.splitlines():
        low = line.lower()
        if not any(tok in low for tok in ["pm2p5", "particulate", "fire"]):
            # si la línea solo tiene fechas pero no nombres, la retenemos si coincide con nombre archivo PM2P5FIRE
            if "pm2p5fire" not in str(path).lower():
                continue
        found = re.findall(r"\b(20[12]\d[01]\d[0-3]\d)\b", line)
        for token in found:
            d = parse_yyyymmdd(token)
            if d:
                dates.add(d)
                if len(samples) < 10:
                    samples.append(line.strip())
    err = cp.stderr.strip()
    return dates, "GRIB_LS", err, samples


def unix_to_date(value: str) -> Optional[str]:
    try:
        # GDAL GRIB_VALID_TIME suele ser epoch seconds.
        n = int(float(str(value).strip()))
        if 0 < n < 4102444800:
            d = dt.datetime.utcfromtimestamp(n).date()
            if d.year in YEARS:
                return d.isoformat()
    except Exception:
        pass
    return None


def extract_dates_from_gdal(path: Path, max_bands: int = 0) -> tuple[set[str], str, str, list[str]]:
    try:
        from osgeo import gdal
    except Exception as e:
        return set(), "NO_GDAL", f"osgeo.gdal not available: {e}", []

    try:
        ds = gdal.Open(str(path))
    except Exception as e:
        return set(), "GDAL_OPEN_ERROR", str(e), []

    if ds is None:
        return set(), "GDAL_OPEN_FAILED", "gdal.Open returned None", []

    dates = set()
    samples = []
    band_count = int(ds.RasterCount or 0)
    limit = band_count if max_bands <= 0 else min(band_count, max_bands)

    for i in range(1, limit + 1):
        band = ds.GetRasterBand(i)
        if band is None:
            continue
        md = band.GetMetadata() or {}
        desc = band.GetDescription() or ""
        alltext = " ".join([desc] + [f"{k}={v}" for k, v in md.items()])
        low = alltext.lower()

        # GFAS PM2P5FIRE puede aparecer con nombres variables.
        is_pm = any(tok in low for tok in ["pm2p5", "pm2.5", "particulate matter", "aerosol"])
        is_fire = any(tok in low for tok in ["fire", "wildfire", "biomass", "burning"])
        if not (is_pm or "pm2p5fire" in str(path).lower()):
            continue

        d = None
        for key in ["GRIB_VALID_TIME", "GRIB_REF_TIME", "VALID_TIME", "NETCDF_DIM_time"]:
            if key in md:
                d = unix_to_date(md[key])
                if d:
                    break

        if not d:
            # Fallback a yyyymmdd en descripción/metadatos.
            found = re.findall(r"\b(20[12]\d[01]\d[0-3]\d)\b", alltext)
            for token in found:
                d = parse_yyyymmdd(token)
                if d:
                    break

        if d:
            dates.add(d)
            if len(samples) < 10:
                samples.append(f"band={i}; {alltext[:500]}")

    return dates, "GDAL_BAND_METADATA", "", samples


def summarize_year_month(dates_by_file: dict[str, set[str]]) -> dict[int, dict[int, set[str]]]:
    ym = {y: {m: set() for m in range(1, 13)} for y in YEARS}
    for dates in dates_by_file.values():
        for s in dates:
            try:
                d = dt.date.fromisoformat(s)
            except Exception:
                continue
            if d.year in ym:
                ym[d.year][d.month].add(s)
    return ym


def read_runtime_dates(runtime_output: Optional[Path]) -> set[str]:
    if not runtime_output:
        return set()
    root = runtime_output
    if (root / "03_outputs").exists():
        root = root / "03_outputs"
    candidates = [
        root / "tables" / "smoke_day_score_nuts3_daily.csv",
        root / "tables" / "smoke_day_score_municipio_daily.csv",
        root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv",
        root / "qa" / "smoke_route_audit.tsv",
    ]
    out = set()
    for p in candidates:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for s in re.findall(r"\b(20[12]\d-[01]\d-[0-3]\d)\b", text):
            try:
                d = dt.date.fromisoformat(s)
                if d.year in YEARS:
                    out.add(d.isoformat())
            except Exception:
                pass
        for s in re.findall(r"\b(20[12]\d[01]\d[0-3]\d)\b", text):
            d = parse_yyyymmdd(s)
            if d:
                out.add(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", required=True)
    ap.add_argument("--runtime-output", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--grib-ls", default="")
    ap.add_argument("--timeout-per-file", type=int, default=240)
    ap.add_argument("--max-gdal-bands", type=int, default=0, help="0 = all bands")
    args = ap.parse_args()

    roots = [Path(x) for x in args.roots]
    out = Path(args.out)
    ensure_dir(out)

    requested_grib_ls = args.grib_ls.strip()
    grib_ls = ""
    grib_ls_note = ""
    if requested_grib_ls:
        if is_placeholder_path(requested_grib_ls) or not Path(requested_grib_ls).exists():
            grib_ls_note = f"IGNORED_INVALID_OR_PLACEHOLDER_GRIB_LS={requested_grib_ls}"
        else:
            grib_ls = requested_grib_ls
    if not grib_ls:
        found = find_executable("grib_ls")
        if found:
            grib_ls = found

    gribs = inventory_gribs(roots)

    inv_rows = []
    for p in gribs:
        st = p.stat()
        inv_rows.append({
            "file": norm_path(p),
            "year_inferred": infer_year_from_path(p) or "",
            "size_bytes": st.st_size,
            "modified": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    write_tsv(out / "gfas_grib_file_inventory.tsv", inv_rows, ["file", "year_inferred", "size_bytes", "modified"])

    dates_by_file = {}
    file_rows = []
    sample_rows = []
    err_rows = []

    for p in gribs:
        dates = set()
        method = ""
        error = ""

        if grib_ls:
            dates, method, error, samples = extract_dates_from_grib_ls(grib_ls, p, args.timeout_per_file)
        else:
            samples = []

        if not dates:
            gd_dates, gd_method, gd_error, gd_samples = extract_dates_from_gdal(p, args.max_gdal_bands)
            if gd_dates:
                dates, method, error, samples = gd_dates, gd_method, gd_error, gd_samples
            else:
                if not method:
                    method = gd_method
                error = (error + " | " + gd_error).strip(" | ")
                samples += gd_samples

        dates_by_file[norm_path(p)] = dates
        months = sorted({dt.date.fromisoformat(d).month for d in dates}) if dates else []
        years = sorted({dt.date.fromisoformat(d).year for d in dates}) if dates else []
        file_rows.append({
            "file": norm_path(p),
            "year_inferred": infer_year_from_path(p) or "",
            "metadata_method": method,
            "date_count": len(dates),
            "year_values": ",".join(map(str, years)),
            "month_values": ",".join(f"{m:02d}" for m in months),
            "min_date": min(dates) if dates else "",
            "max_date": max(dates) if dates else "",
            "error": error,
        })
        if error:
            err_rows.append({"file": norm_path(p), "error": error})
        for s in samples:
            sample_rows.append({"file": norm_path(p), "sample_metadata_row": s})

    write_tsv(out / "gfas_grib_date_coverage_by_file.tsv", file_rows,
              ["file", "year_inferred", "metadata_method", "date_count", "year_values", "month_values", "min_date", "max_date", "error"])
    write_tsv(out / "gfas_grib_metadata_errors.tsv", err_rows, ["file", "error"])
    write_tsv(out / "gfas_grib_metadata_sample_rows.tsv", sample_rows, ["file", "sample_metadata_row"])

    raw_ym = summarize_year_month(dates_by_file)
    runtime_dates = read_runtime_dates(Path(args.runtime_output) if args.runtime_output else None)
    runtime_ym = summarize_year_month({"runtime": runtime_dates})

    ym_rows = []
    for source, ym in [("RAW_GRIB_METADATA", raw_ym), ("RUNTIME_USED_DATES", runtime_ym)]:
        if source == "RUNTIME_USED_DATES" and not runtime_dates:
            continue
        for y in YEARS:
            for m in range(1, 13):
                cnt = len(ym[y][m])
                exp = expected_min_days(y, m)
                ym_rows.append({
                    "source": source,
                    "year": y,
                    "month": f"{m:02d}",
                    "unique_dates": cnt,
                    "expected_min_dates": exp,
                    "calendar_days": calendar.monthrange(y, m)[1],
                    "status": "PASS" if cnt >= exp else "FAIL",
                    "first_date": min(ym[y][m]) if ym[y][m] else "",
                    "last_date": max(ym[y][m]) if ym[y][m] else "",
                })
    write_tsv(out / "gfas_coverage_by_year_month.tsv", ym_rows,
              ["source", "year", "month", "unique_dates", "expected_min_dates", "calendar_days", "status", "first_date", "last_date"])

    decision_rows = []
    for y in YEARS:
        raw_total = sum(len(raw_ym[y][m]) for m in range(1, 13))
        raw_present = sum(1 for m in range(1, 13) if len(raw_ym[y][m]) > 0)
        raw_pass = sum(1 for m in range(1, 13) if len(raw_ym[y][m]) >= expected_min_days(y, m))
        raw_dates = [d for m in range(1, 13) for d in raw_ym[y][m]]

        rt_total = sum(len(runtime_ym[y][m]) for m in range(1, 13)) if runtime_dates else ""
        rt_present = sum(1 for m in range(1, 13) if len(runtime_ym[y][m]) > 0) if runtime_dates else ""
        rt_pass = sum(1 for m in range(1, 13) if len(runtime_ym[y][m]) >= expected_min_days(y, m)) if runtime_dates else ""

        if raw_pass == 12 and runtime_dates and rt_pass != 12:
            decision = "RAW_DATA_FULL_YEAR_BUT_RUNTIME_LIMITED_OR_DOWNSAMPLED"
        elif raw_pass == 12:
            decision = "RAW_DATA_FULL_YEAR_COVERAGE_PASS"
        elif raw_total == 0:
            decision = "NO_DATES_EXTRACTED_NEED_GRIB_TOOL_OR_GDAL_METADATA"
        elif raw_present <= 4 and raw_dates and max(raw_dates)[5:7] in {"03", "04"}:
            decision = "RAW_GRIB_APPEARS_JAN_APR_TRUNCATED_OR_ONLY_EARLY_YEAR"
        else:
            decision = "RAW_GRIB_PARTIAL_YEAR_COVERAGE"

        decision_rows.append({
            "year": y,
            "raw_unique_dates": raw_total,
            "raw_months_present": raw_present,
            "raw_months_pass_min_rule": raw_pass,
            "raw_min_date": min(raw_dates) if raw_dates else "",
            "raw_max_date": max(raw_dates) if raw_dates else "",
            "runtime_unique_dates": rt_total,
            "runtime_months_present": rt_present,
            "runtime_months_pass_min_rule": rt_pass,
            "decision": decision,
        })

    write_tsv(out / "gfas_coverage_decision_by_year.tsv", decision_rows,
              ["year", "raw_unique_dates", "raw_months_present", "raw_months_pass_min_rule",
               "raw_min_date", "raw_max_date", "runtime_unique_dates", "runtime_months_present",
               "runtime_months_pass_min_rule", "decision"])

    counts = Counter(r["decision"] for r in decision_rows)
    if all(r["decision"] == "RAW_DATA_FULL_YEAR_BUT_RUNTIME_LIMITED_OR_DOWNSAMPLED" for r in decision_rows):
        final = "DATA_FULL_YEAR_PIPELINE_LIMITED_OR_DOWNSAMPLED"
    elif all(r["decision"] == "RAW_DATA_FULL_YEAR_COVERAGE_PASS" for r in decision_rows):
        final = "DATA_FULL_YEAR_AVAILABLE"
    elif all(r["decision"] == "RAW_GRIB_APPEARS_JAN_APR_TRUNCATED_OR_ONLY_EARLY_YEAR" for r in decision_rows):
        final = "RAW_GFAS_FILES_APPEAR_JAN_APR_ONLY"
    elif all(r["decision"] == "NO_DATES_EXTRACTED_NEED_GRIB_TOOL_OR_GDAL_METADATA" for r in decision_rows):
        final = "CANNOT_VERIFY_INTERNAL_GRIB_DATES_NO_GRIB_LS_OR_GDAL_METADATA"
    else:
        final = "MIXED_OR_PARTIAL_GFAS_COVERAGE_REQUIRES_REVIEW"

    report = []
    report.append("# GFAS GRIB month/date coverage audit v2")
    report.append("")
    report.append(f"- generated: {dt.datetime.now().isoformat(timespec='seconds')}")
    report.append(f"- requested_grib_ls: {requested_grib_ls or ''}")
    report.append(f"- grib_ls_used: {grib_ls or 'NOT FOUND'}")
    if grib_ls_note:
        report.append(f"- grib_ls_note: {grib_ls_note}")
    report.append(f"- grib_candidates_found: {len(gribs)}")
    report.append(f"- runtime_dates_found: {len(runtime_dates)}")
    report.append("")
    report.append(f"## FINAL_DECISION: `{final}`")
    report.append("")
    for k, v in sorted(counts.items()):
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("| year | raw_dates | raw_months_present | raw_months_pass | raw_min | raw_max | runtime_dates | runtime_months_present | decision |")
    report.append("|---:|---:|---:|---:|---|---|---:|---:|---|")
    for r in decision_rows:
        report.append(f"| {r['year']} | {r['raw_unique_dates']} | {r['raw_months_present']} | {r['raw_months_pass_min_rule']} | {r['raw_min_date']} | {r['raw_max_date']} | {r['runtime_unique_dates']} | {r['runtime_months_present']} | {r['decision']} |")
    (out / "GFAS_GRIB_DATE_COVERAGE_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    print(f"FINAL_DECISION={final}")
    print(f"REPORT={out / 'GFAS_GRIB_DATE_COVERAGE_REPORT.md'}")
    print(f"OUT_DIR={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
