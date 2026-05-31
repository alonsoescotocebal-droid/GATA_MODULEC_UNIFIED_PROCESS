# MODULE C 10D8G - Smoke output value + source line read-only audit

## Decision
HOLD_OR_NO_GO_SMOKE_OUTPUT_SOURCE_RECONCILIATION

## Classification
OUTPUT_ALL_ZERO_CONFIRMED_WITH_OC09_AND_SCIENTIFIC_GATE_BLOCK

## Evidence
- Output smoke_days contains ALL_ZERO for 2023 and 2024 by direct table parsing.
- Scientific/OC09 artifacts contain NO-GO or causal/smoke route blocking tokens.
- Source contains GFAS/GDAL smoke route references.
- Source token count did not find read_parquet; parquet handling must be inspected in extracted snippets.
- Municipal smoke_days is homogeneous by year, including all-zero 2023/2024.
- No GRIB decoder was invoked by this audit.
- No runtime was executed by this audit.
- Source snippets were extracted for manual line-by-line review.

## Generated files
- selected_context.tsv
- output_smoke_value_profile.tsv
- smoke_route_audit_relevant_lines.tsv
- gate_oc09_token_crosscheck.tsv
- source_function_snippet_index.tsv
- source_token_counts.tsv
- source_snippet_*.txt
- classification.tsv
- classification_evidence.tsv

## Closure rule
This audit does not declare Module C closure. It reconciles output smoke values with source/gate evidence by direct file reading only.
