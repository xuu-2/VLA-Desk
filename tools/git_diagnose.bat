@echo off
chcp 65001 >nul
echo ============================================================
echo   Git 推送问题诊断工具
echo ============================================================
echo.

cd f:\Learn\VibeCoding\VLA-Desk

echo [1] 检查 Git 状态
echo ----------------------------------------
git status
echo.

echo [2] 检查远程仓库配置
echo ----------------------------------------
git remote -v
echo.

echo [3] 检查当前分支
echo ----------------------------------------
git branch
echo.

echo [4] 检查最近的提交
echo ----------------------------------------
git log --oneline -3
echo.

echo [5] 尝试连接 GitHub
echo ----------------------------------------
ping github.com -n 2
echo.

echo ============================================================
echo   诊断完成！
echo ============================================================
echo.

echo 根据上面的信息：
echo.
echo 如果看到 "origin  https://github.com/xuu-2/VLA-Desk.git"
echo   → 远程仓库配置正确 ✅
echo.
echo 如果看到 "* main" 或 "* master"
echo   → 分支名称 ✅
echo.
echo 如果能 ping 通 github.com
echo   → 网络连接正常 ✅
echo.
echo ============================================================
echo   推荐的解决方案：
echo ============================================================
echo.
echo 方案 A（安全，推荐）：
echo   git pull origin main --allow-unrelated-histories
echo   git push origin main
echo.
echo 方案 B（快速，会覆盖远程）：
echo   git push -f origin main
echo.
echo 方案 C（重新开始）：
echo   rmdir /s .git
echo   git init
echo   git add .
echo   git commit -m "Initial commit"
echo   git remote add origin https://github.com/xuu-2/VLA-Desk.git
echo   git push -f origin main
echo.

pause
