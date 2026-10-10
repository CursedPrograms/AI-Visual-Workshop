$VenvDir = "venv"

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..."
    python -m venv $VenvDir
    & "$VenvDir\Scripts\Activate.ps1"
    pip install -r requirements.txt
} else {
    & "$VenvDir\Scripts\Activate.ps1"
}

Write-Host "Starting Qwen-Image 2.1 GGUF server on http://127.0.0.1:5000"
python app.py
