@echo off
setlocal
cd /d "%~dp0"
echo.
echo   ChargeSynth AI - Station Planning Studio
echo.
if exist ".venv\Scripts\python.exe" goto check_packages
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Python could not be started. Install Python 3.11 or newer from python.org.
    echo Then close this window and run start_windows.bat again.
    pause
    exit /b 1
)
:check_packages
if exist ".venv\chargesynth_installed.txt" goto launch
echo Installing required packages. Internet is needed for this first setup.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Installation failed. Check your internet connection and try again.
    pause
    exit /b 1
)
echo installed>".venv\chargesynth_installed.txt"
:launch
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
