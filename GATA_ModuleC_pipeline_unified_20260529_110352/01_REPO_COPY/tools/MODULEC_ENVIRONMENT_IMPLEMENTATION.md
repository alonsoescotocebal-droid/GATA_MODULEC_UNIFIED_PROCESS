# Module C - Implementacion de Entorno Codex Web

Este paquete implementa perfiles de entorno para auditar y gatear Module C sin ejecutar pipeline completo.

## Archivos

- `tools/setup_profile_minus1_documental_baseline.ps1`
- `tools/setup_profile0_structural_audit.ps1`
- `tools/setup_profile1_reorg_docs.ps1`
- `tools/setup_profile2_python_smoke.ps1`
- `tools/setup_profile3_qgis_runtime.ps1`

## Uso rapido

Desde `D:\Mestrado\GATA_2025_2026\Prueba_aislada`:

```powershell
.\tools\setup_profile_minus1_documental_baseline.ps1
.\tools\setup_profile0_structural_audit.ps1
.\tools\setup_profile1_reorg_docs.ps1
.\tools\setup_profile2_python_smoke.ps1
.\tools\setup_profile3_qgis_runtime.ps1
```

## Variables configuradas

- `GATA_ROOT`
- `PIPELINE_ROOT`
- `MODULEC_DATOS`
- `INC_NEW`
- `OUTPUT_ROOT`
- `PIPELINE_OUTPUT_AUX`
- `MODULEC_EXCLUDE_GLOBS`
- `PYQGIS` (profile 3)
- `QGIS_PREFIX_PATH` (profile 3)
- `EFFECTIVE_RUNNER` (profile 3)

## NO-GO implementado

`setup_profile_minus1_documental_baseline.ps1` aborta si falta baseline documental o estructural:
- compendio, README, START_HERE, rutas canónicas, secuencia QGIS;
- `PIPELINE_ROOT`;
- `OUTPUT_ROOT` canónico;
- salida auxiliar pipeline;
- o colisión entre output canónico y auxiliar.

`setup_profile3_qgis_runtime.ps1` valida gate estructural y:
- no bloquea solo por ausencia de `run_pipeline_debug_v5.py`;
- exige wrapper `RUN_ModuleC_Pipeline_OSGeo4W.cmd`;
- exige `run_preflight_bootstrap.py`;
- exige `moduleC_pipeline.py` o `moduleC_pipeline_v2.py`;
- exige que el wrapper referencie un runner existente;
- exige `OUTPUT_ROOT` canónico.

Opcionalmente, con `-StrictRuntimeChecks`, bloquea si faltan `python-qgis-ltr.bat` o `QGIS_PREFIX_PATH`.

## Distincion de outputs

- Canónico final: `...\Complementariedad de analisis\Module C\03_outputs`
- Auxiliar pipeline: `...\_qa_catalogs\moduleC_local_pipeline\03_outputs`

## Notas

- No ejecuta pipeline completo.
- No descarga datos externos.
- No modifica datos de outputs.
- `setup_profile2_python_smoke.ps1` instala solo `pandas` en venv local para smoke tabular.
