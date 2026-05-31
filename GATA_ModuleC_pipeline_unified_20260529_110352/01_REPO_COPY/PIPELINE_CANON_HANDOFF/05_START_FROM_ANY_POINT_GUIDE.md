# 05 Start From Any Point Guide

| Punto de inicio | Requisitos previos | Comando/Gate | Artefactos esperados | Dónde parar si falla |
|---|---|---|---|---|
| Limpieza/canon | Inventarios B0-B4.1 disponibles | Scan canon B4.1-CANON | PIPELINE_CANON_FINAL_CONTAMINATION_SCAN.csv | Primer ACTIVE_BLOCKER |
| Entorno QGIS | Canon limpio | PROFILE_3 + probes import/init | PASS de qgis.core/processing/initialize | QtCore o ModuleNotFoundError |
| Runtime ModuleC | Gate 0-3 PASS + wrapper canónico | RUN_ModuleC_Pipeline_OSGeo4W.cmd --pipeline-v2 | run_log, QA, tablas/GPKG | Primera etapa con FAIL/Traceback |
| RUN_QGIS steps | Runtime base consistente | run_qgis_step2.ps1, run_qgis_step3.ps1, run_qgis_step5_municipios.ps1 | outputs step2/3/5 | Step n con output faltante |
| Step9 | Steps previos + QA | run_step9_final_master_pack.ps1 | deliverables, final_manifest, sha | faltantes o hashes incoherentes |
| Validar runtime ya ejecutado | B4 artifacts capturados | lectura stdout/stderr/run_log/QA | decisión PASS/HOLD/NO-GO | primer error bloqueante |

Regla de parada:
- Ante NO-GO, abrir primero OUTPUT_ROOT\qa\report_auditoria_v2.txt y luego run_log.txt.
