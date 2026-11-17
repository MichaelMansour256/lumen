@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Image Enhancer
if not exist "%~dp0backend\.venv\Scripts\python.exe" (
  echo The app is not installed yet. Run setup.bat first.
  pause
  exit /b 1
)
if not exist "%~dp0frontend\node_modules" (
  echo Frontend packages are missing. Run setup.bat first.
  pause
  exit /b 1
)
echo Starting the API on http://127.0.0.1:8000 and the app on http://localhost:3000
start "Enhancer API" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe run.py"
start "Enhancer UI" /D "%~dp0frontend" cmd /k "npm run dev"
echo Waiting for the app to come up...
timeout /t 8 /nobreak >nul
start "" http://localhost:3000
echo.
echo Two windows were opened (API and UI). Close them to stop the app.
timeout /t 5 >nul
