# MODULE C 10D8H - Smoke producer branch read-only audit

## Decision
HOLD_OR_NO_GO_SMOKE_PRODUCER_BRANCH_REVIEWED

## Classification
DECLARED_REAL_ROUTE_BUT_2023_2024_OUTPUT_ZERO_AND_ROUTE_EXTRAPOLATED_MISSING

## Evidence
- Output smoke tables are all-zero for 2023 and 2024 across NUTS3 and municipio summaries.
- Smoke route audit marks 2023 and 2024 as extrapolated_from_anchors or equivalent non-direct branch.
- OC09/scientific artifacts still contain NO-GO or causal/smoke blocking tokens.
- Source contains gfas_pm2p5fire_gdal method tokens.
- Source token scan did not find explicit gdal.Open/OpenEx.
- Source token scan did not find explicit read_parquet/pyarrow.
- Source contains primary_parquet branch token.
- Source contains extrapolated_from_anchors branch token.
- Source contains direct_year branch token.
- No runtime, BAT, QGIS, Python, or GRIB decoder was invoked by this audit.
- Extracted source snippets are stored under source_function_snippets for manual review.

## Generated files
- selected_context.tsv
- year_by_year_output_smoke_summary.tsv
- smoke_route_year_contract_summary.tsv
- source_function_blocks.tsv
- source_token_counts.tsv
- gate_oc09_token_summary.tsv
- classification.tsv
- classification_evidence.tsv
- source_function_snippets/*.txt

## Closure rule
This audit is read-only and does not run BAT, QGIS, Python, GRIB decoders, runtime, git reset, git clean, patch, or commit.
