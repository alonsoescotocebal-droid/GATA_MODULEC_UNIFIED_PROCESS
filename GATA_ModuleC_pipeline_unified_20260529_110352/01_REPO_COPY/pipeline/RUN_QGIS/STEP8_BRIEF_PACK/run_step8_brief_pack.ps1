param(
  [string]$GATA_ROOT = "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505",
  [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

if([string]::IsNullOrWhiteSpace($OutputRoot) -and $env:GATA_EXTERNAL_OUTPUT_ROOT){
  $OutputRoot = $env:GATA_EXTERNAL_OUTPUT_ROOT
}
if([string]::IsNullOrWhiteSpace($OutputRoot)){
  $OutputRoot = Join-Path $GATA_ROOT "Complementariedad de analisis\Module C\03_outputs"
}

# ----------------------------
# Rutas canónicas STEP8
# ----------------------------
$briefDir = Join-Path $OutputRoot "brief"
$briefMd  = Join-Path $briefDir "Brief_Politica_IECH_2030.md"
$cmDir    = Join-Path $briefDir "causal_matrix"

$need = @(
  $briefMd,
  (Join-Path $cmDir "causal_matrix_IECH_NUTS3.json"),
  (Join-Path $cmDir "causal_matrix_IECH_NUTS3.txt"),
  (Join-Path $cmDir "causal_matrix_sha256_checkpoints.txt")
)

$missing = $need | Where-Object { -not (Test-Path $_) }
if($missing.Count -gt 0){
  throw ("FALTAN INPUTS STEP8:`n- " + ($missing -join "`n- "))
}

# ----------------------------
# Output dir (limpio)
# ----------------------------
$outDir = Join-Path $briefDir "deliverables_step8"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Get-ChildItem -File $outDir -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# ----------------------------
# 1) Brief plano QA remoto-friendly (conversión mínima)
# ----------------------------
$briefTxt = Join-Path $outDir "Brief_Politica_IECH_2030.txt"
$text = Get-Content -Raw -Encoding UTF8 $briefMd
$text = $text -replace "`r`n","`n"
$text = $text -replace '(?s)```.*?```',''
$text = $text -replace '\*\*',''
$text = $text -replace '\*',''
$text = $text -replace '(?m)^\s*#+\s*',''
$text = $text -replace "`t","  "
Set-Content -Encoding UTF8 -Path $briefTxt -Value $text

# ----------------------------
# 2) Copiar artefactos STEP7 + brief md
# ----------------------------
Copy-Item -Force (Join-Path $cmDir "causal_matrix_IECH_NUTS3.json") $outDir
Copy-Item -Force (Join-Path $cmDir "causal_matrix_IECH_NUTS3.txt")  $outDir
Copy-Item -Force (Join-Path $cmDir "causal_matrix_sha256_checkpoints.txt") $outDir
Copy-Item -Force $briefMd $outDir

# ----------------------------
# 3) Manifest + SHA256 checkpoints
# ----------------------------
$items = Get-ChildItem -File $outDir | Sort-Object Name
$manifest = @()
$shaLines = @()
$ts = (Get-Date).ToString("s")

foreach($it in $items){
  $h = (Get-FileHash -Algorithm SHA256 $it.FullName).Hash
  $manifest += [pscustomobject]@{
    name = $it.Name
    bytes = $it.Length
    modified = $it.LastWriteTime.ToString("s")
    sha256 = $h
  }
  $shaLines += ("OUT|" + $it.Name + "|sha256=" + $h + "|bytes=" + $it.Length)
}

$manifestPath = Join-Path $outDir "step8_manifest.json"
($manifest | ConvertTo-Json -Depth 10) | Set-Content -Encoding UTF8 $manifestPath

$shaPath = Join-Path $outDir "step8_sha256_checkpoints.txt"
$lines = @(
  "STEP8_BRIEF_PACK checkpoint",
  ("timestamp=" + $ts),
  ("outputs_dir=" + $outDir)
) + $shaLines
Set-Content -Encoding UTF8 -Path $shaPath -Value $lines

# ----------------------------
# 4) ZIP deliverable + hash (auditoría)
# ----------------------------
$zipPath = Join-Path $outDir "ModuleC_STEP8_BRIEF_CAUSAL_deliverables.zip"
if(Test-Path $zipPath){ Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zipPath -Force

$zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash
Add-Content -Encoding UTF8 -Path $shaPath -Value ("ZIP|" + (Split-Path $zipPath -Leaf) + "|sha256=" + $zipHash + "|bytes=" + (Get-Item $zipPath).Length)

Write-Host "OK STEP8_BRIEF_PACK"
Write-Host "OUTDIR =" $outDir
Write-Host "ZIP   =" $zipPath
Write-Host "ZIP_SHA256 =" $zipHash
