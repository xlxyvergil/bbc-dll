#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BBC TCP Loader 构建脚本"""

import os
import sys
import shutil
import subprocess

def main():
    # 切换到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("=" * 50)
    print("BBC TCP Loader Build Script")
    print("=" * 50)
    print(f"Current directory: {os.getcwd()}")
    
    # 配置
    source = "bbc_tcp_loader.cpp"
    output = "_ctypes.pyd"
    gpp = r"mingw64\bin\x86_64-w64-mingw32-g++.exe"
    original = r"original\_ctypes.pyd"
    original_renamed = "_ctypes_orig.pyd"
    
    # 检查 MinGW
    if not os.path.exists(gpp):
        print(f"[ERROR] MinGW g++ not found: {gpp}")
        return 1
    
    # 检查原始文件
    if not os.path.exists(original):
        print(f"[ERROR] Original file not found: {original}")
        return 1
    
    # 复制原始文件
    print("\n[1] Preparing original file...")
    if os.path.exists(original_renamed):
        os.remove(original_renamed)
    shutil.copy2(original, original_renamed)
    print(f"    Copied: {original} -> {original_renamed}")
    print(f"    Size: {os.path.getsize(original_renamed)} bytes")
    
    # 编译
    print(f"\n[2] Compiling {source}...")
    cmd = [
        gpp,
        "-shared",
        "-o", output,
        source,
        "-static-libgcc",
        "-static-libstdc++",
        "-Wl,--subsystem,windows"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Build failed!")
        print(result.stderr)
        return 1
    
    print(f"\n[3] Build successful: {output}")
    print(f"    Size: {os.path.getsize(output)} bytes")
    
    print("\n" + "=" * 50)
    print("Build complete!")
    print("=" * 50)
    
    input("\nPress Enter to exit...")
    return 0

if __name__ == "__main__":
    sys.exit(main())
