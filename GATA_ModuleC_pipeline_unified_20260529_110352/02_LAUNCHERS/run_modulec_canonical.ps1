[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Preflight','Smoke','Full')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$RuntimeId,
    [Parameter(Mandatory=$true)][string]$ExpectedHeadSha,
    [Parameter(Mandatory=$true)][string]$ModuleCDataRoot,
    [Parameter(Mandatory=$true)][string]$PortugueseAgenciesDataRoot,
    [Parameter(Mandatory=$true)][string]$Recovery20152024Root,
    [Parameter(Mandatory=$true)][string]$IncendiosRoot,
    [Parameter(Mandatory=$true)][string]$GfasRoot,
    [Parameter(Mandatory=$true)][string]$CanonicalConfig,
    [switch]$AllowFullRuntime
)

$ErrorActionPreference = 'Stop'
$Container = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$GitRoot = (Resolve-Path (Join-Path $Container '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $Container '01_REPO_COPY')).Path
$GuardScript = Join-Path $RepoRoot 'pipeline\path_scope_guard.py'
$SmokerunScript = Join-Path $RepoRoot 'tools\modulec_canonical_structural_run.py'
$LauncherPath = (Resolve-Path $PSCommandPath).Path
$RuntimeRoot = Join-Path (Join-Path $Container '03_RUNTIMES') $RuntimeId
$SemanticContract = Join-Path $RepoRoot 'contracts\MODULE_C_SEMANTIC_MINIMUM_V1.md'
$SemanticContractTsv = Join-Path $Container '00_CANON\MODULE_C_OBJECTIVE_EXECUTION_CONTRACT.tsv'
$ScientificPython = 'C:\OSGeo4W64\bin\python-qgis-ltr.bat'
$ScientificPipeline = Join-Path $RepoRoot 'pipeline\moduleC_pipeline_v2.py'

if ($Mode -eq 'Full') {
    if (-not $AllowFullRuntime) { throw 'BLOCKED_FULL_RUNTIME_NOT_AUTHORIZED' }
}
if ($ExpectedHeadSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'BLOCKED_EXPECTED_HEAD_SHA_INVALID' }
if ((Resolve-Path $CanonicalConfig).Path -ne (Resolve-Path (Join-Path $RepoRoot 'config\module_c_canonical_paths.json')).Path) { throw 'BLOCKED_NON_CANONICAL_CONFIG' }
if (Test-Path -LiteralPath $RuntimeRoot) { throw "BLOCKED_OUTPUT_ROOT_EXISTS: $RuntimeRoot" }
if (-not (Test-Path -LiteralPath $SemanticContract)) { throw "BLOCKED_SEMANTIC_CONTRACT_MISSING: $SemanticContract" }

$clearNames = @('OUTPUT_ROOT','DATA_ROOT','RUNTIME_ROOT','RUN_ROOT','REPO_ROOT','GATA_ROOT','GATA_REPO_ROOT','MODULEC_OUTPUT_ROOT','GATA_MODULEC_OUTPUT_ROOT','MODULEC_DATA_ROOT','GATA_MODULEC_DATA_ROOT','MODULEC_RUNTIME_ROOT','MODULEC_RUN_ROOT')
$cleared = @()
foreach ($name in $clearNames) {
    $wasDefined = Test-Path "Env:$name"
    if ($wasDefined) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    $cleared += "$name`t" + ($(if ($wasDefined) { 'CLEARED' } else { 'ABSENT' }))
}

if ($Mode -eq 'Full') {
    if (-not (Test-Path -LiteralPath $ScientificPython)) { throw "BLOCKED_SCIENTIFIC_PYTHON_MISSING: $ScientificPython" }
    if (-not (Test-Path -LiteralPath $ScientificPipeline)) { throw "BLOCKED_SCIENTIFIC_PIPELINE_MISSING: $ScientificPipeline" }

    # The runtime is created only after the existence guard and remains a new, non-resumable root.
    New-Item -ItemType Directory -Force -Path $RuntimeRoot, (Join-Path $RuntimeRoot 'logs'), (Join-Path $RuntimeRoot 'provenance') | Out-Null
    $guardStdout = Join-Path $RuntimeRoot 'logs\path_scope_guard_stdout.txt'
    $guardStderr = Join-Path $RuntimeRoot 'logs\path_scope_guard_stderr.txt'
    $guardArgs = @(
        '-u', $GuardScript,
        '--git-toplevel', $GitRoot,
        '--pipeline-code-root', $RepoRoot,
        '--modulec-data-root', $ModuleCDataRoot,
        '--portuguese-agencies-root', $PortugueseAgenciesDataRoot,
        '--recovery-2015-2024-root', $Recovery20152024Root,
        '--incendios-root', $IncendiosRoot,
        '--gfas-root', $GfasRoot,
        '--output-root', $RuntimeRoot,
        '--config-path', $CanonicalConfig,
        '--expected-head-sha', $ExpectedHeadSha,
        '--enforce-clean-tree', '1',
        '--allow-resume', '0'
    )
    & python @guardArgs 1> $guardStdout 2> $guardStderr
    if ($LASTEXITCODE -ne 0) { throw "CANONICAL_FULL_PATH_GUARD_FAILED: exit=$LASTEXITCODE" }

    $provenanceDir = Join-Path $RuntimeRoot 'provenance'
    $logsDir = Join-Path $RuntimeRoot 'logs'
    $command = @($ScientificPython, '-u', $ScientificPipeline, '--gata-root', $GitRoot, '--modulec-datos', $ModuleCDataRoot, '--inc-new', $IncendiosRoot, '--output-root', $RuntimeRoot) -join ' '
    [IO.File]::WriteAllText((Join-Path $provenanceDir 'launcher_command.txt'), $command + [Environment]::NewLine)
    [IO.File]::WriteAllText((Join-Path $provenanceDir 'launcher_roots.tsv'), "role`tpath`nmodulec_data`t$ModuleCDataRoot`nportuguese_agencies`t$PortugueseAgenciesDataRoot`nrecovery`t$Recovery20152024Root`nincendios`t$IncendiosRoot`ngfas_effective`t$GfasRoot`nruntime`t$RuntimeRoot`n")
    & $ScientificPython -u $ScientificPipeline --gata-root $GitRoot --modulec-datos $ModuleCDataRoot --inc-new $IncendiosRoot --output-root $RuntimeRoot 1> (Join-Path $logsDir 'scientific_stdout.txt') 2> (Join-Path $logsDir 'scientific_stderr.txt')
    $scientificExit = $LASTEXITCODE
    [IO.File]::WriteAllText((Join-Path $logsDir 'launcher_stdout.txt'), "mode=Full`n$command`n")
    if ($scientificExit -ne 0) { throw "CANONICAL_FULL_RUNTIME_FAILED: exit=$scientificExit" }
    exit 0
}

& python -u $SmokerunScript `
    --mode ($Mode.ToLowerInvariant()) `
    --repo-root $GitRoot `
    --code-root $RepoRoot `
    --modulec-data-root $ModuleCDataRoot `
    --portuguese-agencies-root $PortugueseAgenciesDataRoot `
    --recovery-2015-2024-root $Recovery20152024Root `
    --incendios-root $IncendiosRoot `
    --gfas-root $GfasRoot `
    --runtime-root $RuntimeRoot `
    --semantic-contract $SemanticContract `
    --semantic-contract-tsv $SemanticContractTsv `
    --canonical-config $CanonicalConfig `
    --expected-head-sha $ExpectedHeadSha `
    --guard-script $GuardScript `
    --launcher-path $LauncherPath `
    --cleared-environment ($cleared -join "`n")
if ($LASTEXITCODE -ne 0) { throw "CANONICAL_STRUCTURAL_RUN_FAILED: exit=$LASTEXITCODE" }
