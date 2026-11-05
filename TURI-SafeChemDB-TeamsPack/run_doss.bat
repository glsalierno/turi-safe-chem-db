@echo off
title TURI Safe Chem DB - DoSS
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: Python was not found on PATH.
  echo.
  echo Please install Python 3.10 or newer from https://www.python.org/downloads/
  echo During setup, CHECK the box: "Add python.exe to PATH"
  echo Then close this window and double-click 1_Open_Safe_Chem_DB.bat again.
  echo.
  echo Full instructions: Install_Python_for_TURI_Safe_Chem_DB.docx in this folder.
  echo.
  pause
  exit /b 1
)

if not exist "app\requirements.txt" (
  echo ERROR: app\ tree missing. This pack is incomplete.
  pause
  exit /b 1
)

if not exist "app\.venv\Scripts\python.exe" (
  echo Creating virtualenv app\.venv ...
  python -m venv "app\.venv"
  if errorlevel 1 (
    echo ERROR: failed to create venv
    pause
    exit /b 1
  )
  echo Installing requirements (first run can take several minutes^)...
  "app\.venv\Scripts\python.exe" -m pip install --upgrade pip
  "app\.venv\Scripts\python.exe" -m pip install -r "app\requirements.txt"
  if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
  )
  if exist "app\requirements-ecosar.txt" (
    echo Installing optional ECOSAR support (pyepisuite^)...
    "app\.venv\Scripts\python.exe" -m pip install -r "app\requirements-ecosar.txt"
  )
) else (
  rem Keep ECOSAR client available when default-on; quiet no-op if already installed
  if exist "app\requirements-ecosar.txt" (
    "app\.venv\Scripts\python.exe" -m pip install -q -r "app\requirements-ecosar.txt"
  )
)

if exist "config\env.bat" (
  call "config\env.bat"
) else (
  echo NOTE: config\env.bat not found — using env.bat.example defaults inline.
  if exist "config\env.bat.example" call "config\env.bat.example"
)

set "PYTHONPATH=%CD%\app;%PYTHONPATH%"
cd /d "%CD%\app"
echo Launching TURI Safe Chem DB - DoSS on-demand on http://localhost:8502 ...
".venv\Scripts\python.exe" -m streamlit run "apps\doss_ondemand\app.py" --server.port 8502
endlocal