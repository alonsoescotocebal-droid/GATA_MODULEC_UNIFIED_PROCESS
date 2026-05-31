param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$VenvPath = ".venv_profile2"
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "setup_profile0_structural_audit.ps1") -RepoRoot $RepoRoot

$venvAbs = Join-Path $RepoRoot $VenvPath
if (-not (Test-Path $venvAbs)) {
    python -m venv $venvAbs
}

$py = Join-Path $venvAbs "Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install pandas | Out-Null

Write-Host "PROFILE_2_PYTHON_SMOKE ready"
Write-Host "Venv: $venvAbs"
Write-Host "Python: $py"
Write-Host "Constraint: no qgis import required"
Write-Host ""
Write-Host "Safe smoke checks:"
Write-Host "  & \"$py\" -c \"import pandas as pd; print(pd.__version__)\""
Write-Host "  & \"$py\" -c \"from pathlib import Path; p=Path(r'$env:GATA_ROOT'); print(p.exists())\""
