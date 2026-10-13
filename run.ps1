$VenvDir = "venv"

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..."
    python -m venv $VenvDir
    & "$VenvDir\Scripts\Activate.ps1"
    pip install -r requirements.txt
} else {
    & "$VenvDir\Scripts\Activate.ps1"
}

# Start ComfyUI in its own window unless it already answers (see start_comfy.bat).
$ComfyDir = if ($env:COMFYUI_DIR) { $env:COMFYUI_DIR } else { "C:\cc\ComfyUI" }
$ComfyArgs = if ($env:COMFYUI_ARGS) { $env:COMFYUI_ARGS } else { "--disable-comfy-compiler --disable-dynamic-vram --disable-async-offload --cache-ram 6 16" }
$ComfyServer = if ($env:COMFY_SERVER) { $env:COMFY_SERVER } else { "http://127.0.0.1:8188" }
function Test-Comfy { try { Invoke-WebRequest "$ComfyServer/system_stats" -UseBasicParsing -TimeoutSec 2 | Out-Null; $true } catch { $false } }

if ($ComfyServer -notmatch "127\.0\.0\.1|localhost") {
    Write-Host "Using ComfyUI at $ComfyServer"
} elseif (Test-Comfy) {
    Write-Host "ComfyUI already running at $ComfyServer"
} elseif (-not (Test-Path "$ComfyDir\main.py")) {
    Write-Host "ComfyUI not found in $ComfyDir - set COMFYUI_DIR or start it yourself."
} else {
    $ComfyPy = if (Test-Path "$ComfyDir\venv\Scripts\python.exe") { "$ComfyDir\venv\Scripts\python.exe" } else { "python" }
    Write-Host "Starting ComfyUI from $ComfyDir ..."
    # cmd /k keeps the window open if ComfyUI crashes, so the error stays readable.
    Start-Process cmd -ArgumentList "/k", "`"`"$ComfyPy`" main.py $ComfyArgs`"" -WorkingDirectory $ComfyDir
    $up = $false
    for ($i = 0; $i -lt 90 -and -not $up; $i++) { Start-Sleep 2; $up = Test-Comfy }
    if ($up) { Write-Host "ComfyUI is up." } else { Write-Host "ComfyUI did not answer after 3 minutes - check its window." }
}

Write-Host "Starting AI Visual Workshop on http://127.0.0.1:5000"
python app.py
