# 10 QGIS Runtime Env Contract

Requerido:
- OSGeo4W: C:\OSGeo4W64
- QGIS_PREFIX_PATH=C:\OSGeo4W64\apps\qgis-ltr
- QT_PLUGIN_PATH=C:\OSGeo4W64\apps\qgis-ltr\qtplugins;C:\OSGeo4W64\apps\qt5\plugins
- GDAL_DATA=C:\OSGeo4W64\apps\gdal\share\gdal
- PROJ_LIB/PROJ_DATA=C:\OSGeo4W64\share\proj
- PATH con prioridad: qgis-ltr\bin, qt5\bin, Python312\Scripts, OSGeo4W\bin.
- QGIS_CUSTOM_CONFIG_PATH limpio (bajo _cleanup_control\qgis_profile_runtime).

Probes obligatorios antes de runtime:
- rom qgis.core import QgsApplication PASS
- import processing PASS
- Processing.initialize() PASS

WindowsApps warning:
- Estado actual: warning residual posible en launcher.
- Bloquea solo si rompe imports/initialize en contexto real del wrapper.
