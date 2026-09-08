@echo off
chcp 936 >nul
cd /d "%~dp0"
setlocal
echo ============================================
echo   Industry Dashboard (Sample Data) Setup
echo ============================================
echo.

REM --- skip if already configured ---
if exist "%~dp0.venv\Scripts\python.exe" if exist "%~dp0.setup_done" (
  echo Environment already configured. Run run_all.bat to start.
  pause
  exit /b 0
)

REM ---- 1. Detect / auto-install Python ----
set "PYEXE="
set "PYARG="
where py >nul 2>nul && (set "PYEXE=py" & set "PYARG=-3")
if not defined PYEXE (
  where python >nul 2>nul && set "PYEXE=python"
)
if defined PYEXE (
  "%PYEXE%" %PYARG% --version >nul 2>nul || (set "PYEXE=" & set "PYARG=")
)
if not defined PYEXE (
  echo [1/3] Python not found. Installing Python 3.12 via winget ...
  winget install --id Python.Python.3.12 --exact --silent --accept-source-agreements --accept-package-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if not defined PYEXE (
    if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
  )
)
if not defined PYEXE (
  echo [ERROR] Python install failed. Please install Python 3.10+ manually and rerun.
  echo         Download: https://www.python.org/downloads/
  pause
  exit /b 1
)
echo [1/3] Python ready.
"%PYEXE%" %PYARG% --version

REM ---- 2. Create virtualenv ----
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [2/3] Creating virtualenv .venv ...
  "%PYEXE%" %PYARG% -m venv "%~dp0.venv"
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] virtualenv creation failed.
  pause
  exit /b 1
)

REM ---- 3. Install deps ----
echo [3/3] Installing Python dependencies (first run 2-4 min)...
"%~dp0.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0dashboard\requirements.txt"
if errorlevel 1 (
  echo [ERROR] pip install failed. Check network and rerun setup.bat
  pause
  exit /b 1
)

type nul > "%~dp0.setup_done"
echo.
echo ============================================
echo   Setup complete!
echo   Next: run run_all.bat to start the dashboard
echo ============================================
pause
