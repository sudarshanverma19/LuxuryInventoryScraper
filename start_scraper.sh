#!/usr/bin/env bash
# ===================================================================
#  InventoryScraper - One-Click Launcher (macOS / Linux)
#
#  First time:  chmod +x start_scraper.sh
#  Then:        ./start_scraper.sh  (or double-click from Finder)
# ===================================================================

set -e

# -- Resolve script directory (works even if symlinked) --
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$BACKEND_DIR/requirements.txt"
PORT=8000
URL="http://127.0.0.1:$PORT"

echo ""
echo "  ==================================================="
echo "    InventoryScraper - Dashboard Launcher"
echo "  ==================================================="
echo ""

# -- Helper: open URL in default browser --
open_browser() {
    local url="$1"
    if command -v open &>/dev/null; then
        open "$url"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$url"
    elif command -v wslview &>/dev/null; then
        wslview "$url"
    else
        echo "  Could not auto-open browser. Open manually: $url"
    fi
}

# -----------------------------------------------------------
#  Step 1: Find Python 3
# -----------------------------------------------------------
echo "  [1/5] Checking for Python..."

PYTHON_CMD=""

if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PY_MAJOR=$(python -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "2")
    if [ "$PY_MAJOR" = "3" ]; then
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo ""
    echo "  ERROR: Python 3 is not installed or not in PATH."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  Install via Homebrew:  brew install python3"
        echo "  Or download from:     https://www.python.org/downloads/"
    else
        echo "  Install via package manager:"
        echo "    Ubuntu/Debian:  sudo apt install python3 python3-venv python3-pip"
        echo "    Fedora/RHEL:    sudo dnf install python3 python3-pip"
        echo "    Or download:    https://www.python.org/downloads/"
    fi
    echo ""
    exit 1
fi

PY_VERSION=$($PYTHON_CMD --version 2>&1)
echo "        OK - Found $PY_VERSION"

# -----------------------------------------------------------
#  Step 2: Create Virtual Environment
# -----------------------------------------------------------
echo "  [2/5] Setting up virtual environment..."

if [ -f "$VENV_DIR/bin/python" ]; then
    echo "        OK - Virtual environment exists"
else
    echo "        Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo ""
        echo "  ERROR: Failed to create virtual environment."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  Try: $PYTHON_CMD -m pip install --upgrade pip virtualenv"
        else
            echo "  Try: sudo apt install python3-venv  (on Ubuntu/Debian)"
        fi
        echo ""
        exit 1
    fi
    echo "        OK - Virtual environment created"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# -----------------------------------------------------------
#  Step 3: Install Dependencies
# -----------------------------------------------------------
echo "  [3/5] Checking dependencies..."

DEPS_MARKER="$VENV_DIR/.deps_installed"

NEED_INSTALL=false

if [ ! -f "$DEPS_MARKER" ]; then
    NEED_INSTALL=true
elif [ "$REQUIREMENTS" -nt "$DEPS_MARKER" ]; then
    NEED_INSTALL=true
fi

if [ "$NEED_INSTALL" = true ]; then
    echo "        Installing Python packages (this may take a minute)..."
    "$VENV_PIP" install -r "$REQUIREMENTS" --quiet --disable-pip-version-check
    if [ $? -ne 0 ]; then
        echo ""
        echo "  ERROR: Failed to install dependencies."
        echo "  Check your internet connection and try again."
        echo ""
        exit 1
    fi
    touch "$DEPS_MARKER"
    echo "        OK - Dependencies installed"
else
    echo "        OK - Dependencies already installed"
fi

# -----------------------------------------------------------
#  Step 4: Install Playwright Browsers
# -----------------------------------------------------------
echo "  [4/5] Checking Playwright browsers..."

PW_MARKER="$VENV_DIR/.playwright_installed"

if [ -f "$PW_MARKER" ]; then
    echo "        OK - Playwright browsers ready"
else
    echo "        Installing Chromium browser (one-time download, ~150MB)..."
    "$VENV_PYTHON" -m playwright install chromium
    if [ $? -ne 0 ]; then
        echo ""
        echo "  ERROR: Failed to install Playwright browsers."
        echo "  Try running manually: $VENV_PYTHON -m playwright install chromium"
        echo ""
        exit 1
    fi

    # Install system dependencies on Linux (not needed on macOS)
    if [[ "$OSTYPE" != "darwin"* ]]; then
        echo "        Installing system dependencies for Chromium..."
        "$VENV_PYTHON" -m playwright install-deps chromium 2>/dev/null || {
            echo "        WARNING: Could not auto-install system deps. If scraping fails, run:"
            echo "           sudo $VENV_PYTHON -m playwright install-deps chromium"
        }
    fi

    touch "$PW_MARKER"
    echo "        OK - Playwright browsers installed"
fi

# -----------------------------------------------------------
#  Step 5: Launch Server
# -----------------------------------------------------------
echo "  [5/5] Starting server..."
echo ""
echo "  ---------------------------------------------------"
echo "    Dashboard will open at: $URL"
echo "    Press Ctrl+C to stop the server"
echo "  ---------------------------------------------------"
echo ""

# Open browser after a short delay
(sleep 3 && open_browser "$URL") &
BROWSER_PID=$!

# Handle Ctrl+C gracefully
cleanup() {
    echo ""
    echo "  Server stopped."
    echo ""
    kill $BROWSER_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start the server (blocks until Ctrl+C)
cd "$BACKEND_DIR"
"$VENV_PYTHON" main.py
