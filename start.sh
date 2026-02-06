#!/usr/bin/env bash
# Banking Query Copilot - Startup Script (macOS / Linux)
# Loads the model via Foundry Local and launches the Streamlit app.

set -e

MODEL_NAME="${MODEL_NAME:-qwen2.5-0.5b}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/4] Checking Python virtual environment..."
if [ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    echo "ERROR: Virtual environment not found at .venv/"
    echo "Run: python -m venv .venv"
    echo "Then: source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi
source "$SCRIPT_DIR/.venv/bin/activate"

echo "[2/4] Checking Foundry Local is installed..."
if ! command -v foundry &> /dev/null; then
    echo "ERROR: Foundry Local CLI not found."
    echo "Install it with:"
    echo "  brew tap microsoft/foundrylocal"
    echo "  brew install foundrylocal"
    exit 1
fi

echo "[3/4] Loading model $MODEL_NAME into Foundry Local..."
foundry model run "$MODEL_NAME" --prompt "ready" --ttl 900 > /dev/null 2>&1 || {
    echo "WARNING: Could not load model. The app will start but may use demo mode."
}

echo "[4/4] Starting Streamlit app..."
echo "Open http://localhost:8501 in your browser."
streamlit run "$SCRIPT_DIR/app.py"
