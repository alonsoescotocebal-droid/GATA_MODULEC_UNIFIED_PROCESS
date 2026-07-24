@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ===== CANONICAL RUNNER: export mode only (ISO diagnostic reference only) =====

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "SCRIPT_DIR=%%~fI"
for %%I in ("%SCRIPT_DIR%") do set "PIPELINE_ROOT=%%~fI"
for %%I in ("%PIPELINE_ROOT%\..") do set "REPO_ROOT=%%~fI"
for %%I in ("%REPO_ROOT%\..\..") do set "GIT_ROOT=%%~fI"

set "PYQGIS=C:\OSGeo4W64\bin\python-qgis-ltr.bat"
set "PIPEPY=%PIPELINE_ROOT%\moduleC_pipeline_v2.py"
set "QAGATE=%PIPELINE_ROOT%\qa_gate_v2.py"
set "PREFLIGHT_BOOTSTRAP=%PIPELINE_ROOT%\run_preflight_bootstrap.py"
set "PREFLIGHT_PY=%PIPELINE_ROOT%\moduleC_preflight.py"
set "OBJECTIVES_GATE=%PIPELINE_ROOT%\validate_modulec_objectives_canon.py"
set "PATH_SCOPE_GUARD=%PIPELINE_ROOT%\path_scope_guard.py"
set "SCIENTIFIC_GATE=%PIPELINE_ROOT%\scientific_threshold_gate.py"
set "PATH_SCOPE_CONFIG=%REPO_ROOT%\config\module_c_canonical_paths.json"

for %%I in ("%PIPELINE_ROOT%") do set "PIPELINE_DIRNAME=%%~nxI"
if /I "%PIPELINE_DIRNAME%"=="moduleC_local_pipeline" (
  echo [NO-GO] BLOCKED_FORBIDDEN_CODE_ROOT
  exit /b 21
)
if /I not "%PIPELINE_DIRNAME%"=="pipeline" (
  echo [NO-GO] BLOCKED_REPO_ROOT_MISMATCH
  echo          expected runner root dirname: pipeline
  echo          observed runner root dirname: %PIPELINE_DIRNAME%
  exit /b 22
)

set "RUNMODE=EXPORT"
set "ISO_DIAGNOSTIC_REFERENCE_ONLY=1"

set "LOCAL_PATHS_PS1=%REPO_ROOT%\config\local_paths.ps1"
if exist "!LOCAL_PATHS_PS1!" (
  set "NEED_LOCAL_CONFIG="
  if not defined GATA_REPO_ROOT set "NEED_LOCAL_CONFIG=1"
  if not defined GATA_EXTERNAL_DATOS_MODC set "NEED_LOCAL_CONFIG=1"
  if not defined GATA_EXTERNAL_INC_NEW set "NEED_LOCAL_CONFIG=1"
  if not defined GATA_EXTERNAL_OUTPUT_ROOT set "NEED_LOCAL_CONFIG=1"
  if defined NEED_LOCAL_CONFIG (
    for /f "usebackq tokens=1,* delims==" %%A in ("!LOCAL_PATHS_PS1!") do (
      set "K=%%A"
      set "V=%%B"
      if /I "!K:~0,10!"=="$env:GATA_" (
        set "K=!K:$env:=!"
        set "K=!K: =!"
        for /f "tokens=* delims= " %%Z in ("!V!") do set "V=%%Z"
        set "V=!V:"=!"
        if not defined !K! set "!K!=!V!"
      )
    )
  )
)

if not defined GATA_REPO_ROOT set "GATA_REPO_ROOT=%REPO_ROOT%"
if /I not "!GATA_REPO_ROOT!"=="%REPO_ROOT%" (
  echo [NO-GO] BLOCKED_REPO_ROOT_MISMATCH
  echo          expected: %REPO_ROOT%
  echo          observed: !GATA_REPO_ROOT!
  exit /b 23
)

if not defined GATA_EXTERNAL_DATOS_MODC (
  echo [NO-GO] Missing GATA_EXTERNAL_DATOS_MODC. Define env var or config\local_paths.ps1.
  exit /b 24
)
if not defined GATA_EXTERNAL_OUTPUT_ROOT (
  echo [NO-GO] Missing GATA_EXTERNAL_OUTPUT_ROOT. Define env var or config\local_paths.ps1.
  exit /b 25
)

set "DATOS_MODC=!GATA_EXTERNAL_DATOS_MODC!"
set "OUTPUT_ROOT=!GATA_EXTERNAL_OUTPUT_ROOT!"
if defined GATA_EXTERNAL_INC_NEW (
  set "INC_NEW=!GATA_EXTERNAL_INC_NEW!"
) else (
  for %%I in ("!DATOS_MODC!\..\..\..") do set "ISO_ROOT_GUESS=%%~fI"
  set "INC_NEW=!ISO_ROOT_GUESS!\Incendios_Nueva version"
)

rem --- Runtime env canonico
set "OSGEO4W_ROOT=C:\OSGeo4W64"
set "QGIS_PREFIX_PATH=%OSGEO4W_ROOT%\apps\qgis-ltr"
set "QT_PLUGIN_PATH=%QGIS_PREFIX_PATH%\qtplugins;%OSGEO4W_ROOT%\apps\qt5\plugins"
set "GDAL_DATA=%OSGEO4W_ROOT%\apps\gdal\share\gdal"
set "GDAL_DRIVER_PATH=%OSGEO4W_ROOT%\apps\gdal\lib\gdalplugins"
set "PROJ_LIB=%OSGEO4W_ROOT%\share\proj"
set "PROJ_DATA=%OSGEO4W_ROOT%\share\proj"
set "GISBASE=%OSGEO4W_ROOT%\apps\grass\grass84"
set "GRASS_PROJSHARE=%OSGEO4W_ROOT%\share\proj"
set "PYTHONHOME=%OSGEO4W_ROOT%\apps\Python312"
set "PYTHONUTF8=1"
set "QGIS_CUSTOM_CONFIG_PATH=%OUTPUT_ROOT%\qa\qgis_profile_runtime"
if not exist "%QGIS_CUSTOM_CONFIG_PATH%" mkdir "%QGIS_CUSTOM_CONFIG_PATH%" >nul 2>&1
set "PATH=%QGIS_PREFIX_PATH%\bin;%OSGEO4W_ROOT%\apps\grass\grass84\lib;%OSGEO4W_ROOT%\apps\grass\grass84\bin;%OSGEO4W_ROOT%\apps\qt5\bin;%OSGEO4W_ROOT%\apps\Python312\Scripts;%OSGEO4W_ROOT%\bin;C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem"
set "Path=%PATH%"

set "WANTHELP=0"
for %%A in (%*) do (
  if "%%~A"=="--help" set "WANTHELP=1"
  if "%%~A"=="-h" set "WANTHELP=1"
)

set "MODE="
set "EXTRA="
if /I "%~1"=="--pipeline-v2" (
  set "MODE=PIPE"
  shift
) else if /I "%~1"=="--qa-gate" (
  set "MODE=QA"
  shift
)

:collect_extra
if "%~1"=="" goto after_args
set "EXTRA=!EXTRA! %~1"
shift
goto collect_extra

:after_args
if "%MODE%"=="" (
  if "%WANTHELP%"=="1" (
    echo [USAGE]
    echo   RUN_ModuleC_Pipeline_OSGeo4W.cmd --pipeline-v2 [extra args]
    echo   RUN_ModuleC_Pipeline_OSGeo4W.cmd --qa-gate     [extra args]
    exit /b 0
  )
  echo [FAIL] Debes indicar --pipeline-v2 o --qa-gate
  exit /b 2
)

if "%WANTHELP%"=="0" (
  if not exist "%PIPELINE_ROOT%" (echo [NO-GO] PIPELINE_ROOT missing: "%PIPELINE_ROOT%" & exit /b 30)
  if not exist "%REPO_ROOT%" (echo [NO-GO] REPO_ROOT missing: "%REPO_ROOT%" & exit /b 30)
  if not exist "%DATOS_MODC%" (echo [NO-GO] DATOS_MODC missing: "%DATOS_MODC%" & exit /b 34)
  if not exist "%INC_NEW%" (echo [NO-GO] INC_NEW missing: "%INC_NEW%" & exit /b 35)
  if not exist "%QGIS_PREFIX_PATH%" (echo [NO-GO] QGIS_PREFIX_PATH missing: "%QGIS_PREFIX_PATH%" & exit /b 37)
  if not exist "%OSGEO4W_ROOT%\apps\qt5\bin\Qt5Core.dll" (echo [NO-GO] Qt5Core.dll missing in "%OSGEO4W_ROOT%\apps\qt5\bin" & exit /b 38)
  if not exist "%PYQGIS%" (echo [FAIL] PYQGIS missing: "%PYQGIS%" & exit /b 31)
  if not exist "%PIPEPY%" (echo [FAIL] PIPEPY missing: "%PIPEPY%" & exit /b 32)
  if not exist "%QAGATE%" (echo [FAIL] QAGATE missing: "%QAGATE%" & exit /b 33)
  if not exist "%PREFLIGHT_BOOTSTRAP%" (echo [FAIL] PREFLIGHT_BOOTSTRAP missing: "%PREFLIGHT_BOOTSTRAP%" & exit /b 36)
  if not exist "%PREFLIGHT_PY%" (echo [FAIL] PREFLIGHT_PY missing: "%PREFLIGHT_PY%" & exit /b 40)
  if not exist "%OBJECTIVES_GATE%" (echo [FAIL] OBJECTIVES_GATE missing: "%OBJECTIVES_GATE%" & exit /b 41)
  if not exist "%PATH_SCOPE_GUARD%" (echo [FAIL] PATH_SCOPE_GUARD missing: "%PATH_SCOPE_GUARD%" & exit /b 42)
  if not exist "%PATH_SCOPE_CONFIG%" (echo [FAIL] PATH_SCOPE_CONFIG missing: "%PATH_SCOPE_CONFIG%" & exit /b 43)
  if not exist "%SCIENTIFIC_GATE%" (echo [FAIL] SCIENTIFIC_GATE missing: "%SCIENTIFIC_GATE%" & exit /b 44)
  if not exist "%OUTPUT_ROOT%" (
    for %%I in ("%OUTPUT_ROOT%\..") do set "_OUT_PARENT=%%~fI"
    if not exist "!_OUT_PARENT!" (
      echo [NO-GO] OUTPUT_ROOT parent missing: "!_OUT_PARENT!"
      exit /b 39
    )
  )
)

set "PYGUARD=C:\OSGeo4W64\apps\Python312\python.exe"
if not exist "%PYGUARD%" set "PYGUARD=python"

echo [RUN] PATH_SCOPE_GUARD
call "%PYGUARD%" -u "%PATH_SCOPE_GUARD%" --repo-root "%REPO_ROOT%" --pipeline-root "%PIPELINE_ROOT%" --git-toplevel "%GIT_ROOT%" --data-root "%DATOS_MODC%" --output-root "%OUTPUT_ROOT%" --config-path "%PATH_SCOPE_CONFIG%" --enforce-clean-tree 0
if errorlevel 1 (
  set "PSG_RC=!ERRORLEVEL!"
  echo [NO-GO] BLOCKED_PATH_DESYNC path_scope_guard_exit=!PSG_RC!
  exit /b !PSG_RC!
)

echo [MODE] %RUNMODE%
echo [ROOT] REPO_ROOT=%REPO_ROOT%
echo [ROOT] DATOS_MODC=%DATOS_MODC%
echo [ROOT] INC_NEW=%INC_NEW%
echo [ROOT] OUTPUT_ROOT=%OUTPUT_ROOT%
echo [INFO] ISO_DIAGNOSTIC_REFERENCE_ONLY=%ISO_DIAGNOSTIC_REFERENCE_ONLY%

if /I "%MODE%"=="QA" goto MODE_QA
if /I "%MODE%"=="PIPE" goto MODE_PIPE
echo [FAIL] Invalid MODE value: "%MODE%"
exit /b 2

:MODE_PIPE
echo [RUN] OBJECTIVES GATE (pre)
call "%PYQGIS%" -u "%OBJECTIVES_GATE%" --output-root "%OUTPUT_ROOT%" --repo-root "%REPO_ROOT%" --mode pre
if errorlevel 1 (
  set "OBJ_PRE_RC=!ERRORLEVEL!"
  echo [HOLD] Objectives pre-gate failed with exit code !OBJ_PRE_RC!
  exit /b !OBJ_PRE_RC!
)
echo [RUN] PREFLIGHT
call "%PYQGIS%" -u "%PREFLIGHT_BOOTSTRAP%" --gata-root "%REPO_ROOT%" --modulec-datos "%DATOS_MODC%" --inc-new "%INC_NEW%" --output-root "%OUTPUT_ROOT%"
if errorlevel 1 (
  set "PF_RC=!ERRORLEVEL!"
  echo [HOLD] Preflight failed with exit code !PF_RC!
  exit /b !PF_RC!
)
echo [RUN] PIPELINE v2
call "%PYQGIS%" -u "%PIPEPY%" --gata-root "%REPO_ROOT%" --modulec-datos "%DATOS_MODC%" --inc-new "%INC_NEW%" --output-root "%OUTPUT_ROOT%" %EXTRA%
exit /b %ERRORLEVEL%

:MODE_QA
echo [RUN] QA GATE v2
call "%PYQGIS%" -u "%QAGATE%" --gata-root "%REPO_ROOT%" --modulec-datos "%DATOS_MODC%" --inc-new "%INC_NEW%" --output-root "%OUTPUT_ROOT%" %EXTRA%
set "QA_RC=%ERRORLEVEL%"
echo [RUN] SCIENTIFIC THRESHOLD GATE
call "%PYGUARD%" -u "%SCIENTIFIC_GATE%" --output-root "%OUTPUT_ROOT%" --repo-root "%REPO_ROOT%"
set "SCI_RC=%ERRORLEVEL%"
echo [RUN] OBJECTIVES GATE (post)
call "%PYQGIS%" -u "%OBJECTIVES_GATE%" --output-root "%OUTPUT_ROOT%" --repo-root "%REPO_ROOT%" --mode post
set "OBJ_POST_RC=%ERRORLEVEL%"
if not "%QA_RC%"=="0" exit /b %QA_RC%
if not "%SCI_RC%"=="0" exit /b %SCI_RC%
if not "%OBJ_POST_RC%"=="0" exit /b %OBJ_POST_RC%
exit /b 0
