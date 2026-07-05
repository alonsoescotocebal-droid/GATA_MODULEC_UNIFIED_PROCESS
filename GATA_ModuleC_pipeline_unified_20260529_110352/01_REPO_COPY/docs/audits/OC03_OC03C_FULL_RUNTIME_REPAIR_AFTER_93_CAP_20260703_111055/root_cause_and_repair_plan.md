# OC03/OC03C Full Runtime Repair Plan After GFAS 93-Day Cap

## 1. Current repo status and SHA/branch evidence

- RepoRoot: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- `git branch --show-current`: `codex/add-oc03c-aq-validation`
- `git rev-parse HEAD`: `b9950ac0a755a01e3f1bd5035f74667761ced7e3`
- `config/module_c_canonical_paths.json`:
  - `EXPECTED_BRANCH = codex/add-oc03c-aq-validation`
  - `EXPECTED_BASE_SHA = adee1226ec0df7d0d052d0a0b146daba8ce0c0cb`
- Worktree state at inspection:
  - decoder/base-smoke dynamic repair already present in `pipeline/moduleC_pipeline_v2.py`
  - false final `HOLD/BLOCKED` remains in post-runtime gate readers
  - fresh runtime already exists at `03_RUNTIMES\OC03_OC03C_FULL_REPAIR_20260702_162310` and proves the 93-day cap is gone

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
- The fresh runtime already shows:
  - `2015: 364`
  - `2016: 366`
  - `2017: 365`
  - `2018: 365`
  - `2019: 365`
  - `2020: 366`
  - `2021: 365`
  - `2022: 365`
  - `2023: 365`
  - `2024: 366`
- Remaining closure work must prove:
  - all years `2015-2024` are present
  - all months are present per year
  - `smoke_day_score_nuts3_daily.csv` row cardinality matches actual `date x unit` coverage
  - no `flat_single_anchor`, `interpolated_from_anchors`, or `extrapolated_from_anchors` final route
  - final scientific/objectives/QA gates consume those already-correct artifacts without false parser failures

## 4. Exact files and functions to edit

- `pipeline/scientific_threshold_gate.py`
  - `sniff_delim`
  - `read_csv_rows`
  - consumers: `evaluate_oc03c_base_smoke_contract`, `evaluate_direct_decoder_contract`
- `pipeline/validate_modulec_objectives_canon.py`
  - `sniff_delim`
  - `read_csv_rows`
  - `_v10b_read_rows_if_exists`
  - `_read_metric_value_map`
  - consumers: `_check_oc03_v13_direct_contract`, `_check_oc03c_aq_validation`
- `pipeline/qa_gate_v2.py`
  - `sniff_delimiter`
  - `read_csv_rows`
  - consumers: objectives/scientific gate readers

## 5. Exact tests to update

- `tests/test_spatial_collapse_contracts.py`
  - keep the pipeline-level delimiter regression for `.tsv` with semicolons in detail
- `tests/test_oc03_v13_recovery_contract.py`
  - add validator regression proving direct decoder contract still passes when `.tsv` detail contains many semicolons
- `tests/test_oc03_v13_scientific_gate_recovery_path.py`
  - add scientific-gate regression proving decoder metrics are not collapsed to `0`
- `tests/test_oc03c_portuguese_aq_validation.py`
  - add OC-03C base-smoke/QA-gate regressions proving `.tsv` parsing does not fabricate missing status or false holds

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

## 7. Exact final artifacts that must be read

- `qa/inputs_resolved.json`
- `qa/report_auditoria_v2.txt`
- `qa/run_log.txt`
- `qa/path_scope_guard_report.tsv`
- `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
- `qa/smoke_route_audit.tsv`
- `qa/oc03c_base_smoke_contract_gate.tsv`
- `qa/portuguese_aq_validation_gate.tsv`
- `qa/gfas_era5_vs_portuguese_aq_concordance.tsv`
- `qa/objectives_canon_alignment_report.tsv`
- `qa/scientific_validation_gate.tsv`
- `qa/QA_checks.csv`
- `qa/global_audit_status_scan.md`
- `qa/global_audit_status_scan.tsv`
- `deliverables_step9/runtime_closure_decision.md`
- `deliverables_step9/runtime_scientific_closure_decision.md`
- `deliverables_step9/final_manifest.json`
- `deliverables_step9/final_sha256_checkpoints.txt`
- `deliverables_step9/ModuleC_ALL_FINAL_deliverables.zip`

## 8. Decision rule for GO/HOLD/NO-GO/BLOCKED

- `GO` only if the fresh full runtime completes from scratch and all final artifacts agree with no active `FAIL`, `HOLD`, `BLOCKED`, stale packaging, or unsupported claim.
- `HOLD` if smoke coverage is correct but final gates or packaging are still inconsistent.
- `BLOCKED` only if the real smoke contract cannot be determined from code/runtime evidence and no meaningful patch path remains.
- `NO-GO` if the fresh runtime still regresses smoke coverage, uses forbidden methods, or leaves unsupported scientific claims active.
