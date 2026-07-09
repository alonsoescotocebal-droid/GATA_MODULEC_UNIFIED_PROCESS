import time, json, sys
from pathlib import Path
repo = Path(r"D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY")
sys.path.insert(0, str(repo / 'pipeline'))
import moduleC_pipeline_v2 as mod
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(r"C:\OSGeo4W64\apps\qgis-ltr", True)
app.initQgis()
gfas_dir = Path(r"D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)")
admin_gpkg = Path(r"D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\IECH_ADMIN_BISECT_STAGE4_20260708_101652\03_outputs\maps\IECH_ModuleC_master.gpkg")
out = {}
t0 = time.time(); rows = mod._load_gfas_pm_summary_rows(gfas_dir); out['gfas_rows']=len(rows); out['gfas_sec']=round(time.time()-t0,3)
t1 = time.time(); samples = mod._load_admin_unit_centroids(admin_gpkg); out['centroid_rows']=len(samples); out['centroid_sec']=round(time.time()-t1,3)
print(json.dumps(out))
QgsApplication.exitQgis()
