/*
 * BBchannel HTTP API Loader - DLL 劫持版本
 * 劫持 _ctypes.pyd，在加载时自动执行 Python 代码导入 http_api_server
 */

#include <windows.h>
#include <stdio.h>
#include <time.h>

// 原始模块句柄
static HMODULE hOriginal = NULL;

// 原始模块导出函数类型
// 使用 void* 代替 PyObject* 避免包含 Python.h
typedef void* (*PyInitFunc)(void);
static PyInitFunc original_PyInit__ctypes = NULL;

// 初始化 Python，导入 http_api_server
void InitPython() {
    // 获取 DLL 所在目录
    wchar_t dllPath[MAX_PATH];
    HMODULE hDll = NULL;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)InitPython, &hDll);
    GetModuleFileNameW(hDll, dllPath, MAX_PATH);
    
    // 移除文件名，保留目录
    wchar_t* lastBackslash = wcsrchr(dllPath, L'\\');
    if (lastBackslash) {
        *lastBackslash = L'\0';
    }
    
    // 创建日志文件 - 使用 DLL 所在目录
    wchar_t logPath[MAX_PATH];
    wcscpy_s(logPath, MAX_PATH, dllPath);
    wcscat_s(logPath, MAX_PATH, L"\\http_api_injection.log");
    
    FILE* log = nullptr;
    _wfopen_s(&log, logPath, L"a, ccs=UTF-8");
    if (!log) {
        return;
    }
    
    fwprintf(log, L"\n=== HTTP API Injection Started ===\n");
    fwprintf(log, L"MAX_PATH constant: %d\n", MAX_PATH);
    
    wchar_t testPath[MAX_PATH];
    DWORD testLen = GetModuleFileNameW(NULL, testPath, MAX_PATH);
    fwprintf(log, L"EXE Path (len=%lu): %S\n", testLen, testPath);
    
    fwprintf(log, L"DLL Path: %S\n", dllPath);
    fwprintf(log, L"DLL Path length: %zu\n", wcslen(dllPath));
    fflush(log);
    
    // 延迟初始化，等待 PyInstaller 完全启动
    Sleep(100); // 等待 100ms，确保 Python 环境就绪
    
    fprintf(log, "[1] Starting injection...\n");
    fflush(log);
    
    // 使用 DLL 所在目录构建 http_api_server.py 路径
    wchar_t scriptPath[MAX_PATH];
    wcscpy_s(scriptPath, MAX_PATH, dllPath);
    wcscat_s(scriptPath, MAX_PATH, L"\\http_api_server.py");
    
    fprintf(log, "[2] Script path: %S\n", scriptPath);
    fprintf(log, "[2] Script path length: %zu\n", wcslen(scriptPath));
    fflush(log);
    
    // 检查文件是否存在
    if (GetFileAttributesW(scriptPath) == INVALID_FILE_ATTRIBUTES) {
        DWORD err = GetLastError();
        if (log) {
            fwprintf(log, L"[ERROR] GetFileAttributes failed for: %s\n", scriptPath);
            fwprintf(log, L"[ERROR] Error code: %lu\n", err);
            fclose(log);
        }
        return;
    }
    
    if (log) {
        fwprintf(log, L"[2] Found http_api_server.py: %s\n", scriptPath);
        fflush(log);
    }
    
    // 加载 Python36.dll
    HMODULE hPython = LoadLibraryW(L"python36.dll");
    if (!hPython) {
        if (log) {
            fwprintf(log, L"[ERROR] Failed to load python36.dll\n");
            fclose(log);
        }
        return;
    }
    
    if (log) {
        fwprintf(log, L"[3] Loaded python36.dll at %p\n", hPython);
        fflush(log);
    }
    
    // 获取 Python API
    typedef int (*PyRun_SimpleStringFunc)(const char*);
    typedef void* (*PyImport_ImportModuleFunc)(const char*);
    typedef void* (*PyGILState_EnsureFunc)(void);
    typedef void (*PyGILState_ReleaseFunc)(void*);
    
    PyRun_SimpleStringFunc PyRun_SimpleString = (PyRun_SimpleStringFunc)GetProcAddress(hPython, "PyRun_SimpleString");
    PyImport_ImportModuleFunc PyImport_ImportModule = (PyImport_ImportModuleFunc)GetProcAddress(hPython, "PyImport_ImportModule");
    PyGILState_EnsureFunc PyGILState_Ensure = (PyGILState_EnsureFunc)GetProcAddress(hPython, "PyGILState_Ensure");
    PyGILState_ReleaseFunc PyGILState_Release = (PyGILState_ReleaseFunc)GetProcAddress(hPython, "PyGILState_Release");
    
    if (!PyRun_SimpleString) {
        if (log) {
            fwprintf(log, L"[ERROR] Failed to get PyRun_SimpleString\n");
            fclose(log);
        }
        FreeLibrary(hPython);
        return;
    }
    
    if (log) {
        fwprintf(log, L"[4] Python API ready, PyGILState_Ensure=%p\n", PyGILState_Ensure);
        fflush(log);
    }
    
    // 获取 GIL
    void* gil_state = NULL;
    if (PyGILState_Ensure) {
        gil_state = PyGILState_Ensure();
        if (log) {
            fwprintf(log, L"[4.5] GIL acquired\n");
            fflush(log);
        }
    }
    
    // 方法 1: 简单的测试代码
    if (log) {
        fwprintf(log, L"[4.6] About to run simple test...\n");
        fflush(log);
    }
    
    int result = PyRun_SimpleString("print('[HTTP API] Test print from DLL')");
    
    if (log) {
        fwprintf(log, L"[5] Simple test returned: %d\n", result);
        fflush(log);
    }
    
    // 方法 2: 启动 HTTP API Server
    if (result == 0) {
        if (log) {
            fwprintf(log, L"[5.1] Starting HTTP API Server...\n");
            fflush(log);
        }
        
        const char* server_code = 
            "import sys\n"
            "import threading\n"
            "import time\n"
            "import gc\n"
            "\n"
            "http_api_bb_window = None\n"
            "\n"
            "def _wait_and_start():\n"
            "    '''等待 BBchannelWindow 创建后启动 HTTP Server'''\n"
            "    try:\n"
            "        # 立即启动 HTTP Server（在免责声明弹窗之前）\n"
            "        import http_api_server\n"
            "        http_api_server.start_http_server(None, 5000)\n"
            "        print('[HTTP API] Server started early')\n"
            "        \n"
            "        # 等待 BBchannelWindow 实例创建\n"
            "        for _ in range(200):\n"
            "            for obj in gc.get_objects():\n"
            "                if obj.__class__.__name__ == 'BBchannelWindow':\n"
            "                    global http_api_bb_window\n"
            "                    http_api_bb_window = obj\n"
            "                    # 更新 http_api_server 中的 bb_window\n"
            "                    http_api_server.update_bb_window(obj)\n"
            "                    print('[HTTP API] BBchannelWindow found and connected')\n"
            "                    return\n"
            "            __import__('time').sleep(0.05)\n"
            "        print('[HTTP API] Warning: BBchannelWindow not found')\n"
            "    except Exception as e:\n"
            "        print(f'[HTTP API] Error: {e}')\n"
            "        import traceback\n"
            "        traceback.print_exc()\n"
            "\n"
            "t = threading.Thread(target=_wait_and_start, daemon=True)\n"
            "t.start()\n"
            "print('[HTTP API] Server thread started')\n";
        
        result = PyRun_SimpleString(server_code);
        
        if (log) {
            fwprintf(log, L"[5.2] Server code returned: %d\n", result);
            fflush(log);
        }
    }
    
    // 释放 GIL
    if (PyGILState_Release && gil_state) {
        PyGILState_Release(gil_state);
        if (log) {
            fwprintf(log, L"[5.5] GIL released\n");
            fflush(log);
        }
    }
    
    if (log) {
        fwprintf(log, L"=== Injection Complete ===\n\n");
        fclose(log);
    }
}

// Python 模块导出函数 - 转发到原始模块
extern "C" __declspec(dllexport)
void* PyInit__ctypes(void) {
    if (original_PyInit__ctypes) {
        return original_PyInit__ctypes();
    }
    return NULL;
}

// DLL 入口
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
    case DLL_PROCESS_ATTACH: {
        DisableThreadLibraryCalls(hModule);
        
        // 首先加载原始 _ctypes.pyd
        wchar_t originalPath[MAX_PATH];
        GetCurrentDirectoryW(MAX_PATH, originalPath);
        wcscat_s(originalPath, MAX_PATH, L"\\_ctypes_orig.pyd");
        
        hOriginal = LoadLibraryW(originalPath);
        if (!hOriginal) {
            OutputDebugStringW(L"[HTTP API] Failed to load original _ctypes\n");
            break;
        }
        
        // 获取原始导出函数
        original_PyInit__ctypes = (PyInitFunc)GetProcAddress(hOriginal, "PyInit__ctypes");
        
        // 在新线程中初始化 Python
        HANDLE hThread = CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)InitPython, NULL, 0, NULL);
        if (hThread) CloseHandle(hThread);
        
        break;
    }
    case DLL_PROCESS_DETACH:
        if (hOriginal) {
            FreeLibrary(hOriginal);
        }
        break;
    }
    return TRUE;
}
