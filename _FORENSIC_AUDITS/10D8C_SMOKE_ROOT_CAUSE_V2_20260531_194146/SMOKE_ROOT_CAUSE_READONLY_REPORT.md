# MODULE C 10D8C V2 - Smoke 2023-2024 root cause read-only audit

## Mode
LOCAL_READ_ONLY_NO_PATCH_NO_COMMIT_NO_RESET_NO_CLEAN_NO_RUNTIME

## Context
- BaseRoot=D:\GATA_MODULEC_UNIFIED_PROCESS
- ExpectedHead=206d40c30c9799ce0da4fcbb9ceb1295e556bfdf
- GitRoot=D:\GATA_MODULEC_UNIFIED_PROCESS
- ActiveUnifiedRoot=D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642
- RepoCopyRoot=D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\01_REPO_COPY
- RuntimeRoot=D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D7_REAL_PRODUCER_PATCH_20260531_083731_ITER3
- OutputRoot=D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110642\03_RUNTIMES\ModuleC_RUNTIME_10D7_REAL_PRODUCER_PATCH_20260531_083731_ITER3\03_outputs
- AuditRoot=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146

## Inputs
- smoke_csv=D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\ParquetFiles 2022.zip
- smoke_gfas_dir=D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\CAM-GFAS (ADS)
- smoke_era5_zip=D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\ERA5_d016a6f04c5e420341cf0e7293fcfb56.zip
- smoke_route_mode=v0_gfas_era5_real
- smoke_route_status=SCIENTIFIC_PRIMARY_REAL
- smoke_route_decision=THRESHOLD_DEFINED_AS_INDEXED_METHOD
- iech_decision=IECH_ROUTE_REAL_SMOKE

## Decision
HOLD_OR_NO_GO_SMOKE_DATA_GAP_CONFIRMED

## Classification
NO_RAW_SMOKE_OR_GFAS_COVERAGE_FOR_BLOCKED_YEARS

## Evidence
- Output smoke profile is homogeneous/all-zero in 2023/2024 and no raw/GFAS coverage for those years was detected by this read-only audit.
- This supports a real data completeness gap, not a simple OC09 writing error.
- inputs_resolved declares SCIENTIFIC_PRIMARY_REAL route, but output smoke has blocked homogeneous years.

## Generated TSVs
- selected_context.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\selected_context.tsv
- inputs_resolved_smoke_paths.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\inputs_resolved_smoke_paths.tsv
- output_smoke_profile.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\output_smoke_profile.tsv
- raw_smoke_csv_profile.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\raw_smoke_csv_profile.tsv
- gfas_file_coverage_by_year.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\gfas_file_coverage_by_year.tsv
- era5_zip_coverage_by_year.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\era5_zip_coverage_by_year.tsv
- oc09_gate_crosscheck.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\oc09_gate_crosscheck.tsv
- gate_status_tokens.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\gate_status_tokens.tsv
- source_smoke_trace.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\source_smoke_trace.tsv
- runtime_log_smoke_trace.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\runtime_log_smoke_trace.tsv
- classification.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\classification.tsv
- classification_evidence.tsv=D:\GATA_MODULEC_UNIFIED_PROCESS\_FORENSIC_AUDITS\10D8C_SMOKE_ROOT_CAUSE_V2_20260531_194146\classification_evidence.tsv

## Closure rule
This script does not declare Module C closure. It only classifies the probable smoke/OC09 blocking mechanism by direct file reading.
