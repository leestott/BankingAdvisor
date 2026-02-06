@echo off
REM Banking Query Copilot - Startup Script (Windows CMD)
REM Loads the model via Foundry Local and launches the Streamlit app.

setlocal

if not defined MODEL_NAME set MODEL_NAME=qwen2.5-0.5b
set SCRIPT_DIR=%~dp0

echo [1/4] Checking Python virtual environment...
if not exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at .venv\
    echo Run: python -m venv .venv
    echo Then: .venv\Scripts\activate ^&^& pip install -r requirements.txt
    exit /b 1
)
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

echo [2/4] Checking Foundry Local is installed...
where foundry >nul 2>&1
if errorlevel 1 (
    echo ERROR: Foundry Local CLI not found.
    echo Install it with: winget install Microsoft.FoundryLocal
    exit /b 1
)

echo [3/4] Loading model %MODEL_NAME% into Foundry Local...
foundry model run %MODEL_NAME% --prompt "ready" --ttl 900 >nul 2>&1
if errorlevel 1 (
    echo WARNING: Could not load model. The app will start but may use demo mode.
)

echo [4/4] Starting Streamlit app...
echo Open http://localhost:8501 in your browser.
streamlit run "%SCRIPT_DIR%app.py"

endlocal
