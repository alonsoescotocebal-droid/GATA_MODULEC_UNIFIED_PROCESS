param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$RequireIncNew = $true
)

$ErrorActionPreference = "Stop"
$holds = @()
$nogos = @()
$warns = @()

function Add-Hold([string]$m) { $script:holds += $m }
function Add-NoGo([string]$m) { $script:nogos += $m }
function Add-Warn([string]$m) { $script:warns += $m }

function Get-DirSizeSummary([string]$PathValue) {
    try {
        if (-not (Test-Path -LiteralPath $PathValue)) {
            return [pscustomobject]@{ Files = 0; Bytes = 0; MB = 0.0; Note = "missing" }
        }
        $m = Get-ChildItem -LiteralPath $PathValue -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum
        $bytes = [int64]($m.Sum)
        $mb = [math]::Round(($bytes / 1MB), 2)
        return [pscustomobject]@{ Files = [int]$m.Count; Bytes = $bytes; MB = $mb; Note = "ok" }
    } catch {
        return [pscustomobject]@{ Files = -1; Bytes = -1; MB = -1.0; Note = "error: $($_.Exception.Message)" }
    }
}

$configPath = Join-Path $RepoRoot "config\local_paths.ps1"
if (-not (Test-Path -LiteralPath $configPath)) {
    Add-Hold "Missing local config: $configPath"
} else {
    . $configPath
}

$datos = $env:GATA_EXTERNAL_DATOS_MODC
$inc = $env:GATA_EXTERNAL_INC_NEW
$outRoot = $env:GATA_EXTERNAL_OUTPUT_ROOT
$repo = $env:GATA_REPO_ROOT

if ([string]::IsNullOrWhiteSpace($repo)) {
    Add-Hold "Missing GATA_REPO_ROOT in local config."
}
if ([string]::IsNullOrWhiteSpace($datos)) {
    Add-Hold "Missing GATA_EXTERNAL_DATOS_MODC."
} elseif (-not (Test-Path -LiteralPath $datos)) {
    Add-Hold "External DATOS path not found: $datos"
}
if ($RequireIncNew) {
    if ([string]::IsNullOrWhiteSpace($inc)) {
        Add-Hold "Missing GATA_EXTERNAL_INC_NEW."
    } elseif (-not (Test-Path -LiteralPath $inc)) {
        Add-Hold "External INC_NEW path not found: $inc"
    }
}
if ([string]::IsNullOrWhiteSpace($outRoot)) {
    Add-Hold "Missing GATA_EXTERNAL_OUTPUT_ROOT."
} else {
    $rootDrive = [System.IO.Path]::GetPathRoot($outRoot)
    if ([string]::IsNullOrWhiteSpace($rootDrive) -or -not (Test-Path -LiteralPath $rootDrive)) {
        Add-Hold "External OUTPUT_ROOT drive/root not found: $rootDrive"
    } else {
        $outParent = Split-Path -Parent $outRoot
        if (-not (Test-Path -LiteralPath $outRoot) -and -not (Test-Path -LiteralPath $outParent)) {
            Add-Warn "External OUTPUT_ROOT no existe aun; se creara en fase runtime: $outRoot"
        }
    }
}

$catalogs = @(
    "data_placeholders\master_dataset_catalog.csv",
    "data_placeholders\master_inputs_for_pipeline.csv",
    "data_placeholders\master_path_aliases.csv"
)
foreach ($c in $catalogs) {
    $full = Join-Path $RepoRoot $c
    if (-not (Test-Path -LiteralPath $full)) {
        Add-NoGo "Missing external catalog contract file: $c"
    }
}

$inRepoData = @(
    (Join-Path $RepoRoot "Module C\Datos"),
    (Join-Path $RepoRoot "Incendios_Nueva version")
)
foreach ($p in $inRepoData) {
    if (Test-Path -LiteralPath $p) {
        Add-NoGo "Data copy risk: repo should not contain $p"
    }
}

$datosSize = if ([string]::IsNullOrWhiteSpace($datos)) { $null } else { Get-DirSizeSummary -PathValue $datos }
$incSize = if ([string]::IsNullOrWhiteSpace($inc)) { $null } else { Get-DirSizeSummary -PathValue $inc }

Write-Host "RepoRoot=$RepoRoot"
Write-Host "ConfigPath=$configPath"
Write-Host "GATA_REPO_ROOT=$repo"
Write-Host "GATA_EXTERNAL_DATOS_MODC=$datos"
Write-Host "GATA_EXTERNAL_INC_NEW=$inc"
Write-Host "GATA_EXTERNAL_OUTPUT_ROOT=$outRoot"
if ($datosSize) { Write-Host ("DATOS approx: files={0} sizeMB={1} note={2}" -f $datosSize.Files, $datosSize.MB, $datosSize.Note) }
if ($incSize) { Write-Host ("INC_NEW approx: files={0} sizeMB={1} note={2}" -f $incSize.Files, $incSize.MB, $incSize.Note) }
Write-Host "Catalog checks: $($catalogs.Count)"
Write-Host "HOLD count: $($holds.Count)"
Write-Host "NO-GO count: $($nogos.Count)"
Write-Host "WARN count: $($warns.Count)"

if ($holds.Count -gt 0) {
    Write-Host "HOLD:"
    $holds | ForEach-Object { Write-Host " - $_" }
}
if ($nogos.Count -gt 0) {
    Write-Host "NO-GO:"
    $nogos | ForEach-Object { Write-Host " - $_" }
}
if ($warns.Count -gt 0) {
    Write-Host "WARN:"
    $warns | ForEach-Object { Write-Host " - $_" }
}

if ($nogos.Count -gt 0) {
    Write-Host "DECISION=NO-GO"
    exit 3
}
if ($holds.Count -gt 0) {
    Write-Host "DECISION=HOLD"
    exit 2
}

Write-Host "DECISION=PASS"
exit 0
