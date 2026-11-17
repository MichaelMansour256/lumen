@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Image Enhancer - tests
if not exist logs mkdir logs
if not exist "%~dp0backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
echo [1/2] Backend tests: pipeline, API, and the real AI models on small images...
pushd "%~dp0backend"
".venv\Scripts\python.exe" -m pytest tests -v -s -rs -p no:cacheprovider > "%~dp0logs\test_backend.log" 2>&1
set "BACKERR=%ERRORLEVEL%"
popd
powershell -NoProfile -Command "Get-Content -Tail 12 -LiteralPath '%~dp0logs\test_backend.log'"

echo.
echo [2/2] Frontend production build...
pushd "%~dp0frontend"
call npm run build > "%~dp0logs\test_frontend.log" 2>&1
set "FRONTERR=%ERRORLEVEL%"
popd
powershell -NoProfile -Command "Get-Content -Tail 15 -LiteralPath '%~dp0logs\test_frontend.log'"

echo.
echo backend exit code %BACKERR%, frontend exit code %FRONTERR% > "%~dp0logs\test_summary.txt"
type "%~dp0logs\test_summary.txt"
echo Full logs: logs\test_backend.log and logs\test_frontend.log
pause
