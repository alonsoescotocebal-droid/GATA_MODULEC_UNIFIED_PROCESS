# bootstrap_moduleC.py
# Arranca moduleC_pipeline.py con PyQGIS headless + sys.path plugins (Processing)
import os
import sys
import runpy

# --- rutas fijas ---
PY_SCRIPT = r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\_qa_catalogs\moduleC_local_pipeline\moduleC_pipeline.py"
GATA_ROOT = r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
MODULEC_DATOS = r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos"
INC_NEW = r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version"
INC_OLD = r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios (Obsoleta)"

OSGEO4W_ROOT = os.environ.get("OSGEO4W_ROOT", r"C:\Users\X412\AppData\Local\Programs\OSGeo4W")
QGIS_APP = os.path.join(OSGEO4W_ROOT, "apps", "qgis")

# --- hardening de entorno QGIS ---
os.environ.setdefault("QGIS_PREFIX_PATH", QGIS_APP)

plugins_path = os.path.join(QGIS_APP, "python", "plugins")
if plugins_path not in sys.path:
    sys.path.insert(0, plugins_path)

# (Opcional) imprime diagnÃƒÂ³stico mÃƒÂ­nimo
print("BOOTSTRAP:")
print("  sys.executable =", sys.executable)
print("  QGIS_PREFIX_PATH =", os.environ.get("QGIS_PREFIX_PATH"))
print("  plugins_path =", plugins_path)

# --- ejecutar script principal como __main__ con argumentos ---
sys.argv = [
    PY_SCRIPT,
    "--gata-root", GATA_ROOT,
    "--modulec-datos", MODULEC_DATOS,
    "--inc-new", INC_NEW,
    "--inc-old", INC_OLD
]

runpy.run_path(PY_SCRIPT, run_name="__main__")

