# 01 Canonical Folder Map

## Canon operativo
- GATA_ROOT: D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505
- PIPELINE_ROOT (único código activo): D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\_qa_catalogs\moduleC_local_pipeline
- OUTPUT_ROOT (única salida final): D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\03_outputs
- DATOS_MODC (entrada masiva protegida): D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos
- INC_NEW (entrada protegida): D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version
- CONTROL_ROOT (auditoría y planes): D:\Mestrado\GATA_2025_2026\Prueba_aislada\_cleanup_control\ISO_GATA_RECONCILIATION_20260518_201808

## Separación obligatoria
- Código activo: solo en PIPELINE_ROOT.
- Datos: no se mueven ni se reordenan.
- Outputs finales: solo en OUTPUT_ROOT.
- Backups/archivos históricos: solo referencia, no baseline.

## Rutas explícitamente no válidas como output final
- D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\_qa_catalogs\moduleC_local_pipeline\03_outputs
- D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\03_outputs
- ...\03_outputs__BACKUP*
- ...\__links_nospace\03_outputs
