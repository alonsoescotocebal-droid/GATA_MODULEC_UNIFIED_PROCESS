# 04 Entrypoints And Gates

## Entrypoint único de runtime ModuleC
- Wrapper: D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\_qa_catalogs\moduleC_local_pipeline\RUN_ModuleC_Pipeline_OSGeo4W.cmd
- Modo runtime: --pipeline-v2

## Entrypoints de gates
- Documental: tools\setup_profile_minus1_documental_baseline.ps1
- Entorno estricto: tools\setup_profile3_qgis_runtime.ps1
- Preflight: run_preflight_bootstrap.py
- QA gate: qa_gate_v2.py

## Entrypoints NO permitidos
- run_pipeline_debug_v5.py
- moduleC_pipeline.py como runner principal
- RUN_ModuleC_Pipeline_OSGeo4W.legacy.cmd
- wrappers .BACKUP_*/.legacy/.bak
