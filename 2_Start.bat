@echo off
setlocal
title Irodori UTAU Maker
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%ProgramFiles%\Git\cmd;%PATH%"
if not exist "Irodori-TTS\infer.py" goto not_installed
echo Starting Irodori UTAU Maker. A browser page opens in a moment.
echo Keep this window open while you use the tool. Close it to quit.
cd Irodori-TTS
uv run --no-sync python "%~dp0app\utau_maker.py"
echo.
echo The tool stopped. If you see an error above, copy it and send it to Claude.
pause
exit /b 0

:not_installed
echo Irodori-TTS is not installed. Double-click 1_Install.bat first.
pause
exit /b 1
