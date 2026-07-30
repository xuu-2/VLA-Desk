@echo off
chcp 65001 >nul
echo ============================================================
echo   VLA-Desk Git 提交检查脚本
echo ============================================================
echo.

echo [1/6] 检查 Git 是否已初始化...
if not exist .git (
    echo 初始化 Git 仓库...
    git init
    echo ✅ Git 已初始化
) else (
    echo ✅ Git 已存在
)
echo.

echo [2/6] 检查 .env 文件安全性...
if exist .env (
    findstr /C:".env" .gitignore >nul
    if errorlevel 1 (
        echo ❌ 警告：.env 未在 .gitignore 中！
        echo 请先修复 .gitignore 文件
        pause
        exit /b 1
    ) else (
        echo ✅ .env 已被正确忽略
    )
) else (
    echo ⚠️  .env 文件不存在
)
echo.

echo [3/6] 清理临时文件...
if exist temp_frame.jpg del temp_frame.jpg
if exist desk.jpg del desk.jpg
if exist README_new.md del README_new.md
if exist test_api.py del test_api.py
echo ✅ 临时文件已清理
echo.

echo [4/6] 检查将要提交的文件...
echo.
git status
echo.

echo ============================================================
echo   重要检查清单：
echo ============================================================
echo   [检查] .env 文件是否在上面的列表中？
echo   [检查] temp_frame.jpg 是否在上面的列表中？
echo   [检查] *.pt 模型文件是否在上面的列表中？
echo.
echo   ❌ 如果看到上述任何文件，请按 Ctrl+C 取消并修复！
echo   ✅ 如果没有看到，说明安全，可以继续
echo ============================================================
echo.

pause
echo.

echo [5/6] 添加文件到 Git...
git add .
echo ✅ 文件已添加
echo.

echo [6/6] 再次确认将要提交的文件...
git status
echo.

echo ============================================================
echo   提交确认
echo ============================================================
echo   即将提交到: https://github.com/xuu-2/VLA-Desk
echo   分支: main
echo.
set /p confirm="确认提交？(输入 yes 继续，其他任意键取消): "

if /i "%confirm%"=="yes" (
    echo.
    echo 正在提交...
    git commit -m "feat: Complete VLA-Desk - Vision-Language-Action Desktop Assistant

Features:
- YOLOv8 object detection with Chinese labels
- Dual-mode language understanding (LLM + rule-based)
- Automatic action planning with IK solver
- PyBullet simulation with desk scene
- Modern Gradio UI with dark tech theme
- Complete test suite and documentation"

    echo.
    echo 关联远程仓库...
    git remote add origin https://github.com/xuu-2/VLA-Desk.git 2>nul
    
    echo.
    echo 推送到 GitHub...
    git branch -M main
    git push -u origin main

    if errorlevel 1 (
        echo.
        echo ❌ 推送失败！可能的原因：
        echo    1. 远程仓库已存在，使用: git push -f origin main
        echo    2. 网络问题
        echo    3. 权限问题
    ) else (
        echo.
        echo ============================================================
        echo   🎉 成功推送到 GitHub！
        echo ============================================================
        echo.
        echo   仓库地址: https://github.com/xuu-2/VLA-Desk
        echo.
        echo   下一步建议：
        echo   1. 访问 GitHub 仓库确认文件
        echo   2. 检查 .env 文件是否存在（不应该存在！）
        echo   3. 添加 Topics 标签
        echo   4. 完善仓库描述
        echo.
    )
) else (
    echo.
    echo 取消提交
)

echo.
pause
