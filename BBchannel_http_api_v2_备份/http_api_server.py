# ==================== HTTP API Server ====================
http_server_instance = None
tcp_server_instance = None  # TCP Server 实例
popup_event_queue = None
original_messagebox = None
CT = None  # 全局 CT 变量
Battle = None  # 全局 Battle 类
_bb_window_global = None  # 全局 bb_window 引用

# 配置
HTTP_PORT = 25002  # HTTP Server 端口
TCP_PORT = 25001  # TCP Server 端口

# TCP 广播函数（由 TCP Server 设置）
_broadcast_popup = None

# 弹窗等待响应的字典：popup_id -> {result: str, callback: func}
# 用于异步等待外部系统返回弹窗决策
_popup_wait_dict = {}
_popup_wait_lock = None  # 将在 start_http_server 中初始化
_popup_callbacks = {}  # 存储弹窗的回调函数

def update_bb_window(bb_window):
    """更新全局 bb_window 引用"""
    global _bb_window_global
    _bb_window_global = bb_window
    log_to_file(f"[HTTP-Server] bb_window updated: {bb_window}")

def _remove_popup_from_queue(popup_id):
    """从队列中移除指定弹窗"""
    global popup_event_queue
    if popup_event_queue is None:
        return
    
    temp_list = []
    removed = False
    while not popup_event_queue.empty():
        try:
            p = popup_event_queue.get_nowait()
            if p['id'] == popup_id:
                removed = True
                log_to_file(f"[Popup] 已从队列移除弹窗: {popup_id}")
            else:
                temp_list.append(p)
        except:
            break
    
    # 将其他弹窗放回队列
    for p in temp_list:
        popup_event_queue.put(p)
    
    return removed

def start_http_server(bb_window, port=25002):
    """启动 HTTP API 服务器，用于外部控制（独立运行，不随战斗线程停止）"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    import threading
    import queue
    import time
    from tkinter import messagebox
    
    global CT, Battle, Windows, LDdevice, Mumudevice
    
    # 导入设备类
    try:
        from device import Windows, LDdevice, Mumudevice
        log_to_file("[Import] Windows, LDdevice and Mumudevice imported successfully")
    except ImportError as e:
        log_to_file(f"[Import Error] device import failed: {e}")
        Windows = None
        LDdevice = None
        Mumudevice = None
    
    # 导入 CT (Consts) 和 Battle
    try:
        from consts import Consts as CT
        log_to_file("[Import] CT imported successfully")
    except ImportError as e:
        log_to_file(f"[Import Error] CT import failed: {e}")
        # 如果 consts 模块不可用，创建模拟的 CT
        class MockCT:
            Gold = "gold"
            Silver = "silver"
            Copper = "copper"
            Blue = "blue"
            Colorful = "colorful"
            BATTLE_TYPE = ['连续出击(或强化本)', '自动编队爬塔(应用操作序列设置)']
            class Pool:
                @staticmethod
                def submit(func):
                    import threading
                    threading.Thread(target=func, daemon=True).start()
        CT = MockCT()
    
    try:
        from FGObattle import Battle
        log_to_file("[Import] Battle imported successfully")
    except ImportError as e:
        log_to_file(f"[Import Error] Battle import failed: {e}")
        Battle = None
    
    global http_server_instance, popup_event_queue, original_messagebox, _popup_wait_lock
    
    popup_event_queue = queue.Queue()
    _popup_wait_lock = threading.Lock()
    
    # 拦截 messagebox
    original_messagebox = {
        'showinfo': messagebox.showinfo,
        'showwarning': messagebox.showwarning,
        'showerror': messagebox.showerror,
        'askokcancel': messagebox.askokcancel,
        'askyesno': messagebox.askyesno,
        'askretrycancel': messagebox.askretrycancel
    }
    
    # 需要外部控制的弹窗标题关键词
    CONTROLLED_POPUPS = ["免责声明", "助战排序不符合", "队伍配置错误", "自动连接失败"]
    
    def create_popup_wrapper(func_name, original_func):
        """
        创建弹窗包装器 - 最终方案：
        1. 弹窗正常显示（用户可见）
        2. 拦截弹窗返回值（不直接返回给 BBC）
        3. 通知外部系统弹窗信息
        4. 外部系统决定应该返回什么值给 BBC
        5. 关闭弹窗，返回外部决定的值
        """
        def wrapper(title, message, **kwargs):
            # 检查是否需要外部控制
            is_controlled = any(keyword in title for keyword in CONTROLLED_POPUPS)
            
            if not is_controlled:
                # 非控制弹窗，正常显示并返回
                return original_func(title, message, **kwargs)
            
            # 免责声明也走外部控制流程（弹窗显示但立即关闭）
            # 外部系统可以决定返回什么值，默认返回 ok
            
            # 生成唯一弹窗 ID
            popup_id = str(time.time())
            
            # 存储弹窗信息
            with _popup_wait_lock:
                _popup_wait_dict[popup_id] = {
                    'result': None,  # 外部决定的返回值
                    'title': title,
                    'message': message,
                    'type': func_name,
                    'status': 'waiting'  # waiting / resolved
                }
            
            # 通知外部系统弹窗出现
            # 修复 Windows 中文编码问题（tkinter 使用 GBK，需要转为 UTF-8）
            def fix_encoding(s):
                if isinstance(s, bytes):
                    return s.decode('utf-8', errors='replace')
                # Windows 下字符串可能是 GBK 编码的 str，需要转换
                try:
                    # 尝试用 latin-1 编码为 bytes，再用 gbk 解码
                    return s.encode('latin-1').decode('gbk', errors='replace')
                except:
                    return s
            
            popup_data = {
                'id': popup_id,
                'type': func_name,
                'title': fix_encoding(title),
                'message': fix_encoding(message)
            }
            popup_event_queue.put(popup_data)
            log_to_file(f"[Popup] 弹窗已显示，等待外部决策: [{func_name}] {title}")
            
            # TCP 广播给 MaaFgo
            global _broadcast_popup
            if _broadcast_popup:
                try:
                    _broadcast_popup(popup_data)
                    log_to_file(f"[TCP] 弹窗已广播: {popup_id}")
                except Exception as e:
                    log_to_file(f"[TCP] 广播失败: {e}")
            
            # 显示原生弹窗，但返回值由外部系统控制
            return create_externally_controlled_dialog(func_name, title, message, popup_id, original_func, **kwargs)
            
        return wrapper
    
    def create_externally_controlled_dialog(func_name, title, message, popup_id, original_func, **kwargs):
        """
        外部控制弹窗返回值
        1. 显示原生弹窗（不拦截）
        2. 通知外部系统
        3. 外部系统返回决策值
        4. 关闭弹窗并返回外部决定的值给 BBC
        """
        import threading
        import time
        import ctypes
        from ctypes import wintypes
        
        # Windows API 定义
        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        
        def find_popup_window(popup_title):
            """通过标题查找弹窗窗口句柄"""
            hwnd = user32.FindWindowW(None, popup_title)
            return hwnd
        
        def close_popup_window(hwnd):
            """关闭弹窗窗口"""
            if hwnd and hwnd != 0:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return True
            return False
        
        # 用于存储外部决策结果和窗口句柄
        popup_data = {'value': None, 'resolved': False, 'hwnd': None}
        
        def monitor_external():
            """后台线程：等待外部系统决策，然后关闭弹窗"""
            # 免责声明直接2秒后自动接受，不等待外部决策
            is_disclaimer = "免责声明" in title
            
            if is_disclaimer:
                # 免责声明：等待2秒后自动接受
                time.sleep(2.0)
                popup_data['value'] = 'ok'
                popup_data['resolved'] = True
                hwnd = find_popup_window(title)
                if hwnd:
                    log_to_file(f"[Popup] 免责声明2秒超时，自动接受并关闭")
                    close_popup_window(hwnd)
                return
            
            # 其他弹窗：一直等待外部决策（弹窗没关，BBC会停止在那里）
            while not popup_data['resolved']:
                with _popup_wait_lock:
                    popup_info = _popup_wait_dict.get(popup_id)
                    if popup_info and popup_info.get('status') == 'resolved':
                        popup_data['value'] = popup_info.get('result')
                        popup_data['resolved'] = True
                        # 获取窗口句柄并关闭弹窗
                        hwnd = find_popup_window(title)
                        if hwnd:
                            popup_data['hwnd'] = hwnd
                            log_to_file(f"[Popup] 找到弹窗句柄: {hwnd}，准备关闭")
                            close_popup_window(hwnd)
                        break
                time.sleep(0.1)
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=monitor_external, daemon=True)
        monitor_thread.start()
        
        # 显示原生弹窗（阻塞等待，但会被外部线程关闭）
        log_to_file(f"[Popup] 显示原生弹窗: {title}")
        original_result = original_func(title, message, **kwargs)
        log_to_file(f"[Popup] 弹窗已关闭，原始返回值: {original_result}")
        
        # 等待监控线程结束
        monitor_thread.join(timeout=1)
        
        # 清理 - 从等待字典和队列中移除
        with _popup_wait_lock:
            _popup_wait_dict.pop(popup_id, None)
        
        # 从队列中移除已处理的弹窗
        _remove_popup_from_queue(popup_id)
        
        # 如果外部有决策，返回外部决定的值；否则返回原始值
        if popup_data['resolved']:
            result = popup_data['value']
            log_to_file(f"[Popup] 返回外部决定的值: {result}")
        else:
            result = original_result
            log_to_file(f"[Popup] 无外部决策，返回原始值: {result}")
        
        # 转换为布尔值
        if func_name == 'askyesno':
            return result == 'yes' if isinstance(result, str) else bool(result)
        elif func_name == 'askokcancel':
            return result == 'ok' if isinstance(result, str) else bool(result)
        elif func_name == 'askretrycancel':
            return result == 'retry' if isinstance(result, str) else bool(result)
        else:
            return None
    
    # 替换 messagebox 函数
    messagebox.showinfo = create_popup_wrapper('showinfo', original_messagebox['showinfo'])
    messagebox.showwarning = create_popup_wrapper('showwarning', original_messagebox['showwarning'])
    messagebox.showerror = create_popup_wrapper('showerror', original_messagebox['showerror'])
    messagebox.askokcancel = create_popup_wrapper('askokcancel', original_messagebox['askokcancel'])
    messagebox.askyesno = create_popup_wrapper('askyesno', original_messagebox['askyesno'])
    messagebox.askretrycancel = create_popup_wrapper('askretrycancel', original_messagebox['askretrycancel'])
    
    class BBchannelHandler(BaseHTTPRequestHandler):
        @property
        def bb(self):
            return _bb_window_global
        
        def log_message(self, format, *args):
            print(f"[HTTP] {self.address_string()} - {format % args}")
        
        def do_GET(self):
            if self.path == '/status':
                # 添加 pages 状态诊断
                pages_info = {
                    'pages_count': len(self.bb.pages) if hasattr(self.bb, 'pages') else 0,
                    'pages_type': type(self.bb.pages).__name__ if hasattr(self.bb, 'pages') else 'N/A',
                    'has_page0': len(self.bb.pages) > 0 if hasattr(self.bb, 'pages') else False
                }
                self.send_json({'status': 'running', 'popup_queue': popup_event_queue.qsize(), 'debug': pages_info})
            elif self.path == '/popups':
                # 获取等待中的弹窗列表（包含正在等待外部决策的弹窗）
                popups = []
                temp_list = []
                while not popup_event_queue.empty():
                    p = popup_event_queue.get()
                    temp_list.append(p)
                    # 检查是否还在等待中
                    with _popup_wait_lock:
                        is_waiting = p['id'] in _popup_wait_dict
                    popup_info = {
                        'id': p['id'], 
                        'type': p['type'], 
                        'title': p['title'], 
                        'message': p['message'],
                        'waiting': is_waiting
                    }
                    popups.append(popup_info)
                for p in temp_list:
                    popup_event_queue.put(p)
                self.send_json({'popups': popups})
            
            elif self.path == '/get':
                # 获取全部设置
                try:
                    page = self.bb.pages[0]
                    settings = {
                        'apple_type': page.appleSet.appleType,
                        'run_times': page.appleSet.runTimes.get(),
                        'battle_type': page.battletype.get()
                    }
                    self.send_json(settings)
                except Exception as e:
                    self.send_json({'error': str(e)}, 500)
            else:
                self.send_json({'error': 'unknown endpoint'}, 404)
        
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body) if body else {}
            except:
                self.send_json({'error': 'invalid json'}, 400)
                return
            
            if self.path == '/popups/clear':
                # 清空弹窗记录
                while not popup_event_queue.empty():
                    popup_event_queue.get()
                self.send_json({'success': True})
            

            
            elif self.path == '/connect/mumu':
                # MuMu连接
                result = api_connect_mumu(self.bb, type('Args', (), data)())
                self.send_json({'success': result})
            
            elif self.path == '/connect/ld':
                # 雷电连接
                result = api_connect_ld(self.bb, type('Args', (), data)())
                self.send_json({'success': result})
            
            elif self.path == '/connect/adb':
                # ADB连接
                result = api_connect_adb(self.bb, type('Args', (), data)())
                self.send_json({'success': result})
            
            elif self.path == '/set/appletype':
                # 设置苹果类型
                try:
                    page = self.bb.pages[0]
                    api_set_apple_type(page, data.get('type'))
                    self.send_json({'success': True})
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.send_json({'error': str(e), 'traceback': traceback.format_exc()}, 500)
            
            elif self.path == '/set/runcount':
                # 设置运行次数
                page = self.bb.pages[0]
                api_set_run_times(page, data.get('times'))
                self.send_json({'success': True})
            
            elif self.path == '/set/battletype':
                # 设置战斗类型
                page = self.bb.pages[0]
                api_set_battle_type(page, data.get('type'))
                self.send_json({'success': True})
            
            elif self.path == '/start':
                # 开始运行
                try:
                    log_to_file("[/start] 端点被调用")
                    page = self.bb.pages[0]
                    log_to_file(f"[/start] 获取到 page: {page}")
                    result = api_start_battle(page)
                    log_to_file(f"[/start] api_start_battle 返回: {result}")
                    self.send_json({'success': result})
                except Exception as e:
                    import traceback
                    log_to_file(f"[/start] 异常: {e}")
                    log_to_file(traceback.format_exc())
                    self.send_json({'error': str(e)}, 500)
            
            elif self.path == '/stop':
                # 停止运行
                page = self.bb.pages[0]
                if page.device.running:
                    page.device.stop()
                self.send_json({'success': True})
            
            elif self.path == '/popup/response':
                # 响应弹窗（外部系统返回决策）
                popup_id = data.get('id', '')
                action = data.get('action', '')  # "ok", "cancel", "yes", "no", "retry"
                
                if not popup_id or not action:
                    self.send_json({'error': 'id and action required'}, 400)
                    return
                
                if action not in ['ok', 'cancel', 'yes', 'no', 'retry']:
                    self.send_json({'error': 'action must be "ok", "cancel", "yes", "no" or "retry"'}, 400)
                    return
                
                try:
                    # 查找等待中的弹窗
                    with _popup_wait_lock:
                        popup_info = _popup_wait_dict.get(popup_id)
                        if popup_info and popup_info.get('status') == 'waiting':
                            # 设置决策结果并标记为已解决
                            popup_info['result'] = action
                            popup_info['status'] = 'resolved'
                            self.send_json({
                                'success': True, 
                                'message': f'Popup {popup_id} resolved with action: {action}',
                                'title': popup_info.get('title', '')
                            })
                        else:
                            self.send_json({
                                'success': False, 
                                'message': f'Popup {popup_id} not found or already resolved'
                            })
                except Exception as e:
                    import traceback
                    self.send_json({'error': str(e), 'traceback': traceback.format_exc()}, 500)
            
            else:
                self.send_json({'error': 'unknown endpoint'}, 404)
        
        def send_json(self, data, status=200):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def run_server():
        server = HTTPServer(('127.0.0.1', port), BBchannelHandler)
        http_server_instance = server
        print(f"[HTTP-Server] 启动于 http://127.0.0.1:{port} (独立运行模式)")
        server.serve_forever()  # 持续运行，不随战斗线程停止
    
    threading.Thread(target=run_server, daemon=True).start()
    
    # 启动 TCP Server（用于 MaaFgo 连接）
    def run_tcp_server():
        import socket
        import json
        
        global tcp_server_instance
        tcp_clients = []  # 连接的客户端列表
        tcp_lock = threading.Lock()
        
        def broadcast_popup(popup_data):
            """向所有 TCP 客户端广播弹窗信息"""
            with tcp_lock:
                disconnected = []
                for client in tcp_clients:
                    try:
                        msg = json.dumps(popup_data, ensure_ascii=False).encode('utf-8')
                        client.sendall(len(msg).to_bytes(4, 'big') + msg)
                    except:
                        disconnected.append(client)
                
                # 清理断开连接
                for client in disconnected:
                    tcp_clients.remove(client)
                    try:
                        client.close()
                    except:
                        pass
        
        # 保存广播函数供外部使用
        global _broadcast_popup
        _broadcast_popup = broadcast_popup
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', TCP_PORT))
        sock.listen(5)
        tcp_server_instance = sock
        print(f"[TCP-Server] 启动于 127.0.0.1:{TCP_PORT} (独立运行模式)")
        
        while True:
            try:
                client, addr = sock.accept()
                print(f"[TCP-Server] 客户端连接: {addr}")
                with tcp_lock:
                    tcp_clients.append(client)
            except Exception as e:
                print(f"[TCP-Server] 错误: {e}")
                break
    
    threading.Thread(target=run_tcp_server, daemon=True).start()


# ==================== API Internal Functions ====================
# 这些函数被 HTTP API 端点内部调用，不是命令行接口

def api_connect_mumu(bb, args):
    """API 内部函数：连接 MuMu 模拟器"""
    import os
    import json
    
    page = bb.pages[0]
    
    path = getattr(args, 'path', None)
    index = getattr(args, 'index', 0) or 0
    pkg = getattr(args, 'pkg', None)
    app_index = getattr(args, 'app_index', 0) or 0
    
    if not path:
        if os.path.exists("MuMuInstallPath.txt"):
            with open("MuMuInstallPath.txt", "r", encoding="utf8") as f:
                path = f.read().strip()
        if not path:
            print("[API错误] 未指定MuMu安装路径")
            return False
    
    try:
        path = Mumudevice.check_mumuInstallPath(path)
        with open("MuMuInstallPath.txt", "w", encoding="utf8") as f:
            f.write(path)
        Mumudevice.mumuPath = path
        
        emulator_name = f"MuMu模拟器12-{index}" if index > 0 else "MuMu模拟器12"
        pkg_name = pkg if pkg else "com.bilibili.fatego"
        
        device = Mumudevice(path, index, app_index, pkg_name, use_manager=True)
        serialno = {'name': emulator_name, 'pkg': pkg_name, 'appIndex': app_index}
        serialno_str = json.dumps(serialno, ensure_ascii=False)
        device.set_serialno(serialno_str)
        device.snapshot()
        
        page.snapshotDevice = page.operateDevice = page.device.snapshotDevice = page.device.operateDevice = device
        bb.pagebar.tags[page.idx].createText(True)
        bb.updateConnectLst(page.idx)
        print(f"[API] MuMu连接成功: {emulator_name}")
        return True
    except Exception as e:
        print(f"[API错误] MuMu连接失败: {e}")
        return False


def api_connect_ld(bb, args):
    """API 内部函数：连接雷电模拟器"""
    import os
    
    page = bb.pages[0]
    
    path = getattr(args, 'path', None)
    index = getattr(args, 'index', 0) or 0
    
    if not path:
        if os.path.exists("LDInstallPath.txt"):
            with open("LDInstallPath.txt", "r", encoding="utf8") as f:
                path = f.read().strip()
        if not path:
            print("[API 错误] 未指定雷电安装路径")
            return False
    
    try:
        path = LDdevice.checkPath(path)
        with open("LDInstallPath.txt", "w", encoding="utf8") as f:
            f.write(path)
        
        device = LDdevice(path, index)
        serialno = {'name': str(index)}
        serialno_str = json.dumps(serialno, ensure_ascii=False)
        device.set_serialno(serialno_str)
        device.snapshot()
        
        # 创建 Windows 触摸设备
        touchDevice = Windows(device.player.bndWnd)
        
        # 设置设备
        page.snapshotDevice = page.device.snapshotDevice = device
        page.operateDevice = page.device.operateDevice = touchDevice
        
        bb.pagebar.tags[page.idx].createText(True)
        bb.updateConnectLst(page.idx)
        print(f"[API] 雷电连接成功：编号{index}")
        return True
    except Exception as e:
        print(f"[API 错误] 雷电连接失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def api_connect_adb(bb, args):
    """API 内部函数：ADB 连接"""
    from bbcmd import cmd
    from device import Android, USE_AS_BOTH
    import os
    import sys
    
    # 获取 adb 路径 - 使用 airtest 内置的 adb
    adb_path = os.path.join(os.path.dirname(sys.executable), "airtest", "core", "android", "static", "adb", "windows")
    
    if not os.path.exists(os.path.join(adb_path, "adb.exe")):
        print(f"[API错误] 找不到 adb.exe: {adb_path}")
        return False
    
    page = bb.pages[0]
    
    ip_port = getattr(args, 'ip', None)
    if not ip_port:
        print("[API错误] ADB连接需要指定ip参数")
        return False
    
    try:
        print(cmd(f'"{adb_path}/adb" connect {ip_port}'))
        device = Android(ip_port, page.server, USE_AS_BOTH, cap_method="Minicap")
        
        if not device.available:
            device.disconnect()
            print("[API错误] ADB设备连接失败")
            return False
        
        page.snapshotDevice = page.operateDevice = page.device.snapshotDevice = page.device.operateDevice = device
        bb.pagebar.tags[page.idx].createText(True)
        bb.updateConnectLst(page.idx)
        print(f"[API] ADB连接成功: {ip_port}")
        return True
    except Exception as e:
        print(f"[API错误] ADB连接失败: {e}")
        return False


def api_set_apple_type(page, apple_type):
    """设置苹果类型"""
    if not apple_type:
        return
    
    apple_map = {
        "gold": CT.Gold,
        "silver": CT.Silver,
        "blue": CT.Blue,
        "copper": CT.Copper,
        "colorful": CT.Colorful
    }
    
    if apple_type in apple_map:
        apple_set = page.appleSet
        apple_set.appleType = apple_map[apple_type]
        # 更新 UI 显示
        try:
            apple_set.appleIconPhoto = apple_set.getAppleIconPhoto()
            apple_set.appleIcon.config(image=apple_set.appleIconPhoto)
            print(f"[API] 苹果类型已设置: {apple_type}")
        except Exception as e:
            print(f"[API警告] 苹果类型已设置但UI更新失败: {e}")
            print(f"[API] 苹果类型已设置: {apple_type}")


def api_set_run_times(page, times):
    """设置运行次数"""
    if times is None:
        return
    
    try:
        page.appleSet.runTimes.set(times)
        print(f"[API] 运行次数: {times}")
    except Exception as e:
        print(f"[API错误] 设置运行次数失败: {e}")


def api_set_battle_type(page, battle_type):
    """设置战斗类型"""
    if not battle_type:
        return
    
    if battle_type == "continuous":
        page.battletype.set(CT.BATTLE_TYPE[0])
        print("[API] 战斗类型: 连续出击")
    elif battle_type == "single":
        page.battletype.set(CT.BATTLE_TYPE[1])
        print("[API] 战斗类型: 单次")


def log_to_file(msg):
    """写入日志文件"""
    try:
        import os
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'http_api_debug.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            from datetime import datetime
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            f.flush()
    except Exception as e:
        # 如果连日志都写不了，就忽略错误
        pass

def api_start_battle(page):
    """开始战斗"""
    log_to_file(f"[API] api_start_battle 被调用")
    
    if Battle is None:
        log_to_file("[API错误] Battle 类未导入，无法开始战斗")
        return False
    
    try:
        log_to_file(f"[API] 检查从者配置...")
        for i in range(3):
            exist = page.servantGroup[i].exist
            log_to_file(f"[API] 从者 {i}: exist={exist}")
            if not exist:
                log_to_file("[API错误] 出战从者不足")
                return False
        
        times = page.appleSet.runTimes.get()
        battle_type = page.battletype.get()
        log_to_file(f"[API] 战斗参数: 次数={times}, 类型={battle_type}")
        
        log_to_file(f"[API] 模拟点击开始按钮...")
        
        # 使用 event_generate 模拟按钮点击，触发 startScript
        # 这样停止按钮也会正常工作
        try:
            # 获取按钮中心位置
            btn_x = page.start.winfo_width() // 2
            btn_y = page.start.winfo_height() // 2
            # 生成点击事件
            page.start.event_generate("<Button-1>", x=btn_x, y=btn_y)
            log_to_file("[API] 已触发按钮点击事件")
        except Exception as e:
            import traceback
            log_to_file(f"[API Error] 模拟点击失败: {e}")
            log_to_file(traceback.format_exc())
            return False
        return True
    except Exception as e:
        import traceback
        log_to_file(f"[API错误] 开始战斗失败: {e}")
        log_to_file(traceback.format_exc())
        return False
