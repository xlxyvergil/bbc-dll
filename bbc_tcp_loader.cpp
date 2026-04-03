/*
 * BBchannel TCP Server Loader - DLL 劫持版本
 * 劫持 _ctypes.pyd，在加载时自动执行 Python 代码导入 bbc_tcp_server
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

// 初始化 Python，导入 bbc_tcp_server
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
    
    // 日志功能已禁用，避免影响 BBC 启动
    FILE* log = nullptr;
    
    // 延迟初始化，等待 PyInstaller 完全启动
    // PyInstaller 需要时间来设置 sys._MEIPASS 和初始化 Python
    Sleep(500); // 等待 500ms，确保 Python 环境就绪
    
    // 再检查一次，如果 Python 仍未初始化，再等待
    for (int i = 0; i < 10; i++) {
        HMODULE hPythonTest = GetModuleHandleW(L"python36.dll");
        if (hPythonTest) {
            break;
        }
        Sleep(200);
    }
    
    // 使用 DLL 所在目录构建 bbc_tcp_server.py 路径
    wchar_t scriptPath[MAX_PATH];
    wcscpy_s(scriptPath, MAX_PATH, dllPath);
    wcscat_s(scriptPath, MAX_PATH, L"\\bbc_tcp_server.py");
    
    fprintf(log, "[2] Script path: %S\n", scriptPath);
    fprintf(log, "[2] Script path length: %zu\n", wcslen(scriptPath));
    fflush(log);
    
    // 检查文件是否存在
    if (GetFileAttributesW(scriptPath) == INVALID_FILE_ATTRIBUTES) {
        return;
    }
    
    // 获取已加载的 Python36.dll（PyInstaller 应该已经加载）
    HMODULE hPython = GetModuleHandleW(L"python36.dll");
    if (!hPython) {
        // 如果还没加载，尝试从 EXE 所在目录加载
        wchar_t exePath[MAX_PATH];
        GetModuleFileNameW(NULL, exePath, MAX_PATH);
        wchar_t* lastBackslash = wcsrchr(exePath, L'\\');
        if (lastBackslash) {
            *lastBackslash = L'\0';
        }
        
        wchar_t pythonDllPath[MAX_PATH];
        wcscpy_s(pythonDllPath, MAX_PATH, exePath);
        wcscat_s(pythonDllPath, MAX_PATH, L"\\python36.dll");
        
        hPython = LoadLibraryW(pythonDllPath);
        if (!hPython) {
            // 最后尝试从 DLL 所在目录加载
            hPython = LoadLibraryW(L"python36.dll");
        }
    }
    
    if (!hPython) {
        return;
    }
    
    // 获取 Python API
    typedef void (*Py_InitializeFunc)(void);
    typedef int (*Py_IsInitializedFunc)(void);
    typedef void (*Py_SetPythonHomeFunc)(const wchar_t*);
    typedef int (*PyRun_SimpleStringFunc)(const char*);
    typedef void* (*PyImport_ImportModuleFunc)(const char*);
    typedef void* (*PyGILState_EnsureFunc)(void);
    typedef void (*PyGILState_ReleaseFunc)(void*);
    
    Py_InitializeFunc Py_Initialize = (Py_InitializeFunc)GetProcAddress(hPython, "Py_Initialize");
    Py_IsInitializedFunc Py_IsInitialized = (Py_IsInitializedFunc)GetProcAddress(hPython, "Py_IsInitialized");
    Py_SetPythonHomeFunc Py_SetPythonHome = (Py_SetPythonHomeFunc)GetProcAddress(hPython, "Py_SetPythonHome");
    PyRun_SimpleStringFunc PyRun_SimpleString = (PyRun_SimpleStringFunc)GetProcAddress(hPython, "PyRun_SimpleString");
    PyImport_ImportModuleFunc PyImport_ImportModule = (PyImport_ImportModuleFunc)GetProcAddress(hPython, "PyImport_ImportModule");
    PyGILState_EnsureFunc PyGILState_Ensure = (PyGILState_EnsureFunc)GetProcAddress(hPython, "PyGILState_Ensure");
    PyGILState_ReleaseFunc PyGILState_Release = (PyGILState_ReleaseFunc)GetProcAddress(hPython, "PyGILState_Release");
    
    if (!PyRun_SimpleString) {
        return;
    }
    
    // 获取 GIL
    void* gil_state = NULL;
    if (PyGILState_Ensure) {
        gil_state = PyGILState_Ensure();
    }
    
    const char* server_code = 
        "import sys\n"
        "import threading\n"
        "import time\n"
        "import gc\n"
        "\n"
        "bbc_tcp_bb_window = None\n"
        "\n"
        "def _wait_and_start():\n"
        "    '''等待 BBchannelWindow 创建后启动 TCP Server'''\n"
        "    try:\n"
        "        # 立即启动 TCP Server（在免责声明弹窗之前）\n"
        "        import bbc_tcp_server\n"
        "        bbc_tcp_server.start_tcp_server(None, 25001)\n"
        "        print('[BBC-TCP] Server started early')\n"
        "        \n"
        "        # 等待 BBchannelWindow 实例创建\n"
        "        for _ in range(200):\n"
        "            for obj in gc.get_objects():\n"
        "                if obj.__class__.__name__ == 'BBchannelWindow':\n"
        "                    global bbc_tcp_bb_window\n"
        "                    bbc_tcp_bb_window = obj\n"
        "                    # 更新 bbc_tcp_server 中的 bb_window\n"
        "                    bbc_tcp_server.update_bb_window(obj)\n"
        "                    print('[BBC-TCP] BBchannelWindow found and connected')\n"
        "                    return\n"
        "            __import__('time').sleep(0.05)\n"
        "        print('[BBC-TCP] Warning: BBchannelWindow not found')\n"
        "    except Exception as e:\n"
        "        print(f'[BBC-TCP] Error: {e}')\n"
        "        import traceback\n"
        "        traceback.print_exc()\n"
        "\n"
        "t = threading.Thread(target=_wait_and_start, daemon=True)\n"
        "t.start()\n"
        "print('[BBC-TCP] Server thread started')\n";
    
    PyRun_SimpleString(server_code);
    
    // 释放 GIL
    if (PyGILState_Release && gil_state) {
        PyGILState_Release(gil_state);
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
            OutputDebugStringW(L"[BBC TCP] Failed to load original _ctypes\n");
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
