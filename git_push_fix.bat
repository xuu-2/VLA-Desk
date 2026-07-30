@echo off
chcp 65001 >nul
echo ============================================================
echo   VLA-Desk Git 推送修复脚本
echo ============================================================
echo.

cd f:\Learn\VibeCoding\VLA-Desk

echo [检查] 当前 Git 状态...
git status
echo.

echo ============================================================
echo   选择推送方式：
echo ============================================================
echo.
echo   1. 拉取远程内容后推送（推荐，安全）
echo   2. 强制推送（会覆盖远程内容）
echo   3. 查看详细错误信息
echo   4. 退出
echo.
set /p choice="请选择 (1-4): "

if "%choice%"=="1" (
    echo.
    echo [方案 1] 拉取远程内容后推送...
    echo.
    
    echo 步骤 1: 拉取远程内容...
    git pull origin main --allow-unrelated-histories
    
    if errorlevel 1 (
        echo.
        echo ⚠️  拉取失败或有冲突
        echo 请手动解决冲突后执行：
        echo   git add .
        echo   git commit -m "Merge remote and local"
        echo   git push origin main
        pause
        exit /b 1
    )
    
    echo.
    echo 步骤 2: 推送到 GitHub...
    git push origin main
    
    if errorlevel 1 (
        echo.
        echo ❌ 推送仍然失败
        echo 尝试使用方案 2（强制推送）
        pause
        exit /b 1
    ) else (
        echo.
        echo ✅ 推送成功！
        echo.
        echo 访问: https://github.com/xuu-2/VLA-Desk
    )
)

if "%choice%"=="2" (
    echo.
    echo [方案 2] 强制推送（覆盖远程内容）...
    echo.
    echo ⚠️  警告：这会覆盖远程仓库的所有内容！
    echo.
    set /p confirm="确认强制推送？(输入 yes 继续): "
    
    if /i "%confirm%"=="yes" (
        echo.
        echo 正在强制推送...
        git push -f origin main
        
        if errorlevel 1 (
            echo.
            echo ❌ 强制推送失败
            echo 可能的原因：
            echo   1. 网络问题
            echo   2. 权限问题（需要 GitHub 登录）
            echo   3. 仓库地址错误
            echo.
            echo 当前远程地址：
            git remote -v
        ) else (
            echo.
            echo ✅ 强制推送成功！
            echo.
            echo 访问: https://github.com/xuu-2/VLA-Desk
        )
    ) else (
        echo 取消强制推送
    )
)

if "%choice%"=="3" (
    echo.
    echo [详细信息]
    echo.
    echo 当前分支：
    git branch
    echo.
    echo 远程仓库：
    git remote -v
    echo.
    echo 提交历史：
    git log --oneline -5
    echo.
    echo 尝试推送（查看详细错误）：
    git push origin main -v
)

echo.
pause
