param(
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
Set-Location 'D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY'
& 'C:\OSGeo4W64\bin\python-qgis-ltr.bat' `
  'D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py' `
  --gata-root 'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos' `
  --modulec-datos 'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos' `
  --inc-new 'D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Incendios_Nueva version' `
  --output-root $OutputRoot
