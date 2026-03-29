@echo off
chcp 65001 >nul
echo ==========================================
echo BBC TCP Loader Build Script
echo ==========================================

set SOURCE=bbc_tcp_loader.cpp
set OUTPUT=_ctypes.pyd
set GPP=tools\x86_64-w64-mingw32-g++.exe
set ORIGINAL=original\_ctypes.pyd
set ORIGINAL_RENAMED=_ctypes_orig.pyd

if not exist %GPP% (
    echo [ERROR] MinGW g++ not found in tools folder
    exit /b 1
)

if not exist %ORIGINAL% (
    echo [ERROR] Original _ctypes.pyd not found in original folder
    exit /b 1
)

echo [1] Preparing original file...
if exist %ORIGINAL_RENAMED% del %ORIGINAL_RENAMED%
copy %ORIGINAL% %ORIGINAL_RENAMED% >nul
echo     Copied: original\_ctypes.pyd -> _ctypes_orig.pyd

echo [2] Compiling %SOURCE%...
%GPP% -shared -o %OUTPUT% %SOURCE% -static-libgcc -static-libstdc++ -Wl,--subsystem,windows

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed!
    exit /b 1
)

echo [3] Build successful: %OUTPUT%
echo [4] File size:
dir %OUTPUT% /-C | findstr /R "^[0-9]"

echo.
echo ==========================================
echo Build complete!
echo Output: %OUTPUT%
echo ==========================================
pause
