# ==================== HTTP API Server ====================
http_server_instance = None
popup_event_queue = None
original_messagebox = None
CT = None  # 全局 CT 变量
Battle = None  # 全局 Battle 类
_bb_window_global = None  # 全局 bb_window 引用

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

def start_http_server(bb_window, port=16888):
    """启动 HTTP API 服务器，用于外部控制"""
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
        创建弹窗包装器
        只拦截指定的3个弹窗，其他弹窗正常显示
        """
        def wrapper(title, message, **kwargs):
            # 检查是否需要外部控制
            is_controlled = any(keyword in title for keyword in CONTROLLED_POPUPS)
            
            if not is_controlled:
                # 非控制弹窗，正常显示
                return original_func(title, message, **kwargs)
            
            # 免责声明自动返回 ok，不阻塞
            if "免责声明" in title:
                log_to_file(f"[Popup] 免责声明自动返回 ok: {title}")
                return None
            
            # 其他控制弹窗，拦截并等待外部决策
            popup_id = str(time.time())
            wait_event = threading.Event()
            
            with _popup_wait_lock:
                _popup_wait_dict[popup_id] = {
                    'event': wait_event,
                    'result': None,
                    'title': title,
                    'message': message,
                    'type': func_name
                }
            
            popup_data = {
                'id': popup_id,
                'type': func_name,
                'title': title,
                'message': message
            }
            popup_event_queue.put(popup_data)
            log_to_file(f"[Popup] 控制弹窗已拦截: [{func_name}] {title}")
            
            # 阻塞等待外部决策（最多60秒）
            total_wait = 0
            while not wait_event.is_set() and total_wait < 60:
                time.sleep(0.1)
                total_wait += 0.1
            
            with _popup_wait_lock:
                popup_info = _popup_wait_dict.pop(popup_id, {})
                result = popup_info.get('result', 'ok')
            
            log_to_file(f"[Popup] 外部决策: {title} -> {result}")
            
            # 根据弹窗类型返回相应的值
            if func_name in ['showinfo', 'showwarning', 'showerror']:
                return None
            elif func_name == 'askokcancel':
                return result == 'ok'
            elif func_name == 'askyesno':
                return result == 'ok' or result == 'yes'
            elif func_name == 'askretrycancel':
                return result == 'ok' or result == 'retry'
            else:
                return result == 'ok'
        return wrapper
    
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
            
            elif self.path == '/settings':
                # 获取当前设置
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
                result = cli_connect_mumu(self.bb, type('Args', (), data)())
                self.send_json({'success': result})
            
            elif self.path == '/connect/ld':
                # 雷电连接
                result = cli_connect_ld(self.bb, type('Args', (), data)())
                self.send_json({'success': result})
            
            elif self.path == '/connect/adb':
                # ADB连接
                result = cli_connect_adb(self.bb, type('Args', (), data)())
                self.send_json({'success': result})
            
            elif self.path == '/set/apple':
                # 设置苹果类型
                try:
                    page = self.bb.pages[0]
                    cli_set_apple_type(page, data.get('type'))
                    self.send_json({'success': True})
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.send_json({'error': str(e), 'traceback': traceback.format_exc()}, 500)
            
            elif self.path == '/set/times':
                # 设置运行次数
                page = self.bb.pages[0]
                cli_set_run_times(page, data.get('times'))
                self.send_json({'success': True})
            
            elif self.path == '/set/battletype':
                # 设置战斗类型
                page = self.bb.pages[0]
                cli_set_battle_type(page, data.get('type'))
                self.send_json({'success': True})
            
            elif self.path == '/start':
                # 开始运行
                try:
                    log_to_file("[/start] 端点被调用")
                    page = self.bb.pages[0]
                    log_to_file(f"[/start] 获取到 page: {page}")
                    result = cli_start_battle(page)
                    log_to_file(f"[/start] cli_start_battle 返回: {result}")
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
                action = data.get('action', '')  # "ok", "cancel", "yes", "no"
                
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
                        if popup_info:
                            # 设置决策结果
                            popup_info['result'] = action
                            # 唤醒等待的线程
                            popup_info['event'].set()
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
        print(f"[HTTP-Server] 启动于 http://127.0.0.1:{port}")
        server.serve_forever()
    
    threading.Thread(target=run_server, daemon=True).start()


# ==================== CLI Functions ====================

def cli_connect_mumu(bb, args):
    """命令行模式连接 MuMu 模拟器"""
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
            print("[CLI错误] 未指定MuMu安装路径")
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
        print(f"[CLI] MuMu连接成功: {emulator_name}")
        return True
    except Exception as e:
        print(f"[CLI错误] MuMu连接失败: {e}")
        return False


def cli_connect_ld(bb, args):
    """命令行模式连接雷电模拟器"""
    import os
    
    page = bb.pages[0]
    
    path = getattr(args, 'path', None)
    index = getattr(args, 'index', 0) or 0
    
    if not path:
        if os.path.exists("LDInstallPath.txt"):
            with open("LDInstallPath.txt", "r", encoding="utf8") as f:
                path = f.read().strip()
        if not path:
            print("[CLI 错误] 未指定雷电安装路径")
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
        print(f"[CLI] 雷电连接成功：编号{index}")
        return True
    except Exception as e:
        print(f"[CLI 错误] 雷电连接失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def cli_connect_adb(bb, args):
    """命令行模式ADB连接"""
    from bbcmd import cmd
    from device import Android, USE_AS_BOTH
    import os
    import sys
    
    # 获取 adb 路径 - 使用 airtest 内置的 adb
    adb_path = os.path.join(os.path.dirname(sys.executable), "airtest", "core", "android", "static", "adb", "windows")
    
    if not os.path.exists(os.path.join(adb_path, "adb.exe")):
        print(f"[CLI错误] 找不到 adb.exe: {adb_path}")
        return False
    
    page = bb.pages[0]
    
    ip_port = getattr(args, 'ip', None)
    if not ip_port:
        print("[CLI错误] ADB连接需要指定ip参数")
        return False
    
    try:
        print(cmd(f'"{adb_path}/adb" connect {ip_port}'))
        device = Android(ip_port, page.server, USE_AS_BOTH, cap_method="Minicap")
        
        if not device.available:
            device.disconnect()
            print("[CLI错误] ADB设备连接失败")
            return False
        
        page.snapshotDevice = page.operateDevice = page.device.snapshotDevice = page.device.operateDevice = device
        bb.pagebar.tags[page.idx].createText(True)
        bb.updateConnectLst(page.idx)
        print(f"[CLI] ADB连接成功: {ip_port}")
        return True
    except Exception as e:
        print(f"[CLI错误] ADB连接失败: {e}")
        return False


def cli_set_apple_type(page, apple_type):
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
            print(f"[CLI] 苹果类型已设置: {apple_type}")
        except Exception as e:
            print(f"[CLI警告] 苹果类型已设置但UI更新失败: {e}")
            print(f"[CLI] 苹果类型已设置: {apple_type}")


def cli_set_run_times(page, times):
    """设置运行次数"""
    if times is None:
        return
    
    try:
        page.appleSet.runTimes.set(times)
        print(f"[CLI] 运行次数: {times}")
    except Exception as e:
        print(f"[CLI错误] 设置运行次数失败: {e}")


def cli_set_battle_type(page, battle_type):
    """设置战斗类型"""
    if not battle_type:
        return
    
    if battle_type == "continuous":
        page.battletype.set(CT.BATTLE_TYPE[0])
        print("[CLI] 战斗类型: 连续出击")
    elif battle_type == "single":
        page.battletype.set(CT.BATTLE_TYPE[1])
        print("[CLI] 战斗类型: 单次")


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

def cli_start_battle(page):
    """开始战斗"""
    log_to_file(f"[CLI] cli_start_battle 被调用")
    
    if Battle is None:
        log_to_file("[CLI错误] Battle 类未导入，无法开始战斗")
        return False
    
    try:
        log_to_file(f"[CLI] 检查从者配置...")
        for i in range(3):
            exist = page.servantGroup[i].exist
            log_to_file(f"[CLI] 从者 {i}: exist={exist}")
            if not exist:
                log_to_file("[CLI错误] 出战从者不足")
                return False
        
        times = page.appleSet.runTimes.get()
        battle_type = page.battletype.get()
        log_to_file(f"[CLI] 战斗参数: 次数={times}, 类型={battle_type}")
        
        log_to_file(f"[CLI] 模拟点击开始按钮...")
        
        # 使用 event_generate 模拟按钮点击，触发 startScript
        # 这样停止按钮也会正常工作
        try:
            # 获取按钮中心位置
            btn_x = page.start.winfo_width() // 2
            btn_y = page.start.winfo_height() // 2
            # 生成点击事件
            page.start.event_generate("<Button-1>", x=btn_x, y=btn_y)
            log_to_file("[CLI] 已触发按钮点击事件")
        except Exception as e:
            import traceback
            log_to_file(f"[CLI Error] 模拟点击失败: {e}")
            log_to_file(traceback.format_exc())
            return False
        return True
    except Exception as e:
        import traceback
        log_to_file(f"[CLI错误] 开始战斗失败: {e}")
        log_to_file(traceback.format_exc())
        return False


if __name__ == "__main__":
    import argparse
    import sys
    
    # 添加当前目录到路径
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true", help="启动 HTTP API 服务模式")
    parser.add_argument("--port", type=int, default=16888, help="HTTP 服务端口")
    args = parser.parse_args()
    
    if args.server:
        # HTTP API 服务模式 - 独立运行
        print('[HTTP API] Starting standalone server...')
        try:
            from BBchannelUI import BBchannelWindow
            bbchannel = BBchannelWindow()
            start_http_server(bbchannel, args.port)
            bbchannel.startBB()
        except ImportError:
            print('[HTTP API] BBchannelUI not available, running without GUI')
            # 创建一个虚拟窗口对象
            class DummyWindow:
                pass
            dummy = DummyWindow()
            start_http_server(dummy, args.port)
            # 保持运行
            import time
            while True:
                time.sleep(1)
    else:
        # 正常 GUI 模式
        try:
            from BBchannelUI import BBchannelWindow
            bbchannel = BBchannelWindow()
            bbchannel.startBB()
        except ImportError:
            print('BBchannelUI not available')
