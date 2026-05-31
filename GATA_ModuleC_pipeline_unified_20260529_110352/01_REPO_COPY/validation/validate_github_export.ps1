param(
  [string]$ExportRoot,
  [int]$MaxFileSizeMB = 100
)

if([string]::IsNullOrWhiteSpace($ExportRoot)){
  $ExportRoot = Split-Path -Parent $PSScriptRoot
}

$ErrorActionPreference = 'Stop'
$fail = @(); $warn = @()
function Add-Fail([string]$m){ $script:fail += $m }
function Add-Warn([string]$m){ $script:warn += $m }

$required=@('README.md','.gitignore','pipeline\RUN_ModuleC_Pipeline_OSGeo4W.cmd','pipeline\moduleC_pipeline_v2.py','PIPELINE_CANON_HANDOFF\00_PIPELINE_CANON_README.md','PIPELINE_CANON_HANDOFF\PIPELINE_CANON_FINAL_CONTAMINATION_SCAN.csv')
foreach($rq in $required){ if(-not (Test-Path (Join-Path $ExportRoot $rq))){ Add-Fail "Missing required: $rq" } }

$w=Get-ChildItem (Join-Path $ExportRoot 'pipeline') -File -Filter 'RUN_ModuleC_Pipeline_OSGeo4W.cmd' -ErrorAction SilentlyContinue
if(($w|Measure-Object).Count -ne 1){ Add-Fail 'Wrapper único no encontrado exactamente una vez.' }
$runner=Get-ChildItem (Join-Path $ExportRoot 'pipeline') -File -Filter 'moduleC_pipeline_v2.py' -ErrorAction SilentlyContinue
if(($runner|Measure-Object).Count -ne 1){ Add-Fail 'Runner único no encontrado exactamente una vez.' }

$allFiles=Get-ChildItem -Path $ExportRoot -Recurse -File -ErrorAction SilentlyContinue

$forbiddenPathPatterns=@('Module C\Datos','Incendios_Nueva version','03_outputs__BACKUP','run_pipeline_debug_v5.py')
foreach($f in $allFiles){
  foreach($p in $forbiddenPathPatterns){ if($f.FullName -match [regex]::Escape($p)){ Add-Fail "Forbidden item in export: $($f.FullName)" } }
}

$maxBytes=$MaxFileSizeMB*1MB
$big=$allFiles|Where-Object{ $_.Length -gt $maxBytes }
if($big){ $big|ForEach-Object{ Add-Fail "Large file >${MaxFileSizeMB}MB: $($_.FullName) ($($_.Length) bytes)" } }

$forbiddenExt=@('.gpkg','.tif','.tiff','.parquet','.grib','.nc','.7z','.rar','.zip')
$extHits=$allFiles|Where-Object{ $forbiddenExt -contains $_.Extension.ToLowerInvariant() }
if($extHits){ $extHits|ForEach-Object{ Add-Fail "Forbidden extension found: $($_.FullName)" } }

$scanPath=Join-Path $ExportRoot 'PIPELINE_CANON_HANDOFF\PIPELINE_CANON_FINAL_CONTAMINATION_SCAN.csv'
if(Test-Path $scanPath){
  $scan=Import-Csv $scanPath
  $blockers=($scan|Where-Object{ $_.Classification -eq 'ACTIVE_BLOCKER' }).Count
  if($blockers -gt 0){ Add-Fail "Contamination scan has ACTIVE_BLOCKER=$blockers" }
}else{
  Add-Fail 'Missing contamination scan CSV.'
}

$activeFiles=@(
  (Join-Path $ExportRoot 'pipeline\RUN_ModuleC_Pipeline_OSGeo4W.cmd'),
  (Join-Path $ExportRoot 'pipeline\moduleC_pipeline_v2.py'),
  (Join-Path $ExportRoot 'tools\setup_profile3_qgis_runtime.ps1'),
  (Join-Path $ExportRoot 'tools\setup_profile_minus1_documental_baseline.ps1')
) | Where-Object { Test-Path $_ }

$legacyPat='HOST_ROOT|03_outputs__BACKUP|run_pipeline_debug_v5\.py|_qa_catalogs\\moduleC_local_pipeline\\03_outputs|Module C\\Datos\\03_outputs|Complementariedad de analisi_sin base de datos'
$legacyHits=@()
foreach($af in $activeFiles){ $legacyHits += Select-String -Path $af -Pattern $legacyPat -CaseSensitive:$false -ErrorAction SilentlyContinue }
if($legacyHits.Count -gt 0){ $legacyHits|ForEach-Object{ Add-Fail "Legacy active reference: $($_.Path):$($_.LineNumber) -> $($_.Line.Trim())" } }

$badDel=$allFiles|Where-Object{ $_.FullName -match 'deliverables_step9' -and $_.FullName -match 'backup' }
if($badDel){ $badDel|ForEach-Object{ Add-Fail "Historical deliverables copied: $($_.FullName)" } }

Write-Host "ExportRoot=$ExportRoot"
Write-Host "FilesTotal=$($allFiles.Count)"
Write-Host "Warnings=$($warn.Count)"
Write-Host "Failures=$($fail.Count)"
if($warn){ Write-Host 'WARN:'; $warn|ForEach-Object{ Write-Host " - $_" } }
if($fail){ Write-Host 'FAIL:'; $fail|ForEach-Object{ Write-Host " - $_" }; exit 1 }
Write-Host 'PASS: validate_github_export'
exit 0
