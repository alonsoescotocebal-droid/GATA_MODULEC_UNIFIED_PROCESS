# SCIENTIFIC THRESHOLD DECLARATION REGISTER - MODULE C / IECH

Status: CANONICAL THRESHOLD LAW FOR CODEX IMPLEMENTATION  
Version: 2026-05-22 (reanchored in canonical GitHub repo)

## Purpose
This register defines the scientific/documentary threshold contract used by Module C.  
Scientific closure must not be inferred from ZIP existence, manifest existence, `exit code 0`, `qa_flag=OK`, or `missing_components=0`.

## Non-negotiable rule
`NO CODE ADEQUACY PHASE MAY START` until this threshold register is integrated as machine-readable + human-readable gate outputs.

If threshold definitions or required variables are missing in critical IECH/smoke/population/recurrence components, the scientific decision must be:
- `NO-GO_SCIENTIFIC_THRESHOLD`

## Mandatory gate states
- `THRESHOLD_DEFINED_AS_OFFICIAL_HEALTH_STANDARD`
- `THRESHOLD_DEFINED_AS_OFFICIAL_ENVIRONMENTAL_OPERATIONAL_STANDARD`
- `THRESHOLD_DEFINED_AS_INDEXED_METHOD`
- `THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION`
- `THRESHOLD_DEFINED_AS_SCENARIO_ASSUMPTION`
- `BLOCKED_FOR_THRESHOLD_DEFINITION`
- `BLOCKED_FOR_REQUIRED_VARIABLE`
- `BLOCKED_FOR_SPATIAL_DIFFERENTIATION`
- `BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM`
- `BLOCKED_FOR_CAUSAL_CLAIM`
- `NO-GO_SCIENTIFIC_THRESHOLD`

## Core threshold rules (enforced by gate contract)
1. Smoke spatial differentiation:
   - if `count_unique(smoke_days across units by year) <= 1` then `BLOCKED_SPATIAL_SMOKE_CLAIM`
2. Health exposure:
   - only official pollutant concentration thresholds (WHO/EPA/EU) can authorize health exposure claims
   - proxy-only smoke sources -> `BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM`
3. IECH ranking:
   - if `count_unique(IECH_mean_2015_2024 across units) <= 1` then `BLOCKED_IECH_RANKING`
4. Causal matrix:
   - if any critical driver has `BLOCKED_*`, scientific closure cannot be GO
5. Brief claim mapping:
   - claims must be traceable to threshold IDs
   - forbidden claims remain blocked while blocking states are active

## Mandatory runtime outputs from scientific gate
- `03_outputs/qa/scientific_validation_gate.tsv`
- `03_outputs/qa/scientific_validation_gate.md`
- `03_outputs/qa/scientific_threshold_evidence_register.tsv`
- `03_outputs/qa/blocked_claims_register.tsv`
- `03_outputs/qa/causal_matrix_scientific_gate_audit.tsv`
- `03_outputs/qa/brief_claim_scientific_gate_audit.tsv`
- `03_outputs/deliverables_step9/runtime_scientific_closure_decision.md`

## Scientific decision model
Two decisions are independent:
- `OPERATIONAL_CLOSURE = GO / GO_WITH_PATCHES / HOLD / NO-GO`
- `SCIENTIFIC_THRESHOLD_CLOSURE = GO / HOLD / NO-GO_SCIENTIFIC_THRESHOLD`

Scientific `NO-GO_SCIENTIFIC_THRESHOLD` can coexist with operational path/packaging pass when explicitly documented.

## Minimum source register (for traceability)
- `SRC-WHO-AQG-2021` (WHO Air Quality Guidelines 2021)
- `SRC-EPA-AQI-2026` (US EPA AQI breakpoints)
- `SRC-EU-AAQD-2024` (EU revised Ambient Air Quality Directive context)
- `SRC-GHSL-POP-2023` (JRC GHSL population)
- `SRC-WUI-NATURE-2023` (global WUI definition)
- `SRC-SOILGRIDS-2021` (SoilGrids 2.0 methodological support)

## Required implementation statement
I declare scientific closure only through the Scientific Threshold Declaration Register and direct reading of artifacts. I do not infer scientific closure from exit code, ZIP existence, manifest existence, qa_flag=OK, or missing_components=0.
