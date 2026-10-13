@echo off
rem Start ComfyUI in its own window unless it already answers; called by run.bat and run-lan.bat.
rem   COMFYUI_DIR   ComfyUI folder (default C:\cc\ComfyUI)
rem   COMFYUI_ARGS  flags for main.py (default: the README's)
rem   COMFY_SERVER  skipped when this points at another machine
setlocal
if not defined COMFYUI_DIR set "COMFYUI_DIR=C:\cc\ComfyUI"
if not defined COMFYUI_ARGS set "COMFYUI_ARGS=--disable-comfy-compiler --disable-dynamic-vram --disable-async-offload --cache-ram 6 16"
if not defined COMFY_SERVER set "COMFY_SERVER=http://127.0.0.1:8188"

echo %COMFY_SERVER% | findstr /i "127.0.0.1 localhost" >nul || (
    echo Using ComfyUI at %COMFY_SERVER%
    exit /b 0
)

curl -s -o nul "%COMFY_SERVER%/system_stats" && (
    echo ComfyUI already running at %COMFY_SERVER%
    exit /b 0
)

if not exist "%COMFYUI_DIR%\main.py" (
    echo ComfyUI not found in %COMFYUI_DIR% - set COMFYUI_DIR or start it yourself.
    exit /b 0
)

set "COMFY_PY=python"
if exist "%COMFYUI_DIR%\venv\Scripts\python.exe" set "COMFY_PY=%COMFYUI_DIR%\venv\Scripts\python.exe"

echo Starting ComfyUI from %COMFYUI_DIR% ...
rem cmd /k keeps the window open if ComfyUI crashes, so the error stays readable.
start "ComfyUI" /D "%COMFYUI_DIR%" cmd /k ""%COMFY_PY%" main.py %COMFYUI_ARGS%"

for /l %%i in (1,1,90) do (
    timeout /t 2 /nobreak >nul
    curl -s -o nul "%COMFY_SERVER%/system_stats" && (
        echo ComfyUI is up.
        exit /b 0
    )
)
echo ComfyUI did not answer after 3 minutes - check its window.
exit /b 0
