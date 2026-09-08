@echo off
chcp 936 >nul
cd /d "%~dp0"
setlocal
echo ============================================
echo   Industry Dashboard - One-Click Setup
echo ============================================
echo.

REM ---- 1. Detect / install Python ----
REM 优先 py launcher（真正安装的 Python 才有）；where python 可能命中
REM Microsoft Store 的 App Execution Alias（假 python），需验证能运行
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
  echo [1/5] Python not found. Trying winget install Python 3.12 ...
  winget install --id Python.Python.3.12 --exact --silent --accept-source-agreements --accept-package-agreements >nul 2>nul
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if not defined PYEXE (
    if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
  )
)
if not defined PYEXE (
  echo [ERROR] Python install failed. Install Python 3.11+ manually, then rerun setup.bat
  echo         Download: https://www.python.org/downloads/
  pause & exit /b 1
)
echo [1/5] Python ready: %PYEXE% %PYARG%
"%PYEXE%" %PYARG% --version

REM ---- 2. Create virtualenv ----
echo [2/5] Creating virtualenv .venv ...
if not exist "%~dp0.venv\Scripts\python.exe" (
  "%PYEXE%" %PYARG% -m venv "%~dp0.venv"
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] virtualenv creation failed
  pause & exit /b 1
)

REM ---- 3. Install Python deps ----
echo [3/5] Installing Python dependencies (first run 1-3 min)...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo [ERROR] pip install failed. Check network and retry.
  pause & exit /b 1
)

REM ---- 4. Detect / install Node.js ----
echo [4/5] Checking Node.js ...
set "NODEEXE="
set "NPMCLI="
where node >nul 2>nul && set "NODEEXE=node"
if defined NODEEXE (
  "%NODEEXE%" --version >nul 2>nul || set "NODEEXE="
)
REM npm 11+ npm.cmd resolves node_modules\npm relative to cwd and fails
REM when missing; call npm-cli.js directly via node instead
if defined NODEEXE (
  if exist "%~dp0node_modules\npm\bin\npm-cli.js" set "NPMCLI=%~dp0node_modules\npm\bin\npm-cli.js"
)
if not defined NPMCLI (
  if exist "%ProgramFiles%\nodejs\node_modules\npm\bin\npm-cli.js" set "NPMCLI=%ProgramFiles%\nodejs\node_modules\npm\bin\npm-cli.js"
)
if not defined NPMCLI (
  if exist "%LOCALAPPDATA%\Programs\nodejs\node_modules\npm\bin\npm-cli.js" set "NPMCLI=%LOCALAPPDATA%\Programs\nodejs\node_modules\npm\bin\npm-cli.js"
)
if not defined NPMCLI (
  if exist "%APPDATA%\npm\node_modules\npm\bin\npm-cli.js" set "NPMCLI=%APPDATA%\npm\node_modules\npm\bin\npm-cli.js"
)
REM fallback: probe npm-cli.js next to wherever node actually lives
if not defined NPMCLI (
  for /f "delims=" %%N in ('where node 2^>nul') do (
    if not defined NPMCLI if exist "%%~dpNnode_modules\npm\bin\npm-cli.js" set "NPMCLI=%%~dpNnode_modules\npm\bin\npm-cli.js"
  )
)
if not defined NPMCLI (
  echo Node.js incomplete. Trying winget install LTS ...
  winget install --id OpenJS.NodeJS.LTS --exact --silent --accept-source-agreements --accept-package-agreements >nul 2>nul
  if exist "%ProgramFiles%\nodejs\node.exe" set "NODEEXE=%ProgramFiles%\nodejs\node.exe"
  if exist "%ProgramFiles%\nodejs\node_modules\npm\bin\npm-cli.js" set "NPMCLI=%ProgramFiles%\nodejs\node_modules\npm\bin\npm-cli.js"
  if not defined NPMCLI (
    if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "NODEEXE=%LOCALAPPDATA%\Programs\nodejs\node.exe"
    if exist "%LOCALAPPDATA%\Programs\nodejs\node_modules\npm\bin\npm-cli.js" set "NPMCLI=%LOCALAPPDATA%\Programs\nodejs\node_modules\npm\bin\npm-cli.js"
  )
)
if not defined NPMCLI (
  echo [ERROR] Node.js install failed. Install Node.js 18+ manually, then rerun setup.bat
  echo         Download: https://nodejs.org/
  pause & exit /b 1
)
echo Node.js ready: %NODEEXE%
echo npm-cli: %NPMCLI%

REM ---- 5. Frontend deps + build (node + npm-cli.js, bypass npm.cmd) ----
echo [5/5] Installing frontend deps and building (first run 2-5 min)...
if exist "%~dp0node_modules" rmdir /s /q "%~dp0node_modules"
set "DASH=%~dp0本地可视化dashboard"
if not exist "%DASH%\frontend\package.json" (
  echo [ERROR] frontend/package.json not found: %DASH%\frontend
  pause & exit /b 1
)
cd /d "%DASH%\frontend"
"%NODEEXE%" "%NPMCLI%" install
if errorlevel 1 ( echo [ERROR] npm install failed & pause & exit /b 1 )
"%NODEEXE%" "%NPMCLI%" run build
if errorlevel 1 ( echo [ERROR] npm run build failed & pause & exit /b 1 )
cd /d "%~dp0"

REM ---- 6. Generate .env (python: UTF-16 args, no codepage issues) ----
"%~dp0.venv\Scripts\python.exe" "%~dp0configure_env.py"
if errorlevel 1 ( echo [ERROR] .env configuration failed & pause & exit /b 1 )

echo.
echo ============================================
echo   Setup complete!
echo   Next: run run_all.bat to process raw data and start the dashboard
echo ============================================
pause
