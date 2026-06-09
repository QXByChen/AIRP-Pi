#!/usr/bin/env sh
cd "$(dirname "$0")"

echo "========================================"
echo "  AIRP-Pi Setup"
echo "========================================"
echo

# 1/4: Check Python
echo "[1/4] Checking Python..."
python3 --version > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "  [ERROR] Python not found. Install Python 3.10+"
    echo "  https://www.python.org/downloads/"
    exit 1
fi
echo "  [OK] Python installed"

# 2/4: Check Node.js
echo "[2/4] Checking Node.js..."
node --version > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "  [ERROR] Node.js not found. Install Node.js 20+"
    echo "  https://nodejs.org/"
    exit 1
fi
echo "  [OK] Node.js installed"

# 3/4: Install dependencies
echo "[3/4] Installing dependencies..."
npm install --silent
cd "$(dirname "$0")/skills"
npm install --silent
cd "$(dirname "$0")"
echo "  [OK] Dependencies installed"

# 4/4: Deploy model config
echo "[4/4] Deploying model config..."
mkdir -p "$HOME/.pi/agent"
if [ ! -f "$HOME/.pi/agent/models.json" ]; then
    cp "$(dirname "$0")/models.json" "$HOME/.pi/agent/models.json"
    echo "  [OK] DeepSeek model config deployed"
else
    echo "  [OK] Model config exists"
fi

echo
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo
echo "Usage:"
echo "  ./start-rp.sh to launch"
echo "  First run will open browser for API Key setup"
echo "  Then drag-and-drop character card PNG to play"
echo

read -p "Press Enter to continue..."
