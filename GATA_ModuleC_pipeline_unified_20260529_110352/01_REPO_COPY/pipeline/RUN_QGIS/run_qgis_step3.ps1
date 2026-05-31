param(
  [string]$GATA_ROOT = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
)

# ---------- limpiar exports (evita PNG update-access) ----------
$exports = Join-Path $GATA_ROOT "Complementariedad de analisis\Module C\03_outputs\qgis\exports_step3"
New-Item -ItemType Directory -Force -Path $exports | Out-Null
Get-ChildItem $exports -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in @(".png",".pdf") } |
  Remove-Item -Force -ErrorAction SilentlyContinue

# ---------- resolver runner PyQGIS ----------
$OSGEO_A = "C:\OSGeo4W64"
$PY_LTR  = Join-Path $OSGEO_A "bin\python-qgis-ltr.bat"
$QGIS_LTR= Join-Path $OSGEO_A "apps\qgis-ltr"

$OSGEO_B = "C:\Users\X412\AppData\Local\Programs\OSGeo4W"
$PY_STD  = Join-Path $OSGEO_B "bin\python-qgis.bat"
$QGIS_STD= Join-Path $OSGEO_B "apps\qgis"

if ((Test-Path $PY_LTR) -and (Test-Path $QGIS_LTR)) {
  $PYQGIS = $PY_LTR
  $QGIS_PREFIX = $QGIS_LTR
} elseif ((Test-Path $PY_STD) -and (Test-Path $QGIS_STD)) {
  $PYQGIS = $PY_STD
  $QGIS_PREFIX = $QGIS_STD
} else {
  throw "No encontrÃ© runner PyQGIS. ProbÃ©: $PY_LTR y $PY_STD"
}

$env:QGIS_PREFIX_PATH = $QGIS_PREFIX
$env:PYTHONNOUSERSITE = "1"
$env:QGIS_CUSTOM_CONFIG_PATH = Join-Path $GATA_ROOT "_qgis_profile_clean"
New-Item -ItemType Directory -Force -Path $env:QGIS_CUSTOM_CONFIG_PATH | Out-Null

$SCRIPT = Join-Path $PSScriptRoot "qgis_step3_discover_muni_and_export.py"
if (!(Test-Path $SCRIPT)) { throw "Falta el script: $SCRIPT" }

$mainLog = Join-Path $PSScriptRoot "qgis_step3_discover_muni_and_export.log"
$warnLog = Join-Path $PSScriptRoot "qgis_step3_warnings.log"
if (Test-Path $warnLog) { Remove-Item $warnLog -Force }

# ---------- ejecutar en CMD con UTF-8 y separar warnings ----------
$inner = 'chcp 65001>nul & set PYTHONIOENCODING=utf-8 & "' + $PYQGIS + '" -u "' + $SCRIPT + '" --gata-root "' + $GATA_ROOT + '" 2^>^&1'
cmd /d /c $inner | ForEach-Object {
  $line = $_.ToString()
  # manda GDAL/PROJ "ERROR x:" a warnings (no bloqueante)
  if ($line -match '^ERROR (1|6):') {
    Add-Content -Path $warnLog -Value $line -Encoding UTF8
  } else {
    $line
  }
} | Tee-Object -FilePath $mainLog

