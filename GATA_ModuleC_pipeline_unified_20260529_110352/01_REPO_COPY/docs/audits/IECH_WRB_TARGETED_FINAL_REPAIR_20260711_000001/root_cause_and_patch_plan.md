# IECH/WRB Targeted Final Repair Root Cause and Patch Plan

## 1. Repository baseline

- Repo root: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- Branch: `codex/wrb-source-route-repair-b9cb373d`
- Starting SHA: `4a2899f87c38d58b83ca29dc23f2e625c7af1bad`
- Worktree status: clean (`git status --short` returned no changed files)

## 2. Direct confirmation of the historical aggregation bug

Primary producer:

- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`

Direct code evidence:

- `compute_iech()` writes detailed rows as:
  - index `6` = `population_exposed_assumed`
  - index `10` = `population_smoke_burden_proxy`
  - index `11` = `IECH`
- The historical mean accumulator then reads `safe_float(r[6])`, not the proxy field.

Observed root cause:

- Historical mean tables are averaging population/exposed-population values instead of `population_smoke_burden_proxy`.

Consequence chain:

- `tables/IECH_unit_2015_2024_mean.csv`
- `tables/IECH_municipio_2015_2024_mean.csv`
- downstream causal-matrix burden fields
- burden percentiles/policy priority
- brief burden range

## 3. Direct confirmation of the scenario aggregation bug

Primary producer:

- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`

Direct code evidence:

- `compute_scenarios()` writes detailed rows as:
  - index `7` = `population_exposed_assumed`
  - index `11` = `population_smoke_burden_proxy`
  - index `12` = `IECH`
  - index `13/14` = deltas vs S0
- The scenario mean accumulator then reads `safe_float(r[7])`, not the proxy field.

Observed root cause:

- Scenario means are averaging population/exposed-population values.
- Because S0 and S1 share the same population, mean deltas collapse to zero even when detailed S1 rows contain real reductions.

Consequence chain:

- `tables/IECH_scenarios_unit_2026_2030_mean.csv`
- `tables/IECH_scenarios_municipio_2026_2030_mean.csv`
- causal matrix scenario fields
- brief scenario delta
- scenario audits

## 4. Direct confirmation of the prohibited WRB admin-unit-only branch

Primary producer:

- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`

Direct code evidence:

- The WRB writer still emits:
  - `Contexto edafico territorial (WRB) sobre unidad territorial completa; sin interseccion quemada 2015-2024; no causal directo.`
- The branch passes `territorial_counts` into `_dominant_wrb_row(...)` when no burned-area WRB counts exist.

Observed root cause:

- The code still substitutes full administrative unit WRB composition when the burned-area overlay has no counts.

Required repair:

- Replace this fallback with explicit classification:
  - `NOT_APPLICABLE_ZERO_BURNED_AREA_2015_2024`
  - `BLOCKED_WRB_BURNED_AREA_EXTRACTION_MISSING`
  - `PASS_BURNED_AREA_WRB_OVERLAY`

## 5. Direct confirmation of the WRB audit token mismatch

Primary producer:

- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`

Direct code evidence:

- `write_territorial_and_wrb_audits()` only scans for:
  - `fallback`
  - `centroid`
  - `admin-unit-only`
  - `admin_unit-only`
  - `global class`
  - `raster metadata`
- It does not scan the actual note language:
  - `unidad territorial completa`
  - `sin interseccion quemada`
  - `full administrative unit`

Observed root cause:

- Existing audit can return zero fallback rows while prohibited admin-unit-only rows still exist.

## 6. Direct confirmation of warning-inventory scope

Primary producer:

- `pipeline/moduleC_pipeline_v2.py`

Direct code evidence:

- `_write_warning_inventory()` is fed by `warning_rows` populated from the GFAS/ERA5 decoder path.
- `_capture_warning_rows()` is specialized to GFAS/GDAL decoder warnings.
- The contract-required files are not part of the inventory logic:
  - `qa/step7_matriz_causal_stdout.txt`
  - `qa/step7_matriz_causal_stderr.txt`
  - `qa/run_log.txt`
  - `qa/report_auditoria_v2.txt`

Observed root cause:

- Final warning inventory covers GFAS/ERA5 decoder messages but not Step7/WRB stderr and runtime warnings comprehensively.

## 7. Direct comparison between Step9 required artifacts and the previous/current package contract

Current package contract producer:

- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`

Direct code evidence:

- Step9 already requires `qa/warning_inventory.tsv`, `brief/causal_matrix/causal_matrix_audit.tsv`, and core IECH/WRB artifacts.
- Repository-wide searches do not show current producers/consumers for:
  - `qa/source_runtime_provenance.tsv`
  - `qa/iech_aggregate_consistency_audit.tsv`
  - `qa/scenario_aggregate_consistency_audit.tsv`
  - `qa/wrb_method_consistency_audit.tsv`
- `collect_final_outputs()` in `pipeline/moduleC_pipeline_v2.py` also does not currently include those new contract artifacts.

Observed root cause:

- Step9/package completeness cannot prove the exact current contract because newly required provenance/consistency artifacts are missing from generation and/or packaging paths.

## 8. Exact source files to edit

- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`
- `pipeline/moduleC_pipeline_v2.py`
- `pipeline/qa_gate_v2.py`
- `pipeline/scientific_threshold_gate.py`
- `pipeline/validate_modulec_objectives_canon.py`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/r6k_refresh_runtime_closure_decision.ps1`

## 9. Exact tests to add or update

Add:

- `tests/test_iech_historical_mean_uses_population_smoke_burden_proxy.py`
- `tests/test_iech_scenario_mean_preserves_s1_delta.py`
- `tests/test_wrb_no_admin_unit_only_fallback.py`
- `tests/test_wrb_zero_burn_is_not_applicable_not_invented.py`
- `tests/test_wrb_positive_burn_missing_blocks.py`
- `tests/test_wrb_audit_detects_full_admin_fallback_language.py`
- `tests/test_causal_matrix_uses_canonical_proxy_means.py`
- `tests/test_brief_uses_repaired_proxy_and_scenario_means.py`
- `tests/test_warning_inventory_covers_step7_wrb.py`
- `tests/test_step9_manifest_zip_required_artifact_equivalence.py`

Update as needed after impact review:

- existing WRB source-route/prevalidation tests
- existing manifest recursive audit tests
- relevant scientific/objective/QA gate tests

## 10. Exact focused prevalidation commands

Planned order:

1. Focused pytest for new regression tests around Step7 aggregation/WRB/audits.
2. Broader relevant pytest slice for gates and Step9 packaging.
3. Diagnostic prevalidation run(s) generating disposable outputs under `03_RUNTIMES` only if needed to read fresh artifacts for:
   - aggregate consistency audits
   - WRB classification/method counts
   - warning inventory classification
   - Step9 required-artifact equivalence

## 11. Exact full-runtime command

To be finalized only after inspecting the real launcher/CLI contract in the repository. The full runtime will run from a single fresh root under:

- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES`

and must execute from preflight through Step9 without `resume`.

## 12. Exact direct-artifact closure criteria

Final closure requires direct readback from one fresh full runtime of:

- provenance and path-scope artifacts
- historical detailed + mean IECH tables and recomputed means
- scenario detailed + mean tables and recomputed deltas
- WRB prevalidation/integration/method artifacts
- causal matrix and brief outputs compared numerically against canonical mean tables
- warning inventory with zero unclassified warnings/errors
- QA/scientific/objective/global gate outputs
- Step9 manifest, recursive audit, SHA checkpoints, staleness audit and ZIP payload equivalence

Closure is `GO_WITH_POPULATION_SMOKE_BURDEN_PROXY_AND_STRICT_WRB_BURNED_AREA_ROUTE` only if every contract predicate passes from those direct reads.
