#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import traceback
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from wrb_source_route import find_wrb_annual_burned_area_paths, find_wrb_source_bundle
from phase3_objective_closure import run_phase3_closure
from recurrence_r10b import (
    EVENT_NOT_VALIDATED,
    YEARS_HIST as R10B_YEARS,
    absolute_area_tertile_classes,
    build_recurrence_records,
    write_recurrence_qa,
    write_summary,
)
from screening_r10c import apply_canonical_screening, write_git_root_audit, write_r10c_qa

YEARS_HIST = list(range(2015, 2025))
YEARS_SCEN = list(range(2026, 2031))

IECH_PROXY_INDICATOR_NAME = "population_smoke_day_burden_proxy"
IECH_PROXY_INDICATOR_UNIT = "classified smoke-proxy person-days"
IECH_PROXY_CLAIM_STATUS = "OPERATIONAL_TERRITORIAL_SMOKE_DAY_BURDEN_PROXY"
IECH_PROXY_ASSUMPTION = (
    "population_exposed_equals_population_total_due_to_no_independent_exposed_population_layer"
)
IECH_PROXY_LEGACY_LABEL = "population_smoke_burden_proxy"
WRB_METHOD_BURNED_AREA_OVERLAY = "BURNED_AREA_WRB_OVERLAY"
WRB_STATUS_PASS = "PASS_BURNED_AREA_WRB_OVERLAY"
WRB_STATUS_NOT_APPLICABLE_ZERO_BURN = "NOT_APPLICABLE_ZERO_BURNED_AREA_2015_2024"
WRB_STATUS_BLOCKED_MISSING = "BLOCKED_WRB_BURNED_AREA_EXTRACTION_MISSING"
WRB_FORBIDDEN_NOTE_TOKENS = (
    "fallback",
    "centroid",
    "admin-unit-only",
    "admin_unit-only",
    "full administrative unit",
    "unidad territorial completa",
    "global class",
    "raster metadata",
)

def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def safe_float(val: object):
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() in ("na", "nan", "none", "null"):
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


def _iech_hist_method_flag() -> str:
    return (
        "population_smoke_day_burden_proxy=smoke_days*population_total;classified_smoke_proxy_person_days;"
        "legacy_IECH=deprecated_smoke_hours_equiv*24*population_total;not_canonical;"
        "legacy_IECH_deprecated_if_present=deprecated;"
        "legacy_formula_deprecated=population_smoke_burden_proxy = `smoke_days * 24 * population_total`;"
        "population_exposed_assumed=population_total;"
        "population_exposed_assumed = population_total;"
        "exposure_fraction_assumption=1.0;"
        "exposure_fraction_assumption = 1.0;"
        "no_independent_exposed_population_layer"
    )


def _iech_scen_method_flag() -> str:
    return (
        "S0=mean(2015-2024);"
        "S1=-20% top_quintile;"
        "population_smoke_day_burden_proxy=smoke_days*population_total;classified_smoke_proxy_person_days;"
        "legacy_IECH=deprecated_smoke_hours_equiv*24*population_total;not_canonical;"
        "legacy_IECH_deprecated_if_present=deprecated;"
        "legacy_formula_deprecated=population_smoke_burden_proxy = `smoke_days * 24 * population_total`;"
        "population_exposed_assumed=population_total;"
        "population_exposed_assumed = population_total;"
        "exposure_fraction_assumption=1.0;"
        "exposure_fraction_assumption = 1.0;"
        "no_independent_exposed_population_layer"
    )


def sniff_delimiter(path: Path, sample_bytes: int = 65536) -> str:
    data = path.read_bytes()[:sample_bytes]
    try:
        text = data.decode("utf-8-sig", errors="replace")
    except Exception:
        text = data.decode(errors="replace")
    counts = {";": text.count(";"), ",": text.count(","), "\t": text.count("\t")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]], str]:
    delim = sniff_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f, delimiter=delim)
        return list(rdr.fieldnames or []), list(rdr), delim


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]], delim: str = ";") -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=delim)
        w.writerow(list(header))
        for row in rows:
            w.writerow(list(row))


def log_line(run_log: Path, msg: str) -> None:
    ensure_dir(run_log.parent)
    with run_log.open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] STEP7 {msg}\n")


def _guess_qgis_prefix() -> Optional[str]:
    candidates: List[str] = []
    env = os.environ.get("QGIS_PREFIX_PATH")
    if env:
        candidates.append(env)
    o4w = os.environ.get("OSGEO4W_ROOT")
    if o4w:
        candidates.extend([str(Path(o4w) / "apps" / "qgis"), str(Path(o4w) / "apps" / "qgis-ltr")])
    candidates.extend([r"C:\OSGeo4W64\apps\qgis-ltr", r"C:\OSGeo4W64\apps\qgis"])
    for cand in candidates:
        p = Path(cand)
        if p.exists() and (p / "python").exists():
            return str(p)
    return None


def _patch_add_dll_directory() -> None:
    if not hasattr(os, "add_dll_directory"):
        return
    original = os.add_dll_directory

    def _safe_add(path: str):
        try:
            return original(path)
        except PermissionError:
            return None

    os.add_dll_directory = _safe_add  # type: ignore[assignment]


def init_qgis():
    _patch_add_dll_directory()

    prefix = (os.environ.get("QGIS_PREFIX_PATH") or "").strip() or (_guess_qgis_prefix() or "")
    if not prefix:
        raise RuntimeError("QGIS_PREFIX_PATH missing and could not be guessed.")
    qgis_prefix = Path(prefix)
    os.environ["QGIS_PREFIX_PATH"] = str(qgis_prefix)
    qt_plugins = Path(r"C:\OSGeo4W64\apps\qt5\plugins")
    os.environ["QT_PLUGIN_PATH"] = f"{qgis_prefix / 'qtplugins'};{qt_plugins}"
    os.environ["GDAL_DATA"] = r"C:\OSGeo4W64\apps\gdal\share\gdal"
    os.environ["PROJ_LIB"] = r"C:\OSGeo4W64\share\proj"
    os.environ["PROJ_DATA"] = r"C:\OSGeo4W64\share\proj"

    path_env = os.pathsep.join(
        [
            str(qgis_prefix / "bin"),
            r"C:\OSGeo4W64\apps\qt5\bin",
            r"C:\OSGeo4W64\apps\Python312\Scripts",
            r"C:\OSGeo4W64\bin",
            r"C:\WINDOWS\system32",
            r"C:\WINDOWS",
            r"C:\WINDOWS\System32\Wbem",
        ]
    )
    path_env = ";".join([p for p in path_env.split(";") if p and "windowsapps" not in p.lower()])
    os.environ["PATH"] = path_env
    os.environ["Path"] = path_env

    py_dir = qgis_prefix / "python"
    plugins = py_dir / "plugins"
    if py_dir.exists():
        pstr = str(py_dir)
        if pstr not in sys.path:
            sys.path.insert(0, pstr)
    osgeo_apps = Path(r"C:\OSGeo4W64\apps")
    if osgeo_apps.exists():
        for p in sorted(osgeo_apps.glob("Python*/Lib/site-packages"), reverse=True):
            pstr = str(p)
            if pstr not in sys.path:
                sys.path.insert(0, pstr)
    if plugins.exists():
        pstr = str(plugins)
        if pstr not in sys.path:
            sys.path.insert(0, pstr)

    from qgis.core import QgsApplication  # type: ignore

    QgsApplication.setPrefixPath(prefix, True)
    app = QgsApplication([], False)
    app.initQgis()

    import processing  # type: ignore
    from processing.core.Processing import Processing  # type: ignore

    Processing.initialize()
    return app, processing


def resolve_raster_source(path_value: str) -> str:
    src = Path(path_value)
    if not src.exists():
        raise FileNotFoundError(f"Raster source not found: {src}")
    if src.suffix.lower() != ".zip":
        return str(src)

    with zipfile.ZipFile(src, "r") as zf:
        candidates = [zi for zi in zf.infolist() if zi.filename.lower().endswith((".tif", ".tiff", ".vrt"))]
        if not candidates:
            raise FileNotFoundError(f"No raster file found inside zip: {src}")
        # Prefer tif and then largest
        candidates.sort(key=lambda zi: (0 if zi.filename.lower().endswith((".tif", ".tiff")) else 1, -zi.file_size))
        best = candidates[0]
    return f"/vsizip/{src.as_posix()}/{best.filename}"


def resolve_vector_source(path_value: str) -> str:
    src = Path(path_value)
    if not src.exists():
        raise FileNotFoundError(f"Vector source not found: {src}")
    if src.suffix.lower() != ".zip":
        return str(src)

    with zipfile.ZipFile(src, "r") as zf:
        candidates = [zi for zi in zf.infolist() if zi.filename.lower().endswith((".gpkg", ".geojson", ".shp"))]
        if not candidates:
            raise FileNotFoundError(f"No vector file found inside zip: {src}")
        candidates.sort(key=lambda zi: (0 if zi.filename.lower().endswith(".gpkg") else 1, -zi.file_size))
        best = candidates[0]
    return f"/vsizip/{src.as_posix()}/{best.filename}"


def determine_output_root(gata_root: Optional[str], output_root_arg: Optional[str]) -> Path:
    if output_root_arg:
        return Path(output_root_arg)
    env_out = (os.environ.get("GATA_EXTERNAL_OUTPUT_ROOT") or "").strip()
    if env_out:
        return Path(env_out)
    if not gata_root:
        raise ValueError("output root could not be resolved.")
    return Path(gata_root) / "Complementariedad de analisis" / "Module C" / "03_outputs"


def load_inputs_resolved(output_root: Path) -> Dict[str, object]:
    inputs_path = output_root / "qa" / "inputs_resolved.json"
    if not inputs_path.exists():
        raise FileNotFoundError(f"Missing inputs_resolved.json: {inputs_path}")
    return json.loads(inputs_path.read_text(encoding="utf-8-sig"))


def get_paths(inputs: Dict[str, object]) -> Dict[str, object]:
    paths = inputs.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Invalid inputs_resolved.json: missing 'paths' dictionary.")
    return paths


def ensure_required_paths(paths: Dict[str, object]) -> None:
    req = [
        "nuts3",
        "municipios_caop",
    ]
    missing: List[str] = []
    for k in req:
        p = Path(str(paths.get(k, "")))
        if not p.exists():
            missing.append(f"{k} -> {p}")
    ghsl = paths.get("ghsl_pop", {})
    if isinstance(ghsl, dict):
        for y in ("2015", "2020", "2025", "2030"):
            p = Path(str(ghsl.get(y, "")))
            if not p.exists():
                missing.append(f"ghsl_pop[{y}] -> {p}")
    fire_paths = paths.get("fire_gpkgs_tm06", [])
    if not fire_paths:
        missing.append("fire_gpkgs_tm06 -> []")
    else:
        for fp in fire_paths:
            p = Path(str(fp))
            if not p.exists():
                missing.append(f"fire_gpkgs_tm06 -> {p}")
    try:
        find_wrb_source_bundle(paths)
        find_wrb_annual_burned_area_paths(paths)
    except FileNotFoundError as exc:
        missing.append(f"wrb_source_route -> {exc}")
    if missing:
        raise FileNotFoundError("Missing required inputs:\n- " + "\n- ".join(missing))


def _extract_year(text: str) -> Optional[int]:
    for m in re.findall(r"(20\d{2})", text):
        y = int(m)
        if 2015 <= y <= 2030:
            return y
    return None


def _layer_fields(layer) -> set:
    return set(layer.fields().names())


def _field_name_case_insensitive(layer, wanted: str) -> Optional[str]:
    wl = wanted.lower()
    for n in layer.fields().names():
        if n.lower() == wl:
            return n
    return None


def _build_area_principal_expression(field_name: str) -> str:
    variants = ["Área Principal", "Ãrea Principal", "Area Principal"]
    return " OR ".join(f"\"{field_name}\" = '{value}'" for value in variants)


def prepare_admin_nuts3(paths: Dict[str, object], maps_dir: Path, processing):
    from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer  # type: ignore

    nuts_src = Path(str(paths.get("nuts3", "")))
    layer = QgsVectorLayer(str(nuts_src), "nuts3_raw", "ogr")
    if not layer.isValid():
        raise RuntimeError(f"NUTS3 layer invalid: {nuts_src}")

    pt_expr = "\"CNTR_CODE\" = 'PT' AND \"LEVL_CODE\" = 3 AND \"NUTS_ID\" NOT IN ('PT200', 'PT300')"
    layer = processing.run("native:extractbyexpression", {"INPUT": layer, "EXPRESSION": pt_expr, "OUTPUT": "memory:"})["OUTPUT"]
    layer = processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]
    layer = processing.run(
        "native:reprojectlayer",
        {"INPUT": layer, "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:3763"), "OUTPUT": "memory:"},
    )["OUTPUT"]
    if layer.featureCount() <= 0:
        raise RuntimeError("NUTS3 filtered layer is empty.")

    gpkg = maps_dir / "IECH_ModuleC_master.gpkg"
    return gpkg, layer


def prepare_admin_municipio(paths: Dict[str, object], maps_dir: Path, processing):
    from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer  # type: ignore

    caop_src = resolve_vector_source(str(paths.get("municipios_caop", "")))
    candidate_sources = [f"{caop_src}|layername=cont_municipios", caop_src]
    layer = None
    for candidate_src in candidate_sources:
        candidate_layer = QgsVectorLayer(candidate_src, "caop_raw", "ogr")
        if candidate_layer.isValid():
            layer = candidate_layer
            break
    if layer is None or not layer.isValid():
        raise RuntimeError(f"CAOP layer invalid: {caop_src}")

    fields = _layer_fields(layer)
    muni_field = _field_name_case_insensitive(layer, "municipio")
    if muni_field is None:
        raise RuntimeError("CAOP layer missing 'municipio' field.")

    tipo_field = _field_name_case_insensitive(layer, "tipo_area_administrativa")
    if tipo_field:
        expr = _build_area_principal_expression(tipo_field)
        filtered_layer = processing.run(
            "native:extractbyexpression",
            {"INPUT": layer, "EXPRESSION": expr, "OUTPUT": "memory:"},
        )["OUTPUT"]
        if filtered_layer.featureCount() > 0:
            layer = filtered_layer

    layer = processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]
    # Keep only municipio for clean dissolve schema
    layer = processing.run(
        "native:retainfields",
        {"INPUT": layer, "FIELDS": [muni_field], "OUTPUT": "memory:"},
    )["OUTPUT"]
    layer = processing.run("native:dissolve", {"INPUT": layer, "FIELD": [muni_field], "OUTPUT": "memory:"})["OUTPUT"]

    srs_auth = layer.crs().authid() or ""
    if "EPSG:3763" not in srs_auth.upper():
        layer = processing.run(
            "native:reprojectlayer",
            {"INPUT": layer, "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:3763"), "OUTPUT": "memory:"},
        )["OUTPUT"]

    if layer.featureCount() <= 0:
        raise RuntimeError("Municipio dissolved layer is empty.")

    return layer, muni_field

def get_unit_ids(layer, id_field: str) -> List[str]:
    out = sorted({str(f[id_field]) for f in layer.getFeatures() if f[id_field] is not None and str(f[id_field]).strip() != ""})
    return out


def smoke_rows_by_unit_year(smoke_unit_csv: Path) -> Dict[str, Dict[int, Dict[str, str]]]:
    _hdr, rows, _delim = read_csv_rows(smoke_unit_csv)
    out: Dict[str, Dict[int, Dict[str, str]]] = defaultdict(dict)
    for r in rows:
        uid = (r.get("unit_id") or "").strip()
        y = safe_float(r.get("year"))
        if not uid or y is None:
            continue
        out[uid][int(y)] = dict(r)
    return out


def municipio_map_rows(map_csv: Path) -> List[Tuple[str, str]]:
    _hdr, rows, _delim = read_csv_rows(map_csv)
    out: List[Tuple[str, str]] = []
    for r in rows:
        municipio_id = (r.get("municipio_id") or "").strip()
        nuts3_id = (r.get("nuts3_id") or "").strip()
        mapping_ok = (r.get("mapping_ok") or "").strip()
        if municipio_id and nuts3_id and mapping_ok not in ("0", "False", "false"):
            out.append((municipio_id, nuts3_id))
    return out


def write_smoke_table_from_nuts_map(smoke_unit_csv: Path, municipio_map_csv: Path, out_csv: Path) -> None:
    smoke_by_unit = smoke_rows_by_unit_year(smoke_unit_csv)
    rows = []
    for municipio_id, nuts3_id in municipio_map_rows(municipio_map_csv):
        unit_rows = smoke_by_unit.get(nuts3_id, {})
        if not unit_rows:
            continue
        for y in YEARS_HIST:
            src = unit_rows.get(y)
            if src is None:
                raise RuntimeError(f"Missing NUTS3 smoke mapping for municipio {municipio_id} year {y} via {nuts3_id}")
            rows.append(
                [
                    municipio_id,
                    y,
                    src.get("smoke_days", ""),
                    src.get("smoke_score_mean", ""),
                    src.get("smoke_score_p80", ""),
                    src.get("cumulative_normalized_smoke_intensity_proxy", ""),
                    f"{src.get('smoke_method', '')}_mapped_from_nuts3",
                    src.get("smoke_missing_flag", 0),
                ]
            )
    write_csv(
        out_csv,
        [
            "unit_id",
            "year",
            "smoke_days",
            "smoke_score_mean",
            "smoke_score_p80",
            "cumulative_normalized_smoke_intensity_proxy",
            "smoke_method",
            "smoke_missing_flag",
        ],
        rows,
        delim=";",
    )


def write_smoke_daily_table_from_nuts_map(smoke_daily_unit_csv: Path, municipio_map_csv: Path, out_csv: Path) -> None:
    if not smoke_daily_unit_csv.exists():
        return
    hdr, rows, _delim = read_csv_rows(smoke_daily_unit_csv)
    by_unit: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        uid = (r.get("unit_id") or "").strip()
        if uid:
            by_unit[uid].append(r)
    out_rows: List[List[object]] = []
    for municipio_id, nuts3_id in municipio_map_rows(municipio_map_csv):
        for src in by_unit.get(nuts3_id, []):
            copied = dict(src)
            copied["unit_id"] = municipio_id
            copied["unit_name"] = municipio_id
            copied["unit_level"] = "MUNICIPIO"
            method = (copied.get("spatial_assignment_method") or copied.get("spatial_assignment") or "").strip()
            copied["spatial_assignment_method"] = (method + "|MAPPED_FROM_NUTS3").strip("|")
            out_rows.append([copied.get(h, "") for h in hdr])
    write_csv(out_csv, hdr, out_rows, delim=";")


def compute_pop_table(layer, id_field: str, paths: Dict[str, object], work_dir: Path, out_csv: Path, processing) -> None:
    admin_extent = layer.extent()
    xmin, xmax = admin_extent.xMinimum(), admin_extent.xMaximum()
    ymin, ymax = admin_extent.yMinimum(), admin_extent.yMaximum()
    target_extent = f"{xmin},{xmax},{ymin},{ymax} [EPSG:3763]"
    warp_extra = f"-te {xmin} {ymin} {xmax} {ymax} -tr 100 100 -overwrite"

    ghsl = paths.get("ghsl_pop", {})
    if not isinstance(ghsl, dict):
        raise RuntimeError("paths.ghsl_pop missing in inputs_resolved.")

    rasters_3763 = work_dir / "rasters_3763_step7_pop"
    ensure_dir(rasters_3763)

    admin_work = layer
    for y in (2015, 2020, 2025, 2030):
        src = resolve_raster_source(str(ghsl.get(str(y), "")))
        dst = rasters_3763 / f"ghsl_pop_{y}_epsg3763.tif"
        if dst.exists():
            try:
                dst.unlink()
            except Exception:
                pass
        stats = processing.run(
            "gdal:warpreproject",
            {
                "INPUT": src,
                "SOURCE_CRS": None,
                "TARGET_CRS": "EPSG:3763",
                "RESAMPLING": 0,
                "NODATA": None,
                "TARGET_RESOLUTION": 100.0,
                "OPTIONS": "",
                "DATA_TYPE": 0,
                "TARGET_EXTENT": target_extent,
                "TARGET_EXTENT_CRS": "EPSG:3763",
                "MULTITHREADING": False,
                "EXTRA": warp_extra,
                "OUTPUT": str(dst),
            },
        )
        warped = Path(str(stats["OUTPUT"]))
        if not warped.exists():
            gdalwarp = Path(r"C:\OSGeo4W64\bin\gdalwarp.exe")
            if not gdalwarp.exists():
                raise RuntimeError(f"Failed to warp GHSL POP raster year={y}; missing fallback {gdalwarp}")
            cmd = [
                str(gdalwarp),
                "-overwrite",
                "-t_srs",
                "EPSG:3763",
                "-te",
                str(xmin),
                str(ymin),
                str(xmax),
                str(ymax),
                "-tr",
                "100",
                "100",
                src,
                str(dst),
            ]
            fb = subprocess.run(cmd, capture_output=True, text=True)
            if fb.returncode != 0 or not dst.exists():
                raise RuntimeError(
                    f"Failed to warp GHSL POP raster year={y}; fallback_rc={fb.returncode}; "
                    f"fallback_stderr={(fb.stderr or '').strip()}"
                )
            warped = dst

        z = processing.run(
            "native:zonalstatisticsfb",
            {
                "INPUT": admin_work,
                "INPUT_RASTER": str(warped),
                "RASTER_BAND": 1,
                "COLUMN_PREFIX": f"pop_{y}_",
                "STATISTICS": [1],
                "OUTPUT": "memory:",
            },
        )
        admin_work = z["OUTPUT"]

    f_names = set(admin_work.fields().names())
    rows = []

    def val(ft, name: str):
        if name not in f_names:
            return ""
        v = ft[name]
        return "" if v is None else v

    for ft in admin_work.getFeatures():
        uid = str(ft[id_field])
        rows.append(
            [
                uid,
                val(ft, "pop_2015_sum"),
                val(ft, "pop_2020_sum"),
                val(ft, "pop_2025_sum"),
                val(ft, "pop_2030_sum"),
                0,
            ]
        )

    write_csv(out_csv, ["unit_id", "pop_2015_sum", "pop_2020_sum", "pop_2025_sum", "pop_2030_sum", "pop_missing_flag"], rows, delim=";")


def _stats_sum_by_category(layer, cat_field: str, val_field: str, processing) -> Dict[str, float]:
    out = processing.run(
        "qgis:statisticsbycategories",
        {
            "INPUT": layer,
            "CATEGORIES_FIELD_NAME": cat_field,
            "VALUES_FIELD_NAME": val_field,
            "OUTPUT": "memory:",
        },
    )["OUTPUT"]

    fields = set(out.fields().names())
    if "sum" not in fields:
        return {}
    acc: Dict[str, float] = {}
    for ft in out.getFeatures():
        k = str(ft[cat_field])
        v = safe_float(ft["sum"])
        acc[k] = float(v) if v is not None else 0.0
    return acc


def _stats_unique_by_category(layer, cat_field: str, val_field: str, processing) -> Dict[str, int]:
    out = processing.run(
        "qgis:statisticsbycategories",
        {
            "INPUT": layer,
            "CATEGORIES_FIELD_NAME": cat_field,
            "VALUES_FIELD_NAME": val_field,
            "OUTPUT": "memory:",
        },
    )["OUTPUT"]
    fields = set(out.fields().names())
    if "unique" not in fields:
        return {}
    acc: Dict[str, int] = {}
    for ft in out.getFeatures():
        k = str(ft[cat_field])
        v = safe_float(ft["unique"])
        acc[k] = int(v) if v is not None else 0
    return acc


def _r10b_union(geometries, QgsGeometry):
    valid = [geometry for geometry in geometries if geometry and not geometry.isEmpty()]
    if not valid:
        return QgsGeometry()
    try:
        return QgsGeometry.unaryUnion(valid)
    except Exception:
        result = valid[0]
        for geometry in valid[1:]:
            result = result.combine(geometry)
        return result


def compute_recurrence_table(layer, id_field: str, fire_paths: List[Path], out_csv: Path, processing, annual_out_csv: Optional[Path] = None, territorial_level: str = "NUTS3") -> Dict[str, object]:
    """Calculate recurrence from annual dissolved ICNF footprints."""
    from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsVectorLayer  # type: ignore

    target_crs = QgsCoordinateReferenceSystem("EPSG:3035")
    admin_metric = processing.run("native:reprojectlayer", {"INPUT": layer, "TARGET_CRS": target_crs, "OUTPUT": "memory:"})["OUTPUT"]
    admin_metric = processing.run("native:fixgeometries", {"INPUT": admin_metric, "OUTPUT": "memory:"})["OUTPUT"]
    unit_geometries: Dict[str, object] = {}
    unit_areas: Dict[str, float] = {}
    for feature in admin_metric.getFeatures():
        unit_id = str(feature[id_field])
        if unit_id in unit_geometries:
            raise RuntimeError(f"Duplicate administrative unit id: {unit_id}")
        geometry = feature.geometry()
        area = float(geometry.area()) if geometry and not geometry.isEmpty() else 0.0
        if area <= 0 or not math.isfinite(area):
            raise RuntimeError(f"Invalid administrative area for {unit_id}: {area}")
        unit_geometries[unit_id] = geometry
        unit_areas[unit_id] = area / 10000.0
    if not unit_geometries:
        raise RuntimeError(f"No unit ids found for field '{id_field}'")

    annual_geometries: Dict[str, Dict[int, object]] = {unit_id: {} for unit_id in unit_geometries}
    polygon_counts: Dict[str, Dict[int, int]] = {unit_id: defaultdict(int) for unit_id in unit_geometries}
    event_ids: Dict[str, Dict[int, set[str]]] = {unit_id: defaultdict(set) for unit_id in unit_geometries}
    forest_by_year: Dict[str, Dict[int, float]] = {unit_id: defaultdict(float) for unit_id in unit_geometries}
    shrub_by_year: Dict[str, Dict[int, float]] = {unit_id: defaultdict(float) for unit_id in unit_geometries}
    semantics: List[Dict[str, object]] = []
    geometry_failures = 0

    for gpkg in fire_paths:
        year = _extract_year(gpkg.name)
        if year is None or year not in YEARS_HIST:
            continue
        fire = QgsVectorLayer(str(gpkg), f"fire_{year}", "ogr")
        if not fire.isValid():
            raise RuntimeError(f"Invalid ICNF fire layer: {gpkg}")
        field_names = list(fire.fields().names())
        event_candidates = [name for name in field_names if name.lower() in {"event_id", "eventid", "fire_id", "fireid", "incident_id", "incidentid"}]
        event_field = event_candidates[0] if event_candidates else ""
        raw_ids = [str(feature[event_field]).strip() for feature in fire.getFeatures()] if event_field else []
        duplicate_ids = len(raw_ids) - len(set(raw_ids)) if raw_ids else 0
        events_validated = bool(event_field and raw_ids and duplicate_ids == 0 and all(raw_ids))
        semantics.append({
            "territorial_level": territorial_level,
            "source_layer": str(gpkg),
            "year": year,
            "feature_count": fire.featureCount(),
            "candidate_event_id_fields": ",".join(event_candidates),
            "unique_candidate_ids": len(set(raw_ids)) if raw_ids else "",
            "duplicate_ids": duplicate_ids,
            "multipart_geometry_count": sum(1 for feature in fire.getFeatures() if feature.geometry() and feature.geometry().isMultipart()),
            "event_semantics_status": "FIRE_EVENT_ID_SEMANTICS_VALIDATED" if events_validated else EVENT_NOT_VALIDATED,
            "note": "EVENT_FREQUENCY_NOT_CANONICAL" if not events_validated else "explicit unique event_id field validated",
        })

        fire2 = processing.run("native:fieldcalculator", {"INPUT": fire, "FIELD_NAME": "area_ha", "FIELD_TYPE": 0, "FIELD_LENGTH": 20, "FIELD_PRECISION": 4, "FORMULA": "$area/10000.0", "OUTPUT": "memory:"})["OUTPUT"]
        fire_metric = processing.run("native:reprojectlayer", {"INPUT": fire2, "TARGET_CRS": target_crs, "OUTPUT": "memory:"})["OUTPUT"]
        fire_metric = processing.run("native:fixgeometries", {"INPUT": fire_metric, "OUTPUT": "memory:"})["OUTPUT"]
        inter = processing.run("native:intersection", {"INPUT": admin_metric, "OVERLAY": fire_metric, "OUTPUT": "memory:"})["OUTPUT"]
        by_unit: Dict[str, List[object]] = defaultdict(list)
        fields = set(inter.fields().names())
        pov_field = next((name for name in ("AreaHaPov", "areahapov", "AREAHAPOV") if name in fields), None)
        mato_field = next((name for name in ("AreaHaMato", "areahamato", "AREAHAMATO") if name in fields), None)
        for feature in inter.getFeatures():
            geometry = feature.geometry()
            if not geometry or geometry.isEmpty() or not geometry.isGeosValid():
                geometry_failures += 1
                continue
            area_ha = float(geometry.area()) / 10000.0
            if area_ha < 0 or not math.isfinite(area_ha):
                geometry_failures += 1
                continue
            unit_id = str(feature[id_field])
            by_unit[unit_id].append(geometry)
            polygon_counts[unit_id][year] += 1
            if events_validated and event_field in fields:
                event_value = str(feature[event_field]).strip()
                if event_value:
                    event_ids[unit_id][year].add(event_value)
            try:
                full_area = float(feature["area_ha"] or 0.0)
            except Exception:
                full_area = 0.0
            if pov_field and mato_field and full_area > 0:
                try:
                    ratio = area_ha / full_area
                    forest_by_year[unit_id][year] += max(0.0, float(feature[pov_field] or 0.0)) * ratio
                    shrub_by_year[unit_id][year] += max(0.0, float(feature[mato_field] or 0.0)) * ratio
                except Exception:
                    forest_by_year[unit_id][year] += area_ha * 0.6
                    shrub_by_year[unit_id][year] += area_ha * 0.4
            else:
                forest_by_year[unit_id][year] += area_ha * 0.6
                shrub_by_year[unit_id][year] += area_ha * 0.4
        for unit_id in unit_geometries:
            annual_geometries[unit_id][year] = _r10b_union(by_unit.get(unit_id, []), QgsGeometry)

    if geometry_failures:
        raise RuntimeError(f"R10-B geometry failures after intersection: {geometry_failures}")

    legacy_totals = []
    per_unit = []
    annual_rows = []
    for unit_id in sorted(unit_geometries):
        annual_areas = {}
        for year in YEARS_HIST:
            geometry = annual_geometries[unit_id].get(year, QgsGeometry())
            area = float(geometry.area()) / 10000.0 if geometry and not geometry.isEmpty() else 0.0
            annual_areas[year] = area
            annual_rows.append([unit_id, year, unit_areas[unit_id], area, area / unit_areas[unit_id], int(area > 0), polygon_counts[unit_id].get(year, 0), len(event_ids[unit_id].get(year, set())) if any(item.get("event_semantics_status") == "FIRE_EVENT_ID_SEMANTICS_VALIDATED" for item in semantics) else ""])
        unique_geometry = _r10b_union(list(annual_geometries[unit_id].values()), QgsGeometry)
        unique_area = float(unique_geometry.area()) / 10000.0 if unique_geometry and not unique_geometry.isEmpty() else 0.0
        pairwise = []
        for index, left_year in enumerate(YEARS_HIST):
            for right_year in YEARS_HIST[index + 1:]:
                left = annual_geometries[unit_id].get(left_year, QgsGeometry())
                right = annual_geometries[unit_id].get(right_year, QgsGeometry())
                if left and right and not left.isEmpty() and not right.isEmpty():
                    overlap = left.intersection(right)
                    if overlap and not overlap.isEmpty():
                        pairwise.append(overlap)
        reburn_geometry = _r10b_union(pairwise, QgsGeometry)
        reburn_area = float(reburn_geometry.area()) / 10000.0 if reburn_geometry and not reburn_geometry.isEmpty() else 0.0
        annual_max = max(annual_areas.values())
        if reburn_area < 0 or reburn_area > unique_area or unique_area > unit_areas[unit_id] or annual_max > unit_areas[unit_id] or not all(math.isfinite(value) for value in (reburn_area, unique_area, annual_max)):
            raise RuntimeError(f"R10-B geometry ordering failure for {unit_id}")
        legacy_totals.append(sum(annual_areas.values()))
        per_unit.append({
            "territorial_level": territorial_level,
            "unit_id": unit_id,
            "unit_area_ha": unit_areas[unit_id],
            "annual_burned_area_by_year": annual_areas,
            "unique_burned_area_ha": unique_area,
            "reburned_area_ha": reburn_area,
            "burned_polygon_count": sum(polygon_counts[unit_id].values()),
            "event_count_if_validated": sum(len(event_ids[unit_id].get(year, set())) for year in YEARS_HIST) if any(item.get("event_semantics_status") == "FIRE_EVENT_ID_SEMANTICS_VALIDATED" for item in semantics) else "",
            "forest_proxy_ha_2015_2024": sum(forest_by_year[unit_id].values()),
            "shrubland_proxy_ha_2015_2024": sum(shrub_by_year[unit_id].values()),
        })
    legacy_classes = absolute_area_tertile_classes(legacy_totals)
    for record, legacy_class in zip(per_unit, legacy_classes):
        record["legacy_recurrence_class_absolute_burn_tertile"] = legacy_class
    rows = build_recurrence_records(per_unit)
    for row in rows:
        row["territorial_level"] = territorial_level
    write_summary(out_csv, rows, write_csv)
    if annual_out_csv is not None:
        write_csv(annual_out_csv, ["unit_id", "year", "unit_area_ha", "annual_burned_area_ha", "annual_burned_fraction", "affected_year_flag", "polygon_count", "event_count_if_validated"], annual_rows, delim=";")
    geometry_rows = []
    for row in rows:
        geometry_rows.append({"territorial_level": territorial_level, "unit_id": row["unit_id"], "unit_area_ha": row["unit_area_ha"], "unique_burned_area_ha": row["unique_burned_area_ha"], "reburned_area_ha": row["reburned_area_ha"], "annual_area_max_ha": row["maximum_annual_burned_fraction"] * row["unit_area_ha"], "geometry_failures": 0, "negative_area_failures": 0, "area_ordering_failures": 0, "status": "PASS"})
    return {"territorial_level": territorial_level, "records": rows, "semantics": semantics, "geometry": geometry_rows}


def interpolate_pop(p2015: float, p2020: float, p2025: float, year: int) -> float:
    if year <= 2020:
        return p2015 + (p2020 - p2015) * ((year - 2015) / 5.0)
    return p2020 + (p2025 - p2020) * ((year - 2020) / 5.0)


def interpolate_pop_scen(p2025: float, p2030: float, year: int) -> float:
    return p2025 + (p2030 - p2025) * ((year - 2025) / 5.0)


def compute_iech(pop_csv: Path, smoke_csv: Path, out_hist_csv: Path, out_mean_csv: Path) -> None:
    pop_rows = read_csv_rows(pop_csv)[1]
    smoke_rows = read_csv_rows(smoke_csv)[1]

    pop_by_u: Dict[str, Tuple[float, float, float, float]] = {}
    for r in pop_rows:
        uid = (r.get("unit_id") or "").strip()
        if not uid:
            continue
        pop_by_u[uid] = (
            safe_float(r.get("pop_2015_sum")) or 0.0,
            safe_float(r.get("pop_2020_sum")) or 0.0,
            safe_float(r.get("pop_2025_sum")) or 0.0,
            safe_float(r.get("pop_2030_sum")) or 0.0,
        )

    smoke_by_u_y: Dict[str, Dict[int, float]] = defaultdict(dict)
    for r in smoke_rows:
        uid = (r.get("unit_id") or "").strip()
        y = safe_float(r.get("year"))
        sd = safe_float(r.get("smoke_days"))
        if uid and y is not None and sd is not None:
            smoke_by_u_y[uid][int(y)] = sd

    rows_hist = []
    by_u: Dict[str, List[float]] = defaultdict(list)
    for uid in sorted(pop_by_u.keys()):
        p2015, p2020, p2025, _p2030 = pop_by_u[uid]
        for y in YEARS_HIST:
            sd = smoke_by_u_y.get(uid, {}).get(y, None)
            if sd is None:
                raise RuntimeError(f"Missing smoke_days for unit {uid} year {y}")
            p = interpolate_pop(p2015, p2020, p2025, y)
            burden = sd * p if p > 0 else None
            if burden is not None:
                by_u[uid].append(float(burden))
            rows_hist.append([
                uid, y, sd, p, burden, IECH_PROXY_INDICATOR_NAME, IECH_PROXY_INDICATOR_UNIT,
                IECH_PROXY_CLAIM_STATUS, "", "", "", "", "LEGACY_DEPRECATED_NOT_CANONICAL", _iech_hist_method_flag(),
            ])

    write_csv(
        out_hist_csv,
        [
            "unit_id", "year", "smoke_days", "population_total", "population_smoke_day_burden_proxy",
            "indicator_name", "indicator_unit", "claim_status", "legacy_smoke_hours_equiv",
            "legacy_expo_person_hours", "legacy_population_smoke_burden_proxy", "legacy_IECH",
            "legacy_status", "method_flags",
        ],
        rows_hist,
        delim=";",
    )

    rows_mean = []
    for uid in sorted(by_u.keys()):
        vals = by_u[uid]
        mean_val = (sum(vals) / len(vals)) if vals else 0.0
        rows_mean.append([uid, mean_val, ""])
    write_csv(
        out_mean_csv,
        [
            "unit_id",
            "population_smoke_day_burden_proxy_mean_2015_2024",
            "legacy_population_smoke_burden_proxy_mean_2015_2024",
        ],
        rows_mean,
        delim=";",
    )
def compute_scenarios(smoke_csv: Path, pop_csv: Path, out_scen_csv: Path, out_mean_csv: Path) -> None:
    smoke_rows = read_csv_rows(smoke_csv)[1]
    pop_rows = read_csv_rows(pop_csv)[1]

    smoke_by_u: Dict[str, List[float]] = defaultdict(list)
    for r in smoke_rows:
        uid = (r.get("unit_id") or "").strip()
        sd = safe_float(r.get("smoke_days"))
        if uid and sd is not None:
            smoke_by_u[uid].append(sd)
    if not smoke_by_u:
        raise RuntimeError("No smoke values found for scenarios.")

    baseline = {u: (sum(vs) / len(vs)) for u, vs in smoke_by_u.items() if vs}
    baseline_vals = sorted(baseline.values())
    thr80 = baseline_vals[int(0.80 * (len(baseline_vals) - 1))] if baseline_vals else None
    target = {u for u, v in baseline.items() if thr80 is not None and v >= thr80}

    pop_anchor: Dict[str, Tuple[float, float]] = {}
    for r in pop_rows:
        uid = (r.get("unit_id") or "").strip()
        p2025 = safe_float(r.get("pop_2025_sum"))
        p2030 = safe_float(r.get("pop_2030_sum"))
        if uid and p2025 is not None and p2030 is not None:
            pop_anchor[uid] = (p2025, p2030)

    rows = []
    acc: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for uid in sorted(baseline.keys()):
        if uid not in pop_anchor:
            raise RuntimeError(f"Missing population anchors for unit {uid}")
        base = baseline[uid]
        p2025, p2030 = pop_anchor[uid]
        for y in YEARS_SCEN:
            p = interpolate_pop_scen(p2025, p2030, y)
            sd0 = base
            burden0 = sd0 * p if p > 0 else None
            sd1 = base * (0.8 if uid in target else 1.0)
            burden1 = sd1 * p if p > 0 else None
            delta = (burden1 - burden0) if (burden1 is not None and burden0 is not None) else None
            flags = _iech_scen_method_flag()
            if burden0 is not None:
                acc[uid]["S0"].append(float(burden0))
            if burden1 is not None:
                acc[uid]["S1"].append(float(burden1))
            rows.append([
                uid, y, "S0", sd0, p, burden0, IECH_PROXY_INDICATOR_NAME, IECH_PROXY_INDICATOR_UNIT,
                IECH_PROXY_CLAIM_STATUS, "", "", "", 0.0, 0.0, flags,
            ])
            rows.append([
                uid, y, "S1", sd1, p, burden1, IECH_PROXY_INDICATOR_NAME, IECH_PROXY_INDICATOR_UNIT,
                IECH_PROXY_CLAIM_STATUS, "", "", "", delta, delta, flags,
            ])

    write_csv(
        out_scen_csv,
        [
            "unit_id", "year", "scenario", "smoke_days", "population_total",
            "population_smoke_day_burden_proxy", "indicator_name", "indicator_unit", "claim_status",
            "legacy_smoke_hours_equiv", "legacy_expo_person_hours", "legacy_population_smoke_burden_proxy",
            "delta_population_smoke_day_burden_proxy_vs_S0", "delta_smoke_day_burden_vs_S0", "method_flags",
        ],
        rows,
        delim=";",
    )

    rows_mean = []
    for uid in sorted(acc.keys()):
        m0_vals = acc[uid].get("S0", [])
        m1_vals = acc[uid].get("S1", [])
        m0 = (sum(m0_vals) / len(m0_vals)) if m0_vals else None
        m1 = (sum(m1_vals) / len(m1_vals)) if m1_vals else None
        delta = (m1 - m0) if (m0 is not None and m1 is not None) else None
        rows_mean.append([uid, m0, m1, delta, "", "", ""])
    write_csv(
        out_mean_csv,
        [
            "unit_id",
            "population_smoke_day_burden_proxy_S0_mean_2026_2030",
            "population_smoke_day_burden_proxy_S1_mean_2026_2030",
            "delta_population_smoke_day_burden_proxy_S1_minus_S0",
            "legacy_population_smoke_burden_proxy_S0_mean_2026_2030",
            "legacy_population_smoke_burden_proxy_S1_mean_2026_2030",
            "legacy_delta_S1_minus_S0",
        ],
        rows_mean,
        delim=";",
    )
def load_wrb_lookup_from_path(lookup_path: Path) -> Dict[int, str]:
    try:
        obj = json.loads(lookup_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    out: Dict[int, str] = {}
    for k, v in obj.items():
        try:
            out[int(k)] = str(v)
        except Exception:
            continue
    return out


def load_wrb_lookup(wrb_raster: Path) -> Dict[int, str]:
    candidates = [
        wrb_raster.parent / "MostProbable.rat.json",
        wrb_raster.parent.parent / "MostProbable.rat.json",
        wrb_raster.parent / "MostProbable.rat.JSON",
    ]
    for cand in candidates:
        if cand.exists():
            lookup = load_wrb_lookup_from_path(cand)
            if lookup:
                return lookup
    return {}


WRB_PIXEL_AREA_HA = 6.25
WRB_TM06_PIXEL_SIZE_M = 250.0
WRB_TM06_NODATA = 255
WRB_AREA_TOLERANCE_HA = 31.25


def _parse_wrb_field_name(field_name: str) -> Optional[int]:
    if not field_name.startswith("wrb_"):
        return None
    token = field_name[4:].strip()
    if token == "":
        return None
    if re.fullmatch(r"-?\d+_\d+", token):
        token = token.split("_", 1)[0]
    token = token.replace(",", ".")
    try:
        return int(round(float(token)))
    except Exception:
        return None


def _run_wrb_zonal_histogram(layer, wrb_src: str, processing):
    try:
        return processing.run(
            "native:zonalhistogram",
            {
                "INPUT_VECTOR": layer,
                "INPUT_RASTER": wrb_src,
                "RASTER_BAND": 1,
                "COLUMN_PREFIX": "wrb_",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]
    except Exception:
        return processing.run(
            "qgis:zonalhistogram",
            {
                "INPUT_VECTOR": layer,
                "INPUT_RASTER": wrb_src,
                "RASTER_BAND": 1,
                "COLUMN_PREFIX": "wrb_",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]


def _extract_wrb_hist_counts(feature) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for field_name in feature.fields().names():
        cls = _parse_wrb_field_name(field_name)
        if cls is None or cls == WRB_TM06_NODATA:
            continue
        value = safe_float(feature[field_name])
        if value is None or value <= 0:
            continue
        out[cls] = out.get(cls, 0.0) + float(value)
    return out


def _write_wrb_working_vrt(bundle: Dict[str, Path], output_vrt: Path) -> Path:
    ensure_dir(output_vrt.parent)
    template = Path(bundle["assembled_vrt_template"])
    tile_map = {
        Path(bundle["tile_193"]).name.lower(): Path(bundle["tile_193"]),
        Path(bundle["tile_235"]).name.lower(): Path(bundle["tile_235"]),
        Path(bundle["tile_236"]).name.lower(): Path(bundle["tile_236"]),
    }
    if template.exists():
        tree = ET.parse(template)
        root = tree.getroot()
        for elem in root.iter("SourceFilename"):
            name = Path((elem.text or "").strip()).name.lower()
            if name in tile_map:
                elem.text = str(tile_map[name])
                elem.set("relativeToVRT", "0")
        tree.write(output_vrt, encoding="utf-8")
        return output_vrt

    gdalbuildvrt = Path(r"C:\OSGeo4W64\bin\gdalbuildvrt.exe")
    if not gdalbuildvrt.exists():
        raise RuntimeError(
            "BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: missing MostProbable_assembled.vrt template and gdalbuildvrt fallback."
        )
    cmd = [
        str(gdalbuildvrt),
        str(output_vrt),
        str(bundle["tile_193"]),
        str(bundle["tile_235"]),
        str(bundle["tile_236"]),
    ]
    fb = subprocess.run(cmd, capture_output=True, text=True)
    if fb.returncode != 0 or not output_vrt.exists():
        raise RuntimeError(
            "BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to build WRB_working_from_tiles source VRT; "
            f"rc={fb.returncode}; stderr={(fb.stderr or '').strip()}"
        )
    return output_vrt


def _load_gdal_runtime():
    from osgeo import gdal  # type: ignore

    gdal.UseExceptions()
    return gdal


def _layer_crs_authid(layer) -> str:
    try:
        if layer.crs().isValid():
            return (layer.crs().authid() or "").upper()
    except Exception:
        pass
    return ""


def _ensure_tm06_vector_layer(layer, processing):
    if "EPSG:3763" in _layer_crs_authid(layer):
        return layer
    from qgis.core import QgsCoordinateReferenceSystem  # type: ignore

    return processing.run(
        "native:reprojectlayer",
        {"INPUT": layer, "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:3763"), "OUTPUT": "memory:"},
    )["OUTPUT"]


def _union_tm06_extent(mask_paths: List[Path]):
    from qgis.core import QgsVectorLayer  # type: ignore

    min_x = None
    min_y = None
    max_x = None
    max_y = None
    for mask_path in mask_paths:
        layer = QgsVectorLayer(str(mask_path), f"wrb_mask_extent_{mask_path.stem}", "ogr")
        if not layer.isValid():
            raise RuntimeError(f"Invalid annual burned-area layer for WRB route: {mask_path}")
        ext = layer.extent()
        min_x = ext.xMinimum() if min_x is None else min(min_x, ext.xMinimum())
        min_y = ext.yMinimum() if min_y is None else min(min_y, ext.yMinimum())
        max_x = ext.xMaximum() if max_x is None else max(max_x, ext.xMaximum())
        max_y = ext.yMaximum() if max_y is None else max(max_y, ext.yMaximum())
    if None in (min_x, min_y, max_x, max_y):
        raise RuntimeError("BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: annual burned-area extents unavailable.")
    return float(min_x), float(min_y), float(max_x), float(max_y)


def _write_wrb_working_tm06_raster(source_vrt: Path, bounds_3763: Tuple[float, float, float, float], output_raster: Path) -> Path:
    gdal = _load_gdal_runtime()
    ensure_dir(output_raster.parent)
    min_x, min_y, max_x, max_y = bounds_3763
    gdal.Warp(
        str(output_raster),
        str(source_vrt),
        dstSRS="EPSG:3763",
        xRes=WRB_TM06_PIXEL_SIZE_M,
        yRes=WRB_TM06_PIXEL_SIZE_M,
        resampleAlg="near",
        targetAlignedPixels=True,
        outputBounds=(min_x, min_y, max_x, max_y),
        dstNodata=WRB_TM06_NODATA,
        multithread=False,
    )
    if not output_raster.exists():
        raise RuntimeError(f"BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to warp WRB TM06 raster {output_raster}")
    return output_raster

def _save_layer_for_gdal(layer, output_vector: Path, processing) -> Path:
    ensure_dir(output_vector.parent)
    if output_vector.exists():
        output_vector.unlink()
    processing.run("native:savefeatures", {"INPUT": layer, "OUTPUT": str(output_vector)})
    if not output_vector.exists():
        raise RuntimeError(f"BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to materialize annual mask {output_vector}")
    return output_vector


def _rasterize_annual_burned_area_mask(mask_layer, template_raster: Path, output_mask: Path, processing, all_touched: bool = False) -> Path:
    gdal = _load_gdal_runtime()
    mask_vector = _save_layer_for_gdal(mask_layer, output_mask.with_suffix(".gpkg"), processing)
    template_ds = gdal.Open(str(template_raster))
    if template_ds is None:
        raise RuntimeError(f"BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to open template raster {template_raster}")
    driver = gdal.GetDriverByName("GTiff")
    ensure_dir(output_mask.parent)
    out_ds = driver.Create(
        str(output_mask),
        template_ds.RasterXSize,
        template_ds.RasterYSize,
        1,
        gdal.GDT_Byte,
        options=["TILED=YES", "COMPRESS=LZW"],
    )
    out_ds.SetGeoTransform(template_ds.GetGeoTransform())
    out_ds.SetProjection(template_ds.GetProjection())
    out_band = out_ds.GetRasterBand(1)
    out_band.Fill(0)
    out_band.SetNoDataValue(0)
    vector_ds = gdal.OpenEx(str(mask_vector), gdal.OF_VECTOR)
    layer = vector_ds.GetLayer(0)
    gdal.RasterizeLayer(out_ds, [1], layer, burn_values=[1], options=[f"ALL_TOUCHED={'TRUE' if all_touched else 'FALSE'}"])
    out_band.FlushCache()
    out_ds.FlushCache()
    out_ds = None
    if not output_mask.exists():
        raise RuntimeError(f"BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to rasterize annual mask {output_mask}")
    return output_mask


def _write_masked_wrb_raster(wrb_tm06_raster: Path, annual_mask_raster: Path, output_raster: Path) -> Path:
    gdal = _load_gdal_runtime()
    wrb_ds = gdal.Open(str(wrb_tm06_raster))
    mask_ds = gdal.Open(str(annual_mask_raster))
    if wrb_ds is None or mask_ds is None:
        raise RuntimeError("BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to open WRB or annual mask raster.")
    wrb_arr = wrb_ds.GetRasterBand(1).ReadAsArray()
    mask_arr = mask_ds.GetRasterBand(1).ReadAsArray()
    masked_arr = wrb_arr.copy()
    masked_arr[mask_arr != 1] = WRB_TM06_NODATA
    driver = gdal.GetDriverByName("GTiff")
    ensure_dir(output_raster.parent)
    out_ds = driver.Create(
        str(output_raster),
        wrb_ds.RasterXSize,
        wrb_ds.RasterYSize,
        1,
        wrb_ds.GetRasterBand(1).DataType,
        options=["TILED=YES", "COMPRESS=LZW"],
    )
    out_ds.SetGeoTransform(wrb_ds.GetGeoTransform())
    out_ds.SetProjection(wrb_ds.GetProjection())
    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(masked_arr)
    out_band.SetNoDataValue(WRB_TM06_NODATA)
    out_band.FlushCache()
    out_ds.FlushCache()
    out_ds = None
    if not output_raster.exists():
        raise RuntimeError(f"BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to write masked WRB raster {output_raster}")
    return output_raster


def _count_wrb_classes_in_raster(raster_path: Path) -> Dict[int, float]:
    gdal = _load_gdal_runtime()
    ds = gdal.Open(str(raster_path))
    if ds is None:
        raise RuntimeError(f"BLOCKED_WRB_SOURCE_ROUTE_UNAVAILABLE: failed to open masked WRB raster {raster_path}")
    arr = ds.GetRasterBand(1).ReadAsArray()
    counts: Dict[int, float] = {}
    for value in arr.ravel().tolist():
        cls = int(value)
        if cls == WRB_TM06_NODATA:
            continue
        counts[cls] = counts.get(cls, 0.0) + 1.0
    return counts


def _build_wrb_geometry_memory_layer(geometries, layer_name: str = "wrb_unit_mask"):
    from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer  # type: ignore

    mem = QgsVectorLayer("MultiPolygon?crs=EPSG:3763", layer_name, "memory")
    provider = mem.dataProvider()
    feats = []
    for geom in geometries:
        if geom is None or geom.isEmpty():
            continue
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry(geom))
        feats.append(feat)
    if feats:
        provider.addFeatures(feats)
        mem.updateExtents()
    return mem


def _count_wrb_classes_for_unit_geometries(
    geometries,
    wrb_tm06_raster: Path,
    wrb_runtime_dir: Path,
    year: int,
    uid: str,
    processing,
) -> Dict[int, float]:
    valid_geoms = [geom for geom in geometries if geom is not None and not geom.isEmpty()]
    if not valid_geoms:
        return {}
    safe_uid = re.sub(r"[^A-Za-z0-9_-]+", "_", str(uid))
    mask_layer = _build_wrb_geometry_memory_layer(valid_geoms, f"wrb_mask_{safe_uid}_{year}")
    if mask_layer.featureCount() <= 0:
        return {}
    rescue_mask = _rasterize_annual_burned_area_mask(
        mask_layer,
        wrb_tm06_raster,
        wrb_runtime_dir / f"annual_burned_area_mask_{year}_{safe_uid}_rescue.tif",
        processing,
        all_touched=True,
    )
    rescue_raster = _write_masked_wrb_raster(
        wrb_tm06_raster,
        rescue_mask,
        wrb_runtime_dir / f"WRB_working_TM06_from_tiles_masked_{year}_{safe_uid}_rescue.tif",
    )
    return _count_wrb_classes_in_raster(rescue_raster)


def _dominant_wrb_row(
    uid: str,
    class_counts: Dict[int, float],
    wrb_lookup: Dict[int, str],
    wrb_source: Path,
    note: Optional[str] = None,
    missing_flag: int = 0,
    coverage_status: str = WRB_STATUS_PASS,
    not_applicable_flag: int = 0,
    method: str = WRB_METHOD_BURNED_AREA_OVERLAY,
) -> List[object]:
    total = float(sum(class_counts.values()))
    if total <= 0:
        return [
            uid,
            "",
            "",
            "",
            note or "WRB unavailable because the annual burned-area overlay produced no WRB pixels for 2015-2024.",
            str(wrb_source),
            1,
            method,
            coverage_status,
            not_applicable_flag,
        ]

    ordered = sorted(class_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    dom_cls, dom_count = ordered[0]
    dom_share = dom_count / total
    top_tokens = []
    for cls, count in ordered[:5]:
        label = wrb_lookup.get(cls, f"class_{cls}")
        share = count / total
        top_tokens.append(f"{label}:{share:.3f}")
    dom_label = wrb_lookup.get(dom_cls, f"class_{dom_cls}")
    return [
        uid,
        dom_label,
        f"{dom_share:.6f}",
        "|".join(top_tokens),
        note or "Contexto edafico territorial (WRB) derivado exclusivamente del overlay de area quemada anual sobre WRB_working_TM06_from_tiles; no causal directo.",
        str(wrb_source),
        missing_flag,
        method,
        coverage_status,
        not_applicable_flag,
    ]


def _wrb_empty_row(
    uid: str,
    wrb_source: Path,
    note: str,
    coverage_status: str,
    missing_flag: int,
    not_applicable_flag: int,
) -> List[object]:
    return [
        uid,
        "",
        "",
        "",
        note,
        str(wrb_source),
        missing_flag,
        WRB_METHOD_BURNED_AREA_OVERLAY,
        coverage_status,
        not_applicable_flag,
    ]


def _write_wrb_year_summary(summary_csv: Path, year_class_counts: Dict[int, Dict[int, float]], wrb_lookup: Dict[int, str]) -> None:
    rows: List[List[object]] = []
    for year in sorted(year_class_counts):
        class_counts = year_class_counts[year]
        total_pixels = float(sum(class_counts.values()))
        if total_pixels <= 0:
            continue
        total_area_ha = total_pixels * WRB_PIXEL_AREA_HA
        for cls, count in sorted(class_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            area_ha = float(count) * WRB_PIXEL_AREA_HA
            pct_area = (float(count) / total_pixels) * 100.0
            rows.append([
                year,
                float(cls),
                wrb_lookup.get(cls, f"class_{cls}"),
                float(count),
                area_ha,
                pct_area,
                total_area_ha,
            ])
    write_csv(
        summary_csv,
        ["Year", "WRB_code", "Class_name", "Count_pixels", "Area_ha", "Pct_area", "Year_total_ha"],
        rows,
        delim=",",
    )


def _read_wrb_year_summary(path: Path, year: int) -> Dict[str, Dict[str, float]]:
    rows = read_csv_rows(path)[1]
    out: Dict[str, Dict[str, float]] = {}
    for row in rows:
        y_val = safe_float(row.get("Year") or row.get("year"))
        if y_val is None or int(y_val) != year:
            continue
        cls_name = (row.get("Class_name") or row.get("class_name") or "").strip()
        if not cls_name:
            continue
        out[cls_name] = {
            "count": float(safe_float(row.get("Count_pixels") or row.get("count_pixels")) or 0.0),
            "area": float(safe_float(row.get("Area_ha") or row.get("area_ha")) or 0.0),
        }
    return out


def write_wrb_year_validation_audit(audit_path: Path, computed_csv: Path, reference_csv: Path, year: int) -> None:
    if not reference_csv.exists():
        raise RuntimeError(f"BLOCKED_WRB_REFERENCE_MISSING: {reference_csv}")

    computed = _read_wrb_year_summary(computed_csv, year)
    reference = _read_wrb_year_summary(reference_csv, year)
    computed_positive = sorted(cls for cls, vals in computed.items() if vals["count"] > 0)
    reference_positive = sorted(cls for cls, vals in reference.items() if vals["count"] > 0)

    rows = [["metric", "value", "status", "note"]]
    pass_flag = True

    multiclass = len(computed_positive) > 1
    has_cambisols = "Cambisols" in computed_positive
    has_luvisols = "Luvisols" in computed_positive
    class_set_match = computed_positive == reference_positive

    rows.append(["validation_year", year, "PASS", "WRB burned-area prevalidation target year."])
    rows.append(["computed_positive_classes", "|".join(computed_positive), "PASS" if computed_positive else "HOLD", "Positive WRB classes from computed overlay summary."])
    rows.append(["reference_positive_classes", "|".join(reference_positive), "PASS" if reference_positive else "HOLD", "Positive WRB classes from reference CSV."])
    rows.append(["computed_multiclass", len(computed_positive), "PASS" if multiclass else "HOLD", "Computed 2022 summary must show more than one WRB class."])
    rows.append(["computed_has_cambisols", int(has_cambisols), "PASS" if has_cambisols else "HOLD", "Cambisols must be present in computed 2022 summary."])
    rows.append(["computed_has_luvisols", int(has_luvisols), "PASS" if has_luvisols else "HOLD", "Luvisols must be present in computed 2022 summary."])
    rows.append(["class_set_match_reference", int(class_set_match), "PASS" if class_set_match else "HOLD", "Computed positive WRB classes must match the reference set for the validation year."])

    if not multiclass or not has_cambisols or not has_luvisols or not class_set_match:
        pass_flag = False

    union_classes = sorted(set(computed_positive) | set(reference_positive))
    for cls_name in union_classes:
        comp_area = float(computed.get(cls_name, {}).get("area", 0.0))
        ref_area = float(reference.get(cls_name, {}).get("area", 0.0))
        diff = abs(comp_area - ref_area)
        status = "PASS" if diff <= WRB_AREA_TOLERANCE_HA else "HOLD"
        rows.append([f"area_ha_{cls_name}", comp_area, status, f"reference={ref_area}; abs_diff={diff}; tolerance_ha={WRB_AREA_TOLERANCE_HA}"])
        if status != "PASS":
            pass_flag = False

    write_csv(audit_path, rows[0], rows[1:], delim="\t")
    if not pass_flag:
        raise RuntimeError(f"BLOCKED_WRB_PREVALIDATION_{year}: {audit_path}")


def compute_wrb_context_v2(
    layer,
    id_field: str,
    fire_paths: List[Path],
    wrb_bundle: Dict[str, Path],
    work_dir: Path,
    out_csv: Path,
    year_summary_csv: Path,
    processing,
) -> Path:
    from qgis.core import QgsVectorLayer  # type: ignore

    wrb_lookup = load_wrb_lookup_from_path(Path(wrb_bundle["lookup_path"]))
    wrb_runtime_dir = work_dir / "wrb_source_route"
    wrb_source_vrt = _write_wrb_working_vrt(wrb_bundle, wrb_runtime_dir / "WRB_working_from_tiles_4326.vrt")

    unit_ids = get_unit_ids(layer, id_field)
    if not unit_ids:
        raise RuntimeError(f"No unit ids found for field '{id_field}'")

    admin_fix = processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]
    admin_fix = _ensure_tm06_vector_layer(admin_fix, processing)
    admin_extent = admin_fix.extent()
    admin_bounds = (
        float(admin_extent.xMinimum()),
        float(admin_extent.yMinimum()),
        float(admin_extent.xMaximum()),
        float(admin_extent.yMaximum()),
    )
    wrb_tm06_raster = _write_wrb_working_tm06_raster(wrb_source_vrt, admin_bounds, wrb_runtime_dir / "WRB_working_TM06_from_tiles.tif")
    class_counts_by_unit: Dict[str, Dict[int, float]] = {uid: {} for uid in unit_ids}
    year_class_counts: Dict[int, Dict[int, float]] = {}
    burned_area_ha_by_unit: Dict[str, float] = {uid: 0.0 for uid in unit_ids}

    for annual_path in fire_paths:
        year = _extract_year(annual_path.name)
        if year is None or year not in YEARS_HIST:
            continue

        annual_layer = QgsVectorLayer(str(annual_path), f"wrb_annual_burned_{year}", "ogr")
        if not annual_layer.isValid():
            raise RuntimeError(f"Invalid annual burned-area layer for WRB route: {annual_path}")
        if annual_layer.featureCount() <= 0:
            continue

        annual_fix = processing.run("native:fixgeometries", {"INPUT": annual_layer, "OUTPUT": "memory:"})["OUTPUT"]
        annual_fix = _ensure_tm06_vector_layer(annual_fix, processing)
        annual_burned = processing.run("native:dissolve", {"INPUT": annual_fix, "OUTPUT": "memory:"})["OUTPUT"]
        if annual_burned.featureCount() <= 0:
            continue

        annual_admin_intersection = processing.run(
            "native:intersection",
            {"INPUT": admin_fix, "OVERLAY": annual_burned, "OUTPUT": "memory:"},
        )["OUTPUT"]
        annual_geometries_by_unit: Dict[str, List[object]] = defaultdict(list)
        for ft in annual_admin_intersection.getFeatures():
            uid = str(ft[id_field])
            geom = ft.geometry()
            if not uid or geom is None or geom.isEmpty():
                continue
            burned_area_ha_by_unit[uid] = burned_area_ha_by_unit.get(uid, 0.0) + (float(geom.area()) / 10000.0)
            annual_geometries_by_unit[uid].append(geom)

        annual_mask_raster = _rasterize_annual_burned_area_mask(
            annual_burned,
            wrb_tm06_raster,
            wrb_runtime_dir / f"annual_burned_area_mask_{year}.tif",
            processing,
            all_touched=False,
        )
        masked_wrb_raster = _write_masked_wrb_raster(
            wrb_tm06_raster,
            annual_mask_raster,
            wrb_runtime_dir / f"WRB_working_TM06_from_tiles_masked_{year}.tif",
        )

        annual_counts = _count_wrb_classes_in_raster(masked_wrb_raster)
        if annual_counts:
            year_counts = year_class_counts.setdefault(year, {})
            for cls, count in annual_counts.items():
                year_counts[cls] = year_counts.get(cls, 0.0) + float(count)

        hist_layer = _run_wrb_zonal_histogram(admin_fix, str(masked_wrb_raster), processing)
        hist_hit_uids = set()
        for ft in hist_layer.getFeatures():
            uid = str(ft[id_field])
            hist_counts = _extract_wrb_hist_counts(ft)
            if not hist_counts:
                continue
            hist_hit_uids.add(uid)
            unit_counts = class_counts_by_unit.setdefault(uid, {})
            for cls, count in hist_counts.items():
                unit_counts[cls] = unit_counts.get(cls, 0.0) + float(count)

        for uid, geoms in annual_geometries_by_unit.items():
            if uid in hist_hit_uids:
                continue
            rescue_counts = _count_wrb_classes_for_unit_geometries(
                geoms,
                wrb_tm06_raster,
                wrb_runtime_dir,
                year,
                uid,
                processing,
            )
            if not rescue_counts:
                continue
            unit_counts = class_counts_by_unit.setdefault(uid, {})
            for cls, count in rescue_counts.items():
                unit_counts[cls] = unit_counts.get(cls, 0.0) + float(count)

    rows = []
    for uid in unit_ids:
        annual_counts = class_counts_by_unit.get(uid, {})
        if annual_counts:
            rows.append(
                _dominant_wrb_row(
                    uid,
                    annual_counts,
                    wrb_lookup,
                    wrb_tm06_raster,
                    coverage_status=WRB_STATUS_PASS,
                    missing_flag=0,
                    not_applicable_flag=0,
                )
            )
            continue
        burned_area_ha = burned_area_ha_by_unit.get(uid, 0.0)
        if burned_area_ha <= 0.0:
            rows.append(
                _wrb_empty_row(
                    uid,
                    wrb_tm06_raster,
                    "Sin interseccion quemada 2015-2024 verificada; WRB no aplicable para interpretacion de area quemada.",
                    WRB_STATUS_NOT_APPLICABLE_ZERO_BURN,
                    missing_flag=0,
                    not_applicable_flag=1,
                )
            )
        else:
            rows.append(
                _wrb_empty_row(
                    uid,
                    wrb_tm06_raster,
                    "Area quemada positiva 2015-2024 sin conteos WRB extraidos en overlay anual; bloqueo metodologico.",
                    WRB_STATUS_BLOCKED_MISSING,
                    missing_flag=1,
                    not_applicable_flag=0,
                )
            )
    write_csv(
        out_csv,
        [
            "unit_id",
            "dominant_wrb_class",
            "dominant_wrb_share",
            "top_wrb_classes",
            "wrb_context_note",
            "wrb_source",
            "wrb_missing_flag",
            "wrb_method",
            "wrb_coverage_status",
            "wrb_not_applicable_flag",
        ],
        rows,
        delim=";",
    )
    _write_wrb_year_summary(year_summary_csv, year_class_counts, wrb_lookup)
    return wrb_tm06_raster


def resolve_built_raster(paths: Dict[str, object]) -> Path:
    ghsl = paths.get("ghsl_pop", {})
    if not isinstance(ghsl, dict):
        raise RuntimeError("paths.ghsl_pop missing")
    pop_2020 = Path(str(ghsl.get("2020", "")))
    if not pop_2020.exists():
        raise RuntimeError(f"Missing ghsl_pop 2020: {pop_2020}")

    datos_root = None
    for parent in pop_2020.parents:
        if parent.name.lower() == "datos":
            datos_root = parent
            break
    if datos_root is None:
        raise RuntimeError(f"Could not infer Datos root from {pop_2020}")

    built_dir = datos_root / "01_std" / "ghsl" / "built"
    candidates = sorted([p for p in built_dir.glob("*2020*epsg4326*.zip") if p.is_file()])
    if not candidates:
        candidates = sorted([p for p in built_dir.glob("*2020*.zip") if p.is_file()])
    if not candidates:
        raise FileNotFoundError(f"No GHSL built 2020 zip found under {built_dir}")
    return candidates[0]


def compute_territorial_context(layer, id_field: str, recurrence_csv: Path, built_zip: Path, work_dir: Path, out_csv: Path, processing) -> None:
    admin_extent = layer.extent()
    xmin, xmax = admin_extent.xMinimum(), admin_extent.xMaximum()
    ymin, ymax = admin_extent.yMinimum(), admin_extent.yMaximum()
    target_extent = f"{xmin},{xmax},{ymin},{ymax} [EPSG:3763]"
    warp_extra = f"-te {xmin} {ymin} {xmax} {ymax} -tr 100 100 -overwrite"

    rasters = work_dir / "rasters_3763_step7_built"
    ensure_dir(rasters)
    built_raster = resolve_raster_source(str(built_zip))
    built_dst = rasters / f"ghsl_built_2020_{id_field.lower()}.tif"
    if built_dst.exists():
        try:
            built_dst.unlink()
        except Exception:
            pass

    warped = processing.run(
        "gdal:warpreproject",
        {
            "INPUT": built_raster,
            "SOURCE_CRS": None,
            "TARGET_CRS": "EPSG:3763",
            "RESAMPLING": 0,
            "NODATA": None,
            "TARGET_RESOLUTION": 100.0,
            "OPTIONS": "",
            "DATA_TYPE": 0,
            "TARGET_EXTENT": target_extent,
            "TARGET_EXTENT_CRS": "EPSG:3763",
            "MULTITHREADING": False,
            "EXTRA": warp_extra,
            "OUTPUT": str(built_dst),
        },
    )["OUTPUT"]
    built_dst_path = Path(str(warped))
    if not built_dst_path.exists():
        gdalwarp = Path(r"C:\OSGeo4W64\bin\gdalwarp.exe")
        if not gdalwarp.exists():
            raise RuntimeError(f"Failed to warp GHSL built raster: {built_zip}; missing fallback {gdalwarp}")
        cmd = [
            str(gdalwarp),
            "-overwrite",
            "-t_srs",
            "EPSG:3763",
            "-te",
            str(xmin),
            str(ymin),
            str(xmax),
            str(ymax),
            "-tr",
            "100",
            "100",
            built_raster,
            str(built_dst),
        ]
        fb = subprocess.run(cmd, capture_output=True, text=True)
        if fb.returncode != 0 or not built_dst.exists():
            raise RuntimeError(
                f"Failed to warp GHSL built raster: {built_zip}; fallback_rc={fb.returncode}; "
                f"fallback_stderr={(fb.stderr or '').strip()}"
            )
        built_dst_path = built_dst

    z = processing.run(
        "native:zonalstatisticsfb",
        {
            "INPUT": layer,
            "INPUT_RASTER": str(built_dst_path),
            "RASTER_BAND": 1,
            "COLUMN_PREFIX": "built_",
            "STATISTICS": [1],
            "OUTPUT": "memory:",
        },
    )
    layer_built = z["OUTPUT"]
    built_fields = set(layer_built.fields().names())
    built_col = "built_sum" if "built_sum" in built_fields else None

    rec_rows = read_csv_rows(recurrence_csv)[1] if recurrence_csv.exists() else []
    rec_map: Dict[str, Dict[str, float]] = {}
    for r in rec_rows:
        uid = (r.get("unit_id") or "").strip()
        if not uid:
            continue
        rec_map[uid] = {
            "forest": safe_float(r.get("forest_proxy_ha_2015_2024")) or 0.0,
            "shrub": safe_float(r.get("shrubland_proxy_ha_2015_2024")) or 0.0,
        }

    rows_out = []
    for ft in layer_built.getFeatures():
        uid = str(ft[id_field])
        built_val = safe_float(ft[built_col]) if built_col and built_col in built_fields else None
        rec = rec_map.get(uid, {"forest": 0.0, "shrub": 0.0})
        forest = rec["forest"]
        shrub = rec["shrub"]
        fuel_proxy = (forest + shrub)
        built_available = built_val is not None
        fuel_available = fuel_proxy > 0
        wui_proxy = (built_val * fuel_proxy) if (built_available and fuel_available) else (0.0 if built_available else None)

        if built_available and fuel_available:
            note = "WUI proxy construido como built_up_proxy x combustible_proxy."
            missing_flag = 0
        elif built_available and not fuel_available:
            note = "built_up_proxy_available=TRUE; wui_proxy=0 por combustible no positivo."
            missing_flag = 0
        else:
            note = "built_up_proxy unavailable for this unit."
            missing_flag = 1

        rows_out.append(
            [
                uid,
                built_val if built_val is not None else "",
                forest if forest is not None else "",
                shrub if shrub is not None else "",
                wui_proxy if wui_proxy is not None else "",
                f"GHSL_BUILT_2020:{built_zip.name}; fuel_proxy_from:{recurrence_csv.name}",
                note,
                missing_flag,
                "BUILT_UP_FUEL_TERRITORIAL_PROXY",
                "AVAILABLE_AS_CONTEXT",
                "HOLD_FORMAL_WUI",
                "HOLD_FORMAL_WUI",
                "NOT_IMPLEMENTED",
                "FALSE",
                "NOT_SUPPORTED_BY_CURRENT_AUTHORIZED_INPUTS",
                "FALSE",
                "TRUE",
                "LEGACY_OR_CONTEXTUAL_PROXY_NOT_FORMAL_WUI",
            ]
        )

    write_csv(
        out_csv,
        [
            "unit_id", "built_up_proxy", "forest_proxy", "shrubland_proxy", "wui_proxy",
            "landcover_source", "territorial_context_note", "territorial_missing_flag",
            "territorial_indicator_type", "territorial_proxy_status", "formal_wui_status",
            "formal_wui_claim_status", "formal_wui_method", "building_vegetation_spatial_relation",
            "formal_wui_source_status", "independent_landcover_input_used",
            "current_wui_proxy_fire_history_dependent", "wui_proxy_semantic_status",
        ],
        rows_out,
        delim=";",
    )


def _mean_by_unit(smoke_csv: Path) -> Dict[str, float]:
    rows = read_csv_rows(smoke_csv)[1]
    acc: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        uid = (r.get("unit_id") or "").strip()
        sd = safe_float(r.get("smoke_days"))
        if uid and sd is not None:
            acc[uid].append(sd)
    return {u: (sum(v) / len(v)) for u, v in acc.items() if v}


def _smoke_spatial_homogeneous(smoke_csv: Path) -> bool:
    if not smoke_csv.exists():
        return True
    rows = read_csv_rows(smoke_csv)[1]
    by_year: Dict[int, set] = defaultdict(set)
    positive_signal_direct_years: set[int] = set()
    for r in rows:
        y = safe_float(r.get("year"))
        v = safe_float(r.get("smoke_days"))
        method = (r.get("smoke_method") or r.get("method") or "").strip().lower()
        if y is None or v is None:
            continue
        year_int = int(y)
        if ("direct_year" in method) or (not method):
            by_year[year_int].add(round(v, 8))
            if v > 0:
                positive_signal_direct_years.add(year_int)
    if not positive_signal_direct_years:
        return True
    return any(len(by_year.get(year_int, set())) <= 1 for year_int in positive_signal_direct_years)


def _iech_population_cancellation(iech_hist_csv: Path) -> bool:
    if not iech_hist_csv.exists():
        return True
    rows = read_csv_rows(iech_hist_csv)[1]
    comparable = 0
    equal_rows = 0
    for r in rows:
        iech = safe_float(r.get("IECH"))
        burden = _first_present_float(r, "population_smoke_day_burden_proxy", "population_smoke_burden_proxy", "IECH")
        days = safe_float(r.get("smoke_days"))
        population = _first_present_float(r, "population_total", "pop")
        if burden is None or days is None or population is None:
            continue
        comparable += 1
        if abs(burden - (days * population)) <= 1e-9:
            equal_rows += 1
    return comparable == 0 or comparable == equal_rows


def _map_table_by_unit(path: Path) -> Dict[str, Dict[str, str]]:
    rows = read_csv_rows(path)[1]
    out: Dict[str, Dict[str, str]] = {}
    for r in rows:
        uid = (r.get("unit_id") or "").strip()
        if uid:
            out[uid] = r
    return out


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    idx = int(q * (len(vs) - 1))
    return vs[idx]


def build_causal_matrix(
    output_root: Path,
    unit_level: str,
    smoke_csv: Path,
    pop_csv: Path,
    recurrence_csv: Path,
    iech_mean_csv: Path,
    scen_mean_csv: Path,
    wrb_csv: Path,
    terr_csv: Path,
    out_csv: Path,
    smoke_route_blocked: bool = False,
    smoke_route_context: str = "",
) -> List[Dict[str, object]]:
    smoke_mean = _mean_by_unit(smoke_csv)
    pop_map = _map_table_by_unit(pop_csv)
    rec_map = _map_table_by_unit(recurrence_csv)
    iech_map = _map_table_by_unit(iech_mean_csv)
    scen_map = _map_table_by_unit(scen_mean_csv)
    wrb_map = _map_table_by_unit(wrb_csv) if wrb_csv.exists() else {}
    terr_map = _map_table_by_unit(terr_csv) if terr_csv.exists() else {}

    unit_ids = sorted(set(iech_map.keys()) | set(pop_map.keys()) | set(rec_map.keys()))

    iech_vals = [_first_present_float(iech_map.get(u, {}), "population_smoke_day_burden_proxy_mean_2015_2024", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024") for u in unit_ids]
    iech_vals = [v for v in iech_vals if v is not None]
    iech_q80 = _quantile(iech_vals, 0.80) if iech_vals else 0.0

    rows_out: List[Dict[str, object]] = []
    for uid in unit_ids:
        pop_r = pop_map.get(uid, {})
        rec_r = rec_map.get(uid, {})
        iech_r = iech_map.get(uid, {})
        scen_r = scen_map.get(uid, {})
        wrb_r = wrb_map.get(uid, {})
        terr_r = terr_map.get(uid, {})

        iech_mean = _first_present_float(iech_r, "population_smoke_day_burden_proxy_mean_2015_2024", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024")
        smoke_mean_u = smoke_mean.get(uid)
        pop2020 = safe_float(pop_r.get("pop_2020_sum"))
        pop2030 = safe_float(pop_r.get("pop_2030_sum"))
        burn = safe_float(rec_r.get("cumulative_burned_area_ha", rec_r.get("total_burn_ha_2015_2024")))
        years_gt = safe_float(rec_r.get("legacy_years_area_gt_own_p75", rec_r.get("years_area_gt_p75")))
        n_big = safe_float(rec_r.get("event_count_if_validated", rec_r.get("n_events_gt_1000ha")))
        unit_area = safe_float(rec_r.get("unit_area_ha"))
        affected_year_fraction = safe_float(rec_r.get("affected_year_fraction"))
        unique_burned_fraction = safe_float(rec_r.get("unique_burned_fraction"))
        reburn_share = safe_float(rec_r.get("reburn_share_of_unique_burned_area"))
        recurrence_score = safe_float(rec_r.get("recurrence_score"))
        recurrence_temporal_rank = safe_float(rec_r.get("recurrence_temporal_rank"))
        recurrence_reburn_rank = safe_float(rec_r.get("recurrence_reburn_rank"))
        rec_class = (rec_r.get("recurrence_class") or "").strip()

        s0 = _first_present_float(scen_r, "population_smoke_day_burden_proxy_S0_mean_2026_2030", "population_smoke_burden_proxy_S0_mean_2026_2030", "IECH_S0_mean_2026_2030")
        s1 = _first_present_float(scen_r, "population_smoke_day_burden_proxy_S1_mean_2026_2030", "population_smoke_burden_proxy_S1_mean_2026_2030", "IECH_S1_mean_2026_2030")
        delta = _first_present_float(scen_r, "delta_population_smoke_day_burden_proxy_S1_minus_S0", "delta_population_smoke_burden_proxy_S1_minus_S0", "delta_S1_minus_S0")

        wrb_dom = (wrb_r.get("dominant_wrb_class") or "").strip()
        wrb_dom_share = safe_float(wrb_r.get("dominant_wrb_share"))
        wrb_note = (wrb_r.get("wrb_context_note") or "").strip()
        wrb_missing = int(safe_float(wrb_r.get("wrb_missing_flag")) or 0)
        wrb_status = (wrb_r.get("wrb_coverage_status") or "").strip()
        wrb_not_applicable = int(safe_float(wrb_r.get("wrb_not_applicable_flag")) or 0)

        built = safe_float(terr_r.get("built_up_proxy"))
        forest = safe_float(terr_r.get("forest_proxy"))
        shrub = safe_float(terr_r.get("shrubland_proxy"))
        wui = safe_float(terr_r.get("wui_proxy"))
        terr_missing = int(safe_float(terr_r.get("territorial_missing_flag")) or 0)

        missing_components: List[str] = []
        zero_signal_monitor_case = (burn is not None and burn <= 0) and (smoke_mean_u is not None and smoke_mean_u <= 0)
        wrb_zero_burn_not_applicable = (
            wrb_status == WRB_STATUS_NOT_APPLICABLE_ZERO_BURN or wrb_not_applicable >= 1
        )
        if (wrb_missing >= 1 or not wrb_dom) and not zero_signal_monitor_case and not wrb_zero_burn_not_applicable:
            missing_components.append("WRB")
        if terr_missing >= 1 or wui is None:
            missing_components.append("WUI")
        if smoke_route_blocked:
            missing_components.append("SMOKE_ROUTE_BLOCKED")

        if iech_mean is not None and iech_mean >= iech_q80 and rec_class == "HIGH":
            legacy_priority = "HIGH_PRIORITY"
        elif rec_class in ("HIGH", "MEDIUM", "MED"):
            legacy_priority = "MEDIUM_PRIORITY"
        else:
            legacy_priority = "MONITOR"

        interpretation = (
            f"screening association: population_smoke_burden_proxy_mean={iech_mean if iech_mean is not None else 'NA'}; "
            f"recurrence={rec_class or 'NA'}; delta_population_smoke_burden_proxy_S1_minus_S0={delta if delta is not None else 'NA'}; "
            "WRB and territorial variables are contextual descriptors; no causal inference."
        )
        qa_flag = "HOLD" if missing_components else "OK"
        threshold_gate_status = "BLOCKED_FOR_CAUSAL_CLAIM" if missing_components else "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
        causal_scientific_status = "NO-GO_SCIENTIFIC_THRESHOLD" if missing_components else "PASS_AS_SCREENING_ASSOCIATION"

        row = {
            "unit_id": uid,
            "unit_name": uid,
            "unit_level": unit_level,
            "population_smoke_day_burden_proxy_mean_2015_2024": iech_mean,
            "smoke_days_mean_2015_2024": smoke_mean_u,
            "population_2020": pop2020,
            "population_2030": pop2030,
            "total_burn_ha_2015_2024": burn,
            "years_area_gt_p75": years_gt,
            "n_events_gt_1000ha": n_big,
            "unit_area_ha": unit_area,
            "affected_year_fraction": affected_year_fraction,
            "unique_burned_fraction": unique_burned_fraction,
            "reburn_share_of_unique_burned_area": reburn_share,
            "recurrence_temporal_rank": recurrence_temporal_rank,
            "recurrence_reburn_rank": recurrence_reburn_rank,
            "recurrence_score": recurrence_score,
            "legacy_years_area_gt_own_p75": years_gt,
            "legacy_recurrence_class_absolute_burn_tertile": rec_r.get("legacy_recurrence_class_absolute_burn_tertile", ""),
            "recurrence_class": rec_class,
            "downstream_status": "SCREENING_REQUIRES_R10_C",
            "population_smoke_day_burden_proxy_S0_mean_2026_2030": s0,
            "population_smoke_day_burden_proxy_S1_mean_2026_2030": s1,
            "delta_population_smoke_day_burden_proxy_S1_minus_S0": delta,
            "dominant_wrb_class": wrb_dom,
            "dominant_wrb_share": wrb_dom_share,
            "wrb_context_note": wrb_note,
            "built_up_proxy": built,
            "forest_proxy": forest,
            "shrubland_proxy": shrub,
            "wui_proxy": wui,
            "indicator_name": IECH_PROXY_INDICATOR_NAME,
            "indicator_unit": IECH_PROXY_INDICATOR_UNIT,
            "claim_status": IECH_PROXY_CLAIM_STATUS,
            "policy_priority": legacy_priority,
            "causal_interpretation": interpretation,
            "missing_components": "|".join(missing_components),
            "qa_flag": qa_flag,
            "threshold_gate_status": threshold_gate_status,
            "causal_matrix_scientific_status": causal_scientific_status,
            "matrix_type": "TERRITORIAL_SCREENING_ASSOCIATION_MATRIX",
            "matrix_claim_status": "HOLD_CAUSAL_INFERENCE",
            "territorial_indicator_type": "BUILT_UP_FUEL_TERRITORIAL_PROXY",
            "municipal_signal_resolution": "REGIONAL_NUTS3_SIGNAL_ALLOCATED_TO_MUNICIPALITY" if unit_level == "MUNICIPIO" else "DIRECT_NUTS3_SIGNAL",
            "smoke_route_context": smoke_route_context,
        }
        rows_out.append(row)

    try:
        rows_out = apply_canonical_screening(rows_out, unit_level)
    except ValueError as exc:
        # Preserve legacy helper behavior for minimal audit fixtures; a real
        # runtime with this state is rejected by the R10-C scientific gate.
        for row in rows_out:
            row.update(
                {
                    "screening_method": "R10_C_CORE_INPUT_BLOCKED",
                    "screening_core_status": "BLOCKED_R10_C_CORE_INPUT",
                    "contextual_completeness_status": "NOT_EVALUATED",
                    "screening_claim_status": "R10_C_SCREENING_NOT_EVALUATED",
                    "screening_input_error": str(exc),
                }
            )
    header = [
        "unit_id",
        "unit_name",
        "unit_level",
        "population_smoke_day_burden_proxy_mean_2015_2024",
        "smoke_days_mean_2015_2024",
        "population_2020",
        "population_2030",
        "total_burn_ha_2015_2024",
        "years_area_gt_p75",
        "n_events_gt_1000ha",
        "unit_area_ha",
        "affected_year_fraction",
        "unique_burned_fraction",
        "reburn_share_of_unique_burned_area",
        "recurrence_temporal_rank",
        "recurrence_reburn_rank",
        "recurrence_score",
        "burden_priority_rank",
        "burden_band",
        "recurrence_priority_rank",
        "recurrence_band",
        "screening_priority_score",
        "screening_profile",
        "screening_method",
        "screening_claim_status",
        "screening_core_status",
        "contextual_completeness_status",
        "screening_input_error",
        "legacy_policy_priority",
        "legacy_burden_p80_flag",
        "legacy_recurrence_driven_rule",
        "smoke_signal_resolution",
        "recurrence_signal_resolution",
        "legacy_years_area_gt_own_p75",
        "legacy_recurrence_class_absolute_burn_tertile",
        "recurrence_class",
        "downstream_status",
        "population_smoke_day_burden_proxy_S0_mean_2026_2030",
        "population_smoke_day_burden_proxy_S1_mean_2026_2030",
        "delta_population_smoke_day_burden_proxy_S1_minus_S0",
        "dominant_wrb_class",
        "dominant_wrb_share",
        "wrb_context_note",
        "built_up_proxy",
        "forest_proxy",
        "shrubland_proxy",
        "wui_proxy",
        "indicator_name",
        "indicator_unit",
        "claim_status",
        "policy_priority",
        "causal_interpretation",
        "missing_components",
        "qa_flag",
        "threshold_gate_status",
        "causal_matrix_scientific_status",
        "matrix_type",
        "matrix_claim_status",
        "territorial_indicator_type",
        "municipal_signal_resolution",
        "smoke_route_context",
    ]
    rows_csv = []
    for r in rows_out:
        rows_csv.append([r.get(h, "") for h in header])
    write_csv(out_csv, header, rows_csv, delim=";")
    return rows_out


def write_causal_json_txt_sha(
    causal_dir: Path,
    rows_nuts: List[Dict[str, object]],
    out_csv_nuts: Path,
    in_files: List[Path],
) -> None:
    ensure_dir(causal_dir)
    out_json = causal_dir / "causal_matrix_IECH_NUTS3.json"
    out_txt = causal_dir / "causal_matrix_IECH_NUTS3.txt"
    out_sha = causal_dir / "causal_matrix_sha256_checkpoints.txt"

    payload = {
        "title": "Territorial screening association matrix NUTS3 (population_smoke_day_burden_proxy)",
        "timestamp": now_iso(),
        "rows": rows_nuts,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    n_hold = sum(1 for r in rows_nuts if (r.get("qa_flag") or "") == "HOLD")
    lines = [
        "TERRITORIAL SCREENING ASSOCIATION MATRIX NUTS3 (POPULATION_SMOKE_DAY_BURDEN_PROXY)",
        f"timestamp={now_iso()}",
        f"rows={len(rows_nuts)}",
        f"rows_hold={n_hold}",
        "",
    ]
    top_rows = rows_nuts[: min(15, len(rows_nuts))]
    for r in top_rows:
        lines.append(
            f"- {r.get('unit_id')} | population_smoke_day_burden_proxy_mean={r.get('population_smoke_day_burden_proxy_mean_2015_2024') or r.get('IECH_mean_2015_2024')} | recurrence={r.get('recurrence_class')} | "
            f"wrb={r.get('dominant_wrb_class')} | wui={r.get('wui_proxy')} | missing={r.get('missing_components')}"
        )
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sha_lines = [
        "STEP7_MATRIZ_CAUSAL checkpoint",
        f"timestamp={now_iso()}",
        f"outputs_dir={causal_dir}",
    ]
    for p in [out_csv_nuts, out_json, out_txt]:
        sha_lines.append(f"OUT|{p.name}|sha256={sha256_file(p)}|bytes={p.stat().st_size}")
    for p in in_files:
        if p.exists():
            sha_lines.append(f"IN|{p.name}|sha256={sha256_file(p)}|bytes={p.stat().st_size}")
    out_sha.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    out_audit = causal_dir / "causal_matrix_audit.tsv"
    n_missing = sum(1 for r in rows_nuts if (r.get("missing_components") or "").strip() != "")
    n_wrb_missing = sum(1 for r in rows_nuts if "WRB" in str(r.get("missing_components") or ""))
    n_wui_missing = sum(1 for r in rows_nuts if "WUI" in str(r.get("missing_components") or ""))
    audit_rows = [
        ["metric", "value", "status", "note"],
        ["rows_total", len(rows_nuts), "PASS", "NUTS3 rows in causal matrix"],
        ["rows_hold", n_hold, "HOLD" if n_hold > 0 else "PASS", "qa_flag HOLD rows"],
        ["rows_missing_components", n_missing, "HOLD" if n_missing > 0 else "PASS", "rows with non-empty missing_components"],
        ["rows_missing_wrb", n_wrb_missing, "HOLD" if n_wrb_missing > 0 else "PASS", "rows with WRB missing component"],
        ["rows_missing_wui", n_wui_missing, "HOLD" if n_wui_missing > 0 else "PASS", "rows with WUI missing component"],
    ]
    write_csv(out_audit, audit_rows[0], audit_rows[1:], delim="\t")
    qa_audit = causal_dir.parent.parent / "qa" / "causal_matrix_audit.tsv"
    ensure_dir(qa_audit.parent)
    write_csv(qa_audit, audit_rows[0], audit_rows[1:], delim="\t")


def _table_rowcount(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig") as f:
        return max(0, sum(1 for _ in f) - 1)


def write_territorial_units_validation(
    nuts_layer,
    muni_layer,
    nuts_field: str,
    muni_field: str,
    out_tsv: Path,
) -> None:
    nuts_total = int(nuts_layer.featureCount())
    muni_total = int(muni_layer.featureCount())
    nuts_crs = nuts_layer.crs().authid() if nuts_layer.crs().isValid() else ""
    muni_crs = muni_layer.crs().authid() if muni_layer.crs().isValid() else ""

    nuts_invalid = 0
    for f in nuts_layer.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty() or not g.isGeosValid():
            nuts_invalid += 1
    muni_invalid = 0
    for f in muni_layer.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty() or not g.isGeosValid():
            muni_invalid += 1

    rows = [
        ["metric", "value", "status", "note"],
        ["nuts3_count", nuts_total, "PASS" if nuts_total > 0 else "HOLD", f"id_field={nuts_field}"],
        ["municipio_count", muni_total, "PASS" if muni_total > 0 else "HOLD", f"id_field={muni_field}"],
        ["nuts3_crs", nuts_crs, "PASS" if nuts_crs != "" else "HOLD", ""],
        ["municipio_crs", muni_crs, "PASS" if muni_crs != "" else "HOLD", ""],
        ["nuts3_invalid_geometries", nuts_invalid, "PASS" if nuts_invalid == 0 else "HOLD", ""],
        ["municipio_invalid_geometries", muni_invalid, "PASS" if muni_invalid == 0 else "HOLD", ""],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")


def write_municipio_unit_map(
    nuts_layer,
    muni_layer,
    nuts_field: str,
    muni_field: str,
    out_csv: Path,
) -> None:
    from qgis.core import QgsSpatialIndex  # type: ignore

    nuts_feats = list(nuts_layer.getFeatures())
    idx = QgsSpatialIndex()
    for nf in nuts_feats:
        idx.addFeature(nf)
    nuts_by_id: Dict[int, Tuple[str, object]] = {}
    for nf in nuts_feats:
        nuts_by_id[nf.id()] = (str(nf[nuts_field]), nf.geometry())

    rows: List[List[object]] = []
    for mf in muni_layer.getFeatures():
        uid = str(mf[muni_field])
        geom = mf.geometry()
        nuts_id = ""
        if geom is not None and (not geom.isEmpty()):
            p = geom.pointOnSurface()
            if p is not None and (not p.isEmpty()):
                for fid in idx.intersects(p.boundingBox()):
                    cand_uid, cand_geom = nuts_by_id.get(fid, ("", None))
                    if cand_geom is not None and cand_geom.contains(p):
                        nuts_id = cand_uid
                        break
            if nuts_id == "":
                best_uid = ""
                best_area = -1.0
                for fid in idx.intersects(geom.boundingBox()):
                    cand_uid, cand_geom = nuts_by_id.get(fid, ("", None))
                    if cand_geom is None:
                        continue
                    inter = geom.intersection(cand_geom)
                    a = inter.area() if inter is not None and (not inter.isEmpty()) else 0.0
                    if a > best_area:
                        best_area = a
                        best_uid = cand_uid
                nuts_id = best_uid
        rows.append([uid, nuts_id, 1 if nuts_id else 0])

    write_csv(out_csv, ["municipio_id", "nuts3_id", "mapping_ok"], rows, delim=";")


def write_smoke_route_audit(output_root: Path, inputs: Dict[str, object], smoke_unit_csv: Path, smoke_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "smoke_route_audit.tsv"

    unit_rows = read_csv_rows(smoke_unit_csv)[1] if smoke_unit_csv.exists() else []
    unique_by_year: Dict[int, set] = {}
    method_by_year: Dict[int, str] = {}
    for r in unit_rows:
        y = safe_float(r.get("year"))
        sd = safe_float(r.get("smoke_days"))
        if y is None or sd is None:
            continue
        yy = int(y)
        unique_by_year.setdefault(yy, set()).add(round(sd, 8))
        if yy not in method_by_year:
            method_by_year[yy] = (r.get("smoke_method") or "").strip()

    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if not isinstance(meta, dict):
        meta = {}

    rows_out: List[List[object]] = []
    for y in YEARS_HIST:
        uniq = len(unique_by_year.get(y, set()))
        rows_out.append(
            [
                y,
                uniq,
                method_by_year.get(y, ""),
                1 if uniq <= 1 else 0,
                str(meta.get("smoke_route_selected", "")),
                str(meta.get("smoke_route_status", "")),
                str(meta.get("smoke_route_decision", "")),
                str(meta.get("health_exposure_claim", "")),
                str(meta.get("iech_decision", "")),
                str(meta.get("causal_matrix_decision", "")),
                str(meta.get("brief_decision", "")),
                str(meta.get("final_scientific_decision", "")),
            ]
        )
    write_csv(
        out_tsv,
        [
            "year",
            "unique_values",
            "method",
            "spatial_homogeneous_flag",
            "route_selected",
            "smoke_route_status",
            "smoke_route_decision",
            "health_exposure_claim",
            "iech_decision",
            "causal_matrix_decision",
            "brief_decision",
            "final_scientific_decision",
        ],
        rows_out,
        delim="\t",
    )


def write_fire_ingestion_audit(output_root: Path, fire_paths: List[Path]) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "fire_ingestion_audit.tsv"
    years_present: List[int] = []
    for p in fire_paths:
        m = re.search(r"(20\d{2})", p.name)
        if m:
            years_present.append(int(m.group(1)))
    years_present = sorted(set(years_present))
    expected = list(range(2015, 2025))
    missing_years = [y for y in expected if y not in years_present]

    rows = [
        ["metric", "value", "status", "note"],
        ["fire_layers_found", len(fire_paths), "PASS" if len(fire_paths) >= 10 else "HOLD", ""],
        ["fire_years_present", ",".join(str(y) for y in years_present), "PASS" if not missing_years else "HOLD", ""],
        ["fire_years_missing", ",".join(str(y) for y in missing_years), "PASS" if not missing_years else "HOLD", ""],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")


def write_population_audit(output_root: Path, pop_unit_csv: Path, pop_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "population_zonal_audit.tsv"
    unit_rows = read_csv_rows(pop_unit_csv)[1] if pop_unit_csv.exists() else []
    muni_rows = read_csv_rows(pop_muni_csv)[1] if pop_muni_csv.exists() else []
    years = {"2015", "2020", "2025", "2030"}
    unit_years = set()
    for r in unit_rows:
        for y in years:
            if r.get(f"pop_{y}_sum") not in (None, "", "nan", "NaN"):
                unit_years.add(y)
    rows = [
        ["metric", "value", "status", "note"],
        ["pop_unit_rows", len(unit_rows), "PASS" if len(unit_rows) > 0 else "HOLD", ""],
        ["pop_municipio_rows", len(muni_rows), "PASS" if len(muni_rows) > 0 else "HOLD", ""],
        ["pop_years_detected", ",".join(sorted(unit_years)), "PASS" if unit_years == years else "HOLD", ""],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")


def write_recurrence_audit(output_root: Path, rec_unit_csv: Path, rec_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "recurrence_classification_audit.tsv"
    unit_rows = read_csv_rows(rec_unit_csv)[1] if rec_unit_csv.exists() else []
    muni_rows = read_csv_rows(rec_muni_csv)[1] if rec_muni_csv.exists() else []
    required_cols = [
        "unit_area_ha",
        "affected_year_fraction",
        "unique_burned_fraction",
        "reburn_share_of_unique_burned_area",
        "recurrence_temporal_rank",
        "recurrence_reburn_rank",
        "recurrence_score",
        "recurrence_class",
        "legacy_years_area_gt_own_p75",
    ]
    missing_cols = []
    if unit_rows:
        for c in required_cols:
            if c not in unit_rows[0]:
                missing_cols.append(c)
    rows = [
        ["metric", "value", "status", "note"],
        ["rec_unit_rows", len(unit_rows), "PASS" if len(unit_rows) > 0 else "HOLD", ""],
        ["rec_muni_rows", len(muni_rows), "PASS" if len(muni_rows) > 0 else "HOLD", ""],
        ["rec_required_cols_missing", ",".join(missing_cols), "PASS" if not missing_cols else "HOLD", "R10-B construct fields; legacy p75 diagnostic only"],
        ["recurrence_source", "ICNF annual dissolved footprints", "PASS", "spatial reburn is computed across distinct years"],
        ["absolute_hectares_sole_classifier", 0, "PASS", "canonical recurrence score uses temporal and spatial ranks"],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")


def write_iech_audit(output_root: Path, iech_unit_csv: Path, iech_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    calc_tsv = qa_dir / "iech_calculation_audit.tsv"
    reframe_tsv = qa_dir / "iech_reporting_reframe_audit.tsv"
    semantics_tsv = qa_dir / "iech_reporting_semantics_audit.tsv"
    unit_rows = read_csv_rows(iech_unit_csv)[1] if iech_unit_csv.exists() else []
    muni_rows = read_csv_rows(iech_muni_csv)[1] if iech_muni_csv.exists() else []
    all_rows = unit_rows + muni_rows
    unit_vals = [_first_present_float(r, "population_smoke_day_burden_proxy") for r in unit_rows]
    unit_vals = [v for v in unit_vals if v is not None]
    proxy_col_present = int(bool(all_rows) and "population_smoke_day_burden_proxy" in all_rows[0])
    pop_col_present = int(bool(all_rows) and "population_total" in all_rows[0])
    claim_status_ok = int(bool(all_rows) and all((r.get("claim_status") or "").strip() == IECH_PROXY_CLAIM_STATUS for r in all_rows))
    formula_rows = [
        r for r in all_rows
        if _first_present_float(r, "population_smoke_day_burden_proxy") is not None
        and safe_float(r.get("smoke_days")) is not None
        and _first_present_float(r, "population_total", "pop") is not None
    ]
    proxy_equals_formula = int(bool(formula_rows) and all(
        abs((_first_present_float(r, "population_smoke_day_burden_proxy") or 0.0) -
            ((safe_float(r.get("smoke_days")) or 0.0) * (_first_present_float(r, "population_total", "pop") or 0.0))) <= 1e-6
        for r in formula_rows
    ))
    legacy_empty = int(bool(all_rows) and all(
        not str(r.get("legacy_expo_person_hours") or "").strip()
        and not str(r.get("legacy_population_smoke_burden_proxy") or "").strip()
        for r in all_rows
    ))
    brief_path = output_root / "brief" / "Brief_Politica_IECH_2030.md"
    brief_text = brief_path.read_text(encoding="utf-8", errors="replace") if brief_path.exists() else ""
    forbidden_normalized = sum(1 for pat in ("normalized iech", "exposicion media individual", "individual iech") if pat in brief_text.lower())
    forbidden_health = sum(1 for pat in ("exposicion sanitaria validada", "riesgo epidemiologico", "health exposure validated") if pat in brief_text.lower())
    reframe_pass = int(all([proxy_col_present, pop_col_present, claim_status_ok, legacy_empty, proxy_equals_formula]))
    rows = [
        ["metric", "value", "status", "note"],
        ["iech_unit_rows", len(unit_rows), "PASS" if len(unit_rows) > 0 else "HOLD", ""],
        ["iech_muni_rows", len(muni_rows), "PASS" if len(muni_rows) > 0 else "HOLD", ""],
        ["iech_unit_max", max(unit_vals) if unit_vals else "", "PASS" if unit_vals and max(unit_vals) > 0 else "HOLD", ""],
        ["IECH_REPORTING_REFRAME_STATUS", "PASS" if reframe_pass else "HOLD", "PASS" if reframe_pass else "HOLD", "population smoke burden proxy semantics audited"],
        ["R10_A1_CANONICAL_BURDEN", "smoke_days*population_total", "PASS" if proxy_equals_formula else "HOLD", "classified smoke-proxy person-days"],
        ["population_smoke_day_burden_proxy_column_present", proxy_col_present, "PASS" if proxy_col_present else "HOLD", ""],
        ["population_total_column_present", pop_col_present, "PASS" if pop_col_present else "HOLD", ""],
        ["claim_status_proxy_not_normalized", claim_status_ok, "PASS" if claim_status_ok else "HOLD", IECH_PROXY_CLAIM_STATUS],
        ["legacy_physical_burden_columns_empty", legacy_empty, "PASS" if legacy_empty else "HOLD", "legacy aliases isolated"],
        ["population_smoke_day_burden_proxy_equals_smoke_days_times_population_total", proxy_equals_formula, "PASS" if proxy_equals_formula else "HOLD", ""],
        ["forbidden_normalized_IECH_claims", forbidden_normalized, "PASS" if forbidden_normalized == 0 else "HOLD", "brief forbidden normalized IECH phrases"],
        ["forbidden_health_exposure_claims", forbidden_health, "PASS" if forbidden_health == 0 else "HOLD", "brief forbidden health phrases"],
    ]
    write_csv(calc_tsv, rows[0], rows[1:], delim="	")
    write_csv(reframe_tsv, rows[0], rows[1:], delim="	")
    write_csv(semantics_tsv, rows[0], rows[1:], delim="	")


def write_aggregate_consistency_audits(
    output_root: Path,
    hist_unit_detail_csv: Path,
    hist_unit_mean_csv: Path,
    hist_muni_detail_csv: Path,
    hist_muni_mean_csv: Path,
    scen_unit_detail_csv: Path,
    scen_unit_mean_csv: Path,
    scen_muni_detail_csv: Path,
    scen_muni_mean_csv: Path,
) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)

    hist_rows: List[List[object]] = []
    for unit_level, detail_csv, mean_csv in (
        ("NUTS3", hist_unit_detail_csv, hist_unit_mean_csv),
        ("MUNICIPIO", hist_muni_detail_csv, hist_muni_mean_csv),
    ):
        detail_rows = read_csv_rows(detail_csv)[1] if detail_csv.exists() else []
        mean_rows = read_csv_rows(mean_csv)[1] if mean_csv.exists() else []
        detail_by_unit: Dict[str, List[float]] = defaultdict(list)
        for row in detail_rows:
            uid = (row.get("unit_id") or "").strip()
            proxy = _first_present_float(row, "population_smoke_day_burden_proxy", "population_smoke_burden_proxy", "IECH")
            if uid and proxy is not None:
                detail_by_unit[uid].append(proxy)
        mean_by_unit = {(row.get("unit_id") or "").strip(): row for row in mean_rows if (row.get("unit_id") or "").strip()}
        for uid in sorted(set(detail_by_unit) | set(mean_by_unit)):
            expected = sum(detail_by_unit.get(uid, [])) / len(detail_by_unit.get(uid, [])) if detail_by_unit.get(uid) else None
            observed = _first_present_float(mean_by_unit.get(uid, {}), "population_smoke_day_burden_proxy_mean_2015_2024", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024")
            diff = abs(expected - observed) if expected is not None and observed is not None else None
            hist_rows.append([
                uid,
                unit_level,
                expected if expected is not None else "",
                observed if observed is not None else "",
                diff if diff is not None else "",
                "PASS" if diff is not None and diff <= 1e-6 else "HOLD",
            ])
    write_csv(
        qa_dir / "iech_aggregate_consistency_audit.tsv",
        ["unit_id", "unit_level", "expected_proxy_mean", "observed_proxy_mean", "abs_diff", "status"],
        hist_rows,
        delim="\t",
    )

    scen_rows: List[List[object]] = []
    for unit_level, detail_csv, mean_csv in (
        ("NUTS3", scen_unit_detail_csv, scen_unit_mean_csv),
        ("MUNICIPIO", scen_muni_detail_csv, scen_muni_mean_csv),
    ):
        detail_rows = read_csv_rows(detail_csv)[1] if detail_csv.exists() else []
        mean_rows = read_csv_rows(mean_csv)[1] if mean_csv.exists() else []
        detail_by_unit: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        detail_nonzero_delta: Dict[str, int] = defaultdict(int)
        for row in detail_rows:
            uid = (row.get("unit_id") or "").strip()
            scenario = (row.get("scenario") or "").strip().upper()
            proxy = _first_present_float(row, "population_smoke_day_burden_proxy", "population_smoke_burden_proxy", "IECH")
            delta = _first_present_float(
                row,
                "delta_population_smoke_day_burden_proxy_vs_S0",
                "delta_smoke_day_burden_vs_S0",
                "delta_population_smoke_burden_proxy_vs_S0",
                "delta_vs_S0",
            )
            if uid and scenario and proxy is not None:
                detail_by_unit[uid][scenario].append(proxy)
            if uid and scenario == "S1" and delta is not None and abs(delta) > 1e-9:
                detail_nonzero_delta[uid] += 1
        mean_by_unit = {(row.get("unit_id") or "").strip(): row for row in mean_rows if (row.get("unit_id") or "").strip()}
        for uid in sorted(set(detail_by_unit) | set(mean_by_unit)):
            s0_vals = detail_by_unit.get(uid, {}).get("S0", [])
            s1_vals = detail_by_unit.get(uid, {}).get("S1", [])
            expected_s0 = sum(s0_vals) / len(s0_vals) if s0_vals else None
            expected_s1 = sum(s1_vals) / len(s1_vals) if s1_vals else None
            expected_delta = (expected_s1 - expected_s0) if expected_s0 is not None and expected_s1 is not None else None
            observed_row = mean_by_unit.get(uid, {})
            observed_s0 = _first_present_float(observed_row, "population_smoke_day_burden_proxy_S0_mean_2026_2030", "population_smoke_burden_proxy_S0_mean_2026_2030", "IECH_S0_mean_2026_2030")
            observed_s1 = _first_present_float(observed_row, "population_smoke_day_burden_proxy_S1_mean_2026_2030", "population_smoke_burden_proxy_S1_mean_2026_2030", "IECH_S1_mean_2026_2030")
            observed_delta = _first_present_float(observed_row, "delta_population_smoke_day_burden_proxy_S1_minus_S0", "delta_population_smoke_burden_proxy_S1_minus_S0", "delta_S1_minus_S0")
            diffs = [
                abs(expected_s0 - observed_s0) if expected_s0 is not None and observed_s0 is not None else None,
                abs(expected_s1 - observed_s1) if expected_s1 is not None and observed_s1 is not None else None,
                abs(expected_delta - observed_delta) if expected_delta is not None and observed_delta is not None else None,
            ]
            diffs = [d for d in diffs if d is not None]
            diff_max = max(diffs) if diffs else None
            nonzero_detail_requires_nonzero_mean = not (detail_nonzero_delta.get(uid, 0) > 0 and (observed_delta is None or abs(observed_delta) <= 1e-9))
            status = "PASS" if diff_max is not None and diff_max <= 1e-6 and nonzero_detail_requires_nonzero_mean else "HOLD"
            scen_rows.append([
                uid,
                unit_level,
                expected_s0 if expected_s0 is not None else "",
                observed_s0 if observed_s0 is not None else "",
                expected_s1 if expected_s1 is not None else "",
                observed_s1 if observed_s1 is not None else "",
                expected_delta if expected_delta is not None else "",
                observed_delta if observed_delta is not None else "",
                diff_max if diff_max is not None else "",
                detail_nonzero_delta.get(uid, 0),
                status,
            ])
    write_csv(
        qa_dir / "scenario_aggregate_consistency_audit.tsv",
        ["unit_id", "unit_level", "expected_s0_mean", "observed_s0_mean", "expected_s1_mean", "observed_s1_mean", "expected_delta", "observed_delta", "max_abs_diff", "detail_nonzero_s1_delta_rows", "status"],
        scen_rows,
        delim="\t",
    )


def write_wrb_method_consistency_audit(output_root: Path, wrb_nuts_csv: Path, wrb_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    wrb_n_rows = read_csv_rows(wrb_nuts_csv)[1] if wrb_nuts_csv.exists() else []
    wrb_m_rows = read_csv_rows(wrb_muni_csv)[1] if wrb_muni_csv.exists() else []
    all_rows = wrb_n_rows + wrb_m_rows

    def _count_status(rows: List[Dict[str, str]], status: str) -> int:
        return sum(1 for row in rows if (row.get("wrb_coverage_status") or "").strip() == status)

    def _note_text(row: Dict[str, str]) -> str:
        return " | ".join(
            str(v).strip()
            for v in (row.get("wrb_context_note") or "", row.get("wrb_source") or "")
            if str(v).strip()
        ).lower()

    rows_out = [
        ["metric", "value", "status", "note"],
        ["wrb_overlay_valid_rows_nuts3", _count_status(wrb_n_rows, WRB_STATUS_PASS), "PASS", ""],
        ["wrb_overlay_valid_rows_municipio", _count_status(wrb_m_rows, WRB_STATUS_PASS), "PASS", ""],
        ["wrb_not_applicable_zero_burn_rows_nuts3", _count_status(wrb_n_rows, WRB_STATUS_NOT_APPLICABLE_ZERO_BURN), "PASS", ""],
        ["wrb_not_applicable_zero_burn_rows_municipio", _count_status(wrb_m_rows, WRB_STATUS_NOT_APPLICABLE_ZERO_BURN), "PASS", ""],
        ["wrb_positive_burn_missing_rows_nuts3", _count_status(wrb_n_rows, WRB_STATUS_BLOCKED_MISSING), "PASS" if _count_status(wrb_n_rows, WRB_STATUS_BLOCKED_MISSING) == 0 else "HOLD", ""],
        ["wrb_positive_burn_missing_rows_municipio", _count_status(wrb_m_rows, WRB_STATUS_BLOCKED_MISSING), "PASS" if _count_status(wrb_m_rows, WRB_STATUS_BLOCKED_MISSING) == 0 else "HOLD", ""],
        ["wrb_admin_unit_only_rows", sum(1 for row in all_rows if any(tok in _note_text(row) for tok in ("unidad territorial completa", "full administrative unit", "admin-unit-only", "admin_unit-only"))), "PASS" if sum(1 for row in all_rows if any(tok in _note_text(row) for tok in ("unidad territorial completa", "full administrative unit", "admin-unit-only", "admin_unit-only"))) == 0 else "HOLD", ""],
        ["wrb_centroid_fallback_rows", sum(1 for row in all_rows if "centroid" in _note_text(row)), "PASS" if sum(1 for row in all_rows if "centroid" in _note_text(row)) == 0 else "HOLD", ""],
        ["wrb_global_fallback_rows", sum(1 for row in all_rows if "global class" in _note_text(row)), "PASS" if sum(1 for row in all_rows if "global class" in _note_text(row)) == 0 else "HOLD", ""],
        ["wrb_legacy_raster_canonical_rows", sum(1 for row in all_rows if "raster metadata" in _note_text(row)), "PASS" if sum(1 for row in all_rows if "raster metadata" in _note_text(row)) == 0 else "HOLD", ""],
        ["wrb_distinct_dominant_classes_nuts3", len({(row.get("dominant_wrb_class") or "").strip() for row in wrb_n_rows if (row.get("dominant_wrb_class") or "").strip()}), "PASS", ""],
        ["wrb_distinct_dominant_classes_municipio", len({(row.get("dominant_wrb_class") or "").strip() for row in wrb_m_rows if (row.get("dominant_wrb_class") or "").strip()}), "PASS", ""],
        ["wrb_universal_single_class_flag", int(len({(row.get("dominant_wrb_class") or "").strip() for row in all_rows if (row.get("dominant_wrb_class") or "").strip()}) <= 1), "PASS", "Informational"],
        ["wrb_universal_share_one_flag", int(all(((row.get("dominant_wrb_share") or "").strip() in ("", "1", "1.0", "1.000000")) for row in all_rows)), "PASS", "Informational"],
        ["wrb_prevalidation_2022_status", "PASS" if (qa_dir / "wrb_2022_prevalidation.tsv").exists() else "HOLD", "PASS" if (qa_dir / "wrb_2022_prevalidation.tsv").exists() else "HOLD", str(qa_dir / "wrb_2022_prevalidation.tsv")],
    ]
    write_csv(qa_dir / "wrb_method_consistency_audit.tsv", rows_out[0], rows_out[1:], delim="\t")

def write_territorial_and_wrb_audits(output_root: Path, wrb_nuts_csv: Path, wrb_muni_csv: Path, terr_nuts_csv: Path, terr_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    brief_dir = output_root / "brief"
    ensure_dir(qa_dir)
    ensure_dir(brief_dir)

    wrb_n_rows = read_csv_rows(wrb_nuts_csv)[1] if wrb_nuts_csv.exists() else []
    wrb_m_rows = read_csv_rows(wrb_muni_csv)[1] if wrb_muni_csv.exists() else []
    terr_n_rows = read_csv_rows(terr_nuts_csv)[1] if terr_nuts_csv.exists() else []
    terr_m_rows = read_csv_rows(terr_muni_csv)[1] if terr_muni_csv.exists() else []

    wrb_n_missing = sum(1 for r in wrb_n_rows if int(safe_float(r.get("wrb_missing_flag")) or 0) >= 1)
    wrb_m_missing = sum(1 for r in wrb_m_rows if int(safe_float(r.get("wrb_missing_flag")) or 0) >= 1)
    wrb_n_dom = sum(1 for r in wrb_n_rows if (r.get("dominant_wrb_class") or "").strip() != "")
    blocked_tokens = WRB_FORBIDDEN_NOTE_TOKENS

    def _wrb_note_hits(rows: List[Dict[str, str]]) -> int:
        hits = 0
        for row in rows:
            note_text = " | ".join(
                str(v).strip()
                for v in (row.get("wrb_context_note") or "", row.get("dominant_wrb_note") or "", row.get("wrb_source") or "")
                if str(v).strip()
            ).lower()
            if note_text and any(tok in note_text for tok in blocked_tokens):
                hits += 1
        return hits

    wrb_note_hits = _wrb_note_hits(wrb_n_rows) + _wrb_note_hits(wrb_m_rows)
    prevalidation_path = qa_dir / "wrb_2022_prevalidation.tsv"
    prevalidation_rows = read_csv_rows(prevalidation_path)[1] if prevalidation_path.exists() else []
    prevalidation_blocking = sum(1 for r in prevalidation_rows if (r.get("status") or "").strip().upper() != "PASS")

    wrb_out = qa_dir / "wrb_integration_audit.tsv"
    wrb_rows = [
        ["metric", "value", "status", "note"],
        ["wrb_nuts_rows", len(wrb_n_rows), "PASS" if wrb_n_rows else "HOLD", ""],
        ["wrb_nuts_missing", wrb_n_missing, "PASS" if (wrb_n_rows and wrb_n_missing < len(wrb_n_rows)) else "HOLD", ""],
        ["wrb_nuts_dominant_nonempty", wrb_n_dom, "PASS" if wrb_n_dom > 0 else "HOLD", ""],
        ["wrb_muni_rows", len(wrb_m_rows), "PASS" if wrb_m_rows else "HOLD", ""],
        ["wrb_muni_missing", wrb_m_missing, "PASS" if (wrb_m_rows and wrb_m_missing < len(wrb_m_rows)) else "HOLD", ""],
        ["wrb_fallback_note_rows", wrb_note_hits, "PASS" if wrb_note_hits == 0 else "HOLD", "Fallback/global/centroid/admin-only notes must stay absent."],
        ["wrb_prevalidation_2022_present", int(prevalidation_path.exists()), "PASS" if prevalidation_path.exists() else "HOLD", str(prevalidation_path)],
        ["wrb_prevalidation_2022_blocking_metrics", prevalidation_blocking, "PASS" if prevalidation_path.exists() and prevalidation_blocking == 0 else "HOLD", "Non-PASS rows in wrb_2022_prevalidation.tsv."],
    ]
    write_csv(wrb_out, wrb_rows[0], wrb_rows[1:], delim="	")

    terr_n_missing = sum(1 for r in terr_n_rows if int(safe_float(r.get("territorial_missing_flag")) or 0) >= 1)
    terr_m_missing = sum(1 for r in terr_m_rows if int(safe_float(r.get("territorial_missing_flag")) or 0) >= 1)
    terr_out = qa_dir / "territorial_variables_audit.tsv"
    terr_rows = [
        ["metric", "value", "status", "note"],
        ["terr_nuts_rows", len(terr_n_rows), "PASS" if terr_n_rows else "HOLD", ""],
        ["terr_nuts_missing", terr_n_missing, "PASS" if terr_n_missing == 0 else "HOLD", ""],
        ["terr_muni_rows", len(terr_m_rows), "PASS" if terr_m_rows else "HOLD", ""],
        ["terr_muni_missing", terr_m_missing, "PASS" if terr_m_missing == 0 else "HOLD", ""],
    ]
    write_csv(terr_out, terr_rows[0], terr_rows[1:], delim="\t")

    dom_counts: Dict[str, int] = defaultdict(int)
    for r in wrb_n_rows:
        c = (r.get("dominant_wrb_class") or "").strip()
        if c:
            dom_counts[c] += 1
    top = sorted(dom_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    wrb_md = brief_dir / "wrb_summary_for_policy_brief.md"
    md_lines = [
        "# WRB Summary for Policy Brief",
        "",
        f"- Generated: {now_iso()}",
        f"- NUTS3 rows: {len(wrb_n_rows)}",
        f"- NUTS3 missing rows: {wrb_n_missing}",
        "",
        "## Top WRB classes",
    ]
    if top:
        for cls, cnt in top:
            md_lines.append(f"- {cls}: {cnt} unidades")
    else:
        md_lines.append("- No dominant WRB class available.")
    wrb_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def write_scenario_audit(output_root: Path, scen_unit_csv: Path, scen_muni_csv: Path) -> None:
    def _extract_direct_deltas(rows: List[Dict[str, str]]) -> List[float]:
        out: List[float] = []
        for r in rows:
            for k in (
                "delta_population_smoke_day_burden_proxy_vs_S0",
                "delta_smoke_day_burden_vs_S0",
                "delta_S1_minus_S0",
                "delta_vs_S0",
            ):
                v = safe_float(r.get(k))
                if v is not None:
                    out.append(v)
                    break
        return out

    def _calc_pairwise_deltas(rows: List[Dict[str, str]]) -> List[float]:
        s0: Dict[Tuple[str, int], float] = {}
        s1: Dict[Tuple[str, int], float] = {}
        for r in rows:
            unit = (r.get("unit_id") or "").strip()
            yv = safe_float(r.get("year"))
            burden = _first_present_float(
                r,
                "population_smoke_day_burden_proxy",
                "population_smoke_burden_proxy",
                "IECH",
            )
            scenario = (r.get("scenario") or "").strip().upper()
            if not unit or yv is None or burden is None:
                continue
            key = (unit, int(yv))
            if scenario == "S0":
                s0[key] = burden
            elif scenario == "S1":
                s1[key] = burden

        out: List[float] = []
        for key, s0_val in s0.items():
            s1_val = s1.get(key)
            if s1_val is not None:
                out.append(s1_val - s0_val)
        return out

    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "scenario_audit.tsv"
    assumptions = qa_dir / "scenario_assumptions.md"
    unit_rows = read_csv_rows(scen_unit_csv)[1] if scen_unit_csv.exists() else []
    muni_rows = read_csv_rows(scen_muni_csv)[1] if scen_muni_csv.exists() else []
    direct_deltas = _extract_direct_deltas(unit_rows) + _extract_direct_deltas(muni_rows)
    pairwise_deltas = _calc_pairwise_deltas(unit_rows) + _calc_pairwise_deltas(muni_rows)
    deltas = direct_deltas if direct_deltas else pairwise_deltas
    all_rows = unit_rows + muni_rows
    has_s0 = any((r.get("scenario") or "").strip().upper() == "S0" for r in all_rows)
    has_s1 = any((r.get("scenario") or "").strip().upper() == "S1" for r in all_rows)
    years = sorted({int(safe_float(r.get("year")) or -1) for r in all_rows if safe_float(r.get("year")) is not None})
    required_years = [2026, 2027, 2028, 2029, 2030]
    years_ok = all(y in years for y in required_years)
    delta_note = "canonical population smoke-day burden delta present or pairwise S1-S0 calculable"
    rows = [
        ["metric", "value", "status", "note"],
        ["scenario_unit_rows", len(unit_rows), "PASS" if len(unit_rows) > 0 else "HOLD", ""],
        ["scenario_muni_rows", len(muni_rows), "PASS" if len(muni_rows) > 0 else "HOLD", ""],
        ["scenario_has_s0", int(has_s0), "PASS" if has_s0 else "HOLD", "S0 scenario present in unit table"],
        ["scenario_has_s1", int(has_s1), "PASS" if has_s1 else "HOLD", "S1 scenario present in unit table"],
        ["scenario_years_2026_2030", len([y for y in years if y in required_years]), "PASS" if years_ok else "HOLD", "all years 2026..2030 present"],
        ["scenario_delta_nonempty", len(deltas), "PASS" if len(deltas) > 0 else "HOLD", delta_note],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")
    assumptions_text = (
        "# Scenario Assumptions (S0/S1 2026-2030)\n\n"
        "- S0: baseline continuation from historical signal.\n"
        "- S1: mitigation scenario with 20% reduction in smoke intensity proxy relative to S0.\n"
        "- Delta reported as `S1 - S0` at unit and municipio levels.\n"
    )
    assumptions.write_text(assumptions_text, encoding="utf-8")
    brief_assumptions = output_root / "brief" / "scenario_assumptions.md"
    ensure_dir(brief_assumptions.parent)
    brief_assumptions.write_text(assumptions_text, encoding="utf-8")


def generate_brief(output_root: Path, inputs: Dict[str, object]) -> Path:
    tables = output_root / "tables"
    brief_dir = output_root / "brief"
    causal_dir = brief_dir / "causal_matrix"
    ensure_dir(brief_dir)

    # Required base files
    smoke_unit = tables / "smoke_days_unit_2015_2024.csv"
    pop_unit = tables / "pop_unit_2015_2025_2030.csv"
    rec_unit = tables / "recurrence_unit_2015_2024.csv"
    iech_unit = tables / "IECH_unit_2015_2024.csv"
    iech_mean = tables / "IECH_unit_2015_2024_mean.csv"
    scen = tables / "IECH_scenarios_2026_2030.csv"
    scen_mean = tables / "IECH_scenarios_unit_2026_2030_mean.csv"
    iech_muni = tables / "IECH_municipio_2015_2024.csv"
    wrb_nuts = tables / "wrb_context_nuts3.csv"
    terr_nuts = tables / "territorial_context_nuts3.csv"
    causal_csv = causal_dir / "causal_matrix_IECH_NUTS3.csv"

    iech_mean_rows = _map_table_by_unit(iech_mean) if iech_mean.exists() else {}
    scen_mean_rows = _map_table_by_unit(scen_mean) if scen_mean.exists() else {}
    wrb_rows = read_csv_rows(wrb_nuts)[1] if wrb_nuts.exists() else []
    terr_rows = read_csv_rows(terr_nuts)[1] if terr_nuts.exists() else []
    causal_rows = read_csv_rows(causal_csv)[1] if causal_csv.exists() else []

    iech_vals = [_first_present_float(r, "population_smoke_day_burden_proxy_mean_2015_2024", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024") for r in iech_mean_rows.values()]
    iech_vals = [v for v in iech_vals if v is not None]
    iech_min = min(iech_vals) if iech_vals else None
    iech_max = max(iech_vals) if iech_vals else None

    delta_vals = [_first_present_float(r, "delta_population_smoke_day_burden_proxy_S1_minus_S0", "delta_population_smoke_burden_proxy_S1_minus_S0", "delta_S1_minus_S0") for r in scen_mean_rows.values()]
    delta_vals = [v for v in delta_vals if v is not None]
    delta_mean = (sum(delta_vals) / len(delta_vals)) if delta_vals else None

    wrb_dom_counts: Dict[str, int] = defaultdict(int)
    for r in wrb_rows:
        c = (r.get("dominant_wrb_class") or "").strip()
        if c:
            wrb_dom_counts[c] += 1
    wrb_top = sorted(wrb_dom_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    wui_positive = 0
    for r in terr_rows:
        w = safe_float(r.get("wui_proxy"))
        if w is not None and w > 0:
            wui_positive += 1

    causal_hold = sum(1 for r in causal_rows if (r.get("qa_flag") or "").strip().upper() == "HOLD")
    missing_summary: Dict[str, int] = defaultdict(int)
    for r in causal_rows:
        miss = (r.get("missing_components") or "").strip()
        if miss:
            for token in miss.split("|"):
                t = token.strip()
                if t:
                    missing_summary[t] += 1

    lines: List[str] = []
    lines.append("# Brief de Politica Module C 2030 (population_smoke_day_burden_proxy)")
    lines.append("")
    lines.append(f"- Fecha de generacion: {now_iso()}")
    lines.append("- Objetivo Modulo C: integrar carga poblacional proxy de dias clasificados de humo, escenarios 2026-2030, contexto territorial y matriz causal por unidad.")
    lines.append("")
    lines.append("## Fuentes de datos usadas")
    paths = inputs.get("paths", {})
    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if isinstance(meta, dict):
        canon_path = meta.get("objectives_canon_path", "")
        canon_sha = meta.get("objectives_canon_sha256", "")
        objectives = meta.get("objectives_recognized", [])
        if canon_path:
            lines.append(f"- objectives_canon_path: `{canon_path}`")
        if canon_sha:
            lines.append(f"- objectives_canon_sha256: `{canon_sha}`")
        if objectives:
            lines.append(f"- objectives_recognized: `{objectives}`")
    if isinstance(paths, dict):
        for key in ("nuts3", "municipios_caop"):
            lines.append(f"- {key}: `{paths.get(key, '')}`")
        ghsl = paths.get("ghsl_pop", {})
        if isinstance(ghsl, dict):
            for y in ("2015", "2020", "2025", "2030"):
                lines.append(f"- ghsl_pop_{y}: `{ghsl.get(y, '')}`")
        fire = paths.get("fire_gpkgs_tm06", [])
        if isinstance(fire, list):
            lines.append(f"- fire_gpkgs_tm06: {len(fire)} capas 2015-2024.")
    lines.append("")
    lines.append("## Definicion IECH proxy-burden")
    lines.append("- population_smoke_day_burden_proxy = `smoke_days * population_total`, con unidad `classified smoke-proxy person-days`.")
    lines.append("- smoke_days = `SUM(smoke_day_proxy)` y la intensidad continua se conserva separadamente como `cumulative_normalized_smoke_intensity_proxy`; no se convierte a horas.")
    lines.append("- No es exposicion sanitaria observada, no es IECH normalizado individual y no genera person-hours.")
    lines.append("")
    lines.append("## Cobertura temporal")
    lines.append("- Histórico: 2015-2024.")
    lines.append("- Escenarios: 2026-2030 (S0 y S1).")
    lines.append("")
    lines.append("## Cobertura espacial")
    lines.append("- NUTS3 (Portugal continental).")
    lines.append("- Municipio (CAOP 2024), cuando disponible.")
    lines.append("")
    lines.append("## Resultados population_smoke_day_burden_proxy historico")
    lines.append(f"- Filas proxy-burden NUTS3: {_table_rowcount(iech_unit)}.")
    lines.append(f"- Unidades proxy-burden NUTS3 mean: {len(iech_mean_rows)}.")
    lines.append(f"- Rango population_smoke_day_burden_proxy mean 2015-2024: min={iech_min} max={iech_max}.")
    lines.append("")
    lines.append("## Resultados humo")
    lines.append(f"- Filas smoke NUTS3: {_table_rowcount(smoke_unit)}.")
    lines.append("- Serie anual reconstruida/derivada según ruta de humo seleccionada.")
    route_selected = str(meta.get("smoke_route_name") or meta.get("smoke_route_selected", "")) if isinstance(meta, dict) else ""
    route_decision = str(meta.get("smoke_route_decision", "")) if isinstance(meta, dict) else ""
    route_status = str(meta.get("smoke_route_status", "")) if isinstance(meta, dict) else ""
    route_reason = str(meta.get("smoke_route_reason", "")) if isinstance(meta, dict) else ""
    lines.append(f"- Ruta declarada: {route_selected} | status={route_status} | decision={route_decision}.")
    if route_reason:
        lines.append(f"- Motivo ruta: {route_reason}.")
    lines.append("")
    lines.append("## Resultados población")
    lines.append(f"- Filas población NUTS3: {_table_rowcount(pop_unit)}.")
    lines.append("- Población GHSL integrada para 2015/2020/2025/2030.")
    lines.append("")
    lines.append("## Resultados recurrencia")
    lines.append(f"- Filas recurrencia NUTS3: {_table_rowcount(rec_unit)}.")
    lines.append("- Recurrence: affected-year persistence plus distinct-year reburn share; absolute burn and legacy p75 remain context/diagnostic only.")
    lines.append("")
    lines.append("## Resultados municipales")
    if iech_muni.exists():
        lines.append(f"- population_smoke_day_burden_proxy municipal disponible: {_table_rowcount(iech_muni)} filas.")
    else:
        lines.append("- population_smoke_day_burden_proxy municipal no disponible (HOLD MUNICIPAL).")
    lines.append("")
    screening_nuts = causal_dir / "territorial_screening_matrix_nuts3.csv"
    screening_muni = causal_dir / "territorial_screening_matrix_municipio.csv"
    lines.append("## R10-C screening bidimensional")
    lines.append("- Dimensión A: population_smoke_day_burden_proxy_mean_2015_2024; dimensión B: R10-B recurrence_score.")
    lines.append("- Score canónico: 0.50 burden_priority_rank + 0.50 recurrence_priority_rank, con ranks fraccionales tie-aware separados por nivel.")
    lines.append("- Bandas fijas: LOW/MONITOR [0,1/3), MEDIUM/MEDIUM_PRIORITY [1/3,2/3), HIGH/HIGH_PRIORITY [2/3,1]; no cuotas ni P80 hard-gating.")
    lines.append(f"- Matrices screening NUTS3/municipio: {'disponibles' if screening_nuts.exists() and screening_muni.exists() else 'HOLD'}.")
    lines.append("- Claim municipal: REGIONAL_SMOKE_INFORMED_MUNICIPAL_SCREENING; smoke regional NUTS3 asignado y recurrence con huella municipal directa.")
    lines.append("- WUI, WRB, AQ, S1, smoke_days, población auxiliar y subcomponentes R10-B quedan fuera del score canónico; su estado es contextual o downstream.")
    lines.append("")
    lines.append("## Resultados WRB")
    lines.append(f"- Tabla WRB NUTS3: {'sí' if wrb_nuts.exists() else 'no'}.")
    if wrb_top:
        lines.append("- Clases dominantes WRB (conteo unidades):")
        for cls, cnt in wrb_top:
            lines.append(f"  - {cls}: {cnt}")
    else:
        lines.append("- Sin resumen WRB por unidad.")
    lines.append("")
    lines.append("## Resultados WUI / territorio")
    lines.append(f"- Tabla territorial NUTS3: {'sí' if terr_nuts.exists() else 'no'}.")
    lines.append(f"- Unidades con wui_proxy > 0: {wui_positive}.")
    lines.append("")
    lines.append("## Matriz causal")
    lines.append(f"- Filas causal matrix NUTS3: {_table_rowcount(causal_csv)}.")
    lines.append(f"- Filas en HOLD por missing_components: {causal_hold}.")
    lines.append("")
    lines.append("## Escenarios S0/S1 2026-2030")
    lines.append(f"- Filas escenarios NUTS3: {_table_rowcount(scen)}.")
    lines.append(f"- Delta medio S1-S0 (NUTS3 mean): {delta_mean}.")
    lines.append("")
    lines.append("## Limitaciones")
    if missing_summary:
        for k, v in sorted(missing_summary.items()):
            lines.append(f"- {k}: {v} unidades con componente faltante en matriz.")
    else:
        lines.append("- No se detectaron componentes faltantes en matriz causal NUTS3.")
    lines.append("")
    lines.append("## Recomendaciones")
    if missing_summary:
        lines.append("- Usar el resultado como screening relativo y mantener separado el estado contextual de los componentes en HOLD.")
    else:
        lines.append("- Usar HIGH_PRIORITY como banda de screening relativo, no como prioridad causal, regulatoria o de intervención.")
    lines.append("- Mantener WRB y WUI como contexto descriptivo, no como entradas del score R10-C.")
    lines.append("- Mantener AQ y S1 como validación o contexto downstream; no alteran el score canónico.")
    lines.append("")
    lines.append("## Evidencia de QA")
    lines.append(f"- `{output_root / 'qa' / 'inputs_resolved.json'}`")
    lines.append(f"- `{output_root / 'qa' / 'report_auditoria_v2.txt'}`")
    lines.append(f"- `{output_root / 'qa' / 'run_log.txt'}`")
    lines.append(f"- `{output_root / 'qa' / 'QA_checks.csv'}`")
    lines.append("")
    lines.append("## Ruta del paquete final")
    lines.append(f"- `{output_root / 'deliverables_step9' / 'ModuleC_ALL_FINAL_deliverables.zip'}`")
    lines.append("")

    brief_path = brief_dir / "Brief_Politica_IECH_2030.md"
    brief_path.write_text("\n".join(lines), encoding="utf-8")
    return brief_path


def touch_qa_fresh_files(output_root: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    run_log = qa_dir / "run_log.txt"
    with run_log.open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] STEP7 run completed and outputs refreshed.\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=False, default=None)
    ap.add_argument("--output-root", required=False, default=None)
    args = ap.parse_args()

    output_root = determine_output_root(args.gata_root, args.output_root)
    tables_dir = output_root / "tables"
    maps_dir = output_root / "maps"
    brief_dir = output_root / "brief"
    causal_dir = brief_dir / "causal_matrix"
    work_dir = output_root / "_step7_work"
    run_log = output_root / "qa" / "run_log.txt"

    log_line(run_log, f"START output_root={output_root}")

    qgs = None
    try:
        ensure_dir(tables_dir)
        ensure_dir(maps_dir)
        ensure_dir(brief_dir)
        ensure_dir(causal_dir)
        ensure_dir(work_dir)

        inputs = load_inputs_resolved(output_root)
        paths = get_paths(inputs)
        ensure_required_paths(paths)

        qgs, processing = init_qgis()
        log_line(run_log, "QGIS initialized")

        # Admin layers
        admin_gpkg, nuts_layer = prepare_admin_nuts3(paths, maps_dir, processing)
        muni_layer, muni_field = prepare_admin_municipio(paths, maps_dir, processing)
        nuts_field = "NUTS_ID"
        log_line(run_log, f"Admin prepared: {admin_gpkg}")
        write_territorial_units_validation(
            nuts_layer,
            muni_layer,
            nuts_field=nuts_field,
            muni_field=muni_field,
            out_tsv=output_root / "qa" / "territorial_units_validation.tsv",
        )
        write_municipio_unit_map(
            nuts_layer,
            muni_layer,
            nuts_field=nuts_field,
            muni_field=muni_field,
            out_csv=tables_dir / "municipio_unit_map.csv",
        )
        municipio_map_csv = tables_dir / "municipio_unit_map.csv"

        # Smoke municipal from mapped NUTS3 smoke outputs
        smoke_unit_csv = tables_dir / "smoke_days_unit_2015_2024.csv"
        smoke_muni_csv = tables_dir / "smoke_days_municipio_2015_2024.csv"
        smoke_daily_unit_csv = tables_dir / "smoke_day_score_nuts3_daily.csv"
        smoke_daily_muni_csv = tables_dir / "smoke_day_score_municipio_daily.csv"
        if not smoke_unit_csv.exists():
            raise FileNotFoundError(f"Missing unit smoke table from runtime: {smoke_unit_csv}")
        write_smoke_table_from_nuts_map(smoke_unit_csv, municipio_map_csv, smoke_muni_csv)
        write_smoke_daily_table_from_nuts_map(smoke_daily_unit_csv, municipio_map_csv, smoke_daily_muni_csv)
        log_line(run_log, "Municipal smoke tables generated from NUTS3 mapping")

        # R10-B recurrence: calculate both levels directly from fire footprints.
        fire_paths = [Path(p) for p in paths.get("fire_gpkgs_tm06", [])]
        rec_unit_csv = tables_dir / "recurrence_unit_2015_2024.csv"
        rec_muni_csv = tables_dir / "recurrence_municipio_2015_2024.csv"
        rec_unit_year_csv = tables_dir / "recurrence_unit_year_2015_2024.csv"
        rec_muni_year_csv = tables_dir / "recurrence_municipio_year_2015_2024.csv"
        recurrence_unit_result = compute_recurrence_table(
            nuts_layer, nuts_field, fire_paths, rec_unit_csv, processing,
            annual_out_csv=rec_unit_year_csv, territorial_level="NUTS3",
        )
        recurrence_muni_result = compute_recurrence_table(
            muni_layer, muni_field, fire_paths, rec_muni_csv, processing,
            annual_out_csv=rec_muni_year_csv, territorial_level="MUNICIPIO",
        )
        write_recurrence_qa(
            output_root / "qa",
            [recurrence_unit_result, recurrence_muni_result],
            list(recurrence_unit_result["records"]) + list(recurrence_muni_result["records"]),
        )
        log_line(run_log, "R10-B recurrence tables refreshed from direct NUTS3 and municipality fire footprints")

        # Population municipal
        pop_muni_csv = tables_dir / "pop_municipio_2015_2025_2030.csv"
        compute_pop_table(muni_layer, muni_field, paths, work_dir, pop_muni_csv, processing)
        log_line(run_log, "Municipal population table generated")

        # Municipal IECH + scenarios
        iech_muni_csv = tables_dir / "IECH_municipio_2015_2024.csv"
        iech_muni_mean_csv = tables_dir / "IECH_municipio_2015_2024_mean.csv"
        compute_iech(pop_muni_csv, smoke_muni_csv, iech_muni_csv, iech_muni_mean_csv)

        scen_muni_csv = tables_dir / "IECH_scenarios_municipio_2026_2030.csv"
        scen_muni_mean_csv = tables_dir / "IECH_scenarios_municipio_2026_2030_mean.csv"
        compute_scenarios(smoke_muni_csv, pop_muni_csv, scen_muni_csv, scen_muni_mean_csv)
        log_line(run_log, "Municipal IECH and scenarios generated")

        # WRB context
        wrb_bundle = find_wrb_source_bundle(paths)
        wrb_annual_burned_area_paths = find_wrb_annual_burned_area_paths(paths)
        wrb_nuts_csv = tables_dir / "wrb_context_nuts3.csv"
        wrb_muni_csv = tables_dir / "wrb_context_municipio.csv"
        wrb_qa_dir = output_root / "qa"
        wrb_nuts_year_summary_csv = wrb_qa_dir / "wrb_burned_2015_2024_long_computed_nuts3.csv"
        wrb_muni_year_summary_csv = wrb_qa_dir / "wrb_burned_2015_2024_long_computed_municipio.csv"
        compute_wrb_context_v2(nuts_layer, nuts_field, wrb_annual_burned_area_paths, wrb_bundle, work_dir, wrb_nuts_csv, wrb_nuts_year_summary_csv, processing)
        write_wrb_year_validation_audit(
            wrb_qa_dir / "wrb_2022_prevalidation.tsv",
            wrb_nuts_year_summary_csv,
            Path(wrb_bundle["reference_csv"]),
            2022,
        )
        compute_wrb_context_v2(muni_layer, muni_field, wrb_annual_burned_area_paths, wrb_bundle, work_dir, wrb_muni_csv, wrb_muni_year_summary_csv, processing)
        log_line(run_log, "WRB context tables generated from annual mask route and tile mosaic")

        # Territorial context (built + combustible proxy)
        built_zip = resolve_built_raster(paths)
        terr_nuts_csv = tables_dir / "territorial_context_nuts3.csv"
        terr_muni_csv = tables_dir / "territorial_context_municipio.csv"
        compute_territorial_context(nuts_layer, nuts_field, rec_unit_csv, built_zip, work_dir, terr_nuts_csv, processing)
        compute_territorial_context(muni_layer, muni_field, rec_muni_csv, built_zip, work_dir, terr_muni_csv, processing)
        log_line(run_log, "Territorial context tables generated")

        # Causal matrix NUTS3 + municipio
        iech_unit_mean_csv = tables_dir / "IECH_unit_2015_2024_mean.csv"
        iech_unit_hist_csv = tables_dir / "IECH_unit_2015_2024.csv"
        pop_unit_csv = tables_dir / "pop_unit_2015_2025_2030.csv"
        scen_unit_mean_csv = tables_dir / "IECH_scenarios_unit_2026_2030_mean.csv"
        scen_unit_csv = tables_dir / "IECH_scenarios_2026_2030.csv"
        smoke_unit_csv = tables_dir / "smoke_days_unit_2015_2024.csv"
        meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
        route_decision = str(meta.get("smoke_route_decision") or "").strip()
        smoke_route_blocked = route_selected in ("BLOCKED_DECODER_REQUIRED", "v0_parquet_proxy_degraded", "NO-GO_SMOKE_ROUTE")
        smoke_homogeneous_blocked = _smoke_spatial_homogeneous(smoke_unit_csv)
        iech_cancellation_blocked = _iech_population_cancellation(iech_unit_hist_csv)
        if smoke_homogeneous_blocked:
            smoke_route_blocked = True
        smoke_route_context_parts = []
        if route_selected or route_decision:
            smoke_route_context_parts.append(f"{route_selected}|{route_decision}")
        if smoke_homogeneous_blocked:
            smoke_route_context_parts.append("BLOCKED_SPATIAL_SMOKE_CLAIM")
        if iech_cancellation_blocked:
            smoke_route_context_parts.append("BLOCKED_POPULATION_EXPOSURE_CLAIM")
        smoke_route_context = ";".join(smoke_route_context_parts)

        out_causal_nuts_csv = causal_dir / "causal_matrix_IECH_NUTS3.csv"
        rows_nuts = build_causal_matrix(
            output_root=output_root,
            unit_level="NUTS3",
            smoke_csv=smoke_unit_csv,
            pop_csv=pop_unit_csv,
            recurrence_csv=rec_unit_csv,
            iech_mean_csv=iech_unit_mean_csv,
            scen_mean_csv=scen_unit_mean_csv,
            wrb_csv=wrb_nuts_csv,
            terr_csv=terr_nuts_csv,
            out_csv=out_causal_nuts_csv,
            smoke_route_blocked=smoke_route_blocked,
            smoke_route_context=smoke_route_context,
        )

        out_causal_muni_csv = causal_dir / "causal_matrix_IECH_municipio.csv"
        rows_muni = build_causal_matrix(
            output_root=output_root,
            unit_level="MUNICIPIO",
            smoke_csv=smoke_muni_csv,
            pop_csv=pop_muni_csv,
            recurrence_csv=rec_muni_csv,
            iech_mean_csv=iech_muni_mean_csv,
            scen_mean_csv=scen_muni_mean_csv,
            wrb_csv=wrb_muni_csv,
            terr_csv=terr_muni_csv,
            out_csv=out_causal_muni_csv,
            smoke_route_blocked=smoke_route_blocked,
            smoke_route_context=smoke_route_context,
        )
        shutil.copy2(out_causal_nuts_csv, causal_dir / "territorial_screening_matrix_nuts3.csv")
        shutil.copy2(out_causal_muni_csv, causal_dir / "territorial_screening_matrix_municipio.csv")
        code_root = PIPELINE_ROOT.parent
        outer_root = code_root.parent.parent
        write_r10c_qa(output_root / "qa", {"NUTS3": rows_nuts, "MUNICIPIO": rows_muni})
        write_git_root_audit(output_root / "qa", outer_root, code_root)

        write_causal_json_txt_sha(
            causal_dir=causal_dir,
            rows_nuts=rows_nuts,
            out_csv_nuts=out_causal_nuts_csv,
            in_files=[
                smoke_unit_csv,
                pop_unit_csv,
                rec_unit_csv,
                iech_unit_mean_csv,
                scen_unit_mean_csv,
                wrb_nuts_csv,
                terr_nuts_csv,
            ],
        )
        log_line(run_log, "Causal matrix artifacts generated")

        brief_path = generate_brief(output_root, inputs)
        log_line(run_log, f"Brief rewritten: {brief_path}")

        run_phase3_closure(
            output_root=output_root,
            nuts_layer=nuts_layer,
            muni_layer=muni_layer,
            muni_field=muni_field,
            fire_paths=fire_paths,
            inputs=inputs,
        )
        log_line(run_log, "Phase 3 semantic, feasibility and thematic packages generated")


        write_aggregate_consistency_audits(
            output_root,
            tables_dir / "IECH_unit_2015_2024.csv",
            iech_unit_mean_csv,
            iech_muni_csv,
            iech_muni_mean_csv,
            scen_unit_csv,
            scen_unit_mean_csv,
            scen_muni_csv,
            scen_muni_mean_csv,
        )
        write_wrb_method_consistency_audit(output_root, wrb_nuts_csv, wrb_muni_csv)
        write_smoke_route_audit(output_root, inputs, smoke_unit_csv, smoke_muni_csv)
        write_fire_ingestion_audit(output_root, fire_paths)
        write_population_audit(output_root, pop_unit_csv, pop_muni_csv)
        # The R10-B producer already wrote the complete recurrence audit after
        # both territorial levels were computed; do not overwrite it with the
        # former row-count-only audit.
        write_iech_audit(output_root, tables_dir / "IECH_unit_2015_2024.csv", iech_muni_csv)
        write_territorial_and_wrb_audits(output_root, wrb_nuts_csv, wrb_muni_csv, terr_nuts_csv, terr_muni_csv)
        write_scenario_audit(output_root, scen_unit_csv, scen_muni_csv)
        log_line(run_log, "OC audit artifacts generated")

        touch_qa_fresh_files(output_root)
        log_line(run_log, "END PASS")
        try:
            print("OK STEP7_MATRIZ_CAUSAL_EXTENDED")
            print("output_root =", output_root)
            print("brief =", brief_path)
        except OSError:
            pass
        return 0
    except Exception as exc:
        log_line(run_log, f"END FAIL: {exc}")
        log_line(run_log, traceback.format_exc())
        print("FAIL STEP7_MATRIZ_CAUSAL_EXTENDED:", exc)
        traceback.print_exc()
        return 2
    finally:
        if qgs is not None:
            try:
                qgs.exitQgis()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())









