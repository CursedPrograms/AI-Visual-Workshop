@echo off
rem Serve the UI on the whole local network (reachable as http://qwen.flask:7870).
setlocal
set "VENV_DIR=venv"
set "HOST=0.0.0.0"
set "PORT=7870"

if not exist "%VENV_DIR%" (
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate" && pip install -r requirements.txt
) else (
    call "%VENV_DIR%\Scripts\activate"
)

call "%~dp0start_comfy.bat"

echo Serving on http://0.0.0.0:%PORT%  (LAN: http://qwen.flask:%PORT%)
python app.py
pause
