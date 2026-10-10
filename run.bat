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

echo Starting Qwen-Image 2.1 GGUF server on http://127.0.0.1:5000
python app.py
pause
