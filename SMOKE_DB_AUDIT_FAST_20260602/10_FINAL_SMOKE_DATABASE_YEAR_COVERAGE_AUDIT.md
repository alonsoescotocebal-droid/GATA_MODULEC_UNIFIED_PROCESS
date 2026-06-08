# MODULE C â€” Smoke database year coverage audit
## Scope
This audit is READ ONLY. It does not patch code, mutate input data, run the pipeline, commit, reset, or clean git state.
## Inputs
- RepoRoot: `D:\GitHub\GATA_ModuleC_pipeline_clean`
- DataRoot: `D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos`
- OutputRoot used: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D8R_CANON_THRESHOLD_ONLY_20260601_171721_ITER1\03_outputs`
- Required years: `2015,2016,2017,2018,2019,2020,2021,2022,2023,2024`
- DeepGrib: `False`
- DeepParquet: `False`
- GDAL available: `True`
- pandas available: `True`

## Runtime smoke route flags
- `smoke_route_status` = `HOLD_DIRECT_YEAR_DECODER_EVIDENCE_MISSING`
- `smoke_route_decision` = `BLOCKED_DIRECT_YEAR_DECODER_EVIDENCE_MISSING`
- `smoke_route_reason` = `v0_gfas_era5_real was selected, but 2023/2024 smoke outputs are all-zero and audit/output flags indicate extrapolated or missing direct-year coverage.`
- `required_decoder` = `GFAS_ERA5_DIRECT_YEAR_DECODER_PROOF_REQUIRED`
- `smoke_route_contract_correction` = `CODEX_10D8M`
- `smoke_route_contract_correction_status` = `APPLIED_ROUTE_METADATA_DEGRADATION`
- `smoke_route_contract_correction_basis` = `direct output all-zero 2023/2024 plus extrapolated/missing branch evidence`

## Direct evidence summary
- Years consumed by runtime as direct evidence: `2017,2022`
- Years reconstructed/interpolated/extrapolated without direct runtime evidence: `2015,2016,2018,2019,2020,2021,2023,2024`
- Years not consumed as direct runtime evidence: `2015,2016,2018,2019,2020,2021,2023,2024`

## Year decisions
| year | decision | action |
|---:|---|---|
| 2015 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. |
| 2016 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. |
| 2017 | `PASS_CONSUMED_AS_DIRECT_YEAR_EVIDENCE` | Keep as direct smoke evidence, but still verify daily coverage completeness. |
| 2018 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. |
| 2019 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. |
| 2020 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. |
| 2021 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. |
| 2022 | `PASS_CONSUMED_AS_DIRECT_YEAR_EVIDENCE` | Keep as direct smoke evidence, but still verify daily coverage completeness. |
| 2023 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY__ALL_ZERO_HOMOGENEOUS_OUTPUT` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. Do not interpret zero as no smoke; it is missing/invalid evidence until proven otherwise. |
| 2024 | `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY__ALL_ZERO_HOMOGENEOUS_OUTPUT` | Treat as invalid for direct historical smoke. Recover/download direct data for this year. Do not interpret zero as no smoke; it is missing/invalid evidence until proven otherwise. |

## Interpretation rule
- If `DATA_PRESENT_OR_INDEXED_BUT_NOT_CONSUMED` appears, the local database likely contains a year-linked source but the pipeline did not consume it as direct smoke evidence. Investigate decoder/indexing/selector code.
- If `NO_DIRECT_DATA_EVIDENCE_RUNTIME_RECONSTRUCTED_ONLY` appears, the runtime output for that year is not a valid historical direct smoke observation. It is interpolation/extrapolation and must not feed final IECH as direct evidence.
- If `ALL_ZERO_HOMOGENEOUS_OUTPUT` appears, zero must be treated as missing/invalid until direct year decoding proves otherwise. It is not evidence of no smoke.

## Output files
- `01_data_root_smoke_inventory.tsv`
- `02_archive_member_inventory.tsv`
- `03_gfas_grib_metadata_inventory.tsv`
- `04_parquet_aq_inventory.tsv`
- `05_runtime_smoke_coverage_by_year.tsv`
- `06_local_database_year_evidence.tsv`
- `07_pipeline_code_smoke_references.tsv`
- `08_FINAL_year_coverage_decision.tsv`
- `09_runtime_key_smoke_flags.json`

## Final rule
A year is valid for historical smoke only if it has direct, year-specific source evidence and the runtime consumes it as direct evidence. Interpolation/extrapolation from anchor years is not acceptable for final IECH closure unless explicitly declared as non-final proxy reconstruction.
