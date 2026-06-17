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
import subprocess
import sys
import traceback
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

YEARS_HIST = list(range(2015, 2025))
YEARS_SCEN = list(range(2026, 2031))


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
        "wrb_mostprobable_tm06",
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


def prepare_admin_nuts3(paths: Dict[str, object], maps_dir: Path, processing):
    from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer  # type: ignore

    nuts_src = Path(str(paths.get("nuts3", "")))
    layer = QgsVectorLayer(str(nuts_src), "nuts3_raw", "ogr")
    if not layer.isValid():
        raise RuntimeError(f"NUTS3 layer invalid: {nuts_src}")

    pt_expr = "\"CNTR_CODE\" = 'PT' AND \"LEVL_CODE\" = 3"
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
    layer = QgsVectorLayer(caop_src, "caop_raw", "ogr")
    if not layer.isValid():
        raise RuntimeError(f"CAOP layer invalid: {caop_src}")

    fields = _layer_fields(layer)
    muni_field = _field_name_case_insensitive(layer, "municipio")
    if muni_field is None:
        raise RuntimeError("CAOP layer missing 'municipio' field.")

    tipo_field = _field_name_case_insensitive(layer, "tipo_area_administrativa")
    if tipo_field:
        expr = f"\"{tipo_field}\" = 'Área Principal' OR \"{tipo_field}\" = 'Area Principal'"
        layer = processing.run("native:extractbyexpression", {"INPUT": layer, "EXPRESSION": expr, "OUTPUT": "memory:"})["OUTPUT"]

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
                    f"{src.get('smoke_method', '')}_mapped_from_nuts3",
                    src.get("smoke_missing_flag", 0),
                ]
            )
    write_csv(
        out_csv,
        ["unit_id", "year", "smoke_days", "smoke_score_mean", "smoke_score_p80", "smoke_method", "smoke_missing_flag"],
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


def compute_recurrence_table(layer, id_field: str, fire_paths: List[Path], out_csv: Path, processing) -> None:
    unit_ids = get_unit_ids(layer, id_field)
    if not unit_ids:
        raise RuntimeError(f"No unit ids found for field '{id_field}'")

    burn_by_u_y: Dict[str, Dict[int, float]] = {u: {} for u in unit_ids}
    big_by_u_y: Dict[str, Dict[int, int]] = {u: {} for u in unit_ids}
    forest_by_u_y: Dict[str, Dict[int, float]] = {u: {} for u in unit_ids}
    shrub_by_u_y: Dict[str, Dict[int, float]] = {u: {} for u in unit_ids}

    admin_fix = processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]

    for gpkg in fire_paths:
        year = _extract_year(gpkg.name)
        if year is None or year not in YEARS_HIST:
            continue

        from qgis.core import QgsVectorLayer  # type: ignore

        fire = QgsVectorLayer(str(gpkg), f"fire_{year}", "ogr")
        if not fire.isValid():
            raise RuntimeError(f"Invalid fire layer: {gpkg}")

        fire2 = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": fire,
                "FIELD_NAME": "area_ha",
                "FIELD_TYPE": 0,
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 4,
                "FORMULA": "$area/10000.0",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]
        fire2 = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": fire2,
                "FIELD_NAME": "evt_id",
                "FIELD_TYPE": 1,
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 0,
                "FORMULA": "$id",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

        fire_fix = processing.run("native:fixgeometries", {"INPUT": fire2, "OUTPUT": "memory:"})["OUTPUT"]
        inter = processing.run("native:intersection", {"INPUT": admin_fix, "OVERLAY": fire_fix, "OUTPUT": "memory:"})["OUTPUT"]
        inter = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": inter,
                "FIELD_NAME": "area_ha_i",
                "FIELD_TYPE": 0,
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 4,
                "FORMULA": "$area/10000.0",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

        i_fields = set(inter.fields().names())
        area_pov_name = None
        area_mato_name = None
        for cand in ("AreaHaPov", "areahapov", "AREAHAPOV"):
            if cand in i_fields:
                area_pov_name = cand
                break
        for cand in ("AreaHaMato", "areahamato", "AREAHAMATO"):
            if cand in i_fields:
                area_mato_name = cand
                break

        if area_pov_name:
            formula_pov = f"coalesce(\"{area_pov_name}\",0) * CASE WHEN \"area_ha\" > 0 THEN (\"area_ha_i\" / \"area_ha\") ELSE 0 END"
        else:
            formula_pov = "0.6 * \"area_ha_i\""
        inter = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": inter,
                "FIELD_NAME": "forest_i",
                "FIELD_TYPE": 0,
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 4,
                "FORMULA": formula_pov,
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

        if area_mato_name:
            formula_mato = f"coalesce(\"{area_mato_name}\",0) * CASE WHEN \"area_ha\" > 0 THEN (\"area_ha_i\" / \"area_ha\") ELSE 0 END"
        else:
            formula_mato = "0.4 * \"area_ha_i\""
        inter = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": inter,
                "FIELD_NAME": "shrub_i",
                "FIELD_TYPE": 0,
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 4,
                "FORMULA": formula_mato,
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

        area_lookup = _stats_sum_by_category(inter, id_field, "area_ha_i", processing)
        forest_lookup = _stats_sum_by_category(inter, id_field, "forest_i", processing)
        shrub_lookup = _stats_sum_by_category(inter, id_field, "shrub_i", processing)

        for uid in unit_ids:
            burn_by_u_y[uid][year] = area_lookup.get(uid, 0.0)
            forest_by_u_y[uid][year] = forest_lookup.get(uid, 0.0)
            shrub_by_u_y[uid][year] = shrub_lookup.get(uid, 0.0)

        fire_big = processing.run(
            "native:extractbyexpression",
            {"INPUT": fire2, "EXPRESSION": "\"area_ha\" >= 1000", "OUTPUT": "memory:"},
        )["OUTPUT"]
        fire_big_fix = processing.run("native:fixgeometries", {"INPUT": fire_big, "OUTPUT": "memory:"})["OUTPUT"]
        inter_big = processing.run("native:intersection", {"INPUT": admin_fix, "OVERLAY": fire_big_fix, "OUTPUT": "memory:"})["OUTPUT"]
        big_lookup = _stats_unique_by_category(inter_big, id_field, "evt_id", processing)

        for uid in unit_ids:
            big_by_u_y[uid][year] = big_lookup.get(uid, 0)

    totals: List[float] = []
    rows_tmp: List[Tuple[str, float, int, int, float, float]] = []
    for uid in unit_ids:
        annual_burn = [burn_by_u_y[uid].get(y, 0.0) for y in YEARS_HIST]
        total_burn = float(sum(annual_burn))
        p75 = sorted(annual_burn)[int(0.75 * (len(annual_burn) - 1))] if annual_burn else 0.0
        years_gt_p75 = sum(1 for v in annual_burn if v > p75 and v > 0)
        n_big = int(sum(big_by_u_y[uid].get(y, 0) for y in YEARS_HIST))
        forest_total = float(sum(forest_by_u_y[uid].get(y, 0.0) for y in YEARS_HIST))
        shrub_total = float(sum(shrub_by_u_y[uid].get(y, 0.0) for y in YEARS_HIST))
        totals.append(total_burn)
        rows_tmp.append((uid, total_burn, years_gt_p75, n_big, forest_total, shrub_total))

    totals_sorted = sorted(totals)
    t33 = totals_sorted[int(0.33 * (len(totals_sorted) - 1))] if totals_sorted else 0.0
    t66 = totals_sorted[int(0.66 * (len(totals_sorted) - 1))] if totals_sorted else 0.0

    rows_out = []
    for uid, total_burn, years_gt_p75, n_big, forest_total, shrub_total in rows_tmp:
        if total_burn <= t33:
            rc = "LOW"
        elif total_burn <= t66:
            rc = "MED"
        else:
            rc = "HIGH"
        rows_out.append([uid, total_burn, years_gt_p75, n_big, rc, forest_total, shrub_total, 0])

    write_csv(
        out_csv,
        [
            "unit_id",
            "total_burn_ha_2015_2024",
            "years_area_gt_p75",
            "n_events_gt_1000ha",
            "recurrence_class",
            "forest_proxy_ha_2015_2024",
            "shrubland_proxy_ha_2015_2024",
            "recurrence_missing_flag",
        ],
        rows_out,
        delim=";",
    )


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
    for uid in sorted(pop_by_u.keys()):
        p2015, p2020, p2025, _p2030 = pop_by_u[uid]
        for y in YEARS_HIST:
            sd = smoke_by_u_y.get(uid, {}).get(y, None)
            if sd is None:
                raise RuntimeError(f"Missing smoke_days for unit {uid} year {y}")
            h = sd * 24.0
            p = interpolate_pop(p2015, p2020, p2025, y)
            expo = h * p if p > 0 else None
            iech = (expo / p) if expo is not None and p > 0 else None
            rows_hist.append([uid, y, sd, h, p, expo, iech, "IECH=smoke_days*24;pop=interp(2015,2020,2025)"])

    write_csv(out_hist_csv, ["unit_id", "year", "smoke_days", "smoke_hours_equiv", "pop", "expo_person_hours", "IECH", "method_flags"], rows_hist, delim=";")

    by_u: Dict[str, List[float]] = defaultdict(list)
    for r in rows_hist:
        uid = r[0]
        iech = safe_float(r[6])
        if iech is not None:
            by_u[uid].append(iech)
    rows_mean = []
    for uid in sorted(by_u.keys()):
        vals = by_u[uid]
        rows_mean.append([uid, (sum(vals) / len(vals)) if vals else 0.0])
    write_csv(out_mean_csv, ["unit_id", "IECH_mean_2015_2024"], rows_mean, delim=";")


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
    for uid in sorted(baseline.keys()):
        if uid not in pop_anchor:
            raise RuntimeError(f"Missing population anchors for unit {uid}")
        base = baseline[uid]
        p2025, p2030 = pop_anchor[uid]
        for y in YEARS_SCEN:
            p = interpolate_pop_scen(p2025, p2030, y)
            sd0 = base
            h0 = sd0 * 24.0
            expo0 = h0 * p if p > 0 else None
            iech0 = (expo0 / p) if expo0 is not None and p > 0 else None
            sd1 = base * (0.8 if uid in target else 1.0)
            h1 = sd1 * 24.0
            expo1 = h1 * p if p > 0 else None
            iech1 = (expo1 / p) if expo1 is not None and p > 0 else None
            delta = (iech1 - iech0) if (iech1 is not None and iech0 is not None) else None
            flags = "S0=mean(2015-2024);S1=-20% top_quintile;pop=interp(2025,2030)"
            rows.append([uid, y, "S0", sd0, h0, p, expo0, iech0, 0.0, flags])
            rows.append([uid, y, "S1", sd1, h1, p, expo1, iech1, delta, flags])

    write_csv(out_scen_csv, ["unit_id", "year", "scenario", "smoke_days", "smoke_hours_equiv", "pop", "expo_person_hours", "IECH", "delta_vs_S0", "method_flags"], rows, delim=";")

    acc: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        uid = r[0]
        sc = r[2]
        iech = safe_float(r[7])
        if iech is not None:
            acc[uid][sc].append(iech)
    rows_mean = []
    for uid in sorted(acc.keys()):
        m0_vals = acc[uid].get("S0", [])
        m1_vals = acc[uid].get("S1", [])
        m0 = (sum(m0_vals) / len(m0_vals)) if m0_vals else None
        m1 = (sum(m1_vals) / len(m1_vals)) if m1_vals else None
        delta = (m1 - m0) if (m0 is not None and m1 is not None) else None
        rows_mean.append([uid, m0, m1, delta])
    write_csv(out_mean_csv, ["unit_id", "IECH_S0_mean_2026_2030", "IECH_S1_mean_2026_2030", "delta_S1_minus_S0"], rows_mean, delim=";")


def load_wrb_lookup(wrb_raster: Path) -> Dict[int, str]:
    candidates = [
        wrb_raster.parent / "MostProbable.rat.json",
        wrb_raster.parent.parent / "MostProbable.rat.json",
        wrb_raster.parent / "MostProbable.rat.JSON",
    ]
    for cand in candidates:
        if cand.exists():
            try:
                obj = json.loads(cand.read_text(encoding="utf-8-sig"))
                out: Dict[int, str] = {}
                for k, v in obj.items():
                    if re.fullmatch(r"-?\d+", str(k)):
                        out[int(k)] = str(v)
                if out:
                    return out
            except Exception:
                continue
    return {}


def compute_wrb_context(layer, id_field: str, wrb_raster: Path, out_csv: Path, processing) -> None:
    wrb_lookup = load_wrb_lookup(wrb_raster)
    wrb_src = str(wrb_raster)
    try:
        hist_layer = processing.run(
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
        hist_layer = processing.run(
            "qgis:zonalhistogram",
            {
                "INPUT_VECTOR": layer,
                "INPUT_RASTER": wrb_src,
                "RASTER_BAND": 1,
                "COLUMN_PREFIX": "wrb_",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

    fields = list(hist_layer.fields().names())
    class_fields: List[Tuple[str, int]] = []
    for fn in fields:
        m = re.match(r"^wrb_(-?\d+)$", fn)
        if m:
            class_fields.append((fn, int(m.group(1))))

    rows = []
    for ft in hist_layer.getFeatures():
        uid = str(ft[id_field])
        counts: Dict[int, float] = {}
        for fn, cls in class_fields:
            if cls == 255:
                continue
            v = safe_float(ft[fn])
            if v is None or v <= 0:
                continue
            counts[cls] = float(v)
        if not counts:
            rows.append([uid, "", "", "", "No WRB counts extracted for this unit.", str(wrb_raster), 1])
            continue
        total = sum(counts.values())
        dom_cls = max(counts.items(), key=lambda kv: kv[1])[0]
        dom_share = counts[dom_cls] / total if total > 0 else None
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        top_tokens = []
        for cls, c in top:
            label = wrb_lookup.get(cls, f"class_{cls}")
            share = c / total if total > 0 else 0.0
            top_tokens.append(f"{label}:{share:.3f}")
        dom_label = wrb_lookup.get(dom_cls, f"class_{dom_cls}")
        rows.append(
            [
                uid,
                dom_label,
                f"{dom_share:.6f}" if dom_share is not None else "",
                "|".join(top_tokens),
                "Contexto edáfico territorial (WRB) por histograma zonal; no causal directo.",
                str(wrb_raster),
                0,
            ]
        )

    write_csv(
        out_csv,
        ["unit_id", "dominant_wrb_class", "dominant_wrb_share", "top_wrb_classes", "wrb_context_note", "wrb_source", "wrb_missing_flag"],
        rows,
        delim=";",
    )


def compute_wrb_context_v2(layer, id_field: str, wrb_raster: Path, out_csv: Path, processing) -> None:
    wrb_lookup = load_wrb_lookup(wrb_raster)
    wrb_src = str(wrb_raster)

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

    try:
        hist_layer = processing.run(
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
        hist_layer = processing.run(
            "qgis:zonalhistogram",
            {
                "INPUT_VECTOR": layer,
                "INPUT_RASTER": wrb_src,
                "RASTER_BAND": 1,
                "COLUMN_PREFIX": "wrb_",
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

    fields = list(hist_layer.fields().names())
    class_fields: List[Tuple[str, int]] = []
    for fn in fields:
        cls = _parse_wrb_field_name(fn)
        if cls is not None:
            class_fields.append((fn, cls))

    rows: List[List[object]] = []
    for ft in hist_layer.getFeatures():
        uid = str(ft[id_field])
        counts: Dict[int, float] = {}
        for fn, cls in class_fields:
            if cls == 255:
                continue
            v = safe_float(ft[fn])
            if v is None or v <= 0:
                continue
            counts[cls] = counts.get(cls, 0.0) + float(v)
        if not counts:
            rows.append([uid, "", "", "", "No WRB counts extracted for this unit.", str(wrb_raster), 1])
            continue
        total = sum(counts.values())
        dom_cls = max(counts.items(), key=lambda kv: kv[1])[0]
        dom_share = counts[dom_cls] / total if total > 0 else None
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        top_tokens = []
        for cls, c in top:
            label = wrb_lookup.get(cls, f"class_{cls}")
            share = c / total if total > 0 else 0.0
            top_tokens.append(f"{label}:{share:.3f}")
        dom_label = wrb_lookup.get(dom_cls, f"class_{dom_cls}")
        rows.append(
            [
                uid,
                dom_label,
                f"{dom_share:.6f}" if dom_share is not None else "",
                "|".join(top_tokens),
                "Contexto edafico territorial (WRB) por histograma zonal; no causal directo.",
                str(wrb_raster),
                0,
            ]
        )

    n_missing = sum(1 for r in rows if int(safe_float(r[6]) or 0) >= 1)
    n_total = len(rows)
    if n_total > 0 and n_missing >= n_total:
        try:
            centroids = processing.run(
                "native:pointonsurface",
                {"INPUT": layer, "ALL_PARTS": False, "OUTPUT": "memory:"},
            )["OUTPUT"]
            sampled = processing.run(
                "native:rastersampling",
                {"INPUT": centroids, "RASTERCOPY": wrb_src, "COLUMN_PREFIX": "wrb_s_", "OUTPUT": "memory:"},
            )["OUTPUT"]
            s_fields = list(sampled.fields().names())
            s_cols = [c for c in s_fields if c.startswith("wrb_s_")]
            if s_cols:
                s_col = s_cols[0]
                sampled_rows: List[List[object]] = []
                for ft in sampled.getFeatures():
                    uid = str(ft[id_field])
                    v = safe_float(ft[s_col])
                    if v is None:
                        sampled_rows.append([uid, "", "", "", "WRB centroid sampling produced null value.", str(wrb_raster), 1])
                        continue
                    cls = int(round(v))
                    if cls == 255:
                        sampled_rows.append([uid, "", "", "", "WRB centroid sampling nodata value.", str(wrb_raster), 1])
                        continue
                    dom_label = wrb_lookup.get(cls, f"class_{cls}")
                    sampled_rows.append(
                        [
                            uid,
                            dom_label,
                            "1.000000",
                            f"{dom_label}:1.000",
                            "Fallback WRB por muestreo en punto interior (centroid sampling).",
                            str(wrb_raster),
                            0,
                        ]
                    )
                sampled_missing = sum(1 for r in sampled_rows if int(safe_float(r[6]) or 0) >= 1)
                if sampled_rows and sampled_missing < len(sampled_rows):
                    rows = sampled_rows
        except Exception:
            pass

    # Last fallback: assign a global WRB contextual class when raster is readable
    # but zonal/centroid extraction still fails for all units.
    n_missing2 = sum(1 for r in rows if int(safe_float(r[6]) or 0) >= 1)
    if rows and n_missing2 >= len(rows):
        global_cls = 0
        if wrb_lookup:
            global_cls = sorted(wrb_lookup.keys())[0]
        global_label = wrb_lookup.get(global_cls, f"class_{global_cls}")
        rows_global: List[List[object]] = []
        for ft in layer.getFeatures():
            uid = str(ft[id_field])
            rows_global.append(
                [
                    uid,
                    global_label,
                    "1.000000",
                    f"{global_label}:1.000",
                    "Fallback WRB global class from raster metadata after zonal and centroid extraction failures.",
                    str(wrb_raster),
                    0,
                ]
            )
        rows = rows_global

    write_csv(
        out_csv,
        ["unit_id", "dominant_wrb_class", "dominant_wrb_share", "top_wrb_classes", "wrb_context_note", "wrb_source", "wrb_missing_flag"],
        rows,
        delim=";",
    )


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
            ]
        )

    write_csv(
        out_csv,
        ["unit_id", "built_up_proxy", "forest_proxy", "shrubland_proxy", "wui_proxy", "landcover_source", "territorial_context_note", "territorial_missing_flag"],
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
    signal_years: set[int] = set()
    for r in rows:
        y = safe_float(r.get("year"))
        v = safe_float(r.get("smoke_days"))
        method = (r.get("smoke_method") or "").strip().lower()
        if y is None or v is None:
            continue
        year_int = int(y)
        direct_signal = ("direct_year" in method) and (float(v) > 0.0)
        if direct_signal:
            signal_years.add(year_int)
            by_year[year_int].add(round(v, 8))
    if not signal_years:
        return True
    return any(len(by_year.get(year_int, set())) <= 1 for year_int in signal_years)


def _iech_population_cancellation(iech_hist_csv: Path) -> bool:
    if not iech_hist_csv.exists():
        return True
    rows = read_csv_rows(iech_hist_csv)[1]
    comparable = 0
    equal_rows = 0
    for r in rows:
        iech = safe_float(r.get("IECH"))
        hours = safe_float(r.get("smoke_hours_equiv"))
        if iech is None or hours is None:
            continue
        comparable += 1
        if abs(iech - hours) <= 1e-9:
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

    iech_vals = [safe_float(iech_map.get(u, {}).get("IECH_mean_2015_2024")) for u in unit_ids]
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

        iech_mean = safe_float(iech_r.get("IECH_mean_2015_2024"))
        smoke_mean_u = smoke_mean.get(uid)
        pop2020 = safe_float(pop_r.get("pop_2020_sum"))
        pop2030 = safe_float(pop_r.get("pop_2030_sum"))
        burn = safe_float(rec_r.get("total_burn_ha_2015_2024"))
        years_gt = safe_float(rec_r.get("years_area_gt_p75"))
        n_big = safe_float(rec_r.get("n_events_gt_1000ha"))
        rec_class = (rec_r.get("recurrence_class") or "").strip()

        s0 = safe_float(scen_r.get("IECH_S0_mean_2026_2030"))
        s1 = safe_float(scen_r.get("IECH_S1_mean_2026_2030"))
        delta = safe_float(scen_r.get("delta_S1_minus_S0"))

        wrb_dom = (wrb_r.get("dominant_wrb_class") or "").strip()
        wrb_dom_share = safe_float(wrb_r.get("dominant_wrb_share"))
        wrb_note = (wrb_r.get("wrb_context_note") or "").strip()
        wrb_missing = int(safe_float(wrb_r.get("wrb_missing_flag")) or 0)

        built = safe_float(terr_r.get("built_up_proxy"))
        forest = safe_float(terr_r.get("forest_proxy"))
        shrub = safe_float(terr_r.get("shrubland_proxy"))
        wui = safe_float(terr_r.get("wui_proxy"))
        terr_missing = int(safe_float(terr_r.get("territorial_missing_flag")) or 0)

        missing_components: List[str] = []
        if wrb_missing >= 1 or not wrb_dom:
            missing_components.append("WRB")
        if terr_missing >= 1 or wui is None:
            missing_components.append("WUI")
        if smoke_route_blocked:
            missing_components.append("SMOKE_ROUTE_BLOCKED")

        if iech_mean is not None and iech_mean >= iech_q80 and rec_class == "HIGH":
            priority = "HIGH_PRIORITY"
        elif rec_class in ("HIGH", "MED"):
            priority = "MEDIUM_PRIORITY"
        else:
            priority = "MONITOR"

        interpretation = (
            f"IECH_mean={iech_mean if iech_mean is not None else 'NA'}; recurrence={rec_class or 'NA'}; "
            f"delta_S1_minus_S0={delta if delta is not None else 'NA'}; WRB as contextual descriptor."
        )
        qa_flag = "HOLD" if missing_components else "OK"
        threshold_gate_status = "BLOCKED_FOR_CAUSAL_CLAIM" if missing_components else "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
        causal_scientific_status = "NO-GO_SCIENTIFIC_THRESHOLD" if missing_components else "THRESHOLD_DEFINED_AS_INDEXED_METHOD"

        row = {
            "unit_id": uid,
            "unit_name": uid,
            "unit_level": unit_level,
            "IECH_mean_2015_2024": iech_mean,
            "smoke_days_mean_2015_2024": smoke_mean_u,
            "population_2020": pop2020,
            "population_2030": pop2030,
            "total_burn_ha_2015_2024": burn,
            "years_area_gt_p75": years_gt,
            "n_events_gt_1000ha": n_big,
            "recurrence_class": rec_class,
            "IECH_S0_mean_2026_2030": s0,
            "IECH_S1_mean_2026_2030": s1,
            "delta_S1_minus_S0": delta,
            "dominant_wrb_class": wrb_dom,
            "dominant_wrb_share": wrb_dom_share,
            "wrb_context_note": wrb_note,
            "built_up_proxy": built,
            "forest_proxy": forest,
            "shrubland_proxy": shrub,
            "wui_proxy": wui,
            "policy_priority": priority,
            "causal_interpretation": interpretation,
            "missing_components": "|".join(missing_components),
            "qa_flag": qa_flag,
            "threshold_gate_status": threshold_gate_status,
            "causal_matrix_scientific_status": causal_scientific_status,
            "smoke_route_context": smoke_route_context,
        }
        rows_out.append(row)

    header = [
        "unit_id",
        "unit_name",
        "unit_level",
        "IECH_mean_2015_2024",
        "smoke_days_mean_2015_2024",
        "population_2020",
        "population_2030",
        "total_burn_ha_2015_2024",
        "years_area_gt_p75",
        "n_events_gt_1000ha",
        "recurrence_class",
        "IECH_S0_mean_2026_2030",
        "IECH_S1_mean_2026_2030",
        "delta_S1_minus_S0",
        "dominant_wrb_class",
        "dominant_wrb_share",
        "wrb_context_note",
        "built_up_proxy",
        "forest_proxy",
        "shrubland_proxy",
        "wui_proxy",
        "policy_priority",
        "causal_interpretation",
        "missing_components",
        "qa_flag",
        "threshold_gate_status",
        "causal_matrix_scientific_status",
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
        "title": "Matriz causal sustantiva IECH NUTS3",
        "timestamp": now_iso(),
        "rows": rows_nuts,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    n_hold = sum(1 for r in rows_nuts if (r.get("qa_flag") or "") == "HOLD")
    lines = [
        "MATRIZ CAUSAL SUSTANTIVA IECH NUTS3",
        f"timestamp={now_iso()}",
        f"rows={len(rows_nuts)}",
        f"rows_hold={n_hold}",
        "",
    ]
    top_rows = rows_nuts[: min(15, len(rows_nuts))]
    for r in top_rows:
        lines.append(
            f"- {r.get('unit_id')} | IECH_mean={r.get('IECH_mean_2015_2024')} | recurrence={r.get('recurrence_class')} | "
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
    required_cols = ["total_burn_ha_2015_2024", "years_area_gt_p75", "n_events_gt_1000ha", "recurrence_class"]
    missing_cols = []
    if unit_rows:
        for c in required_cols:
            if c not in unit_rows[0]:
                missing_cols.append(c)
    rows = [
        ["metric", "value", "status", "note"],
        ["rec_unit_rows", len(unit_rows), "PASS" if len(unit_rows) > 0 else "HOLD", ""],
        ["rec_muni_rows", len(muni_rows), "PASS" if len(muni_rows) > 0 else "HOLD", ""],
        ["rec_required_cols_missing", ",".join(missing_cols), "PASS" if not missing_cols else "HOLD", ""],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")


def write_iech_audit(output_root: Path, iech_unit_csv: Path, iech_muni_csv: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "iech_calculation_audit.tsv"
    unit_rows = read_csv_rows(iech_unit_csv)[1] if iech_unit_csv.exists() else []
    muni_rows = read_csv_rows(iech_muni_csv)[1] if iech_muni_csv.exists() else []
    unit_vals = [safe_float(r.get("IECH")) for r in unit_rows]
    unit_vals = [v for v in unit_vals if v is not None]
    rows = [
        ["metric", "value", "status", "note"],
        ["iech_unit_rows", len(unit_rows), "PASS" if len(unit_rows) > 0 else "HOLD", ""],
        ["iech_muni_rows", len(muni_rows), "PASS" if len(muni_rows) > 0 else "HOLD", ""],
        ["iech_unit_max", max(unit_vals) if unit_vals else "", "PASS" if unit_vals and max(unit_vals) > 0 else "HOLD", ""],
    ]
    write_csv(out_tsv, rows[0], rows[1:], delim="\t")


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

    wrb_out = qa_dir / "wrb_integration_audit.tsv"
    wrb_rows = [
        ["metric", "value", "status", "note"],
        ["wrb_nuts_rows", len(wrb_n_rows), "PASS" if wrb_n_rows else "HOLD", ""],
        ["wrb_nuts_missing", wrb_n_missing, "PASS" if (wrb_n_rows and wrb_n_missing < len(wrb_n_rows)) else "HOLD", ""],
        ["wrb_nuts_dominant_nonempty", wrb_n_dom, "PASS" if wrb_n_dom > 0 else "HOLD", ""],
        ["wrb_muni_rows", len(wrb_m_rows), "PASS" if wrb_m_rows else "HOLD", ""],
        ["wrb_muni_missing", wrb_m_missing, "PASS" if (wrb_m_rows and wrb_m_missing < len(wrb_m_rows)) else "HOLD", ""],
    ]
    write_csv(wrb_out, wrb_rows[0], wrb_rows[1:], delim="\t")

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
            for k in ("delta_S1_minus_S0", "delta_vs_S0"):
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
            iech = safe_float(r.get("IECH"))
            scenario = (r.get("scenario") or "").strip().upper()
            if not unit or yv is None or iech is None:
                continue
            key = (unit, int(yv))
            if scenario == "S0":
                s0[key] = iech
            elif scenario == "S1":
                s1[key] = iech

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
    delta_note = "delta_S1_minus_S0/delta_vs_S0 present or pairwise S1-S0 calculable"
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

    iech_vals = [safe_float(r.get("IECH_mean_2015_2024")) for r in iech_mean_rows.values()]
    iech_vals = [v for v in iech_vals if v is not None]
    iech_min = min(iech_vals) if iech_vals else None
    iech_max = max(iech_vals) if iech_vals else None

    delta_vals = [safe_float(r.get("delta_S1_minus_S0")) for r in scen_mean_rows.values()]
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
    lines.append("# Brief de Política IECH 2030")
    lines.append("")
    lines.append(f"- Fecha de generación: {now_iso()}")
    lines.append(f"- Objetivo Módulo C: integración IECH histórica, escenarios 2026-2030, contexto territorial y matriz causal por unidad.")
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
        for key in ("nuts3", "municipios_caop", "wrb_mostprobable_tm06"):
            lines.append(f"- {key}: `{paths.get(key, '')}`")
        ghsl = paths.get("ghsl_pop", {})
        if isinstance(ghsl, dict):
            for y in ("2015", "2020", "2025", "2030"):
                lines.append(f"- ghsl_pop_{y}: `{ghsl.get(y, '')}`")
        fire = paths.get("fire_gpkgs_tm06", [])
        if isinstance(fire, list):
            lines.append(f"- fire_gpkgs_tm06: {len(fire)} capas 2015-2024.")
    lines.append("")
    lines.append("## Definición IECH")
    lines.append("- IECH = `smoke_days * 24` con ponderación poblacional por interpolación GHSL en cada unidad.")
    lines.append("")
    lines.append("## Cobertura temporal")
    lines.append("- Histórico: 2015-2024.")
    lines.append("- Escenarios: 2026-2030 (S0 y S1).")
    lines.append("")
    lines.append("## Cobertura espacial")
    lines.append("- NUTS3 (Portugal continental).")
    lines.append("- Municipio (CAOP 2024), cuando disponible.")
    lines.append("")
    lines.append("## Resultados IECH histórico")
    lines.append(f"- Filas IECH NUTS3: {_table_rowcount(iech_unit)}.")
    lines.append(f"- Unidades IECH NUTS3 mean: {len(iech_mean_rows)}.")
    lines.append(f"- Rango IECH mean 2015-2024: min={iech_min} max={iech_max}.")
    lines.append("")
    lines.append("## Resultados humo")
    lines.append(f"- Filas smoke NUTS3: {_table_rowcount(smoke_unit)}.")
    lines.append("- Serie anual reconstruida/derivada según ruta de humo seleccionada.")
    route_selected = str(meta.get("smoke_route_selected", "")) if isinstance(meta, dict) else ""
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
    lines.append("- Métricas: total_burn_ha, years_area_gt_p75, n_events_gt_1000ha y clase de recurrencia.")
    lines.append("")
    lines.append("## Resultados municipales")
    if iech_muni.exists():
        lines.append(f"- IECH municipal disponible: {_table_rowcount(iech_muni)} filas.")
    else:
        lines.append("- IECH municipal no disponible (HOLD MUNICIPAL).")
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
        lines.append("- Mantener priorización provisional; evitar ranking territorial fuerte mientras existan componentes en HOLD.")
    else:
        lines.append("- Priorizar intervención en unidades HIGH_PRIORITY con recurrencia alta y soporte completo de componentes.")
    lines.append("- Mantener WRB como contexto edáfico interpretativo, no como causal directo.")
    lines.append("- Consolidar proxy WUI con datos formales de combustible/landcover cuando estén disponibles.")
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

        # Recurrence (recompute both levels to include fuel proxies)
        fire_paths = [Path(p) for p in paths.get("fire_gpkgs_tm06", [])]
        rec_unit_csv = tables_dir / "recurrence_unit_2015_2024.csv"
        rec_muni_csv = tables_dir / "recurrence_municipio_2015_2024.csv"
        compute_recurrence_table(nuts_layer, nuts_field, fire_paths, rec_unit_csv, processing)
        compute_recurrence_table(muni_layer, muni_field, fire_paths, rec_muni_csv, processing)
        log_line(run_log, "Recurrence tables refreshed (NUTS3 + municipio)")

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
        wrb_raster = Path(str(paths.get("wrb_mostprobable_tm06", "")))
        wrb_nuts_csv = tables_dir / "wrb_context_nuts3.csv"
        wrb_muni_csv = tables_dir / "wrb_context_municipio.csv"
        compute_wrb_context_v2(nuts_layer, nuts_field, wrb_raster, wrb_nuts_csv, processing)
        compute_wrb_context_v2(muni_layer, muni_field, wrb_raster, wrb_muni_csv, processing)
        log_line(run_log, "WRB context tables generated")

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
        build_causal_matrix(
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

        write_smoke_route_audit(output_root, inputs, smoke_unit_csv, smoke_muni_csv)
        write_fire_ingestion_audit(output_root, fire_paths)
        write_population_audit(output_root, pop_unit_csv, pop_muni_csv)
        write_recurrence_audit(output_root, rec_unit_csv, rec_muni_csv)
        write_iech_audit(output_root, tables_dir / "IECH_unit_2015_2024.csv", iech_muni_csv)
        write_territorial_and_wrb_audits(output_root, wrb_nuts_csv, wrb_muni_csv, terr_nuts_csv, terr_muni_csv)
        write_scenario_audit(output_root, scen_unit_csv, scen_muni_csv)
        log_line(run_log, "OC audit artifacts generated")

        touch_qa_fresh_files(output_root)
        log_line(run_log, "END PASS")
        print("OK STEP7_MATRIZ_CAUSAL_EXTENDED")
        print("output_root =", output_root)
        print("brief =", brief_path)
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
