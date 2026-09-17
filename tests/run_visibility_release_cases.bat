@echo off
setlocal
set "ARU_RETOPO_TEST=%~dp0visibility_release_cases.py"
set "MAYA_VER=%~1"
if not defined MAYA_VER set "MAYA_VER=2027"
set "MAYA_LOCATION=C:\Program Files\Autodesk\Maya%MAYA_VER%"
call "%~dp0..\..\..\..\..\..\..\setEnv.bat"
if errorlevel 1 exit /b 1
call "%PROJECT_ENV%\maya_env.bat"
if errorlevel 1 exit /b 1
set "MAYA_SKIP_USERSETUP_PY=1"
"%MAYA_LOCATION%\bin\mayapy.exe" -u "%ARU_RETOPO_TEST%"
exit /b %errorlevel%
