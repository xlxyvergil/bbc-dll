@echo off
chcp 65001 >nul

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查 Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH
    pause
    exit /b 1
)

REM 运行 Python 构建脚本
python build.py

exit /b %ERRORLEVEL%
