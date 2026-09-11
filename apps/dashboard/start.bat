@echo off
chcp 936 >nul
cd /d "%~dp0"

REM 检测 8000 已监听则直接打开浏览器
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo Market Dashboard Server already running.
  start "" "http://127.0.0.1:8000"
  exit /b 0
)

REM 定位 python:源项目场景 venv 在本目录,部署包场景 venv 在包根
set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo [ERROR] Python venv not found. Run setup.bat in the package root first.
  pause
  exit /b 1
)

echo ============================================
echo Market Dashboard Server
echo URL: http://127.0.0.1:8000
echo ============================================
echo Starting background server...

REM 与 run_all.bat 相同方式启动 server(已验证可行)
start "IndustryDashboardServer" "%PYEXE%" -m uvicorn server:app --host 127.0.0.1 --port 8000 --log-level warning

REM 等待端口就绪(最多 90 秒),然后打开浏览器
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
if defined READY (
  echo.
  echo Dashboard started: http://127.0.0.1:8000
  start "" "http://127.0.0.1:8000"
) else (
  echo.
  echo [WARN] Server not ready on port 8000 yet. Open http://127.0.0.1:8000 manually.
)
pause
exit /b 0
