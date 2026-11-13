@echo off
title 岔路 - 三路径决策支持系统
cd /d %~dp0

echo ==========================================
echo   岔路 - 三路径职业决策支持系统
echo ==========================================
echo.

REM 检查是否已解压
if not exist backend\main.py (
    echo [错误] 未找到 backend 文件夹
    echo 请先把 zip 解压出来，进入解压后的文件夹再双击本脚本
    echo 不要在压缩包窗口里直接双击！
    echo.
    pause
    exit /b 1
)

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python
    echo.
    echo 请先安装 Python 3.10 或更高版本：
    echo   1. 打开 https://www.python.org/downloads/ 下载安装
    echo   2. 安装第一屏务必勾选 Add python.exe to PATH
    echo   3. 装完后重新双击本脚本
    echo.
    pause
    exit /b 1
)

REM 首次运行自动安装依赖
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [首次运行] 正在安装依赖，请保持联网，约 1 分钟...
    echo.
    python -m pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败，请检查网络后重试
        pause
        exit /b 1
    )
)

echo 系统启动中，浏览器将自动打开 http://127.0.0.1:8000
echo 如需停止系统，直接关闭本窗口即可
echo ==========================================
echo.
start "" http://127.0.0.1:8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

echo.
echo 系统已停止。如果是异常退出，请把上面的错误信息截图发给开发者。
pause
