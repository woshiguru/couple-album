@echo off
chcp 65001 >nul 2>&1
title 情侣相册 - 打包
echo.
echo   ========================================
echo     💕 情侣相册 - 打包工具 💕
echo   ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   错误：找不到 Python
    pause
    exit /b 1
)

REM 安装打包工具
pip install pyinstaller -q

echo   正在打包...
echo.

REM 执行打包
pyinstaller --noconfirm ^
    --name "情侣相册" ^
    --add-data "index.html;." ^
    --add-data "ffmpeg;ffmpeg" ^
    --add-data "src;src" ^
    --hidden-import "webview" ^
    --hidden-import "webview.platforms.edgechromium" ^
    --windowed ^
    --clean ^
    --icon "icon.ico" ^
    src\app.py

if %errorlevel% neq 0 (
    echo.
    echo   打包失败！
    pause
    exit /b 1
)

echo.
echo   打包完成！
echo   输出目录: dist\情侣相册
echo.

REM 复制 storage 到输出目录
echo   复制数据文件...
xcopy /E /I /Y "storage" "dist\情侣相册\storage" >nul

echo.
echo   ========================================
echo     完成！可以把 dist\情侣相册 文件夹
echo     发给别人使用了
echo   ========================================
pause
