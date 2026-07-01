@echo off
chcp 65001 >nul 2>&1
title 情侣相册 - 运行
echo.
echo   ========================================
echo     💕 情侣相册 - 桌面版 💕
echo   ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   错误：找不到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 检查依赖
python -c "import webview" >nul 2>&1
if %errorlevel% neq 0 (
    echo   正在安装依赖...
    pip install pywebview -q
)

echo   正在启动相册...
echo.
python "%~dp0src\app.py"
pause
