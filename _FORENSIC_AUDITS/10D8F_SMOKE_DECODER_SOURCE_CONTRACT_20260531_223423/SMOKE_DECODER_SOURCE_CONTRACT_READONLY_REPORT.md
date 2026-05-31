# MODULE C 10D8F - Smoke decoder source contract read-only audit

## Context
- Mode: LOCAL_READ_ONLY_NO_PATCH_NO_COMMIT_NO_RESET_NO_CLEAN_NO_RUNTIME_NO_BAT_NO_QGIS_NO_PYTHON
- BaseRoot: D:\GATA_MODULEC_UNIFIED_PROCESS
- ExpectedHead: 206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- Branch: main
- CurrentHead: 206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- GitStatusRows: 2
- RuntimeRoot: D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D7_REAL_PRODUCER_PATCH_20260531_083731_ITER3
- OutputRoot: D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D7_REAL_PRODUCER_PATCH_20260531_083731_ITER3\03_outputs
- AuditRoot: D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8F_SMOKE_DECODER_SOURCE_CONTRACT_20260531_223423

## Decision
HOLD_OR_NO_GO_SMOKE_DECODER_SOURCE_CONTRACT_REVIEWED

## Classification
NO_2023_2024_ALL_ZERO_PATTERN_DETECTED_BY_THIS_AUDIT

## Evidence
- inputs/artifacts declare SCIENTIFIC_PRIMARY_REAL route.
- inputs/artifacts declare GFAS + ERA5 decoder is available.
- artifacts contain SMOKE_ROUTE_BLOCKED.
- artifacts contain BLOCKED_FOR_CAUSAL_CLAIM.
- source contains GFAS references.
- source contains ERA5 references.
- source contains GRIB references.
- This audit did not reproduce the 2023/2024 all-zero output pattern.

## Generated TSV files
- selected_context.tsv
- output_smoke_crosscheck.tsv
- source_smoke_decoder_trace.tsv
- source_smoke_decoder_summary.tsv
- generated_artifact_smoke_contract_trace.tsv
- classification.tsv
- classification_evidence.tsv

## Closure rule
This audit does not declare Module C closure. It only classifies whether the current OC09 smoke block is more consistent with data gap, decoder/source contract mismatch, or unresolved producer behavior.
