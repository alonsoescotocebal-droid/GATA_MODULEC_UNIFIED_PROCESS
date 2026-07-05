#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
audit_gfas_grib_month_coverage.py

Verifica si los GRIB GFAS/PM2P5FIRE 2015-2024 contienen fechas de los 12 meses
o si el runtime/pipeline está leyendo solamente una ventana parcial (por ejemplo enero-abril).

Este script NO lee valores raster ni reprocesa el pipeline.
Solo inspecciona metadatos de archivos GRIB mediante ecCodes grib_ls cuando está disponible,
y opcionalmente compara contra un runtime ya producido.

Uso recomendado en PowerShell:

cd "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY"

python audit_gfas_grib_month_coverage.py `
  --roots `
    "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" `
    "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos_RECOVERY_2015_2024_PIPELINE_GRIB" `
    "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos_RECOVERY_2015_2024" `
  --runtime-output "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027" `
  --out "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\GFAS_DATE_COVERAGE_AUDIT"

Si no tienes grib_ls en PATH, el script intenta localizarlo en rutas típicas de OSGeo4W/Miniforge.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional


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


def find_executable(name: str) -> Optional[str]:
    hit = shutil.which(name)
    if hit:
        return hit
    candidates = [
        Path(r"C:\OSGeo4W64\bin") / name,
        Path(r"C:\OSGeo4W\bin") / name,
        Path(r"C:\ProgramData\miniforge3\Library\bin") / name,
        Path(r"C:\ProgramData\Miniforge3\Library\bin") / name,
        Path(r"C:\Users") / os.environ.get("USERNAME", "") / "miniforge3" / "Library" / "bin" / name,
        Path(r"C:\Users") / os.environ.get("USERNAME", "") / "mambaforge" / "Library" / "bin" / name,
    ]
    if os.name == "nt" and not name.lower().endswith(".exe"):
        candidates += [c.with_suffix(".exe") for c in candidates]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def expected_min_days(year: int, month: int) -> int:
    # Regla conservadora pedida: al menos 29 días por mes, con consideración real para febrero.
    # Para febrero se exige lo que el calendario permite: 28 o 29.
    days = calendar.monthrange(year, month)[1]
    return min(days, 29)


def parse_date_token(token: str) -> Optional[str]:
    token = str(token).strip()
    if not token or token in {"-", "MISSING", "missing", "None", "nan"}:
        return None
    token = re.sub(r"\D", "", token)
    if len(token) >= 8:
        yyyy = int(token[:4])
        mm = int(token[4:6])
        dd = int(token[6:8])
        if 1900 <= yyyy <= 2100 and 1 <= mm <= 12 and 1 <= dd <= 31:
            try:
                return dt.date(yyyy, mm, dd).isoformat()
            except ValueError:
                return None
    return None


def infer_year_from_path(path: Path) -> Optional[int]:
    text = str(path)
    years = [int(y) for y in re.findall(r"(20[12]\d)", text)]
    years = [y for y in years if y in YEARS]
    if years:
        return years[-1]
    return None


def is_gfas_candidate(path: Path) -> bool:
    text = str(path)
    return path.suffix.lower() in GRIB_EXTS and any(h in text for h in GFAS_HINTS)


def inventory_gribs(roots: Iterable[Path]) -> list[Path]:
    out = []
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if is_gfas_candidate(p):
                key = str(p).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def run_grib_ls(grib_ls: str, path: Path, only_pm2p5: bool = True, timeout: int = 240) -> tuple[int, str, str, list[str]]:
    # Primero intentamos filtrar shortName conocido. Si no devuelve nada útil, el caller hará fallback sin filtro.
    cmd = [
        grib_ls,
        "-p",
        "shortName,name,paramId,dataDate,dataTime,validityDate,validityTime",
    ]
    if only_pm2p5:
        cmd += ["-w", "shortName=pm2p5fire/shortName=pm2p5/shortName=pm2p5fire"]
    cmd.append(str(path))
    try:
        cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        lines = [ln.rstrip("\n") for ln in cp.stdout.splitlines()]
        return cp.returncode, cp.stdout, cp.stderr, lines
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", e.stderr or f"TIMEOUT after {timeout}s", []


def extract_dates_from_grib_ls_lines(lines: list[str], prefer_pm2p5: bool = True) -> tuple[set[str], int, list[str]]:
    dates: set[str] = set()
    parsed_rows = 0
    sample_rows = []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(("shortname", "name ", "paramid", "dataDate".lower())):
            continue
        if low.startswith(("count=", "total=", "grib_ls", "edition", "file")):
            continue
        if "messages in" in low or "of them" in low:
            continue

        # Filtra preferentemente PM2P5FIRE, pero deja pasar si el caller ya filtró y no aparece texto.
        if prefer_pm2p5 and not any(tok in low for tok in ["pm2p5", "particulate", "aerosol"]):
            # A veces la línea incluye solo dataDate por efecto de -w; no la descartamos si tiene fecha clara.
            if not re.search(r"\b20[12]\d[01]\d[0-3]\d\b", s):
                continue

        found = re.findall(r"\b(20[12]\d[01]\d[0-3]\d)\b", s)
        if found:
            # validityDate, si existe, suele ser última fecha; dataDate también vale para diario.
            d = parse_date_token(found[-1])
            if d:
                dates.add(d)
                parsed_rows += 1
                if len(sample_rows) < 8:
                    sample_rows.append(s)
    return dates, parsed_rows, sample_rows


def dates_from_grib_metadata(path: Path, grib_ls: Optional[str]) -> dict:
    result = {
        "file": norm_path(path),
        "year_inferred": infer_year_from_path(path),
        "method": "",
        "dates": set(),
        "message_rows_parsed": 0,
        "error": "",
        "sample_rows": [],
    }
    if not grib_ls:
        result["method"] = "NO_GRIB_LS_AVAILABLE"
        result["error"] = "No se encontró grib_ls/ecCodes; solo se puede inventariar nombres, no fechas internas."
        return result

    # Intento 1: filtro PM2P5FIRE.
    rc, stdout, stderr, lines = run_grib_ls(grib_ls, path, only_pm2p5=True)
    dates, nrows, sample = extract_dates_from_grib_ls_lines(lines, prefer_pm2p5=False)
    if dates:
        result.update(method="grib_ls_filtered_pm2p5", dates=dates, message_rows_parsed=nrows, sample_rows=sample)
        if rc != 0:
            result["error"] = stderr.strip()
        return result

    # Intento 2: sin filtro; puede ser más lento, pero solo metadata.
    rc2, stdout2, stderr2, lines2 = run_grib_ls(grib_ls, path, only_pm2p5=False)
    dates2, nrows2, sample2 = extract_dates_from_grib_ls_lines(lines2, prefer_pm2p5=True)
    result.update(method="grib_ls_unfiltered_metadata", dates=dates2, message_rows_parsed=nrows2, sample_rows=sample2)
    if not dates2:
        result["error"] = (stderr2 or stderr or "No se pudieron extraer fechas PM2P5FIRE desde grib_ls.").strip()
    return result


def summarize_year_month(dates_by_file: dict[str, set[str]]) -> dict[int, dict[int, set[str]]]:
    ym: dict[int, dict[int, set[str]]] = {y: {m: set() for m in range(1, 13)} for y in YEARS}
    for dates in dates_by_file.values():
        for d in dates:
            try:
                obj = dt.date.fromisoformat(d)
            except ValueError:
                continue
            if obj.year in ym:
                ym[obj.year][obj.month].add(d)
    return ym


def read_runtime_dates(runtime_output: Optional[Path]) -> dict:
    result = {
        "runtime_root": "",
        "runtime_dates": set(),
        "runtime_year_month": {},
        "files_checked": [],
        "error": "",
    }
    if not runtime_output:
        return result
    root = runtime_output
    # Acepta wrapper o 03_outputs.
    if (root / "03_outputs").exists():
        root = root / "03_outputs"
    result["runtime_root"] = norm_path(root)
    candidates = [
        root / "tables" / "smoke_day_score_nuts3_daily.csv",
        root / "tables" / "smoke_day_score_municipio_daily.csv",
        root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv",
        root / "qa" / "smoke_route_audit.tsv",
    ]
    dates = set()
    checked = []
    for p in candidates:
        if not p.exists():
            continue
        checked.append(norm_path(p))
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            result["error"] += f"ERROR reading {p}: {e}\n"
            continue
        # Extrae ISO dates y YYYYMMDD por si están en auditorías.
        for m in re.findall(r"\b(20[12]\d-[01]\d-[0-3]\d)\b", text):
            try:
                dates.add(dt.date.fromisoformat(m).isoformat())
            except ValueError:
                pass
        for m in re.findall(r"\b(20[12]\d[01]\d[0-3]\d)\b", text):
            d = parse_date_token(m)
            if d:
                dates.add(d)
    result["files_checked"] = checked
    result["runtime_dates"] = dates
    result["runtime_year_month"] = summarize_year_month({"runtime": dates})
    return result


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", required=True, help="Raíces de datos a escanear.")
    ap.add_argument("--runtime-output", default="", help="Runtime o 03_outputs opcional para comparar fechas usadas por el pipeline.")
    ap.add_argument("--out", required=True, help="Carpeta de salida del reporte.")
    ap.add_argument("--grib-ls", default="", help="Ruta explícita a grib_ls.exe si no está en PATH.")
    ap.add_argument("--timeout-per-file", type=int, default=240)
    args = ap.parse_args()

    roots = [Path(x) for x in args.roots]
    out = Path(args.out)
    ensure_dir(out)

    grib_ls = args.grib_ls or find_executable("grib_ls")
    gribs = inventory_gribs(roots)

    inventory_rows = []
    for p in gribs:
        try:
            size = p.stat().st_size
            mtime = dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            size = ""
            mtime = ""
        inventory_rows.append({
            "file": norm_path(p),
            "year_inferred": infer_year_from_path(p) or "",
            "size_bytes": size,
            "modified": mtime,
            "root_match": next((norm_path(r) for r in roots if str(p).lower().startswith(str(r).lower())), ""),
        })

    write_tsv(out / "gfas_grib_file_inventory.tsv", inventory_rows,
              ["file", "year_inferred", "size_bytes", "modified", "root_match"])

    file_coverage_rows = []
    dates_by_file: dict[str, set[str]] = {}
    errors = []
    samples = []

    for i, p in enumerate(gribs, start=1):
        res = dates_from_grib_metadata(p, grib_ls)
        dates = set(res["dates"])
        dates_by_file[norm_path(p)] = dates
        months = sorted({dt.date.fromisoformat(d).month for d in dates}) if dates else []
        years = sorted({dt.date.fromisoformat(d).year for d in dates}) if dates else []
        file_coverage_rows.append({
            "file": norm_path(p),
            "year_inferred": res.get("year_inferred") or "",
            "metadata_method": res.get("method", ""),
            "date_count": len(dates),
            "year_values": ",".join(str(y) for y in years),
            "month_values": ",".join(f"{m:02d}" for m in months),
            "min_date": min(dates) if dates else "",
            "max_date": max(dates) if dates else "",
            "message_rows_parsed": res.get("message_rows_parsed", 0),
            "error": res.get("error", ""),
        })
        if res.get("error"):
            errors.append({"file": norm_path(p), "error": res.get("error", "")})
        for s in res.get("sample_rows", []):
            samples.append({"file": norm_path(p), "sample_grib_ls_row": s})

    write_tsv(out / "gfas_grib_date_coverage_by_file.tsv", file_coverage_rows,
              ["file", "year_inferred", "metadata_method", "date_count", "year_values", "month_values",
               "min_date", "max_date", "message_rows_parsed", "error"])
    write_tsv(out / "gfas_grib_metadata_errors.tsv", errors, ["file", "error"])
    write_tsv(out / "gfas_grib_ls_sample_rows.tsv", samples, ["file", "sample_grib_ls_row"])

    ym = summarize_year_month(dates_by_file)
    ym_rows = []
    for y in YEARS:
        for m in range(1, 13):
            cnt = len(ym[y][m])
            exp = expected_min_days(y, m)
            ym_rows.append({
                "source": "RAW_GRIB_METADATA",
                "year": y,
                "month": f"{m:02d}",
                "unique_dates": cnt,
                "expected_min_dates": exp,
                "calendar_days": calendar.monthrange(y, m)[1],
                "status": "PASS" if cnt >= exp else "FAIL",
                "first_date": min(ym[y][m]) if ym[y][m] else "",
                "last_date": max(ym[y][m]) if ym[y][m] else "",
            })

    runtime = read_runtime_dates(Path(args.runtime_output) if args.runtime_output else None)
    if runtime.get("runtime_dates"):
        runtime_ym = runtime["runtime_year_month"]
        for y in YEARS:
            for m in range(1, 13):
                cnt = len(runtime_ym[y][m])
                exp = expected_min_days(y, m)
                ym_rows.append({
                    "source": "RUNTIME_USED_DATES",
                    "year": y,
                    "month": f"{m:02d}",
                    "unique_dates": cnt,
                    "expected_min_dates": exp,
                    "calendar_days": calendar.monthrange(y, m)[1],
                    "status": "PASS" if cnt >= exp else "FAIL",
                    "first_date": min(runtime_ym[y][m]) if runtime_ym[y][m] else "",
                    "last_date": max(runtime_ym[y][m]) if runtime_ym[y][m] else "",
                })

    write_tsv(out / "gfas_coverage_by_year_month.tsv", ym_rows,
              ["source", "year", "month", "unique_dates", "expected_min_dates", "calendar_days", "status", "first_date", "last_date"])

    # Decisión por año.
    decision_rows = []
    for y in YEARS:
        raw_counts = [len(ym[y][m]) for m in range(1, 13)]
        raw_months_pass = sum(1 for m in range(1, 13) if len(ym[y][m]) >= expected_min_days(y, m))
        raw_months_present = sum(1 for m in range(1, 13) if len(ym[y][m]) > 0)
        raw_total = sum(raw_counts)
        raw_min = min([d for m in range(1, 13) for d in ym[y][m]], default="")
        raw_max = max([d for m in range(1, 13) for d in ym[y][m]], default="")
        runtime_total = ""
        runtime_months_present = ""
        runtime_months_pass = ""
        if runtime.get("runtime_dates"):
            rym = runtime["runtime_year_month"]
            runtime_total = sum(len(rym[y][m]) for m in range(1, 13))
            runtime_months_present = sum(1 for m in range(1, 13) if len(rym[y][m]) > 0)
            runtime_months_pass = sum(1 for m in range(1, 13) if len(rym[y][m]) >= expected_min_days(y, m))

        if raw_months_pass == 12:
            if runtime.get("runtime_dates") and runtime_months_pass != 12:
                decision = "RAW_DATA_FULL_YEAR_BUT_RUNTIME_LIMITED_OR_DOWNSAMPLED"
            else:
                decision = "RAW_DATA_FULL_YEAR_COVERAGE_PASS"
        elif raw_months_present <= 4 and raw_max and raw_max[5:7] in {"03", "04"}:
            decision = "RAW_GRIB_APPEARS_JAN_APR_TRUNCATED_OR_ONLY_EARLY_YEAR"
        elif raw_total == 0:
            decision = "NO_DATES_EXTRACTED_NEED_GRIB_TOOL_OR_DIFFERENT_METADATA"
        else:
            decision = "RAW_GRIB_PARTIAL_YEAR_COVERAGE"
        decision_rows.append({
            "year": y,
            "raw_unique_dates": raw_total,
            "raw_months_present": raw_months_present,
            "raw_months_pass_min_rule": raw_months_pass,
            "raw_min_date": raw_min,
            "raw_max_date": raw_max,
            "runtime_unique_dates": runtime_total,
            "runtime_months_present": runtime_months_present,
            "runtime_months_pass_min_rule": runtime_months_pass,
            "decision": decision,
        })

    write_tsv(out / "gfas_coverage_decision_by_year.tsv", decision_rows,
              ["year", "raw_unique_dates", "raw_months_present", "raw_months_pass_min_rule",
               "raw_min_date", "raw_max_date", "runtime_unique_dates", "runtime_months_present",
               "runtime_months_pass_min_rule", "decision"])

    overall = Counter(row["decision"] for row in decision_rows)
    raw_all_full = all(row["decision"] in {"RAW_DATA_FULL_YEAR_COVERAGE_PASS", "RAW_DATA_FULL_YEAR_BUT_RUNTIME_LIMITED_OR_DOWNSAMPLED"} for row in decision_rows)
    any_runtime_limited = any(row["decision"] == "RAW_DATA_FULL_YEAR_BUT_RUNTIME_LIMITED_OR_DOWNSAMPLED" for row in decision_rows)
    all_jan_apr = all(row["decision"] == "RAW_GRIB_APPEARS_JAN_APR_TRUNCATED_OR_ONLY_EARLY_YEAR" for row in decision_rows)

    if raw_all_full and any_runtime_limited:
        final_decision = "DATA_FULL_YEAR_PIPELINE_LIMITED_OR_DOWNSAMPLED"
    elif raw_all_full:
        final_decision = "DATA_FULL_YEAR_AVAILABLE"
    elif all_jan_apr:
        final_decision = "RAW_GFAS_FILES_APPEAR_JAN_APR_ONLY"
    elif not grib_ls:
        final_decision = "CANNOT_VERIFY_INTERNAL_GRIB_DATES_NO_GRIB_LS"
    else:
        final_decision = "MIXED_OR_PARTIAL_GFAS_COVERAGE_REQUIRES_REVIEW"

    report = []
    report.append("# GFAS GRIB month/date coverage audit")
    report.append("")
    report.append(f"- generated: {dt.datetime.now().isoformat(timespec='seconds')}")
    report.append(f"- grib_ls: {grib_ls or 'NOT FOUND'}")
    report.append(f"- roots scanned:")
    for r in roots:
        report.append(f"  - {norm_path(r)} | exists={r.exists()}")
    report.append(f"- grib_candidates_found: {len(gribs)}")
    report.append(f"- runtime_output_checked: {runtime.get('runtime_root','')}")
    report.append(f"- runtime_files_checked: {len(runtime.get('files_checked', []))}")
    report.append("")
    report.append(f"## FINAL_DECISION: `{final_decision}`")
    report.append("")
    report.append("## Decision counts")
    for k, v in sorted(overall.items()):
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Year decisions")
    report.append("")
    report.append("| year | raw_dates | raw_months_present | raw_months_pass | raw_min | raw_max | runtime_dates | runtime_months_present | decision |")
    report.append("|---:|---:|---:|---:|---|---|---:|---:|---|")
    for row in decision_rows:
        report.append(
            f"| {row['year']} | {row['raw_unique_dates']} | {row['raw_months_present']} | {row['raw_months_pass_min_rule']} | "
            f"{row['raw_min_date']} | {row['raw_max_date']} | {row['runtime_unique_dates']} | {row['runtime_months_present']} | {row['decision']} |"
        )
    report.append("")
    report.append("## Interpretation")
    report.append("")
    report.append("- If `RAW_DATA_FULL_YEAR_BUT_RUNTIME_LIMITED_OR_DOWNSAMPLED`: the raw GFAS files contain broad annual coverage, but the runtime/pipeline used fewer months/dates.")
    report.append("- If `RAW_GRIB_APPEARS_JAN_APR_TRUNCATED_OR_ONLY_EARLY_YEAR`: the actual inspected GRIB metadata only exposes early-year dates, so the data download/source is likely incomplete or contains a limited product.")
    report.append("- If `NO_DATES_EXTRACTED`: install/use ecCodes `grib_ls` or pass `--grib-ls` explicitly.")
    report.append("")
    (out / "GFAS_GRIB_DATE_COVERAGE_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    print(f"FINAL_DECISION={final_decision}")
    print(f"REPORT={out / 'GFAS_GRIB_DATE_COVERAGE_REPORT.md'}")
    print(f"OUT_DIR={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
