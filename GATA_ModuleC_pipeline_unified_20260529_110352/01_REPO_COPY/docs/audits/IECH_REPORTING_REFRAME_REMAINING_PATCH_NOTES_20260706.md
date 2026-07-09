# IECH Reporting Reframe Remaining Patch Notes

## Partial state confirmed

The current worktree already contains a partial semantic migration in:

- `pipeline/moduleC_pipeline_v2.py`
- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`

Confirmed current additions:

- canonical proxy columns in historical/scenario IECH tables
- legacy `IECH` retained for compatibility
- `claim_status = OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH`
- `legacy_IECH_label_deprecated = population_smoke_burden_proxy`
- `qa/iech_reporting_reframe_audit.tsv` generation in Step7
- canonical proxy fields propagated into the causal matrix payload

## Remaining code edits still required

### `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`

The brief section still contains legacy wording and must be updated:

- `# Brief de Política IECH 2030`
- `Objetivo Módulo C: integración IECH histórica...`
- `## Definición IECH`
- `## Resultados IECH histórico`
- `IECH municipal disponible`

Required rewrite:

- state that the operative metric is `population_smoke_burden_proxy`
- keep `IECH` only as legacy label
- state `population_exposed_assumed = population_total`
- state `exposure_fraction_assumption = 1.0`
- block normalized/individual/health claims

### `pipeline/scientific_threshold_gate.py`

Still legacy:

- `evaluate_iech_ranking()` reads only `IECH_mean_2015_2024`
- `evaluate_population_cancellation()` only checks `IECH` vs `smoke_hours_equiv`
- closure token is still `GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL`
- brief forbidden phrases do not include normalized/differential IECH claim blocking

Required rewrite:

- prefer `population_smoke_burden_proxy_mean_2015_2024`, fallback to legacy mean
- treat `population_smoke_burden_proxy == expo_person_hours` plus proxy claim status as operational proxy, not a failure
- add forbidden patterns for normalized IECH / individual IECH / differential exposed population
- write final closure token `GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_AND_POPULATION_BURDEN_SEMANTICS`
- include proxy burden semantics in `runtime_scientific_closure_decision.md`

### `pipeline/qa_gate_v2.py`

Still missing:

- `qa/iech_reporting_reframe_audit.tsv` in required artifacts
- semantic hold checks for `IECH_REPORTING_REFRAME_STATUS`
- claim-status verification for proxy-burden semantics
- brief forbidden-claim scan for normalized/health wording

### `pipeline/validate_modulec_objectives_canon.py`

Still legacy:

- OC-05 validation rule text
- `_v10b_iech_non_degenerate()` only scans legacy IECH mean columns
- OC-05 status remains plain `PASS`

Required rewrite:

- verify `qa/iech_reporting_reframe_audit.tsv`
- prefer canonical proxy mean columns
- emit `PASS_WITH_PROXY_BURDEN_SEMANTICS` for OC-05

### `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/r6k_refresh_runtime_closure_decision.ps1`

Still legacy:

- `$ExpectedFinal = "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL"`
- runtime closure text still declares only AQ-anchored proxy protocol

Required rewrite:

- final token `GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_AND_POPULATION_BURDEN_SEMANTICS`
- preserve AQ protocol token separately
- add:
  - `indicator_name: population_smoke_burden_proxy`
  - `indicator_unit: proxy person-hours`
  - `claim_status: OPERATIONAL_POPULATION_BURDEN_PROXY_NOT_NORMALIZED_IECH`
  - `population_smoke_burden_proxy_formula: smoke_hours_equiv * population_total`
  - `population_exposed_assumed: population_total`
  - `exposure_fraction_assumption: 1.0`
  - `normalized_IECH_individual_claim: BLOCKED`
  - `population_exposed_differential_claim: BLOCKED`
  - `proxy_population_burden_claim: ALLOWED`

### `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`

Still missing:

- `qa/iech_reporting_reframe_audit.tsv` in `requiredRel`

### Tests still required

Missing new files:

- `tests/test_iech_reporting_reframe_no_calc_change.py`
- `tests/test_iech_population_smoke_burden_proxy_columns.py`
- `tests/test_iech_claims_block_normalized_and_health.py`
- `tests/test_iech_legacy_columns_deprecated.py`

Also existing tests likely need updates:

- `tests/test_oc03_v12_iech_proxy_contract.py`
- `tests/test_iech_blocks_population_cancellation.py`

## Current blocking condition

Edits to existing files are currently blocked by environment/tooling failure:

- `apply_patch` on existing files fails with
  - `windows sandbox failed: helper_unknown_error: setup refresh had errors`
- elevated shell edits were later rejected by approval review with
  - `You've hit your usage limit`

## Next action when editing is restored

1. finish the five remaining code edits above
2. add/update the six IECH tests
3. run focused pytest
4. run IECH/WRB prevalidation
5. read prevalidation artifacts directly
6. run full runtime only if prevalidation passes
7. read final artifacts directly before any GO/HOLD decision
