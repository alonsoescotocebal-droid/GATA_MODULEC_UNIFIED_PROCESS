# OC03/OC03C Full Repair Final Audit

## 1. RepoRoot, branch, SHA

- `RepoRoot`: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- `Branch`: `codex/add-oc03c-aq-validation`
- `Current SHA`: `b9950ac0a755a01e3f1bd5035f74667761ced7e3`

## 2. All files edited

- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/r6k_refresh_runtime_closure_decision.ps1`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`
- `pipeline/moduleC_pipeline_v2.py`
- `pipeline/portuguese_aq_validation.py`
- `pipeline/qa_gate_v2.py`
- `pipeline/scientific_threshold_gate.py`
- `pipeline/validate_modulec_objectives_canon.py`
- `tests/test_inputs_resolved_traces_gfas_era5.py`
- `tests/test_manifest_recursive_audit.py`
- `tests/test_oc03_v12_decoder_summary_fallback_contract.py`
- `tests/test_oc03_v13_decoder_grib_fallback.py`
- `tests/test_oc03_v13_recovery_contract.py`
- `tests/test_oc03_v13_scientific_gate_recovery_path.py`
- `tests/test_oc03c_portuguese_aq_validation.py`
- `tests/test_smoke_route_selector_prefers_gfas_era5.py`
- `tests/test_spatial_collapse_contracts.py`

## 3. All tests run and results

- `python -m py_compile pipeline\moduleC_pipeline_v2.py pipeline\portuguese_aq_validation.py pipeline\qa_gate_v2.py pipeline\scientific_threshold_gate.py pipeline\validate_modulec_objectives_canon.py tests\test_spatial_collapse_contracts.py tests\test_oc03_v13_recovery_contract.py tests\test_oc03c_blocks_degraded_smoke_runtime.py tests\test_oc03c_portuguese_aq_validation.py`
  - Result: success
- `python -m pytest -q tests\test_spatial_collapse_contracts.py`
  - Result: `9 passed in 0.31s`
- `python -m pytest -q tests\test_oc03_v13_recovery_contract.py`
  - Result: `3 passed in 0.34s`
- `python -m pytest -q tests\test_oc03c_blocks_degraded_smoke_runtime.py`
  - Result: `1 passed in 0.81s`
- `python -m pytest -q tests\test_oc03c_portuguese_aq_validation.py`
  - Result: `21 passed in 8.27s`
- `python -m pytest -q tests\test_inputs_resolved_traces_gfas_era5.py tests\test_manifest_recursive_audit.py tests\test_oc03_v12_decoder_summary_fallback_contract.py tests\test_oc03_v13_decoder_grib_fallback.py tests\test_oc03_v13_scientific_gate_recovery_path.py tests\test_smoke_route_selector_prefers_gfas_era5.py`
  - Result: `14 passed in 0.79s`
- `python -m pytest -q tests`
  - Result: `74 passed in 9.47s`

## 4. Full runtime root

- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\OC03_OC03C_FULL_REPAIR_20260704_090106`

The runtime process fully exited after final artifact generation.

## 5. Runtime command used

Successful launcher:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\run_full_oc03_oc03c_runtime.ps1" -OutputRoot "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\OC03_OC03C_FULL_REPAIR_20260704_090106"
```

The wrapper internally invokes:

```powershell
C:\OSGeo4W64\bin\python-qgis-ltr.bat "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py" --gata-root "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" --modulec-datos "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos" --inc-new "D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version" --output-root "D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\OC03_OC03C_FULL_REPAIR_20260704_090106"
```

## 6. Smoke temporal coverage table by year and month

Direct evidence:

- `qa/gfas_pm2p5fire_portugal_daily_summary.csv`
  - `FIRST_DATE=2015-01-01`
  - `LAST_DATE=2024-12-31`
  - `YEAR_COUNTS=2015:365|2016:366|2017:365|2018:365|2019:365|2020:366|2021:365|2022:365|2023:365|2024:366`
- `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
  - `unique_dates=3653`
  - `unique_units=26`
  - `daily_rows=94978`
  - `years_2015_2024_present=1`
  - `all_months_present_each_year=1`

Coverage summary:

| Year | Dates | Months present |
| --- | ---: | --- |
| 2015 | 365 | 01-12 |
| 2016 | 366 | 01-12 |
| 2017 | 365 | 01-12 |
| 2018 | 365 | 01-12 |
| 2019 | 365 | 01-12 |
| 2020 | 366 | 01-12 |
| 2021 | 365 | 01-12 |
| 2022 | 365 | 01-12 |
| 2023 | 365 | 01-12 |
| 2024 | 366 | 01-12 |

No `2025` spillover remained in final GFAS daily artifacts.

## 7. Smoke route audit summary

- `inputs_resolved.json`
  - `smoke_route_selected=v0_gfas_era5_real`
  - `smoke_route_decision=THRESHOLD_DEFINED_AS_INDEXED_METHOD`
  - `smoke_route_reason=GFAS/ERA5 GDAL-only decoder produced direct PM2P5FIRE unit-level daily coverage for years 2015..2024 ... days_per_year=2015:365,2016:366,2017:365,2018:365,2019:365,2020:366,2021:365,2022:365,2023:365,2024:366.`
- `qa/smoke_route_audit.tsv`
  - `ROUTE_METHODS=gfas_era5_proxy_p60_unit_daily_spatial_direct_year`
- `tables/smoke_day_score_nuts3_daily.csv`
  - `spatial_assignment_method=MULTI_POINT_UNIT_FOOTPRINT_GFAS`

Forbidden smoke methods were not present:

- no `flat_single_anchor`
- no `interpolated_from_anchors`
- no `extrapolated_from_anchors`
- no V12-derived final route
- no resume-derived final route

## 8. Base smoke contract result

- `qa/oc03c_base_smoke_contract_gate.tsv`
  - `base_smoke_contract_for_oc03c_status=BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`
  - `daily_rows=94978`
  - `unique_dates=3653`
  - `unique_years=10`
  - `unique_units=26`
  - `homogeneous_years=0`
  - `all_expected_dates_present=1`
  - `daily_row_cardinality_consistent=1`
  - `forbidden_smoke_methods=NONE`
  - `flat_anchor_reconstruction_detected=0`

## 9. Portuguese AQ consumption and concordance result

- `qa/portuguese_aq_normalization_audit.tsv`
  - `files_discovered=1764`
  - `timeseries_files_normalized=840`
  - `station_metadata_files_normalized=0`
  - `station_inventory_count=262`
  - `daily_station_rows=763579`
  - `assigned_station_count=147`
  - `matched_gfas_aq_day_count=65918`
  - `pollutants_detected=C6H6|CO|NO2|O3|PM10|PM2.5|SO2`
  - `station_metadata_files_normalized=0` was treated as `WARN_METADATA_FORMAL_FILE_NOT_NORMALIZED`, not as a blocker.
- `qa/portuguese_aq_validation_gate.tsv`
  - `portuguese_aq_validation_status=LOCAL_AQ_ANCHORED_PROXY`
  - `final_proxy_tier=TIER_2_LOCAL_SMOKE_PROXY_VALIDATED_BY_AQ`
  - `aq_protocol_decision=GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL`
  - `health_exposure_claim_status=HEALTH_EXPOSURE_NOT_DECLARED`
- `qa/gfas_era5_vs_portuguese_aq_concordance.tsv`
  - strongest matched evidence in final table:
    - `PM10 SPATIAL_MATCHED matched_day_count=65918 station_count=26 unit_count=21 concordance_signal=POSITIVE`
    - `NO2 SPATIAL_MATCHED matched_day_count=59730 concordance_signal=POSITIVE`

## 10. IECH, population, recurrence, scenarios, causal matrix, brief status

- `qa/objectives_canon_alignment_report.tsv`
  - `OC-01 .. OC-12 = PASS`
- `tables/IECH_unit_2015_2024.csv` and `tables/IECH_municipio_2015_2024.csv` present and non-degenerate
- `tables/pop_unit_2015_2025_2030.csv` present
- `tables/recurrence_unit_2015_2024.csv` present
- `tables/IECH_scenarios_2026_2030.csv` present
- `brief/causal_matrix/causal_matrix_IECH_NUTS3.csv` present and `OC-09 = PASS`
- `brief/Brief_Politica_IECH_2030.md` present and `OC-11 = PASS`

## 11. Scientific gate result

- `deliverables_step9/runtime_scientific_closure_decision.md`
  - `scientific_threshold_decision=GO`
  - smoke route scope explicitly limited to `scientific_route_with_proxy_limits`
  - forbidden use explicitly includes health or epidemiological exposure claims
- `qa/scientific_validation_gate.tsv`
  - `SMOKE-DIRECT-2015-2024 = THRESHOLD_DEFINED_AS_INDEXED_METHOD`
  - `BASE_SMOKE_CONTRACT_FOR_OC03C = BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`
  - `OC03C-AQ-001 = LOCAL_AQ_ANCHORED_PROXY`
  - `SMOKE-001 = BLOCKED_FOR_HEALTH_EXPOSURE_CLAIM`
  - every row had `final_decision_effect = NONE`

Interpretation:

- scientific closure is valid for a proxy-limited route
- health exposure remains intentionally not declared

## 12. QA gate result

- `qa/QA_checks.csv`
  - `SUMMARY:decision = GO`
  - `detail = NO_HOLDS`
- `deliverables_step9/runtime_closure_decision.md`
  - `qa_gate_decision = GO`
  - `summary = All GO and canon requirements present with no HOLD flags.`

## 13. Global audit scan result

- `qa/global_audit_status_scan.md`
  - `files_scanned = 70`
  - `active_blockers = 0`
  - `historical_mentions_ignored = 1531`
- `qa/global_audit_status_scan.tsv`
  - every scanned artifact reported `decision = PASS`
  - textual tokens such as `HOLD`, `FAIL`, or `BLOCKED` were correctly classified as historical/forbidden-language contexts, not active blockers

## 14. Manifest/SHA/ZIP freshness check

- `deliverables_step9/final_manifest.json`
  - timestamp `2026-07-05T00:34:33`
  - `MANIFEST_COUNT=59`
- `deliverables_step9/final_sha256_checkpoints.txt`
  - timestamp `2026-07-05T00:34:43`
  - includes fresh hashes for closure, audit, smoke, AQ, and table artifacts
- `deliverables_step9/ModuleC_ALL_FINAL_deliverables.zip`
  - timestamp `2026-07-05T00:34:43`
  - `ZIP_ENTRY_COUNT=60`
  - verified packaged entries include:
    - `qa/QA_checks.csv`
    - `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
    - `qa/global_audit_status_scan.tsv`
    - `qa/global_audit_status_scan.md`
    - `deliverables_step9/runtime_closure_decision.md`
    - `deliverables_step9/runtime_scientific_closure_decision.md`
    - `deliverables_step9/final_manifest.json`

Freshness decision:

- manifest fresh: `PASS`
- SHA checkpoint fresh: `PASS`
- ZIP fresh and rebuilt after the scan/closure set: `PASS`

## 15. Final decision

`FINAL_MODULEC_DECISION = GO_WITH_PROXY_PROTOCOL`

Reason:

- the repaired runtime directly proves full annual GFAS/ERA5 coverage for `2015-01-01 .. 2024-12-31`
- OC-03C AQ upgraded to `LOCAL_AQ_ANCHORED_PROXY`
- health exposure remains explicitly not declared
- proxy limitations are written directly in the scientific closure and AQ claim disposition
- QA gate is `GO`
- global audit active blockers are `0`
- manifest/SHA/ZIP are fresh

## 16. Exact unresolved blockers, if any

- No active runtime blockers remain in the final audit artifacts.
- Remaining limitation is not a blocker:
  - `HEALTH_EXPOSURE_NOT_DECLARED`
  - this is an explicit proxy-limit boundary, not an unresolved fail/hold/block.
