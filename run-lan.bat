@echo off
rem Serve the UI on the whole local network (reachable as http://qwen.flask:5000).
setlocal
set "VENV_DIR=venv"
set "HOST=0.0.0.0"
set "PORT=5000"

if not exist "%VENV_DIR%" (
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate" && pip install -r requirements.txt
) else (
    call "%VENV_DIR%\Scripts\activate"
)

echo Serving on http://0.0.0.0:%PORT%  (LAN: http://qwen.flask:%PORT%)
python app.py
pause
