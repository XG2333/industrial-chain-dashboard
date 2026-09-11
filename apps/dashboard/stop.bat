@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "server.pid" (
    echo server.pid not found. The dashboard server may not be running.
    exit /b 0
)

set /p SERVER_PID=<server.pid
netstat -ano | findstr ":8000" | findstr /c:"%SERVER_PID%" >nul 2>nul
if errorlevel 1 (
    del "server.pid" >nul 2>nul
    echo server.pid is stale. No dashboard process is listening on port 8000.
    exit /b 0
)
taskkill /PID %SERVER_PID% /F >nul 2>nul
del "server.pid" >nul 2>nul
echo Market Dashboard Server stopped.
