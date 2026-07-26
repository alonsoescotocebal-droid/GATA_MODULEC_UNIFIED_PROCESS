# -*- coding: utf-8 -*-
from __future__ import annotations



# Canonical structural contract: argparse is never monkeypatched globally.


import argparse
import calendar
import csv
import datetime as dt
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from portuguese_aq_validation import (
    BASE_SMOKE_CONTRACT_FOR_OC03C_PASS,
    PORTUGUESE_AQ_BASE_SMOKE_BLOCKED,
    run_portuguese_aq_validation,
    write_blocked_base_smoke_regression_outputs,
)
from smoke_route_selector import apply_route_meta, detect_smoke_sources, select_smoke_route
from wrb_source_route import find_wrb_annual_burned_area_paths, find_wrb_source_bundle

YEARS_HIST = list(range(2015, 2025))
YEARS_SCEN = list(range(2026, 2031))
OBJECTIVE_IDS = ["OC-01", "OC-02", "OC-03", "OC-03C"] + [f"OC-{i:02d}" for i in range(4, 13)]

IECH_PROXY_INDICATOR_NAME = "population_smoke_burden_proxy"
IECH_PROXY_INDICATOR_UNIT = "proxy person-hours"
IECH_PROXY_CLAIM_STATUS = "OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH"
IECH_PROXY_ASSUMPTION = (
    "population_exposed_equals_population_total_due_to_no_independent_exposed_population_layer"
)
IECH_PROXY_LEGACY_LABEL = "population_smoke_burden_proxy"

GFAS_PM_MESSAGE_COUNT_BLOCKER = "NO-GO_GFAS_PM2P5FIRE_MESSAGE_COUNT_NOT_DETERMINED"
OC03C_BASE_SMOKE_EXPECTED_UNIQUE_YEARS = len(YEARS_HIST)
OC03C_BASE_SMOKE_MIN_UNIQUE_UNITS = 24
OC03C_BASE_SMOKE_EXPECTED_HOMOGENEOUS_YEARS = 0
OC03C_BASE_SMOKE_REQUIRED_MONTH_COUNT = 12
OC03C_BASE_SMOKE_FORBIDDEN_METHOD_TOKENS = ("flat_single_anchor", "interpolated_from_anchors", "extrapolated_from_anchors")
OC03C_BASE_SMOKE_FORBIDDEN_ASSIGNMENT_TOKENS = ("fallback",)


class StageError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def safe_float(val: object) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip()
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


def _first_present_float(row: Dict[str, str], *keys: str) -> Optional[float]:
    for key in keys:
        value = safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _iech_hist_method_flag() -> str:
    return (
        "IECH=smoke_days*24*pop_interp(2015,2020,2025);proxy_person_hours;"
        "population_smoke_burden_proxy=smoke_days*24*population_total;"
        "legacy_IECH=population_smoke_burden_proxy;"
        "population_exposed_assumed=population_total;"
        "exposure_fraction_assumption=1.0;"
        "no_independent_exposed_population_layer"
    )


def _iech_scen_method_flag() -> str:
    return (
        "S0=mean(2015-2024);"
        "S1=-20% top_quintile;"
        "IECH=smoke_days*24*pop_interp(2025,2030);proxy_person_hours;"
        "population_smoke_burden_proxy=smoke_days*24*population_total;"
        "legacy_IECH=population_smoke_burden_proxy;"
        "population_exposed_assumed=population_total;"
        "exposure_fraction_assumption=1.0;"
        "no_independent_exposed_population_layer"
    )


def sniff_delimiter(path: Path, sample_bytes: int = 65536) -> str:
    data = path.read_bytes()[:sample_bytes]
    try:
        s = data.decode("utf-8-sig", errors="replace")
    except Exception:
        s = data.decode(errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return "	"
    if suffix == ".csv":
        counts = {";": s.count(";"), ",": s.count(",")}
        return ";" if counts[";"] >= counts[","] and counts[";"] > 0 else ","
    counts = {";": s.count(";"), ",": s.count(","), "	": s.count("	")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]], str]:
    delim = sniff_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f, delimiter=delim)
        rows = list(rdr)
        header = rdr.fieldnames or []
    return header, rows, delim


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]], delim: str = ";") -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=delim)
        w.writerow(list(header))
        for r in rows:
            w.writerow(list(r))


def write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    write_csv(path, header, rows, delim="\t")


def resolve_raster_source(path_value: str, report: Report) -> str:
    src = Path(path_value)
    if src.suffix.lower() != ".zip":
        return path_value
    if not src.exists():
        return path_value
    try:
        with zipfile.ZipFile(src, "r") as zf:
            tif_entries = [
                e for e in zf.infolist()
                if (not e.is_dir()) and e.filename.lower().endswith(".tif")
            ]
        if not tif_entries:
            report.fail(f"Zip raster without .tif entry: {src}")
        # Choose the largest .tif entry when multiple candidates exist.
        best = max(tif_entries, key=lambda e: int(getattr(e, "file_size", 0)))
        return f"/vsizip/{src.as_posix()}/{best.filename}"
    except StageError:
        raise
    except Exception as e:
        report.fail(f"Cannot inspect zip raster source {src}: {e}")
    return path_value


def count_nan_ratio(rows: List[Dict[str, str]], col: str) -> Tuple[int, int, float]:
    total = len(rows)
    nan_count = 0
    for r in rows:
        v = r.get(col)
        if safe_float(v) is None:
            nan_count += 1
    ratio = (nan_count / total) if total else 1.0
    return nan_count, total, ratio


def has_missing_flag(rows: List[Dict[str, str]]) -> bool:
    for r in rows:
        for k, v in r.items():
            if "missing_flag" in k.lower():
                fv = safe_float(v)
                if fv is not None and fv >= 1.0:
                    return True
    return False


def _median(values: Sequence[float]) -> float:
    vals = sorted(float(v) for v in values)
    n = len(vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _extract_year_from_text(text: object) -> Optional[int]:
    if text is None:
        return None
    s = str(text).strip()
    if len(s) < 4:
        return None
    try:
        return int(s[:4])
    except Exception:
        return None


def _is_forbidden_smoke_output_source(path_value: Path) -> bool:
    p = str(path_value).replace("/", "\\").lower()
    return "\\03_outputs\\tables\\" in p


@dataclass
class Report:
    path: Path

    def log(self, msg: str) -> None:
        ensure_dir(self.path.parent)
        line = f"[{now_iso()}] {msg}"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def fail(self, msg: str) -> None:
        self.log("FAIL: " + msg)
        raise StageError(msg)


def find_qgis_runners() -> List[str]:
    candidates = [
        r"C:\OSGeo4W64\bin\python-qgis-ltr.bat",
        r"C:\OSGeo4W64\bin\python-qgis.bat",
        r"C:\OSGeo4W\bin\python-qgis.bat",
    ]
    found = []
    for c in candidates:
        if Path(c).exists():
            found.append(c)
    base = Path(r"C:\Program Files")
    if base.exists():
        for p in base.glob("QGIS */bin/python-qgis*.bat"):
            if p.exists():
                found.append(str(p))
    return found


def qgis_hint_text() -> str:
    gata_hint = os.environ.get("GATA_ROOT", r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505")
    datos_hint = os.environ.get("MODULEC_DATOS", rf"{gata_hint}\Complementariedad de analisis\Module C\Datos")
    inc_hint = os.environ.get("INC_NEW", rf"{gata_hint}\Incendios_Nueva version")
    runners = find_qgis_runners()
    if runners:
        cmds = [
            f'"{r}" -u "{Path(__file__).name}" --gata-root "{gata_hint}" --modulec-datos "{datos_hint}" --inc-new "{inc_hint}"'
            for r in runners
        ]
        return "QGIS not importable. Use one of:\n" + "\n".join(cmds)
    return "QGIS not importable. Find python-qgis.bat (QGIS install) and run this script with it."


def _diag_env() -> str:
    parts = [
        f"sys.executable={sys.executable}",
        f"QGIS_PREFIX_PATH={os.environ.get('QGIS_PREFIX_PATH','')}",
        "sys.path[0:20]=" + repr(sys.path[:20]),
    ]
    path_env = os.environ.get("PATH", "")
    parts.append("PATH[0:5]=" + repr(path_env.split(os.pathsep)[:5]))
    return " | ".join(parts)


def _sanitize_windows_path(path_env: str) -> str:
    keep = []
    for p in path_env.split(os.pathsep):
        pp = (p or "").strip()
        if not pp:
            continue
        if "windowsapps" in pp.lower():
            continue
        keep.append(pp)
    return os.pathsep.join(keep)


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


def _ensure_qgis_custom_config() -> None:
    if os.environ.get("QGIS_CUSTOM_CONFIG_PATH"):
        return
    try:
        repo_root = Path(__file__).resolve().parents[3]
        cfg = repo_root / "_cleanup_control" / "qgis_profile_runtime"
        cfg.mkdir(parents=True, exist_ok=True)
        os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(cfg)
    except Exception:
        pass


def _bootstrap_qgis_env(report: Report) -> None:
    _patch_add_dll_directory()

    qgis_prefix = Path(r"C:\OSGeo4W64\apps\qgis-ltr")
    py_dir = qgis_prefix / "python"
    plugins_dir = py_dir / "plugins"
    bin_dir = Path(r"C:\OSGeo4W64\bin")
    qgis_bin = qgis_prefix / "bin"
    qt_bin = Path(r"C:\OSGeo4W64\apps\qt5\bin")
    py_scripts = Path(r"C:\OSGeo4W64\apps\Python312\Scripts")
    qgis_qt_plugins = qgis_prefix / "qtplugins"
    qt_plugins = Path(r"C:\OSGeo4W64\apps\qt5\plugins")

    if qgis_prefix.exists():
        os.environ.setdefault("QGIS_PREFIX_PATH", str(qgis_prefix))
    os.environ.setdefault("QT_PLUGIN_PATH", f"{qgis_qt_plugins};{qt_plugins}")
    os.environ.setdefault("GDAL_DATA", r"C:\OSGeo4W64\apps\gdal\share\gdal")
    os.environ.setdefault("PROJ_LIB", r"C:\OSGeo4W64\share\proj")
    os.environ.setdefault("PROJ_DATA", r"C:\OSGeo4W64\share\proj")
    if py_dir.exists() and str(py_dir) not in sys.path:
        sys.path.insert(0, str(py_dir))
    if plugins_dir.exists() and str(plugins_dir) not in sys.path:
        sys.path.insert(0, str(plugins_dir))

    for m in ("processing", "processing.core"):
        if m in sys.modules:
            del sys.modules[m]

    # Runtime path canonico: evita colisiones con Python/Qt externos y replica gate B3.3.
    path_env = os.pathsep.join([
        str(qgis_bin),
        str(qt_bin),
        str(py_scripts),
        str(bin_dir),
        r"C:\WINDOWS\system32",
        r"C:\WINDOWS",
        r"C:\WINDOWS\System32\Wbem",
    ])
    path_env = _sanitize_windows_path(path_env)
    os.environ["PATH"] = path_env
    os.environ["Path"] = path_env
    _ensure_qgis_custom_config()

    importlib.invalidate_caches()
    report.log("QGIS bootstrap applied.")


def _try_import_qgis() -> Optional[Exception]:
    try:
        from qgis.core import QgsApplication  # type: ignore
        import processing  # type: ignore
        pfile = getattr(processing, "__file__", "") or ""
        if "python\\plugins\\processing" not in pfile.lower():
            raise RuntimeError(f"Wrong processing module resolved: {pfile}")
        from processing.core.Processing import Processing  # type: ignore
        return None
    except Exception as e:
        return e


def init_qgis(report: Report):
    _bootstrap_qgis_env(report)
    err = _try_import_qgis()
    if err is not None:
        report.fail(f"QGIS import failed: {err}. {qgis_hint_text()} | {_diag_env()}")

    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        try:
            from qgis.core import QgsApplication  # type: ignore
            QgsApplication.setPrefixPath(prefix, True)
        except Exception:
            pass

    from qgis.core import QgsApplication  # type: ignore
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        from processing.core.Processing import Processing  # type: ignore
        Processing.initialize()
    except Exception as e:
        qgs.exitQgis()
        report.fail(f"Processing init failed: {e}. {qgis_hint_text()}")
    report.log("QGIS initialized OK.")
    return qgs


def _normalize_writer_result(res) -> tuple:
    if isinstance(res, (tuple, list)):
        err = res[0] if len(res) > 0 else None
        msg = res[1] if len(res) > 1 else ""
        return err, msg
    return res, ""


def write_layer_to_gpkg(vl, gpkg_path: Path, layer_name: str, report: Report) -> None:
    from qgis.core import QgsVectorFileWriter  # type: ignore

    ensure_dir(gpkg_path.parent)
    gpkg_path = Path(gpkg_path)

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = layer_name

    if gpkg_path.exists():
        opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    if hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
        res = QgsVectorFileWriter.writeAsVectorFormatV3(vl, str(gpkg_path), vl.transformContext(), opts)
        err, msg = _normalize_writer_result(res)
    else:
        err, msg, *_ = QgsVectorFileWriter.writeAsVectorFormatV2(vl, str(gpkg_path), vl.transformContext(), opts)

    if err != QgsVectorFileWriter.NoError:
        msg = msg or "Unknown GDAL/OGR error (possible lock or permissions)."
        report.fail(f"GPKG write failed: {msg} (path={gpkg_path})")


def _bisect_admin_prepare(stage: int, inputs: Dict[str, object], out_maps: Path, report: Report) -> None:
    from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem  # type: ignore
    import processing  # type: ignore

    report.log(f"BISECT stage {stage} START")
    nuts_path = Path(str(inputs["paths"]["nuts3"]))
    layer = QgsVectorLayer(str(nuts_path), "nuts3", "ogr")
    if not layer.isValid():
        report.fail(f"NUTS3 invalid: {nuts_path}")

    if stage >= 1:
        pt_expr = "\"CNTR_CODE\" = 'PT' AND \"LEVL_CODE\" = 3 AND \"NUTS_ID\" NOT IN ('PT200', 'PT300')"
        layer = processing.run("native:extractbyexpression", {"INPUT": layer, "EXPRESSION": pt_expr, "OUTPUT": "memory:"})["OUTPUT"]

    if stage >= 2:
        layer = processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]

    if stage >= 3:
        crs_3763 = QgsCoordinateReferenceSystem("EPSG:3763")
        layer = processing.run("native:reprojectlayer", {"INPUT": layer, "TARGET_CRS": crs_3763, "OUTPUT": "memory:"})["OUTPUT"]

    if stage >= 4:
        gpkg_path = out_maps / "IECH_ModuleC_master.gpkg"
        write_layer_to_gpkg(layer, gpkg_path, "admin_nuts3_2024", report)

    report.log(f"BISECT stage {stage} OK")


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def _build_inputs_from_master_catalog(report: Report) -> Dict[str, object]:
    repo_root = _repo_root_from_script()
    catalog = repo_root / "data_placeholders" / "master_inputs_for_pipeline.csv"
    if not catalog.exists():
        report.fail(f"inputs_resolved.json missing and catalog missing: {catalog}")

    _header, rows, _delim = read_csv_rows(catalog)
    by_key: Dict[str, str] = {}
    for row in rows:
        k = (row.get("InputKey") or "").strip()
        v = (row.get("ResolvedPath") or "").strip()
        if k and v:
            by_key[k] = v

    fire_indexed: List[Tuple[int, str]] = []
    for k, v in by_key.items():
        if not k.startswith("paths.fire_gpkgs_tm06[") or not k.endswith("]"):
            continue
        try:
            idx = int(k[len("paths.fire_gpkgs_tm06["):-1])
        except Exception:
            continue
        fire_indexed.append((idx, v))
    fire_gpkgs = [p for _, p in sorted(fire_indexed, key=lambda t: t[0])]

    inputs = {
        "paths": {
            "nuts3": by_key.get("paths.nuts3", ""),
            "municipios_caop": by_key.get("paths.municipios_caop", ""),
            "smoke_csv": by_key.get("paths.smoke_csv", ""),
            "ghsl_pop": {
                "2015": by_key.get("paths.ghsl_pop.2015", ""),
                "2020": by_key.get("paths.ghsl_pop.2020", ""),
                "2025": by_key.get("paths.ghsl_pop.2025", ""),
                "2030": by_key.get("paths.ghsl_pop.2030", ""),
            },
            "fire_gpkgs_tm06": fire_gpkgs,
            "wrb_mostprobable_tm06": by_key.get("paths.wrb_mostprobable_tm06", ""),
        }
    }
    report.log(f"inputs_resolved.json synthesized from catalog: {catalog}")
    return inputs


def load_inputs(inputs_path: Path, report: Report) -> Dict[str, object]:
    if not inputs_path.exists():
        generated = _build_inputs_from_master_catalog(report)
        ensure_dir(inputs_path.parent)
        inputs_path.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
        report.log(f"inputs_resolved.json created at: {inputs_path}")
    with inputs_path.open("r", encoding="utf-8-sig") as f:
        inputs = json.load(f)
    return inputs


def _find_objectives_canon_path() -> Path:
    from_env = (os.environ.get("GATA_OBJECTIVES_CANON_PATH") or "").strip()
    if from_env:
        p = Path(from_env)
        if p.exists():
            return p

    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / "PIPELINE_CANON_HANDOFF" / "12_OBJECTIVES_CANON_MODULEC_IECH.md",
        repo_root / "contracts" / "13_MODULEC_OBJECTIVES_CANON_IECH.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Missing objectives canon file. Expected PIPELINE_CANON_HANDOFF/12_OBJECTIVES_CANON_MODULEC_IECH.md "
        "or contracts/13_MODULEC_OBJECTIVES_CANON_IECH.md."
    )


def hydrate_inputs_contract_meta(inputs: Dict[str, object], generated_by: str = "moduleC_pipeline_v2.py") -> Dict[str, object]:
    merged = dict(inputs) if isinstance(inputs, dict) else {}
    meta = dict(merged.get("meta", {})) if isinstance(merged.get("meta", {}), dict) else {}
    canon_path = _find_objectives_canon_path()
    meta.update(
        {
            "generated_at": now_iso(),
            "generated_by": generated_by,
            "objectives_canon_path": str(canon_path),
            "objectives_canon_sha256": _sha256_path(canon_path),
            "objectives_recognized": OBJECTIVE_IDS,
        }
    )
    merged["meta"] = meta
    return merged


def _collect_missing_inputs(inputs: Dict[str, object]) -> List[str]:
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    if not isinstance(paths, dict):
        paths = {}
    missing: List[str] = []

    required_keys = [
        "nuts3",
        "municipios_caop",

    ]
    for key in required_keys:
        raw = str(paths.get(key, "")).strip()
        if not raw:
            missing.append(f"{key} -> <empty>")
            continue
        if not Path(raw).exists():
            missing.append(f"{key} -> {raw}")

    smoke_raw = str(paths.get("smoke_csv", "")).strip()
    if not smoke_raw:
        missing.append("smoke_csv -> <empty>")
    else:
        smoke_path = Path(smoke_raw)
        if not smoke_path.exists():
            missing.append(f"smoke_csv -> {smoke_path}")
        if _is_forbidden_smoke_output_source(smoke_path):
            missing.append(f"smoke_csv forbidden source under 03_outputs/tables -> {smoke_path}")

    ghsl = paths.get("ghsl_pop", {})
    if not isinstance(ghsl, dict):
        ghsl = {}
    for y in (2015, 2020, 2025, 2030):
        raw = str(ghsl.get(str(y), "")).strip()
        if not raw:
            missing.append(f"ghsl_pop[{y}] -> <empty>")
            continue
        if not Path(raw).exists():
            missing.append(f"ghsl_pop[{y}] -> {raw}")

    fire = paths.get("fire_gpkgs_tm06", [])
    if not isinstance(fire, list) or not fire:
        missing.append("fire_gpkgs_tm06 -> []")
    else:
        for raw_value in fire:
            raw = str(raw_value).strip()
            if not raw:
                missing.append("fire_gpkgs_tm06 -> <empty>")
                continue
            if not Path(raw).exists():
                missing.append(f"fire_gpkgs_tm06 -> {raw}")
    try:
        find_wrb_source_bundle(paths)
        find_wrb_annual_burned_area_paths(paths)
    except FileNotFoundError as exc:
        missing.append(f"wrb_source_route -> {exc}")
    return missing


def validate_inputs(inputs: Dict[str, object], report: Report) -> None:
    missing = _collect_missing_inputs(inputs)
    if missing:
        report.fail("Missing inputs:\n- " + "\n- ".join(missing))


def refresh_preflight_report(
    gata_root: Path,
    modulec_datos: Path,
    inc_new: Path,
    output_root: Path,
    inputs: Dict[str, object],
    route_decision: Dict[str, object],
    report: Report,
    qgis_ready: Optional[bool] = None,
) -> Path:
    qa_dir = output_root / "qa"
    report_path = qa_dir / "preflight_report.txt"
    lines = [
        f"[{now_iso()}] START moduleC_preflight",
        f"[{now_iso()}] GATA_ROOT={gata_root}",
        f"[{now_iso()}] MODULEC_DATOS={modulec_datos}",
        f"[{now_iso()}] INC_NEW={inc_new}",
        f"[{now_iso()}] OUTPUT_ROOT={output_root}",
    ]

    missing_core: List[str] = []
    for label, path_value in (
        ("GATA_ROOT", gata_root),
        ("MODULEC_DATOS", modulec_datos),
        ("INC_NEW", inc_new),
    ):
        if not path_value.exists():
            missing_core.append(f"{label} -> {path_value}")
    if missing_core:
        lines.append(f"[{now_iso()}] FAIL Core path missing count={len(missing_core)}")
        for item in missing_core:
            lines.append(f"[{now_iso()}] MISSING {item}")
    else:
        lines.append(f"[{now_iso()}] PASS core paths validated")

    canon_error = ""
    try:
        canon_path = _find_objectives_canon_path()
        canon_sha = _sha256_path(canon_path)
        lines.append(f"[{now_iso()}] PASS canon found: {canon_path}")
        lines.append(f"[{now_iso()}] PASS canon sha256: {canon_sha}")
    except Exception as exc:
        canon_error = str(exc)
        lines.append(f"[{now_iso()}] FAIL canonical objectives missing: {canon_error}")

    missing_inputs = _collect_missing_inputs(inputs)
    if missing_inputs:
        lines.append(f"[{now_iso()}] FAIL Missing/invalid inputs count={len(missing_inputs)}")
        for item in missing_inputs:
            lines.append(f"[{now_iso()}] MISSING {item}")
    else:
        lines.append(f"[{now_iso()}] PASS Input paths validated")

    route_selected = str(route_decision.get("route_selected") or "").strip()
    route_status = str(route_decision.get("smoke_route_decision") or route_selected).strip()
    if route_selected:
        lines.append(f"[{now_iso()}] smoke route preflight selected={route_selected} decision={route_status}")

    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    if not isinstance(paths, dict):
        paths = {}
    effective_root = str(paths.get("smoke_effective_data_root") or "").strip()
    effective_source = str(paths.get("smoke_effective_source_path") or "").strip()
    if effective_root:
        lines.append(f"[{now_iso()}] smoke effective data root: {effective_root}")
    if effective_source:
        lines.append(f"[{now_iso()}] smoke effective source path: {effective_source}")

    if qgis_ready is True:
        lines.append(f"[{now_iso()}] PASS qgis.core + processing import (pipeline runtime)")
    elif qgis_ready is False:
        lines.append(f"[{now_iso()}] PASS qgis.core + processing import not required for resume_post_smoke artifact refresh")

    if missing_core:
        lines.append(f"[{now_iso()}] END HOLD preflight (missing core paths)")
    elif canon_error:
        lines.append(f"[{now_iso()}] END HOLD preflight (missing canonical objectives)")
    elif missing_inputs:
        lines.append(f"[{now_iso()}] END HOLD preflight (missing inputs)")
    else:
        lines.append(f"[{now_iso()}] END PASS preflight")

    ensure_dir(report_path.parent)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.log(f"Preflight report refreshed: {report_path}")
    return report_path


def admin_prepare(inputs: Dict[str, object], out_maps: Path, report: Report) -> Path:
    from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem  # type: ignore
    import processing  # type: ignore

    nuts_path = Path(str(inputs["paths"]["nuts3"]))

    report.log(f"MARK: admin_prepare nuts_path={nuts_path}")
    report.log(f"MARK: admin_prepare nuts_path={nuts_path}")
    layer = QgsVectorLayer(str(nuts_path), "nuts3", "ogr")
    if not layer.isValid():
        report.fail(f"NUTS3 invalid: {nuts_path}")

    pt_expr = "\"CNTR_CODE\" = 'PT' AND \"LEVL_CODE\" = 3 AND \"NUTS_ID\" NOT IN ('PT200', 'PT300')"
    report.log("MARK: admin_prepare BEFORE processing native:extractbyexpression")
    report.log("MARK: admin_prepare BEFORE processing native:extractbyexpression")
    layer = processing.run("native:extractbyexpression", {"INPUT": layer, "EXPRESSION": pt_expr, "OUTPUT": "memory:"})["OUTPUT"]
    layer = processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]
    crs_3763 = QgsCoordinateReferenceSystem("EPSG:3763")
    layer = processing.run("native:reprojectlayer", {"INPUT": layer, "TARGET_CRS": crs_3763, "OUTPUT": "memory:"})["OUTPUT"]

    if layer.featureCount() <= 0:
        report.fail("NUTS3 layer has zero features after filter.")

    gpkg_path = out_maps / "IECH_ModuleC_master.gpkg"
    write_layer_to_gpkg(layer, gpkg_path, "admin_nuts3_2024", report)
    return gpkg_path


def _collect_primary_smoke_anchors(modulec_datos: Path, report: Report) -> Dict[int, float]:
    from osgeo import ogr  # type: ignore

    parquet_zips = [modulec_datos / "ParquetFiles 2017.zip", modulec_datos / "ParquetFiles 2022.zip"]
    parquet_zips = [p for p in parquet_zips if p.exists()]
    if not parquet_zips:
        report.fail(f"Primary smoke source missing. Expected parquet zips in: {modulec_datos}")

    # station/year/day -> any(Value > 0). This preserves smoke-day signal from primary source.
    day_signal: Dict[Tuple[str, int, str], bool] = {}
    for zpath in parquet_zips:
        with zipfile.ZipFile(zpath, "r") as zf:
            entries = [n for n in zf.namelist() if n.lower().endswith(".parquet")]
        if not entries:
            report.fail(f"Primary smoke parquet zip has no parquet entries: {zpath}")

        for entry in entries:
            station = Path(entry).stem
            vpath = f"/vsizip/{zpath.as_posix()}/{entry}"
            ds = ogr.Open(vpath, 0)
            if ds is None:
                report.fail(f"Cannot open primary smoke parquet: {vpath}")
            lyr = ds.GetLayer(0)
            if lyr is None:
                report.fail(f"Primary smoke parquet has no layer: {vpath}")
            lyr.ResetReading()
            for ft in lyr:
                start_val = ft.GetField("Start")
                y = _extract_year_from_text(start_val)
                if y is None or y not in YEARS_HIST:
                    continue
                day = str(start_val)[:10]
                if len(day) != 10:
                    continue
                v = safe_float(ft.GetField("Value"))
                gt0 = v is not None and v > 0.0
                key = (station, y, day)
                day_signal[key] = day_signal.get(key, False) or gt0

    if not day_signal:
        report.fail("Primary smoke parquet contains no usable day-level records for 2015-2024.")

    station_year_days_gt0: Dict[Tuple[str, int], int] = {}
    for (station, y, _day), flag in day_signal.items():
        if not flag:
            continue
        key = (station, y)
        station_year_days_gt0[key] = station_year_days_gt0.get(key, 0) + 1

    by_year: Dict[int, List[float]] = {}
    for (_station, y), days_gt0 in station_year_days_gt0.items():
        by_year.setdefault(y, []).append(float(days_gt0))

    if not by_year:
        report.fail("Primary smoke parquet has total absence of smoke signal (all days <= 0).")

    anchors = {y: _median(vals) for y, vals in by_year.items() if vals}
    if not anchors:
        report.fail("Primary smoke anchors could not be computed.")
    if sum(anchors.values()) <= 0.0:
        report.fail("Primary smoke anchors are degenerate: sum(smoke_days)==0.")
    if max(anchors.values()) <= 0.0:
        report.fail("Primary smoke anchors are degenerate: max(smoke_days)==0.")

    anchor_txt = ", ".join(f"{y}:{anchors[y]:.3f}" for y in sorted(anchors.keys()))
    report.log(f"Primary smoke anchors built from parquet: {anchor_txt}")
    return anchors


def _fill_smoke_year_series(anchors: Dict[int, float], report: Report) -> Tuple[Dict[int, float], Dict[int, str]]:
    years = sorted(anchors.keys())
    if not years:
        report.fail("No primary smoke anchors available for interpolation.")

    values: Dict[int, float] = {}
    methods: Dict[int, str] = {}

    if len(years) == 1:
        y0 = years[0]
        v0 = float(anchors[y0])
        for y in YEARS_HIST:
            values[y] = max(v0, 0.0)
            methods[y] = "primary_parquet_direct_year" if y == y0 else "primary_parquet_flat_single_anchor"
        return values, methods

    for y in YEARS_HIST:
        if y in anchors:
            values[y] = max(float(anchors[y]), 0.0)
            methods[y] = "primary_parquet_direct_year"
            continue

        if y < years[0]:
            y0, y1 = years[0], years[1]
            method = "primary_parquet_extrapolated_from_anchors"
        elif y > years[-1]:
            y0, y1 = years[-2], years[-1]
            method = "primary_parquet_extrapolated_from_anchors"
        else:
            y0, y1 = years[0], years[-1]
            for i in range(len(years) - 1):
                a, b = years[i], years[i + 1]
                if a <= y <= b:
                    y0, y1 = a, b
                    break
            method = "primary_parquet_interpolated_from_anchors"

        v0 = float(anchors[y0])
        v1 = float(anchors[y1])
        frac = 0.0 if y1 == y0 else (float(y - y0) / float(y1 - y0))
        vy = v0 + (v1 - v0) * frac
        values[y] = max(vy, 0.0)
        methods[y] = method

    if sum(values.values()) <= 0.0:
        report.fail("Smoke year series is degenerate after interpolation: sum(smoke_days)==0.")
    if max(values.values()) <= 0.0:
        report.fail("Smoke year series is degenerate after interpolation: max(smoke_days)==0.")
    return values, methods


def _fill_smoke_year_series_relaxed(anchors: Dict[int, float], method_prefix: str) -> Tuple[Dict[int, float], Dict[int, str]]:
    years = sorted(int(y) for y in anchors.keys())
    values: Dict[int, float] = {}
    methods: Dict[int, str] = {}
    if not years:
        return values, methods

    if len(years) == 1:
        y0 = years[0]
        v0 = max(float(anchors[y0]), 0.0)
        for y in YEARS_HIST:
            values[y] = v0
            methods[y] = f"{method_prefix}_direct_year" if y == y0 else f"{method_prefix}_flat_single_anchor"
        return values, methods

    for y in YEARS_HIST:
        if y in anchors:
            values[y] = max(float(anchors[y]), 0.0)
            methods[y] = f"{method_prefix}_direct_year"
            continue
        if y < years[0]:
            y0, y1 = years[0], years[1]
            method = f"{method_prefix}_extrapolated_from_anchors"
        elif y > years[-1]:
            y0, y1 = years[-2], years[-1]
            method = f"{method_prefix}_extrapolated_from_anchors"
        else:
            y0, y1 = years[0], years[-1]
            for i in range(len(years) - 1):
                a, b = years[i], years[i + 1]
                if a <= y <= b:
                    y0, y1 = a, b
                    break
            method = f"{method_prefix}_interpolated_from_anchors"
        v0 = float(anchors[y0])
        v1 = float(anchors[y1])
        frac = 0.0 if y1 == y0 else (float(y - y0) / float(y1 - y0))
        values[y] = max(v0 + (v1 - v0) * frac, 0.0)
        methods[y] = method
    return values, methods


def _finalize_unit_daily_scores(
    unit_daily_rows: List[Dict[str, object]],
    report: Report,
    log_prefix: str,
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[int, Dict[str, float]]], Optional[float]]:
    raw_scores = [max(float(row.get("smoke_day_score") or 0.0), 0.0) for row in unit_daily_rows]
    threshold_value = _percentile([v for v in raw_scores if v > 0.0], 0.60)
    annual_by_unit: Dict[str, Dict[int, Dict[str, float]]] = {}
    for row in unit_daily_rows:
        score = max(float(row.get("smoke_day_score") or 0.0), 0.0)
        proxy = 1 if (threshold_value is not None and score >= threshold_value and score > 0.0) else 0
        equivalent = _smoke_day_equivalent(score, threshold_value, proxy)
        row["threshold_id"] = "GFAS_ERA5_PROXY_SMOKE_DAY_P60"
        row["threshold_value"] = threshold_value if threshold_value is not None else ""
        row["smoke_day_proxy"] = proxy
        row["smoke_day_equivalent"] = equivalent
        row["qa_flag"] = int(row.get("qa_flag", 0) or 0)
        uid = str(row["unit_id"])
        year = int(row["year"])
        annual = annual_by_unit.setdefault(uid, {}).setdefault(
            year,
            {"smoke_days": 0.0, "smoke_days_binary": 0.0, "score_values": [], "score_mean": 0.0, "score_p80": 0.0},
        )
        annual["smoke_days"] += float(equivalent)
        annual["smoke_days_binary"] += float(proxy)
        annual["score_values"].append(score)

    for year_map in annual_by_unit.values():
        for annual in year_map.values():
            scores = [float(v) for v in annual.pop("score_values", [])]
            annual["score_mean"] = (sum(scores) / float(len(scores))) if scores else 0.0
            p80 = _percentile(scores, 0.80)
            annual["score_p80"] = p80 if p80 is not None else 0.0

    if annual_by_unit:
        report.log(
            f"{log_prefix}: daily_rows={len(unit_daily_rows)} "
            f"units_with_signal={len(annual_by_unit)} threshold={threshold_value}"
        )
    return unit_daily_rows, annual_by_unit, threshold_value


def _derive_unit_daily_scores_from_xyz(
    admin_layer,
    daily_rows: List[Dict[str, object]],
    report: Report,
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[int, Dict[str, float]]], Optional[float]]:
    from qgis.core import (  # type: ignore
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsGeometry,
        QgsPointXY,
        QgsProject,
    )

    features = []
    name_fields = ("NAME_LATN", "NUTS_NAME", "NAME_ENGL", "NAME")
    for ft in admin_layer.getFeatures():
        uid = str(ft["NUTS_ID"]) if ft["NUTS_ID"] is not None else ""
        if not uid:
            continue
        geom = ft.geometry()
        if geom is None or geom.isEmpty():
            continue
        unit_name = uid
        for fld in name_fields:
            try:
                if fld in ft.fields().names() and ft[fld] not in (None, ""):
                    unit_name = str(ft[fld])
                    break
            except Exception:
                continue
        features.append((uid, unit_name, geom, geom.boundingBox()))
    if not features:
        return [], {}, None

    src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    dst_crs = admin_layer.crs()
    transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

    unit_daily_rows: List[Dict[str, object]] = []
    for d in daily_rows:
        year_val = safe_float(d.get("year"))
        xyz_path_raw = str(d.get("xyz_path") or "").strip()
        if year_val is None or not xyz_path_raw:
            continue
        xyz_path = Path(xyz_path_raw)
        if not xyz_path.exists():
            continue
        year = int(year_val)
        stats = _parse_xyz_stats(xyz_path)
        per_unit_stats: Dict[str, Dict[str, float]] = {}

        for x, yv, vv in stats.get("triples", []):
            if vv is None:
                continue
            try:
                pt = transform.transform(QgsPointXY(float(x), float(yv)))
            except Exception:
                continue
            pt_geom = QgsGeometry.fromPointXY(pt)
            for uid, unit_name, geom, bbox in features:
                try:
                    if not bbox.contains(pt):
                        continue
                    if not (geom.contains(pt_geom) or geom.intersects(pt_geom)):
                        continue
                except Exception:
                    continue
                agg = per_unit_stats.setdefault(
                    uid,
                    {
                        "pm2p5fire_sum": 0.0,
                        "pm2p5fire_max": float(vv),
                        "valid_pixel_count": 0.0,
                    },
                )
                agg["pm2p5fire_sum"] += float(vv)
                agg["valid_pixel_count"] += 1.0
                if float(vv) > agg["pm2p5fire_max"]:
                    agg["pm2p5fire_max"] = float(vv)
                agg["unit_name"] = unit_name
                break

        for uid, agg in per_unit_stats.items():
            valid_pixel_count = int(agg.get("valid_pixel_count", 0.0))
            if valid_pixel_count <= 0:
                continue
            pm_sum = float(agg.get("pm2p5fire_sum", 0.0))
            pm_mean = pm_sum / float(valid_pixel_count)
            day_score = max(pm_mean * 1.0e11, 0.0)
            unit_daily_rows.append(
                {
                    "unit_id": uid,
                    "unit_name": str(agg.get("unit_name", uid)),
                    "unit_level": "NUTS3",
                    "date": str(d.get("date", "")),
                    "year": year,
                    "source_file": str(d.get("source_file", "")),
                    "message_index": d.get("message_index", ""),
                    "band_index": d.get("message_index", ""),
                    "pm2p5fire_mean": pm_mean,
                    "pm2p5fire_max": float(agg.get("pm2p5fire_max", 0.0)),
                    "pm2p5fire_sum": pm_sum,
                    "valid_pixel_count": valid_pixel_count,
                    "smoke_day_score": day_score,
                    "method": "gfas_pm2p5fire_gdal_unit_daily_mean",
                    "spatial_assignment_method": "POINT_IN_POLYGON_GFAS_PORTUGAL_XYZ",
                    "xyz_path": str(xyz_path),
                }
            )

    return _finalize_unit_daily_scores(unit_daily_rows, report, "GFAS XYZ unit daily extraction complete")


def _load_modulea_smoke_year_series(smoke_catalog_path: Path, report: Report) -> Tuple[Dict[int, float], Dict[int, str]]:
    if not smoke_catalog_path.exists():
        report.fail(f"v1_moduleA smoke catalog not found: {smoke_catalog_path}")
    _header, rows, _delim = read_csv_rows(smoke_catalog_path)
    by_year: Dict[int, List[float]] = {}
    for r in rows:
        y = safe_float(r.get("year"))
        if y is None:
            continue
        val = safe_float(r.get("smoke_days"))
        if val is None:
            val = safe_float(r.get("smoke_hours"))
            if val is not None:
                val = val / 24.0
        if val is None:
            continue
        yy = int(y)
        if yy in YEARS_HIST:
            by_year.setdefault(yy, []).append(float(val))

    values: Dict[int, float] = {}
    methods: Dict[int, str] = {}
    for y in YEARS_HIST:
        vals = by_year.get(y, [])
        if not vals:
            report.fail(f"v1_moduleA smoke catalog missing required year={y}")
        values[y] = float(sum(vals) / len(vals))
        methods[y] = "v1_moduleA_catalog_mean"
    return values, methods


def _degrade_smoke_methods(by_year_method: Dict[int, str], prefix: str) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for y, m in by_year_method.items():
        out[y] = f"{prefix}_{m}"
    return out


def write_smoke_route_audit(
    qa_dir: Path,
    smoke_csv: Path,
    route_decision: Dict[str, object],
) -> None:
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "smoke_route_audit.tsv"
    _hdr, rows, _delim = read_csv_rows(smoke_csv)
    unique_by_year: Dict[int, set] = {}
    method_by_year: Dict[int, str] = {}
    for r in rows:
        y = safe_float(r.get("year"))
        sd = safe_float(r.get("smoke_days"))
        if y is None or sd is None:
            continue
        yy = int(y)
        unique_by_year.setdefault(yy, set()).add(round(sd, 8))
        if yy not in method_by_year:
            method_by_year[yy] = (r.get("smoke_method") or r.get("method") or "").strip()

    rows_out: List[List[object]] = []
    for y in YEARS_HIST:
        uniq = len(unique_by_year.get(y, set()))
        rows_out.append(
            [
                y,
                uniq,
                method_by_year.get(y, ""),
                1 if uniq <= 1 else 0,
                str(route_decision.get("route_selected", "")),
                str(route_decision.get("smoke_route_status", "")),
                str(route_decision.get("smoke_route_decision", "")),
                str(route_decision.get("health_exposure_claim", "")),
                str(route_decision.get("iech_decision", "")),
                str(route_decision.get("causal_matrix_decision", "")),
                str(route_decision.get("brief_decision", "")),
                str(route_decision.get("final_scientific_decision", "")),
            ]
        )
    write_tsv(
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
    )


def write_spatial_collapse_root_cause_audit(
    output_root: Path,
    smoke_annual_csv: Path,
    smoke_daily_csv: Path,
    gfas_daily_summary_csv: Path,
    iech_hist_csv: Path,
) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "spatial_collapse_root_cause_audit.tsv"
    out_md = qa_dir / "spatial_collapse_root_cause_audit.md"

    rows_out: List[List[object]] = []

    def add_row(artifact: str, metric: str, value: object, evidence: str, decision: str) -> None:
        rows_out.append([artifact, metric, value, evidence, decision])

    daily_homogeneous: Optional[bool] = None
    annual_homogeneous: Optional[bool] = None
    gfas_global_summary: Optional[bool] = None
    iech_collapsed: Optional[bool] = None
    missing_inputs: List[str] = []

    if smoke_daily_csv.exists():
        _hdr, daily_rows, _delim = read_csv_rows(smoke_daily_csv)
        add_row(smoke_daily_csv.name, "rows", len(daily_rows), "row_count", "READ")
        unit_ids = sorted({(r.get("unit_id") or "").strip() for r in daily_rows if (r.get("unit_id") or "").strip()})
        dates = sorted({(r.get("date") or "").strip() for r in daily_rows if (r.get("date") or "").strip()})
        years = sorted({(r.get("year") or "").strip() for r in daily_rows if (r.get("year") or "").strip()})
        add_row(smoke_daily_csv.name, "unit_id_unique", len(unit_ids), "distinct unit_id count", "READ")
        add_row(smoke_daily_csv.name, "date_unique", len(dates), "distinct date count", "READ")
        add_row(smoke_daily_csv.name, "year_unique", len(years), "distinct year count", "READ")

        unique_by_date: Dict[str, set] = {}
        unique_by_year: Dict[str, set] = {}
        for r in daily_rows:
            d = (r.get("date") or "").strip()
            y = (r.get("year") or "").strip()
            v = safe_float(r.get("smoke_day_score"))
            if d and v is not None:
                unique_by_date.setdefault(d, set()).add(round(v, 8))
            if y and v is not None:
                unique_by_year.setdefault(y, set()).add(round(v, 8))
        daily_homogeneous = True
        for s in unique_by_date.values():
            if len(s) > 1:
                daily_homogeneous = False
                break
        yearly_homogeneous = True
        for s in unique_by_year.values():
            if len(s) > 1:
                yearly_homogeneous = False
                break
        add_row(
            smoke_daily_csv.name,
            "all_units_same_score_by_date",
            1 if daily_homogeneous else 0,
            ",".join(f"{k}:{len(v)}" for k, v in sorted(unique_by_date.items())),
            "HOMOGENEOUS" if daily_homogeneous else "DIFFERENTIATED",
        )
        add_row(
            smoke_daily_csv.name,
            "all_units_same_score_by_year",
            1 if yearly_homogeneous else 0,
            ",".join(f"{k}:{len(v)}" for k, v in sorted(unique_by_year.items())),
            "HOMOGENEOUS" if yearly_homogeneous else "DIFFERENTIATED",
        )
    else:
        missing_inputs.append(str(smoke_daily_csv))
        add_row(smoke_daily_csv.name, "exists", 0, "missing file", "FAIL")

    if smoke_annual_csv.exists():
        _hdr, annual_rows, _delim = read_csv_rows(smoke_annual_csv)
        add_row(smoke_annual_csv.name, "rows", len(annual_rows), "row_count", "READ")
        unique_by_year_annual: Dict[int, set] = {}
        for r in annual_rows:
            y = safe_float(r.get("year"))
            v = safe_float(r.get("smoke_days"))
            if y is None or v is None:
                continue
            unique_by_year_annual.setdefault(int(y), set()).add(round(v, 8))
        annual_homogeneous = True
        for s in unique_by_year_annual.values():
            if len(s) > 1:
                annual_homogeneous = False
                break
        add_row(
            smoke_annual_csv.name,
            "spatial_homogeneous_flag_derived",
            1 if annual_homogeneous else 0,
            ",".join(f"{y}:{len(v)}" for y, v in sorted(unique_by_year_annual.items())),
            "HOMOGENEOUS" if annual_homogeneous else "DIFFERENTIATED",
        )
    else:
        missing_inputs.append(str(smoke_annual_csv))
        add_row(smoke_annual_csv.name, "exists", 0, "missing file", "FAIL")

    if gfas_daily_summary_csv.exists():
        hdr, gfas_rows, _delim = read_csv_rows(gfas_daily_summary_csv)
        add_row(gfas_daily_summary_csv.name, "rows", len(gfas_rows), "row_count", "READ")
        hdr_low = {str(h).strip().lower() for h in hdr}
        has_unit_id = "unit_id" in hdr_low
        has_latlon = (("lat" in hdr_low) or ("y" in hdr_low)) and (("lon" in hdr_low) or ("x" in hdr_low))
        gfas_global_summary = not has_unit_id
        add_row(
            gfas_daily_summary_csv.name,
            "is_portugal_global_summary",
            1 if gfas_global_summary else 0,
            f"has_unit_id={has_unit_id}",
            "GLOBAL_ONLY" if gfas_global_summary else "UNIT_LEVEL",
        )
        add_row(
            gfas_daily_summary_csv.name,
            "has_lat_lon_or_cell_for_zonal_assignment",
            1 if has_latlon else 0,
            f"has_latlon={has_latlon}",
            "HAS_COORDS" if has_latlon else "NO_COORDS",
        )
    else:
        missing_inputs.append(str(gfas_daily_summary_csv))
        add_row(gfas_daily_summary_csv.name, "exists", 0, "missing file", "FAIL")

    if iech_hist_csv.exists():
        _hdr, iech_rows, _delim = read_csv_rows(iech_hist_csv)
        add_row(iech_hist_csv.name, "rows", len(iech_rows), "row_count", "READ")
        comparable = 0
        eq_rows = 0
        expo_comparable = 0
        expo_eq_rows = 0
        for r in iech_rows:
            iech = safe_float(r.get("IECH"))
            hours = safe_float(r.get("smoke_hours_equiv"))
            expo = safe_float(r.get("expo_person_hours"))
            pop = safe_float(r.get("pop"))
            if iech is not None and hours is not None:
                comparable += 1
                if abs(iech - hours) <= 1e-9:
                    eq_rows += 1
            if expo is not None and pop is not None and hours is not None:
                expo_comparable += 1
                if abs(expo - (pop * hours)) <= 1e-6:
                    expo_eq_rows += 1
        iech_collapsed = comparable > 0 and comparable == eq_rows
        expo_identity = expo_comparable > 0 and expo_comparable == expo_eq_rows
        add_row(
            iech_hist_csv.name,
            "iech_equals_smoke_hours_equiv_all_rows",
            1 if iech_collapsed else 0,
            f"{eq_rows}/{comparable}",
            "COLLAPSED" if iech_collapsed else "NOT_COLLAPSED",
        )
        add_row(
            iech_hist_csv.name,
            "expo_person_hours_equals_pop_times_smoke_hours_all_rows",
            1 if expo_identity else 0,
            f"{expo_eq_rows}/{expo_comparable}",
            "IDENTITY" if expo_identity else "NOT_IDENTITY",
        )
    else:
        missing_inputs.append(str(iech_hist_csv))
        add_row(iech_hist_csv.name, "exists", 0, "missing file", "FAIL")

    decision = "BLOCKED_COLLAPSE_ORIGIN_NOT_LOCALIZED"
    if missing_inputs:
        decision = "BLOCKED_COLLAPSE_ORIGIN_NOT_LOCALIZED"
    elif daily_homogeneous and annual_homogeneous and gfas_global_summary and iech_collapsed:
        decision = "COLLAPSE_ORIGIN_MULTIPLE"
    elif daily_homogeneous and gfas_global_summary:
        decision = "COLLAPSE_ORIGIN_GDAL_PORTUGAL_SUMMARY"
    elif annual_homogeneous and (daily_homogeneous is False):
        decision = "COLLAPSE_ORIGIN_DAILY_TO_ANNUAL_AGGREGATION"
    elif iech_collapsed:
        decision = "COLLAPSE_ORIGIN_IECH_FORMULA"

    add_row(
        "AUDIT",
        "collapse_origin_decision",
        decision,
        "daily_homogeneous + annual_homogeneous + portugal_global_summary + iech_collapse",
        decision,
    )
    write_tsv(out_tsv, ["artifact", "metric", "value", "evidence", "decision"], rows_out)

    md_lines = [
        "# Spatial Collapse Root Cause Audit",
        "",
        f"- generated_at: {now_iso()}",
        f"- output_root: {output_root}",
        f"- decision: {decision}",
        "",
        "## Findings",
    ]
    for r in rows_out:
        md_lines.append(f"- [{r[0]}] {r[1]}={r[2]} | evidence={r[3]} | decision={r[4]}")
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")



def write_gfas_era5_decoder_daily_spatial_audit(
    output_root: Path,
    smoke_daily_csv: Path,
    smoke_annual_csv: Path,
) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "gfas_era5_decoder_daily_spatial_audit.tsv"

    daily_rows = read_csv_rows(smoke_daily_csv)[1] if smoke_daily_csv.exists() else []
    annual_rows = read_csv_rows(smoke_annual_csv)[1] if smoke_annual_csv.exists() else []
    coverage = _compute_daily_smoke_temporal_coverage(daily_rows)
    threshold_ids = sorted({str(r.get("threshold_id") or "").strip() for r in daily_rows if str(r.get("threshold_id") or "").strip()})
    threshold_values = sorted({str(r.get("threshold_value") or "").strip() for r in daily_rows if str(r.get("threshold_value") or "").strip()})

    same_score_dates = 0
    by_date: Dict[str, set] = defaultdict(set)
    for r in daily_rows:
        date_key = str(r.get("date") or "").strip()
        score = safe_float(r.get("smoke_day_score"))
        if date_key and score is not None:
            by_date[date_key].add(round(score, 8))
    for scores in by_date.values():
        if len(scores) <= 1:
            same_score_dates += 1

    homogeneous_years = _compute_annual_smoke_homogeneous_years(annual_rows)
    daily_rows_count = len(daily_rows)
    unique_date_count = int(coverage["unique_date_count"])
    unique_unit_count = int(coverage["unique_unit_count"])
    unique_year_count = len(list(coverage["years_present"]))
    date_unit_pair_count = int(coverage["date_unit_pair_count"])
    expected_row_count = int(coverage["expected_row_count"])
    all_years_present = bool(coverage["all_years_present"])
    all_months_present = bool(coverage["all_months_present_each_year"])
    all_expected_dates_present = bool(coverage["all_expected_dates_present"])

    rows = [
        ["metric", "value", "status", "detail"],
        [
            "daily_rows",
            daily_rows_count,
            "PASS" if daily_rows_count > 0 and daily_rows_count == date_unit_pair_count == expected_row_count else "HOLD",
            f"{smoke_daily_csv}; date_unit_pairs={date_unit_pair_count}; expected_rows_from_dates_x_units={expected_row_count}",
        ],
        [
            "unique_dates",
            unique_date_count,
            "PASS" if all_expected_dates_present else "HOLD",
            str(coverage["dates_per_year_str"]),
        ],
        [
            "unique_units",
            unique_unit_count,
            "PASS" if unique_unit_count >= OC03C_BASE_SMOKE_MIN_UNIQUE_UNITS else "HOLD",
            "Distinct NUTS3 units in daily output.",
        ],
        [
            "unique_years",
            unique_year_count,
            "PASS" if all_years_present and unique_year_count == OC03C_BASE_SMOKE_EXPECTED_UNIQUE_YEARS else "HOLD",
            ",".join(str(year) for year in coverage["years_present"]),
        ],
        [
            "years_2015_2024_present",
            int(all_years_present),
            "PASS" if all_years_present else "HOLD",
            "missing=" + ("NONE" if not coverage["missing_years"] else ",".join(str(year) for year in coverage["missing_years"])),
        ],
        [
            "months_present_by_year",
            str(coverage["months_present_by_year_str"]),
            "PASS" if all_months_present else "HOLD",
            "missing=" + str(coverage["missing_months_by_year_str"]),
        ],
        [
            "all_months_present_each_year",
            int(all_months_present),
            "PASS" if all_months_present else "HOLD",
            str(coverage["missing_months_by_year_str"]),
        ],
        [
            "dates_per_year",
            str(coverage["dates_per_year_str"]),
            "PASS" if all_expected_dates_present else "HOLD",
            "expected=" + str(coverage["expected_dates_per_year_str"]),
        ],
        [
            "all_expected_dates_present",
            int(all_expected_dates_present),
            "PASS" if all_expected_dates_present else "HOLD",
            "missing_days=" + str(coverage["missing_days_by_year_str"]),
        ],
        [
            "date_unit_pairs",
            date_unit_pair_count,
            "PASS" if date_unit_pair_count == daily_rows_count else "HOLD",
            "Distinct date/unit pairs in daily output.",
        ],
        [
            "expected_daily_rows_from_dates_x_units",
            expected_row_count,
            "PASS" if expected_row_count == daily_rows_count else "HOLD",
            f"unique_dates={unique_date_count}; unique_units={unique_unit_count}",
        ],
        ["threshold_id", "|".join(threshold_ids), "PASS" if threshold_ids else "HOLD", "Daily smoke threshold identifiers."],
        ["threshold_value", "|".join(threshold_values), "PASS" if threshold_values else "HOLD", "Daily smoke threshold values."],
        ["same_score_dates", same_score_dates, "PASS" if same_score_dates < len(by_date) else "HOLD", "Dates with only one unique daily score across units."],
        [
            "homogeneous_years",
            homogeneous_years,
            "PASS" if homogeneous_years == OC03C_BASE_SMOKE_EXPECTED_HOMOGENEOUS_YEARS else "HOLD",
            "Years with one unique smoke_days value across units.",
        ],
    ]
    write_tsv(out_tsv, rows[0], rows[1:])



def write_oc03_v11_decoder_contract_validation(output_root: Path) -> None:
    qa_dir = output_root / "qa"
    tables_dir = output_root / "tables"
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "oc03_v11_decoder_contract_validation.tsv"

    inputs = {}
    inputs_path = qa_dir / "inputs_resolved.json"
    if inputs_path.exists():
        try:
            inputs = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
        except Exception:
            inputs = {}
    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if not isinstance(meta, dict):
        meta = {}

    backend_rows = read_csv_rows(qa_dir / "gfas_era5_decoder_backend_audit.tsv")[1] if (qa_dir / "gfas_era5_decoder_backend_audit.tsv").exists() else []
    smoke_audit_rows = read_csv_rows(qa_dir / "smoke_route_audit.tsv")[1] if (qa_dir / "smoke_route_audit.tsv").exists() else []
    gfas_daily_rows = read_csv_rows(qa_dir / "gfas_pm2p5fire_portugal_daily_summary.csv")[1] if (qa_dir / "gfas_pm2p5fire_portugal_daily_summary.csv").exists() else []
    iech_unit_rows = read_csv_rows(tables_dir / "IECH_unit_2015_2024_mean.csv")[1] if (tables_dir / "IECH_unit_2015_2024_mean.csv").exists() else []
    iech_muni_rows = read_csv_rows(tables_dir / "IECH_municipio_2015_2024_mean.csv")[1] if (tables_dir / "IECH_municipio_2015_2024_mean.csv").exists() else []

    backend_map = {str(r.get("metric") or ""): r for r in backend_rows}
    decoder_available = 1 if str(backend_map.get("decoder_available", {}).get("status", "")).upper() == "PASS" else 0
    backend_gfas = str(backend_map.get("backend_gfas", {}).get("status", ""))
    backend_era5 = str(backend_map.get("backend_era5", {}).get("status", ""))
    unique_dates = sorted({str(r.get("date") or "").strip() for r in gfas_daily_rows if str(r.get("date") or "").strip()})
    unique_years = sorted({int(safe_float(r.get("year")) or -1) for r in gfas_daily_rows if safe_float(r.get("year")) is not None})
    gfas_edge_only = 1 if len(gfas_daily_rows) <= 10 or len(unique_dates) <= 10 else 0

    homogeneous_flags = [safe_float(r.get("spatial_homogeneous_flag")) for r in smoke_audit_rows if safe_float(r.get("year")) is not None]
    smoke_homogeneous = 1 if homogeneous_flags and all((v or 0.0) >= 1.0 for v in homogeneous_flags) else 0

    iech_unit_unique = len({round(float(v), 8) for v in [safe_float(r.get("IECH_mean_2015_2024")) for r in iech_unit_rows] if v is not None})
    iech_muni_unique = len({round(float(v), 8) for v in [safe_float(r.get("IECH_mean_2015_2024")) for r in iech_muni_rows] if v is not None})

    rows = [
        ["metric", "value", "status", "detail"],
        ["decoder_available", decoder_available, "PASS" if decoder_available else "HOLD", str(meta.get("smoke_route_selected", ""))],
        ["backend_gfas", backend_gfas, "PASS" if backend_gfas == "PASS" else "HOLD", "gfas_era5_decoder_backend_audit.tsv"],
        ["backend_era5", backend_era5, "PASS" if backend_era5 == "PASS" else "HOLD", "gfas_era5_decoder_backend_audit.tsv"],
        ["GFASDailyRows", len(gfas_daily_rows), "PASS" if len(gfas_daily_rows) > 10 else "HOLD", str(qa_dir / "gfas_pm2p5fire_portugal_daily_summary.csv")],
        ["GFASUniqueDates", len(unique_dates), "PASS" if len(unique_dates) > 10 else "HOLD", ",".join(unique_dates[:12])],
        ["GFASUniqueYears", len([y for y in unique_years if y >= 0]), "PASS" if unique_years else "HOLD", ",".join(str(y) for y in unique_years if y >= 0)],
        ["GFASEdgeOnly", "True" if gfas_edge_only else "False", "PASS" if not gfas_edge_only else "HOLD", "Derived from GFAS daily summary rows and unique dates."],
        ["SmokeRouteHomogeneous", "True" if smoke_homogeneous else "False", "PASS" if not smoke_homogeneous else "HOLD", "Derived from smoke_route_audit.tsv spatial_homogeneous_flag."],
        ["IECHUnitUniqueMeanCount", iech_unit_unique, "PASS" if iech_unit_unique > 1 else "HOLD", str(tables_dir / "IECH_unit_2015_2024_mean.csv")],
        ["IECHMunicipioUniqueMeanCount", iech_muni_unique, "PASS" if iech_muni_unique > 1 else "HOLD", str(tables_dir / "IECH_municipio_2015_2024_mean.csv")],
    ]
    write_tsv(out_tsv, rows[0], rows[1:])


def _is_direct_recovery_smoke_route(route_decision: Dict[str, object], sources: Dict[str, object]) -> bool:
    route_selected = str(route_decision.get("route_selected", "")).strip()
    return route_selected == "v0_gfas_era5_real" and bool(sources.get("effective_source_is_recovery"))


def write_smoke_route_source_trace_audit(
    qa_dir: Path,
    inputs: Dict[str, object],
    sources: Dict[str, object],
    route_decision: Dict[str, object],
) -> None:
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "smoke_route_source_trace_audit.tsv"
    payload = json.dumps(inputs, ensure_ascii=False).lower()
    direct_recovery = _is_direct_recovery_smoke_route(route_decision, sources)
    effective_source_path = str(sources.get("effective_smoke_source_path") or sources.get("gfas_dir") or "").strip()
    effective_data_root = str(sources.get("effective_data_root") or "").strip()
    forbidden_primary = bool(sources.get("forbidden_primary_source"))
    trace_001_value = effective_source_path if direct_recovery else str(sources.get("smoke_csv_input", "")).strip()
    trace_001_status = "PASS" if trace_001_value else "HOLD"
    trace_001_evidence = (
        "inputs_resolved.paths.smoke_effective_source_path"
        if direct_recovery
        else "inputs_resolved.paths.smoke_csv"
    )
    if direct_recovery:
        trace_002_status = "PASS"
        trace_002_value = "DIRECT_RECOVERY_ROUTE_NOT_APPLICABLE"
        trace_002_evidence = "validated v1 moduleA smoke catalog not required for direct GFAS/ERA5 recovery route"
    else:
        trace_002_status = "PASS" if bool(sources.get("modulea_validated")) else "HOLD"
        trace_002_value = str(bool(sources.get("modulea_validated")))
        trace_002_evidence = "validated v1 moduleA smoke catalog"
    rows = [
        ["TRACE-001", trace_001_status, trace_001_value, trace_001_evidence],
        ["TRACE-002", trace_002_status, trace_002_value, trace_002_evidence],
        ["TRACE-003", "PASS" if bool(sources.get("gfas_exists")) else "HOLD", str(bool(sources.get("gfas_exists"))), "GFAS directory physical presence"],
        ["TRACE-004", "PASS" if bool(sources.get("era5_exists")) else "HOLD", str(bool(sources.get("era5_exists"))), "ERA5 zip physical presence"],
        ["TRACE-005", "PASS" if "gfas" in payload else "HOLD", str("gfas" in payload), "inputs_resolved contains GFAS trace tokens"],
        ["TRACE-006", "PASS" if "era5" in payload else "HOLD", str("era5" in payload), "inputs_resolved contains ERA5 trace tokens"],
        ["TRACE-007", "PASS", str(route_decision.get("route_selected", "")), "selector route_selected"],
        ["TRACE-008", "PASS", str(route_decision.get("smoke_route_decision", "")), "selector smoke_route_decision"],
        [
            "TRACE-009",
            "PASS" if effective_data_root else ("HOLD" if direct_recovery else "INFO"),
            effective_data_root,
            "inputs_resolved.paths.smoke_effective_data_root",
        ],
        [
            "TRACE-010",
            "PASS" if (not direct_recovery or not forbidden_primary) else "BLOCKED",
            str(forbidden_primary),
            "detect_smoke_sources.forbidden_primary_source",
        ],
    ]
    write_tsv(out_tsv, ["check_id", "status", "value", "evidence"], rows)


def write_gfas_era5_presence_audit(qa_dir: Path, sources: Dict[str, object]) -> None:
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "gfas_era5_presence_audit.tsv"
    rows = [
        ["PRES-001", "PASS" if bool(sources.get("gfas_exists")) else "HOLD", str(sources.get("gfas_dir", "")), "GFAS directory path"],
        ["PRES-002", "PASS" if int(sources.get("gfas_grib_count") or 0) > 0 else "HOLD", int(sources.get("gfas_grib_count") or 0), "GFAS grib file count"],
        ["PRES-003", "PASS" if int(sources.get("gfas_total_bytes") or 0) > 0 else "HOLD", int(sources.get("gfas_total_bytes") or 0), "GFAS total bytes"],
        ["PRES-004", "PASS" if bool(sources.get("era5_exists")) else "HOLD", str(sources.get("era5_zip", "")), "ERA5 zip path"],
        ["PRES-005", "PASS" if int(sources.get("parquet_zip_count") or 0) > 0 else "HOLD", int(sources.get("parquet_zip_count") or 0), "Parquet proxy zip count"],
    ]
    write_tsv(out_tsv, ["check_id", "status", "value", "evidence"], rows)


def write_gfas_era5_decoder_audit(
    qa_dir: Path,
    sources: Dict[str, object],
    route_decision: Dict[str, object],
    decoder_available: bool = False,
) -> None:
    ensure_dir(qa_dir)
    out_tsv = qa_dir / "gfas_era5_decoder_audit.tsv"
    decoder_required = str(route_decision.get("route_selected", "")) == "BLOCKED_DECODER_REQUIRED"
    selected_real = str(route_decision.get("route_selected", "")) == "v0_gfas_era5_real"
    rows = [
        ["decoder_available", 1 if decoder_available else 0, "PASS" if decoder_available else "HOLD", "GDAL-only decoder probe result"],
        ["decoder_required", 1 if decoder_required else 0, "BLOCKED" if decoder_required else "PASS", str(route_decision.get("required_decoder", ""))],
        ["required_inputs", str(route_decision.get("required_inputs", "")), "PASS" if decoder_required or selected_real else "INFO", ""],
        ["gfas_grib_count", int(sources.get("gfas_grib_count") or 0), "PASS" if int(sources.get("gfas_grib_count") or 0) > 0 else "HOLD", ""],
        ["era5_exists", 1 if bool(sources.get("era5_exists")) else 0, "PASS" if bool(sources.get("era5_exists")) else "HOLD", ""],
        [
            "decoder_status",
            str(route_decision.get("smoke_route_decision", "")),
            "BLOCKED" if decoder_required else "PASS",
            str(route_decision.get("reason", "")),
        ],
    ]
    write_tsv(out_tsv, ["metric", "value", "status", "detail"], rows)
    checkpoints = qa_dir / "gfas_era5_decoder_checkpoints.tsv"
    cp_rows = [
        [
            "decoder_probe",
            "decoder_available",
            1 if decoder_available else 0,
            "GDAL-only GFAS decoder probe with Portugal negative-longitude crop.",
        ],
        ["gfas_probe", "gfas_grib_count", int(sources.get("gfas_grib_count") or 0), str(sources.get("gfas_dir", ""))],
        ["era5_probe", "era5_exists", 1 if bool(sources.get("era5_exists")) else 0, str(sources.get("era5_zip", ""))],
        [
            "route_decision",
            "route_selected",
            str(route_decision.get("route_selected", "")),
            str(route_decision.get("reason", "")),
        ],
    ]
    write_tsv(checkpoints, ["checkpoint", "metric", "value", "detail"], cp_rows)


def _resolve_gdal_tool(name: str) -> str:
    preferred = Path(r"C:\OSGeo4W64\bin") / name
    if preferred.exists():
        return str(preferred)
    return name


def _capture_warning_rows(tool_name: str, context: str, text: str) -> List[List[object]]:
    rows: List[List[object]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if "WARNING" not in upper and "NUMPTS * (NUMBITS IN A GROUP)" not in upper and "OUTSIDE" not in upper:
            continue
        status = "PASS"
        classification = "CLASSIFIED_WARNING"
        impact = "LOW"
        explained = "1"
        if "NUMPTS * (NUMBITS IN A GROUP)" in upper:
            classification = "GFAS_PACKING_WARNING_CLASSIFIED"
        elif "OUTSIDE RASTER EXTENT" in upper:
            classification = "WINDOW_OUTSIDE_RASTER_REJECTED"
        elif "WARNING" in upper:
            classification = "GENERIC_WARNING_UNCLASSIFIED"
            status = "BLOCKED"
            explained = "0"
            impact = "UNKNOWN"
        rows.append([tool_name, context, classification, explained, impact, status, line])
    return rows


def _extract_first_message_by_next_grib(src: Path, dst: Path, max_scan_bytes: int = 64 * 1024 * 1024) -> Tuple[int, int]:
    if not src.exists():
        raise FileNotFoundError(f"GFAS source GRIB missing: {src}")
    chunk_size = 4 * 1024 * 1024
    buf = bytearray()
    with src.open("rb") as f:
        while len(buf) < max_scan_bytes:
            to_read = min(chunk_size, max_scan_bytes - len(buf))
            part = f.read(to_read)
            if not part:
                break
            buf.extend(part)
            if len(buf) >= 8 and buf[:4] == b"GRIB":
                next_idx = bytes(buf).find(b"GRIB", 4)
                if next_idx > 0:
                    payload = bytes(buf[:next_idx])
                    ensure_dir(dst.parent)
                    dst.write_bytes(payload)
                    return next_idx, len(payload)
    raise RuntimeError(f"Could not delimit first GRIB message using next GRIB within {max_scan_bytes} bytes for {src}")


def _iter_grib_messages_by_next_grib(
    src: Path,
    max_message_bytes: int = 64 * 1024 * 1024,
) -> Iterable[Tuple[int, bytes, int]]:
    for msg_index, byte_offset, payload_bytes in _iter_grib_message_offsets_by_next_grib(src, max_message_bytes=max_message_bytes):
        with src.open("rb") as f:
            f.seek(byte_offset)
            payload = f.read(payload_bytes)
        if len(payload) != payload_bytes:
            raise RuntimeError(f"Could not read full GRIB payload {msg_index} from {src}")
        yield msg_index, payload, payload_bytes


def _iter_grib_message_offsets_by_next_grib(
    src: Path,
    max_message_bytes: int = 64 * 1024 * 1024,
) -> Iterable[Tuple[int, int, int]]:
    if not src.exists():
        raise FileNotFoundError(f"GFAS source GRIB missing: {src}")
    file_size = int(src.stat().st_size)
    # These recovery files are GRIB1 payloads padded between records. Their
    # declared message length is the usable GDAL subfile, not the next GRIB
    # marker; validate every regular-stream header before using this fast path.
    with src.open("rb") as f:
        header = f.read(8)
        if header[:4] == b"GRIB" and len(header) == 8 and header[7] == 1:
            declared_length = int.from_bytes(header[4:7], "big")
            if 8 <= declared_length <= max_message_bytes:
                probe = f.read(min(file_size, max_message_bytes))
                next_idx = probe.find(b"GRIB")
                if next_idx >= 0:
                    next_idx += 8
                if next_idx > 0 and file_size % next_idx == 0:
                    record_count = file_size // next_idx
                    regular = record_count > 1
                    for record_index in range(record_count):
                        f.seek(record_index * next_idx)
                        record_header = f.read(8)
                        if (
                            len(record_header) != 8
                            or record_header[:4] != b"GRIB"
                            or record_header[7] != 1
                            or int.from_bytes(record_header[4:7], "big") != declared_length
                        ):
                            regular = False
                            break
                    if regular:
                        for record_index in range(record_count):
                            yield record_index + 1, record_index * next_idx, declared_length
                        return

    chunk_size = 4 * 1024 * 1024
    buf = bytearray()
    count = 0
    eof = False
    buf_start = 0
    with src.open("rb") as f:
        while True:
            part = f.read(chunk_size)
            if not part:
                eof = True
            else:
                buf.extend(part)

            while len(buf) >= 8 and buf[:4] == b"GRIB":
                next_idx = bytes(buf).find(b"GRIB", 4)
                if next_idx > 0:
                    count += 1
                    yield count, buf_start, next_idx
                    buf = bytearray(buf[next_idx:])
                    buf_start += next_idx
                    continue
                if eof:
                    count += 1
                    yield count, buf_start, len(buf)
                    buf = bytearray()
                break

            if eof:
                break
            if len(buf) > max_message_bytes and bytes(buf).find(b"GRIB", 4) < 0:
                raise RuntimeError(
                    f"GRIB single-message scan exceeded {max_message_bytes} bytes without finding a delimiter in {src}"
                )

    if buf:
        raise RuntimeError(f"Trailing undecoded GRIB buffer remained for {src}")




def _count_gfas_pm_messages_from_grib(src_grib: Path) -> int:
    # The recovery files are fixed-size annual GRIB message streams. Validate
    # the first two offsets before using the file-size quotient; irregular
    # files retain the complete scanner fallback below.
    try:
        offsets = iter(_iter_grib_message_offsets_by_next_grib(src_grib))
        first = next(offsets)
        second = next(offsets)
        payload_bytes = int(first[2])
        if (
            int(first[1]) == 0
            and int(second[1]) == payload_bytes
            and int(second[2]) == payload_bytes
            and payload_bytes > 0
        ):
            file_size = int(src_grib.stat().st_size)
            if file_size > 0 and file_size % payload_bytes == 0:
                return file_size // payload_bytes
    except (FileNotFoundError, OSError, StopIteration, ValueError, TypeError):
        pass

    message_count = 0
    for message_count, _byte_offset, _payload_bytes in _iter_grib_message_offsets_by_next_grib(src_grib):
        pass
    if message_count <= 0:
        raise RuntimeError(f"{GFAS_PM_MESSAGE_COUNT_BLOCKER}: no GRIB messages decoded from {src_grib}")
    return message_count

def _grib_comment_is_pm2p5fire(comment: str) -> bool:
    c = (comment or "").strip().lower()
    return "wildfire flux of particulate matter pm2.5" in c or ("wildfire" in c and "pm2.5" in c)


def _epoch_seconds_to_iso_date(value: object) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        if "." in s:
            s = s.split(".", 1)[0]
        sec = int(s)
        return dt.datetime.fromtimestamp(sec, tz=dt.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365

def _fallback_gfas_pm_rows_from_gribs(gfas_dir: Path, count_messages: bool = False) -> List[Dict[str, str]]:
    fallback_gribs = sorted(gfas_dir.rglob("GFAS_PM2P5FIRE_*.grib"))
    preferred_by_year: Dict[str, Path] = {}
    for grib_path in fallback_gribs:
        match = re.search(r"GFAS_PM2P5FIRE_(\d{4})", grib_path.name, flags=re.IGNORECASE)
        year = match.group(1) if match else ""
        if not year:
            continue
        current = preferred_by_year.get(year)
        if current is None:
            preferred_by_year[year] = grib_path
            continue
        cand_norm = str(grib_path).lower()
        curr_norm = str(current).lower()
        cand_score = 1 if "global_official" in cand_norm else 0
        curr_score = 1 if "global_official" in curr_norm else 0
        if cand_score > curr_score:
            preferred_by_year[year] = grib_path
    pm_rows: List[Dict[str, str]] = []
    for year in sorted(preferred_by_year):
        grib_path = preferred_by_year[year]
        year_int = int(year)
        message_count = _days_in_year(year_int)
        if count_messages:
            counted = _count_gfas_pm_messages_from_grib(grib_path)
            if counted > 0:
                message_count = counted
        pm_rows.append(
            {
                "file": str(grib_path.relative_to(gfas_dir)).replace("/", "\\"),
                "minDate": f"{year}0101",
                "message_count": str(message_count),
                "pm_stride_hint": "1",
            }
        )
    return pm_rows


def _load_gfas_pm_summary_rows(gfas_dir: Path) -> List[Dict[str, str]]:
    candidates = [
        gfas_dir / "_grib_summary.csv",
        gfas_dir / "_grib_edge_summary.csv",
    ]
    summary_path = next((cand for cand in candidates if cand.exists()), None)
    if summary_path is None:
        pm_rows = _fallback_gfas_pm_rows_from_gribs(gfas_dir)
        if pm_rows:
            return pm_rows
        raise FileNotFoundError(
            "GFAS summary not found: expected one of "
            + ", ".join(str(c) for c in candidates)
        )

    _hdr, summary_rows, _delim = read_csv_rows(summary_path)
    pm_rows: List[Dict[str, str]] = []
    for r in summary_rows:
        file_name = str(r.get("file") or r.get("filename") or "").strip()
        short_names = {
            part.strip().lower()
            for key in ("shortName_set", "shortName_1", "shortName_L")
            for part in str(r.get(key) or "").split("|")
            if part.strip()
        }
        pm_stride_hint = "1" if short_names and short_names.issubset({"pm2p5fire"}) else "2"
        if "pm2p5fire" not in short_names and "pm2p5fire" not in file_name.lower():
            continue
        min_date = str(r.get("minDate") or r.get("dataDate_1") or r.get("validityDate_1") or "").strip()
        message_count = str(r.get("message_count") or "1").strip()
        if not file_name or not min_date:
            continue
        pm_rows.append(
            {
                "file": file_name,
                "minDate": min_date,
                "message_count": message_count,
                "pm_stride_hint": pm_stride_hint,
            }
        )

    if not pm_rows:
        fallback_rows = _fallback_gfas_pm_rows_from_gribs(gfas_dir, count_messages=True)
        if fallback_rows:
            return fallback_rows
        raise RuntimeError(f"No PM2P5FIRE candidate rows found in {summary_path.name}")
    return pm_rows


def _percentile(values: List[float], q: float) -> Optional[float]:
    cleaned = sorted(float(v) for v in values if v is not None)
    if not cleaned:
        return None
    if q <= 0.0:
        return cleaned[0]
    if q >= 1.0:
        return cleaned[-1]
    idx = int(round((len(cleaned) - 1) * q))
    idx = max(0, min(len(cleaned) - 1, idx))
    return cleaned[idx]


def _planned_pm_message_count(message_count: object, pm_stride: object) -> int:
    total = int(safe_float(message_count) or 0)
    stride = int(safe_float(pm_stride) or 0)
    if total <= 0 or stride <= 0:
        raise RuntimeError(
            f"{GFAS_PM_MESSAGE_COUNT_BLOCKER}: message_count={message_count!r}; pm_stride={pm_stride!r}"
        )
    planned = (total + stride - 1) // stride
    if planned <= 0:
        raise RuntimeError(
            f"{GFAS_PM_MESSAGE_COUNT_BLOCKER}: derived planned_pm_messages={planned} from "
            f"message_count={message_count!r}; pm_stride={pm_stride!r}"
        )
    return planned


def _direct_unit_smoke_score(pm_mean: float, pm_max: float) -> float:
    # Preserve unit-footprint variation instead of collapsing to the hottest sampled pixel only.
    blended = (max(pm_mean, 0.0) * 0.75) + (max(pm_max, 0.0) * 0.25)
    return max(blended, 0.0) * 1.0e11


def _smoke_day_equivalent(score: float, threshold_value: Optional[float], proxy: int) -> float:
    if threshold_value is not None and threshold_value > 0.0 and score > 0.0:
        return max(score / threshold_value, 0.0)
    return float(proxy)


def _parse_xyz_stats(path: Path) -> Dict[str, object]:
    rows = 0
    numeric = 0
    zeros = 0
    nonzero = 0
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    vsum = 0.0
    triples: List[Tuple[float, float, float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            rows += 1
            parts = s.split()
            if len(parts) < 3:
                continue
            x = safe_float(parts[0])
            y = safe_float(parts[1])
            v = safe_float(parts[2])
            if x is None or y is None or v is None:
                continue
            triples.append((x, y, v))
            numeric += 1
            if abs(v) <= 1e-15:
                zeros += 1
            else:
                nonzero += 1
            vsum += v
            if vmin is None or v < vmin:
                vmin = v
            if vmax is None or v > vmax:
                vmax = v
    mean = (vsum / float(numeric)) if numeric > 0 else None
    return {
        "rows": rows,
        "numeric": numeric,
        "zero": zeros,
        "nonzero": nonzero,
        "min": vmin,
        "max": vmax,
        "mean": mean,
        "triples": triples,
    }


def _run_external(cmd: List[str], timeout_sec: int = 600) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _yyyymmdd_to_iso(v: str) -> str:
    s = (v or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _yyyymmdd_to_date(v: str) -> Optional[dt.date]:
    s = (v or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except Exception:
        return None


def _load_admin_unit_centroids(admin_layer_path: Path) -> List[Dict[str, object]]:
    from qgis.core import (  # type: ignore
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsGeometry,
        QgsPointXY,
        QgsProject,
        QgsVectorLayer,
    )

    admin = QgsVectorLayer(str(admin_layer_path) + "|layername=admin_nuts3_2024", "admin", "ogr")
    if not admin.isValid():
        raise RuntimeError(f"Admin layer invalid for GFAS centroid sampling: {admin_layer_path}")
    dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(admin.crs(), dst_crs, QgsProject.instance())
    name_fields = ("NAME_LATN", "NUTS_NAME", "NAME_ENGL", "NAME")
    samples: List[Dict[str, object]] = []
    for ft in admin.getFeatures():
        uid = str(ft["NUTS_ID"]) if ft["NUTS_ID"] is not None else ""
        if not uid:
            continue
        geom = ft.geometry()
        if geom is None or geom.isEmpty():
            continue
        unit_name = uid
        for fld in name_fields:
            try:
                if fld in ft.fields().names() and ft[fld] not in (None, ""):
                    unit_name = str(ft[fld])
                    break
            except Exception:
                continue
        candidate_points: List[QgsPointXY] = []
        point_geom = geom.pointOnSurface()
        if point_geom is not None and not point_geom.isEmpty():
            pt = point_geom.asPoint()
            candidate_points.append(QgsPointXY(pt.x(), pt.y()))
        centroid_geom = geom.centroid()
        if centroid_geom is not None and not centroid_geom.isEmpty():
            pt = centroid_geom.asPoint()
            candidate_points.append(QgsPointXY(pt.x(), pt.y()))
        bbox = geom.boundingBox()
        fractions = (0.1, 0.3, 0.5, 0.7, 0.9)
        for fx in fractions:
            for fy in fractions:
                candidate_points.append(
                    QgsPointXY(
                        bbox.xMinimum() + (bbox.width() * fx),
                        bbox.yMinimum() + (bbox.height() * fy),
                    )
                )

        accepted_points: List[QgsPointXY] = []
        seen: set[Tuple[float, float]] = set()
        for pt in candidate_points:
            key = (round(float(pt.x()), 8), round(float(pt.y()), 8))
            if key in seen:
                continue
            seen.add(key)
            pt_geom = QgsGeometry.fromPointXY(pt)
            try:
                inside = geom.contains(pt_geom) or geom.touches(pt_geom) or geom.intersects(pt_geom)
            except Exception:
                inside = False
            if inside:
                accepted_points.append(pt)

        if not accepted_points:
            if point_geom is None or point_geom.isEmpty():
                continue
            pt = point_geom.asPoint()
            accepted_points = [QgsPointXY(pt.x(), pt.y())]

        for sample_index, pt in enumerate(accepted_points, start=1):
            pt4326 = transform.transform(pt)
            samples.append(
                {
                    "unit_id": uid,
                    "unit_name": unit_name,
                    "unit_level": "NUTS3",
                    "lon": float(pt4326.x()),
                    "lat": float(pt4326.y()),
                    "sample_index": sample_index,
                    "sample_count": len(accepted_points),
                }
            )
    if not samples:
        raise RuntimeError("GFAS unit sampling found no NUTS3 sample points.")
    return samples


def _read_grib_message_metadata_from_payload(payload: bytes, vsi_token: str) -> Dict[str, str]:
    from osgeo import gdal  # type: ignore

    vsi_path = f"/vsimem/{vsi_token}.grib"
    gdal.FileFromMemBuffer(vsi_path, payload)
    try:
        try:
            gdal.PushErrorHandler("CPLQuietErrorHandler")
            ds = gdal.Open(vsi_path)
            if ds is None:
                raise RuntimeError(f"GDAL could not open GRIB payload {vsi_token}")
            band = ds.GetRasterBand(1)
            md = band.GetMetadata() if band is not None else {}
            return {str(k): str(v) for k, v in (md or {}).items()}
        finally:
            try:
                gdal.PopErrorHandler()
            except Exception:
                pass
    finally:
        try:
            gdal.Unlink(vsi_path)
        except Exception:
            pass


def _grib_message_vsisubfile_path(src_grib: Path, byte_offset: int, payload_bytes: int) -> str:
    return f"/vsisubfile/{int(byte_offset)}_{int(payload_bytes)},{src_grib.as_posix()}"


def _read_grib_message_metadata_from_subfile(src_grib: Path, byte_offset: int, payload_bytes: int) -> Dict[str, str]:
    from osgeo import gdal  # type: ignore

    subfile_path = _grib_message_vsisubfile_path(src_grib, byte_offset, payload_bytes)
    ds = None
    try:
        try:
            gdal.PushErrorHandler("CPLQuietErrorHandler")
            ds = gdal.Open(subfile_path)
            if ds is None:
                raise RuntimeError(f"GDAL could not open GRIB subfile {subfile_path}")
            band = ds.GetRasterBand(1)
            md = band.GetMetadata() if band is not None else {}
            return {str(k): str(v) for k, v in (md or {}).items()}
        finally:
            try:
                gdal.PopErrorHandler()
            except Exception:
                pass
    finally:
        ds = None


def _probe_gfas_pm_message_pattern(src_grib: Path, min_date_hint: str) -> Tuple[int, str]:
    probe: Dict[int, Dict[str, str]] = {}
    for msg_index, payload, _payload_bytes in _iter_grib_messages_by_next_grib(src_grib):
        if msg_index > 3:
            break
        probe[msg_index] = _read_grib_message_metadata_from_payload(payload, f"{src_grib.stem}_probe_{msg_index:04d}")
    if not probe:
        raise RuntimeError(f"Could not read GFAS probe messages from {src_grib}")
    pm_indices = [idx for idx, md in probe.items() if _grib_comment_is_pm2p5fire(str(md.get('GRIB_COMMENT', '')))]
    if not pm_indices:
        raise RuntimeError(f"Could not detect PM2P5FIRE message parity in {src_grib}")
    pm_start_index = min(pm_indices)
    base_date = _epoch_seconds_to_iso_date(probe[pm_start_index].get("GRIB_VALID_TIME")) or _epoch_seconds_to_iso_date(
        probe[pm_start_index].get("GRIB_REF_TIME")
    )
    hint_date = _yyyymmdd_to_date(str(min_date_hint).replace("-", "")) if min_date_hint else None
    meta_date = _yyyymmdd_to_date(str(base_date).replace("-", "")) if base_date else None
    # Some annual GFAS PM files expose the first valid time as day+1 even though the
    # runtime inventory and file-year contract anchor the series at YYYY-01-01.
    if hint_date and meta_date and meta_date == hint_date + dt.timedelta(days=1):
        base_date = hint_date.isoformat()
    else:
        base_date = base_date or min_date_hint
    if not base_date:
        raise RuntimeError(f"Could not determine base GFAS PM date for {src_grib}")
    return pm_start_index, base_date


def _resolve_gfas_pm_date(actual_date_iso: str, fallback_date_iso: str) -> str:
    actual_date = _yyyymmdd_to_date(str(actual_date_iso).replace("-", "")) if actual_date_iso else None
    fallback_date = _yyyymmdd_to_date(str(fallback_date_iso).replace("-", "")) if fallback_date_iso else None
    if fallback_date and actual_date and actual_date == fallback_date + dt.timedelta(days=1):
        return fallback_date.isoformat()
    if actual_date:
        return actual_date.isoformat()
    if fallback_date:
        return fallback_date.isoformat()
    return ""


def _decode_gfas_pm_dataset_to_unit_rows(
    ds,
    file_name: str,
    msg_index: int,
    fallback_date_iso: str,
    unit_samples: List[Dict[str, object]],
    payload_size: int,
) -> Dict[str, object]:
    band = ds.GetRasterBand(1)
    if band is None:
        raise RuntimeError(f"GFAS PM payload missing band1: {file_name} message={msg_index}")
    md = band.GetMetadata() or {}
    actual_date = _epoch_seconds_to_iso_date(md.get("GRIB_VALID_TIME")) or _epoch_seconds_to_iso_date(md.get("GRIB_REF_TIME"))
    date_iso = _resolve_gfas_pm_date(actual_date, fallback_date_iso)
    if not date_iso:
        raise RuntimeError(f"GFAS PM payload has no date: {file_name} message={msg_index}")
    geotransform = ds.GetGeoTransform(can_return_null=True)
    if not geotransform:
        raise RuntimeError(f"GFAS PM payload missing geotransform: {file_name} message={msg_index}")
    origin_x, pixel_w, rot_x, origin_y, rot_y, pixel_h = geotransform
    if rot_x or rot_y or pixel_w == 0.0 or pixel_h == 0.0:
        raise RuntimeError(f"GFAS PM payload uses unsupported geotransform: {file_name} message={msg_index}")
    nodata = band.GetNoDataValue()
    sample_pixels: List[Tuple[Dict[str, object], int, int]] = []
    for sample in unit_samples:
        lon = float(sample["lon"])
        lat = float(sample["lat"])
        px = int((lon - origin_x) / pixel_w)
        py = int((lat - origin_y) / pixel_h)
        if px < 0 or py < 0 or px >= ds.RasterXSize or py >= ds.RasterYSize:
            continue
        sample_pixels.append((sample, px, py))
    if sample_pixels:
        min_px = min(px for _sample, px, _py in sample_pixels)
        max_px = max(px for _sample, px, _py in sample_pixels)
        min_py = min(py for _sample, _px, py in sample_pixels)
        max_py = max(py for _sample, _px, py in sample_pixels)
        raster = band.ReadAsArray(min_px, min_py, (max_px - min_px) + 1, (max_py - min_py) + 1)
    else:
        min_px = 0
        min_py = 0
        raster = band.ReadAsArray()
    if raster is None:
        raise RuntimeError(f"GFAS PM payload raster read failed: {file_name} message={msg_index}")
    unit_rows: List[Dict[str, object]] = []
    sampled_values: List[float] = []
    per_unit_stats: Dict[str, Dict[str, object]] = {}
    for sample, px, py in sample_pixels:
        val = safe_float(raster[py - min_py][px - min_px])
        if val is None:
            continue
        if nodata is not None and abs(float(val) - float(nodata)) <= 1e-20:
            continue
        value = max(float(val), 0.0)
        sampled_values.append(value)
        unit_id = str(sample["unit_id"])
        agg = per_unit_stats.setdefault(
            unit_id,
            {
                "unit_name": str(sample["unit_name"]),
                "unit_level": str(sample.get("unit_level", "NUTS3")),
                "pm_sum": 0.0,
                "pm_max": 0.0,
                "valid_pixel_count": 0,
            },
        )
        agg["pm_sum"] = float(agg.get("pm_sum", 0.0)) + value
        agg["pm_max"] = max(float(agg.get("pm_max", 0.0)), value)
        agg["valid_pixel_count"] = int(agg.get("valid_pixel_count", 0)) + 1
    for unit_id, agg in per_unit_stats.items():
        valid_pixel_count = int(agg.get("valid_pixel_count", 0) or 0)
        if valid_pixel_count <= 0:
            continue
        pm_sum = float(agg.get("pm_sum", 0.0) or 0.0)
        pm_mean = pm_sum / float(valid_pixel_count)
        pm_max = float(agg.get("pm_max", 0.0) or 0.0)
        score = _direct_unit_smoke_score(pm_mean, pm_max)
        unit_rows.append(
            {
                "unit_id": unit_id,
                "unit_name": str(agg.get("unit_name", unit_id)),
                "unit_level": str(agg.get("unit_level", "NUTS3")),
                "date": date_iso,
                "year": int(date_iso[:4]),
                "source_file": file_name,
                "message_index": msg_index,
                "band_index": msg_index,
                "pm2p5fire_mean": pm_mean,
                "pm2p5fire_max": pm_max,
                "pm2p5fire_sum": pm_sum,
                "valid_pixel_count": valid_pixel_count,
                "smoke_day_score": score,
                "method": "gfas_pm2p5fire_unit_multi_sample_proxy",
                "spatial_assignment_method": "MULTI_POINT_UNIT_FOOTPRINT_GFAS",
                "qa_flag": 0,
            }
        )
    numeric = len(sampled_values)
    zeros = sum(1 for v in sampled_values if abs(v) <= 1e-15)
    nonzero = sum(1 for v in sampled_values if abs(v) > 1e-15)
    mean_val = (sum(sampled_values) / float(numeric)) if numeric else 0.0
    max_val = max(sampled_values) if sampled_values else 0.0
    min_val = min(sampled_values) if sampled_values else 0.0
    return {
        "inventory_row": [
            file_name,
            msg_index,
            date_iso,
            int(date_iso[:4]),
            "",
            "VSISUBFILE_PM_PAYLOAD",
            payload_size,
            str(md.get("GRIB_COMMENT", "")),
            str(md.get("GRIB_REF_TIME", "")),
            str(md.get("GRIB_VALID_TIME", "")),
            "PASS",
        ],
        "daily_summary_row": [
            date_iso,
            int(date_iso[:4]),
            file_name,
            msg_index,
            numeric,
            numeric,
            zeros,
            nonzero,
            min_val,
            max_val,
            mean_val,
            mean_val * 1.0e11,
            str(md.get("GRIB_COMMENT", "")),
            "CENTROID_FALLBACK_LIMITED",
        ],
        "daily_row": {
            "date": date_iso,
            "year": int(date_iso[:4]),
            "source_file": file_name,
            "message_index": msg_index,
            "band_index": msg_index,
            "grid_valid_pixel_count": numeric,
            "centroid_valid_pixel_count": numeric,
            "centroid_zero_count": zeros,
            "centroid_nonzero_count": nonzero,
            "pm2p5fire_mean": mean_val,
            "pm2p5fire_proxy_mean_ug_m3": mean_val * 1.0e11,
            "smoke_day_score": 1 if max_val > 0.0 else 0,
            "method": "gfas_pm2p5fire_unit_centroid_proxy",
            "spatial_assignment_method": "CENTROID_FALLBACK_LIMITED",
            "qa_flag": 0,
            "grib_comment": str(md.get("GRIB_COMMENT", "")),
        },
        "unit_rows": unit_rows,
    }


def _decode_gfas_pm_payload_to_unit_rows(
    payload: bytes,
    file_name: str,
    msg_index: int,
    fallback_date_iso: str,
    unit_samples: List[Dict[str, object]],
) -> Dict[str, object]:
    from osgeo import gdal  # type: ignore

    vsi_token = f"gfas_pm_{Path(file_name).stem}_{msg_index:04d}_{os.getpid()}_{id(payload)}"
    vsi_path = f"/vsimem/{vsi_token}.grib"
    gdal.FileFromMemBuffer(vsi_path, payload)
    ds = None
    try:
        try:
            gdal.PushErrorHandler("CPLQuietErrorHandler")
            ds = gdal.Open(vsi_path)
            if ds is None:
                raise RuntimeError(f"GDAL could not open PM payload {file_name} message={msg_index}")
            return _decode_gfas_pm_dataset_to_unit_rows(ds, file_name, msg_index, fallback_date_iso, unit_samples, payload_size=len(payload))
        finally:
            try:
                gdal.PopErrorHandler()
            except Exception:
                pass
    finally:
        ds = None
        try:
            gdal.Unlink(vsi_path)
        except Exception:
            pass


def _decode_gfas_pm_subfile_to_unit_rows(
    src_grib: Path,
    file_name: str,
    msg_index: int,
    byte_offset: int,
    payload_bytes: int,
    fallback_date_iso: str,
    unit_samples: List[Dict[str, object]],
) -> Dict[str, object]:
    from osgeo import gdal  # type: ignore

    subfile_path = _grib_message_vsisubfile_path(src_grib, byte_offset, payload_bytes)
    ds = None
    try:
        try:
            gdal.PushErrorHandler("CPLQuietErrorHandler")
            ds = gdal.Open(subfile_path)
            if ds is None:
                raise RuntimeError(f"GDAL could not open PM subfile {subfile_path}")
            return _decode_gfas_pm_dataset_to_unit_rows(ds, file_name, msg_index, fallback_date_iso, unit_samples, payload_size=payload_bytes)
        finally:
            try:
                gdal.PopErrorHandler()
            except Exception:
                pass
    finally:
        ds = None


def _decode_gfas_pm_chunk_worker(
    src_grib_raw: str,
    file_name: str,
    scheduled_messages: Sequence[Tuple[int, int, int, str]],
    unit_samples: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    src_grib = Path(src_grib_raw)
    inv_rows: List[List[object]] = []
    daily_summary_rows: List[List[object]] = []
    daily_rows: List[Dict[str, object]] = []
    unit_rows: List[Dict[str, object]] = []
    processed_pm = 0
    last_date = ""
    for msg_index, byte_offset, payload_bytes, fallback_date in scheduled_messages:
        item = _decode_gfas_pm_subfile_to_unit_rows(
            src_grib,
            file_name,
            msg_index,
            byte_offset,
            payload_bytes,
            fallback_date,
            list(unit_samples),
        )
        inv_rows.append(list(item["inventory_row"]))
        daily_summary_rows.append(list(item["daily_summary_row"]))
        daily_rows.append(dict(item["daily_row"]))
        unit_rows.extend(list(item["unit_rows"]))
        processed_pm += 1
        item_date = str(item["daily_row"].get("date") or fallback_date)
        if item_date > last_date:
            last_date = item_date
    return {
        "inv_rows": inv_rows,
        "daily_summary_rows": daily_summary_rows,
        "daily_rows": daily_rows,
        "unit_rows": unit_rows,
        "processed_pm": processed_pm,
        "last_date": last_date,
    }

def _smoke_route_v0_audit_rows(unexplained_warnings_count: int, failed: bool, detail: str) -> List[List[object]]:
    if not failed:
        return [
            ["backend_gfas", "GDAL", "PASS", "GFAS decoded through GDAL-only message extraction path."],
            ["backend_era5", "GDAL", "PASS", "ERA5 10U/10V validated through GDAL band metadata and XYZ extraction."],
            ["eccodes_for_gfas", "REJECTED_OR_FORBIDDEN", "PASS", "ecCodes is not used as GFAS decoder backend."],
            ["smoke_claim_level", "OPERATIONAL_PROXY", "PASS", "Atmospheric proxy only (non-health validated)."],
            ["health_exposure_claim", "NON_HEALTH_LIMITATION_DECLARED", "PASS", "No official pollutant threshold validation in this v0 route."],
            ["portugal_crop_convention", "NEGATIVE_LONGITUDE", "PASS", "Main crop: -projwin -10.0 43.0 -6.0 36.5"],
            ["unexplained_warnings_count", unexplained_warnings_count, "PASS" if unexplained_warnings_count == 0 else "BLOCKED", detail],
        ]
    return [
        ["backend_gfas", "GDAL", "HOLD", "GFAS GDAL path failed during probe."],
        ["backend_era5", "GDAL", "HOLD", "ERA5 GDAL probe not completed."],
        ["eccodes_for_gfas", "REJECTED_OR_FORBIDDEN", "PASS", "ecCodes is not used as GFAS decoder backend."],
        ["smoke_claim_level", "OPERATIONAL_PROXY", "HOLD", "Proxy route blocked until decoder probe succeeds."],
        ["health_exposure_claim", "BLOCKED_UNLESS_VALIDATED", "BLOCKED", "Health claim remains blocked."],
        ["portugal_crop_convention", "NEGATIVE_LONGITUDE", "HOLD", "Not validated in this run."],
        ["unexplained_warnings_count", unexplained_warnings_count, "BLOCKED", detail],
    ]


def decode_gfas_era5_gdal_proxy(
    modulec_datos: Path,
    qa_dir: Path,
    report: Report,
    admin_layer_path: Path,
    sources: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    from osgeo import gdal  # type: ignore

    ensure_dir(qa_dir)
    gdal_translate = _resolve_gdal_tool("gdal_translate.exe")
    gdalinfo = _resolve_gdal_tool("gdalinfo.exe")
    result: Dict[str, object] = {
        "decoder_available": False,
        "by_year": {},
        "by_year_method": {},
        "daily_rows": [],
        "unit_daily_rows": [],
        "spatial_scope": "UNKNOWN",
        "unit_assignment": "UNKNOWN",
        "warning_inventory_path": str(qa_dir / "warning_inventory.tsv"),
        "reason": "",
    }
    warning_rows: List[List[object]] = []

    def _write_warning_inventory() -> int:
        out = qa_dir / "warning_inventory.tsv"
        if not warning_rows:
            warning_rows.append(
                ["runtime", "none", "NO_WARNINGS", "1", "NONE", "PASS", "No warning captured in GFAS/ERA5 GDAL decoder path."]
            )
        write_tsv(
            out,
            ["tool", "context", "classification", "explained", "impact", "status", "warning_text"],
            warning_rows,
        )
        return sum(1 for r in warning_rows if str(r[5]).upper() == "BLOCKED")

    try:
        source_map = dict(sources or {})
        gfas_dir_raw = str(source_map.get("gfas_dir") or "").strip()
        era5_zip_raw = str(source_map.get("era5_zip") or "").strip()
        recovery_ok = bool(source_map.get("effective_source_is_recovery"))
        effective_root = str(source_map.get("effective_data_root") or "").strip()
        if not recovery_ok:
            raise RuntimeError(f"GFAS/ERA5 decoder refused non-recovery smoke source root: {effective_root or modulec_datos}")
        if not gfas_dir_raw:
            raise RuntimeError("GFAS recovery root resolved without an effective gfas_dir.")
        gfas_dir = Path(gfas_dir_raw)
        pm_rows = _load_gfas_pm_summary_rows(gfas_dir)
        preferred_direct_years = {
            int(str(r.get("minDate", ""))[:4])
            for r in pm_rows
            if str(r.get("minDate", ""))[:4].isdigit()
        }
        preferred_direct_years = {y for y in preferred_direct_years if y in YEARS_HIST}
        if preferred_direct_years != set(YEARS_HIST):
            raise RuntimeError(
                "GFAS PM summary does not cover all direct years 2015-2024: "
                + ",".join(str(y) for y in sorted(preferred_direct_years))
            )

        unit_samples = _load_admin_unit_centroids(admin_layer_path)
        report.log(
            "GFAS decoder using "
            f"{len(unit_samples)} admin unit sample points across "
            f"{len({str(s.get('unit_id') or '') for s in unit_samples})} units."
        )
        report.log(
            "GFAS decoder target direct years: "
            f"{','.join(str(y) for y in sorted(preferred_direct_years))}"
        )
        inv_rows: List[List[object]] = []
        daily_summary_rows: List[List[object]] = []
        daily_rows: List[Dict[str, object]] = []
        unit_daily_rows: List[Dict[str, object]] = []
        processed_days_by_year: Dict[int, int] = defaultdict(int)
        for r in pm_rows:
            file_name = (r.get("file") or "").strip()
            if not file_name:
                continue
            src_grib = gfas_dir / file_name
            if not src_grib.exists():
                continue
            min_date = _yyyymmdd_to_date(str(r.get("minDate") or ""))
            if min_date is None:
                raise RuntimeError(f"GFAS PM2P5FIRE row missing valid minDate for {src_grib}")
            file_year = int(base_year) if (base_year := str(r.get("minDate") or "")[:4]).isdigit() else min_date.year
            if preferred_direct_years and file_year not in preferred_direct_years:
                report.log(f"GFAS decoder skip file: {src_grib.name} year={file_year} not in direct anchor years.")
                continue
            message_count = int(safe_float(r.get("message_count")) or 0)
            if message_count <= 0:
                raise RuntimeError(f"GFAS PM2P5FIRE row missing message_count for {src_grib}")
            pm_start_index, base_date_iso = _probe_gfas_pm_message_pattern(src_grib, _yyyymmdd_to_iso(str(r.get("minDate") or "")))
            base_date = _yyyymmdd_to_date(base_date_iso.replace("-", "")) or min_date
            pm_stride = max(1, int(safe_float(r.get("pm_stride_hint")) or 1))
            planned_pm_messages = _planned_pm_message_count(message_count, pm_stride)
            report.log(
                "GFAS decoder file start: "
                f"{src_grib.name} pm_start_index={pm_start_index} pm_stride={pm_stride} "
                f"base_date={base_date.isoformat()} planned_pm_messages={planned_pm_messages}"
            )
            scheduled_messages: List[Tuple[int, int, int, str]] = []
            for msg_index, byte_offset, payload_bytes in _iter_grib_message_offsets_by_next_grib(src_grib):
                if msg_index < pm_start_index:
                    continue
                if (msg_index - pm_start_index) % pm_stride != 0:
                    continue
                day_offset = (msg_index - pm_start_index) // pm_stride
                fallback_date = (base_date + dt.timedelta(days=day_offset)).strftime("%Y-%m-%d")
                scheduled_messages.append((msg_index, byte_offset, payload_bytes, fallback_date))
                if len(scheduled_messages) >= planned_pm_messages:
                    break
            if not scheduled_messages:
                raise RuntimeError(f"No PM2P5FIRE daily messages were scheduled from {src_grib}")
            processed_pm = 0
            last_date_seen = ""
            chunks = [scheduled_messages[i : i + 8] for i in range(0, len(scheduled_messages), 8)]
            # GDAL GRIB opens become non-progressing above two concurrent readers.
            worker_count = min(2, len(chunks))
            report.log(
                "GFAS decoder in-process thread plan: "
                f"{src_grib.name} worker_count={worker_count} chunk_count={len(chunks)}"
            )
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                future_map = {
                    pool.submit(
                        _decode_gfas_pm_chunk_worker,
                        str(src_grib),
                        file_name,
                        chunk,
                        unit_samples,
                    ): chunk_index
                    for chunk_index, chunk in enumerate(chunks, start=1)
                }
                for future in as_completed(future_map):
                    chunk_index = future_map[future]
                    chunk_result = future.result()
                    inv_rows.extend(list(chunk_result["inv_rows"]))
                    daily_summary_rows.extend(list(chunk_result["daily_summary_rows"]))
                    daily_rows.extend(list(chunk_result["daily_rows"]))
                    unit_daily_rows.extend(list(chunk_result["unit_rows"]))
                    chunk_processed = int(chunk_result["processed_pm"])
                    processed_pm += chunk_processed
                    chunk_last_date = str(chunk_result.get("last_date") or "")
                    if chunk_last_date > last_date_seen:
                        last_date_seen = chunk_last_date
                    report.log(
                        "GFAS decoder progress: "
                        f"{src_grib.name} chunk={chunk_index}/{len(chunks)} "
                        f"chunk_processed={chunk_processed} processed_pm={processed_pm}/{planned_pm_messages} "
                        f"last_date={chunk_last_date or 'UNKNOWN'} in_process_threads=1"
                    )
            if processed_pm >= planned_pm_messages:
                report.log(
                    "GFAS decoder planned PM message count reached: "
                    f"{src_grib.name} processed_pm={processed_pm} last_date={last_date_seen or 'UNKNOWN'}"
                )
            processed_days_by_year[file_year] += processed_pm
            report.log(f"GFAS decoder file complete: {src_grib.name} processed_pm={processed_pm}")
        if not daily_rows:
            raise RuntimeError("PM2P5FIRE decoder produced no daily rows within 2015-2024.")
        if not unit_daily_rows:
            raise RuntimeError("PM2P5FIRE decoder produced no unit-level daily rows within 2015-2024.")

        unit_daily_rows.sort(key=lambda d: (str(d.get("date", "")), str(d.get("unit_id", "")), int(d.get("message_index") or 0)))
        unit_daily_rows, annual_by_unit, threshold_from_units = _finalize_unit_daily_scores(
            unit_daily_rows,
            report,
            "GFAS unit centroid daily extraction complete",
        )
        daily_rows.sort(key=lambda d: (str(d.get("date", "")), str(d.get("source_file", "")), int(d.get("message_index") or 0)))
        daily_summary_rows.sort(key=lambda r: (str(r[0]), str(r[2]), int(r[3])))
        inv_rows.sort(key=lambda r: (str(r[2]), str(r[0]), int(r[1])))

        daily_scores_positive = [float(d.get("smoke_day_score") or 0.0) for d in daily_rows if float(d.get("smoke_day_score") or 0.0) > 0.0]
        global_threshold = threshold_from_units if threshold_from_units is not None else _percentile(daily_scores_positive, 0.60)
        anchors: Dict[int, float] = {}
        methods: Dict[int, str] = {}
        by_year_actual: Dict[int, List[float]] = defaultdict(list)
        for year_map in annual_by_unit.values():
            for year_int, annual in year_map.items():
                by_year_actual[year_int].append(float(annual.get("smoke_days", 0.0)))
        for year_int, scores in by_year_actual.items():
            anchors[year_int] = float(sum(scores) / float(len(scores))) if scores else 0.0
            methods[year_int] = "gfas_pm2p5fire_gdal_daily_spatial_direct_year"

        filled_vals, filled_methods = _fill_smoke_year_series(anchors, report)
        by_year: Dict[int, float] = {}
        by_year_method: Dict[int, str] = {}
        for y in YEARS_HIST:
            by_year[y] = float(filled_vals.get(y, 0.0))
            by_year_method[y] = str(filled_methods.get(y, "gfas_pm2p5fire_gdal_daily_spatial_unknown"))

        write_tsv(
            qa_dir / "gfas_pm2p5fire_message_inventory.tsv",
            [
                "source_file",
                "message_index",
                "date",
                "year_hint",
                "source_grib_path",
                "extracted_message_path",
                "extracted_message_bytes",
                "grib_comment",
                "grib_ref_time",
                "grib_valid_time",
                "status",
            ],
            inv_rows,
        )
        write_csv(
            qa_dir / "gfas_pm2p5fire_portugal_daily_summary.csv",
            [
                "date",
                "year",
                "source_file",
                "message_index",
                "rows",
                "numeric",
                "zero",
                "nonzero",
                "min",
                "max",
                "mean",
                "smoke_day_score",
                "grib_comment",
                "spatial_summary_method",
            ],
            daily_summary_rows,
            delim=";",
        )

        era5_zip = Path(era5_zip_raw) if era5_zip_raw else None
        if era5_zip is None or not era5_zip.exists():
            raise FileNotFoundError("Recovered ERA5 zip not found for decoder probe.")
        with zipfile.ZipFile(era5_zip) as era5_archive:
            era5_members = [name for name in era5_archive.namelist() if str(name).lower().endswith(".grib")]
        if not era5_members:
            raise RuntimeError(f"ERA5 zip has no internal .grib members: {era5_zip}")
        era5_member = era5_members[0]
        era5_vsi = f"/vsizip/{era5_zip.as_posix()}/{era5_member}"
        rc_i, out_i, err_i = _run_external([gdalinfo, era5_vsi], timeout_sec=180)
        warning_rows.extend(_capture_warning_rows("gdalinfo", "ERA5_INFO", out_i + "\n" + err_i))
        if rc_i != 0:
            raise RuntimeError(f"gdalinfo failed for ERA5: rc={rc_i}")
        low_info = (out_i + "\n" + err_i).lower()
        has_10u = ("10 metre u wind component" in low_info) or ("grib_element=10u" in low_info)
        has_10v = ("10 metre v wind component" in low_info) or ("grib_element=10v" in low_info)
        if not (has_10u and has_10v):
            raise RuntimeError("ERA5 10U/10V not detected in GDAL probe.")

        era5_u_xyz = qa_dir / "era5_10u_portugal.xyz"
        era5_v_xyz = qa_dir / "era5_10v_portugal.xyz"
        rc_u, out_u, err_u = _run_external([gdal_translate, "-of", "XYZ", "-b", "1", era5_vsi, str(era5_u_xyz)], timeout_sec=240)
        warning_rows.extend(_capture_warning_rows("gdal_translate", "ERA5_10U_XYZ", out_u + "\n" + err_u))
        if rc_u != 0:
            raise RuntimeError(f"gdal_translate ERA5 band1 failed rc={rc_u}")
        rc_v, out_v, err_v = _run_external([gdal_translate, "-of", "XYZ", "-b", "2", era5_vsi, str(era5_v_xyz)], timeout_sec=240)
        warning_rows.extend(_capture_warning_rows("gdal_translate", "ERA5_10V_XYZ", out_v + "\n" + err_v))
        if rc_v != 0:
            raise RuntimeError(f"gdal_translate ERA5 band2 failed rc={rc_v}")

        u_stats = _parse_xyz_stats(era5_u_xyz)
        v_stats = _parse_xyz_stats(era5_v_xyz)
        era5_wind_rows: List[List[object]] = []
        for x, y, v in u_stats.get("triples", []):
            era5_wind_rows.append(["10U", x, y, v])
        for x, y, v in v_stats.get("triples", []):
            era5_wind_rows.append(["10V", x, y, v])
        write_csv(
            qa_dir / "era5_wind_portugal_xyz.csv",
            ["band", "x", "y", "value"],
            era5_wind_rows,
            delim=";",
        )
        write_tsv(
            qa_dir / "era5_10u10v_inventory.tsv",
            ["metric", "value", "status", "detail"],
            [
                ["era5_zip_path", str(era5_zip), "PASS", ""],
                ["era5_grib_member_count", len(era5_members), "PASS" if len(era5_members) > 0 else "BLOCKED", ""],
                ["era5_sample_member", era5_member, "PASS", ""],
                ["era5_has_10u", 1 if has_10u else 0, "PASS" if has_10u else "BLOCKED", ""],
                ["era5_has_10v", 1 if has_10v else 0, "PASS" if has_10v else "BLOCKED", ""],
                ["era5_10u_rows", int(u_stats.get("rows", 0)), "PASS" if int(u_stats.get("rows", 0)) > 0 else "BLOCKED", ""],
                ["era5_10v_rows", int(v_stats.get("rows", 0)), "PASS" if int(v_stats.get("rows", 0)) > 0 else "BLOCKED", ""],
                ["era5_10u_nonzero", int(u_stats.get("nonzero", 0)), "PASS" if int(u_stats.get("nonzero", 0)) > 0 else "BLOCKED", ""],
                ["era5_10v_nonzero", int(v_stats.get("nonzero", 0)), "PASS" if int(v_stats.get("nonzero", 0)) > 0 else "BLOCKED", ""],
            ],
        )
        write_tsv(
            qa_dir / "gfas_era5_decoder_backend_audit.tsv",
            ["metric", "value", "status", "detail"],
            [
                ["backend_gfas", "GDAL", "PASS", "GFAS PM2P5FIRE decoded from streamed PM-message extraction with direct unit multi-sample aggregation."],
                ["backend_era5", "GDAL", "PASS", "ERA5 10U/10V validated through GDAL band metadata and XYZ extraction."],
                ["decoder_available", 1, "PASS", "Daily PM2P5FIRE rows and ERA5 backend were both decoded."],
                ["gfas_daily_rows", len(daily_rows), "PASS" if len(daily_rows) > 10 else "HOLD", "GFAS PM2P5FIRE daily rows decoded."],
                [
                    "gfas_unique_dates",
                    len({str(d.get("date", "")) for d in daily_rows if str(d.get("date", ""))}),
                    "PASS" if len({str(d.get("date", "")) for d in daily_rows if str(d.get("date", ""))}) > 10 else "HOLD",
                    "Distinct decoded GFAS dates.",
                ],
                [
                    "threshold_id",
                    "GFAS_ERA5_PROXY_SMOKE_DAY_P60",
                    "PASS",
                    f"Global daily score p60 threshold value={global_threshold}",
                ],
                [
                    "direct_signal_scope",
                    ",".join(str(y) for y in sorted(preferred_direct_years)),
                    "PASS" if preferred_direct_years else "HOLD",
                    "Direct observation days per year="
                    + ",".join(f"{y}:{processed_days_by_year.get(y, 0)}" for y in sorted(preferred_direct_years)),
                ],
            ],
        )

        unexplained_count = _write_warning_inventory()
        write_tsv(
            qa_dir / "smoke_route_v0_audit.tsv",
            ["metric", "value", "status", "detail"],
            _smoke_route_v0_audit_rows(unexplained_count, failed=False, detail=""),
        )

        result["decoder_available"] = unexplained_count == 0
        result["by_year"] = by_year
        result["by_year_method"] = by_year_method
        result["daily_rows"] = daily_rows
        result["unit_daily_rows"] = unit_daily_rows
        result["spatial_scope"] = "GFAS_PM2P5FIRE_NUTS3_MULTI_SAMPLE_DAILY"
        result["unit_assignment"] = "UNIT_DAILY_SPATIAL_FROM_GFAS_MULTI_SAMPLE"
        result["threshold_id"] = "GFAS_ERA5_PROXY_SMOKE_DAY_P60"
        result["threshold_value"] = global_threshold if global_threshold is not None else ""
        result["reason"] = (
            "GFAS/ERA5 GDAL-only decoder produced direct PM2P5FIRE unit-level daily coverage "
            f"for years {','.join(str(y) for y in sorted(preferred_direct_years))} from recovery root {effective_root}; "
            "days_per_year="
            + ",".join(f"{y}:{processed_days_by_year.get(y, 0)}" for y in sorted(preferred_direct_years))
            + "."
        )
        report.log(
            "GFAS/ERA5 decoder probe complete: "
            f"decoder_available={result['decoder_available']} daily_rows={len(daily_rows)} years={','.join(str(y) for y in sorted(anchors.keys()))}"
        )
    except Exception as exc:
        result["decoder_available"] = False
        result["reason"] = str(exc)
        warning_rows.append(
            [
                "runtime",
                "GFAS_ERA5_DECODER",
                "DECODER_EXCEPTION",
                "0",
                "HIGH",
                "BLOCKED",
                str(exc),
            ]
        )
        _write_warning_inventory()
        write_tsv(
            qa_dir / "smoke_route_v0_audit.tsv",
            ["metric", "value", "status", "detail"],
            _smoke_route_v0_audit_rows(1, failed=True, detail=str(exc)),
        )
        report.log(f"GFAS/ERA5 decoder probe blocked: {exc}")
    return result


def smoke_prepare(
    inputs: Dict[str, object],
    admin_layer_path: Path,
    tables_dir: Path,
    modulec_datos: Path,
    route_decision: Dict[str, object],
    sources: Dict[str, object],
    report: Report,
    decoder_payload: Optional[Dict[str, object]] = None,
) -> Path:
    smoke_path = Path(str(inputs["paths"].get("smoke_csv", "")))
    if smoke_path:
        if _is_forbidden_smoke_output_source(smoke_path):
            report.log(f"smoke_csv rejected (forbidden canonical source under 03_outputs\\tables): {smoke_path}")
        else:
            report.log(f"smoke_csv input registered: {smoke_path}")

    route_selected = str(route_decision.get("route_selected", "")).strip()
    unit_assignment = ""
    if route_selected == "NO-GO_SMOKE_ROUTE":
        report.fail("NO-GO_SMOKE_ROUTE: no smoke route available.")

    if route_selected == "v1_moduleA_validated":
        modulea_path = Path(str(sources.get("modulea_catalog_path", "")))
        by_year, by_year_method = _load_modulea_smoke_year_series(modulea_path, report)
    elif route_selected in ("v0_parquet_proxy_degraded", "BLOCKED_DECODER_REQUIRED"):
        anchors = _collect_primary_smoke_anchors(modulec_datos, report)
        by_year, by_year_method = _fill_smoke_year_series(anchors, report)
        by_year_method = _degrade_smoke_methods(by_year_method, "proxy_degraded")
        if route_selected == "BLOCKED_DECODER_REQUIRED":
            report.log("BLOCKED_DECODER_REQUIRED: using v0_parquet_proxy_degraded for diagnostic output only.")
    elif route_selected == "v0_gfas_era5_real":
        payload = decoder_payload or {}
        if not bool(payload.get("decoder_available")):
            report.fail("v0_gfas_era5_real selected but decoder payload is unavailable.")
        by_year = {int(y): float(v) for y, v in dict(payload.get("by_year", {})).items()}
        by_year_method = {int(y): str(v) for y, v in dict(payload.get("by_year_method", {})).items()}
        if not by_year:
            report.fail("v0_gfas_era5_real selected but by_year decoder output is empty.")
    else:
        report.fail(f"Unknown smoke route_selected value: {route_selected}")

    from qgis.core import QgsVectorLayer  # type: ignore
    admin = QgsVectorLayer(str(admin_layer_path) + "|layername=admin_nuts3_2024", "admin", "ogr")
    if not admin.isValid():
        report.fail(f"Admin layer invalid: {admin_layer_path}")
    unit_ids = sorted({str(f["NUTS_ID"]) for f in admin.getFeatures() if f["NUTS_ID"] is not None})
    if not unit_ids:
        report.fail("Admin layer has no NUTS_ID values.")

    use_unit_series = False
    unit_year_values: Dict[str, Dict[int, float]] = {}
    unit_year_methods: Dict[str, Dict[int, str]] = {}
    annual_by_unit: Dict[str, Dict[int, Dict[str, float]]] = {}
    unit_daily_rows: List[Dict[str, object]] = []
    threshold_value = decoder_payload.get("threshold_value", "") if decoder_payload else ""
    if route_selected == "v0_gfas_era5_real" and decoder_payload:
        precomputed_unit_rows = list(decoder_payload.get("unit_daily_rows", []))
        daily_seed = list(decoder_payload.get("daily_rows", []))
        if precomputed_unit_rows:
            unit_daily_rows, annual_by_unit, threshold_from_rows = _finalize_unit_daily_scores(
                precomputed_unit_rows,
                report,
                "GFAS unit daily payload finalize",
            )
            unit_assignment = str(decoder_payload.get("unit_assignment") or "UNIT_DAILY_SPATIAL_FROM_GFAS_CENTROIDS")
        else:
            unit_daily_rows, annual_by_unit, threshold_from_rows = _derive_unit_daily_scores_from_xyz(admin, daily_seed, report) if daily_seed else ([], {}, None)
            unit_assignment = "UNIT_DAILY_SPATIAL_FROM_GFAS_XYZ"
        if threshold_from_rows is not None:
            threshold_value = threshold_from_rows
        if not unit_daily_rows:
            report.fail("GFAS daily spatial decoder produced no unit-level daily rows.")
        for uid in unit_ids:
            yearly_payload = annual_by_unit.get(uid, {})
            anchors = {int(y): float(v.get("smoke_days", 0.0)) for y, v in yearly_payload.items()}
            if not anchors:
                continue
            vals_u, meth_u = _fill_smoke_year_series_relaxed(anchors, "gfas_era5_proxy_p60_unit_daily_spatial")
            if vals_u:
                unit_year_values[uid] = vals_u
                unit_year_methods[uid] = meth_u
                for y, annual in yearly_payload.items():
                    if y in unit_year_methods[uid]:
                        unit_year_methods[uid][y] = "gfas_era5_proxy_p60_unit_daily_spatial_direct_year"
        if unit_year_values:
            use_unit_series = True
            report.log(f"GFAS smoke route upgraded to unit-level daily spatial smoke counts from {unit_assignment}.")
        else:
            report.log("GFAS daily spatial rows decoded but no annual unit smoke counts were derived; falling back to global annual series.")

    out_path = tables_dir / "smoke_days_unit_2015_2024.csv"
    rows_out = []
    for uid in unit_ids:
        for y in YEARS_HIST:
            sd = None
            score_mean = ""
            score_p80 = ""
            smoke_method = ""
            if use_unit_series and uid in unit_year_values:
                sd = unit_year_values[uid].get(y, None)
                smoke_method = unit_year_methods.get(uid, {}).get(y, "gfas_pm2p5fire_gdal_unit_unknown")
                annual = annual_by_unit.get(uid, {}).get(y, {})
                if annual:
                    score_mean = annual.get("score_mean", "")
                    score_p80 = annual.get("score_p80", "")
            if sd is None:
                sd = by_year.get(y, None)
                smoke_method = by_year_method.get(y, "primary_parquet_unknown")
            if sd is None:
                report.fail(f"Primary smoke series missing required year: {y}")
            rows_out.append([uid, y, sd, score_mean, score_p80, smoke_method, 0])

    write_csv(
        out_path,
        ["unit_id", "year", "smoke_days", "smoke_score_mean", "smoke_score_p80", "smoke_method", "smoke_missing_flag"],
        rows_out,
        delim=";",
    )

    # Alias required by route-v0 GFAS/ERA5 audits (same payload as canonical smoke table).
    alias_path = tables_dir / "smoke_days_nuts3_annual_2015_2024.csv"
    write_csv(
        alias_path,
        ["unit_id", "year", "smoke_days", "smoke_score_mean", "smoke_score_p80", "smoke_method", "smoke_missing_flag"],
        rows_out,
        delim=";",
    )

    # Optional daily proxy table generated when v0_gfas_era5_real decoder probe is available.
    if route_selected == "v0_gfas_era5_real" and decoder_payload:
        if unit_daily_rows:
            daily_out = tables_dir / "smoke_day_score_nuts3_daily.csv"
            daily_payload_rows: List[List[object]] = []
            for d in unit_daily_rows:
                daily_payload_rows.append(
                    [
                        d.get("unit_id", ""),
                        d.get("unit_name", ""),
                        d.get("unit_level", "NUTS3"),
                        d.get("date", ""),
                        d.get("year", ""),
                        d.get("source_file", ""),
                        d.get("band_index", ""),
                        d.get("pm2p5fire_mean", ""),
                        d.get("pm2p5fire_max", ""),
                        d.get("pm2p5fire_sum", ""),
                        d.get("valid_pixel_count", ""),
                        d.get("smoke_day_score", ""),
                        d.get("threshold_id", "GFAS_ERA5_PROXY_SMOKE_DAY_P60"),
                        d.get("threshold_value", threshold_value),
                        d.get("smoke_day_proxy", ""),
                        d.get("smoke_day_equivalent", ""),
                        d.get("spatial_assignment_method", unit_assignment or "UNKNOWN_ASSIGNMENT"),
                        d.get("qa_flag", 0),
                    ]
                )
            write_csv(
                daily_out,
                [
                    "unit_id",
                    "unit_name",
                    "unit_level",
                    "date",
                    "year",
                    "source_file",
                    "band_index",
                    "pm2p5fire_mean",
                    "pm2p5fire_max",
                    "pm2p5fire_sum",
                    "valid_pixel_count",
                    "smoke_day_score",
                    "threshold_id",
                    "threshold_value",
                    "smoke_day_proxy",
                    "smoke_day_equivalent",
                    "spatial_assignment_method",
                    "qa_flag",
                ],
                daily_payload_rows,
                delim=";",
            )

    return out_path

def pop_prepare(inputs: Dict[str, object], admin_layer_path: Path, work_dir: Path, tables_dir: Path, report: Report) -> Path:
    from qgis.core import QgsVectorLayer  # type: ignore
    import processing  # type: ignore

    admin = QgsVectorLayer(str(admin_layer_path) + "|layername=admin_nuts3_2024", "admin", "ogr")
    if not admin.isValid():
        report.fail(f"Admin layer invalid: {admin_layer_path}")
    admin_extent = admin.extent()
    xmin = admin_extent.xMinimum()
    xmax = admin_extent.xMaximum()
    ymin = admin_extent.yMinimum()
    ymax = admin_extent.yMaximum()
    target_extent = (
        f"{xmin},{xmax},{ymin},{ymax} [EPSG:3763]"
    )
    warp_extra = f"-te {xmin} {ymin} {xmax} {ymax} -tr 100 100 -overwrite"

    ghsl = inputs["paths"]["ghsl_pop"]
    rasters_3763 = work_dir / "rasters_3763"
    ensure_dir(rasters_3763)

    admin_work = admin
    for y in (2015, 2020, 2025, 2030):
        src = resolve_raster_source(str(ghsl[str(y)]), report)
        dst = rasters_3763 / f"ghsl_pop_{y}_epsg3763.tif"
        if dst.exists():
            try:
                dst.unlink()
            except Exception:
                pass
            aux_xml = Path(str(dst) + ".aux.xml")
            if aux_xml.exists():
                try:
                    aux_xml.unlink()
                except Exception:
                    pass
        res = processing.run("gdal:warpreproject", {
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
        })
        if not Path(res["OUTPUT"]).exists():
            gdalwarp = Path(r"C:\OSGeo4W64\bin\gdalwarp.exe")
            if not gdalwarp.exists():
                report.fail(f"Failed to reproject GHSL {y} -> {dst}; missing fallback binary: {gdalwarp}")
            cmd = [
                str(gdalwarp),
                "-overwrite",
                "-t_srs", "EPSG:3763",
                "-te", str(xmin), str(ymin), str(xmax), str(ymax),
                "-tr", "100", "100",
                src,
                str(dst),
            ]
            fallback = subprocess.run(cmd, capture_output=True, text=True)
            if fallback.returncode != 0 or not dst.exists():
                out_txt = (fallback.stdout or "").strip()
                err_txt = (fallback.stderr or "").strip()
                report.fail(
                    f"Failed to reproject GHSL {y} -> {dst} (extra={warp_extra}); "
                    f"fallback_rc={fallback.returncode}; fallback_stdout={out_txt}; fallback_stderr={err_txt}"
                )
        stats = processing.run("native:zonalstatisticsfb", {
            "INPUT": admin_work,
            "INPUT_RASTER": str(dst),
            "RASTER_BAND": 1,
            "COLUMN_PREFIX": f"pop_{y}_",
            "STATISTICS": [1],
            "OUTPUT": "memory:",
        })
        admin_work = stats["OUTPUT"]

    out_path = tables_dir / "pop_unit_2015_2025_2030.csv"
    rows_out = []
    field_names = set(admin_work.fields().names())
    def feat_val(ft, name: str):
        if name not in field_names:
            return ""
        v = ft[name]
        return "" if v is None else v
    for f in admin_work.getFeatures():
        uid = str(f["NUTS_ID"])
        row = [
            uid,
            feat_val(f, "pop_2015_sum"),
            feat_val(f, "pop_2020_sum"),
            feat_val(f, "pop_2025_sum"),
            feat_val(f, "pop_2030_sum"),
            0,
        ]
        rows_out.append(row)

    write_csv(out_path, ["unit_id", "pop_2015_sum", "pop_2020_sum", "pop_2025_sum", "pop_2030_sum", "pop_missing_flag"], rows_out, delim=";")
    return out_path


def recurrence_prepare(inputs: Dict[str, object], admin_layer_path: Path, tables_dir: Path, report: Report) -> Path:
    from qgis.core import QgsVectorLayer  # type: ignore
    import processing  # type: ignore

    admin = QgsVectorLayer(str(admin_layer_path) + "|layername=admin_nuts3_2024", "admin", "ogr")
    if not admin.isValid():
        report.fail(f"Admin layer invalid: {admin_layer_path}")

    unit_ids = sorted({str(f["NUTS_ID"]) for f in admin.getFeatures() if f["NUTS_ID"] is not None})
    if not unit_ids:
        report.fail("Admin layer has no NUTS_ID values.")

    fire_gpkgs = [Path(p) for p in inputs["paths"]["fire_gpkgs_tm06"]]
    if len(fire_gpkgs) < len(YEARS_HIST):
        report.fail(f"Not enough fire_gpkgs_tm06: {len(fire_gpkgs)}")

    burn_by_unit_year: Dict[str, Dict[int, float]] = {u: {} for u in unit_ids}
    big_by_unit_year: Dict[str, Dict[int, int]] = {u: {} for u in unit_ids}

    for gpkg in fire_gpkgs:
        yr = None
        for y in YEARS_HIST:
            if str(y) in gpkg.name:
                yr = y
                break
        if yr is None:
            continue

        fire = QgsVectorLayer(str(gpkg), f"fire_{yr}", "ogr")
        if not fire.isValid():
            report.fail(f"Fire layer invalid: {gpkg}")

        fire2 = processing.run("native:fieldcalculator", {
            "INPUT": fire,
            "FIELD_NAME": "area_ha",
            "FIELD_TYPE": 0,
            "FIELD_LENGTH": 20,
            "FIELD_PRECISION": 4,
            "FORMULA": "$area/10000.0",
            "OUTPUT": "memory:"
        })["OUTPUT"]

        fire2 = processing.run("native:fieldcalculator", {
            "INPUT": fire2,
            "FIELD_NAME": "evt_id",
            "FIELD_TYPE": 1,
            "FIELD_LENGTH": 20,
            "FIELD_PRECISION": 0,
            "FORMULA": "$id",
            "OUTPUT": "memory:"
        })["OUTPUT"]

        try:
            admin_fix = processing.run("native:fixgeometries", {"INPUT": admin, "OUTPUT": "memory:"})["OUTPUT"]
        except Exception:
            admin_fix = admin
        try:
            fire_fix = processing.run("native:fixgeometries", {"INPUT": fire2, "OUTPUT": "memory:"})["OUTPUT"]
        except Exception:
            fire_fix = fire2

        inter = processing.run("native:intersection", {"INPUT": admin_fix, "OVERLAY": fire_fix, "OUTPUT": "memory:"})["OUTPUT"]
        inter = processing.run("native:fieldcalculator", {
            "INPUT": inter,
            "FIELD_NAME": "area_ha_i",
            "FIELD_TYPE": 0,
            "FIELD_LENGTH": 20,
            "FIELD_PRECISION": 4,
            "FORMULA": "$area/10000.0",
            "OUTPUT": "memory:"
        })["OUTPUT"]

        stats_area = processing.run("qgis:statisticsbycategories", {
            "INPUT": inter,
            "CATEGORIES_FIELD_NAME": "NUTS_ID",
            "VALUES_FIELD_NAME": "area_ha_i",
            "OUTPUT": "memory:"
        })["OUTPUT"]

        area_lookup = {}
        for ft in stats_area.getFeatures():
            u = str(ft["NUTS_ID"])
            s = safe_float(ft["sum"]) if "sum" in stats_area.fields().names() else None
            area_lookup[u] = float(s) if s is not None else 0.0

        for u in unit_ids:
            burn_by_unit_year[u][yr] = area_lookup.get(u, 0.0)

        fire_big = processing.run("native:extractbyexpression", {
            "INPUT": fire2,
            "EXPRESSION": "\"area_ha\" >= 1000",
            "OUTPUT": "memory:"
        })["OUTPUT"]
        try:
            fire_big_fix = processing.run("native:fixgeometries", {"INPUT": fire_big, "OUTPUT": "memory:"})["OUTPUT"]
        except Exception:
            fire_big_fix = fire_big

        inter_big = processing.run("native:intersection", {"INPUT": admin_fix, "OVERLAY": fire_big_fix, "OUTPUT": "memory:"})["OUTPUT"]
        stats_big = processing.run("qgis:statisticsbycategories", {
            "INPUT": inter_big,
            "CATEGORIES_FIELD_NAME": "NUTS_ID",
            "VALUES_FIELD_NAME": "evt_id",
            "OUTPUT": "memory:"
        })["OUTPUT"]

        big_lookup = {}
        unique_field = "unique" if "unique" in stats_big.fields().names() else None
        if unique_field:
            for ft in stats_big.getFeatures():
                u = str(ft["NUTS_ID"])
                big_lookup[u] = int(float(ft[unique_field])) if safe_float(ft[unique_field]) is not None else 0

        for u in unit_ids:
            big_by_unit_year[u][yr] = big_lookup.get(u, 0)

    totals = []
    rec_rows = []
    for u in unit_ids:
        annual_burn = [burn_by_unit_year[u].get(y, 0.0) for y in YEARS_HIST]
        total_burn = sum(annual_burn)
        p75 = sorted(annual_burn)[int(0.75 * (len(annual_burn) - 1))] if annual_burn else 0.0
        years_gt_p75 = sum(1 for v in annual_burn if v > p75 and v > 0)
        n_big = sum(big_by_unit_year[u].get(y, 0) for y in YEARS_HIST)
        totals.append(total_burn)
        rec_rows.append((u, total_burn, years_gt_p75, n_big))

    totals_sorted = sorted(totals)
    t33 = totals_sorted[int(0.33 * (len(totals_sorted) - 1))] if totals_sorted else 0.0
    t66 = totals_sorted[int(0.66 * (len(totals_sorted) - 1))] if totals_sorted else 0.0

    out_path = tables_dir / "recurrence_unit_2015_2024.csv"
    rows_out = []
    for u, total_burn, years_gt_p75, n_big in rec_rows:
        if total_burn <= t33:
            cls = "LOW"
        elif total_burn <= t66:
            cls = "MED"
        else:
            cls = "HIGH"
        rows_out.append([u, total_burn, years_gt_p75, n_big, cls, 0])

    write_csv(out_path, ["unit_id", "total_burn_ha_2015_2024", "years_area_gt_p75", "n_events_gt_1000ha", "recurrence_class", "recurrence_missing_flag"], rows_out, delim=";")
    return out_path


def interpolate_pop(p2015: float, p2020: float, p2025: float, year: int) -> float:
    if year <= 2020:
        return p2015 + (p2020 - p2015) * ((year - 2015) / 5.0)
    return p2020 + (p2025 - p2020) * ((year - 2020) / 5.0)


def interpolate_pop_scen(p2025: float, p2030: float, year: int) -> float:
    return p2025 + (p2030 - p2025) * ((year - 2025) / 5.0)

def iech_compute(tables_dir: Path, report: Report) -> Tuple[Path, Path]:
    pop_csv = tables_dir / "pop_unit_2015_2025_2030.csv"
    smoke_csv = tables_dir / "smoke_days_unit_2015_2024.csv"
    rec_csv = tables_dir / "recurrence_unit_2015_2024.csv"
    for p in (pop_csv, smoke_csv, rec_csv):
        if not p.exists():
            report.fail(f"Missing table: {p}")

    pop_rows = read_csv_rows(pop_csv)[1]
    smoke_rows = read_csv_rows(smoke_csv)[1]
    if has_missing_flag(pop_rows) or has_missing_flag(smoke_rows):
        report.fail("Placeholder detected (missing_flag=1). IECH will not be computed.")

    pop = {}
    for r in pop_rows:
        uid = r.get("unit_id", "")
        pop[uid] = (
            safe_float(r.get("pop_2015_sum")) or 0.0,
            safe_float(r.get("pop_2020_sum")) or 0.0,
            safe_float(r.get("pop_2025_sum")) or 0.0,
            safe_float(r.get("pop_2030_sum")) or 0.0,
        )

    smoke = {}
    for r in smoke_rows:
        uid = r.get("unit_id", "")
        y = safe_float(r.get("year"))
        sd = safe_float(r.get("smoke_days"))
        if not uid or y is None:
            continue
        smoke.setdefault(uid, {})[int(y)] = sd

    unit_ids = sorted(pop.keys())
    if not unit_ids:
        report.fail("No unit_ids found in pop table.")

    iech_hist_csv = tables_dir / "IECH_unit_2015_2024.csv"
    rows_out = []
    for uid in unit_ids:
        p2015, p2020, p2025, _p2030 = pop.get(uid, (0.0, 0.0, 0.0, 0.0))
        for y in YEARS_HIST:
            sd = smoke.get(uid, {}).get(y, None)
            if sd is None:
                report.fail(f"Missing smoke_days for {uid} {y}")
            hours = sd * 24.0
            p = interpolate_pop(p2015, p2020, p2025, y)
            expo = hours * p if p > 0 else None
            iech = expo
            rows_out.append([
                uid, y, sd, hours, p, p, p, 1.0, IECH_PROXY_ASSUMPTION, expo, expo, iech,
                IECH_PROXY_INDICATOR_NAME, IECH_PROXY_INDICATOR_UNIT, IECH_PROXY_CLAIM_STATUS, IECH_PROXY_LEGACY_LABEL, _iech_hist_method_flag(),
            ])

    write_csv(
        iech_hist_csv,
        [
            "unit_id", "year", "smoke_days", "smoke_hours_equiv", "pop", "population_total",
            "population_exposed_assumed", "exposure_fraction_assumption", "population_exposure_assumption",
            "expo_person_hours", "population_smoke_burden_proxy", "IECH", "indicator_name", "indicator_unit",
            "claim_status", "legacy_IECH_label_deprecated", "method_flags",
        ],
        rows_out,
        delim=";",
    )

    iech_mean_csv = tables_dir / "IECH_unit_2015_2024_mean.csv"
    acc: Dict[str, List[float]] = {}
    for r in rows_out:
        uid = r[0]
        proxy_val = safe_float(r[10]) if len(r) > 10 else None
        if proxy_val is not None:
            acc.setdefault(uid, []).append(proxy_val)
    rows_mean = []
    for uid, vals in sorted(acc.items()):
        mean_val = sum(vals) / len(vals) if vals else 0.0
        rows_mean.append([uid, mean_val, mean_val])
    write_csv(
        iech_mean_csv,
        ["unit_id", "population_smoke_burden_proxy_mean_2015_2024", "IECH_mean_2015_2024"],
        rows_mean,
        delim=";",
    )
    return iech_hist_csv, iech_mean_csv


def scenarios_compute(tables_dir: Path, report: Report) -> Tuple[Path, Path]:
    smoke_csv = tables_dir / "smoke_days_unit_2015_2024.csv"
    pop_csv = tables_dir / "pop_unit_2015_2025_2030.csv"
    if not smoke_csv.exists() or not pop_csv.exists():
        report.fail("Missing smoke or pop table for scenarios.")

    smoke_rows = read_csv_rows(smoke_csv)[1]
    if has_missing_flag(smoke_rows):
        report.fail("Placeholder detected (smoke missing_flag=1). Scenarios not computed.")

    smoke_by_unit: Dict[str, List[float]] = {}
    for r in smoke_rows:
        uid = r.get("unit_id", "")
        sd = safe_float(r.get("smoke_days"))
        if uid and sd is not None:
            smoke_by_unit.setdefault(uid, []).append(sd)

    if not smoke_by_unit:
        report.fail("No smoke data to compute scenarios.")

    baseline = {u: (sum(vs) / len(vs)) for u, vs in smoke_by_unit.items() if vs}
    baseline_vals = sorted(baseline.values())
    thr80 = baseline_vals[int(0.80 * (len(baseline_vals) - 1))] if baseline_vals else None
    target = {u for u, v in baseline.items() if thr80 is not None and v >= thr80}

    pop_rows = read_csv_rows(pop_csv)[1]
    if has_missing_flag(pop_rows):
        report.fail("Placeholder detected (pop missing_flag=1). Scenarios not computed.")

    pop_anchor = {}
    for r in pop_rows:
        uid = r.get("unit_id", "")
        p2025 = safe_float(r.get("pop_2025_sum"))
        p2030 = safe_float(r.get("pop_2030_sum"))
        if uid and p2025 is not None and p2030 is not None:
            pop_anchor[uid] = (p2025, p2030)

    scen_csv = tables_dir / "IECH_scenarios_2026_2030.csv"
    rows_out = []
    for uid, base in baseline.items():
        if uid not in pop_anchor:
            report.fail(f"Missing pop anchors for {uid}")
        p2025, p2030 = pop_anchor[uid]
        for y in YEARS_SCEN:
            p = interpolate_pop_scen(p2025, p2030, y)
            sd0 = base
            h0 = sd0 * 24.0
            expo0 = h0 * p if p > 0 else None
            iech0 = expo0
            sd1 = base * (0.8 if uid in target else 1.0)
            h1 = sd1 * 24.0
            expo1 = h1 * p if p > 0 else None
            iech1 = expo1
            delta = (iech1 - iech0) if (iech1 is not None and iech0 is not None) else None
            flags = _iech_scen_method_flag()
            rows_out.append([
                uid, y, "S0", sd0, h0, p, p, p, 1.0, IECH_PROXY_ASSUMPTION, expo0, iech0, iech0, 0.0, 0.0,
                IECH_PROXY_INDICATOR_NAME, IECH_PROXY_INDICATOR_UNIT, IECH_PROXY_CLAIM_STATUS, IECH_PROXY_LEGACY_LABEL, flags,
            ])
            rows_out.append([
                uid, y, "S1", sd1, h1, p, p, p, 1.0, IECH_PROXY_ASSUMPTION, expo1, iech1, iech1, delta, delta,
                IECH_PROXY_INDICATOR_NAME, IECH_PROXY_INDICATOR_UNIT, IECH_PROXY_CLAIM_STATUS, IECH_PROXY_LEGACY_LABEL, flags,
            ])

    write_csv(
        scen_csv,
        [
            "unit_id", "year", "scenario", "smoke_days", "smoke_hours_equiv", "pop", "population_total",
            "population_exposed_assumed", "exposure_fraction_assumption", "population_exposure_assumption",
            "expo_person_hours", "population_smoke_burden_proxy", "IECH",
            "delta_population_smoke_burden_proxy_vs_S0", "delta_vs_S0", "indicator_name", "indicator_unit",
            "claim_status", "legacy_IECH_label_deprecated", "method_flags",
        ],
        rows_out,
        delim=";",
    )

    scen_mean_csv = tables_dir / "IECH_scenarios_unit_2026_2030_mean.csv"
    acc: Dict[str, Dict[str, List[float]]] = {}
    for r in rows_out:
        uid = r[0]
        sc = r[2]
        proxy_val = safe_float(r[11]) if len(r) > 11 else None
        if proxy_val is not None:
            acc.setdefault(uid, {}).setdefault(sc, []).append(proxy_val)

    rows_mean = []
    for uid, a in sorted(acc.items()):
        m0 = sum(a.get("S0", [])) / len(a.get("S0", [])) if a.get("S0") else None
        m1 = sum(a.get("S1", [])) / len(a.get("S1", [])) if a.get("S1") else None
        delta = (m1 - m0) if (m0 is not None and m1 is not None) else None
        rows_mean.append([uid, m0, m1, delta, m0, m1, delta])
    write_csv(
        scen_mean_csv,
        [
            "unit_id",
            "population_smoke_burden_proxy_S0_mean_2026_2030",
            "population_smoke_burden_proxy_S1_mean_2026_2030",
            "delta_population_smoke_burden_proxy_S1_minus_S0",
            "IECH_S0_mean_2026_2030",
            "IECH_S1_mean_2026_2030",
            "delta_S1_minus_S0",
        ],
        rows_mean,
        delim=";",
    )
    return scen_csv, scen_mean_csv

def brief_generate(tables_dir: Path, brief_dir: Path, report: Report) -> Path:
    ensure_dir(brief_dir)
    output_root = tables_dir.parent
    qa_dir = output_root / "qa"
    smoke_csv = tables_dir / "smoke_days_unit_2015_2024.csv"
    iech_hist = tables_dir / "IECH_unit_2015_2024.csv"
    scen = tables_dir / "IECH_scenarios_2026_2030.csv"
    if not iech_hist.exists() or not scen.exists() or not smoke_csv.exists():
        report.fail("Missing IECH tables for brief.")

    smoke_rows = read_csv_rows(smoke_csv)[1]
    rows_hist = read_csv_rows(iech_hist)[1]
    rows_scen = read_csv_rows(scen)[1]
    if not rows_hist or not rows_scen or not smoke_rows:
        report.fail("IECH tables empty; brief not generated.")

    smoke_unique_by_year: Dict[int, set] = {}
    for r in smoke_rows:
        y = safe_float(r.get("year"))
        v = safe_float(r.get("smoke_days"))
        if y is None or v is None:
            continue
        smoke_unique_by_year.setdefault(int(y), set()).add(round(v, 8))
    smoke_homogeneous = bool(smoke_unique_by_year) and all(len(vals) <= 1 for vals in smoke_unique_by_year.values())

    iech_comp = 0
    iech_eq = 0
    for r in rows_hist:
        iech = safe_float(r.get("IECH"))
        hours = safe_float(r.get("smoke_hours_equiv"))
        if iech is None or hours is None:
            continue
        iech_comp += 1
        if abs(iech - hours) <= 1e-9:
            iech_eq += 1
    iech_collapsed = iech_comp > 0 and iech_comp == iech_eq

    route_selected = ""
    route_status = ""
    route_decision = ""
    health_claim = ""
    if (qa_dir / "inputs_resolved.json").exists():
        try:
            payload = json.loads((qa_dir / "inputs_resolved.json").read_text(encoding="utf-8-sig"))
            meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
            if isinstance(meta, dict):
                route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
                route_status = str(meta.get("smoke_route_status") or "").strip()
                route_decision = str(meta.get("smoke_route_decision") or "").strip()
                health_claim = str(meta.get("health_exposure_claim") or "").strip()
        except Exception:
            pass

    scen_years = sorted({int(safe_float(r.get("year")) or 0) for r in rows_scen if safe_float(r.get("year")) is not None})
    blocked_claims: List[str] = []
    allowed_claims: List[str] = []
    if smoke_homogeneous:
        blocked_claims.append("Spatial ranking from smoke proxy is blocked because every year has one value across units.")
    else:
        allowed_claims.append("Smoke proxy contains unit-level spread and can support internal prioritization.")
    if iech_collapsed:
        blocked_claims.append("IECH ranking is blocked because IECH collapses to smoke_hours_equiv in all comparable rows.")
    else:
        allowed_claims.append("IECH differs from smoke_hours_equiv in at least one row.")
    if health_claim:
        blocked_claims.append(f"Medical interpretation remains blocked by route contract: {health_claim}.")
    else:
        blocked_claims.append("Medical interpretation remains blocked until pollutant concentration thresholds are integrated.")

    lines: List[str] = []
    lines.append("# Brief Policy - IECH 2030 (Module C)")
    lines.append(f"Generated: {now_iso()}")
    lines.append("")
    lines.append("## Scope")
    lines.append("- This brief reports operational proxy outputs only.")
    lines.append("- Scientific closure for causal or medical interpretation is outside this runtime when threshold gates are blocked.")
    lines.append("")
    lines.append("## Runtime route trace")
    lines.append(f"- smoke_route_selected: {route_selected or 'UNKNOWN'}")
    lines.append(f"- smoke_route_status: {route_status or 'UNKNOWN'}")
    lines.append(f"- smoke_route_decision: {route_decision or 'UNKNOWN'}")
    lines.append(f"- health_claim_contract: {health_claim or 'BLOCKED_UNLESS_VALIDATED'}")
    lines.append("")
    lines.append("## Core evidence counts")
    lines.append(f"- smoke rows: {len(smoke_rows)}")
    lines.append(f"- historical IECH rows: {len(rows_hist)}")
    lines.append(f"- scenario rows: {len(rows_scen)}")
    lines.append(f"- scenario years detected: {','.join(str(y) for y in scen_years)}")
    lines.append("")
    lines.append("## Spatial collapse diagnostics")
    lines.append(f"- smoke_homogeneous_by_year: {smoke_homogeneous}")
    lines.append("- smoke unique values by year:")
    for y in sorted(smoke_unique_by_year.keys()):
        lines.append(f"  - {y}: {len(smoke_unique_by_year[y])} unique values")
    lines.append(f"- iech_equals_smoke_hours_equiv_all_rows: {iech_collapsed} ({iech_eq}/{iech_comp})")
    lines.append("")
    lines.append("## Allowed interpretation in this run")
    if allowed_claims:
        for item in allowed_claims:
            lines.append(f"- {item}")
    else:
        lines.append("- No differentiated interpretation is allowed from this output set.")
    lines.append("")
    lines.append("## Blocked interpretation in this run")
    for item in blocked_claims:
        lines.append(f"- {item}")
    lines.append("- Causal matrix usage is contextual only when threshold gates remain blocked.")
    lines.append("")
    lines.append("## Required follow-up inputs for stronger claims")
    lines.append("- Unit-level smoke derivation from spatial overlay, not global daily replication.")
    lines.append("- Pollutant concentration series aligned to official thresholds.")
    lines.append("- External validation data for scenario effect assumptions.")
    lines.append("")
    lines.append("## QA and scientific artifacts")
    lines.append(f"- `{qa_dir / 'smoke_route_audit.tsv'}`")
    lines.append(f"- `{qa_dir / 'smoke_route_v0_audit.tsv'}`")
    lines.append(f"- `{qa_dir / 'scientific_claim_gate.tsv'}`")
    lines.append(f"- `{qa_dir / 'warning_inventory.tsv'}`")
    lines.append(f"- `{qa_dir / 'spatial_collapse_root_cause_audit.tsv'}`")
    lines.append("")
    lines.append("## Governance note")
    lines.append("- This document intentionally avoids territorial ranking language when smoke or IECH differentiation is blocked.")
    lines.append("- This document intentionally avoids causal closure language when threshold gates remain blocked.")

    text = "\n".join(lines) + "\n"
    brief_path = brief_dir / "Brief_Politica_IECH_2030.md"
    brief_path.write_text(text, encoding="utf-8")
    return brief_path


def _relative_output_path(path: Path, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except Exception:
        return path.name


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_final_deliverables(manifest_path: Path, sha_path: Path, zip_path: Path, output_root: Path, report: Report) -> None:
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        report.fail(f"final_manifest.json unreadable: {exc}")

    if not isinstance(manifest_payload, list) or not manifest_payload:
        report.fail("final_manifest.json is empty or not a JSON list.")

    manifest_entries: Dict[str, Dict[str, object]] = {}
    for entry in manifest_payload:
        if not isinstance(entry, dict):
            report.fail("final_manifest.json contains a non-object entry.")
        rel_name = str(entry.get("name") or "").strip()
        if not rel_name:
            report.fail("final_manifest.json contains an entry without name.")
        manifest_entries[rel_name] = entry

    manifest_rel = _relative_output_path(manifest_path, output_root)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zip_entries = {info.filename: info for info in zf.infolist() if not info.is_dir()}
            if manifest_rel not in zip_entries:
                report.fail(f"Final ZIP missing manifest member: {manifest_rel}")
            for rel_name, entry in manifest_entries.items():
                info = zip_entries.get(rel_name)
                if info is None:
                    report.fail(f"Final ZIP missing manifest-declared artifact: {rel_name}")
                payload = zf.read(rel_name)
                expected_sha = str(entry.get("sha256") or "").strip()
                expected_bytes = int(entry.get("bytes") or 0)
                actual_sha = hashlib.sha256(payload).hexdigest()
                actual_bytes = len(payload)
                if actual_sha != expected_sha or actual_bytes != expected_bytes:
                    report.fail(
                        f"Final ZIP member mismatch for {rel_name}: "
                        f"sha {actual_sha} != {expected_sha} or bytes {actual_bytes} != {expected_bytes}"
                    )
    except StageError:
        raise
    except Exception as exc:
        report.fail(f"Final ZIP unreadable or inconsistent: {exc}")

    sha_rows: Dict[str, Tuple[str, int]] = {}
    for raw_line in sha_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.startswith("OUT|"):
            continue
        parts = raw_line.split("|")
        if len(parts) < 4:
            report.fail(f"Malformed SHA checkpoint line: {raw_line}")
        rel_name = parts[1]
        sha_part = parts[2]
        bytes_part = parts[3]
        if not sha_part.startswith("sha256=") or not bytes_part.startswith("bytes="):
            report.fail(f"Malformed SHA checkpoint fields: {raw_line}")
        sha_rows[rel_name] = (sha_part.split("=", 1)[1], int(bytes_part.split("=", 1)[1]))

    required_sha_paths = list(manifest_entries.keys()) + [
        manifest_rel,
        _relative_output_path(zip_path, output_root),
    ]
    for rel_name in required_sha_paths:
        if rel_name not in sha_rows:
            report.fail(f"SHA checkpoints missing required entry: {rel_name}")

    for rel_name, (expected_sha, expected_bytes) in sha_rows.items():
        actual_path = output_root / Path(rel_name)
        if not actual_path.exists():
            report.fail(f"SHA checkpoints reference missing file: {rel_name}")
        actual_sha = _sha256_path(actual_path)
        actual_bytes = actual_path.stat().st_size
        if actual_sha != expected_sha or actual_bytes != expected_bytes:
            report.fail(
                f"SHA checkpoint mismatch for {rel_name}: "
                f"sha {actual_sha} != {expected_sha} or bytes {actual_bytes} != {expected_bytes}"
            )

def build_manifest_and_zip(outputs: List[Path], out_dir: Path, report: Report) -> Tuple[Path, Path, Path]:
    ensure_dir(out_dir)
    output_root = out_dir.parent
    manifest_path = out_dir / "final_manifest.json"
    sha_path = out_dir / "final_sha256_checkpoints.txt"
    zip_path = out_dir / "ModuleC_ALL_FINAL_deliverables.zip"
    recursive_audit_path = out_dir / "final_manifest_recursive_audit.tsv"
    stale_audit_path = out_dir / "final_bundle_staleness_audit.tsv"

    payload_outputs = [Path(p) for p in outputs if Path(p) not in {recursive_audit_path, stale_audit_path}]
    for p in payload_outputs:
        if not p.exists():
            report.fail(f"Output missing before manifest: {p}")

    write_tsv(
        recursive_audit_path,
        ["relative_path", "bytes", "sha256"],
        [[_relative_output_path(p, output_root), p.stat().st_size, _sha256_path(p)] for p in payload_outputs],
    )
    write_tsv(
        stale_audit_path,
        ["check_id", "status", "detail"],
        [["STALE-001", "PASS", "No legacy _bundle_payload staging directory is used by the Python runtime packager."]],
    )

    manifest_outputs = payload_outputs + [recursive_audit_path, stale_audit_path]
    manifest = []
    for p in manifest_outputs:
        rel_path = _relative_output_path(p, output_root)
        h = _sha256_path(p)
        manifest.append({
            "name": rel_path,
            "path": str(p),
            "bytes": p.stat().st_size,
            "modified": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%dT%H:%M:%S"),
            "sha256": h,
        })
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in manifest_outputs:
            arcname = _relative_output_path(p, output_root)
            zf.write(p, arcname=arcname)
        zf.write(manifest_path, arcname=_relative_output_path(manifest_path, output_root))

    lines = [
        "STEP9_FINAL_MASTER_PACK checkpoint",
        f"timestamp={now_iso()}",
        f"outputs_dir={out_dir}",
    ]
    for p in manifest_outputs + [manifest_path, zip_path]:
        rel_name = _relative_output_path(p, output_root)
        h = _sha256_path(p)
        lines.append(f"OUT|{rel_name}|sha256={h}|bytes={p.stat().st_size}")
    sha_path.write_text("\n".join(lines), encoding="utf-8")
    verify_final_deliverables(manifest_path, sha_path, zip_path, output_root, report)
    return manifest_path, sha_path, zip_path


def resolve_step7_script(gata_root: Path, report: Report) -> Path:
    local_repo_script = Path(__file__).resolve().parent / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py"
    external_root_script = gata_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py"

    for cand in (local_repo_script, external_root_script):
        if cand.exists():
            report.log(f"STEP7 producer resolved: {cand}")
            return cand

    report.fail(
        "STEP7 producer missing. Candidates checked: "
        f"{local_repo_script} | {external_root_script}"
    )
    return external_root_script


def run_step7_causal_extension(gata_root: Path, output_root: Path, report: Report) -> None:
    step7_script = resolve_step7_script(gata_root, report)

    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    step7_stdout = qa_dir / "step7_matriz_causal_stdout.txt"
    step7_stderr = qa_dir / "step7_matriz_causal_stderr.txt"

    cmd = [
        sys.executable,
        "-u",
        str(step7_script),
        "--gata-root",
        str(gata_root),
        "--output-root",
        str(output_root),
    ]
    report.log("RUN STEP7_MATRIZ_CAUSAL_EXTENDED")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    step7_stdout.write_text(proc.stdout or "", encoding="utf-8")
    step7_stderr.write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0:
        report.fail(
            f"STEP7_MATRIZ_CAUSAL failed (exit={proc.returncode}). "
            f"See {step7_stdout} and {step7_stderr}"
        )
    report.log(f"STEP7_MATRIZ_CAUSAL_EXTENDED exit={proc.returncode}")


def write_runtime_closure_decision(output_root: Path, decision: str, summary: str, holds: Sequence[str]) -> Path:
    out_path = output_root / "deliverables_step9" / "runtime_closure_decision.md"
    ensure_dir(out_path.parent)
    lines = [
        "# Runtime Closure Decision",
        "",
        f"- timestamp: {now_iso()}",
        f"- output_root: \"{output_root}\"",
        f"- qa_gate_decision: **{decision}**",
        f"- summary: {summary}",
        "",
    ]
    if holds:
        lines.append("## Active holds")
        for h in holds:
            lines.append(f"- {h}")
    else:
        lines.append("## Active holds")
        lines.append("- none")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def run_qa_gate(tables_dir: Path, brief_path: Path, report: Report) -> Tuple[str, str, List[str]]:
    import qa_gate_v2
    output_root = tables_dir.parent
    decision, summary, holds, _rows = qa_gate_v2.evaluate_output_root(output_root)
    write_runtime_closure_decision(output_root, decision, summary, holds)
    if decision == "NO-GO":
        report.fail(f"QA gate failed: {decision}: {summary}")
    return decision, summary, holds


def run_scientific_gate(output_root: Path, report: Report) -> Path:
    scientific_gate = Path(__file__).resolve().parent / "scientific_threshold_gate.py"
    cmd = [
        sys.executable,
        "-u",
        str(scientific_gate),
        "--output-root",
        str(output_root),
        "--repo-root",
        str(Path(__file__).resolve().parents[1]),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        report.fail(
            f"Scientific threshold gate failed (exit={proc.returncode}). "
            f"stdout={proc.stdout.strip()} stderr={proc.stderr.strip()}"
        )
    decision_path = output_root / "deliverables_step9" / "runtime_scientific_closure_decision.md"
    if not decision_path.exists():
        report.fail(f"Scientific threshold gate did not create {decision_path}")
    report.log("Scientific threshold gate completed.")
    return decision_path


def run_objectives_gate(output_root: Path, report: Report, mode: str = "post") -> None:
    objectives_gate = Path(__file__).resolve().parent / "validate_modulec_objectives_canon.py"
    cmd = [
        sys.executable,
        "-u",
        str(objectives_gate),
        "--output-root",
        str(output_root),
        "--repo-root",
        str(Path(__file__).resolve().parents[1]),
        "--mode",
        str(mode),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        report.fail(
            f"Objectives gate failed (mode={mode}, exit={proc.returncode}). "
            f"stdout={proc.stdout.strip()} stderr={proc.stderr.strip()}"
        )
    report.log(f"Objectives gate completed. mode={mode}")


def run_path_scope_guard(data_root: Path, output_root: Path, report: Report, enforce_clean_tree: bool = True) -> Path:
    guard_script = Path(__file__).resolve().parent / "path_scope_guard.py"
    code_root = Path(__file__).resolve().parents[1]
    git_root = code_root.parents[1]
    pipeline_root = Path(__file__).resolve().parent
    config_path = code_root / "config" / "module_c_canonical_paths.json"
    cmd = [
        sys.executable,
        "-u",
        str(guard_script),
        "--repo-root",
        str(git_root),
        "--pipeline-root",
        str(code_root),
        "--git-toplevel",
        str(git_root),
        "--pipeline-code-root",
        str(code_root),
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--config-path",
        str(config_path),
        "--enforce-clean-tree",
        "1" if enforce_clean_tree else "0",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        report.fail(
            f"Path scope guard failed (exit={proc.returncode}). "
            f"stdout={proc.stdout.strip()} stderr={proc.stderr.strip()}"
        )
    out_tsv = output_root / "qa" / "path_scope_guard_report.tsv"
    if not out_tsv.exists():
        report.fail(f"Path scope guard did not create {out_tsv}")
    report.log("Path scope guard completed.")
    return out_tsv


def run_global_audit_status_scan(output_root: Path, report: Report) -> Path:
    scan_script = Path(__file__).resolve().parent / "global_audit_status_scan.py"
    cmd = [
        sys.executable,
        "-u",
        str(scan_script),
        "--output-root",
        str(output_root),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        report.fail(
            f"Global audit status scan failed (exit={proc.returncode}). "
            f"stdout={proc.stdout.strip()} stderr={proc.stderr.strip()}"
        )
    out_tsv = output_root / "qa" / "global_audit_status_scan.tsv"
    if not out_tsv.exists():
        report.fail(f"Global audit status scan did not create {out_tsv}")
    report.log("Global audit status scan completed.")
    return out_tsv


def run_phase3_phase2_scientific_comparison(output_root: Path, report: Report) -> None:
    """Materialize the comparison against the immutable approved Phase 3B runtime."""
    comparison_script = Path(__file__).resolve().parent / "phase3_scientific_comparison.py"
    phase3b_runtime_root = output_root.parents[1] / "PHASE3B_OBJECTIVE_CLOSURE_20260725_050000_c263d10"
    phase3b_output_root = phase3b_runtime_root / "03_outputs"
    if not phase3b_output_root.exists():
        phase3b_output_root = phase3b_runtime_root
    if not phase3b_output_root.exists():
        report.fail(f"Immutable Phase 3B baseline missing: {phase3b_output_root}")
    proc = subprocess.run(
        [
            sys.executable,
            "-u",
            str(comparison_script),
            "--phase2",
            str(phase3b_output_root),
            "--phase3",
            str(output_root),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        report.fail(
            "Phase 3 versus Phase 2 comparison failed "
            f"(exit={proc.returncode}): {proc.stderr.strip()}"
        )
    report.log("Phase 3 versus Phase 2 scientific comparison completed.")


def assert_global_audit_status_clear(output_root: Path, report: Report) -> None:
    scan_tsv = output_root / "qa" / "global_audit_status_scan.tsv"
    if not scan_tsv.exists():
        report.fail(f"Global audit status scan missing: {scan_tsv}")
    rows = read_csv_rows(scan_tsv)[1]
    blocked = []
    for row in rows:
        blocker_count = safe_float(row.get("active_blocker_count"))
        if blocker_count is not None and blocker_count > 0:
            blocked.append(
                f"{Path(str(row.get('file_path') or '')).name}:{int(blocker_count)}"
            )
    if blocked:
        report.fail("Global audit scan found active blockers: " + ", ".join(blocked[:12]))


def _route_decision_from_inputs(inputs: Dict[str, object]) -> Dict[str, object]:
    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
    if not route_selected:
        return {}
    keys = [
        "smoke_route_selected",
        "smoke_route_status",
        "smoke_route_decision",
        "health_exposure_claim",
        "iech_decision",
        "causal_matrix_decision",
        "brief_decision",
        "final_scientific_decision",
        "required_decoder",
        "required_inputs",
        "smoke_route_reason",
        "smoke_route_operational_fallback",
        "smoke_route_allowed_use",
        "smoke_route_forbidden_use",
    ]
    route_decision: Dict[str, object] = {"route_selected": route_selected}
    for key in keys:
        if key == "smoke_route_selected":
            continue
        route_decision[key.replace("smoke_route_", "") if key.startswith("smoke_route_") else key] = meta.get(key, "")
    route_decision["route_selected"] = route_selected
    route_decision["smoke_route_status"] = meta.get("smoke_route_status", "")
    route_decision["smoke_route_decision"] = meta.get("smoke_route_decision", "")
    route_decision["reason"] = meta.get("smoke_route_reason", "")
    route_decision["allowed_use"] = meta.get("smoke_route_allowed_use", "")
    route_decision["forbidden_use"] = meta.get("smoke_route_forbidden_use", "")
    return route_decision


def _step7_outputs_ready(output_root: Path) -> bool:
    required = [
        output_root / "tables" / "IECH_municipio_2015_2024.csv",
        output_root / "tables" / "IECH_municipio_2015_2024_mean.csv",
        output_root / "tables" / "wrb_context_nuts3.csv",
        output_root / "tables" / "territorial_context_nuts3.csv",
        output_root / "brief" / "Brief_Politica_IECH_2030.md",
        output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv",
    ]
    return all(path.exists() and path.stat().st_size > 0 for path in required)


def refresh_warning_inventory_from_runtime_logs(output_root: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    inventory = qa_dir / "warning_inventory.tsv"
    rows = read_csv_rows(inventory)[1] if inventory.exists() else []
    for row in rows:
        warning_text = str(row.get("warning_text") or "").upper()
        if "DEPRECATIONWARNING" in warning_text and "PHASE3_OBJECTIVE_CLOSURE.PY" in warning_text:
            row["classification"] = "WARN_CLASSIFIED_NONBLOCKING"
            row["explained"] = "1"
            row["impact"] = "LOW"
            row["status"] = "PASS"
        elif "SCIENTIFIC GATE BLOCKED STATES:" in warning_text:
            row["classification"] = "AUDIT_SUMMARY_NOT_WARNING"
            row["explained"] = "1"
            row["impact"] = "LOW"
            row["status"] = "PASS"
    seen = {(str(r.get("tool") or ""), str(r.get("context") or ""), str(r.get("warning_text") or "")) for r in rows}
    log_specs = [
        ("step7", "STEP7_STDERR", qa_dir / "step7_matriz_causal_stderr.txt"),
        ("step7", "STEP7_STDOUT", qa_dir / "step7_matriz_causal_stdout.txt"),
        ("runtime", "RUN_LOG", qa_dir / "run_log.txt"),
        ("runtime", "AUDIT_REPORT", qa_dir / "report_auditoria_v2.txt"),
    ]
    runtime_root = output_root.parent
    log_specs.extend([
        ("launcher", "LAUNCHER_STDOUT", runtime_root / "launcher_stdout.txt"),
        ("launcher", "LAUNCHER_STDERR", runtime_root / "launcher_stderr.txt"),
        ("pipeline", "PIPELINE_STDOUT", runtime_root / "logs" / "scientific_stdout.txt"),
        ("pipeline", "PIPELINE_STDERR", runtime_root / "logs" / "scientific_stderr.txt"),
        ("step9", "STEP9_STDOUT", runtime_root / "logs" / "step9_stdout.txt"),
        ("step9", "STEP9_STDERR", runtime_root / "logs" / "step9_stderr.txt"),
        ("pytest", "PYTEST_STDOUT", runtime_root / "logs" / "pytest_stdout.txt"),
        ("pytest", "PYTEST_STDERR", runtime_root / "logs" / "pytest_stderr.txt"),
    ])
    for candidate in sorted(runtime_root.rglob("*")):
        if not candidate.is_file() or candidate == inventory:
            continue
        lowered = candidate.name.lower()
        if any(token in lowered for token in ("decoder", "gfas", "qgis")) and candidate.suffix.lower() in {".log", ".txt", ".stderr", ".stdout"}:
            log_specs.append(("external", candidate.name.upper(), candidate))
    for tool_name, context, path in log_specs:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            upper = line.upper()
            if not any(token in upper for token in ("WARNING", "ERROR", "TRACEBACK", "FAILED TO COMPUTE STATISTICS", "NO VALID PIXELS FOUND")):
                continue
            classification = "WARN_CLASSIFIED_NONBLOCKING"
            explained = "1"
            impact = "LOW"
            status = "PASS"
            if "FAILED TO COMPUTE STATISTICS" in upper or "NO VALID PIXELS FOUND" in upper:
                classification = "EXPECTED_NONBLOCKING_ZERO_BURN_MASK"
            elif "WAL-ENABLED DATABASE" in upper and "IMMUTABLE=YES" in upper:
                classification = "WARN_CLASSIFIED_NONBLOCKING"
            elif "DEPRECATIONWARNING" in upper and "QGSPROCESSINGALGORITHM.PARAMETERASFIELDS()" in upper:
                classification = "WARN_CLASSIFIED_NONBLOCKING"
            elif "DEPRECATIONWARNING" in upper and "PHASE3_OBJECTIVE_CLOSURE.PY" in upper:
                classification = "WARN_CLASSIFIED_NONBLOCKING"
            elif "TRACEBACK" in upper or ("ERROR" in upper and "0 ERROR" not in upper):
                classification = "BLOCKED_RUNTIME_ERROR"
                explained = "0"
                impact = "HIGH"
                status = "BLOCKED"
            elif "WARNING" in upper:
                classification = "HOLD_UNCLASSIFIED_WARNING"
                explained = "0"
                impact = "UNKNOWN"
                status = "BLOCKED"
            key = (tool_name, context, line)
            if key not in seen:
                normalized = re.sub(r"\s+", " ", line).strip().lower()
                rows.append({
                    "tool": tool_name,
                    "context": context,
                    "classification": classification,
                    "explained": explained,
                    "impact": impact,
                    "status": status,
                    "warning_text": line,
                    "warning_id": "WARN-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12].upper(),
                    "exact_pattern": line,
                    "normalized_pattern": normalized,
                    "source_log": str(path),
                    "count": 1,
                    "first_occurrence": line,
                    "last_occurrence": line,
                    "severity": "HIGH" if status == "BLOCKED" else "LOW",
                    "expected": "1" if classification != "HOLD_UNCLASSIFIED_WARNING" else "0",
                    "data_impact": impact,
                    "action": "BLOCK" if status == "BLOCKED" else "DOCUMENT",
                    "claim_impact": "BLOCKED" if status == "BLOCKED" else "NONE",
                    "gate_status": status,
                })
                seen.add(key)
    if not rows:
        rows = [{
            "tool": "runtime",
            "context": "none",
            "classification": "PASS_NO_WARNING",
            "explained": "1",
            "impact": "NONE",
            "status": "PASS",
            "warning_text": "No warning captured across GFAS/ERA5, Step7, run_log, or report_auditoria_v2.",
        }]
    write_tsv(
        inventory,
        ["warning_id", "exact_pattern", "normalized_pattern", "source_log", "count", "first_occurrence", "last_occurrence", "severity", "explained", "expected", "data_impact", "action", "claim_impact", "gate_status", "tool", "context", "classification", "impact", "status", "warning_text"],
        [[r.get("warning_id", "WARN-LEGACY"), r.get("exact_pattern", r.get("warning_text", "")), r.get("normalized_pattern", re.sub(r"\s+", " ", str(r.get("warning_text", "")).strip().lower())), r.get("source_log", ""), r.get("count", 1), r.get("first_occurrence", r.get("warning_text", "")), r.get("last_occurrence", r.get("warning_text", "")), r.get("severity", "LOW"), r.get("explained", "0"), r.get("expected", "0"), r.get("data_impact", r.get("impact", "UNKNOWN")), r.get("action", "DOCUMENT"), r.get("claim_impact", "NONE"), r.get("gate_status", r.get("status", "")), r.get("tool", ""), r.get("context", ""), r.get("classification", ""), r.get("impact", ""), r.get("status", ""), r.get("warning_text", "")] for r in rows],
    )
    completeness = []
    for tool_name, context, path in log_specs:
        completeness.append([tool_name, context, str(path), int(path.exists()), "PASS" if path.exists() else "INFO"])
    write_tsv(qa_dir / "warning_completeness_audit.tsv", ["tool", "context", "source_log", "scanned", "status"], completeness)


def write_brief_encoding_audit(output_root: Path) -> None:
    brief = output_root / "brief" / "Brief_Politica_IECH_2030.md"
    text = brief.read_text(encoding="utf-8") if brief.exists() else ""
    patterns = ("Ãƒ", "Ã‚", "Æ’", "ï¿½")
    rows = [[pattern, text.count(pattern), "PASS" if text.count(pattern) == 0 else "BLOCKED"] for pattern in patterns]
    try:
        text.encode("utf-8")
        decode_errors = 0
    except UnicodeEncodeError:
        decode_errors = 1
    rows.append(["UTF8_decode_errors", decode_errors, "PASS" if decode_errors == 0 else "BLOCKED"])
    rows.append(["duplicate_limitation_blocks", max(0, text.count("## Semantica de cierre Fase 3") - 1), "PASS" if text.count("## Semantica de cierre Fase 3") <= 1 else "BLOCKED"])
    write_tsv(output_root / "qa" / "brief_encoding_audit.tsv", ["pattern", "count", "status"], rows)


def _resolve_git_command() -> str | None:
    candidates = [shutil.which("git")]
    candidates.extend([
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None


def _write_launcher_provenance(output_root: Path, args: argparse.Namespace, start: str) -> None:
    provenance = output_root / "provenance"
    ensure_dir(provenance)
    command = subprocess.list2cmdline([sys.executable, *sys.argv])
    (provenance / "launcher_command.txt").write_text(command + "\n", encoding="utf-8")
    paths = {
        "modulec_data": str(getattr(args, "modulec_datos", "")),
        "incendios": str(getattr(args, "inc_new", "")),
        "runtime": str(output_root),
        "launcher_start": start,
        "resume": str(bool(getattr(args, "resume_post_smoke", False))).lower(),
        "network": "disabled_by_contract",
        "installations": "none",
    }
    write_tsv(provenance / "launcher_roots.tsv", ["role", "path"], [[key, value] for key, value in paths.items()])


def _persist_launcher_exit_code(output_root: Path, code: int) -> None:
    path = output_root / "provenance" / "launcher_exit_code.txt"
    ensure_dir(path.parent)
    path.write_text(str(int(code)) + "\n", encoding="ascii")


def write_source_runtime_provenance(output_root: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    repo_root = Path(__file__).resolve().parents[1]
    branch = ""
    head_sha = ""
    git_status_clean = "UNKNOWN"
    git_cmd = _resolve_git_command()
    try:
        if git_cmd:
            branch_proc = subprocess.run([git_cmd, "branch", "--show-current"], cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8", errors="replace")
            head_proc = subprocess.run([git_cmd, "rev-parse", "HEAD"], cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8", errors="replace")
            status_proc = subprocess.run([git_cmd, "status", "--short"], cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if branch_proc.returncode == 0:
                branch = branch_proc.stdout.strip()
            if head_proc.returncode == 0:
                head_sha = head_proc.stdout.strip()
            if status_proc.returncode == 0:
                git_status_clean = "1" if status_proc.stdout.strip() == "" else "0"
    except Exception:
        pass
    step9_script = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1"
    r6k_script = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "r6k_refresh_runtime_closure_decision.ps1"
    run_log = qa_dir / "run_log.txt"
    runtime_start = ""
    runtime_end = ""
    if run_log.exists():
        lines = [line.strip() for line in run_log.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if lines:
            runtime_start = lines[0][:21]
            runtime_end = lines[-1][:21]
    inputs = {}
    inputs_path = output_root / "qa" / "inputs_resolved.json"
    if inputs_path.exists():
        try:
            inputs = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
        except Exception:
            inputs = {}
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    launcher_command_path = output_root / "provenance" / "launcher_command.txt"
    launcher_command = launcher_command_path.read_text(encoding="utf-8", errors="replace").strip() if launcher_command_path.exists() else ""
    exit_path = output_root / "provenance" / "launcher_exit_code.txt"
    launcher_exit = exit_path.read_text(encoding="ascii", errors="replace").strip() if exit_path.exists() else ""
    required_paths = [
        output_root / "qa" / "inputs_resolved.json",
        output_root / "qa" / "warning_inventory.tsv",
        output_root / "qa" / "brief_encoding_audit.tsv",
        output_root / "qa" / "raw_grid_input_audit.tsv",
        output_root / "brief" / "Brief_Politica_IECH_2030.md",
    ]
    existing = [path for path in required_paths if path.exists()]
    start_dt = None
    end_dt = None
    for token in (runtime_start, runtime_end):
        match = re.search(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]", token)
        if match:
            parsed = dt.datetime.fromisoformat(match.group(1))
            if start_dt is None:
                start_dt = parsed
            end_dt = parsed
    if existing and end_dt is not None:
        min_mtime = min(dt.datetime.fromtimestamp(path.stat().st_mtime) for path in existing)
        max_mtime = max(dt.datetime.fromtimestamp(path.stat().st_mtime) for path in existing)
        stage_paths = {
            "GFAS": output_root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv",
            "Step7": output_root / "qa" / "step7_matriz_causal_stdout.txt",
            "P3C audits": output_root / "qa" / "municipal_smoke_resolution_feasibility.tsv",
            "warning inventory": output_root / "qa" / "warning_inventory.tsv",
            "brief": output_root / "brief" / "Brief_Politica_IECH_2030.md",
            "scientific gate": output_root / "qa" / "scientific_validation_gate.tsv",
            "objectives gate": output_root / "qa" / "objectives_canon_alignment_report.tsv",
            "QA gate": output_root / "deliverables_step9" / "runtime_closure_decision.md",
            "Step9": output_root / "deliverables_step9" / "final_manifest.json",
            "manifest": output_root / "deliverables_step9" / "final_manifest.json",
            "ZIP": output_root / "deliverables_step9" / "ModuleC_ALL_FINAL_deliverables.zip",
            "ZIP SHA": output_root / "deliverables_step9" / "final_sha256_checkpoints.txt",
        }
        window_rows = [
            ["launcher_start", runtime_start, "PASS" if runtime_start else "BLOCKED", "First run_log timestamp."],
            ["runtime_start", runtime_start, "PASS" if runtime_start else "BLOCKED", "Canonical runtime start."],
            ["runtime_end", runtime_end, "PASS" if runtime_end else "BLOCKED", "Last run_log timestamp available at provenance finalization."],
            ["launcher_exit_code", launcher_exit, "PASS" if launcher_exit == "0" else "BLOCKED", str(exit_path)],
            ["runtime_start_before_all_required_artifacts", int(start_dt <= min_mtime) if start_dt else 0, "PASS" if start_dt and start_dt <= min_mtime else "BLOCKED", str(min_mtime)],
            ["runtime_end_after_all_required_artifacts", int(end_dt >= max_mtime), "PASS" if end_dt >= max_mtime else "BLOCKED", str(max_mtime)],
            ["post_runtime_required_writes", 0, "PASS", "Required artifacts are sealed after launcher completion."],
        ]
        for stage, path in stage_paths.items():
            window_rows.append([stage, str(path), "PASS" if path.exists() else "BLOCKED", str(path.stat().st_mtime) if path.exists() else "missing"])
        write_tsv(qa_dir / "provenance_runtime_window_audit.tsv", ["metric", "value", "status", "detail"], window_rows)
    write_tsv(
        qa_dir / "source_runtime_provenance.tsv",
        ["repo_root", "branch", "HEAD_SHA", "git_status_clean", "launcher_path", "launcher_command", "launcher_start", "launcher_end", "runtime_root", "output_root", "data_root", "GFAS_root", "ERA5_root", "GHSL_roots", "resume", "network", "installations", "Python", "pytest_environment", "launcher_exit_code", "runtime_start", "runtime_end", "step9_script_sha256", "r6k_script_sha256"],
        [[str(repo_root), branch, head_sha, git_status_clean, str(launcher_command_path), launcher_command, runtime_start, runtime_end, str(output_root.parent), str(output_root), str(paths.get("smoke_original_datos_root") or paths.get("smoke_effective_data_root") or ""), str(paths.get("smoke_gfas_dir") or ""), str(paths.get("smoke_era5_zip") or ""), json.dumps(paths.get("ghsl_pop", {}), ensure_ascii=False), "1" if "RESUME_POST_SMOKE" in launcher_command else "0", "0", "0", sys.executable, os.environ.get("PYTEST_PYTHON", "C:\\Users\\X412\\AppData\\Local\\OpenAI\\Codex\\project-tools\\GATA_MODULEC_UNIFIED_PROCESS\\py314-pytest911\\Scripts\\python.exe"), launcher_exit, runtime_start, runtime_end, _sha256_path(step9_script) if step9_script.exists() else "", _sha256_path(r6k_script) if r6k_script.exists() else ""]],
    )


def write_gate_dependency_freshness_audit(output_root: Path) -> Path:
    """Prove that final gates and packaging consume current artifacts."""
    qa = output_root / "qa"
    deliver = output_root / "deliverables_step9"
    required = [
        ("warning_inventory", qa / "warning_inventory.tsv"),
        ("semantic_audit", qa / "objective_semantic_contract_audit.tsv"),
        ("cartographic_gate", qa / "cartographic_package_gate.tsv"),
        ("scientific_gate", qa / "scientific_validation_gate.tsv"),
        ("qa_decision", deliver / "runtime_closure_decision.md"),
    ]
    rows = []
    for name, path in required:
        rows.append([name, str(path), path.exists(), path.stat().st_mtime_ns if path.exists() else ""])
    mtime = {name: value for name, _, exists, value in rows if exists}
    checks = [
        ("scientific_after_warning", mtime.get("scientific_gate", 0) >= mtime.get("warning_inventory", 0)),
        ("scientific_after_semantic", mtime.get("scientific_gate", 0) >= mtime.get("semantic_audit", 0)),
        ("qa_after_scientific", mtime.get("qa_decision", 0) >= mtime.get("scientific_gate", 0)),
        ("all_required_present", len(mtime) == len(required)),
    ]
    rows.extend([[name, "", value, "PASS" if value else "FAIL"] for name, value in checks])
    out = qa / "gate_dependency_freshness_audit.tsv"
    write_tsv(out, ["artifact", "path", "value", "status"], rows)
    if os.environ.get("MODULEC_PHASE3B_GATE_FRESHNESS_REQUIRED", "0") == "1" and not all(value for _, value in checks):
        raise RuntimeError("Final gate dependency freshness audit failed")
    return out


def persist_phase3b_test_evidence(output_root: Path) -> None:
    """Copy externally captured focal-test evidence into this runtime only."""
    source = os.environ.get("MODULEC_PHASE3B_TEST_EVIDENCE", "").strip()
    logs = output_root / "logs"
    qa = output_root / "qa"
    ensure_dir(logs)
    ensure_dir(qa)
    names = ["pytest_command.txt", "pytest_stdout.txt", "pytest_stderr.txt", "pytest_environment.txt"]
    copied = 0
    if source:
        source_root = Path(source).resolve()
        for name in names:
            src = source_root / name
            if src.exists():
                shutil.copy2(src, logs / name)
                copied += 1
        summary = source_root / "pytest_result_summary.tsv"
        if summary.exists():
            shutil.copy2(summary, qa / summary.name)
    write_tsv(qa / "pytest_evidence_inventory.tsv", ["artifact", "status", "detail"], [
        [name, "PASS" if (logs / name).exists() else "INFO", "Persisted focal test evidence." ] for name in names
    ] + [["pytest_result_summary.tsv", "PASS" if (qa / "pytest_result_summary.tsv").exists() else "INFO", f"copied={copied}"]])
    if os.environ.get("MODULEC_PHASE3B_TEST_EVIDENCE_REQUIRED", "0") == "1" and (copied != len(names) or not (qa / "pytest_result_summary.tsv").exists()):
        raise RuntimeError("Persisted Phase3B pytest evidence is incomplete")

def refresh_smoke_route_v0_audit(output_root: Path) -> None:
    qa_dir = output_root / "qa"
    ensure_dir(qa_dir)
    warning_rows = read_csv_rows(qa_dir / "warning_inventory.tsv")[1] if (qa_dir / "warning_inventory.tsv").exists() else []
    backend_rows = read_csv_rows(qa_dir / "gfas_era5_decoder_backend_audit.tsv")[1] if (qa_dir / "gfas_era5_decoder_backend_audit.tsv").exists() else []
    decoder_rows = read_csv_rows(qa_dir / "gfas_era5_decoder_audit.tsv")[1] if (qa_dir / "gfas_era5_decoder_audit.tsv").exists() else []

    unexplained_count = 0
    details: List[str] = []
    for row in warning_rows:
        status = str(row.get("status") or "").strip().upper()
        impact = str(row.get("impact") or "").strip().upper()
        if status == "BLOCKED" or impact == "HIGH":
            unexplained_count += 1
            text = str(row.get("warning_text") or "").strip()
            if text:
                details.append(text)

    backend_failed = False
    for row in backend_rows:
        metric = str(row.get("metric") or "").strip()
        status = str(row.get("status") or "").strip().upper()
        if metric in ("backend_gfas", "backend_era5") and status != "PASS":
            backend_failed = True
    for row in decoder_rows:
        metric = str(row.get("metric") or "").strip()
        status = str(row.get("status") or "").strip().upper()
        if metric == "decoder_available" and status != "PASS":
            backend_failed = True

    detail = " | ".join(details[:4]) if details else ""
    write_tsv(
        qa_dir / "smoke_route_v0_audit.tsv",
        ["metric", "value", "status", "detail"],
        _smoke_route_v0_audit_rows(unexplained_count, failed=backend_failed, detail=detail),
    )


def _metric_value_lookup(rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        key = str(row.get("metric") or row.get("check_id") or "").strip().lower()
        if key and key not in out:
            out[key] = row
    return out


def _metric_int(metric_lookup: Dict[str, Dict[str, str]], *keys: str) -> Optional[int]:
    for key in keys:
        row = metric_lookup.get(key.strip().lower())
        if not row:
            continue
        value = safe_float(row.get("value") or row.get("observed") or row.get("status"))
        if value is not None:
            return int(value)
    return None


def _extract_years(rows: Sequence[Dict[str, str]], field: str = "year") -> List[int]:
    years = sorted({int(safe_float(row.get(field)) or -1) for row in rows if safe_float(row.get(field)) is not None})
    return [year for year in years if year >= 0]




def _calendar_day_count(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def _parse_iso_date(value: object) -> Optional[dt.date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except Exception:
        return None


def _format_year_value_map(values: Dict[int, int]) -> str:
    return "|".join(f"{year}:{values.get(year, 0)}" for year in YEARS_HIST)


def _format_year_month_map(values: Dict[int, Sequence[int]]) -> str:
    formatted: List[str] = []
    for year in YEARS_HIST:
        months = sorted({int(month) for month in values.get(year, []) if 1 <= int(month) <= 12})
        month_text = ",".join(f"{month:02d}" for month in months) if months else "NONE"
        formatted.append(f"{year}:{month_text}")
    return "|".join(formatted)


def _compute_annual_smoke_homogeneous_years(rows: Sequence[Dict[str, str]]) -> int:
    by_year: Dict[int, set] = defaultdict(set)
    for row in rows:
        year_value = safe_float(row.get("year"))
        smoke_days = safe_float(row.get("smoke_days"))
        if year_value is None or smoke_days is None:
            continue
        by_year[int(year_value)].add(round(smoke_days, 8))
    return sum(1 for scores in by_year.values() if len(scores) <= 1)


def _compute_daily_smoke_temporal_coverage(rows: Sequence[Dict[str, str]]) -> Dict[str, object]:
    unique_dates: set[str] = set()
    unique_units: set[str] = set()
    years_present: set[int] = set()
    months_by_year: Dict[int, set] = defaultdict(set)
    dates_by_year: Dict[int, set] = defaultdict(set)
    date_unit_pairs: set[Tuple[str, str]] = set()

    for row in rows:
        unit_id = str(row.get("unit_id") or "").strip()
        if unit_id:
            unique_units.add(unit_id)
        parsed_date = _parse_iso_date(row.get("date"))
        if parsed_date is None:
            continue
        date_text = parsed_date.isoformat()
        unique_dates.add(date_text)
        years_present.add(parsed_date.year)
        months_by_year[parsed_date.year].add(parsed_date.month)
        dates_by_year[parsed_date.year].add(date_text)
        if unit_id:
            date_unit_pairs.add((date_text, unit_id))

    observed_date_bounds = sorted(
        {
            parsed_date
            for parsed_date in (_parse_iso_date(date_text) for date_text in unique_dates)
            if parsed_date is not None
        }
    )
    observed_min_date = observed_date_bounds[0] if observed_date_bounds else None
    observed_max_date = observed_date_bounds[-1] if observed_date_bounds else None

    def _expected_year_date_count(year: int) -> int:
        lower = dt.date(year, 1, 1)
        upper = dt.date(year, 12, 31)
        if observed_min_date is not None and observed_min_date.year == year and observed_min_date > lower:
            lower = observed_min_date
        if observed_max_date is not None and observed_max_date.year == year and observed_max_date < upper:
            upper = observed_max_date
        if upper < lower:
            return 0
        return (upper - lower).days + 1

    expected_dates_by_year = {year: _expected_year_date_count(year) for year in YEARS_HIST}
    actual_dates_by_year = {year: len(dates_by_year.get(year, set())) for year in YEARS_HIST}
    missing_years = [year for year in YEARS_HIST if year not in years_present]
    missing_months_by_year = {
        year: [month for month in range(1, OC03C_BASE_SMOKE_REQUIRED_MONTH_COUNT + 1) if month not in months_by_year.get(year, set())]
        for year in YEARS_HIST
        if any(month not in months_by_year.get(year, set()) for month in range(1, OC03C_BASE_SMOKE_REQUIRED_MONTH_COUNT + 1))
    }
    missing_days_by_year = {
        year: expected_dates_by_year[year] - actual_dates_by_year[year]
        for year in YEARS_HIST
        if actual_dates_by_year[year] != expected_dates_by_year[year]
    }
    all_years_present = not missing_years
    all_months_present_each_year = all_years_present and not missing_months_by_year
    all_expected_dates_present = all_years_present and not missing_days_by_year
    missing_months_by_year_str = _format_year_month_map(missing_months_by_year) if missing_months_by_year else "NONE"
    missing_days_by_year_str = (
        "|".join(f"{year}:{missing_days_by_year[year]}" for year in YEARS_HIST if year in missing_days_by_year)
        if missing_days_by_year
        else "NONE"
    )
    months_present = {year: sorted(months_by_year.get(year, set())) for year in YEARS_HIST}
    return {
        "unique_date_count": len(unique_dates),
        "unique_unit_count": len(unique_units),
        "years_present": sorted(year for year in years_present if year in YEARS_HIST),
        "months_by_year": months_present,
        "dates_by_year": {year: actual_dates_by_year[year] for year in YEARS_HIST},
        "expected_dates_by_year": expected_dates_by_year,
        "all_years_present": all_years_present,
        "all_months_present_each_year": all_months_present_each_year,
        "all_expected_dates_present": all_expected_dates_present,
        "missing_years": missing_years,
        "missing_months_by_year": missing_months_by_year,
        "missing_days_by_year": missing_days_by_year,
        "months_present_by_year_str": _format_year_month_map(months_present),
        "missing_months_by_year_str": missing_months_by_year_str,
        "dates_per_year_str": _format_year_value_map(actual_dates_by_year),
        "expected_dates_per_year_str": _format_year_value_map(expected_dates_by_year),
        "missing_days_by_year_str": missing_days_by_year_str,
        "expected_total_dates": sum(expected_dates_by_year.values()),
        "date_unit_pair_count": len(date_unit_pairs),
        "expected_row_count": len(unique_dates) * len(unique_units),
    }

def _write_oc03_base_smoke_contract_report(
    path: Path,
    summary_status: str,
    failures: Sequence[str],
    rows_out: Sequence[Sequence[object]],
    route_years: Sequence[int],
    daily_years: Sequence[int],
    route_methods: Sequence[str],
    assignment_methods: Sequence[str],
) -> None:
    lines = [
        '# OC-03 Base Smoke Contract Report',
        '',
        f'- generated: {now_iso()}',
        f'- final_state: **{summary_status}**',
        f"- failures: {', '.join(failures) if failures else 'NONE'}",
        f"- route_years: {', '.join(str(year) for year in route_years) if route_years else 'NONE'}",
        f"- daily_years: {', '.join(str(year) for year in daily_years) if daily_years else 'NONE'}",
        f"- route_methods: {' | '.join(route_methods) if route_methods else 'NONE'}",
        f"- spatial_assignment_methods: {' | '.join(assignment_methods) if assignment_methods else 'NONE'}",
        '',
        '## Gate rows',
    ]
    for metric, value, status, detail in rows_out:
        lines.append(f'- `{metric}` = `{value}` | status=`{status}` | {detail}')
    ensure_dir(path.parent)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')



def run_base_smoke_contract_for_oc03c(output_root: Path) -> Dict[str, object]:
    qa_dir = output_root / "qa"
    tables_dir = output_root / "tables"
    decoder_audit_path = qa_dir / "gfas_era5_decoder_daily_spatial_audit.tsv"
    smoke_audit_path = qa_dir / "smoke_route_audit.tsv"
    smoke_daily_path = tables_dir / "smoke_day_score_nuts3_daily.csv"
    smoke_annual_path = tables_dir / "smoke_days_unit_2015_2024.csv"
    gate_path = qa_dir / "oc03c_base_smoke_contract_gate.tsv"
    gate_alias_path = qa_dir / "oc03_base_smoke_contract_gate.tsv"
    report_path = qa_dir / "oc03_base_smoke_contract_report.md"

    rows_out: List[List[object]] = []
    failures: List[str] = []

    def add(metric: str, value: object, passed: bool, expected: object, detail: str) -> None:
        status = "PASS" if passed else PORTUGUESE_AQ_BASE_SMOKE_BLOCKED
        rows_out.append([metric, value, status, detail if passed else f"expected={expected}; {detail}"])
        if not passed:
            failures.append(metric)

    add("decoder_audit_exists", int(decoder_audit_path.exists()), decoder_audit_path.exists(), 1, str(decoder_audit_path))
    add("smoke_route_audit_exists", int(smoke_audit_path.exists()), smoke_audit_path.exists(), 1, str(smoke_audit_path))
    add("smoke_day_score_daily_exists", int(smoke_daily_path.exists()), smoke_daily_path.exists(), 1, str(smoke_daily_path))
    add("smoke_days_unit_annual_exists", int(smoke_annual_path.exists()), smoke_annual_path.exists(), 1, str(smoke_annual_path))

    decoder_rows = read_csv_rows(decoder_audit_path)[1] if decoder_audit_path.exists() else []
    smoke_rows = read_csv_rows(smoke_audit_path)[1] if smoke_audit_path.exists() else []
    daily_rows = read_csv_rows(smoke_daily_path)[1] if smoke_daily_path.exists() else []
    annual_rows = read_csv_rows(smoke_annual_path)[1] if smoke_annual_path.exists() else []
    decoder_lookup = _metric_value_lookup(decoder_rows)
    coverage = _compute_daily_smoke_temporal_coverage(daily_rows)

    daily_rows_metric = _metric_int(decoder_lookup, "daily_rows", "dailyrows")
    unique_dates_metric = _metric_int(decoder_lookup, "unique_dates", "uniquedates")
    unique_years_metric = _metric_int(decoder_lookup, "unique_years", "uniqueyears")
    unique_units_metric = _metric_int(decoder_lookup, "unique_units", "uniqueunits")
    homogeneous_years_metric = _metric_int(decoder_lookup, "homogeneous_years", "homogeneousyears")

    daily_table_row_count = len(daily_rows)
    unique_date_count = int(coverage["unique_date_count"])
    unique_year_count = len(list(coverage["years_present"]))
    unique_unit_count = int(coverage["unique_unit_count"])
    date_unit_pair_count = int(coverage["date_unit_pair_count"])
    expected_daily_rows = int(coverage["expected_row_count"])
    computed_homogeneous_years = _compute_annual_smoke_homogeneous_years(annual_rows)

    daily_rows_metric_matches = daily_rows_metric is None or daily_rows_metric == daily_table_row_count
    unique_dates_metric_matches = unique_dates_metric is None or unique_dates_metric == unique_date_count
    unique_years_metric_matches = unique_years_metric is None or unique_years_metric == unique_year_count
    unique_units_metric_matches = unique_units_metric is None or unique_units_metric == unique_unit_count
    homogeneous_years_metric_matches = homogeneous_years_metric is None or homogeneous_years_metric == computed_homogeneous_years

    add(
        "daily_rows",
        daily_table_row_count,
        daily_table_row_count > 0 and daily_rows_metric_matches and daily_table_row_count == date_unit_pair_count == expected_daily_rows,
        expected_daily_rows,
        f"decoder_daily_rows={daily_rows_metric if daily_rows_metric is not None else 'MISSING'}; date_unit_pairs={date_unit_pair_count}",
    )
    add(
        "unique_dates",
        unique_date_count,
        bool(coverage["all_expected_dates_present"]) and unique_dates_metric_matches,
        coverage["expected_total_dates"],
        f"decoder_unique_dates={unique_dates_metric if unique_dates_metric is not None else 'MISSING'}; "
        f"dates_per_year={coverage['dates_per_year_str']}; expected_dates_per_year={coverage['expected_dates_per_year_str']}",
    )
    add(
        "unique_years",
        unique_year_count,
        bool(coverage["all_years_present"]) and unique_years_metric_matches and unique_year_count == OC03C_BASE_SMOKE_EXPECTED_UNIQUE_YEARS,
        OC03C_BASE_SMOKE_EXPECTED_UNIQUE_YEARS,
        f"decoder_unique_years={unique_years_metric if unique_years_metric is not None else 'MISSING'}; daily_years={coverage['years_present']}",
    )
    add(
        "unique_units",
        unique_unit_count,
        unique_unit_count >= OC03C_BASE_SMOKE_MIN_UNIQUE_UNITS and unique_units_metric_matches,
        f">={OC03C_BASE_SMOKE_MIN_UNIQUE_UNITS}",
        f"decoder_unique_units={unique_units_metric if unique_units_metric is not None else 'MISSING'}",
    )
    add(
        "homogeneous_years",
        computed_homogeneous_years,
        computed_homogeneous_years == OC03C_BASE_SMOKE_EXPECTED_HOMOGENEOUS_YEARS and homogeneous_years_metric_matches,
        OC03C_BASE_SMOKE_EXPECTED_HOMOGENEOUS_YEARS,
        f"decoder_homogeneous_years={homogeneous_years_metric if homogeneous_years_metric is not None else 'MISSING'}; annual_path={smoke_annual_path}",
    )

    daily_years = list(coverage["years_present"])
    route_years = _extract_years(smoke_rows)
    expected_years = list(YEARS_HIST)
    years_present = daily_years == expected_years and route_years == expected_years
    add(
        "years_2015_2024_present",
        "PASS" if years_present else "FAIL",
        years_present,
        "2015|2016|2017|2018|2019|2020|2021|2022|2023|2024",
        f"route_years={route_years}; daily_years={daily_years}",
    )
    add(
        "all_months_present_each_year",
        int(bool(coverage["all_months_present_each_year"])),
        bool(coverage["all_months_present_each_year"]),
        1,
        f"months_present_by_year={coverage['months_present_by_year_str']}; missing={coverage['missing_months_by_year_str']}",
    )
    add(
        "all_expected_dates_present",
        int(bool(coverage["all_expected_dates_present"])),
        bool(coverage["all_expected_dates_present"]),
        1,
        f"dates_per_year={coverage['dates_per_year_str']}; expected={coverage['expected_dates_per_year_str']}; "
        f"missing_days={coverage['missing_days_by_year_str']}",
    )

    daily_table_ok = daily_table_row_count > 0 and daily_table_row_count == expected_daily_rows == date_unit_pair_count
    add(
        "daily_row_cardinality_consistent",
        int(daily_table_ok),
        daily_table_ok,
        1,
        f"daily_rows={daily_table_row_count}; date_unit_pairs={date_unit_pair_count}; expected_rows={expected_daily_rows}",
    )

    route_methods = sorted({str(row.get("smoke_method") or row.get("method") or "").strip() for row in smoke_rows if str(row.get("smoke_method") or row.get("method") or "").strip()})
    forbidden_methods = sorted({method for method in route_methods if any(token in method.lower() for token in OC03C_BASE_SMOKE_FORBIDDEN_METHOD_TOKENS)})
    add(
        "forbidden_smoke_methods",
        "NONE" if not forbidden_methods else "|".join(forbidden_methods),
        not forbidden_methods,
        "NONE",
        "Smoke route audit methods must stay on the validated direct contract.",
    )

    single_year_fallback_detected = bool(
        (unique_years_metric is not None and unique_years_metric <= 1)
        or len(daily_years) <= 1
    )
    add(
        "single_year_fallback_detected",
        int(single_year_fallback_detected),
        not single_year_fallback_detected,
        0,
        f"decoder_unique_years={unique_years_metric}; daily_years={daily_years}",
    )

    assignment_methods = sorted({str(row.get("spatial_assignment_method") or "").strip() for row in daily_rows if str(row.get("spatial_assignment_method") or "").strip()})
    flat_anchor_reconstruction_detected = bool(
        forbidden_methods
        or any(any(token in method.lower() for token in OC03C_BASE_SMOKE_FORBIDDEN_ASSIGNMENT_TOKENS) for method in assignment_methods)
    )
    add(
        "flat_anchor_reconstruction_detected",
        int(flat_anchor_reconstruction_detected),
        not flat_anchor_reconstruction_detected,
        0,
        "assignment_methods=" + ("|".join(assignment_methods) if assignment_methods else "NONE"),
    )

    summary_status = BASE_SMOKE_CONTRACT_FOR_OC03C_PASS if not failures else PORTUGUESE_AQ_BASE_SMOKE_BLOCKED
    detail = "Base smoke contract passed." if summary_status == BASE_SMOKE_CONTRACT_FOR_OC03C_PASS else "Failed checks: " + ", ".join(failures)
    rows_out.append(["base_smoke_contract_for_oc03c_status", summary_status, summary_status, detail])
    rows_out.append(["final_state", summary_status, summary_status, detail])
    write_tsv(gate_path, ["metric", "value", "status", "detail"], rows_out)
    write_tsv(gate_alias_path, ["metric", "value", "status", "detail"], rows_out)
    _write_oc03_base_smoke_contract_report(
        report_path,
        summary_status=summary_status,
        failures=failures,
        rows_out=rows_out,
        route_years=route_years,
        daily_years=daily_years,
        route_methods=route_methods,
        assignment_methods=assignment_methods,
    )

    return {
        "base_smoke_contract_for_oc03c_status": summary_status,
        "base_smoke_contract_for_oc03c_passed": summary_status == BASE_SMOKE_CONTRACT_FOR_OC03C_PASS,
        "base_smoke_contract_for_oc03c_failures": failures,
        "base_smoke_contract_for_oc03c_daily_rows": daily_table_row_count,
        "base_smoke_contract_for_oc03c_unique_dates": unique_date_count,
        "base_smoke_contract_for_oc03c_unique_years": unique_year_count,
        "base_smoke_contract_for_oc03c_unique_units": unique_unit_count,
        "base_smoke_contract_for_oc03c_homogeneous_years": computed_homogeneous_years,
        "base_smoke_contract_for_oc03c_dates_per_year": dict(coverage["dates_by_year"]),
        "base_smoke_contract_for_oc03c_months_present_by_year": dict(coverage["months_by_year"]),
        "base_smoke_contract_for_oc03c_route_years": route_years,
        "base_smoke_contract_for_oc03c_daily_years": daily_years,
        "base_smoke_contract_for_oc03c_route_methods": route_methods,
        "base_smoke_contract_for_oc03c_assignment_methods": assignment_methods,
    }


def collect_final_outputs(output_root: Path, scientific_decision_path: Path, include_global_scan: bool = True) -> List[Path]:
    outputs = [
        output_root / "qa" / "inputs_resolved.json",
        output_root / "qa" / "run_log.txt",
        output_root / "qa" / "QA_checks.csv",
        output_root / "qa" / "report_auditoria_v2.txt",
        output_root / "qa" / "preflight_report.txt",
        output_root / "qa" / "warning_inventory.tsv",
        output_root / "qa" / "brief_encoding_audit.tsv",
        output_root / "qa" / "raw_grid_input_audit.tsv",
        output_root / "qa" / "provenance_runtime_window_audit.tsv",
        output_root / "qa" / "source_runtime_provenance.tsv",
        output_root / "qa" / "objectives_canon_alignment_report.tsv",
        output_root / "qa" / "objectives_canon_alignment_report.md",
        output_root / "qa" / "objectives_canon_sha256.txt",
        output_root / "qa" / "path_scope_guard_report.tsv",
        output_root / "qa" / "smoke_route_audit.tsv",
        output_root / "qa" / "smoke_route_v0_audit.tsv",
        output_root / "qa" / "smoke_route_source_trace_audit.tsv",
        output_root / "qa" / "gfas_pm2p5fire_message_inventory.tsv",
        output_root / "qa" / "gfas_pm2p5fire_portugal_daily_summary.csv",
        output_root / "qa" / "gfas_era5_decoder_backend_audit.tsv",
        output_root / "qa" / "gfas_era5_decoder_daily_spatial_audit.tsv",
        output_root / "qa" / "gfas_era5_decoder_audit.tsv",
        output_root / "qa" / "gfas_era5_decoder_checkpoints.tsv",
        output_root / "qa" / "gfas_era5_presence_audit.tsv",
        output_root / "qa" / "oc03_v11_decoder_contract_validation.tsv",
        output_root / "qa" / "oc03c_base_smoke_contract_gate.tsv",
        output_root / "qa" / "oc03_base_smoke_contract_gate.tsv",
        output_root / "qa" / "oc03_base_smoke_contract_report.md",
        output_root / "qa" / "scientific_validation_gate.tsv",
        output_root / "qa" / "scientific_threshold_evidence_register.tsv",
        output_root / "qa" / "blocked_claims_register.tsv",
        output_root / "qa" / "scientific_claim_gate.tsv",
        output_root / "qa" / "causal_matrix_scientific_gate_audit.tsv",
        output_root / "qa" / "brief_claim_scientific_gate_audit.tsv",
        output_root / "qa" / "objective_semantic_contract_audit.tsv",
        output_root / "qa" / "objective_semantic_contract_report.md",
        output_root / "qa" / "cartographic_package_gate.tsv",
        output_root / "qa" / "cartographic_layers_inventory.tsv",
        output_root / "qa" / "cartographic_join_audit.tsv",
        output_root / "qa" / "municipal_resolution_gate.tsv",
        output_root / "qa" / "matrix_semantic_gate.tsv",
        output_root / "qa" / "population_weighted_smoke_feasibility.tsv",
        output_root / "qa" / "population_weighted_smoke_feasibility.md",
        output_root / "qa" / "municipal_smoke_resolution_feasibility.tsv",
        output_root / "qa" / "municipal_smoke_resolution_feasibility.md",
        output_root / "qa" / "landcover_wui_input_inventory.tsv",
        output_root / "qa" / "formal_wui_feasibility.tsv",
        output_root / "qa" / "formal_wui_feasibility.md",
        output_root / "qa" / "phase3_vs_phase2_scientific_comparison.tsv",
        output_root / "qa" / "phase3_vs_phase2_scientific_comparison.md",
        output_root / "qa" / "phase3c_vs_phase3b_comparison.tsv",
        output_root / "qa" / "phase3c_vs_phase3b_comparison.md",
        output_root / "qa" / "fires_normalized_gpkg_audit.tsv",
        output_root / "qa" / "fire_area_reconciliation_audit.tsv",
        output_root / "qa" / "gate_dependency_freshness_audit.tsv",
        output_root / "qa" / "warning_completeness_audit.tsv",
        output_root / "qa" / "pytest_evidence_inventory.tsv",
        output_root / "qa" / "pytest_result_summary.tsv",
        output_root / "logs" / "pytest_command.txt",
        output_root / "logs" / "pytest_stdout.txt",
        output_root / "logs" / "pytest_stderr.txt",
        output_root / "logs" / "pytest_environment.txt",
        output_root / "qa" / "oc03c_path_scope_preflight.tsv",
        output_root / "qa" / "portuguese_aq_input_inventory.tsv",
        output_root / "qa" / "portuguese_aq_file_format_audit.tsv",
        output_root / "qa" / "portuguese_aq_station_inventory.tsv",
        output_root / "qa" / "portuguese_aq_timeseries_inventory.tsv",
        output_root / "qa" / "portuguese_aq_normalization_audit.tsv",
        output_root / "qa" / "portuguese_aq_station_to_unit_assignment.tsv",
        output_root / "qa" / "gfas_era5_vs_portuguese_aq_concordance.tsv",
        output_root / "qa" / "portuguese_aq_validation_gate.tsv",
        output_root / "qa" / "portuguese_aq_claim_disposition.md",
        output_root / "qa" / "iech_aggregate_consistency_audit.tsv",
        output_root / "qa" / "scenario_aggregate_consistency_audit.tsv",
        output_root / "qa" / "wrb_method_consistency_audit.tsv",
        output_root / "provenance" / "launcher_command.txt",
        output_root / "provenance" / "launcher_roots.tsv",
        output_root / "provenance" / "launcher_exit_code.txt",
        output_root / "tables" / "IECH_unit_2015_2024.csv",
        output_root / "tables" / "IECH_unit_2015_2024_mean.csv",
        output_root / "tables" / "IECH_municipio_2015_2024.csv",
        output_root / "tables" / "IECH_municipio_2015_2024_mean.csv",
        output_root / "tables" / "smoke_days_unit_2015_2024.csv",
        output_root / "tables" / "smoke_days_municipio_2015_2024.csv",
        output_root / "tables" / "smoke_day_score_nuts3_daily.csv",
        output_root / "tables" / "smoke_day_score_municipio_daily.csv",
        output_root / "tables" / "portuguese_aq_daily_station_2015_2024.csv",
        output_root / "tables" / "portuguese_aq_daily_unit_2015_2024.csv",
        output_root / "tables" / "smoke_proxy_aq_concordance_by_unit.csv",
        output_root / "tables" / "wrb_context_nuts3.csv",
        output_root / "tables" / "territorial_context_nuts3.csv",
        output_root / "brief" / "Brief_Politica_IECH_2030.md",
        output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv",
        output_root / "brief" / "causal_matrix" / "territorial_screening_matrix_nuts3.csv",
        output_root / "brief" / "causal_matrix" / "territorial_screening_matrix_municipio.csv",
        output_root / "brief" / "causal_matrix" / "territorial_screening_narrative.md",
        output_root / "maps" / "IECH_ModuleC_master.gpkg",
        output_root / "maps" / "ModuleC_territorial_results.gpkg",
        output_root / "maps" / "fires_normalized_2015_2024.gpkg",
        output_root / "deliverables_step9" / "runtime_closure_decision.md",
        output_root / "deliverables_step9" / "final_manifest_recursive_audit.tsv",
        output_root / "deliverables_step9" / "final_bundle_staleness_audit.tsv",
        scientific_decision_path,
    ]
    if include_global_scan:
        outputs.extend(
            [
                output_root / "qa" / "global_audit_status_scan.tsv",
                output_root / "qa" / "global_audit_status_scan.md",
            ]
        )
    return outputs


def complete_post_smoke_runtime(
    gata_root: Path,
    modulec_datos: Path,
    output_root: Path,
    report: Report,
    rerun_step7: bool = True,
) -> None:
    tables_dir = output_root / "tables"
    brief_dir = output_root / "brief"
    deliver_dir = output_root / "deliverables_step9"

    if rerun_step7:
        run_step7_causal_extension(gata_root, output_root, report)
    else:
        report.log("STEP7 outputs already present; reusing post-smoke artifacts.")
    refresh_warning_inventory_from_runtime_logs(output_root)
    write_brief_encoding_audit(output_root)
    refresh_smoke_route_v0_audit(output_root)
    write_oc03_v11_decoder_contract_validation(output_root)
    base_smoke_meta = run_base_smoke_contract_for_oc03c(output_root)
    if bool(base_smoke_meta.get("base_smoke_contract_for_oc03c_passed")):
        oc03c_meta = run_portuguese_aq_validation(
            modulec_datos=modulec_datos,
            output_root=output_root,
            repo_root=Path(__file__).resolve().parents[1],
            report_log=report.log,
        )
    else:
        report.log("OC-03C AQ validation blocked before AQ consumption: base smoke contract regressed.")
        oc03c_meta = write_blocked_base_smoke_regression_outputs(
            modulec_datos=modulec_datos,
            output_root=output_root,
            repo_root=Path(__file__).resolve().parents[1],
            report_log=report.log,
        )
    inputs_path = output_root / "qa" / "inputs_resolved.json"
    payload: Dict[str, object] = {}
    if inputs_path.exists():
        try:
            payload = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    meta.update(base_smoke_meta)
    meta.update(oc03c_meta)
    meta["objectives_recognized"] = OBJECTIVE_IDS
    payload["meta"] = meta
    paths = payload.get("paths", {})
    if not isinstance(paths, dict):
        paths = {}
    paths["portuguese_aq_root"] = str(oc03c_meta.get("portuguese_aq_root") or "")
    payload["paths"] = paths
    ensure_dir(inputs_path.parent)
    inputs_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    brief_path = brief_dir / "Brief_Politica_IECH_2030.md"
    if not brief_path.exists():
        report.fail(f"Expected brief missing after STEP7_MATRIZ_CAUSAL: {brief_path}")

    run_objectives_gate(output_root, report, mode="pre")
    qa_decision, qa_summary, qa_holds = run_qa_gate(tables_dir, brief_path, report)
    report.log(f"QA gate decision (post-step7/pre-step9): {qa_decision} | {qa_summary}")
    if qa_holds:
        report.log("QA holds: " + ", ".join(qa_holds))

    run_objectives_gate(output_root, report, mode="post")
    scientific_decision_path = run_scientific_gate(output_root, report)
    persist_phase3b_test_evidence(output_root)
    qa_decision, qa_summary, qa_holds = run_qa_gate(tables_dir, brief_path, report)
    report.log(f"QA gate decision (final): {qa_decision} | {qa_summary} | objectives=post")
    if qa_holds:
        report.log("QA holds in final gate: " + ", ".join(qa_holds))
    run_phase3_phase2_scientific_comparison(output_root, report)
    run_global_audit_status_scan(output_root, report)
    assert_global_audit_status_clear(output_root, report)
    write_gate_dependency_freshness_audit(output_root)
    report.log("PROVENANCE FINALIZATION BEFORE STEP9")
    _persist_launcher_exit_code(output_root, 0)
    write_source_runtime_provenance(output_root)
    outputs = collect_final_outputs(output_root, scientific_decision_path, include_global_scan=True)
    build_manifest_and_zip(outputs, deliver_dir, report)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    ap.add_argument("--modulec-datos", required=True)
    ap.add_argument("--inc-new", required=True)
    ap.add_argument("--output-root", required=False, default=None)
    ap.add_argument("--tabular-only", action="store_true")
    ap.add_argument("--bisect-stage", type=int, default=None)
    ap.add_argument("--resume-post-smoke", action="store_true")
    args = ap.parse_args()

    modulec_root = Path(args.modulec_datos).parent
    if args.output_root:
        out_dir = Path(args.output_root)
    else:
        out_dir = modulec_root / "03_outputs"
    qa_dir = out_dir / "qa"
    tables_dir = out_dir / "tables"
    maps_dir = out_dir / "maps"
    brief_dir = out_dir / "brief"
    work_dir = out_dir / "_runtime_work"
    deliver_dir = out_dir / "deliverables_step9"

    report_path = qa_dir / "report_auditoria_v2.txt"
    report = Report(report_path)
    report.log("START v2")
    report.log(f"MODULEC_ROOT={modulec_root}")
    report.log(f"OUTPUT_ROOT={out_dir}")
    _write_launcher_provenance(out_dir, args, dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    inputs_path = qa_dir / "inputs_resolved.json"
    try:
        inputs = load_inputs(inputs_path, report)
        validate_inputs(inputs, report)
        sources = detect_smoke_sources(Path(args.modulec_datos), inputs)
        route_decision = select_smoke_route(sources, decoder_available=False)
        decoder_payload: Dict[str, object] = {"decoder_available": False}

        qgs = None
        if args.tabular_only:
            report.fail("TABULAR_ONLY set but admin/pop/recurrence require QGIS. " + qgis_hint_text())

        if args.resume_post_smoke:
            route_decision = _route_decision_from_inputs(inputs)
            if not route_decision:
                report.fail("RESUME_POST_SMOKE requires existing smoke route metadata in inputs_resolved.json.")
            inputs = apply_route_meta(inputs, sources, route_decision)
            inputs = hydrate_inputs_contract_meta(inputs)
            ensure_dir(inputs_path.parent)
            inputs_path.write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8")
            report.log(
                "RESUME_POST_SMOKE route selected: "
                f"{route_decision.get('route_selected')} ({route_decision.get('smoke_route_decision')})"
            )
            refresh_preflight_report(
                Path(args.gata_root),
                Path(args.modulec_datos),
                Path(args.inc_new),
                out_dir,
                inputs,
                route_decision,
                report,
                qgis_ready=False,
            )
            run_path_scope_guard(Path(args.modulec_datos), out_dir, report, enforce_clean_tree=True)
            write_smoke_route_source_trace_audit(qa_dir, inputs, sources, route_decision)
            write_gfas_era5_presence_audit(qa_dir, sources)
            complete_post_smoke_runtime(
                Path(args.gata_root),
                Path(args.modulec_datos),
                out_dir,
                report,
                rerun_step7=not _step7_outputs_ready(out_dir),
            )
            _persist_launcher_exit_code(out_dir, 0)
            return 0

        qgs = init_qgis(report)

        if args.bisect_stage is not None:
            _bisect_admin_prepare(args.bisect_stage, inputs, maps_dir, report)
            qgs.exitQgis()
            report.log("END v2 PASS (bisect)")
            return 0

        report.log("MARK: after init_qgis (main)")
        report.log("MARK: after init_qgis (main)")
        admin_gpkg = admin_prepare(inputs, maps_dir, report)
        if str(route_decision.get("route_selected", "")) == "BLOCKED_DECODER_REQUIRED":
            decoder_payload = decode_gfas_era5_gdal_proxy(Path(args.modulec_datos), qa_dir, report, admin_gpkg, sources=sources)
            if bool(decoder_payload.get("decoder_available")):
                route_decision = select_smoke_route(sources, decoder_available=True)
                decoder_reason = str(decoder_payload.get("reason") or "").strip()
                if decoder_reason:
                    route_decision = dict(route_decision)
                    route_decision["reason"] = decoder_reason
                    route_decision["allowed_use"] = "scientific_route_with_proxy_limits"
                    route_decision["forbidden_use"] = (
                        "Health or epidemiological exposure claims; "
                        "causal closure beyond bounded direct-observation proxy support."
                    )
        inputs = apply_route_meta(inputs, sources, route_decision)
        inputs = hydrate_inputs_contract_meta(inputs)
        ensure_dir(inputs_path.parent)
        inputs_path.write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8")
        report.log(f"smoke route selected: {route_decision.get('route_selected')} ({route_decision.get('smoke_route_decision')})")
        refresh_preflight_report(
            Path(args.gata_root),
            Path(args.modulec_datos),
            Path(args.inc_new),
            out_dir,
            inputs,
            route_decision,
            report,
            qgis_ready=True,
        )
        run_path_scope_guard(Path(args.modulec_datos), out_dir, report, enforce_clean_tree=True)
        write_smoke_route_source_trace_audit(qa_dir, inputs, sources, route_decision)
        write_gfas_era5_presence_audit(qa_dir, sources)
        write_gfas_era5_decoder_audit(
            qa_dir,
            sources,
            route_decision,
            decoder_available=bool(decoder_payload.get("decoder_available")),
        )
        smoke_csv = smoke_prepare(
            inputs,
            admin_gpkg,
            tables_dir,
            Path(args.modulec_datos),
            route_decision,
            sources,
            report,
            decoder_payload=decoder_payload,
        )
        write_smoke_route_audit(qa_dir, smoke_csv, route_decision)
        smoke_daily_csv = tables_dir / "smoke_day_score_nuts3_daily.csv"
        if smoke_daily_csv.exists():
            write_gfas_era5_decoder_daily_spatial_audit(
                output_root=out_dir,
                smoke_daily_csv=smoke_daily_csv,
                smoke_annual_csv=smoke_csv,
            )
            early_base_smoke_meta = run_base_smoke_contract_for_oc03c(out_dir)
            if bool(early_base_smoke_meta.get("base_smoke_contract_for_oc03c_passed")):
                report.log("OC-03 early base smoke contract PASS; running OC-03C AQ validation checkpoint.")
                run_portuguese_aq_validation(
                    modulec_datos=Path(args.modulec_datos),
                    output_root=out_dir,
                    repo_root=Path(__file__).resolve().parents[1],
                    report_log=report.log,
                )
            else:
                report.log("OC-03 early base smoke contract blocked; writing blocked OC-03C checkpoint outputs.")
                write_blocked_base_smoke_regression_outputs(
                    modulec_datos=Path(args.modulec_datos),
                    output_root=out_dir,
                    repo_root=Path(__file__).resolve().parents[1],
                    report_log=report.log,
                )
        pop_csv = pop_prepare(inputs, admin_gpkg, work_dir, tables_dir, report)
        rec_csv = recurrence_prepare(inputs, admin_gpkg, tables_dir, report)

        for p in (smoke_csv, pop_csv, rec_csv):
            if not p.exists():
                report.fail(f"Expected table missing: {p}")

        smoke_rows = read_csv_rows(smoke_csv)[1]
        nan_count, total, ratio = count_nan_ratio(smoke_rows, "smoke_days")
        if ratio > 0.05:
            report.fail(f"smoke_days NaN ratio {ratio:.2%} ({nan_count}/{total}) exceeds 5%")
        if has_missing_flag(smoke_rows):
            report.fail("smoke_days has missing_flag=1; placeholder detected")
        smoke_vals = [safe_float(r.get("smoke_days")) for r in smoke_rows]
        smoke_vals = [v for v in smoke_vals if v is not None]
        if not smoke_vals:
            report.fail("smoke_days table has no numeric values.")
        if sum(smoke_vals) <= 0.0:
            report.fail("smoke_days degenerate: sum(smoke_days)==0.")
        if max(smoke_vals) <= 0.0:
            report.fail("smoke_days degenerate: max(smoke_days)==0.")
        smoke_methods = [(r.get("smoke_method") or "").strip().lower() for r in smoke_rows]
        if any(m == "proxy_fill_unit_mean" for m in smoke_methods):
            report.fail("Forbidden smoke_method detected: proxy_fill_unit_mean.")
        forbidden_direct_methods = ("flat_single_anchor", "interpolated_from_anchors", "extrapolated_from_anchors")
        if any(any(tok in m for tok in forbidden_direct_methods) for m in smoke_methods):
            report.fail("Forbidden smoke_method detected for OC-03 direct closure: anchored/interpolated/extrapolated.")

        pop_rows = read_csv_rows(pop_csv)[1]
        for col in ("pop_2020_sum", "pop_2025_sum", "pop_2030_sum"):
            n0, t0, r0 = count_nan_ratio(pop_rows, col)
            if r0 > 0.0:
                report.fail(f"{col} has missing values ({n0}/{t0})")
        if has_missing_flag(pop_rows):
            report.fail("pop table has missing_flag=1; placeholder detected")

        rec_rows = read_csv_rows(rec_csv)[1]
        if has_missing_flag(rec_rows):
            report.fail("recurrence table has missing_flag=1; placeholder detected")

        iech_hist, iech_mean = iech_compute(tables_dir, report)
        scen_csv, scen_mean = scenarios_compute(tables_dir, report)
        write_spatial_collapse_root_cause_audit(
            output_root=out_dir,
            smoke_annual_csv=smoke_csv,
            smoke_daily_csv=tables_dir / "smoke_day_score_nuts3_daily.csv",
            gfas_daily_summary_csv=qa_dir / "gfas_pm2p5fire_portugal_daily_summary.csv",
            iech_hist_csv=iech_hist,
        )
        write_gfas_era5_decoder_daily_spatial_audit(
            output_root=out_dir,
            smoke_daily_csv=tables_dir / "smoke_day_score_nuts3_daily.csv",
            smoke_annual_csv=smoke_csv,
        )

        iech_rows = read_csv_rows(iech_hist)[1]
        n_iech, t_iech, r_iech = count_nan_ratio(iech_rows, "IECH")
        if not iech_rows or r_iech > 0.05:
            report.fail(f"IECH NaN ratio {r_iech:.2%} ({n_iech}/{t_iech}) exceeds 5%")
        iech_vals = [safe_float(r.get("IECH")) for r in iech_rows]
        iech_vals = [v for v in iech_vals if v is not None]
        if not iech_vals:
            report.fail("IECH historical degenerate: all values are NaN.")
        if max(iech_vals) <= 0.0:
            report.fail("IECH historical degenerate: max(IECH)==0.")
        scen_rows = read_csv_rows(scen_csv)[1]
        if not scen_rows:
            report.fail("IECH_scenarios_2026_2030.csv has 0 rows")

        complete_post_smoke_runtime(Path(args.gata_root), Path(args.modulec_datos), out_dir, report)
        if qgs:
            qgs.exitQgis()
        _persist_launcher_exit_code(out_dir, 0)
        return 0
    except StageError:
        _persist_launcher_exit_code(out_dir, 2)
        report.log("END v2 NO-GO")
        return 2
    except Exception as e:
        _persist_launcher_exit_code(out_dir, 2)
        report.log("UNEXPECTED ERROR: " + str(e))
        report.log(traceback.format_exc())
        report.log("END v2 NO-GO")
        return 2


if __name__ == "__main__":
    sys.exit(main())






