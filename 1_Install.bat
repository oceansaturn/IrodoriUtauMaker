@echo off
setlocal
title Irodori UTAU Maker - Install
cd /d "%~dp0"
echo ============================================================
echo  Irodori UTAU Maker - one-time installation
echo  This step downloads about 6 GB. Keep this window open.
echo ============================================================
echo.

rem ---- 1. uv (installs Python and the libraries) ----
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto have_uv
echo [1/4] Installing uv ...
powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul
if errorlevel 1 goto fail_uv
:have_uv
echo [1/4] uv is ready.

rem ---- 2. Git (some Irodori-TTS libraries need it) ----
set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
where git >nul 2>nul
if not errorlevel 1 goto have_git
echo [2/4] Installing Git ...
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
where git >nul 2>nul
if errorlevel 1 goto fail_git
:have_git
echo [2/4] Git is ready.

rem ---- 3. Irodori-TTS program ----
if exist "Irodori-TTS\infer.py" goto have_repo
echo [3/4] Downloading Irodori-TTS ...
git clone --depth 1 https://github.com/Aratako/Irodori-TTS.git
if not exist "Irodori-TTS\infer.py" goto fail_repo
:have_repo
echo [3/4] Irodori-TTS is ready.

rem ---- 4. Libraries (NVIDIA graphics card = fast, other = slow CPU mode) ----
set "EXTRA=cpu"
nvidia-smi >nul 2>nul
if not errorlevel 1 set "EXTRA=cu128"
echo [4/4] Installing libraries (mode: %EXTRA%). This step takes 5 to 20 minutes ...
cd Irodori-TTS
uv sync --extra %EXTRA%
if errorlevel 1 goto fail_sync
uv pip install scipy numpy gradio
if errorlevel 1 goto fail_sync
cd ..

echo.
echo ============================================================
echo  Installation complete. Now double-click 2_Start.bat
if "%EXTRA%"=="cpu" echo  NOTE: No NVIDIA graphics card found. Generation will be slow.
echo ============================================================
pause
exit /b 0

:fail_uv
echo ERROR: uv did not install. Close this window and run 1_Install.bat again.
goto end
:fail_git
echo ERROR: Git did not install. Install it from https://git-scm.com/download/win
echo Then run 1_Install.bat again.
goto end
:fail_repo
echo ERROR: The Irodori-TTS download failed. Check the internet connection.
goto end
:fail_sync
echo ERROR: The library installation failed. Copy the text above and send it to Claude.
:end
pause
exit /b 1
