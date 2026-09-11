@echo off
REM Restart your default browser (Edge or Chrome) with remote debugging on port 9222,
REM so tools can attach to YOUR running browser (record_offline_data.py 离线录制 / tools\snapshot 定时截图).
REM NOTE: all open browser windows will close (tabs/history are restored on reopen).
echo Closing Edge/Chrome...
taskkill /f /im msedge.exe >nul 2>nul
taskkill /f /im chrome.exe >nul 2>nul
timeout /t 2 /nobreak >nul

REM Browser binary search order: Microsoft Edge first (Windows default), Chrome as fallback.
set "BROWSER="
if exist "%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%PROGRAMFILES%\Google\Chrome\Application\chrome.exe" set "BROWSER=%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER (
  echo [ERROR] Neither Edge nor Chrome found. Start your browser manually with --remote-debugging-port=9222
  pause
  exit /b 1
)

set "PROFILE=%LOCALAPPDATA%\Microsoft\Edge\User Data"
if not exist "%PROFILE%" set "PROFILE=%LOCALAPPDATA%\Google\Chrome\User Data"

echo Starting: %BROWSER%
start "" "%BROWSER%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%"
echo Browser started with remote debugging on port 9222.
echo 重新打开看板页面后, 运行: python record_offline_data.py 录制离线数据
echo     或按 tools\snapshot\README.md 运行定时截图
pause
