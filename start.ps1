# Banking Query Copilot - Startup Script (PowerShell)
# Loads the model via Foundry Local and launches the Streamlit app.

$ErrorActionPreference = "Stop"

$ModelName = if ($env:MODEL_NAME) { $env:MODEL_NAME } else { "qwen2.5-0.5b" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[1/4] Checking Python virtual environment..."
$VenvActivate = Join-Path $ScriptDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Host "ERROR: Virtual environment not found at .venv\" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv"
    Write-Host "Then: .venv\Scripts\Activate.ps1; pip install -r requirements.txt"
    exit 1
}
& $VenvActivate

Write-Host "[2/4] Checking Foundry Local is installed..."
$FoundryCli = Get-Command foundry -ErrorAction SilentlyContinue
if (-not $FoundryCli) {
    Write-Host "ERROR: Foundry Local CLI not found." -ForegroundColor Red
    Write-Host "Install it with: winget install Microsoft.FoundryLocal"
    exit 1
}

Write-Host "[3/4] Loading model $ModelName into Foundry Local..."
& foundry model run $ModelName --prompt "ready" --ttl 900 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Could not load model. The app will start but may use demo mode." -ForegroundColor Yellow
}

Write-Host "[4/4] Starting Streamlit app..."
Write-Host "Open http://localhost:8501 in your browser."
$AppPath = Join-Path $ScriptDir "app.py"
& streamlit run $AppPath
