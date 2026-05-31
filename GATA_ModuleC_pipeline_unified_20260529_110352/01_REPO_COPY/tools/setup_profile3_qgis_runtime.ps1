param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$PyQgis = "C:\OSGeo4W64\bin\python-qgis-ltr.bat",
    [string]$QgisPrefixPath = "C:\OSGeo4W64\apps\qgis-ltr",
    [string]$QgisCustomConfigPath = "",
    [switch]$StrictRuntimeChecks
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($QgisCustomConfigPath)) {
    $QgisCustomConfigPath = Join-Path $RepoRoot "logs\qgis_profile_runtime"
}

function Invoke-QgisStrictProbe {
    param(
        [string]$PyQgisLauncher,
        [string]$QgisPrefix,
        [string]$QgisCustomConfig
    )

    if (-not (Test-Path -LiteralPath $QgisCustomConfig)) {
        New-Item -ItemType Directory -Path $QgisCustomConfig -Force | Out-Null
    }

    $probePath = Join-Path $env:TEMP ("modulec_qgis_probe_{0}.py" -f ([Guid]::NewGuid().ToString("N")))
    $cleanPath = "C:\OSGeo4W64\apps\qgis-ltr\bin;C:\OSGeo4W64\apps\qt5\bin;C:\OSGeo4W64\apps\Python312\Scripts;C:\OSGeo4W64\bin;C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem"
    $pluginsPath = Join-Path $QgisPrefix "python\plugins"
    $probeScript = @"
import os
import sys

os.environ["QGIS_CUSTOM_CONFIG_PATH"] = r"$QgisCustomConfig"
os.environ["PATH"] = r"$cleanPath"
plugins = r"$pluginsPath"
if plugins not in sys.path:
    sys.path.insert(0, plugins)

from qgis.core import QgsApplication
print("QGIS_CORE_OK")

import processing
print("PROCESSING_IMPORT_OK")

from processing.core.Processing import Processing
QgsApplication.setPrefixPath(r"$QgisPrefix", True)
qgs = QgsApplication([], False)
qgs.initQgis()
Processing.initialize()
providers = sorted([p.id() for p in QgsApplication.processingRegistry().providers()])
print("PROCESSING_INIT_OK")
print("PROVIDERS=" + "|".join(providers))
qgs.exitQgis()
"@

    Set-Content -LiteralPath $probePath -Value $probeScript -Encoding ASCII
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $probeOutput = & $PyQgisLauncher -u $probePath 2>&1
        $probeExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
        if (Test-Path -LiteralPath $probePath) {
            Remove-Item -LiteralPath $probePath -Force
        }
    }

    $outputText = ($probeOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine
    return @{
        ExitCode = $probeExit
        Output = $outputText
        QgisCoreOk = ($outputText -match "QGIS_CORE_OK")
        ProcessingImportOk = ($outputText -match "PROCESSING_IMPORT_OK")
        ProcessingInitOk = ($outputText -match "PROCESSING_INIT_OK")
        ProvidersLine = ((@($probeOutput | Where-Object { "$_" -like "PROVIDERS=*" }) | Select-Object -First 1) -as [string])
        HasWindowsAppsPermissionWarning = ($outputText -match "PermissionError: \[WinError 5\].*WindowsApps")
    }
}

$exportPipelineRoot = Join-Path $RepoRoot "pipeline"
$exportWrapper = Join-Path $exportPipelineRoot "RUN_ModuleC_Pipeline_OSGeo4W.cmd"
$exportPreflight = Join-Path $exportPipelineRoot "run_preflight_bootstrap.py"
$exportPipelineV2 = Join-Path $exportPipelineRoot "moduleC_pipeline_v2.py"
$exportPipelineV1 = Join-Path $exportPipelineRoot "moduleC_pipeline.py"
$exportRunDebug = Join-Path $exportPipelineRoot "run_pipeline_debug.py"

$isoRoot = Join-Path $RepoRoot "ISO_GATA_20260121_130505"
$isoPipelineRoot = Join-Path $isoRoot "_qa_catalogs\moduleC_local_pipeline"
$isoWrapper = Join-Path $isoPipelineRoot "RUN_ModuleC_Pipeline_OSGeo4W.cmd"
$isoPreflight = Join-Path $isoPipelineRoot "run_preflight_bootstrap.py"
$isoPipelineV1 = Join-Path $isoPipelineRoot "moduleC_pipeline.py"
$isoPipelineV2 = Join-Path $isoPipelineRoot "moduleC_pipeline_v2.py"
$isoRunDebug = Join-Path $isoPipelineRoot "run_pipeline_debug.py"
$isoOutputCanonical = Join-Path $isoRoot "Complementariedad de analisis\Module C\03_outputs"
$compendio = Join-Path $isoRoot "Estado de situacion previo a QGIS PROGRAMA\ModuleC_COMPENDIO_PreProgramacion_DEFINITIVO_NO TOCAR\ModuleC_COMPENDIO_PreProgramacion_2026-01-14\11_RUTAS_CANONICAS_Y_ENTRADAS.txt"

$hasExport = Test-Path -LiteralPath $exportWrapper
$hasIso = Test-Path -LiteralPath $isoWrapper

if ($hasExport -and $hasIso) {
    Write-Host "NO-GO: layout ambiguo (export + ISO) en RepoRoot=$RepoRoot"
    exit 11
}
if (-not $hasExport -and -not $hasIso) {
    Write-Host "NO-GO: no se encontro wrapper activo ni en export ni en ISO"
    exit 12
}

$mode = "EXPORT"
$pipelineRoot = $exportPipelineRoot
$wrapper = $exportWrapper
$preflight = $exportPreflight
$pipelineV1 = $exportPipelineV1
$pipelineV2 = $exportPipelineV2
$runDebug = $exportRunDebug
$outputCanonical = $env:GATA_EXTERNAL_OUTPUT_ROOT
$datosPath = $env:GATA_EXTERNAL_DATOS_MODC
$incPath = $env:GATA_EXTERNAL_INC_NEW
$mountWarnings = @()

if ($hasIso) {
    $mode = "ISO"
    . (Join-Path $PSScriptRoot "setup_profile_minus1_documental_baseline.ps1") -RepoRoot $RepoRoot
    $pipelineRoot = $isoPipelineRoot
    $wrapper = $isoWrapper
    $preflight = $isoPreflight
    $pipelineV1 = $isoPipelineV1
    $pipelineV2 = $isoPipelineV2
    $runDebug = $isoRunDebug
    $outputCanonical = $isoOutputCanonical
    $datosPath = Join-Path $isoRoot "Complementariedad de analisis\Module C\Datos"
    $incPath = Join-Path $isoRoot "Incendios_Nueva version"
} else {
    $localConfig = Join-Path $RepoRoot "config\local_paths.ps1"
    if (Test-Path -LiteralPath $localConfig) {
        . $localConfig
        $outputCanonical = $env:GATA_EXTERNAL_OUTPUT_ROOT
        $datosPath = $env:GATA_EXTERNAL_DATOS_MODC
        $incPath = $env:GATA_EXTERNAL_INC_NEW
    }
}

$requiredHard = @(
    @{ Name = "Wrapper"; Path = $wrapper },
    @{ Name = "Preflight bootstrap"; Path = $preflight }
)
if ($mode -eq "ISO") {
    $requiredHard += @{ Name = "Output canonico"; Path = $outputCanonical }
}
$missingHard = @($requiredHard | Where-Object { -not (Test-Path -LiteralPath $_.Path) })
if ($missingHard.Count -gt 0) {
    Write-Host "NO-GO: faltan componentes estructurales obligatorios"
    $missingHard | ForEach-Object { Write-Host "  - $($_.Name): $($_.Path)" }
    exit 2
}

if ($mode -eq "EXPORT") {
    if ([string]::IsNullOrWhiteSpace($datosPath)) {
        Write-Host "NO-GO: GATA_EXTERNAL_DATOS_MODC no definido (config/local_paths.ps1 o variable de entorno)."
        exit 13
    }
    if (-not (Test-Path -LiteralPath $datosPath)) {
        Write-Host "NO-GO: GATA_EXTERNAL_DATOS_MODC no existe: $datosPath"
        exit 14
    }
    if ([string]::IsNullOrWhiteSpace($incPath)) {
        Write-Host "NO-GO: GATA_EXTERNAL_INC_NEW no definido (config/local_paths.ps1 o variable de entorno)."
        exit 15
    }
    if (-not (Test-Path -LiteralPath $incPath)) {
        Write-Host "NO-GO: GATA_EXTERNAL_INC_NEW no existe: $incPath"
        exit 16
    }
    if ([string]::IsNullOrWhiteSpace($outputCanonical)) {
        Write-Host "NO-GO: GATA_EXTERNAL_OUTPUT_ROOT no definido (config/local_paths.ps1 o variable de entorno)."
        exit 17
    }
    if (-not (Test-Path -LiteralPath $outputCanonical)) {
        $outputParent = Split-Path -Parent $outputCanonical
        if ([string]::IsNullOrWhiteSpace($outputParent)) {
            Write-Host "NO-GO: parent de GATA_EXTERNAL_OUTPUT_ROOT invalido: $outputParent"
            exit 18
        }
        if (-not (Test-Path -LiteralPath $outputParent)) {
            $outputDrive = [System.IO.Path]::GetPathRoot($outputCanonical)
            if ([string]::IsNullOrWhiteSpace($outputDrive) -or -not (Test-Path -LiteralPath $outputDrive)) {
                Write-Host "NO-GO: root/drive de GATA_EXTERNAL_OUTPUT_ROOT no existe: $outputDrive"
                exit 18
            }
            $mountWarnings += "OUTPUT_ROOT no existe aun y se creara en runtime: $outputCanonical"
        }
    }
}

$hasPipelineCore = (Test-Path -LiteralPath $pipelineV1) -or (Test-Path -LiteralPath $pipelineV2)
if (-not $hasPipelineCore) {
    Write-Host "NO-GO: falta pipeline core (moduleC_pipeline.py o moduleC_pipeline_v2.py)"
    exit 3
}

$wrapperText = Get-Content -LiteralPath $wrapper -Raw
$runnerCandidates = [ordered]@{
    "moduleC_pipeline_v2.py" = $pipelineV2
    "moduleC_pipeline.py" = $pipelineV1
    "run_pipeline_debug.py" = $runDebug
}

$referencedInWrapper = @()
foreach ($k in $runnerCandidates.Keys) {
    if ($wrapperText -match [regex]::Escape($k)) {
        $referencedInWrapper += $k
    }
}
if ($referencedInWrapper.Count -eq 0) {
    Write-Host "NO-GO: wrapper no referencia runners conocidos"
    Write-Host "  Wrapper: $wrapper"
    exit 4
}

$existingReferenced = @($referencedInWrapper | Where-Object { Test-Path -LiteralPath $runnerCandidates[$_] })
if ($existingReferenced.Count -eq 0) {
    Write-Host "NO-GO: wrapper referencia runners que no existen"
    $referencedInWrapper | ForEach-Object { Write-Host "  - $_" }
    exit 5
}

$effectiveRunner = $existingReferenced[0]
$effectiveRunnerPath = $runnerCandidates[$effectiveRunner]

if ($mode -eq "ISO" -and $effectiveRunner -eq "run_pipeline_debug.py" -and (Test-Path -LiteralPath $compendio)) {
    $docMentions = Select-String -LiteralPath $compendio -Pattern "run_pipeline_debug.py" -SimpleMatch -Quiet
    if (-not $docMentions) {
        Write-Host "HOLD: run_pipeline_debug.py existe pero no aparece documentado en rutas canonicas"
        exit 6
    }
}

$runtimePrereqMissing = @()
if (-not (Test-Path -LiteralPath $PyQgis)) { $runtimePrereqMissing += "PYQGIS launcher: $PyQgis" }
if (-not (Test-Path -LiteralPath $QgisPrefixPath)) { $runtimePrereqMissing += "QGIS_PREFIX_PATH: $QgisPrefixPath" }

if ($StrictRuntimeChecks -and $runtimePrereqMissing.Count -gt 0) {
    Write-Host "NO-GO: prerequisitos runtime no disponibles"
    $runtimePrereqMissing | ForEach-Object { Write-Host "  - $_" }
    exit 7
}

if ($StrictRuntimeChecks) {
    $probe = Invoke-QgisStrictProbe -PyQgisLauncher $PyQgis -QgisPrefix $QgisPrefixPath -QgisCustomConfig $QgisCustomConfigPath
    if ($probe.ExitCode -ne 0 -or -not $probe.QgisCoreOk -or -not $probe.ProcessingImportOk -or -not $probe.ProcessingInitOk) {
        Write-Host "HOLD_ENVIRONMENT: probes strictos QGIS/Processing no pasaron"
        Write-Host "  ProbeExitCode=$($probe.ExitCode)"
        Write-Host "  QGIS_CORE_OK=$($probe.QgisCoreOk)"
        Write-Host "  PROCESSING_IMPORT_OK=$($probe.ProcessingImportOk)"
        Write-Host "  PROCESSING_INIT_OK=$($probe.ProcessingInitOk)"
        Write-Host "  --- Probe output ---"
        Write-Host $probe.Output
        exit 8
    }
}

$env:PYQGIS = $PyQgis
$env:QGIS_PREFIX_PATH = $QgisPrefixPath
$env:QGIS_CUSTOM_CONFIG_PATH = $QgisCustomConfigPath
$env:PIPELINE_ROOT = $pipelineRoot
$env:OUTPUT_ROOT = $outputCanonical
$env:EFFECTIVE_RUNNER = $effectiveRunnerPath
$env:MODULEC_DATOS = $datosPath
$env:INC_NEW = $incPath

Write-Host "PROFILE_3_QGIS_RUNTIME ready"
Write-Host "Mode=$mode"
Write-Host "Wrapper=$wrapper"
Write-Host "EffectiveRunner=$effectiveRunnerPath"
Write-Host "Preflight=$preflight"
Write-Host "OutputCanonical=$outputCanonical"
Write-Host "ModuleCDatos=$datosPath"
Write-Host "IncendiosNew=$incPath"
Write-Host "PYQGIS=$env:PYQGIS"
Write-Host "QGIS_PREFIX_PATH=$env:QGIS_PREFIX_PATH"
Write-Host "QGIS_CUSTOM_CONFIG_PATH=$env:QGIS_CUSTOM_CONFIG_PATH"
Write-Host ""
if ($runtimePrereqMissing.Count -gt 0) {
    Write-Host "Runtime prereq warnings (no bloqueantes en gate estructural):"
    $runtimePrereqMissing | ForEach-Object { Write-Host "  - $_" }
    Write-Host ""
}
if ($mountWarnings.Count -gt 0) {
    Write-Host "Mount warnings (no bloqueantes):"
    $mountWarnings | ForEach-Object { Write-Host "  - $_" }
    Write-Host ""
}
Write-Host "Safe runtime checks:"
Write-Host '  & "$env:PYQGIS" -c "from qgis.core import QgsApplication; print(''ok'')"'
Write-Host '  & "$env:PYQGIS" -c "from osgeo import gdal; print(gdal.VersionInfo())"'
if ($StrictRuntimeChecks) {
    if ($probe.HasWindowsAppsPermissionWarning) {
        Write-Host ""
        Write-Host "Warning observado: PermissionError WinError 5 sobre WindowsApps (sitecustomize), mitigado por probe controlado."
    }
    Write-Host "StrictProbeProviders=$($probe.ProvidersLine)"
}
