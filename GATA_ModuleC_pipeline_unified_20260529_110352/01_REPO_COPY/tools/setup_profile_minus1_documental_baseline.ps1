param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$isoRoot = Join-Path $RepoRoot "ISO_GATA_20260121_130505"
$compendioRoot = Join-Path $isoRoot "Estado de situacion previo a QGIS PROGRAMA\ModuleC_COMPENDIO_PreProgramacion_DEFINITIVO_NO TOCAR\ModuleC_COMPENDIO_PreProgramacion_2026-01-14"
$pipelineRoot = Join-Path $isoRoot "_qa_catalogs\moduleC_local_pipeline"
$outputCanonical = Join-Path $isoRoot "Complementariedad de analisis\Module C\03_outputs"
$outputAux = Join-Path $pipelineRoot "03_outputs"

$required = @(
    @{ Name = "Compendio historico"; Path = $compendioRoot },
    @{ Name = "README"; Path = (Join-Path $compendioRoot "README.txt") },
    @{ Name = "START_HERE"; Path = (Join-Path $compendioRoot "10_START_HERE__PRE_QGIS_GO.txt") },
    @{ Name = "Rutas canonicas"; Path = (Join-Path $compendioRoot "11_RUTAS_CANONICAS_Y_ENTRADAS.txt") },
    @{ Name = "Secuencia QGIS"; Path = (Join-Path $compendioRoot "13_SECUENCIA_QGIS__PASOS_EJECUTABLES.txt") },
    @{ Name = "PIPELINE_ROOT"; Path = $pipelineRoot },
    @{ Name = "OUTPUT_ROOT canonico"; Path = $outputCanonical },
    @{ Name = "OUTPUT_ROOT auxiliar pipeline"; Path = $outputAux }
)

$rows = foreach ($i in $required) {
    $exists = Test-Path -LiteralPath $i.Path
    [pscustomobject]@{
        Item = $i.Name
        Exists = $exists
        Path = $i.Path
    }
}

$rows | Format-Table -AutoSize

$missing = @($rows | Where-Object { -not $_.Exists })
if ($missing.Count -gt 0) {
    Write-Host "NO-GO: baseline documental incompleto"
    Write-Host "Faltan items obligatorios:"
    $missing | ForEach-Object { Write-Host "  - $($_.Item): $($_.Path)" }
    exit 2
}

$canonNorm = (Resolve-Path -LiteralPath $outputCanonical).Path.TrimEnd('\')
$auxNorm = (Resolve-Path -LiteralPath $outputAux).Path.TrimEnd('\')
if ($canonNorm -eq $auxNorm) {
    Write-Host "NO-GO: OUTPUT canonico y auxiliar son la misma ruta"
    Write-Host "  OUTPUT canonico: $canonNorm"
    Write-Host "  OUTPUT auxiliar: $auxNorm"
    exit 3
}

$expectedCanonical = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\03_outputs"
if ($canonNorm -ne $expectedCanonical) {
    Write-Host "NO-GO: OUTPUT_ROOT canonico distinto del esperado"
    Write-Host "  Esperado: $expectedCanonical"
    Write-Host "  Actual:   $canonNorm"
    exit 4
}

$env:GATA_ROOT = $isoRoot
$env:PIPELINE_ROOT = $pipelineRoot
$env:OUTPUT_ROOT = $outputCanonical
$env:PIPELINE_OUTPUT_AUX = $outputAux

Write-Host "PROFILE_-1_DOCUMENTAL_BASELINE ready"
Write-Host "GATA_ROOT=$env:GATA_ROOT"
Write-Host "PIPELINE_ROOT=$env:PIPELINE_ROOT"
Write-Host "OUTPUT_ROOT=$env:OUTPUT_ROOT"
Write-Host "PIPELINE_OUTPUT_AUX=$env:PIPELINE_OUTPUT_AUX"
Write-Host "Distincion canonico vs auxiliar: OK"
