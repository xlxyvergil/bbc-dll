@echo off
chcp 65001 >nul
echo BBC TCP API Test
echo ====================
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0test.ps1" %*
