@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Image Enhancer - setup
if not exist logs mkdir logs
set "LOG=%~dp0logs\setup.log"
echo ==== setup started %DATE% %TIME% ==== > "%LOG%"

echo.
echo  AI Image Enhancer - setup
echo  Full log: logs\setup.log
echo.

rem ---- 1. Python 3.10 - 3.13 -------------------------------------------
set "PY="
for %%V in (3.12 3.11 3.10 3.13) do call :trypy %%V
if defined PY goto :havepy
python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
:havepy
if not defined PY (
  echo [ERROR] Python 3.10 - 3.13 was not found. Install Python 3.12 from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH", then run setup.bat again.
  echo [ERROR] no suitable Python >> "%LOG%"
  goto :fail
)
echo [1/6] Using Python: %PY%
%PY% --version >> "%LOG%" 2>&1

rem ---- 2. virtual environment ------------------------------------------
set "VPY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [2/6] Creating virtual environment in backend\.venv
  %PY% -m venv "%~dp0backend\.venv" >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail
) else (
  echo [2/6] Virtual environment already exists
)
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1

rem ---- 3. PyTorch (CUDA build when an NVIDIA GPU is present) -----------
call :detectgpu
"%VPY%" -c "import torch" >nul 2>&1
if errorlevel 1 goto :installtorch
"%VPY%" -c "import torch, sys; sys.exit(1 if torch.version.cuda is None else 0)" >nul 2>&1
if not errorlevel 1 (
  echo [3/6] PyTorch with CUDA already installed
  goto :deps
)
if not defined GPU (
  echo [3/6] PyTorch already installed - CPU build, no NVIDIA GPU detected
  goto :deps
)
echo [3/6] NVIDIA GPU found but the installed PyTorch is CPU-only - replacing it
"%VPY%" -m pip uninstall -y torch torchvision >> "%LOG%" 2>&1

:installtorch
if not defined GPU (
  echo [3/6] No NVIDIA GPU detected - installing CPU-only PyTorch
  "%VPY%" -m pip install torch torchvision >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail
  goto :deps
)
echo [3/6] Installing PyTorch with CUDA - about 2.5 GB, this can take 10+ minutes...
for %%C in (cu128 cu126 cu130 cu124) do call :trytorch %%C
"%VPY%" -c "import torch, sys; sys.exit(1 if torch.version.cuda is None else 0)" >nul 2>&1
if errorlevel 1 (
  echo       CUDA builds failed - falling back to CPU-only PyTorch
  "%VPY%" -m pip uninstall -y torch torchvision >> "%LOG%" 2>&1
  "%VPY%" -m pip install torch torchvision >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail
)

:deps
)
nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo [3/6] No NVIDIA driver found - installing CPU-only PyTorch
  echo nvidia-smi not found, CPU torch >> "%LOG%"
  "%VPY%" -m pip install torch torchvision >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail
  goto :deps
)
echo [3/6] Installing PyTorch with CUDA - about 2.5 GB, this can take 10+ minutes...
for %%C in (cu126 cu124 cu121) do call :trytorch %%C
"%VPY%" -c "import torch" >nul 2>&1
if errorlevel 1 (
  echo       CUDA builds failed - falling back to CPU-only PyTorch
  "%VPY%" -m pip install torch torchvision >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail
)

:deps
rem ---- 4. backend packages ----------------------------------------------
echo [4/6] Installing backend packages
"%VPY%" -m pip install -r "%~dp0backend\requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 goto :fail
echo ---- environment check ---- >> "%LOG%"
"%VPY%" -c "import torch, spandrel, cv2, fastapi; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '| cuda build', torch.version.cuda, '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only'); print('spandrel', spandrel.__version__, '| opencv', cv2.__version__, '| fastapi', fastapi.__version__)" > "%~dp0logs\environment.txt" 2>&1
type "%~dp0logs\environment.txt"
type "%~dp0logs\environment.txt" >> "%LOG%"
if defined GPU "%VPY%" -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if defined GPU if errorlevel 1 (
  echo [WARN] PyTorch cannot use the NVIDIA GPU. Update the NVIDIA driver from nvidia.com and run setup.bat again.
  echo [WARN] GPU present but torch.cuda.is_available is False >> "%LOG%"
)

rem ---- 5. model weights --------------------------------------------------
echo [5/6] Downloading AI models - about 425 MB, from the official GitHub releases
"%VPY%" "%~dp0backend\scripts\download_models.py"
if errorlevel 1 echo [WARN] Some models failed to download. Run setup.bat again to retry.
"%VPY%" "%~dp0backend\scripts\download_models.py" --list >> "%LOG%" 2>&1

rem ---- 6. frontend --------------------------------------------------------
where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js was not found. Install the LTS version from https://nodejs.org/ and run setup.bat again.
  echo [ERROR] node not found >> "%LOG%"
  goto :fail
)
echo [6/6] Installing frontend packages
pushd "%~dp0frontend"
call npm install >> "%LOG%" 2>&1
set "NPMERR=%ERRORLEVEL%"
popd
if not "%NPMERR%"=="0" goto :fail

echo ==== setup finished OK %DATE% %TIME% ==== >> "%LOG%"
echo.
echo  Setup complete. Start the app with start.bat
echo.
pause
exit /b 0

:trypy
if defined PY exit /b 0
py -%1 -c "import sys" >nul 2>&1 && set "PY=py -%1"
exit /b 0

:detectgpu
set "GPU="
echo ---- GPU detection ---- >> "%LOG%"
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }" >> "%LOG%" 2>&1
powershell -NoProfile -Command "if (Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like '*NVIDIA*' }) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 set "GPU=1"
where nvidia-smi >nul 2>&1
if not errorlevel 1 set "GPU=1"
if exist "%SystemRoot%\System32\nvidia-smi.exe" set "GPU=1"
if exist "%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe" set "GPU=1"
if defined GPU (echo NVIDIA GPU detected >> "%LOG%") else (echo no NVIDIA GPU detected >> "%LOG%")
exit /b 0

:trytorch
"%VPY%" -c "import torch, sys; sys.exit(1 if torch.version.cuda is None else 0)" >nul 2>&1
if not errorlevel 1 exit /b 0
echo       trying build %1
echo ---- torch %1 ---- >> "%LOG%"
"%VPY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/%1 >> "%LOG%" 2>&1
exit /b 0

:fail
echo ==== setup FAILED %DATE% %TIME% ==== >> "%LOG%"
echo.
echo  Setup failed. Last lines of logs\setup.log:
echo  ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 25 -LiteralPath '%LOG%'"
echo.
pause
exit /b 1
