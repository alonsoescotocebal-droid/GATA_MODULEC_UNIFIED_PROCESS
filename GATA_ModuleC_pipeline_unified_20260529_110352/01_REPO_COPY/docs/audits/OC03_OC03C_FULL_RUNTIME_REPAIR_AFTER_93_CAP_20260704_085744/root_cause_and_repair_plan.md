# OC03/OC03C Full Runtime Repair Plan After 93-Day Cap

## 1. Current repo status and SHA/branch evidence

- `RepoRoot`: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- `Branch`: `codex/add-oc03c-aq-validation`
- `HEAD`: `b9950ac0a755a01e3f1bd5035f74667761ced7e3`
- `config/module_c_canonical_paths.json` still declares `EXPECTED_BASE_SHA=adee1226ec0df7d0d052d0a0b146daba8ce0c0cb`.
- The working tree is dirty in the OC03/OC03C repair files and related tests. This runtime attempt must use the current filesystem state, not the stale canonical SHA expectation.

## 2. Confirmation that the 93-day hard cap was read from code

- The prior audit at `docs/audits/OC03_GFAS_93_DAY_LIMIT_ROOT_CAUSE_AUDIT_20260629_120000.md` correctly identified the former hard cap in `_planned_pm_message_count`.
- Current code in `pipeline/moduleC_pipeline_v2.py` no longer returns `max(1, min(93, planned))`.
- Current `_planned_pm_message_count(message_count, pm_stride)` returns the derived annual planned count and raises `NO-GO_GFAS_PM2P5FIRE_MESSAGE_COUNT_NOT_DETERMINED` if count/stride are invalid.
- Current `_fallback_gfas_pm_rows_from_gribs()` derives `message_count` from GRIB message enumeration and no longer fabricates `"93"`.
- Current `_decode_gfas_pm_payload_to_unit_rows()` uses `_resolve_gfas_pm_date()` so a one-day-late `GRIB_VALID_TIME` no longer shifts emitted rows into `2015-01-02 .. 2025-01-01`.

## 3. Hypothesis for expected repaired coverage

- Expected repaired smoke temporal coverage is annual daily GFAS PM2P5FIRE coverage for `2015-01-01` through `2024-12-31`.
- Expected annual date counts if the product is complete:
  - `2015:365`
  - `2016:366`
  - `2017:365`
  - `2018:365`
  - `2019:365`
  - `2020:366`
  - `2021:365`
  - `2022:365`
  - `2023:365`
  - `2024:366`
- Expected unique total dates: `3653`
- Expected unique years: `10`
- Expected unique units: `>=26`
- Expected daily rows: exact `date/unit` cardinality, not `24180`.

## 4. Exact files and functions to edit if another defect appears

- `pipeline/moduleC_pipeline_v2.py`
  - `_planned_pm_message_count`
  - `_fallback_gfas_pm_rows_from_gribs`
  - `_probe_gfas_pm_message_pattern`
  - `_resolve_gfas_pm_date`
  - `_decode_gfas_pm_payload_to_unit_rows`
  - `run_base_smoke_contract_for_oc03c`
- `pipeline/portuguese_aq_validation.py`
  - Only if Portuguese AQ final-state logic still ignores a blocked or incomplete base smoke contract.
- `pipeline/scientific_threshold_gate.py`
- `pipeline/validate_modulec_objectives_canon.py`
- `pipeline/qa_gate_v2.py`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/r6k_refresh_runtime_closure_decision.ps1`

## 5. Exact tests to update if another defect appears

- `tests/test_spatial_collapse_contracts.py`
- `tests/test_oc03_v13_recovery_contract.py`
- `tests/test_oc03c_blocks_degraded_smoke_runtime.py`
- `tests/test_oc03c_portuguese_aq_validation.py`
- `tests/test_inputs_resolved_traces_gfas_era5.py`
- `tests/test_oc03_v12_decoder_summary_fallback_contract.py`
- `tests/test_oc03_v13_decoder_grib_fallback.py`
- `tests/test_oc03_v13_scientific_gate_recovery_path.py`
- `tests/test_smoke_route_selector_prefers_gfas_era5.py`
- `tests/test_manifest_recursive_audit.py`

## 6. Exact runtime command to execute after tests

```powershell
cd "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\OC03_OC03C_FULL_REPAIR_$stamp"

& "C:\OSGeo4W64\bin\python-qgis-ltr.bat" `
  "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py" `
  --gata-root "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" `
  --modulec-datos "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" `
  --inc-new "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version" `
  --output-root "$out"
```

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
- `qa/scientific_validation_gate.tsv`
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
- `brief/causal_matrix/causal_matrix_screening_nuts3.csv` or the manifest-equivalent causal-matrix CSV if naming differs
- `brief/causal_matrix/causal_matrix_narrative.md` or the manifest-equivalent causal-matrix narrative if naming differs
- `brief/Brief_Politica_IECH_2030.md`
- `deliverables_step9/runtime_closure_decision.md`
- `deliverables_step9/runtime_scientific_closure_decision.md`
- `deliverables_step9/final_manifest.json`
- `deliverables_step9/final_sha256_checkpoints.txt`
- `deliverables_step9/ModuleC_ALL_FINAL_deliverables.zip`

## 8. Decision rule for GO/HOLD/NO-GO/BLOCKED

- `GO` only if final artifacts directly prove:
  - no active `FAIL`, `HOLD`, or `BLOCKED`
  - no stale manifest/SHA/ZIP mismatch
  - smoke coverage spans `2015-01-01 .. 2024-12-31`
  - all years `2015-2024` are present
  - all months are present per year unless raw-data evidence documents a source gap
  - no forbidden smoke methods (`flat_single_anchor`, interpolation, extrapolation, V12-derived, resume-derived final route)
  - Portuguese AQ is interpreted only after a passing repaired base smoke contract
- `HOLD` if artifacts exist but any gate or artifact disagrees, or if warnings are semantically inconsistent with the final decision.
- `NO-GO` if the decoder cannot determine real annual PM2P5FIRE message counts or if smoke coverage remains incomplete without data-backed justification.
- `BLOCKED` only if an external execution dependency prevents a fresh full runtime after code/tests are otherwise ready.
