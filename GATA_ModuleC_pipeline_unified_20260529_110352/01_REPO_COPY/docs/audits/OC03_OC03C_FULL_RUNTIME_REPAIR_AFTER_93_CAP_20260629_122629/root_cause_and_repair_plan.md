# OC03/OC03C Full Runtime Repair Plan After GFAS 93-Day Cap

## 1. Current repo status and SHA/branch evidence

- Repo root: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- `git branch --show-current`: `codex/add-oc03c-aq-validation`
- `git rev-parse HEAD`: `b9950ac0a755a01e3f1bd5035f74667761ced7e3`
- `git status --short`:
  - `?? audit_gfas_grib_month_coverage.py`
  - `?? audit_gfas_grib_month_coverage_v2.py`
  - `?? docs/audits/OC03_GFAS_93_DAY_LIMIT_ROOT_CAUSE_AUDIT_20260629_120000.md`
  - `?? run_gfas_grib_month_coverage_audit.ps1`
  - `?? run_gfas_grib_month_coverage_audit_v2.ps1`
- Canonical config evidence from `config/module_c_canonical_paths.json`:
  - `EXPECTED_BRANCH = codex/add-oc03c-aq-validation`
  - `EXPECTED_BASE_SHA = adee1226ec0df7d0d052d0a0b146daba8ce0c0cb`
- Immediate implication:
  - The active tree is on the expected branch.
  - The active HEAD is newer/different than the baseline SHA declared by config and must be reported exactly in later audits.

## 2. Confirmation that the 93-day hard cap was read from code

Confirmed by direct code reading in `pipeline/moduleC_pipeline_v2.py`:

- `_planned_pm_message_count`:
  - `planned = (total + stride - 1) // stride`
  - `return max(1, min(93, planned))`
- `decode_gfas_era5_gdal_proxy`:
  - computes `planned_pm_messages = _planned_pm_message_count(message_count, pm_stride)`
  - breaks the decode loop when `processed_pm >= planned_pm_messages`
- `_fallback_gfas_pm_rows_from_gribs`:
  - fabricates `message_count = "93"` when summary metadata are missing
- `run_base_smoke_contract_for_oc03c`:
  - still treats `daily_rows = 24180` and `unique_dates = 930` as a passing OC-03C base smoke contract

This confirms the root cause remains code-level and contract-level, not just an artifact in prior runtimes.

## 3. Hypothesis for expected repaired coverage

- The repaired direct GFAS route must use the real annual PM2P5FIRE daily coverage per year, not a fixed `93`.
- If annual daily data are present, expected decoded day counts should approximate:
  - `2015=365`
  - `2016=366`
  - `2017=365`
  - `2018=365`
  - `2019=365`
  - `2020=366`
  - `2021=365`
  - `2022=365`
  - `2023=365`
  - `2024=366`
- If any year/month has fewer days, the runtime must show that as source-backed coverage evidence, not as a silent code cap.
- The repaired smoke contract must therefore validate:
  - all years `2015-2024`
  - all 12 months per year unless source evidence documents missing months
  - dynamic `daily_rows` consistent with `unique_dates x unique_units`
  - no forbidden smoke reconstruction methods

## 4. Exact files and functions to edit

Primary code repair:

- `pipeline/moduleC_pipeline_v2.py`
  - `_fallback_gfas_pm_rows_from_gribs`
  - `_load_gfas_pm_summary_rows`
  - `_planned_pm_message_count`
  - `write_gfas_era5_decoder_daily_spatial_audit`
  - `_write_oc03_base_smoke_contract_report`
  - `run_base_smoke_contract_for_oc03c`

Downstream smoke-contract alignment:

- `pipeline/scientific_threshold_gate.py`
  - `evaluate_direct_decoder_contract`
- `pipeline/validate_modulec_objectives_canon.py`
  - `_check_oc03_v13_direct_contract`

Potential warning-semantics alignment if runtime confirms the issue:

- `pipeline/portuguese_aq_validation.py`
  - normalization audit rows around `station_metadata_files_normalized`
  - keep AQ blocked/provisional until repaired base smoke contract passes

Current review indicates `pipeline/qa_gate_v2.py`, `pipeline/smoke_route_selector.py`, `pipeline/scientific_threshold_gate.py`, and `pipeline/path_scope_guard.py` do not create the 93-day cap themselves, but some of them consume the resulting smoke contract and must remain aligned after the repair.

## 5. Exact tests to update

Must update:

- `tests/test_spatial_collapse_contracts.py`
  - remove assertions that `_planned_pm_message_count(...) == 93`
- `tests/test_oc03c_portuguese_aq_validation.py`
  - replace `930/24180/range(93)` valid-runtime fixtures with annual-coverage fixtures
  - keep degraded runtime blocked
- `tests/test_oc03c_blocks_degraded_smoke_runtime.py`
  - keep 93-day runtime blocked as regression evidence
- `tests/test_oc03_v13_recovery_contract.py`
  - remove `unique_dates=930` as the passing direct contract
- `tests/test_oc03_v13_decoder_grib_fallback.py`
  - stop expecting fabricated `message_count == "93"`
- `tests/test_oc03_v13_scientific_gate_recovery_path.py`
  - stop treating `unique_dates=930` as sufficient direct coverage

Likely fixture-only alignment:

- `tests/test_inputs_resolved_traces_gfas_era5.py`
- `tests/test_smoke_route_selector_prefers_gfas_era5.py`

These two do not define the smoke contract, but any unrealistic `message_count=93` fixture should be reviewed so it does not accidentally re-normalize the old cap.

## 6. Exact runtime command to execute after tests

Working directory:

`D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`

Command pattern to use after the isolated tests pass:

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\OC03_OC03C_FULL_REPAIR_$stamp"

& "C:\OSGeo4W64\bin\python-qgis-ltr.bat" `
  "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py" `
  --gata-root "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" `
  --modulec-datos "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" `
  --inc-new "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version" `
  --output-root "$out"
```

Constraints for the final validation attempt:

- no `--resume-post-smoke`
- no copied old `03_outputs`
- no reuse of prior runtime as final validator

## 7. Exact final artifacts that must be read

The fresh runtime must be audited by direct reading of:

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
- `qa/scientific_threshold_gate.tsv` or the runtime’s generated scientific gate equivalent if the actual filename is `scientific_validation_gate.tsv`
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

## 8. Decision rule for GO / HOLD / NO-GO / BLOCKED

- `GO`
  - only if the fresh runtime shows repaired annual GFAS coverage, OC-03/OC-03C gates agree, no forbidden smoke methods appear, and no final artifact contains unresolved `FAIL`, `HOLD`, `BLOCKED`, stale manifest/SHA/ZIP, or unsupported claims.
- `HOLD`
  - if the runtime completes but leaves unresolved audit/gate inconsistencies or warning semantics that still need repair.
- `BLOCKED`
  - if the code can no longer determine the real PM2P5FIRE message count and emits the explicit blocker `NO-GO_GFAS_PM2P5FIRE_MESSAGE_COUNT_NOT_DETERMINED`, or if required runtime inputs are unavailable.
- `NO-GO`
  - if the repaired direct route still fails the scientific/QA/global-audit closure conditions, or if final outputs make unsupported health/causal/closure claims.

Immediate implementation strategy:

1. Remove the 93-message cap and fabricated fallback counts.
2. Upgrade the decoder/base-smoke audits to emit month/year coverage evidence.
3. Make all downstream direct-coverage gates consume the new dynamic evidence instead of `930/24180`.
4. Keep Portuguese AQ blocked/provisional until the repaired base smoke contract passes.
5. Run the isolated tests.
6. Run a fresh full runtime from scratch.
7. Read every final artifact directly before declaring any closure state.
