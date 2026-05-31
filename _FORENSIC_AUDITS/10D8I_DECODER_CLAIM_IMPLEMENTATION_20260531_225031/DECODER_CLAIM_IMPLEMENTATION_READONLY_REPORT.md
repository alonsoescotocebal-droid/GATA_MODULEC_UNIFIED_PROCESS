# MODULE C 10D8I - Decoder claim vs implementation read-only audit

## Context
- BaseRoot: D:\GATA_MODULEC_UNIFIED_PROCESS
- ExpectedHead: 206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- CurrentHead: 206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- RuntimeRoot: D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D7_REAL_PRODUCER_PATCH_20260531_083731_ITER3
- OutputRoot: D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D7_REAL_PRODUCER_PATCH_20260531_083731_ITER3\03_outputs
- SourcePath: D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py
- AuditRoot: D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8I_DECODER_CLAIM_IMPLEMENTATION_20260531_225031

## Decision
HOLD_OR_NO_GO_DECODER_CLAIM_IMPLEMENTATION_REVIEWED

## Classification
DECLARED_REAL_GFAS_ERA5_ROUTE_WITHOUT_DIRECT_DECODER_CALL_AND_MISSING_2023_2024_BRANCH

## Evidence
- Smoke outputs are all-zero for 2023 and 2024 across NUTS3 and municipio tables.
- Smoke route audit marks 2023 and 2024 as extrapolated/missing branch.
- Artifacts declare SCIENTIFIC_PRIMARY_REAL or decoder-available route.
- Source scan did not find direct decoder calls such as gdal.Open/OpenEx/ReadAsArray/read_parquet/pyarrow/cfgrib.
- This supports an implementation-contract mismatch: declared real route is not proven as effective decoding for 2023/2024.
- OC09/scientific artifacts contain blocking tokens consistent with the smoke output problem.
- Source contains primary_parquet branch token.
- Source contains gfas_pm2p5fire_gdal method token.
- No runtime, BAT, QGIS, Python, or GRIB decoder was invoked by this audit.
- Source snippets are stored under source_function_snippets for manual line-by-line review.

## Generated files
- selected_context.tsv
- smoke_output_year_summary.tsv
- smoke_route_audit_year_rows.tsv
- source_function_blocks.tsv
- source_function_token_counts.tsv
- source_global_token_counts.tsv
- artifact_decision_token_counts.tsv
- classification.tsv
- classification_evidence.tsv
- source_function_snippets/*.txt

## Safety statement
This audit is read-only. It does not patch code, modify data, execute runtime, call BAT/QGIS/Python, or decode GRIB files.
