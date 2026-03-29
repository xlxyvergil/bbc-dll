@echo off
chcp 65001 >nul
echo ==========================================
echo BBC TCP Loader Build Script
echo ==========================================

set SOURCE=bbc_tcp_loader.cpp
set OUTPUT=_ctypes.pyd
set GPP=tools\x86_64-w64-mingw32-g++.exe

if not exist %GPP% (
    echo [ERROR] MinGW g++ not found in tools folder
    exit /b 1
)

echo [1] Compiling %SOURCE%...
%GPP% -shared -o %OUTPUT% %SOURCE% -static-libgcc -static-libstdc++ -Wl,--subsystem,windows

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed!
    exit /b 1
)

echo [2] Build successful: %OUTPUT%
echo [3] File size:
dir %OUTPUT% /-C | findstr /R "^[0-9]"

echo.
echo ==========================================
echo Copy to BBchannel64? (Y/N)
set /p choice=
if /I "%choice%"=="Y" (
    copy /Y %OUTPUT% ..\BBchannel\dist\BBchannel64\
    copy /Y bbc_tcp_server.py ..\BBchannel\dist\BBchannel64\
    echo [4] Files copied to BBchannel64
)

echo.
echo Done.
pause
