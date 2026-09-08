@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Regenerate anonymized sample data and deploy into data/ (numbers re-randomized).
REM All Chinese file names are handled inside the python script (codepage-safe).
set "PYEXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
"%PYEXE%" gen_sample_package_data.py --deploy
if errorlevel 1 (
  echo [ERROR] generation failed.
  pause
  exit /b 1
)
echo Done. Restart the dashboard (run_all.bat) to reload new samples.
pause
