@echo off
REM Build script for CrawlPhotos Windows exe package.
REM 宝宝照片自动筛选工具 - Windows 打包脚本.
REM
REM Usage: build.bat

echo ============================================
echo   Building CrawlPhotos.exe ...
echo ============================================

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller>=6.0
)

REM Clean previous build & __pycache__
if exist build rmdir /s /q build
if exist dist\CrawlPhotos rmdir /s /q dist\CrawlPhotos
for /d /r app %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul

REM Build with -B to suppress .pyc generation
pyinstaller -B --noconfirm --clean crawlphotos.spec

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
) else (
    echo.
    echo ============================================
    echo   Build SUCCESS!
    echo   Output: dist\CrawlPhotos\CrawlPhotos.exe
    echo ============================================
    explorer dist\CrawlPhotos
)
