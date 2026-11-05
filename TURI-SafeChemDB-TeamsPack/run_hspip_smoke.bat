@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist "config\env.bat" call "config\env.bat"
if not defined HSPIP_PATH (
  echo HSPIP_PATH not set. Configure config\env.bat first.
  echo This smoke script only documents CLI availability — it does not run a full batch.
  exit /b 1
)
if not exist "%HSPIP_PATH%\HSPiP.exe" if not exist "%HSPIP_PATH%\hspip.exe" (
  echo WARNING: HSPiP.exe not found under HSPIP_PATH=%HSPIP_PATH%
  exit /b 1
)
echo HSPIP_PATH=%HSPIP_PATH%
echo HSPIP_DATA=%HSPIP_DATA%
echo Close the HSPiP GUI before CLI use. Prefer sofx via HSPIP_DATA for DoSS.
echo Open glue: app\vendors\cas_to_hspip\HSPiP_CLI_v7.py
echo Smoke OK ^(paths present^). Not invoking CLI automatically.
endlocal
