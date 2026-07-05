# run_gfas_grib_month_coverage_audit.ps1
# Ejecutar desde PowerShell. Ajusta $RuntimeOutput si quieres comparar contra otro runtime.

$ErrorActionPreference = "Stop"

$Roots = @(
  "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos",
  "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
  "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos_RECOVERY_2015_2024"
)

$RuntimeOutput = "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027"

$Out = "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\GFAS_DATE_COVERAGE_AUDIT_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")

$Script = Join-Path (Get-Location) "audit_gfas_grib_month_coverage.py"

if (!(Test-Path $Script)) {
  throw "No encuentro el script Python en: $Script"
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null

Write-Host "============================================================"
Write-Host "GFAS GRIB MONTH COVERAGE AUDIT"
Write-Host "Out: $Out"
Write-Host "============================================================"

python $Script --roots $Roots --runtime-output $RuntimeOutput --out $Out

Write-Host ""
Write-Host "Revisa:"
Write-Host "  $Out\GFAS_GRIB_DATE_COVERAGE_REPORT.md"
Write-Host "  $Out\gfas_coverage_by_year_month.tsv"
Write-Host "  $Out\gfas_coverage_decision_by_year.tsv"
