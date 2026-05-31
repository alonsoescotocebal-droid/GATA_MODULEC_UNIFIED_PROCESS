#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_preflight_bootstrap.py

Arranca QgsApplication + Processing y luego ejecuta el preflight real (moduleC_preflight.py)
con runpy, preservando argumentos.

Uso:
  set "PREFLIGHT_PY=...\moduleC_preflight.py"
  C:\OSGeo4W64\bin\python-qgis-ltr.bat -u run_preflight_bootstrap.py --gata-root ... --modulec-datos ... --inc-new ...
"""

from __future__ import annotations

import os
import sys
import runpy
from pathlib import Path


def _sanitize_windows_path(path_env: str) -> str:
    keep = []
    for part in path_env.split(os.pathsep):
        p = (part or "").strip()
        if not p:
            continue
        if "windowsapps" in p.lower():
            continue
        keep.append(p)
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


def _guess_qgis_prefix() -> str | None:
    candidates: list[str] = []

    env = os.environ.get("QGIS_PREFIX_PATH")
    if env:
        candidates.append(env)

    o4w = os.environ.get("OSGEO4W_ROOT")
    if o4w:
        candidates.extend([str(Path(o4w) / "apps" / "qgis"), str(Path(o4w) / "apps" / "qgis-ltr")])

    candidates.extend([r"C:\OSGeo4W64\apps\qgis", r"C:\OSGeo4W64\apps\qgis-ltr"])

    for c in candidates:
        try:
            p = Path(c)
            if p.exists() and (p / "python").exists():
                return str(p)
        except Exception:
            continue
    return None


def init_qgis_and_processing(prefix_path: str) -> None:
    qgis_prefix = Path(prefix_path)
    qgis_bin = qgis_prefix / "bin"
    qt_bin = Path(r"C:\OSGeo4W64\apps\qt5\bin")
    py_scripts = Path(r"C:\OSGeo4W64\apps\Python312\Scripts")
    osgeo_bin = Path(r"C:\OSGeo4W64\bin")
    py_dir = qgis_prefix / "python"
    plugins = py_dir / "plugins"

    os.environ["QGIS_PREFIX_PATH"] = str(qgis_prefix)
    os.environ["QT_PLUGIN_PATH"] = f"{qgis_prefix / 'qtplugins'};{Path(r'C:\OSGeo4W64\apps\qt5\plugins')}"
    os.environ["GDAL_DATA"] = r"C:\OSGeo4W64\apps\gdal\share\gdal"
    os.environ["PROJ_LIB"] = r"C:\OSGeo4W64\share\proj"
    os.environ["PROJ_DATA"] = r"C:\OSGeo4W64\share\proj"

    path_env = os.pathsep.join(
        [
            str(qgis_bin),
            str(qt_bin),
            str(py_scripts),
            str(osgeo_bin),
            r"C:\WINDOWS\system32",
            r"C:\WINDOWS",
            r"C:\WINDOWS\System32\Wbem",
        ]
    )
    path_env = _sanitize_windows_path(path_env)
    os.environ["PATH"] = path_env
    os.environ["Path"] = path_env

    if py_dir.exists():
        sp = str(py_dir)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    if plugins.exists():
        sp = str(plugins)
        if sp not in sys.path:
            sys.path.insert(0, sp)

    from qgis.core import QgsApplication  # type: ignore

    QgsApplication.setPrefixPath(str(qgis_prefix), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    import processing  # noqa: F401
    from processing.core.Processing import Processing  # type: ignore
    Processing.initialize()


def main() -> int:
    _patch_add_dll_directory()

    path_env = os.environ.get("PATH", "")
    if path_env:
        os.environ["PATH"] = _sanitize_windows_path(path_env)

    preflight = (os.environ.get("PREFLIGHT_PY") or "").strip()
    if not preflight:
        print("ERROR: PREFLIGHT_PY no definido", file=sys.stderr)
        return 2

    preflight_path = Path(preflight)
    if not preflight_path.exists():
        print(f"ERROR: no existe PREFLIGHT_PY: {preflight_path}", file=sys.stderr)
        return 2

    prefix = (os.environ.get("QGIS_PREFIX_PATH") or "").strip()
    if not prefix:
        guessed = _guess_qgis_prefix()
        if not guessed:
            print("ERROR: No pude deducir QGIS_PREFIX_PATH", file=sys.stderr)
            return 3
        prefix = guessed
        os.environ["QGIS_PREFIX_PATH"] = prefix

    init_qgis_and_processing(prefix)

    argv0 = sys.argv[0]
    sys.argv[0] = str(preflight_path)
    try:
        runpy.run_path(str(preflight_path), run_name="__main__")
        return 0
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    finally:
        sys.argv[0] = argv0
        try:
            from qgis.core import QgsApplication  # type: ignore
            QgsApplication.exitQgis()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
