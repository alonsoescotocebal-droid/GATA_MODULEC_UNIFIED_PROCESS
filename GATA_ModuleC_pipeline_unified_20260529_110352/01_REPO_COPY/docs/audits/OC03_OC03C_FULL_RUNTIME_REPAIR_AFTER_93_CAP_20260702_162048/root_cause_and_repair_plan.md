# OC03/OC03C Full Runtime Repair Plan After GFAS 93-Day Cap

## 1. Current repo status and SHA/branch evidence

- RepoRoot: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- `git branch --show-current`: `codex/add-oc03c-aq-validation`
- `git rev-parse HEAD`: `b9950ac0a755a01e3f1bd5035f74667761ced7e3`
- `config/module_c_canonical_paths.json`:
  - `EXPECTED_BRANCH = codex/add-oc03c-aq-validation`
  - `EXPECTED_BASE_SHA = adee1226ec0df7d0d052d0a0b146daba8ce0c0cb`
- Worktree state at inspection:
  - modified pipeline/tests related to OC-03 and OC-03C
  - wrapper `run_full_oc03_oc03c_runtime.ps1` present
  - prior runtime roots under `03_RUNTIMES` exist but none are valid final closure evidence

## 2. Confirmation that the 93-day hard cap was read from code

Historical committed code was already verified to contain:

- `_planned_pm_message_count` with `return max(1, min(93, planned))`
- `_fallback_gfas_pm_rows_from_gribs` with fabricated `message_count = "93"`
- `decode_gfas_era5_gdal_proxy` breaking at `processed_pm >= planned_pm_messages`
- downstream OC-03C gate constants accepting `930` dates and `24180` rows

Current active worktree now shows the intended repair direction:

- `_planned_pm_message_count` returns the computed planned count and raises `NO-GO_GFAS_PM2P5FIRE_MESSAGE_COUNT_NOT_DETERMINED` on invalid metadata
- `_fallback_gfas_pm_rows_from_gribs` derives `message_count` from GRIB message enumeration instead of inventing `93`
- OC-03C base smoke contract uses dynamic temporal coverage checks and cardinality consistency

## 3. Hypothesis for expected repaired coverage

- The repaired direct GFAS route should decode full annual PM2P5FIRE coverage per year, not stop at day 93.
- Expected year counts if annual daily messages are present:
  - `2015: 364 or 365 depending on observed first valid direct date`
  - `2016: 366`
  - `2017: 365`
  - `2018: 365`
  - `2019: 365`
  - `2020: 366`
  - `2021: 365`
  - `2022: 365`
  - `2023: 365`
  - `2024: 366`
- The repaired runtime must prove:
  - all years `2015-2024` are present
  - all months are present per year unless source-backed missing days exist
  - `smoke_day_score_nuts3_daily.csv` row cardinality matches actual `date x unit` coverage
  - no `flat_single_anchor`, `interpolated_from_anchors`, or `extrapolated_from_anchors` final route

## 4. Exact files and functions to edit

If further repair is needed after tests/runtime evidence:

- `pipeline/moduleC_pipeline_v2.py`
  - `_fallback_gfas_pm_rows_from_gribs`
  - `_planned_pm_message_count`
  - `decode_gfas_era5_gdal_proxy`
  - `_compute_daily_smoke_temporal_coverage`
  - `write_gfas_era5_decoder_daily_spatial_audit`
  - `run_base_smoke_contract_for_oc03c`
- `pipeline/scientific_threshold_gate.py`
  - direct decoder contract evaluation
- `pipeline/validate_modulec_objectives_canon.py`
  - direct decoder contract and OC-03C gate consumption
- tests if any remaining fixture or assertion still normalizes `93`, `930`, or `24180`

## 5. Exact tests to update

Current relevant tests to validate or update if they fail:

- `tests/test_spatial_collapse_contracts.py`
- `tests/test_oc03_v13_recovery_contract.py`
- `tests/test_oc03c_blocks_degraded_smoke_runtime.py`
- `tests/test_oc03c_portuguese_aq_validation.py`
- then `python -m pytest -q tests`

The tests must prove:

- `_planned_pm_message_count` no longer caps broad annual counts at 93
- fallback does not synthesize `message_count=93`
- a 93-day runtime is blocked
- OC-03C base smoke contract is dynamic, not fixed at `930/24180`
- Portuguese AQ remains provisional when base smoke is regressed

## 6. Exact runtime command to execute after tests

Working directory:

`D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`

Wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_full_oc03_oc03c_runtime.ps1 -OutputRoot "<fresh_runtime_root>"
```

Underlying command:

```powershell
& 'C:\OSGeo4W64\bin\python-qgis-ltr.bat' `
  'D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py' `
  --gata-root 'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos' `
  --modulec-datos 'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos' `
  --inc-new 'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version' `
  --output-root '<fresh_runtime_root>'
```

Final validation constraints:

- no `--resume-post-smoke`
- no copied old `03_outputs`
- no V12-derived runtime

## 7. Exact final artifacts that must be read

- `qa/inputs_resolved.json`
- `qa/report_auditoria_v2.txt`
- `qa/run_log.txt`
- `qa/path_scope_guard_report.tsv`
- `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
- `qa/smoke_route_audit.tsv`
- `qa/oc03c_base_smoke_contract_gate.tsv`
- `qa/portuguese_aq_input_inventory.tsv`
- `qa/portuguese_aq_normalization_audit.tsv`
- `qa/portuguese_aq_validation_gate.tsv`
- `qa/gfas_era5_vs_portuguese_aq_concordance.tsv`
- `qa/objectives_canon_alignment_report.tsv`
- `qa/scientific_validation_gate.tsv` or exact generated equivalent
- `qa/QA_checks.csv`
- `qa/global_audit_status_scan.md`
- `qa/global_audit_status_scan.tsv`
- `tables/smoke_day_score_nuts3_daily.csv`
- `tables/smoke_days_unit_2015_2024.csv`
- `tables/smoke_day_score_municipio_daily.csv`
- `tables/smoke_days_municipio_2015_2024.csv`
- `tables/pop_unit_2015_2025_2030.csv`
- `tables/IECH_unit_2015_2024.csv`
- `tables/IECH_scenarios_2026_2030.csv`
- `brief/causal_matrix/causal_matrix_screening_nuts3.csv`
- `brief/causal_matrix/causal_matrix_narrative.md`
- `brief/Brief_Politica_IECH_2030.md`
- `deliverables_step9/runtime_closure_decision.md`
- `deliverables_step9/runtime_scientific_closure_decision.md`
- `deliverables_step9/final_manifest.json`
- `deliverables_step9/final_sha256_checkpoints.txt`
- `deliverables_step9/ModuleC_ALL_FINAL_deliverables.zip`

## 8. Decision rule for GO/HOLD/NO-GO/BLOCKED

- `GO`
  - only if the fresh runtime proves repaired smoke temporal coverage, downstream gates agree, and no final artifact contains unresolved `FAIL`, `HOLD`, `BLOCKED`, stale manifest/SHA/ZIP, warning inconsistency, or unsupported claim
- `HOLD`
  - if runtime completes but evidence remains internally inconsistent or some gate/package artifact is still unresolved
- `BLOCKED`
  - if the decoder cannot determine real PM2P5FIRE message count and emits `NO-GO_GFAS_PM2P5FIRE_MESSAGE_COUNT_NOT_DETERMINED`, or some external prerequisite prevents a meaningful full rerun
- `NO-GO`
  - if final artifacts still fail scientific, QA, or closure conditions after fresh rerun

Immediate sequence:

1. Run targeted tests on the active worktree.
2. If tests are clean, run a fresh full runtime from scratch with the wrapper.
3. Read final artifacts directly and only then decide closure state.
