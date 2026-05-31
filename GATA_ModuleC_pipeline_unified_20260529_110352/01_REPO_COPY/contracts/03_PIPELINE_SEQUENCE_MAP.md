# 03 Pipeline Sequence Map

| Etapa | Script/Responsable | Inputs esperados | Outputs esperados | PASS | HOLD | NO-GO | Dependencia |
|---|---|---|---|---|---|---|---|
| 0. Gate documental/canon | tools\setup_profile_minus1_documental_baseline.ps1 | Canon de rutas, contratos vigentes | Validación documental | Baseline PASS | evidencia incompleta | rutas canónicas inválidas | Se puede ejecutar sola |
| 1. Gate limpieza repo | scan canon B3.1/B3.2/B4.1 | Inventarios + registros legacy | Matriz contaminación | ACTIVE_BLOCKER=0 | warnings por revisar | blocker activo | Depende de 0 |
| 2. Gate wrapper/rutas | RUN_ModuleC_Pipeline_OSGeo4W.cmd (estático) | Wrapper canónico | Validación de rutas/vars | sin HOST_ROOT, rutas canónicas | check parcial | rutas legacy activas | Depende de 1 |
| 3. Gate entorno QGIS | PROFILE_3 + probes B3.3/B4.1 | OSGeo4W, env vars | PASS import/init | qgis.core + processing + initialize PASS | warning no bloqueante | QtCore/processing FAIL | Depende de 2 |
| 4. Preflight | run_preflight_bootstrap.py | Gates 0-3 PASS | Preflight report/env | preflight sin FAIL crítico | faltantes corregibles | entorno/rutas inválidas | Depende de 3 |
| 5. Runtime ModuleC v2 | RUN_ModuleC_Pipeline_OSGeo4W.cmd --pipeline-v2 -> moduleC_pipeline_v2.py | inputs_resolved + datos canónicos | tablas/maps/qa runtime | exitcode+QA coherentes | ejecución parcial | traceback/fallo bloqueante | Depende de 4 |
| 6. QA gate | qa_gate_v2.py | Outputs runtime | QA_checks.csv actualizado | sin FAIL | WARN tolerables | FAIL QA real | Depende de 5 |
| 7. RUN_QGIS Step2/3/5 | run_qgis_step2.ps1, run_qgis_step3.ps1, run_qgis_step5_municipios.ps1 | outputs base + runtime coherente | artefactos qgis step2/3/5 | steps completan | step intermedio pendiente | error en step crítico | Depende de 5/6 |
| 8. Step7 matriz causal | RUN_QGIS\STEP7_MATRIZ_CAUSAL\run_step7_matriz_causal.ps1 | resultados step previos | causal matrix outputs | matrix válida | salida parcial | falla de generación | Depende de 7 |
| 9. Step8 brief pack | RUN_QGIS\STEP8_BRIEF_PACK\run_step8_brief_pack.ps1 | step7 completo | brief pack | pack generado | warning menor | no genera pack | Depende de 8 |
| 10. Step9 final master pack | RUN_QGIS\STEP9_FINAL_MASTER_PACK\run_step9_final_master_pack.ps1 | step8 + outputs completos | deliverables_step9, finales | deliverables+manifests coherentes | faltante menor documentado | falta Step9 esperado | Depende de 9 |
| 11. Validación final | plan B4 post-runtime | run_log, QA, CSV, GPKG, manifests | decisión final | todo coherente | warning no bloqueante | incoherencia de outputs | Depende de 10 |

Notas:
- Etapas 0-4 son gates; no sustituyen runtime final.
- deliverables_step9 histórico de backup nunca se usa como cierre.
