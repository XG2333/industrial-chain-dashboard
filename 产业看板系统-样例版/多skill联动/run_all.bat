@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ============================================
echo   Industry Dashboard - Process ^& Launch
echo ============================================
echo.

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] virtualenv not found. Run setup.bat first.
  pause & exit /b 1
)

echo [1/2] Running skill pipeline on raw data (lithium/tin/silicon, 10-30 min)...
"%~dp0.venv\Scripts\python.exe" "%~dp0process_all.py" --parallel 3 %*
if errorlevel 1 (
  echo.
  echo [ERROR] Data processing failed. Check:
  echo   1. Raw files exist in 多skill联动\input\ - 碳酸锂数据库.xlsx, 锡产业链数据.xlsx, 硅产业链数据.xlsx
  echo   2. Error details in the log above
  pause & exit /b 1
)

echo [2/2] Starting dashboard ...
cd /d "%~dp0本地可视化dashboard"
REM 先启动 server(后台),再等待端口就绪,最后打开浏览器
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
  echo [WARN] Server not ready on port 8000 yet. Open http://127.0.0.1:8000 manually.
) else (
  start "" "http://127.0.0.1:8000"
)

echo.
echo ============================================
echo   Dashboard started: http://127.0.0.1:8000
echo   To stop: kill "IndustryDashboardServer" in Task Manager
echo ============================================
pause
