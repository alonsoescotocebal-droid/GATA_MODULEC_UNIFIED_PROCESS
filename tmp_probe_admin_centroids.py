import time, json, sys
from pathlib import Path
repo = Path(r"D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY")
sys.path.insert(0, str(repo / 'pipeline'))
import moduleC_pipeline_v2 as mod
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(r"C:\OSGeo4W64\apps\qgis-ltr", True)
app.initQgis()
admin_gpkg = Path(r"D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\IECH_ADMIN_BISECT_STAGE4_20260708_101652\03_outputs\maps\IECH_ModuleC_master.gpkg")
t0 = time.time(); samples = mod._load_admin_unit_centroids(admin_gpkg); print(json.dumps({'rows': len(samples), 'sec': round(time.time()-t0,3)}))
QgsApplication.exitQgis()
