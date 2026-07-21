param(
  [string]$GATA_ROOT = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
)

Write-Error 'BLOCKED_NON_CANONICAL_LAUNCHER'
Write-Error 'Use: ..\..\02_LAUNCHERS\run_modulec_canonical.ps1'
exit 97

Set-ExecutionPolicy -Scope Process Bypass -Force
$ErrorActionPreference = "Stop"

$REPO = Join-Path $GATA_ROOT "_qa_catalogs\moduleC_local_pipeline"
$CMD = Join-Path $REPO "run_pipeline_v2.cmd"

if (!(Test-Path $CMD)) { throw "No existe: $CMD" }

cmd /c $CMD

