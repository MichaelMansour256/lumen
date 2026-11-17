@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Lumen - public server
if not exist "%~dp0backend\.venv\Scripts\python.exe" (
  echo The app is not installed yet. Run setup.bat first.
  pause
  exit /b 1
)

rem ---- cloudflared -----------------------------------------------------
set "CF="
where cloudflared >nul 2>&1
if not errorlevel 1 set "CF=cloudflared"
if not defined CF if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not defined CF if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
if not defined CF if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe" set "CF=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
if defined CF goto :haveCF
echo Cloudflare's free tunnel tool (cloudflared) is not installed.
choice /c YN /m "Install it now with winget"
if errorlevel 2 goto :nocf
winget install --id Cloudflare.cloudflared -e
echo.
echo Close this window and run start_public.bat again so Windows picks up the new program.
pause
exit /b 0
:nocf
echo Install it with:  winget install --id Cloudflare.cloudflared
pause
exit /b 1
:haveCF

rem ---- one-time settings -------------------------------------------------
if exist "%~dp0backend\.env.public" goto :haveEnv
echo First run: this creates backend\.env.public with a new access key.
set /p "SITE=Paste your Vercel site address (for example https://lumen.vercel.app): "
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0backend\scripts\make_public_env.py" "%SITE%"
if errorlevel 1 (
  pause
  exit /b 1
)
:haveEnv

rem ---- start the API in public mode, then the tunnel ------------------------
start "Lumen API (public)" /D "%~dp0backend" cmd /k "set ENHANCER_ENV_FILE=.env.public&& .venv\Scripts\python.exe run.py"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backend\scripts\tunnel.ps1" -Cloudflared "%CF%"
pause
