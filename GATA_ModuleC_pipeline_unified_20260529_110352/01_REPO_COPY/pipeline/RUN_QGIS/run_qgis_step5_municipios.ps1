param(
  [string]$GATA_ROOT = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
)

Write-Host "LOCKS: QGIS Desktop debe estar CERRADO (bloqueos GPKG)." -ForegroundColor Yellow

# Salidas oficiales
$qgisOut = Join-Path $GATA_ROOT "Complementariedad de analisis\Module C\03_outputs\qgis"
$exports = Join-Path $qgisOut "exports_step5_muni"
$delivs  = Join-Path $qgisOut "deliverables_step5_muni"
New-Item -ItemType Directory -Force -Path $exports | Out-Null
New-Item -ItemType Directory -Force -Path $delivs  | Out-Null

# ---- LIMPIEZA FUERTE (evita reusar GPKG parcial/WAL/SHM) ----
$outGpkg = Join-Path $qgisOut "muni_iech_from_nuts3.gpkg"
$outZip  = Join-Path $delivs "ModuleC_STEP5_MUNICIPIOS_deliverables.zip"
$outRep  = Join-Path $qgisOut "qgis_step5_report.json"
$outQgz  = Join-Path $qgisOut "ModuleC_STEP5_municipios.qgz"

$toDelete = @(
  $outGpkg, "$outGpkg-wal", "$outGpkg-shm",
  $outZip, $outRep, $outQgz
)

foreach ($p in $toDelete) {
  if (Test-Path $p) {
    try { Remove-Item -Force $p -ErrorAction Stop } catch { Write-Host "WARN no pude borrar: $p" -ForegroundColor Yellow }
  }
}

# limpiar exports (png/pdf)
Get-ChildItem $exports -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in @(".png",".pdf") } |
  Remove-Item -Force -ErrorAction SilentlyContinue

# Runner LTR (preferido) + fallback
$OSGEO_LTR_ROOT = "C:\OSGeo4W64"
$PY_LTR   = Join-Path $OSGEO_LTR_ROOT "bin\python-qgis-ltr.bat"
$QGIS_LTR = Join-Path $OSGEO_LTR_ROOT "apps\qgis-ltr"

$OSGEO_STD_ROOT = "C:\Users\X412\AppData\Local\Programs\OSGeo4W"
$PY_STD   = Join-Path $OSGEO_STD_ROOT "bin\python-qgis.bat"
$QGIS_STD = Join-Path $OSGEO_STD_ROOT "apps\qgis"

if ((Test-Path $PY_LTR) -and (Test-Path $QGIS_LTR)) {
  $PYQGIS = $PY_LTR
  $env:QGIS_PREFIX_PATH = $QGIS_LTR
} elseif ((Test-Path $PY_STD) -and (Test-Path $QGIS_STD)) {
  $PYQGIS = $PY_STD
  $env:QGIS_PREFIX_PATH = $QGIS_STD
} else {
  throw "No encontrÃ© runner PyQGIS. ProbÃ©: $PY_LTR y $PY_STD"
}

# Perfil limpio
$env:PYTHONNOUSERSITE = "1"
$env:QGIS_CUSTOM_CONFIG_PATH = Join-Path $GATA_ROOT "_qgis_profile_clean"
New-Item -ItemType Directory -Force -Path $env:QGIS_CUSTOM_CONFIG_PATH | Out-Null

Write-Host ("PYQGIS=" + $PYQGIS)
Write-Host ("QGIS_PREFIX_PATH=" + $env:QGIS_PREFIX_PATH)
Write-Host ("QGIS_CUSTOM_CONFIG_PATH=" + $env:QGIS_CUSTOM_CONFIG_PATH)

$SCRIPT = Join-Path $PSScriptRoot "qgis_step5_municipios_caop.py"
if (!(Test-Path $SCRIPT)) { throw "Falta el script: $SCRIPT" }

$mainLog = Join-Path $PSScriptRoot "qgis_step5_municipios_caop.log"
$warnLog = Join-Path $PSScriptRoot "qgis_step5_warnings.log"
if (Test-Path $warnLog) { Remove-Item $warnLog -Force }

$inner = 'chcp 65001>nul & set PYTHONIOENCODING=utf-8 & "' + $PYQGIS + '" -u "' + $SCRIPT + '" --gata-root "' + $GATA_ROOT + '" 2^>^&1'
cmd /d /c $inner | ForEach-Object {
  $line = $_.ToString()
  if ($line -match '^ERROR (1|6):') {
    Add-Content -Path $warnLog -Value $line -Encoding UTF8
  } else {
    $line
  }
} | Tee-Object -FilePath $mainLog

