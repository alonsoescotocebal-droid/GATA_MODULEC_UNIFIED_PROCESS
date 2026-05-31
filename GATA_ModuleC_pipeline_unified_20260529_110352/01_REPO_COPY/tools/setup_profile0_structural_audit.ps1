param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$isoRoot = Join-Path $RepoRoot "ISO_GATA_20260121_130505"
$gataRoot = $isoRoot
$moduleCDatos = Join-Path $isoRoot "Complementariedad de analisis\Module C\Datos"
$incNew = Join-Path $isoRoot "Incendios_Nueva version"
$excludeGlobs = "__exports_for_ai;audit/session_*;_TEXTVIEW;_BINVIEW;_rollback_quarantine*;archive;*03_outputs*;*BACKUP*"

if (-not (Test-Path $isoRoot)) { throw "ISO root not found: $isoRoot" }
if (-not (Test-Path $moduleCDatos)) { throw "Module C Datos not found: $moduleCDatos" }
if (-not (Test-Path $incNew)) { throw "Incendios_Nueva version not found: $incNew" }

$env:GATA_ROOT = $gataRoot
$env:MODULEC_DATOS = $moduleCDatos
$env:INC_NEW = $incNew
$env:MODULEC_EXCLUDE_GLOBS = $excludeGlobs

Write-Host "PROFILE_0_STRUCTURAL_AUDIT ready"
Write-Host "GATA_ROOT=$env:GATA_ROOT"
Write-Host "MODULEC_DATOS=$env:MODULEC_DATOS"
Write-Host "INC_NEW=$env:INC_NEW"
Write-Host "MODULEC_EXCLUDE_GLOBS=$env:MODULEC_EXCLUDE_GLOBS"
Write-Host ""
Write-Host "Safe validation commands:"
Write-Host '  rg --files "$isoRoot" | rg "moduleC_pipeline|run_preflight|run_pipeline_debug|preflight"'
Write-Host '  rg --files -g "*.py" "$isoRoot"'
Write-Host '  rg --files | rg "_qa_catalogs\\moduleC_local_pipeline"'
Write-Host '  Get-Content "$isoRoot\\Complementariedad de analisis\\Module C\\03_outputs__BACKUP_20260121_235500\\qa\\preflight_report.csv" -TotalCount 40'
Write-Host '  Get-Content "$isoRoot\\Complementariedad de analisis\\Module C\\03_outputs__BACKUP_20260121_235500\\qa\\preflight_env.json" -TotalCount 80'
