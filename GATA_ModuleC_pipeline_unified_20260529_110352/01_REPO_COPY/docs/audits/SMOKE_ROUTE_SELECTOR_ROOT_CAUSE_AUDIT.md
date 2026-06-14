# SMOKE ROUTE SELECTOR ROOT CAUSE AUDIT

## Scope
- Repo analyzed: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- Branch/SHA at audit time: `main` / `e4b415e38198b90186d8dab8fa78ccfa0f323131`
- Objective: isolate the active smoke-route root cause before implementation edits.

## Canon files read directly
- `PIPELINE_CANON_HANDOFF/12_OBJECTIVES_CANON_MODULEC_IECH.md`
- `docs/canon/SCIENTIFIC_THRESHOLD_DECLARATION_REGISTER_MODULE_C.md`
- `pipeline/RUN_ModuleC_Pipeline_OSGeo4W.cmd`
- `pipeline/moduleC_preflight.py`
- `pipeline/smoke_route_selector.py`
- `pipeline/moduleC_pipeline_v2.py`
- `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`
- `pipeline/scientific_threshold_gate.py`
- `pipeline/qa_gate_v2.py`
- `pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`

## Root-cause findings (current code)
1. Selector priority contract is present and correct.
   - File: `pipeline/smoke_route_selector.py`
   - Evidence: route order is `v1_moduleA_validated -> v0_gfas_era5_real -> BLOCKED_DECODER_REQUIRED -> v0_parquet_proxy_degraded -> NO-GO_SMOKE_ROUTE`.

2. Runtime still remained blocked upstream because real decoder path was missing in execution branch.
   - File: `pipeline/moduleC_pipeline_v2.py`
   - Evidence before this intervention: `smoke_prepare` failed explicitly when `route_selected == "v0_gfas_era5_real"` with \"decoder not implemented\".

3. With decoder unavailable, runtime downgraded to parquet proxy and kept homogeneous smoke.
   - Files: `pipeline/moduleC_pipeline_v2.py`, outputs under `03_outputs/tables`.
   - Evidence: `BLOCKED_DECODER_REQUIRED` plus `proxy_degraded_primary_parquet_*` methods and `unique_values=1` per year.

4. IECH remained operationally computable but scientifically blocked for exposure/ranking claims.
   - Files: `pipeline/moduleC_pipeline_v2.py`, `pipeline/scientific_threshold_gate.py`
   - Evidence: `IECH` collapses to `smoke_hours_equiv`, gate emits `BLOCKED_POPULATION_EXPOSURE_CLAIM` and `BLOCKED_IECH_RANKING`.

5. Causal matrix and brief are downstream and correctly inherit blocked route context when provided.
   - File: `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`
   - Evidence: `SMOKE_ROUTE_BLOCKED` injected into `missing_components`, then `threshold_gate_status` is blocked.

## Confirmed root cause
The open Falla 3 root cause was no longer selector priority; it was the missing executable GFAS/ERA5 decoder branch in runtime.  
Therefore the corrective action must be decoder-path implementation (GDAL-only) plus explicit warning/claim gating, not causal-matrix relaxation.

