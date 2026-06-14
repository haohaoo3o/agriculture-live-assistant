@echo off
chcp 65001 >nul
title 智农直播助手 - 三农直播电商AI辅助平台

echo ================================================
echo   面向三农场景的直播电商人工智能辅助平台
echo   AI-Powered Live Commerce Assistant for Agriculture
echo ================================================
echo.

echo [1/4] 检查 Python 环境...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo       下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo [OK] Python 环境正常
echo.

echo [2/4] 检查依赖包...
pip install -r backend\requirements.txt -q --disable-pip-version-check 2>nul
if %errorlevel% neq 0 (
    echo [警告] 依赖安装可能有误，尝试继续...
)
echo [OK] 依赖检查完成
echo.

echo [3/4] 检查 Playwright 浏览器...
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 首次使用，正在安装 Chromium 浏览器（约150MB，仅需一次）...
    python -m playwright install chromium
    if %errorlevel% neq 0 (
        echo [警告] Chromium 安装失败，请手动执行: python -m playwright install chromium
    )
)
echo [OK] Playwright 就绪
echo.

echo [4/4] 检查 API Key 配置...
if exist ".env" (
    echo [OK] 已找到 .env 配置文件
) else if exist ".env.example" (
    echo [警告] 未找到 .env 文件！
    echo       请复制 .env.example 为 .env 并填入你的 API Key
    echo       详见 README.md
) else (
    echo [警告] 未配置 API Key，AI功能将不可用
)
echo.

echo ================================================
echo   启动平台服务...
echo   访问地址: http://localhost:8000
echo   按 Ctrl+C 停止服务
echo ================================================
echo.

cd /d "%~dp0backend"
python main.py

echo.
echo 服务已停止
pause
