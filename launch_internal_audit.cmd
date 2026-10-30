@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_ARGS="
if defined AUDIT_PYTHON (
  set "PYTHON_EXE=%AUDIT_PYTHON%"
  goto check_python
)
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
  goto check_python
)
if exist "%~dp0venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
  goto check_python
)
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
  goto check_python
)
where python >nul 2>nul
if errorlevel 1 goto missing_python
set "PYTHON_EXE=python"
:check_python
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import streamlit, requests, dotenv; from packaging.version import Version; assert Version(streamlit.__version__) >= Version('1.66.1')" >nul 2>nul
if errorlevel 1 goto missing_dependencies
set "LISTEN_ADDRESS=127.0.0.1"
if /i "%~1"=="--lan" (
  echo WARNING: everyone who can reach this port can view evidence and act as either reviewer.
  echo Use only a trusted private LAN. No public internet, router forwarding or tunnels.
  choice /M "Enable private LAN access for this run"
  if errorlevel 2 exit /b 0
  if not errorlevel 1 exit /b 0
  set "LISTEN_ADDRESS=0.0.0.0"
)
echo Opening Internal Comparable Review. Leave this window open while reviewing.
echo Close this window or press Ctrl+C to stop the pilot.
"%PYTHON_EXE%" %PYTHON_ARGS% -m streamlit run "apps\internal_validation_ui.py" --server.address=%LISTEN_ADDRESS% --server.port=8501 --server.headless=false --browser.serverAddress=localhost --browser.gatherUsageStats=false --client.toolbarMode=minimal --theme.baseFontSize=18
if errorlevel 1 (
  echo The pilot stopped with an error. See the message above and docs\internal-validation-pilot.md.
  pause
)
exit /b
:missing_python
echo Python was not found. Ask the host operator to install Python and configure the pilot.
echo See docs\internal-validation-pilot.md. No installation was attempted.
pause
exit /b 1
:missing_dependencies
echo The selected Python cannot load the pilot dependencies, or Streamlit is older than 1.66.1.
echo Selected Python: "%PYTHON_EXE%" %PYTHON_ARGS%
echo Ask the host operator to configure the virtual environment using docs\internal-validation-pilot.md.
echo No installation was attempted.
pause
exit /b 1
