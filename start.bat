@echo off
chcp 65001 >nul
echo ================================================
echo   面向三农场景的直播电商人工智能辅助平台
echo   AI-Powered Live Commerce Assistant for Agriculture
echo ================================================
echo.
echo [1/3] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

echo [2/3] 安装依赖包...
pip install -r backend\requirements.txt -q

echo [3/3] 安装Playwright浏览器...
python -m playwright install chromium

echo.
echo ================================================
echo   启动平台服务...
echo ================================================
echo.
cd backend
python main.py
pause
