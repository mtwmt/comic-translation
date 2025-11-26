@echo off
chcp 65001 >nul
echo ========================================
echo   Comic Translator - Build Script
echo ========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Python not found! Please install Python first.
    pause
    exit /b 1
)

echo [1/4] Upgrading pip and PyInstaller...
python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller
echo.

echo [2/4] Installing dependencies...
pip install -r requirements.txt
echo.

echo [3/4] Building executable...
echo This may take a few minutes, please wait...
echo.

pyinstaller --onedir --windowed --name "ComicTranslator" --add-data "src;src" gui.py

if %errorlevel% neq 0 (
    echo.
    echo [Error] Build failed!
    pause
    exit /b 1
)

echo.
echo [4/4] Cleaning up...
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__
if exist "ComicTranslator.spec" del "ComicTranslator.spec"

echo.
echo ========================================
echo   Build Complete!
echo ========================================
echo.
echo Output location: dist\ComicTranslator\ComicTranslator.exe
echo.
echo Please distribute the entire "ComicTranslator" folder to users.
echo Users just need to double-click ComicTranslator.exe to run!
echo.
echo Opening dist folder...
start explorer "dist"
echo.
pause
