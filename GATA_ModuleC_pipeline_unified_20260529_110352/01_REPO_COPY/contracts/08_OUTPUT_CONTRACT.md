# 08 Output Contract

OUTPUT_ROOT canónico:
$outputRoot

## Mínimo para arrancar gate pre-runtime
- maps\IECH_ModuleC_master.gpkg
- 	ables\IECH_unit_2015_2024.csv
- 	ables\pop_unit_2015_2025_2030.csv
- 	ables\recurrence_unit_2015_2024.csv
- 	ables\IECH_scenarios_2026_2030.csv
- 	ables\smoke_days_unit_2015_2024.csv (puede quedar EXPECTED_REGENERATE_BY_RUNTIME)
- qa\run_log.txt
- qa\QA_checks.csv
- qa\inputs_resolved.json

## Deben regenerarse por runtime
- qa\report_auditoria_v2.txt
- 	ables\smoke_days_unit_2015_2024.csv (si aplica recalculo)
- deliverables_step9\*
- inal_manifest.json
- inal_sha256_checkpoints.txt

## No copiar desde backup sin gate
- maps\IECH_ModuleC_master.gpkg
- qa\inputs_resolved.json
- cualquier archivo con hash conflictivo.

## Decisión
- PASS: outputs coherentes + QA sin FAIL + sin rutas prohibidas.
- HOLD: faltantes regenerables o warnings pendientes.
- NO-GO: incoherencia, mezcla de rutas, backup activo o QA FAIL.
