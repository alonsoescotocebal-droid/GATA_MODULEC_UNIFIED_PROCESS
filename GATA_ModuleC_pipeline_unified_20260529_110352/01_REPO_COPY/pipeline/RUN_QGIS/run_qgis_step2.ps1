param(
  [string]$GATA_ROOT = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
)

$OSGEO = "C:\OSGeo4W64"
$PYQGIS = Join-Path $OSGEO "bin\python-qgis-ltr.bat"
$QGIS_PREFIX = Join-Path $OSGEO "apps\qgis-ltr"

if (!(Test-Path $OSGEO)) { throw "No existe OSGeo4W64 en: $OSGEO" }
if (!(Test-Path $PYQGIS)) { throw "No existe runner: $PYQGIS" }
if (!(Test-Path $QGIS_PREFIX)) { throw "No existe QGIS LTR en: $QGIS_PREFIX" }

$env:QGIS_PREFIX_PATH = $QGIS_PREFIX
$env:PYTHONNOUSERSITE = "1"
$env:QGIS_CUSTOM_CONFIG_PATH = Join-Path $GATA_ROOT "_qgis_profile_clean"
New-Item -ItemType Directory -Force -Path $env:QGIS_CUSTOM_CONFIG_PATH | Out-Null

$SCRIPT = Join-Path $PSScriptRoot "qgis_step2_rebuild_nuts3_pt.py"
if (!(Test-Path $SCRIPT)) { throw "Falta el script: $SCRIPT" }

& $PYQGIS -u $SCRIPT --gata-root $GATA_ROOT 2>&1 |
  Tee-Object -FilePath (Join-Path $PSScriptRoot "qgis_step2_rebuild_nuts3_pt.log")

