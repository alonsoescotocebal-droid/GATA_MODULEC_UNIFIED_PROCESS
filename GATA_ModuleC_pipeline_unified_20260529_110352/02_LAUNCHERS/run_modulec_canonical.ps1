[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('smoke')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$RuntimeId,
    [Parameter(Mandatory=$true)][string]$ModuleCDataRoot,
    [Parameter(Mandatory=$true)][string]$IncendiosRoot,
    [Parameter(Mandatory=$true)][string]$GfasRoot
)

$ErrorActionPreference = 'Stop'
$Container = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$GitRoot = (Resolve-Path (Join-Path $Container '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $Container '01_REPO_COPY')).Path
$RuntimeRoot = Join-Path (Join-Path $Container '03_RUNTIMES') $RuntimeId
$SemanticContract = Join-Path $RepoRoot 'contracts\MODULE_C_SEMANTIC_MINIMUM_V1.md'

if (Test-Path -LiteralPath $RuntimeRoot) { throw "BLOCKED_OUTPUT_ROOT_EXISTS: $RuntimeRoot" }
if (-not (Test-Path -LiteralPath $SemanticContract)) { throw "BLOCKED_SEMANTIC_CONTRACT_MISSING: $SemanticContract" }

& python -u (Join-Path $RepoRoot 'tools\modulec_structural_smokerun.py') `
    --repo-root $GitRoot `
    --code-root $RepoRoot `
    --modulec-data-root $ModuleCDataRoot `
    --incendios-root $IncendiosRoot `
    --gfas-root $GfasRoot `
    --runtime-root $RuntimeRoot `
    --semantic-contract $SemanticContract
if ($LASTEXITCODE -ne 0) { throw "STRUCTURAL_SMOKERUN_FAILED: exit=$LASTEXITCODE" }
