#!/bin/bash
# run_app.sh — One-click launcher for the WR Binary Analysis web app
# Usage: bash settings/run_app.sh
#
# Opens at http://localhost:8501 in your browser.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting WR Binary Analysis app..."
echo "Open http://localhost:8501 in your browser."
echo "Press Ctrl+C to stop."
echo ""

conda run -n guyenv streamlit run "$ROOT_DIR/app/app.py" \
    --server.headless false \
    --browser.gatherUsageStats false
