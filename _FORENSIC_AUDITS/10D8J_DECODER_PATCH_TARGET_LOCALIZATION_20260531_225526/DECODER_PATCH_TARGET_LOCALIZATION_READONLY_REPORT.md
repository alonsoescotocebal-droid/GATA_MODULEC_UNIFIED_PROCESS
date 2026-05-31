# MODULE C 10D8J - Decoder patch target localization read-only audit

## Decision
HOLD_OR_NO_GO_PATCH_TARGET_LOCALIZATION_REVIEWED

## Classification
PATCH_TARGET_CONFIRMED_ROUTE_DECLARATION_AND_DECODER_IMPLEMENTATION_CONTRACT

## Evidence
- Outputs are all-zero for 2023 and 2024 across NUTS3 and municipio smoke tables.
- inputs_resolved declares SCIENTIFIC_PRIMARY_REAL and decoder-available route.
- Source scan did not find direct decoder calls for GDAL/Parquet/GRIB read execution.
- smoke_route_audit marks 2023 and 2024 as extrapolated_from_anchors with missing flag.
- inputs_resolved shows required_decoder as empty string.

## Patch targets
- P1: pipeline\moduleC_pipeline_v2.py :: write_gfas_era5_decoder_audit / route declaration block :: Do not declare decoder available or SCIENTIFIC_PRIMARY_REAL when direct decoder evidence is absent or required_decoder is empty.
- P2: pipeline\moduleC_pipeline_v2.py :: smoke_prepare :: Propagate missing 2023/2024 direct-year state into route status and route reason; keep output zero only as HOLD/NO-GO evidence, not as real decoded smoke.
- P3: pipeline\moduleC_pipeline_v2.py :: _fill_smoke_year_series :: Separate direct_year, interpolated, extrapolated, and missing branches in audit outputs; prevent extrapolated missing years from being labeled as primary real coverage.
- P4: pipeline\moduleC_pipeline_v2.py :: _derive_unit_anchor_scores_from_xyz :: Verify whether GFAS/XYZ anchor scores are actual decoded values or synthetic anchors; expose decoder proof columns.
- P5: pipeline\scientific_threshold_gate.py :: smoke/causal gate rules :: Gate appears correctly blocking; only adjust messages if route declaration is corrected.

## Generated files
- selected_context.tsv
- output_smoke_year_summary.tsv
- smoke_route_audit_year_lines.tsv
- artifact_declaration_vs_blocking_trace.tsv
- source_function_snippets.tsv
- source_global_token_counts.tsv
- source_patch_target_lines.tsv
- gate_source_trace.tsv
- patch_targets.tsv
- classification.tsv
- classification_evidence.tsv

## Mode
LOCAL_READ_ONLY_NO_PATCH_NO_COMMIT_NO_RESET_NO_CLEAN_NO_RUNTIME_NO_BAT_NO_QGIS_NO_PYTHON_NO_GRIB_DECODE
