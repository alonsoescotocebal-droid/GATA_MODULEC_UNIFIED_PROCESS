# MODULE C 10D8L - Decoder contract patch dry-run

## Mode
LOCAL_READ_ONLY_NO_PATCH_NO_COMMIT_NO_RESET_NO_CLEAN_NO_RUNTIME_NO_BAT_NO_QGIS_NO_PYTHON_NO_GRIB_DECODE

## Context
- BaseRoot: D:\GATA_MODULEC_UNIFIED_PROCESS
- ExpectedHead: 206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- CurrentHead: 206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- GitStatusRows: 2
- SourcePath: D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py
- LatestBundlePath: D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8K_PATCH_SOURCE_CONTEXT_BUNDLE_20260531_225835\PATCH_SOURCE_CONTEXT_BUNDLE.txt

## Required correction
The patch must correct the implementation-contract mismatch: the pipeline must not declare SCIENTIFIC_PRIMARY_REAL or decoder available when required_decoder is empty, direct decoder proof is absent, or 2023/2024 are extrapolated missing branches with all-zero outputs.

## Patch targets
- P1: pipeline\moduleC_pipeline_v2.py :: write_gfas_era5_decoder_audit :: Change decoder-available wording to require direct decoder evidence, non-empty required_decoder, and non-missing direct-year coverage.
- P2: pipeline\moduleC_pipeline_v2.py :: smoke_prepare :: Propagate 2023/2024 extrapolated missing branch into route status/reason and audit columns before writing smoke outputs.
- P3: pipeline\moduleC_pipeline_v2.py :: _fill_smoke_year_series / _fill_smoke_year_series_relaxed :: Separate direct, interpolated, extrapolated, and missing branches; prevent extrapolated missing years from being labeled as real coverage.
- P4: pipeline\moduleC_pipeline_v2.py :: _derive_unit_anchor_scores_from_xyz / GRIB helper zone :: Expose proof columns showing whether values are decoded from GRIB/ERA5 or synthetic anchors.
- P5: pipeline\scientific_threshold_gate.py :: smoke/causal gate rules :: Do not relax blocking logic; only align messages after route declaration is corrected.

## Dry-run result
- Failed requirements: 0
- Warning/review requirements: 0

## Next step
If failed requirements equal zero, the next microfase may author an apply-patch script against moduleC_pipeline_v2.py. This file does not apply changes.
