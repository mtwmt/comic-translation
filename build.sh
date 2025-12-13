#!/bin/bash

echo "========================================"
echo "  Comic Translator - Build Script (macOS)"
echo "========================================"
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "[Error] Python3 not found! Please install Python first."
    exit 1
fi

echo "[1/4] Upgrading pip and PyInstaller..."
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade pyinstaller
echo ""

echo "[2/4] Installing dependencies..."
pip3 install -r requirements.txt
echo ""

echo "[3/4] Building macOS application..."
echo "This may take a few minutes, please wait..."
echo ""

# macOS uses ':' as path separator for --add-data
# Note: To add a custom icon, create assets/icon.icns and add: --icon "assets/icon.icns"
pyinstaller --onedir --windowed \
    --name "ComicTranslator" \
    --add-data "src:src" \
    gui.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[Error] Build failed!"
    exit 1
fi

echo ""
echo "[4/4] Cleaning up..."
rm -rf build __pycache__ ComicTranslator.spec 2>/dev/null

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "Output location: dist/ComicTranslator.app"
echo ""
echo "To distribute: Compress the ComicTranslator.app into a .zip or .dmg"
echo "Users just need to double-click ComicTranslator.app to run!"
echo ""

# Open dist folder in Finder
open dist/
