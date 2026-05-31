param(
  [string]$GATA_ROOT = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505",
  [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

if([string]::IsNullOrWhiteSpace($OutputRoot) -and $env:GATA_EXTERNAL_OUTPUT_ROOT){
  $OutputRoot = $env:GATA_EXTERNAL_OUTPUT_ROOT
}
if([string]::IsNullOrWhiteSpace($OutputRoot)){
  $OutputRoot = Join-Path $GATA_ROOT "Complementariedad de analisis\Module C\03_outputs"
}

$SCRIPT = Join-Path $PSScriptRoot "step7_matriz_causal.py"
if(!(Test-Path $SCRIPT)){ throw "Falta: $SCRIPT" }

$OSGEO_CANDIDATES = @(
  "C:\OSGeo4W64",
  "C:\Users\X412\AppData\Local\Programs\OSGeo4W"
)

$OSGEO = $null
foreach($c in $OSGEO_CANDIDATES){
  if(Test-Path $c){ $OSGEO = $c; break }
}
if(!$OSGEO){
  throw ("No encontré OSGeo4W en candidatos: " + ($OSGEO_CANDIDATES -join "; "))
}

$PYQGIS_LTR = Join-Path $OSGEO "bin\python-qgis-ltr.bat"
$PYQGIS_STD = Join-Path $OSGEO "bin\python-qgis.bat"

if(Test-Path $PYQGIS_LTR){ $PYQGIS = $PYQGIS_LTR; $env:QGIS_PREFIX_PATH = (Join-Path $OSGEO "apps\qgis-ltr") }
elseif(Test-Path $PYQGIS_STD){ $PYQGIS = $PYQGIS_STD; $env:QGIS_PREFIX_PATH = (Join-Path $OSGEO "apps\qgis") }
else{ throw "No existe python-qgis-ltr.bat ni python-qgis.bat en $OSGEO\bin" }

$env:GDAL_DRIVER_PATH = (Join-Path $OSGEO 'apps\gdal\lib\gdalplugins')
$env:GISBASE = (Join-Path $OSGEO 'apps\grass\grass84')
$env:GRASS_PROJSHARE = (Join-Path $OSGEO 'share\proj')
$env:PYTHONHOME = (Join-Path $OSGEO 'apps\Python312')
$env:PYTHONUTF8 = "1"
$env:PATH = "$($env:QGIS_PREFIX_PATH)\bin;$(Join-Path $OSGEO 'apps\grass\grass84\lib');$(Join-Path $OSGEO 'apps\grass\grass84\bin');$(Join-Path $OSGEO 'apps\qt5\bin');$(Join-Path $OSGEO 'apps\Python312\Scripts');$(Join-Path $OSGEO 'bin');C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem"
$env:Path = $env:PATH
$env:QGIS_CUSTOM_CONFIG_PATH = Join-Path $OutputRoot "qa\qgis_profile_runtime_step7"
New-Item -ItemType Directory -Force -Path $env:QGIS_CUSTOM_CONFIG_PATH | Out-Null
$env:PYTHONNOUSERSITE = "1"

Write-Host "OSGEO=" $OSGEO
Write-Host "PYQGIS=" $PYQGIS
Write-Host "QGIS_PREFIX_PATH=" $env:QGIS_PREFIX_PATH
Write-Host "QGIS_CUSTOM_CONFIG_PATH=" $env:QGIS_CUSTOM_CONFIG_PATH
Write-Host "OUTPUT_ROOT=" $OutputRoot

$LOG = Join-Path $OutputRoot "qa\step7_matriz_causal.log"
$cmd = ('"{0}" -u "{1}" --gata-root "{2}" --output-root "{3}"' -f $PYQGIS, $SCRIPT, $GATA_ROOT, $OutputRoot)
$oldErr = $ErrorActionPreference
$ErrorActionPreference = "Continue"
cmd /c $cmd 2>&1 | Tee-Object -FilePath $LOG
$ErrorActionPreference = $oldErr
$rc = $LASTEXITCODE
if($rc -ne 0){
  throw "STEP7 failed with exit code $rc. Ver log: $LOG"
}
