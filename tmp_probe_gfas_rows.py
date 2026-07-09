import time, json, sys
from pathlib import Path
repo = Path(r"D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY")
sys.path.insert(0, str(repo / 'pipeline'))
import moduleC_pipeline_v2 as mod
gfas_dir = Path(r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)")
t0 = time.time(); rows = mod._load_gfas_pm_summary_rows(gfas_dir); print(json.dumps({'rows': len(rows), 'sec': round(time.time()-t0,3)}))
