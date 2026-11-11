@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo uv was not found. Installing it now...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo.
        echo Could not install uv automatically.
        echo Install it from https://docs.astral.sh/uv/getting-started/installation/ and run this file again.
        pause
        exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo Starting Recipe Studio...
uv run --frozen python -m RecipeStudio
if errorlevel 1 (
    echo.
    echo Recipe Studio exited with an error.
    echo Copy the text above if you need help.
    pause
)
