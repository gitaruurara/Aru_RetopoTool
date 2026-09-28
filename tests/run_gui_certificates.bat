@echo off
setlocal
set "ARU_RETOPO_TEST=%~dp0gui_certificates.py"
set "MAYA_VER=%~1"
if not defined MAYA_VER set "MAYA_VER=2027"
set "MAYA_LOCATION=C:\Program Files\Autodesk\Maya%MAYA_VER%"
call "%~dp0..\..\..\..\..\..\..\setEnv.bat"
if errorlevel 1 exit /b 1
call "%PROJECT_ENV%\maya_env.bat"
if errorlevel 1 exit /b 1
set "MAYA_SKIP_USERSETUP_PY=1"
set "ARU_MAYA_MCP_PORT=50018"
"%MAYA_LOCATION%\bin\maya.exe" -noAutoloadPlugins -command "python(\"import Aru_RetopoTool.tests.gui_certificates\")"
exit /b %errorlevel%
