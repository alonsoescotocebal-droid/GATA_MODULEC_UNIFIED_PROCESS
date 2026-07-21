@echo off
echo BLOCKED_NON_CANONICAL_LAUNCHER
echo Use: ..\..\02_LAUNCHERS\run_modulec_canonical.ps1
exit /b 97

setlocal

set "GATA_ROOT=D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505"
set "REPO=%GATA_ROOT%\_qa_catalogs\moduleC_local_pipeline"
set "PIPE=%REPO%\moduleC_pipeline_v2.py"
set "PYQGIS=C:\OSGeo4W64\bin\python-qgis-ltr.bat"
set "QGIS_PREFIX_PATH=C:\OSGeo4W64\apps\qgis-ltr"
set "PYTHONPATH=C:\OSGeo4W64\apps\qgis-ltr\python;C:\OSGeo4W64\apps\qgis-ltr\python\plugins;%PYTHONPATH%"
set "PATH=C:\OSGeo4W64\bin;C:\OSGeo4W64\apps\qgis-ltr\bin;%PATH%"

if not exist "%PIPE%" (
  echo [FATAL] No existe: %PIPE%
  exit /b 1
)
if not exist "%PYQGIS%" (
  echo [FATAL] No existe: %PYQGIS%
  exit /b 1
)

cd /d "%REPO%"

call "%PYQGIS%" -c "import sys,os; sys.path.insert(0,r'C:\OSGeo4W64\apps\qgis-ltr\python'); sys.path.insert(0,r'C:\OSGeo4W64\apps\qgis-ltr\python\plugins'); os.environ['QGIS_PREFIX_PATH']=r'C:\OSGeo4W64\apps\qgis-ltr'; from qgis.core import QgsApplication; QgsApplication.setPrefixPath(r'C:\OSGeo4W64\apps\qgis-ltr', True); qgs=QgsApplication([], False); qgs.initQgis(); import processing; print('processing.__file__', getattr(processing,'__file__',None)); from processing.core.Processing import Processing; Processing.initialize(); print('OK'); qgs.exitQgis()"
if errorlevel 1 (
  echo [FATAL] QGIS/processing import failed. Aborting.
  exit /b 1
)

call "%PYQGIS%" -u "%PIPE%" --gata-root "%GATA_ROOT%" --modulec-datos "%GATA_ROOT%\Complementariedad de analisis\Module C\Datos" --inc-new "%GATA_ROOT%\Incendios_Nueva version" > "%REPO%\_console_run_v2_qgispython.log" 2>&1

endlocal

