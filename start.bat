@echo off
chcp 65001 >nul
echo ========================================
echo   🤖 VLA-Desk 桌面助手启动脚本
echo ========================================
echo.

echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装或不在 PATH 中
    echo 请先安装 Python 3.10 或更高版本
    pause
    exit /b 1
)
echo ✅ Python 环境正常

echo.
echo [2/3] 检查依赖包...
pip show gradio >nul 2>&1
if errorlevel 1 (
    echo ⚠️  检测到缺少依赖，正在安装...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo ❌ 依赖安装失败，请手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo ✅ 依赖安装完成
) else (
    echo ✅ 依赖包已安装
)

echo.
echo [3/3] 启动应用...
echo.
echo ========================================
echo   界面将在浏览器中打开
echo   访问地址: http://127.0.0.1:7860
echo   按 Ctrl+C 停止服务器
echo ========================================
echo.

python app.py

pause
