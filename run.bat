@echo off
setlocal
set "VENV_DIR=venv"

if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate" && pip install -r requirements.txt
) else (
    call "%VENV_DIR%\Scripts\activate"
)

call "%~dp0start_comfy.bat"

echo Starting AI Visual Workshop on http://127.0.0.1:7870
python app.py
pause
