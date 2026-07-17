Set-Location 'D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY'
$argsList = @(
    '-u',
    'pipeline\\moduleC_pipeline_v2.py',
    '--gata-root',
    'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505',
    '--modulec-datos',
    'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos',
    '--inc-new',
    'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Incendios_Nueva version',
    '--output-root',
    'D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\IECH_WRB_AGGREGATE_STRICT_REPAIR_20260715_231752'
)
& 'C:\OSGeo4W64\bin\python-qgis-ltr.bat' @argsList
