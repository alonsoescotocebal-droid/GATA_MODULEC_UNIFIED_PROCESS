$ErrorActionPreference = "Continue"

$ROOT   = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
$RUN    = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\_qa_catalogs\moduleC_local_pipeline\RUN_QGIS"
$EXP    = "$ROOT\__exports_for_ai\step3_base_gis"
$OUTQGIS= "$ROOT\Complementariedad de analisis\Module C\03_outputs\qgis"
$OGR    = "C:\OSGeo4W64\bin\ogrinfo.exe"

New-Item -ItemType Directory -Force -Path $EXP | Out-Null

function Invoke-StepIsolated {
  param(
    [string]$StepName,
    [string]$ScriptPath,
    [string]$ConsoleOut,
    [string]$ExitOut,
    [string]$MarkerOut
  )

  (Get-Date -Format "yyyy-MM-dd HH:mm:ss") | Out-File $MarkerOut -Encoding utf8

  $stdout = Join-Path $EXP ($StepName + "_stdout.txt")
  $stderr = Join-Path $EXP ($StepName + "_stderr.txt")

  Remove-Item -Force $stdout,$stderr,$ConsoleOut,$ExitOut -ErrorAction SilentlyContinue

  $cmd = "cd `"$RUN`"; Set-ExecutionPolicy -Scope Process Bypass -Force; & `"$ScriptPath`""
  $p = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-Command",$cmd `
    -Wait -PassThru `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError  $stderr

  ("STEP3_" + $StepName + "_EXITCODE=" + $p.ExitCode) | Out-File $ExitOut -Encoding utf8

  "=== STDOUT ===" | Out-File $ConsoleOut -Encoding utf8
  if (Test-Path $stdout) { Get-Content $stdout | Out-File $ConsoleOut -Append -Encoding utf8 }
  "=== STDERR ===" | Out-File $ConsoleOut -Append -Encoding utf8
  if (Test-Path $stderr) { Get-Content $stderr | Out-File $ConsoleOut -Append -Encoding utf8 }

  return $p.ExitCode
}

# STEP3
$ec3 = Invoke-StepIsolated `
  -StepName "STEP3" `
  -ScriptPath (Join-Path $RUN "run_qgis_step3.ps1") `
  -ConsoleOut (Join-Path $EXP "step3_step3_console.txt") `
  -ExitOut    (Join-Path $EXP "step3_step3_exitcode.txt") `
  -MarkerOut  (Join-Path $EXP "RUN_MARKER_STEP3.txt")

if ($ec3 -ne 0) {
  ("STOP_CURRENT: Step3 fallo (exitcode=" + $ec3 + "). NO correr Step5.") | Out-File (Join-Path $EXP "STEP3_STOP_REASON_CURRENT.txt") -Encoding utf8
  Read-Host "FIN (Step3 fallo). Presiona Enter para cerrar"
  exit $ec3
}

# STEP5
$ec5 = Invoke-StepIsolated `
  -StepName "STEP5" `
  -ScriptPath (Join-Path $RUN "run_qgis_step5_municipios.ps1") `
  -ConsoleOut (Join-Path $EXP "step3_step5_console.txt") `
  -ExitOut    (Join-Path $EXP "step3_step5_exitcode.txt") `
  -MarkerOut  (Join-Path $EXP "RUN_MARKER_STEP5.txt")

# QA MINIMO (si hay outputs)
# Lista GPKG
Get-ChildItem -Path $OUTQGIS -Filter *.gpkg -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 30 Name,Length,LastWriteTime |
  Format-Table -AutoSize | Out-String |
  Out-File (Join-Path $EXP "step3_outqgis_gpkg_list.txt") -Encoding utf8

# ogrinfo summary
$sum = Join-Path $EXP "step3_ogrinfo_summary.txt"
Remove-Item -Force $sum -ErrorAction SilentlyContinue
$gpkg = Get-ChildItem -Path $OUTQGIS -Filter *.gpkg -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
foreach($f in $gpkg){
  "===== OGRINFO: $($f.FullName) =====" | Out-File $sum -Append -Encoding utf8
  & $OGR -so "$($f.FullName)" 2>&1 | Out-File $sum -Append -Encoding utf8
  "" | Out-File $sum -Append -Encoding utf8
}

# Señales AUTO (NUTS3 + MUNI candidato)
$nuts = Join-Path $OUTQGIS "nuts3_iech.gpkg"
$muni = Get-ChildItem -Path $OUTQGIS -Filter *.gpkg -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'mun|muni|municip' } |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1

$nutsCount = ""
$muniCount = ""
$crsOk = ""

if (Test-Path $nuts) {
  $t = (& $OGR -so $nuts 2>&1 | Out-String)
  if ($t -match 'Feature Count:\s*(\d+)') { $nutsCount = $Matches[1] }
  if ($t -match 'AUTHORITY\["EPSG","3763"\]' -or $t -match 'EPSG[:\s]*3763') { $crsOk = "EPSG:3763" }
}

if ($muni) {
  $t2 = (& $OGR -so $muni.FullName 2>&1 | Out-String)
  if ($t2 -match 'Feature Count:\s*(\d+)') { $muniCount = $Matches[1] }
}

("NUTS3_FEATURES=" + $nutsCount + " ; MUNI_FEATURES=" + $muniCount + " ; CRS_OK=" + $crsOk) |
  Out-File (Join-Path $EXP "step3_counts_signals.txt") -Encoding utf8

@"
PASO 3 — QA BASE GIS (Step3/Step5)
OUT_QGIS: $OUTQGIS
EXPORTS:  $EXP

Exitcodes:
- Step3: $ec3
- Step5: $ec5
"@ | Out-File (Join-Path $EXP "STEP3_BASEGIS_SUMMARY.txt") -Encoding utf8

Read-Host "FIN (SAFE wrapper). Presiona Enter para cerrar"
exit $ec5

