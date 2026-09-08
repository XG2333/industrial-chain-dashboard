@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ============================================
echo   Industry Dashboard (Sample Data) - Launch
echo ============================================
echo.

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] virtualenv not found. Run setup.bat first.
  pause & exit /b 1
)

echo Starting dashboard on http://127.0.0.1:8000 ...
cd /d "%~dp0dashboard"
start "IndustryDashboardServer" "%~dp0.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000 --log-level warning
cd /d "%~dp0"
set "READY="
for /l %%i in (1,1,90) do (
  netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>nul
  if not errorlevel 1 (
    set "READY=1"
    goto server_ready
  )
  timeout /t 1 /nobreak >nul
)
:server_ready
if not defined READY (
  echo.
  echo [WARN] Server not ready yet. Open http://127.0.0.1:8000 manually.
) else (
  start "" "http://127.0.0.1:8000"
)
echo.
echo ============================================
echo   Dashboard started: http://127.0.0.1:8000
echo   Data = anonymized sample Excel in data/ (numbers random each regenerate)
echo   To stop: close this window or kill IndustryDashboardServer
echo ============================================
pause
