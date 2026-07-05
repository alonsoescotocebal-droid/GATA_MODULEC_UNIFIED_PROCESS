# OC-03 / OC-03C Root Cause Diagnosis

- Generated: 2026-06-25
- Repo root: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- Scope: restore the OC-03 GFAS/ERA5 smoke baseline and ensure OC-03C consumes Portuguese AQ only after the base smoke contract passes.

## Executive finding

The observed OC-03C failure was not caused by Portuguese AQ insufficiency. The failing runtime was derived from a V12 runtime and resumed with `--resume-post-smoke`, which skipped fresh smoke reconstruction and reused an already regressed smoke base. That reused base carried a one-year direct anchor plus flat interpolated/extrapolated years, so the OC-03 smoke contract was already invalid before Portuguese AQ validation executed.

If the smoke base cannot be restored from a fresh full runtime, the correct terminal state is `NO-GO_OC03_SMOKE_BASE_NOT_RESTORED`.

## Required evidence

### Runtime derivation evidence

Source file:
`D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03C_PORTUGUESE_AQ_VALIDATION_20260624_153719\OC03C_RUNTIME_DERIVATION.md`

Observed facts from direct artifact reading:

- `source_runtime_wrapper` points to `ModuleC_RUNTIME_OC03_V12_RECENTER_CANONICAL_20260618_190708`
- `source_output_root` points to that V12 runtime's `03_outputs`
- `next_step` states `resume-post-smoke refresh with OC-03C Portuguese AQ validation enabled`

Conclusion: the failed OC-03C runtime was a derived resume-post-smoke runtime from V12 and is forbidden as final validation.

### Regressed smoke-base evidence

Source files:

- `...\ModuleC_RUNTIME_OC03C_PORTUGUESE_AQ_VALIDATION_20260624_153719\03_outputs\qa\gfas_era5_decoder_daily_spatial_audit.tsv`
- `...\ModuleC_RUNTIME_OC03C_PORTUGUESE_AQ_VALIDATION_20260624_153719\03_outputs\qa\smoke_route_audit.tsv`
- `...\ModuleC_RUNTIME_OC03C_PORTUGUESE_AQ_VALIDATION_20260624_153719\03_outputs\qa\inputs_resolved.json`

Observed facts from direct artifact reading:

- decoder audit reports `daily_rows=2418`, `unique_dates=93`, `unique_years=1`, `unique_units=26`
- smoke-route audit shows most years 2015-2024 using `gfas_era5_proxy_p60_unit_daily_spatial_flat_single_anchor`
- `inputs_resolved.json` still references legacy parquet smoke input while the route reason admits only one direct anchor year and interpolated/extrapolated surrounding years
- Portuguese AQ inventory was consumed in that runtime despite the invalid smoke base

Conclusion: the smoke baseline had already regressed to a single-anchor reconstruction before OC-03C ran.

## Code-path diagnosis

### Which code writes the OC-03 smoke artifacts

- `pipeline/moduleC_pipeline_v2.py::smoke_prepare`
  - writes `tables/smoke_days_unit_2015_2024.csv`
  - writes alias `tables/smoke_days_nuts3_annual_2015_2024.csv`
  - writes `tables/smoke_day_score_nuts3_daily.csv` when the active route is the real GFAS/ERA5 decoder route
- `pipeline/moduleC_pipeline_v2.py::write_smoke_route_audit`
  - writes `qa/smoke_route_audit.tsv`
- `pipeline/moduleC_pipeline_v2.py::write_gfas_era5_decoder_daily_spatial_audit`
  - writes `qa/gfas_era5_decoder_daily_spatial_audit.tsv`

These are the contract artifacts that must prove:

- `daily_rows=24180`
- `unique_dates=930`
- `unique_years=10`
- `unique_units=26`
- `homogeneous_years=0`
- years `2015-2024` present
- no `flat_single_anchor`
- no interpolated or extrapolated anchor methods

### Does `refresh_smoke_route_v0_audit(output_root)` degrade valid smoke outputs

No.

`pipeline/moduleC_pipeline_v2.py::refresh_smoke_route_v0_audit` only reads:

- `qa/warning_inventory.tsv`
- `qa/gfas_era5_decoder_backend_audit.tsv`
- `qa/gfas_era5_decoder_audit.tsv`

and writes:

- `qa/smoke_route_v0_audit.tsv`

It does not rewrite `qa/smoke_route_audit.tsv`, `qa/gfas_era5_decoder_daily_spatial_audit.tsv`, or `tables/smoke_day_score_nuts3_daily.csv`. Therefore it does not itself flatten or degrade a valid smoke baseline.

### Where the bad behavior entered

`pipeline/moduleC_pipeline_v2.py::main` allows a `--resume-post-smoke` path. That path dispatches into `complete_post_smoke_runtime(...)`, which:

1. reuses existing smoke artifacts
2. refreshes only the `smoke_route_v0_audit.tsv` summary
3. runs the OC-03 decoder contract validation
4. runs the base-smoke gate for OC-03C
5. only then runs Portuguese AQ validation if the base smoke gate passes

The root problem in the failed runtime was not this gate logic. The problem was that the runtime was started from a derived V12 smoke base instead of a fresh full smoke rebuild.

## Current repo state

The repo already contains the core OC-03C hard gate:

- `pipeline/moduleC_pipeline_v2.py::run_base_smoke_contract_for_oc03c`
  - reads `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
  - reads `qa/smoke_route_audit.tsv`
  - reads `tables/smoke_day_score_nuts3_daily.csv`
  - blocks if the base smoke contract regresses
- `pipeline/moduleC_pipeline_v2.py::complete_post_smoke_runtime`
  - calls Portuguese AQ validation only when `base_smoke_contract_for_oc03c_passed` is true
- `pipeline/portuguese_aq_validation.py::write_blocked_base_smoke_regression_outputs`
  - writes blocked OC-03C artifacts and explicitly forbids any Portuguese AQ insufficiency conclusion in that blocked state

## Remaining repair gaps to close before full rerun

1. Emit the prompt-aligned alias artifacts:
   - `qa/oc03_base_smoke_contract_gate.tsv`
   - `qa/oc03_base_smoke_contract_report.md`
2. Remove the conflated OC-03C wording `PORTUGUESE_AQ_VALIDATION_NOT_CONSUMED_OR_INSUFFICIENT` from consumed-but-insufficient outcomes.
3. Add regression coverage proving degraded smoke runtimes are blocked before Portuguese AQ consumption.

## Root cause

Exact root cause:

The failed OC-03C runtime inherited smoke artifacts from `ModuleC_RUNTIME_OC03_V12_RECENTER_CANONICAL_20260618_190708\03_outputs` and resumed post-smoke, so no fresh GFAS/ERA5 2015-2024 smoke rebuild occurred. The inherited smoke artifacts were already regressed to a single-anchor flat reconstruction (`unique_years=1`, `daily_rows=2418`, `unique_dates=93`, `flat_single_anchor` present). Portuguese AQ was therefore consumed on top of an invalid OC-03 smoke base.

## Repair direction

The correct repair is:

1. keep the existing OC-03C hard gate
2. align artifact names and report outputs with the requested base smoke contract
3. remove the conflated AQ claim wording
4. execute a fresh full runtime under `03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_<timestamp>`
5. validate only by direct reading of the new runtime artifacts

Until a fresh runtime proves the full smoke contract, no Portuguese AQ insufficiency claim is valid.
