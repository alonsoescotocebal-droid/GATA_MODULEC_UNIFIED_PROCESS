# 12. OBJECTIVES CANON — MODULE C IECH

## Scope
Canonical objectives for the full closure of Module C (IECH), including scientific, documentary, and runtime reproducibility requirements.

## Runtime Rule
Do not declare `GO` from technical runtime pass only. Closure requires objective-level evidence for OC-01..OC-12 from fresh artifacts produced in current execution.

## OC-01 Territorial Base (NUTS3 + Municipio)
- Required DB: GISCO NUTS 2024 LEVL_3, CAOP 2024.1 Continente.
- Required outputs:
  - `03_outputs/maps/IECH_ModuleC_master.gpkg`
  - `03_outputs/qa/territorial_units_validation.tsv`
  - `03_outputs/tables/municipio_unit_map.csv`
- Validation: non-empty units, valid CRS/geometries, municipio→NUTS3 mapping resolved.

## OC-02 Fire + Recurrence 2015-2024
- Required DB: annual `ardida_YYYY_TM06.gpkg` (2015..2024) from `Incendios_Nueva version`.
- Required outputs:
  - `03_outputs/tables/recurrence_unit_2015_2024.csv`
  - `03_outputs/tables/recurrence_municipio_2015_2024.csv`
  - `03_outputs/qa/fire_ingestion_audit.tsv`

## OC-03 Smoke Route (v0/v1 declared)
- Current expected route in this repo: v0 primary/provisional from Parquet anchors.
- Required outputs:
  - `03_outputs/tables/smoke_days_unit_2015_2024.csv`
  - `03_outputs/tables/smoke_days_municipio_2015_2024.csv`
  - `03_outputs/qa/smoke_route_audit.tsv`
- Rule: reject legacy smoke source under `03_outputs/tables` as primary input.

## OC-04 Population GHSL
- Required DB: GHSL POP 2015/2020/2025/2030.
- Required outputs:
  - `03_outputs/tables/pop_unit_2015_2025_2030.csv`
  - `03_outputs/tables/pop_municipio_2015_2025_2030.csv`
  - `03_outputs/qa/population_zonal_audit.tsv`

## OC-05 IECH Historical 2015-2024
- Required outputs:
  - `03_outputs/tables/IECH_unit_2015_2024.csv`
  - `03_outputs/tables/IECH_unit_2015_2024_mean.csv`
  - `03_outputs/tables/IECH_municipio_2015_2024.csv`
  - `03_outputs/tables/IECH_municipio_2015_2024_mean.csv`
  - `03_outputs/qa/iech_calculation_audit.tsv`

## OC-06 Recurrence Classification
- Required outputs:
  - `03_outputs/tables/recurrence_unit_2015_2024.csv`
  - `03_outputs/tables/recurrence_municipio_2015_2024.csv`
  - `03_outputs/qa/recurrence_classification_audit.tsv`

## OC-07 WUI / Territorial Context
- Required outputs:
  - `03_outputs/tables/territorial_context_nuts3.csv`
  - `03_outputs/tables/territorial_context_municipio.csv`
  - `03_outputs/qa/territorial_variables_audit.tsv`

## OC-08 WRB Context Integration
- Required DB: `WRB_MostProbable_TM06.tif` (+ lookup when available).
- Required outputs:
  - `03_outputs/tables/wrb_context_nuts3.csv`
  - `03_outputs/tables/wrb_context_municipio.csv`
  - `03_outputs/qa/wrb_integration_audit.tsv`
  - `03_outputs/brief/wrb_summary_for_policy_brief.md`
- Rule: WRB is contextual/edaphic descriptor, not direct causal fire driver.

## OC-09 Substantive Causal Matrix
- Required outputs:
  - `03_outputs/brief/causal_matrix/causal_matrix_IECH_NUTS3.csv`
  - `03_outputs/brief/causal_matrix/causal_matrix_IECH_NUTS3.json`
  - `03_outputs/brief/causal_matrix/causal_matrix_IECH_NUTS3.txt`
  - `03_outputs/brief/causal_matrix/causal_matrix_IECH_municipio.csv`
  - `03_outputs/brief/causal_matrix/causal_matrix_audit.tsv`
  - `03_outputs/brief/causal_matrix/causal_matrix_sha256_checkpoints.txt`
- Rule: no `qa_flag=HOLD` and no unresolved `missing_components` for GO.

## OC-10 Scenarios S0/S1 2026-2030
- Required outputs:
  - `03_outputs/tables/IECH_scenarios_2026_2030.csv`
  - `03_outputs/tables/IECH_scenarios_unit_2026_2030_mean.csv`
  - `03_outputs/tables/IECH_scenarios_municipio_2026_2030.csv`
  - `03_outputs/tables/IECH_scenarios_municipio_2026_2030_mean.csv`
  - `03_outputs/qa/scenario_assumptions.md`
  - `03_outputs/qa/scenario_audit.tsv`

## OC-11 Policy Brief
- Required output:
  - `03_outputs/brief/Brief_Politica_IECH_2030.md`
- Rule: no placeholder text; include limitations and linkage to canonical objectives.

## OC-12 Reproducible Technical Closure
- Required outputs:
  - `03_outputs/qa/inputs_resolved.json`
  - `03_outputs/qa/run_log.txt`
  - `03_outputs/qa/QA_checks.csv`
  - `03_outputs/qa/report_auditoria_v2.txt`
  - `03_outputs/qa/preflight_report.txt`
  - `03_outputs/qa/objectives_canon_alignment_report.tsv`
  - `03_outputs/qa/objectives_canon_alignment_report.md`
  - `03_outputs/deliverables_step9/final_manifest.json`
  - `03_outputs/deliverables_step9/final_sha256_checkpoints.txt`
  - `03_outputs/deliverables_step9/ModuleC_ALL_FINAL_deliverables.zip`
  - `03_outputs/deliverables_step9/runtime_closure_decision.md`

## Decision Policy
- `GO`: all OC-01..OC-12 validated with coherent fresh artifacts and clean repo state.
- `HOLD`: correctable integration gaps remain (WRB/WUI/causal/brief/objectives gate/packaging).
- `NO-GO`: critical scientific/runtime failure (no IECH/smoke/pop/fire base or non-reproducible runtime).
- `BLOCKED`: unavoidable environment/permission/data-access blocker not solvable by code.

