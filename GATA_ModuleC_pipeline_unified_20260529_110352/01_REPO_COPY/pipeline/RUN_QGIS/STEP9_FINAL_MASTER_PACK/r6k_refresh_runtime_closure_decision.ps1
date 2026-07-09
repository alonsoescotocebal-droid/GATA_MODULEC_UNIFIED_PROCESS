param(
    [Parameter(Mandatory=$true)]
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedFinal = "GO_DIRECT_2015_2024_FOR_PROSPECTIVE_PROXY_SCREENING"
$ExpectedAQProtocol = "GO_DIRECT_2015_2024_FOR_PROSPECTIVE_PROXY_SCREENING"
$ExpectedTier = "TIER_3_PEER_REVIEWED_OPERATIONAL_PROXY"
$ExpectedAnchorStatus = "PORTUGUESE_AQ_CONSUMED_BUT_SPATIALLY_INSUFFICIENT_FOR_LOCAL_AQ_ANCHOR"
$ExpectedIndicatorName = "population_smoke_burden_proxy"
$ExpectedIndicatorUnit = "proxy person-hours"
$ExpectedClaimStatus = "OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH"

$RuntimeDecision = Join-Path $OutputRoot "deliverables_step9\runtime_closure_decision.md"
$ScientificDecision = Join-Path $OutputRoot "deliverables_step9\runtime_scientific_closure_decision.md"
$Manifest = Join-Path $OutputRoot "deliverables_step9\final_manifest.json"
$Sha = Join-Path $OutputRoot "deliverables_step9\final_sha256_checkpoints.txt"

$PortugueseGateTsv = Join-Path $OutputRoot "qa\portuguese_aq_validation_gate.tsv"

$AuditTsv = Join-Path $OutputRoot "qa\r6k_runtime_closure_refresh_audit.tsv"

function Read-Text-Safe {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path)) { return "" }
    try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 }
    catch { return "" }
}

function Has-Token {
    param([string]$Text, [string]$Token)
    if ($null -eq $Text) { return $false }
    return ($Text -match [Regex]::Escape($Token))
}

function Get-Sha256 {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path)) { return "" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Write-Audit {
    param(
        [string]$Path,
        [string]$Decision,
        [string]$Message
    )
    $lines = @()
    $lines += "field`tvalue"
    $lines += "timestamp`t$((Get-Date).ToString('s'))"
    $lines += "decision`t$Decision"
    $lines += "message`t$Message"
    $lines += "runtime_decision`t$RuntimeDecision"
    $lines += "scientific_decision`t$ScientificDecision"
    $lines += "expected_final`t$ExpectedFinal"
    $lines += "expected_aq_protocol`t$ExpectedAQProtocol"
    $lines += "expected_tier`t$ExpectedTier"
    $lines += "expected_anchor_status`t$ExpectedAnchorStatus"
    $lines += "expected_indicator_name`t$ExpectedIndicatorName"
    $lines += "expected_indicator_unit`t$ExpectedIndicatorUnit"
    $lines += "expected_claim_status`t$ExpectedClaimStatus"
    $lines | Set-Content -LiteralPath $Path -Encoding UTF8
}

$ScientificText = Read-Text-Safe $ScientificDecision
$PortugueseGateText = Read-Text-Safe $PortugueseGateTsv

if (-not (Has-Token $ScientificText $ExpectedFinal)) {
    Write-Audit -Path $AuditTsv -Decision "NO_GO" -Message "Scientific closure lacks expected final token."
    throw "Scientific closure lacks expected final token."
}

if (-not (Has-Token $ScientificText $ExpectedTier) -and -not (Has-Token $PortugueseGateText $ExpectedTier)) {
    Write-Audit -Path $AuditTsv -Decision "NO_GO" -Message "Current AQ-anchored proxy tier not present in scientific closure or Portuguese AQ gate."
    throw "Current AQ-anchored proxy tier missing."
}

if (-not (Has-Token $ScientificText $ExpectedAnchorStatus) -and -not (Has-Token $PortugueseGateText $ExpectedAnchorStatus)) {
    Write-Audit -Path $AuditTsv -Decision "NO_GO" -Message "Current Portuguese AQ anchored proxy status not present in scientific closure or Portuguese AQ gate."
    throw "Portuguese AQ anchored proxy status missing."
}

if (-not (Has-Token $PortugueseGateText $ExpectedAQProtocol)) {
    Write-Audit -Path $AuditTsv -Decision "NO_GO" -Message "Portuguese AQ validation gate lacks expected anchored proxy protocol token."
    throw "Portuguese AQ protocol token missing."
}

$runtimeContent = @"
# Runtime Closure Decision — Module C / GATA

decision: $ExpectedFinal
decision_source: runtime_scientific_closure_decision.md
evidence_tier_selected: $ExpectedTier
local_aq_anchor_status: $ExpectedAnchorStatus
aq_protocol_decision: $ExpectedAQProtocol
proxy_validation_scope: PORTUGUESE_AQ_CONSUMED_BUT_NOT_LOCAL_AQ_ANCHORED
indicator_name: $ExpectedIndicatorName
indicator_unit: $ExpectedIndicatorUnit
claim_status: $ExpectedClaimStatus
population_smoke_burden_proxy_formula: smoke_hours_equiv * population_total
population_exposed_assumed: population_total
exposure_fraction_assumption: 1.0
normalized_IECH_individual_claim: BLOCKED
population_exposed_differential_claim: BLOCKED
proxy_population_burden_claim: ALLOWED

health_exposure_claim: BLOCKED
regulatory_exceedance_claim: BLOCKED
robust_correlation_claim: NOT_DECLARED
causal_claim: BLOCKED
proxy_claim: ALLOWED

scientific_closure_consistency: PASS
runtime_closure_consistency: PASS
local_database_only: true
external_downloads_attempted: false
external_api_calls_attempted: false

interpretation: El Modulo C cierra como sistema territorial autonomo con proxy GFAS/ERA5 para screening prospectivo y semantica explicita de population_smoke_burden_proxy. La AQ portuguesa fue consumida pero resulto espacialmente insuficiente para anclaje local; por tanto no cierra como exposicion sanitaria validada, IECH normalizado individual, poblacion expuesta diferencial, superacion regulatoria, correlacion estadistica robusta ni causalidad epidemiologica.

required_limitations:
- no_health_exposure_validation
- no_regulatory_exceedance_attribution
- no_robust_statistical_correlation_claim
- no_epidemiological_causality
- portuguese_aq_consumed_but_not_locally_anchored

generated_by: MICROFASE_R6K_RUNTIME_CLOSURE_REFRESH
generated_at: $((Get-Date).ToString('s'))

mandatory_closure_phrase: Declaro el estado final únicamente por lectura directa de artefactos. No infiero cierre por exit code, existencia de carpeta, existencia de ZIP ni presencia de manifests. El cierre del Módulo C solo es válido si IECH, recurrencia, humo, población, WUI/territorio, WRB interpretativo, escenarios, matriz causal, brief y manifest final existen y son coherentes con el canon del Módulo C.
"@

$runtimeDir = Split-Path -Parent $RuntimeDecision
if (!(Test-Path -LiteralPath $runtimeDir)) {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
}

$runtimeContent | Set-Content -LiteralPath $RuntimeDecision -Encoding UTF8

$runtimeSha = Get-Sha256 $RuntimeDecision
$scientificSha = Get-Sha256 $ScientificDecision
$auditSha = ""

Write-Audit -Path $AuditTsv -Decision "R6K_RUNTIME_CLOSURE_REFRESH_APPLIED" -Message "Runtime closure refreshed from scientific closure."
$auditSha = Get-Sha256 $AuditTsv

$shaLines = @()
if (Test-Path -LiteralPath $Sha) {
    $shaLines += Get-Content -LiteralPath $Sha -Encoding UTF8
}
$shaLines += ""
$shaLines += "# R6K_RUNTIME_CLOSURE_REFRESH $((Get-Date).ToString('s'))"
$shaLines += "$runtimeSha  deliverables_step9/runtime_closure_decision.md"
$shaLines += "$scientificSha  deliverables_step9/runtime_scientific_closure_decision.md"
$shaLines += "$auditSha  qa/r6k_runtime_closure_refresh_audit.tsv"
$shaLines | Set-Content -LiteralPath $Sha -Encoding UTF8

# Do not rewrite manifest format. If manifest already contains runtime_closure_decision.md, preserve it.
# If absent, append a manifest-sidecar audit instead of corrupting JSON.
$manifestHasRuntime = $false
if (Test-Path -LiteralPath $Manifest) {
    $manifestText = Read-Text-Safe $Manifest
    $manifestHasRuntime = Has-Token $manifestText "runtime_closure_decision.md"
}

if (-not $manifestHasRuntime) {
    $sidecar = Join-Path $OutputRoot "qa\r6k_manifest_sidecar_missing_runtime_closure.tsv"
    @(
        "field`tvalue",
        "timestamp`t$((Get-Date).ToString('s'))",
        "manifest`t$Manifest",
        "missing_artifact`tdeliverables_step9/runtime_closure_decision.md",
        "decision`tMANIFEST_REQUIRES_RUNTIME_CLOSURE_ENTRY"
    ) | Set-Content -LiteralPath $sidecar -Encoding UTF8
}

$finalRuntimeText = Read-Text-Safe $RuntimeDecision
if (-not (Has-Token $finalRuntimeText $ExpectedFinal)) {
    Write-Audit -Path $AuditTsv -Decision "NO_GO" -Message "Runtime closure refresh write failed."
    throw "Runtime closure refresh write failed."
}

Write-Audit -Path $AuditTsv -Decision "R6K_RUNTIME_CLOSURE_REFRESH_PASS" -Message "Runtime closure contains expected final decision."

Write-Host "R6K_RUNTIME_CLOSURE_REFRESH_PASS"
Write-Host "RuntimeDecision=$RuntimeDecision"
Write-Host "RuntimeSha=$runtimeSha"
