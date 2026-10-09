#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32-S3 HUB75 LED Matrix Server with OpenClaw Status Display
带有OpenClaw状态显示的LED灯板服务端 - 精美像素风格
"""
# --- deploy: resolve project assets relative to this file (macOS-safe) ---
import os as _os
BASE_DIR = _os.environ.get("INTRIX_HOME") or _os.path.dirname(_os.path.abspath(__file__))

def _first_existing(paths):
    for _p in paths:
        try:
            if _p and _os.path.isfile(_p):
                return _p
        except Exception:
            pass
    return ""


# 小号等宽字体：安卓/容器里没有 /usr/share/fonts，回退到包内 quan.ttf
_MONO_FONT = _first_existing([
    _os.path.join(BASE_DIR, "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    _os.path.join(BASE_DIR, "quan.ttf"),
])


import os
import socket
import json
import threading
import time
import argparse
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template_string, jsonify, request, send_file
import io
from datetime import datetime

# 主题支持
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from themes.kitten import KittenTheme
    from themes.vocab import VocabTheme
    from themes.calendar import CalendarTheme
    from themes.bitcoin import BitcoinTheme
    from themes.fortune import FortuneTheme
    from themes.stock import StockTheme
    from themes.fireworks import FireworksTheme
    from themes.lava import LavaTheme
    from themes.snow import SnowTheme
    from themes.plasma import PlasmaTheme
    from themes.warp import WarpTheme
    from themes.aurora import AuroraTheme
    from themes.ripple import RippleTheme
    from themes.cube import CubeTheme
    from themes.bounce import BounceTheme
    from themes.cyberclock import CyberClockTheme as CyberClockTheme1
    from themes.cyberclock2 import CyberClockTheme
    from themes.gifclock import GifClockTheme
    from themes.pearl import PearlTheme
    from themes.pixellife import PixelLifeTheme
    from themes.theme_manager import ThemeManager
    HAS_THEMES = True
except ImportError as e:
    HAS_THEMES = False
    print(f"⚠️  主题模块加载失败: {e}")

# 默认模式常量
DEFAULT_MODE = 'openclaw_status'

# 所有可用模式列表
ALL_MODES = [
    'openclaw_status', 'demo', 'rainbow', 'text', 'clock', 'matrix', 'pulse',
    'kitten', 'vocab', 'calendar', 'bitcoin', 'fortune', 'stock', 'pearl',
    'gif', 'fireworks', 'lava', 'snow', 'plasma', 'warp', 'aurora', 'ripple', 'cube', 'bounce',
    'cyberclock', 'cyberclock2', 'gifclock', 'pixellife'
]

app = Flask(__name__)


class LEDMatrixServer:
    def __init__(self, tcp_host='0.0.0.0', tcp_port=8080, web_port=5050, width=64, height=64, web_host='0.0.0.0'):
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.web_port = web_port
        self.web_host = web_host
        self.width = width
        self.height = height

        self.clients = {}
        self.running = False
        self.server_socket = None

        # 显示设置
        self.current_mode = 'openclaw_status'
        self.brightness = 253
        self.custom_text = "HELLO"
        self.animation_speed = 1.0
        self.text_font = 'quan'
        self.text_speed = 30

        # 自定义图像
        self.custom_image = None

        # GIF/视频播放
        self.gif_frames = []       # GIF 每帧图像列表
        self.gif_index = 0         # 当前播放帧索引
        self.gif_loaded = False     # GIF 是否已加载
        self.gif_path = None        # 当前 GIF 路径
        self._gif_lock = threading.Lock()

        # 统计
        self.frame_count = 0
        self.start_time = time.time()
        self.fps = 0
        self._fps_frames = 0  # 最近 FPS 窗口内的帧数
        self._fps_window_start = time.time()  # FPS 窗口起始时间
        self._fps_window_seconds = 1.0  # FPS 计算窗口（秒）

        # 预览图像
        self.preview_image = None
        self.lock = threading.Lock()

        # 客户端设置持久化
        self._client_settings_path = os.path.join(BASE_DIR, 'client_settings.json')
        self.client_settings = {}  # {ip: {mode: str, brightness: int, ...}}
        self._load_client_settings()

        # GIF时钟持久化
        self._gifclock_gif_path = os.path.join(BASE_DIR, 'gifclock_background.gif')
        self._gifclock_config_path = os.path.join(BASE_DIR, 'gifclock_config.json')

        # 主题系统
        if HAS_THEMES:
            self.kitten_theme = KittenTheme(width=width, height=height)
            self.vocab_theme = VocabTheme(width=width, height=height)
            self.calendar_theme = CalendarTheme(width=width, height=height)
            self.bitcoin_theme = BitcoinTheme(width=width, height=height)
            self.fortune_theme = FortuneTheme(width=width, height=height)
            self.stock_theme = StockTheme(width=width, height=height)
            self.fireworks_theme = FireworksTheme(width=width, height=height)
            self.lava_theme = LavaTheme(width=width, height=height)
            self.snow_theme = SnowTheme(width=width, height=height)
            self.plasma_theme = PlasmaTheme(width=width, height=height)
            self.warp_theme = WarpTheme(width=width, height=height)
            self.aurora_theme = AuroraTheme(width=width, height=height)
            self.ripple_theme = RippleTheme(width=width, height=height)
            self.cube_theme = CubeTheme(width=width, height=height)
            self.bounce_theme = BounceTheme(width=width, height=height)
            self.cyberclock_theme = CyberClockTheme1(width=width, height=height)
            self.cyberclock2_theme = CyberClockTheme(width=width, height=height)
            self.gifclock_theme = GifClockTheme(width=width, height=height)
            self.pearl_theme = PearlTheme(width=width, height=height)
            self.pixellife_theme = PixelLifeTheme(width=width, height=height)
            # 加载保存的GIF和配置
            if os.path.exists(self._gifclock_gif_path):
                self.gifclock_theme.load_gif(self._gifclock_gif_path)
                print(f"📁 Loaded gifclock background GIF")
            if os.path.exists(self._gifclock_config_path):
                try:
                    with open(self._gifclock_config_path, 'r') as f:
                        cfg = json.load(f)
                        self.gifclock_theme.set_config(**cfg)
                        print(f"📁 Loaded gifclock config")
                except: pass
        else:
            self.kitten_theme = None
            self.vocab_theme = None
            self.calendar_theme = None
            self.bitcoin_theme = None
            self.fortune_theme = None
            self.stock_theme = None
            self.fireworks_theme = None
            self.lava_theme = None
            self.snow_theme = None
            self.plasma_theme = None
            self.warp_theme = None
            self.aurora_theme = None
            self.ripple_theme = None
            self.cube_theme = None
            self.bounce_theme = None
            self.cyberclock_theme = None
            self.cyberclock2_theme = None
            self.gifclock_theme = None
            self.pearl_theme = None

        # OpenClaw 状态
        self.openclaw_status = {
            'session_count': 0,
            'active_sessions': 0,
            'memory_usage': 0.0,
            'cpu_load': 0.0,
            'is_busy': False,
            'last_message': '',
            'model': 'unknown',
            'heartbeat_count': 0,
        }
        self.openclaw_status_history = []
        self._history_maxlen = 30

        # 像素动画状态
        self.anim_frame = 0

        # 调色板 - 高对比度版本
        self.COLORS = {
            'bg': (5, 5, 15),
            # 小龙虾颜色
            'lobster_body': (255, 80, 80),      # 红色虾身
            'lobster_light': (255, 150, 150),   # 浅红高光
            'lobster_dark': (180, 50, 50),      # 暗红
            'lobster_claw': (255, 100, 100),    # 虾钳
            'lobster_eye': (255, 255, 200),     # 眼睛
            'lobster_antenna': (255, 200, 100), # 触须
            # 状态颜色
            'status_green': (0, 255, 150),
            'status_yellow': (255, 220, 0),
            'status_red': (255, 80, 80),
            'bar_bg': (20, 20, 35),
            'text_dim': (150, 150, 180),         # 调亮！
            'text_bright': (255, 255, 255),      # 纯白
            'chart_line': (0, 200, 255),
            'scanline': (255, 255, 255),
            'heartbeat': (255, 120, 180),
        }

    def start(self):
        """启动TCP服务器和Web服务器"""
        self.running = True

        tcp_thread = threading.Thread(target=self._tcp_server_loop)
        tcp_thread.daemon = True
        tcp_thread.start()

        broadcast_thread = threading.Thread(target=self._broadcast_loop)
        broadcast_thread.daemon = True
        broadcast_thread.start()

        print(f"🌐 Web界面: http://localhost:{self.web_port}")
        print(f"📡 TCP端口: {self.tcp_port}")
        from flask_cors import CORS
        CORS(app, resources={r"/api/pearl-data": {"origins": "*"}})
        app.run(host=self.web_host, port=self.web_port, debug=False, use_reloader=False)

    def stop(self):
        self.running = False
        for client in self.clients.values():
            try:
                client['socket'].close()
            except:
                pass
        if self.server_socket:
            self.server_socket.close()

    def _tcp_server_loop(self):
        """TCP服务器循环"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.tcp_host, self.tcp_port))
        self.server_socket.listen(5)

        print(f"🚀 TCP Server started on {self.tcp_host}:{self.tcp_port}")

        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                # 优化TCP发送性能
                client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # 64KB 发送缓冲区
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 禁用Nagle算法
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.running:
                    print(f"❌ Accept error: {e}")

    def _handle_client(self, client_sock, addr):
        """处理客户端连接"""
        print(f"📱 New client: {addr}")

        try:
            client_sock.settimeout(5.0)
            data = client_sock.recv(1024).decode('utf-8').strip()
            client_info = json.loads(data)
            print(f"   Info: {client_info}")

            # 尝试恢复此IP之前的设置
            client_ip = self._get_client_ip(addr)
            saved_settings = self.client_settings.get(client_ip, {})
            restored_mode = saved_settings.get('mode', DEFAULT_MODE)

            with self.lock:
                self.clients[addr] = {
                    'socket': client_sock,
                    'info': client_info,
                    'connected_at': time.time(),
                    'frame_count': 0,
                    'mode': restored_mode,  # 每客户端独立主题
                }

            # 恢复主题设置
            if restored_mode != DEFAULT_MODE:
                print(f"   ↪️ Restored mode: {restored_mode} for {client_ip}")

            self._send_brightness(client_sock, self.brightness)

            while self.running:
                try:
                    data = client_sock.recv(1024)
                    if not data:
                        break
                except socket.timeout:
                    continue
                except:
                    break

        except Exception as e:
            print(f"❌ Client {addr} error: {e}")
        finally:
            print(f"📴 Client disconnected: {addr}")
            with self.lock:
                if addr in self.clients:
                    del self.clients[addr]
            try:
                client_sock.close()
            except:
                pass

    def _broadcast_loop(self):
        """广播图像数据 - 每客户端独立主题"""
        render_interval = 0.050  # ~20fps 渲染
        last_render = 0
        # 缓存: mode -> frame
        frame_cache = {}

        while self.running:
            if self.clients:
                try:
                    now = time.time()
                    render_interval = 0.067 / max(0.5, self.animation_speed)

                    if now - last_render >= render_interval:
                        # 按 mode 分组客户端，每种 mode 只生成一次
                        modes_needed = set()
                        with self.lock:
                            for client in self.clients.values():
                                modes_needed.add(client.get('mode', DEFAULT_MODE))

                        # 生成需要的帧
                        old_cache = frame_cache
                        frame_cache = {}
                        for mode in modes_needed:
                            # 临时切换 current_mode 以复用 _generate_frame
                            saved_mode = self.current_mode
                            self.current_mode = mode
                            frame_cache[mode] = self._generate_frame()
                            self.current_mode = saved_mode

                        self.preview_image = frame_cache.get(
                            self.current_mode,
                            frame_cache.get(DEFAULT_MODE, None)
                        )
                        last_render = now

                        # 发送帧到各个客户端
                        with self.lock:
                            for addr, client in list(self.clients.items()):
                                mode = client.get('mode', DEFAULT_MODE)
                                frame = frame_cache.get(mode)
                                if frame is None:
                                    continue
                                try:
                                    self._send_frame(client['socket'], frame)
                                    client['frame_count'] += 1
                                except Exception as e:
                                    print(f"❌ Send to {addr} failed: {e}")
                                    self._remove_client(addr)

                        # FPS 统计
                        with self.lock:
                            self.frame_count += 1
                            self._fps_frames += 1
                            if now - self._fps_window_start >= self._fps_window_seconds:
                                self.fps = self._fps_frames / (now - self._fps_window_start)
                                self._fps_frames = 0
                                self._fps_window_start = now

                except Exception as e:
                    print(f"❌ Broadcast error: {e}")

                time.sleep(0.001 / self.animation_speed)
            else:
                frame_cache = {}
                last_render = 0
                time.sleep(0.5)

    def _load_client_settings(self):
        """从文件加载客户端设置"""
        try:
            if os.path.exists(self._client_settings_path):
                with open(self._client_settings_path, 'r') as f:
                    self.client_settings = json.load(f)
                print(f"📁 Loaded client settings for {len(self.client_settings)} clients")
        except Exception as e:
            print(f"⚠️ Failed to load client settings: {e}")
            self.client_settings = {}

    def _save_client_settings(self):
        """保存客户端设置到文件"""
        try:
            with open(self._client_settings_path, 'w') as f:
                json.dump(self.client_settings, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save client settings: {e}")

    def _get_client_ip(self, addr):
        """从addr元组提取IP部分（不含端口），用于跨会话识别客户端"""
        return addr[0] if isinstance(addr, tuple) else str(addr)

    def _remove_client(self, addr):
        """移除客户端"""
        if addr in self.clients:
            try:
                self.clients[addr]['socket'].close()
            except:
                pass
            del self.clients[addr]

    def _send_frame(self, sock, rgb_array: np.ndarray):
        """发送一帧到指定 socket"""
        rgb565_data = self._rgb_to_rgb565(rgb_array)
        data_size = len(rgb565_data)
        header = {
            "type": "frame_data",
            "width": self.width,
            "height": self.height,
            "format": "RGB565",
            "data_size": data_size
        }
        header_json = json.dumps(header) + '\n'
        sock.send(header_json.encode('utf-8'))
        sock.sendall(rgb565_data)

    def _generate_frame(self) -> np.ndarray:
        """生成一帧图像"""
        self.anim_frame += 1

        if self.current_mode == 'openclaw_status':
            return self._generate_openclaw_status_frame()
        elif self.current_mode == 'demo':
            return self._generate_demo_frame()
        elif self.current_mode == 'rainbow':
            return self._generate_rainbow_frame()
        elif self.current_mode == 'text':
            return self._generate_text_frame(self.custom_text)
        elif self.current_mode == 'clock':
            return self._generate_clock_frame()
        elif self.current_mode == 'matrix':
            return self._generate_matrix_rain()
        elif self.current_mode == 'pulse':
            return self._generate_pulse()
        elif self.current_mode == 'kitten':
            return self._generate_kitten_frame()
        elif self.current_mode == 'vocab':
            return self._generate_vocab_frame()
        elif self.current_mode == 'calendar':
            return self._generate_calendar_frame()
        elif self.current_mode == 'bitcoin':
            return self._generate_bitcoin_frame()
        elif self.current_mode == 'fortune':
            return self._generate_fortune_frame()
        elif self.current_mode == 'stock':
            return self._generate_stock_frame()
        elif self.current_mode == 'gif':
            return self._generate_gif_frame()
        elif self.current_mode == 'fireworks':
            return self._generate_fireworks_frame()
        elif self.current_mode == 'lava':
            return self._generate_lava_frame()
        elif self.current_mode == 'snow':
            return self._generate_snow_frame()
        elif self.current_mode == 'plasma':
            return self._generate_plasma_frame()
        elif self.current_mode == 'warp':
            return self._generate_warp_frame()
        elif self.current_mode == 'aurora':
            return self._generate_aurora_frame()
        elif self.current_mode == 'ripple':
            return self._generate_ripple_frame()
        elif self.current_mode == 'cube':
            return self._generate_cube_frame()
        elif self.current_mode == 'bounce':
            return self._generate_bounce_frame()
        elif self.current_mode == 'cyberclock':
            return self._generate_cyberclock_frame()
        elif self.current_mode == 'cyberclock2':
            return self._generate_cyberclock2_frame()
        elif self.current_mode == 'gifclock':
            return self._generate_gifclock_frame()
        elif self.current_mode == 'pearl':
            return self._generate_pearl_frame()
        elif self.current_mode == 'pixellife':
            return self._generate_pixellife_frame()
        elif self.current_mode == 'image' and self.custom_image is not None:
            return self.custom_image
        else:
            return self._generate_openclaw_status_frame()

    def _generate_openclaw_status_frame(self) -> np.ndarray:
        """生成精美的OpenClaw状态显示帧"""
        t = time.time()
        img = Image.new('RGB', (self.width, self.height), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        status = self.openclaw_status

        # 记录历史
        if len(self.openclaw_status_history) >= self._history_maxlen:
            self.openclaw_status_history.pop(0)
        self.openclaw_status_history.append({
            'memory': status['memory_usage'],
            'cpu': status['cpu_load'],
        })

        # === 布局分区 ===
        # 顶部: 小猫咪 (y: 2-28)
        # 中部: 状态信息 (y: 30-50)
        # 底部: 趋势图 (y: 52-62) + 文字消息

        # 绘制小猫咪
        self._draw_cat(draw, t, status)

        # 绘制状态条
        self._draw_status_section(draw, status, t)

        # 绘制底部滚动文字
        self._draw_message_display(draw, status, t)

        return np.array(img)

    # ──────────── GIF 播放 ────────────
    def load_gif(self, path: str) -> bool:
        """加载 GIF 文件，返回是否成功"""
        with self._gif_lock:
            try:
                img = Image.open(path)
                if img.format != 'GIF':
                    return False
                
                self.gif_frames = []
                try:
                    while True:
                        # 转换每一帧为 RGB 并调整大小
                        frame = img.copy().convert('RGB')
                        frame = frame.resize((self.width, self.height), Image.LANCZOS)
                        self.gif_frames.append(np.array(frame))
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass
                
                if len(self.gif_frames) == 0:
                    return False
                
                self.gif_index = 0
                self.gif_loaded = True
                self.gif_path = path
                return True
            except Exception as e:
                print(f"GIF load error: {e}")
                self.gif_loaded = False
                return False

    def _generate_gif_frame(self) -> np.ndarray:
        """GIF 播放模式：逐帧播放上传的 GIF"""
        if not self.gif_loaded or len(self.gif_frames) == 0:
            return self._generate_openclaw_status_frame()

        frame = self.gif_frames[self.gif_index].copy()
        self.gif_index = (self.gif_index + 1) % len(self.gif_frames)
        return frame

    def _generate_fireworks_frame(self) -> np.ndarray:
        """烟花模式：华丽粒子烟花表演"""
        if self.fireworks_theme is None:
            return self._generate_openclaw_status_frame()
        return self.fireworks_theme.generate_frame()

    def _generate_lava_frame(self) -> np.ndarray:
        """熔岩灯模式：向上升腾的火焰效果"""
        if self.lava_theme is None:
            return self._generate_openclaw_status_frame()
        return self.lava_theme.generate_frame()

    def _generate_snow_frame(self) -> np.ndarray:
        """雪花模式：雪花飘落效果"""
        if self.snow_theme is None:
            return self._generate_openclaw_status_frame()
        return self.snow_theme.generate_frame()

    def _generate_plasma_frame(self) -> np.ndarray:
        """等离子波浪模式：流动的彩色波纹"""
        if self.plasma_theme is None:
            return self._generate_openclaw_status_frame()
        return self.plasma_theme.generate_frame()

    def _generate_warp_frame(self) -> np.ndarray:
        """Warp Speed 星空模式：星星从中心向外飞散"""
        if self.warp_theme is None:
            return self._generate_openclaw_status_frame()
        return self.warp_theme.generate_frame()

    def _generate_aurora_frame(self) -> np.ndarray:
        """极光模式：缓慢流动的彩色光带"""
        if self.aurora_theme is None:
            return self._generate_openclaw_status_frame()
        return self.aurora_theme.generate_frame()

    def _generate_ripple_frame(self) -> np.ndarray:
        """水波纹模式：滴水泛起的涟漪扩散"""
        if self.ripple_theme is None:
            return self._generate_openclaw_status_frame()
        return self.ripple_theme.generate_frame()

    def _generate_cube_frame(self) -> np.ndarray:
        """旋转立方体模式：3D 透视旋转"""
        if self.cube_theme is None:
            return self._generate_openclaw_status_frame()
        return self.cube_theme.generate_frame()

    def _generate_bounce_frame(self) -> np.ndarray:
        """3D 弹跳球模式"""
        if self.bounce_theme is None:
            return self._generate_openclaw_status_frame()
        return self.bounce_theme.generate_frame()

    def _generate_cyberclock_frame(self) -> np.ndarray:
        """赛博朋克时钟模式"""
        if self.cyberclock_theme is None:
            return self._generate_openclaw_status_frame()
        status = self.openclaw_status
        return self.cyberclock_theme.generate_frame(status)

    def _generate_cyberclock2_frame(self) -> np.ndarray:
        """赛博朋克时钟模式2 (用户自定义)"""
        if self.cyberclock2_theme is None:
            return self._generate_openclaw_status_frame()
        return self.cyberclock2_theme.generate_frame()

    def _generate_gifclock_frame(self) -> np.ndarray:
        """GIF背景时钟模式"""
        if self.gifclock_theme is None:
            return self._generate_openclaw_status_frame()
        return self.gifclock_theme.generate_frame()

    # ──────────── Rainbow ────────────
    def _generate_rainbow_frame(self) -> np.ndarray:
        """彩虹模式：全屏流动光谱波浪（向量化）"""
        t = time.time() % 60  # 只用秒的小数部分，避免 float32 精度问题
        x = np.arange(self.width, dtype=np.float64) / self.width
        y = np.arange(self.height, dtype=np.float64) / self.height
        xx, yy = np.meshgrid(x, y)
        hue = (xx - yy + t * 0.3) % 1.0

        # HSV → RGB（V=1, S=1）
        i = (hue * 6.0).astype(np.int32)
        f = (hue * 6.0) - i
        p = np.zeros_like(hue)
        q = 1.0 - f
        tt = f

        # 6段颜色映射
        r = np.where((i % 6) == 0, 1.0,
              np.where((i % 6) == 1, tt,
              np.where((i % 6) == 2, p,
              np.where((i % 6) == 3, p,
              np.where((i % 6) == 4, 1.0 - tt, 1.0)))))
        g = np.where((i % 6) == 0, 1.0 - tt,
              np.where((i % 6) == 1, 1.0,
              np.where((i % 6) == 2, 1.0,
              np.where((i % 6) == 3, tt,
              np.where((i % 6) == 4, p, p)))))
        b = np.where((i % 6) == 0, p,
              np.where((i % 6) == 1, p,
              np.where((i % 6) == 2, 1.0 - tt,
              np.where((i % 6) == 3, 1.0,
              np.where((i % 6) == 4, p, 1.0 - tt)))))

        rgb = np.stack([(r * 255).astype(np.uint8),
                         (g * 255).astype(np.uint8),
                         (b * 255).astype(np.uint8)], axis=-1)
        return rgb

    # ──────────── Clock ────────────
    def _generate_clock_frame(self) -> np.ndarray:
        """时钟模式：圆盘时钟"""
        t = time.time()
        cx, cy = self.width // 2, self.height // 2
        radius = 26
        img = Image.new('RGB', (self.width, self.height), (5, 5, 20))
        draw = ImageDraw.Draw(img)

        # 外圈
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                      outline=(80, 80, 120), width=1)
        # 内圈
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(200, 200, 255))

        now = datetime.now()
        sec = now.second + t - int(t)
        minute = now.minute + sec / 60.0
        hour = (now.hour % 12) + minute / 60.0

        # 秒针（红色，细长）
        sec_angle = sec / 60.0 * 2 * math.pi - math.pi / 2
        sx = int(cx + 22 * math.cos(sec_angle))
        sy = int(cy + 22 * math.sin(sec_angle))
        draw.line([(cx, cy), (sx, sy)], fill=(255, 80, 80), width=1)

        # 分针（蓝色）
        min_angle = minute / 60.0 * 2 * math.pi - math.pi / 2
        mx = int(cx + 18 * math.cos(min_angle))
        my = int(cy + 18 * math.sin(min_angle))
        draw.line([(cx, cy), (mx, my)], fill=(100, 180, 255), width=2)

        # 时针（白色，粗）
        hr_angle = hour / 12.0 * 2 * math.pi - math.pi / 2
        hx = int(cx + 12 * math.cos(hr_angle))
        hy = int(cy + 12 * math.sin(hr_angle))
        draw.line([(cx, cy), (hx, hy)], fill=(255, 255, 255), width=2)

        # 小时刻度（12个点）
        for h in range(12):
            ang = h / 12.0 * 2 * math.pi - math.pi / 2
            px = int(cx + (radius - 3) * math.cos(ang))
            py = int(cy + (radius - 3) * math.sin(ang))
            draw.ellipse([px - 1, py - 1, px + 1, py + 1], fill=(200, 200, 200))

        # 数字时间显示在底部
        time_str = now.strftime("%H:%M")
        try:
            font = ImageFont.truetype(os.path.join(BASE_DIR, 'quan.ttf'), 8)
        except:
            font = None
        bbox = draw.textbbox((0, 0), time_str, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw // 2, 48), time_str, fill=(150, 150, 200), font=font)

        return np.array(img)

    # ──────────── Matrix Rain ────────────
    def _generate_matrix_rain(self) -> np.ndarray:
        """代码雨模式：随机字母 + 拖影掉落"""
        t = time.time()
        if not hasattr(self, '_rain_cols'):
            self._rain_cols = [{'x': random.randint(0, self.width - 1),
                                 'speed': random.uniform(0.8, 2.0),
                                 'head': random.randint(-30, 0),
                                 'text': [random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$&') for _ in range(20)]}
                                for _ in range(6)]  # 减少到6列

        img = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        for col in self._rain_cols:
            # 更新位置
            col['head'] += col['speed']
            if col['head'] > self.height + 20:
                col['head'] = random.randint(-30, -10)
                col['text'] = [random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$&') for _ in range(20)]
                col['x'] = random.randint(0, self.width - 1)

            head_y = int(col['head'])
            char_h = 6  # 每个字符高度

            # 绘制拖影（从头部往下渐变减淡）
            for i in range(20):
                y = head_y - i * char_h
                if y < 0 or y > self.height:
                    continue
                fade = max(0, 1.0 - i / 12.0)  # 拖影12个字符渐变
                bright = int(255 * fade)
                # 头部是亮白绿色，尾部渐暗
                if i < 2:
                    color = (180, 255, 200)
                else:
                    color = (0, bright, bright // 4)
                ch = col['text'][i % len(col['text'])]
                draw.text((col['x'], y), ch, fill=color)

        return np.array(img)

    # ──────────── Demo (星火/火焰) ────────────
    def _generate_demo_frame(self) -> np.ndarray:
        """演示模式：星火燃烧 + 粒子动画"""
        t = time.time()
        img = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 底部火焰发光
        cx = self.width // 2
        for y in range(self.height - 1, self.height - 20, -1):
            intensity = (self.height - y) / 20.0
            r = int(255 * intensity)
            g = int(100 * intensity * math.sin(t * 5 + y * 0.3))
            b = 0
            draw.rectangle([0, y, self.width, y + 1], fill=(r, g, b))

        # 上方火花粒子
        if not hasattr(self, '_sparks'):
            self._sparks = [{'x': random.uniform(0, self.width),
                              'y': random.uniform(0, self.height),
                              'vx': random.uniform(-0.5, 0.5),
                              'vy': random.uniform(-1.5, -0.5),
                              'life': random.uniform(0, 1),
                              'color': (random.randint(200, 255), random.randint(100, 200), 0)}
                             for _ in range(30)]

        for s in self._sparks:
            s['x'] += s['vx']
            s['y'] += s['vy']
            s['life'] -= 0.015
            if s['life'] <= 0 or s['y'] < 0:
                s['x'] = random.uniform(0, self.width)
                s['y'] = self.height - random.randint(5, 15)
                s['vx'] = random.uniform(-0.5, 0.5)
                s['vy'] = random.uniform(-1.5, -0.5)
                s['life'] = random.uniform(0.5, 1.0)
                s['color'] = (random.randint(200, 255), random.randint(50, 200), 0)

            alpha = int(255 * s['life'])
            r, g, b = s['color']
            draw.ellipse([int(s['x']) - 1, int(s['y']) - 1, int(s['x']) + 1, int(s['y']) + 1],
                         fill=(r, g, b))

        return np.array(img)

    # ──────────── Pulse ────────────
    def _generate_pulse(self) -> np.ndarray:
        """脉冲模式：心跳波纹效果"""
        t = time.time()
        img = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = self.width // 2, self.height // 2
        # 背景波纹
        for r in range(max(cx, cy), 0, -4):
            phase = (t * 2 + r * 0.05) % (2 * math.pi)
            intensity = max(0, math.sin(phase))
            gray = int(60 * intensity)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         outline=(gray, gray // 2, gray // 4), width=1)
        # 中心脉冲
        pulse = int(15 + 15 * abs(math.sin(t * 3)))
        draw.ellipse([cx - pulse, cy - pulse, cx + pulse, cy + pulse],
                     fill=(255, 50, 50))
        draw.ellipse([cx - pulse//2, cy - pulse//2, cx + pulse//2, cy + pulse//2],
                     fill=(255, 200, 200))
        return np.array(img)

    # ──────────── Text ────────────
    def _generate_text_frame(self, text: str) -> np.ndarray:
        """文字模式：滚动文字"""
        t = time.time()
        img = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        font_name = getattr(self, 'text_font', 'quan')
        speed = getattr(self, 'text_speed', 30)

        # 选择字体
        if font_name == 'hzk12':
            char_w = 12
        elif font_name == 'hzk16':
            char_w = 16
        else:
            # quan.ttf
            font = ImageFont.truetype(os.path.join(BASE_DIR, 'quan.ttf'), 10)
            try:
                bbox = font.getbbox(text)
                text_width_px = bbox[2]
            except:
                text_width_px = len(text) * 8
            char_w = text_width_px // max(len(text), 1)

        text_width = len(text) * char_w
        # 线性滚动：文字从右边缘外进入（x=width），向左移动到左侧外（x=-text_width），循环
        cycle = text_width + self.width
        offset = self.width - (int(t * speed) % cycle)

        if font_name == 'hzk12':
            self._draw_text_hzk12(draw, offset, 26, text, (255, 255, 100))
        elif font_name == 'hzk16':
            self._draw_text_hzk16(draw, offset, 22, text, (255, 255, 100))
        else:
            draw.text((offset, 26), text, fill=(255, 255, 100), font=font)

        return np.array(img)

    def _draw_text_hzk12(self, draw, x, y, text, color):
        """用 HZK12 绘制一行汉字（12px高，每个汉字12px宽）
        非 GB2312 字符（ASCII 等）直接跳过，保持滚动连贯性"""
        import os
        hzk_path = os.path.join(BASE_DIR, 'HZK12')
        if not os.path.exists(hzk_path):
            return
        with open(hzk_path, 'rb') as f:
            hzk = f.read()
        cx = x
        for ch in text:
            try:
                cb = ch.encode('gb2312')
            except:
                cx += 8  # 非 GB2312 跳过
                continue
            if len(cb) != 2:
                cx += 8  # ASCII 等单字节字符跳过
                continue
            q, w = cb[0] - 0xA1, cb[1] - 0xA1
            off = 24 * (94 * q + w)
            if off < 0 or off + 24 > len(hzk):
                cx += 12
                continue
            bmp = hzk[off:off + 24]
            for row in range(12):
                for col in range(12):
                    bi = row * 2 + (col // 8)
                    bii = 7 - (col % 8)
                    if bi < len(bmp) and (bmp[bi] >> bii) & 1:
                        draw.point((cx + col, y + row), fill=color)
            cx += 12

    def _draw_text_hzk16(self, draw, x, y, text, color):
        """用 HZK16 绘制一行汉字（16px高，每个汉字16px宽）
        非 GB2312 字符直接跳过"""
        import os
        hzk_path = os.path.join(BASE_DIR, 'HZK16')
        if not os.path.exists(hzk_path):
            return
        with open(hzk_path, 'rb') as f:
            hzk = f.read()
        # 标准 HZK16 至少需要 87*94*32=261504 字节
        if len(hzk) < 100000:
            return
        cx = x
        for ch in text:
            try:
                cb = ch.encode('gb2312')
            except:
                cx += 8
                continue
            if len(cb) != 2:
                cx += 8
                continue
            q, w = cb[0] - 0xA1, cb[1] - 0xA1
            off = 32 * (94 * q + w)
            if off < 0 or off + 32 > len(hzk):
                cx += 16
                continue
            bmp = hzk[off:off + 32]
            for row in range(16):
                for col in range(16):
                    bi = row * 2 + (col // 8)
                    bii = 7 - (col % 8)
                    if bi < len(bmp) and (bmp[bi] >> bii) & 1:
                        draw.point((cx + col, y + row), fill=color)
            cx += 16

    def _draw_cat(self, draw: ImageDraw, t: float, status: dict):
        """绘制可爱的像素小猫咪 - 动画增强版"""
        def i(x): return int(round(x))  # 整数取整辅助
        cx = 32
        cy = 16

        # 动画相位
        bounce = int(round(2 * np.sin(t * 4)))  # 上下弹跳
        breathe = (np.sin(t * 2) + 1) / 2  # 呼吸效果
        tail_phase = int(round(t * 5)) % 3  # 尾巴动画
        ear_phase = int(round(t * 3)) % 2  # 耳朵抖动

        # 颜色
        if status['is_busy']:
            hue = (t * 0.3) % 1.0
            body_color = self._hsv_to_rgb(hue, 0.6, 1.0)
            eye_color = (255, 80, 80)  # 忙碌时红眼
        else:
            body_color = (255, 140, 150)  # 粉色猫
            eye_color = (50, 200, 100)  # 绿色眼睛

        offset_y = bounce

        # ========== 尾巴 ==========
        tail_y = cy + 10 + offset_y
        tail_sway = int(3 * np.sin(t * 6))
        # 尾巴 (弯曲线条)
        for i in range(5):
            ty = int(tail_y + i)
            tx = cx + 4 + int(tail_sway * (i // 3))
            draw.rectangle([tx, ty, tx + 1, ty], fill=body_color)

        # ========== 身体 ==========
        body_top = cy - 2 + offset_y
        body_bottom = cy + 10 + offset_y
        body_left = cx - 6
        body_right = cx + 6

        # 主身体 (椭圆)
        body_scale = int(breathe)
        draw.ellipse([body_left - body_scale, body_top, body_right + body_scale, body_bottom],
                    fill=body_color)
        # 身体高光
        draw.ellipse([body_left + 1, body_top + 1, body_left + 3, body_top + 3],
                    fill=(255, 200, 200))

        # ========== 头部 ==========
        head_top = body_top - 8
        head_left = cx - 7
        head_right = cx + 7
        head_bottom = body_top

        # 头 (圆角方块)
        draw.ellipse([head_left, head_top, head_right, head_bottom],
                    fill=body_color)

        # ========== 耳朵 ==========
        ear_wiggle = ear_phase * 2 - 1  # -1 or 1
        # 左耳
        draw.polygon([(head_left + 1, head_top + 1), (head_left - 1 + ear_wiggle, head_top - 5), (head_left + 4, head_top)],
                    fill=body_color)
        draw.polygon([(head_left + 1, head_top + 1), (head_left + ear_wiggle, head_top - 3), (head_left + 3, head_top)],
                    fill=(255, 180, 180))  # 粉色耳朵内
        # 右耳
        draw.polygon([(head_right - 1, head_top + 1), (head_right + 1 - ear_wiggle, head_top - 5), (head_right - 4, head_top)],
                    fill=body_color)
        draw.polygon([(head_right - 1, head_top + 1), (head_right - ear_wiggle, head_top - 3), (head_right - 3, head_top)],
                    fill=(255, 180, 180))

        # ========== 眼睛 ==========
        eye_blink = int(t * 2) % 8 == 0
        eye_y = head_top + 4

        if not eye_blink:
            # 左眼 (大圆)
            draw.ellipse([cx - 5, eye_y, cx - 2, eye_y + 3], fill=eye_color)
            draw.ellipse([cx - 5, eye_y, cx - 4, eye_y + 1], fill=(255, 255, 255))  # 高光
            # 右眼
            draw.ellipse([cx + 2, eye_y, cx + 5, eye_y + 3], fill=eye_color)
            draw.ellipse([cx + 2, eye_y, cx + 3, eye_y + 1], fill=(255, 255, 255))
        else:
            # 眯眼
            draw.line([(cx - 5, eye_y + 1), (cx - 2, eye_y + 1)], fill=eye_color, width=1)
            draw.line([(cx + 2, eye_y + 1), (cx + 5, eye_y + 1)], fill=eye_color, width=1)

        # ========== 鼻子和嘴巴 ==========
        nose_y = eye_y + 4
        # 鼻子
        draw.polygon([(cx - 1, nose_y), (cx + 1, nose_y), (cx, nose_y + 2)], fill=(255, 150, 150))
        # 嘴巴 (微笑)
        draw.line([(cx, nose_y + 2), (cx - 2, nose_y + 4)], fill=(200, 100, 100), width=1)
        draw.line([(cx, nose_y + 2), (cx + 2, nose_y + 4)], fill=(200, 100, 100), width=1)

        # ========== 胡须 ==========
        whisker_y = nose_y + 1
        # 左胡须
        draw.line([(cx - 3, whisker_y), (cx - 8, whisker_y - 1)], fill=(200, 200, 200), width=1)
        draw.line([(cx - 3, whisker_y + 1), (cx - 8, whisker_y + 1)], fill=(200, 200, 200), width=1)
        draw.line([(cx - 3, whisker_y + 2), (cx - 8, whisker_y + 3)], fill=(200, 200, 200), width=1)
        # 右胡须
        draw.line([(cx + 3, whisker_y), (cx + 8, whisker_y - 1)], fill=(200, 200, 200), width=1)
        draw.line([(cx + 3, whisker_y + 1), (cx + 8, whisker_y + 1)], fill=(200, 200, 200), width=1)
        draw.line([(cx + 3, whisker_y + 2), (cx + 8, whisker_y + 3)], fill=(200, 200, 200), width=1)

        # ========== 前爪 ==========
        paw_y = body_bottom - 2
        # 左爪
        draw.ellipse([body_left, paw_y, body_left + 3, paw_y + 3], fill=body_color)
        draw.ellipse([body_left, paw_y + 3, body_left + 3, paw_y + 4], fill=(255, 180, 180))
        # 右爪
        draw.ellipse([body_right - 3, paw_y, body_right, paw_y + 3], fill=body_color)
        draw.ellipse([body_right - 3, paw_y + 3, body_right, paw_y + 4], fill=(255, 180, 180))

        # ========== 腮红 (空闲时) ==========
        if not status['is_busy'] and int(t * 3) % 4 == 0:
            draw.ellipse([cx - 6, eye_y + 1, cx - 4, eye_y + 3], fill=(255, 180, 180, 100))

    def _draw_pixel_box(self, draw: ImageDraw, x, y, w, h, fill, outline=None):
        """绘制像素风格方块"""
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=fill)
        if outline:
            # 上边框高亮
            draw.line([(x, y), (x + w - 1, y)], fill=outline, width=1)
            # 左边框高亮
            draw.line([(x, y), (x, y + h - 1)], fill=outline, width=1)
            # 下边框暗边
            draw.line([(x, y + h - 1), (x + w - 1, y + h - 1)], fill=(20, 20, 40), width=1)
            draw.line([(x + w - 1, y), (x + w - 1, y + h - 1)], fill=(20, 20, 40), width=1)

    def _draw_status_section(self, draw: ImageDraw, status: dict, t: float):
        """绘制清晰的状态指示区 - 全像素方块文字"""
        y_start = 30

        # === 左侧: 资源使用率 ===
        bar_x = 2
        bar_width = 28
        bar_height = 5

        # 内存条 (用像素方块画 "MEM")
        mem_pct = max(0, min(1, status['memory_usage']))
        mem_color = self._get_usage_color(mem_pct)

        # "MEM" 像素文字 - 每个字符 3x5 像素
        self._draw_text_3x5(draw, bar_x, y_start, "MEM", self.COLORS['text_dim'])
        # 进度条
        self._draw_bar(draw, bar_x + 12, y_start + 1, bar_width - 12, bar_height, mem_pct, mem_color)

        # CPU条
        cpu_y = y_start + 9
        cpu_pct = max(0, min(1, status['cpu_load']))
        cpu_color = self._get_usage_color(cpu_pct)
        self._draw_text_3x5(draw, bar_x, cpu_y, "CPU", self.COLORS['text_dim'])
        self._draw_bar(draw, bar_x + 12, cpu_y + 1, bar_width - 12, bar_height, cpu_pct, cpu_color)

        # === 右侧: 日期时间 ===
        right_x = 40

        # 第一行: 月.日 星期
        now = datetime.now()
        month_str = f"{now.month:02d}"
        day_str = f"{now.day:02d}"
        # 月.日
        self._draw_text_3x5(draw, right_x, y_start, month_str, self.COLORS['text_dim'])
        draw.rectangle([right_x + 8, y_start + 2, right_x + 9, y_start + 2], fill=self.COLORS['text_dim'])
        self._draw_text_3x5(draw, right_x + 10, y_start, day_str, self.COLORS['text_dim'])

        # 星期 (第二行)
        weekdays = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        day_abbr = weekdays[now.weekday()]
        self._draw_text_3x5(draw, right_x + 2, y_start + 7, day_abbr, self.COLORS['text_dim'])

        # 时间 (第三行) - 往上移
        time_y = y_start + 13
        current_time = datetime.now().strftime("%H%M")
        self._draw_text_3x5(draw, right_x, time_y, current_time[:2], self.COLORS['text_bright'])
        # 冒号闪烁
        if int(t * 2) % 2 == 0:
            draw.rectangle([right_x + 14, time_y + 1, right_x + 15, time_y + 1], fill=self.COLORS['text_bright'])
            draw.rectangle([right_x + 14, time_y + 3, right_x + 15, time_y + 3], fill=self.COLORS['text_bright'])
        self._draw_text_3x5(draw, right_x + 17, time_y, current_time[2:], self.COLORS['text_bright'])

        # === 底部: 文字显示区 ===
        self._draw_message_display(draw, status, t)

    def _draw_text_3x5(self, draw: ImageDraw, x: int, y: int, text: str, color: tuple):
        """绘制 3x5 像素风格的文字"""
        # 3x5 像素字体定义 - 优化区分度
        font_3x5 = {
            'M': [[1,0,1],[1,1,1],[1,0,1],[1,0,1],[1,0,1]],  # M
            'E': [[1,1,1],[1,0,1],[1,1,0],[1,0,1],[1,1,1]],  # E
            'C': [[1,1,1],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],  # C
            'P': [[1,1,0],[1,0,1],[1,1,0],[1,0,0],[1,0,0]],  # P
            'U': [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],  # U
            'B': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,1,0]],  # B
            'I': [[0,1,0],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],  # I (竖线)
            'D': [[1,1,0],[1,0,1],[1,0,1],[1,0,1],[1,1,0]],  # D
            'L': [[1,0,0],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],  # L
            'S': [[1,1,1],[1,0,0],[1,1,1],[0,0,1],[1,1,1]],  # S
            'Y': [[1,0,1],[1,0,1],[0,1,0],[0,1,0],[0,1,0]],  # Y
            'A': [[0,1,0],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],  # A (三角形)
            'T': [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],  # T
            'W': [[1,0,1],[1,0,1],[1,0,1],[1,1,1],[0,1,0]],  # W
            'N': [[1,0,1],[1,1,1],[1,1,1],[1,0,1],[1,0,1]],  # N
            'O': [[1,1,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],  # O
            'H': [[1,0,1],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],  # H
            '0': [[1,1,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],
            '1': [[0,1,0],[1,1,0],[0,1,0],[0,1,0],[1,1,1]],
            '2': [[1,1,1],[0,0,1],[1,1,1],[1,0,0],[1,1,1]],
            '3': [[1,1,1],[0,0,1],[1,1,1],[0,0,1],[1,1,1]],
            '4': [[1,0,1],[1,0,1],[1,1,1],[0,0,1],[0,0,1]],
            '5': [[1,1,1],[1,0,0],[1,1,1],[0,0,1],[1,1,1]],
            '6': [[1,1,1],[1,0,0],[1,1,1],[1,0,1],[1,1,1]],
            '7': [[1,1,1],[0,0,1],[0,0,1],[0,0,1],[0,0,1]],
            '8': [[1,1,1],[1,0,1],[1,1,1],[1,0,1],[1,1,1]],
            '9': [[1,1,1],[1,0,1],[1,1,1],[0,0,1],[1,1,1]],
            'F': [[1,1,1],[1,0,0],[1,1,0],[1,0,0],[1,0,0]],  # F (for FRI)
            'R': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,0,1]],  # R (for SAT)
        }

        cx = x
        for char in text.upper():
            if char in font_3x5:
                bitmap = font_3x5[char]
                for row in range(5):
                    for col in range(3):
                        if bitmap[row][col]:
                            draw.rectangle([cx + col, y + row, cx + col, y + row], fill=color)
            cx += 4  # 字符宽度 + 间距

    def _draw_digit_3x5(self, draw: ImageDraw, x: int, y: int, num: int, color: tuple):
        """绘制单个数字 (0-9)"""
        digit = str(num)
        self._draw_text_3x5(draw, x, y, digit if len(digit) == 1 else "9", color)

    def _draw_letter_M(self, draw: ImageDraw, x: int, y: int, color: tuple):
        """绘制像素风格的 M - 更清晰"""
        # 左竖
        draw.rectangle([x, y, x + 1, y + 6], fill=color)
        # 右竖
        draw.rectangle([x + 4, y, x + 5, y + 6], fill=color)
        # 左斜线 (从上到中)
        draw.rectangle([x + 1, y, x + 2, y + 1], fill=color)
        draw.rectangle([x + 2, y + 1, x + 3, y + 2], fill=color)
        # 右斜线 (从中到下)
        draw.rectangle([x + 3, y + 2, x + 4, y + 3], fill=color)
        draw.rectangle([x + 2, y + 3, x + 3, y + 4], fill=color)
        draw.rectangle([x + 1, y + 4, x + 2, y + 5], fill=color)

    def _draw_letter_C(self, draw: ImageDraw, x: int, y: int, color: tuple):
        """绘制像素风格的 C"""
        # 上横
        draw.rectangle([x + 1, y, x + 4, y + 1], fill=color)
        # 左竖
        draw.rectangle([x, y + 1, x + 1, y + 5], fill=color)
        # 下横
        draw.rectangle([x + 1, y + 5, x + 4, y + 6], fill=color)

    def _draw_digit(self, draw: ImageDraw, x: int, y: int, num: int, color: tuple):
        """绘制像素风格的数字"""
        if num == 0:
            # 绘制 0
            draw.rectangle([x + 1, y, x + 3, y + 1], fill=color)  # 上横
            draw.rectangle([x, y + 1, x + 1, y + 5], fill=color)   # 左竖
            draw.rectangle([x + 3, y + 1, x + 4, y + 5], fill=color)  # 右竖
            draw.rectangle([x + 1, y + 5, x + 3, y + 6], fill=color)  # 下横
        elif num == 1:
            # 绘制 1
            draw.rectangle([x + 1, y, x + 2, y + 6], fill=color)
        elif num == 2:
            draw.rectangle([x, y, x + 4, y + 1], fill=color)
            draw.rectangle([x + 2, y + 1, x + 3, y + 3], fill=color)
            draw.rectangle([x, y + 3, x + 4, y + 4], fill=color)
            draw.rectangle([x, y + 4, x + 3, y + 6], fill=color)
        elif num == 3:
            draw.rectangle([x, y, x + 4, y + 1], fill=color)
            draw.rectangle([x + 2, y + 1, x + 3, y + 3], fill=color)
            draw.rectangle([x, y + 3, x + 4, y + 4], fill=color)
            draw.rectangle([x + 2, y + 4, x + 3, y + 6], fill=color)
        elif num == 4:
            draw.rectangle([x, y, x + 1, y + 3], fill=color)
            draw.rectangle([x + 2, y + 1, x + 4, y + 6], fill=color)
        elif num >= 5:
            # 简化：显示一个点表示 5+
            draw.ellipse([x + 1, y + 2, x + 3, y + 4], fill=color)

    def _draw_text_busy(self, draw: ImageDraw, x: int, y: int, color: tuple):
        """绘制 BUSY"""
        # B
        draw.rectangle([x, y, x + 1, y + 5], fill=color)
        draw.rectangle([x + 1, y, x + 3, y + 1], fill=color)
        draw.rectangle([x + 1, y + 2, x + 3, y + 3], fill=color)
        draw.rectangle([x + 1, y + 4, x + 3, y + 5], fill=color)
        # U
        draw.rectangle([x + 4, y, x + 5, y + 4], fill=color)
        draw.rectangle([x + 7, y, x + 8, y + 4], fill=color)
        draw.rectangle([x + 5, y + 4, x + 7, y + 5], fill=color)
        # S (用 5 代替)
        draw.rectangle([x + 9, y, x + 12, y + 1], fill=color)
        draw.rectangle([x + 9, y + 2, x + 10, y + 4], fill=color)
        draw.rectangle([x + 9, y + 4, x + 12, y + 5], fill=color)

    def _draw_text_idle(self, draw: ImageDraw, x: int, y: int, color: tuple):
        """绘制 IDLE"""
        # I
        draw.rectangle([x + 1, y, x + 2, y + 5], fill=color)
        # D
        draw.rectangle([x + 3, y, x + 4, y + 5], fill=color)
        draw.rectangle([x + 4, y, x + 6, y + 1], fill=color)
        draw.rectangle([x + 4, y + 4, x + 6, y + 5], fill=color)
        draw.rectangle([x + 6, y + 1, x + 7, y + 4], fill=color)
        # L
        draw.rectangle([x + 8, y, x + 9, y + 5], fill=color)
        draw.rectangle([x + 9, y + 4, x + 11, y + 5], fill=color)
        # E
        draw.rectangle([x + 12, y, x + 13, y + 5], fill=color)
        draw.rectangle([x + 13, y, x + 15, y + 1], fill=color)
        draw.rectangle([x + 13, y + 2, x + 14, y + 3], fill=color)
        draw.rectangle([x + 13, y + 4, x + 15, y + 5], fill=color)

    def _draw_bar(self, draw: ImageDraw, x, y, width, height, pct, color):
        """绘制进度条"""
        # 背景
        draw.rectangle([x, y, x + width, y + height], fill=self.COLORS['bar_bg'])

        # 填充
        fill_w = max(1, int(width * pct))
        draw.rectangle([x, y, x + fill_w, y + height], fill=color)

        # 像素化高光
        if fill_w > 2:
            draw.line([(x, y), (x + fill_w - 1, y)], fill=(255, 255, 255), width=1)

    def _get_usage_color(self, pct: float) -> tuple:
        """根据使用率获取颜色"""
        if pct < 0.5:
            return self.COLORS['status_green']
        elif pct < 0.8:
            return self.COLORS['status_yellow']
        else:
            return self.COLORS['status_red']

    def _draw_message_display(self, draw: ImageDraw, status: dict, t: float):
        """绘制底部滚动文字显示区 - HZK12中文支持 12x12像素"""
        msg_y = 51
        message = status.get('last_message', '') or "OK"

        # 背景
        draw.rectangle([0, msg_y, 63, msg_y + 12], fill=(5, 5, 15))
        draw.line([(0, msg_y), (63, msg_y)], fill=(50, 50, 80), width=1)

        # 加载HZK12字库（如果还没加载）
        if not hasattr(self, 'hzk12_data'):
            try:
                with open(os.path.join(BASE_DIR, 'HZK12'), 'rb') as f:
                    self.hzk12_data = f.read()
            except:
                self.hzk12_data = None

        # 计算滚动位置 (每个字符14像素宽，留间隙)
        scroll_pos = int(t * 10) % (len(message) * 14 + 64)
        x = 64 - scroll_pos

        for char in message:
            if x < -14 or x > 64:
                x += 14
                continue
            
            # 判断是否是中文
            if ord(char) > 127 and self.hzk12_data:
                self._draw_hzk12_char(draw, x, msg_y + 1, char, (200, 200, 220))
            else:
                self._draw_text_3x5(draw, x, msg_y + 3, char, (200, 200, 220))
            x += 14

    def _draw_hzk12_char(self, draw, x, y, char, color):
        """绘制HZK12格式的12x12中文字符"""
        if not self.hzk12_data:
            return
        try:
            gb = char.encode('gb2312')
            if len(gb) != 2:
                return
            area = gb[0] - 0xA1
            pos = gb[1] - 0xA1
            offset = (area * 94 + pos) * 24
            if offset < 0 or offset >= len(self.hzk12_data):
                return
            bitmap = self.hzk12_data[offset:offset+24]
            for row in range(12):
                byte1 = bitmap[row * 2]
                byte2 = bitmap[row * 2 + 1]
                for col in range(12):
                    if col < 8:
                        bit = (byte1 >> (7 - col)) & 1
                    else:
                        bit = (byte2 >> (15 - col)) & 1
                    if bit:
                        draw.rectangle([x + col, y + row, x + col, y + row], fill=color)
        except:
            pass



    def _draw_hzk16_char(self, draw, x, y, char, color):
        """绘制HZK16格式的16x16中文字符"""
        if not self.hzk16_data:
            return
        try:
            gb = char.encode('gb2312')
            if len(gb) != 2:
                return
            area = gb[0] - 0xA1
            pos = gb[1] - 0xA1
            offset = (area * 94 + pos) * 32
            if offset < 0 or offset >= len(self.hzk16_data):
                return
            bitmap = self.hzk16_data[offset:offset+32]
            for row in range(16):
                byte1 = bitmap[row * 2]
                byte2 = bitmap[row * 2 + 1]
                for col in range(16):
                    if col < 8:
                        bit = (byte1 >> (7 - col)) & 1
                    else:
                        bit = (byte2 >> (15 - col)) & 1
                    if bit:
                        draw.rectangle([x + col, y + row, x + col, y + row], fill=color)
        except:
            pass



    def _draw_12x12_char(self, draw: ImageDraw, x: int, y: int, char: str, color: tuple):
        """绘制12x12像素字符"""
        # 中文字符直接查找，英文转大写
        if ord(char) < 128:  # ASCII字符
            char_lookup = char.upper()
        else:  # 非ASCII（中文等）
            char_lookup = char

        # 12x12像素字符定义
        char_12x12 = {
            # 英文大写 (12x5居中)
            'A': [[0,0,1,1,1,0,0,0,0,0,0,0],[0,1,1,0,0,1,0,0,0,0,0,0],[1,1,0,0,0,0,1,0,0,0,0,0],[1,0,0,1,1,1,1,0,0,0,0,0],[1,0,0,0,0,0,0,1,0,0,0,0]],
            'B': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            'C': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            'D': [[1,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0]],
            'E': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            'F': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0]],
            'G': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0],[1,0,0,1,1,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            'H': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0]],
            'I': [[1,1,1,0,0,0,0,0,0,0,0,0],[0,1,0,0,0,0,0,0,0,0,0,0],[0,1,0,0,0,0,0,0,0,0,0,0],[0,1,0,0,0,0,0,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0,0,0]],
            'J': [[0,0,1,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[1,0,0,1,0,0,0,0,0,0,0,0],[0,1,1,0,0,0,0,0,0,0,0,0]],
            'K': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,1,1,0,0,0,0,0,0],[1,0,0,1,1,0,0,0,0,0,0,0],[1,0,1,0,0,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0]],
            'L': [[1,0,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            'M': [[1,0,0,0,0,0,1,0,0,0,0,0],[1,1,0,0,1,1,1,0,0,0,0,0],[1,0,1,1,0,0,0,1,0,0,0,0],[1,0,0,0,0,0,0,1,0,0,0,0],[1,0,0,0,0,0,0,1,0,0,0,0]],
            'N': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,1,0,0,1,1,0,0,0,0,0,0],[1,0,1,1,0,0,1,0,0,0,0,0],[1,0,0,0,0,0,1,0,0,0,0,0],[1,0,0,0,0,0,1,0,0,0,0,0]],
            'O': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            'P': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0]],
            'Q': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,1,1,1,0,0,0,0,0,0],[0,1,1,1,0,1,0,0,0,0,0,0]],
            'R': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0]],
            'S': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            'T': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0]],
            'U': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            'V': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,0,0,1,0,0,0,0,0,0,0],[0,0,1,1,0,0,0,0,0,0,0,0]],
            'W': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,1,0,1,1,0,0,0,0,0,0],[0,1,0,1,0,0,1,0,0,0,0,0]],
            'X': [[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,0,0,1,0,0,0,0,0,0,0],[0,0,1,1,0,0,0,0,0,0,0,0],[0,1,0,0,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0]],
            'Y': [[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,0,0,1,0,0,0,0,0,0,0],[0,0,1,1,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0]],
            'Z': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            '0': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            '1': [[0,1,0,0,0,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0],[0,1,0,0,0,0,0,0,0,0,0,0],[0,1,0,0,0,0,0,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0,0,0]],
            '2': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,1,1,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            '3': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            '4': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,1,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0]],
            '5': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            '6': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            '7': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0]],
            '8': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            '9': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,1,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            ' ': [[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0]],
            ':': [[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0]],
            '!': [[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0]],
            '.': [[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0]],
            '-': [[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0]],
            # 常用中文 (12x5像素表示)
            '你': [[0,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0]],
            '好': [[1,1,1,0,0,0,0,0,0,0,0,0],[1,0,1,0,0,0,0,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0,0,0],[1,0,1,0,0,0,0,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0,0,0]],
            '我': [[1,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0]],
            '是': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,1,1,1,0,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            '的': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,0,0,0,0,0,0,0]],
            '在': [[1,1,1,0,0,0,0,0,0,0,0,0],[1,0,0,1,0,0,0,0,0,0,0,0],[1,0,0,1,0,0,0,0,0,0,0,0],[1,0,0,1,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0]],
            '不': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0]],
            '了': [[0,1,1,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[0,0,1,0,0,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0]],
            '哈': [[1,1,0,0,0,0,0,0,0,0,0,0],[0,1,1,1,0,0,0,0,0,0,0,0],[0,1,0,0,1,0,0,0,0,0,0,0],[0,1,1,1,0,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0]],
            '哦': [[0,1,1,1,0,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[1,0,0,0,1,0,0,0,0,0,0,0],[0,1,1,1,0,0,0,0,0,0,0,0]],
            '啊': [[1,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,0,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0]],
            '喂': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            '开': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0]],
            '始': [[1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,0,1,0,0,0,0,0,0,0],[0,0,1,1,0,0,0,0,0,0,0,0],[0,0,0,1,0,0,0,0,0,0,0,0],[0,0,1,1,1,0,0,0,0,0,0,0]],
            'O': [[0,1,1,1,1,0,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,0,1,0,0,0,0,0,0],[0,1,1,1,1,0,0,0,0,0,0,0]],
            'K': [[1,0,0,0,0,1,0,0,0,0,0,0],[1,0,0,0,1,1,0,0,0,0,0,0],[1,0,0,1,1,0,0,0,0,0,0,0],[1,0,1,0,0,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0,0,0,0]],
        }

        # 直接查找
        if char_lookup in char_12x12:
            bitmap = char_12x12[char_lookup]
        else:
            # 未定义的字符显示为空
            bitmap = [[0]*12 for _ in range(5)]

        # 绘制像素 (5x12区域，居中显示)
        for row in range(5):
            for col in range(12):
                if bitmap[row][col]:
                    draw.rectangle([x + col, y + row, x + col, y + row], fill=color)

    def _draw_trend_chart(self, draw: ImageDraw):
        """绘制迷你趋势图 (放在MEM/CPU条下方)"""
        chart_x = 4
        chart_y = 43
        chart_w = 34
        chart_h = 5

        # 背景
        draw.rectangle([chart_x, chart_y, chart_x + chart_w, chart_y + chart_h],
                      fill=(15, 15, 30), outline=(30, 30, 50))

        # 绘制网格线 (微弱)
        for gx in range(chart_x + 14, chart_x + chart_w, 14):
            draw.line([(gx, chart_y), (gx, chart_y + chart_h)],
                      fill=(30, 30, 50), width=1)

        # 绘制趋势线
        history = self.openclaw_status_history
        if len(history) >= 2:
            points = []
            for i, h in enumerate(history):
                px = chart_x + 1 + int(i * (chart_w - 2) / self._history_maxlen)
                py = chart_y + chart_h - 2 - int(h['memory'] * (chart_h - 3))
                points.append((px, py))

            # 绘制填充区域
            for i in range(len(points) - 1):
                # 渐变色效果 - 用重复线条模拟
                alpha_factor = (i / len(points))
                r = int(self.COLORS['chart_line'][0] * (0.5 + 0.5 * alpha_factor))
                g = int(self.COLORS['chart_line'][1] * (0.5 + 0.5 * alpha_factor))
                b = int(self.COLORS['chart_line'][2] * (0.5 + 0.5 * alpha_factor))
                draw.line([points[i], points[i + 1]], fill=(r, g, b), width=1)

    def _draw_footer(self, draw: ImageDraw, t: float):
        """绘制底部信息栏"""
        # 运行时间
        uptime = int(time.time() - self.start_time)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        try:
            font = ImageFont.truetype(_MONO_FONT, 5)
        except:
            font = ImageFont.load_default()

        draw.text((4, 61), uptime_str, fill=self.COLORS['text_dim'], font=font)

        # FPS
        fps_text = f"{self.fps:.0f}fps"
        draw.text((52, 61), fps_text, fill=self.COLORS['text_dim'], font=font)

        # 底部扫描线动画
        scan_y = int(t * 40) % 64
        if scan_y > 50:  # 只在底部区域显示
            draw.line([(0, scan_y), (64, scan_y)], fill=(255, 255, 255), width=1)

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple:
        """HSV转RGB，返回整数 RGB"""
        if s == 0.0:
            return (int(v * 255), int(v * 255), int(v * 255))
        i = int(h * 6.0)
        f = (h * 6.0) - i
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        tt = v * (1.0 - s * (1.0 - f))
        i = i % 6
        cases = {
            0: (v, tt, p), 1: (q, v, p), 2: (p, v, tt),
            3: (p, q, v), 4: (tt, p, v), 5: (v, p, q)
        }
        rgb = cases.get(i, (v, v, v))
        return (int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))

    def _rgb_to_rgb565(self, rgb_array: np.ndarray) -> bytes:
        """RGB888转RGB565"""
        if rgb_array.shape != (self.height, self.width, 3):
            rgb_array = np.resize(rgb_array, (self.height, self.width, 3))

        r = rgb_array[:, :, 0].astype(np.uint16)
        g = rgb_array[:, :, 1].astype(np.uint16)
        b = rgb_array[:, :, 2].astype(np.uint16)

        rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        return rgb565.astype(np.uint16).tobytes()

    def _send_frame_to_all(self, rgb_array: np.ndarray):
        """发送帧到所有客户端（兼容旧调用）"""
        rgb565_data = self._rgb_to_rgb565(rgb_array)
        data_size = len(rgb565_data)
        header = {
            "type": "frame_data",
            "width": self.width,
            "height": self.height,
            "format": "RGB565",
            "data_size": data_size
        }
        header_json = json.dumps(header) + '\n'

        disconnected = []
        with self.lock:
            for addr, client in list(self.clients.items()):
                try:
                    sock = client['socket']
                    sock.send(header_json.encode('utf-8'))
                    sock.sendall(rgb565_data)
                    client['frame_count'] += 1
                except Exception as e:
                    print(f"❌ Send failed to {addr}: {e}")
                    disconnected.append(addr)

            for addr in disconnected:
                self._remove_client(addr)

    def _send_brightness(self, sock, brightness: int):
        """发送亮度命令"""
        try:
            cmd = {"type": "brightness", "value": brightness}
            sock.send((json.dumps(cmd) + '\n').encode('utf-8'))
        except:
            pass

    def set_mode(self, mode: str):
        self.current_mode = mode
        print(f"🎨 Mode: {mode}")

    def set_client_mode(self, addr, mode: str) -> bool:
        """设置指定客户端的主题模式，返回是否成功"""
        with self.lock:
            if addr not in self.clients:
                return False
            self.clients[addr]['mode'] = mode
            print(f"🎨 Client {addr} mode: {mode}")
            # 保存设置
            client_ip = self._get_client_ip(addr)
            if client_ip not in self.client_settings:
                self.client_settings[client_ip] = {}
            self.client_settings[client_ip]['mode'] = mode
            self._save_client_settings()
            return True

    def set_brightness(self, brightness: int):
        self.brightness = max(0, min(253, brightness))
        with self.lock:
            for client in self.clients.values():
                self._send_brightness(client['socket'], self.brightness)
        return self.brightness

    def update_openclaw_status(self, status: dict):
        """更新OpenClaw状态"""
        with self.lock:
            self.openclaw_status.update(status)

    def get_openclaw_status(self) -> dict:
        """获取当前OpenClaw状态"""
        with self.lock:
            return dict(self.openclaw_status)

    def _generate_kitten_frame(self) -> np.ndarray:
        """生成小猫主题帧 - 使用独立主题模块"""
        if not HAS_THEMES or self.kitten_theme is None:
            # 回退到默认状态显示
            return self._generate_openclaw_status_frame()

        status = self.get_openclaw_status()
        return self.kitten_theme.generate_frame(status)

    def _generate_vocab_frame(self) -> np.ndarray:
        """生成背单词主题帧"""
        if not HAS_THEMES or self.vocab_theme is None:
            return self._generate_openclaw_status_frame()

        status = self.get_openclaw_status()
        return self.vocab_theme.generate_frame(status)

    def _generate_calendar_frame(self) -> np.ndarray:
        """生成万年历主题帧"""
        if not HAS_THEMES or self.calendar_theme is None:
            return self._generate_openclaw_status_frame()

        status = self.get_openclaw_status()
        return self.calendar_theme.generate_frame(status)

    def _generate_bitcoin_frame(self) -> np.ndarray:
        """生成比特币主题帧"""
        if not HAS_THEMES or self.bitcoin_theme is None:
            return self._generate_openclaw_status_frame()

        status = self.get_openclaw_status()
        return self.bitcoin_theme.generate_frame(status)

    def _generate_fortune_frame(self) -> np.ndarray:
        """生成今日运势主题帧"""
        if not HAS_THEMES or self.fortune_theme is None:
            return self._generate_openclaw_status_frame()

        status = self.get_openclaw_status()
        return self.fortune_theme.generate_frame(status)

    def _generate_stock_frame(self) -> np.ndarray:
        """生成A股主题帧"""
        if not HAS_THEMES or self.stock_theme is None:
            return self._generate_openclaw_status_frame()

        return self.stock_theme.generate_frame()

    def _generate_pearl_frame(self) -> np.ndarray:
        """生成PEARL挖矿Dashboard主题帧"""
        if not HAS_THEMES or self.pearl_theme is None:
            return self._generate_openclaw_status_frame()
        return self.pearl_theme.generate_frame()

    def _generate_pixellife_frame(self) -> np.ndarray:
        """生成 PixelLife 像素养成游戏帧（AI 自主驱动）"""
        if not HAS_THEMES or getattr(self, 'pixellife_theme', None) is None:
            return self._generate_openclaw_status_frame()
        return self.pixellife_theme.generate_frame()


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Intrix（无限矩阵） 控制台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        header {
            text-align: center;
            padding: 20px 0;
            border-bottom: 2px solid #00d4ff;
            margin-bottom: 30px;
        }
        header h1 {
            font-size: 2em;
            background: linear-gradient(45deg, #00d4ff, #00f5d4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card h2 {
            font-size: 1.1em;
            margin-bottom: 15px;
            color: #00d4ff;
        }
        .mode-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }
        .mode-btn {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 10px 4px;
            color: #aaa;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
            font-size: 12px;
        }
        .mode-btn:hover { background: rgba(0,212,255,0.2); border-color: #00d4ff; color: #fff; }
        .mode-btn .icon { font-size: 20px; margin-bottom: 4px; }
        .mode-btn.active {
            background: rgba(0,212,255,0.25);
            border-color: #00d4ff;
            color: #00d4ff;
        }
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(0,0,0,0.3);
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 13px;
        }
        .status-bar span { color: #aaa; }
        .status-bar .value { color: #00d4ff; font-weight: bold; }
        .preview-box {
            background: #000;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }
        .preview-box img {
            max-width: 100%;
            border-radius: 4px;
            image-rendering: pixelated;
        }
        .control-row {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 10px 0;
        }
        .control-row label { color: #aaa; min-width: 60px; font-size: 13px; }
        .control-row input[type=range] { flex: 1; }
        .btn {
            background: rgba(0,212,255,0.2);
            border: 1px solid #00d4ff;
            color: #00d4ff;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }
        .btn:hover { background: rgba(0,212,255,0.35); }
        .btn-primary { background: #00d4ff; color: #1a1a2e; }
        .btn-primary:hover { background: #00f5d4; }
        .stock-config textarea {
            width: 100%;
            background: #1a1a2e;
            border: 1px solid #333;
            color: #fff;
            font-family: monospace;
            font-size: 12px;
            padding: 8px;
            border-radius: 6px;
            resize: vertical;
            box-sizing: border-box;
        }
        .stock-status { margin-top: 8px; font-size: 12px; color: #aaa; }
        .text-input { width: 100%; background: #1a1a2e; border: 1px solid #333; color: #fff; padding: 8px; border-radius: 6px; font-size: 13px; }
        .upload-zone {
            border: 2px dashed rgba(255,255,255,0.2);
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            color: #888;
        }
        .upload-zone:hover { border-color: #00d4ff; color: #00d4ff; }
        .upload-zone input { display: none; }
        #uploadStatus { margin-top: 8px; font-size: 12px; }
        .thm-btn {
            background: #1a1a2e;
            border: 1px solid #333;
            color: #888;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .thm-btn:hover { border-color: #00d4ff; color: #00d4ff; background: #1a2a3a; }
        .thm-btn.active { background: #0a2a1a; border-color: #0f9; color: #0f9; font-weight: bold; }

        /* ── v6.4 theme-scoped layout ───────────────────────────── */
        .theme-group { margin-bottom: 12px; }
        .theme-group:last-child { margin-bottom: 0; }
        .theme-group-title {
            font-size: 11px; color: #667; letter-spacing: 1px;
            margin: 0 0 6px 2px;
        }
        .col-stack { display: flex; flex-direction: column; gap: 20px; }
        .panel-head {
            display: flex; justify-content: space-between;
            align-items: center; gap: 10px;
        }
        .panel-head .tag {
            font-size: 11px; font-weight: normal; color: #00d4ff;
            background: rgba(0,212,255,0.12);
            border: 1px solid rgba(0,212,255,0.35);
            border-radius: 20px; padding: 2px 10px; white-space: nowrap;
        }
        #themePanels {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 14px;
        }
        .tpanel {
            background: rgba(0,0,0,0.22);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 14px;
        }
        .tpanel h3 { font-size: 13px; color: #00d4ff; margin-bottom: 10px; }
        .hint { font-size: 12px; color: #667; line-height: 1.7; }
        .field-label { font-size: 12px; color: #889; margin-bottom: 4px; }
        .fld {
            background: #1a1a2e; border: 1px solid #333; color: #fff;
            padding: 6px; border-radius: 6px; box-sizing: border-box;
            font-size: 12px; width: 100%; font-family: inherit;
        }
        .fld.mono { font-family: monospace; }
        .row { display: flex; gap: 8px; align-items: flex-end; }
        .row > div { flex: 1; }
        .row.tight { align-items: center; }
        .chip { font-size: 11px; color: #889; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎨 Intrix（无限矩阵） 控制台</h1>
        </header>

        <div class="status-bar">
            <span>模式: <span class="value" id="curMode">-</span></span>
            <span>FPS: <span class="value" id="fpsDisplay">-</span></span>
            <span>客户端: <span class="value" id="clientsDisplay">-</span></span>
            <span>CPU: <span class="value" id="cpuDisplay">-</span></span>
            <span>内存: <span class="value" id="memDisplay">-</span></span>
        </div>

        <div class="card" id="clientCard">
            <h2>📱 客户端管理 <button class="btn" style="float:right;font-size:12px;padding:4px 10px;" onclick="refreshClients()">🔄 刷新</button></h2>
            <div id="clientList">
                <div style="color:#666;font-size:12px;padding:10px 0;">暂无客户端连接</div>
            </div>
            <div style="margin-top:10px;padding-top:10px;border-top:1px solid #333;">
                <button class="btn" style="background:#1a4a1a;" onclick="setAllClientsMode(prompt('输入全局主题模式:\n' + ALL_MODES.join(', '))) || null)">🌍 设为全部客户端同一主题</button>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>🎭 主题</h2>

                <div class="theme-group">
                    <div class="theme-group-title">基础</div>
                    <div class="mode-grid">
                        <button class="mode-btn" data-mode="openclaw_status" onclick="setMode('openclaw_status')"><div class="icon">🖥️</div><div>状态</div></button>
                        <button class="mode-btn" data-mode="demo" onclick="setMode('demo')"><div class="icon">🎨</div><div>演示</div></button>
                        <button class="mode-btn" data-mode="rainbow" onclick="setMode('rainbow')"><div class="icon">🌈</div><div>彩虹</div></button>
                        <button class="mode-btn" data-mode="text" onclick="setMode('text')"><div class="icon">📝</div><div>文字</div></button>
                        <button class="mode-btn" data-mode="matrix" onclick="setMode('matrix')"><div class="icon">💻</div><div>代码雨</div></button>
                        <button class="mode-btn" data-mode="pulse" onclick="setMode('pulse')"><div class="icon">💓</div><div>脉冲</div></button>
                    </div>
                </div>

                <div class="theme-group">
                    <div class="theme-group-title">时钟</div>
                    <div class="mode-grid">
                        <button class="mode-btn" data-mode="clock" onclick="setMode('clock')"><div class="icon">🕐</div><div>时钟</div></button>
                        <button class="mode-btn" data-mode="cyberclock" onclick="setMode('cyberclock')"><div class="icon">🤖</div><div>赛博钟</div></button>
                        <button class="mode-btn" data-mode="cyberclock2" onclick="setMode('cyberclock2')"><div class="icon">🌧️</div><div>雨钟</div></button>
                        <button class="mode-btn" data-mode="gifclock" onclick="setMode('gifclock')"><div class="icon">🖼️</div><div>图钟</div></button>
                    </div>
                </div>

                <div class="theme-group">
                    <div class="theme-group-title">生活与工具</div>
                    <div class="mode-grid">
                        <button class="mode-btn" data-mode="pixellife" onclick="setMode('pixellife')"><div class="icon">🧍</div><div>像素人生</div></button>
                        <button class="mode-btn" data-mode="kitten" onclick="setMode('kitten')"><div class="icon">😺</div><div>小猫</div></button>
                        <button class="mode-btn" data-mode="vocab" onclick="setMode('vocab')"><div class="icon">📚</div><div>单词</div></button>
                        <button class="mode-btn" data-mode="calendar" onclick="setMode('calendar')"><div class="icon">📅</div><div>日历</div></button>
                        <button class="mode-btn" data-mode="bitcoin" onclick="setMode('bitcoin')"><div class="icon">₿</div><div>比特币</div></button>
                        <button class="mode-btn" data-mode="fortune" onclick="setMode('fortune')"><div class="icon">☘️</div><div>运势</div></button>
                        <button class="mode-btn" data-mode="stock" onclick="setMode('stock')"><div class="icon">📈</div><div>A股</div></button>
                        <button class="mode-btn" data-mode="pearl" onclick="setMode('pearl')"><div class="icon">⛏️</div><div>Pearl</div></button>
                        <button class="mode-btn" data-mode="gif" onclick="setMode('gif')"><div class="icon">🎞️</div><div>GIF</div></button>
                    </div>
                </div>

                <div class="theme-group">
                    <div class="theme-group-title">动效</div>
                    <div class="mode-grid">
                        <button class="mode-btn" data-mode="fireworks" onclick="setMode('fireworks')"><div class="icon">🎆</div><div>烟花</div></button>
                        <button class="mode-btn" data-mode="lava" onclick="setMode('lava')"><div class="icon">🔥</div><div>熔岩灯</div></button>
                        <button class="mode-btn" data-mode="snow" onclick="setMode('snow')"><div class="icon">❄️</div><div>雪花</div></button>
                        <button class="mode-btn" data-mode="plasma" onclick="setMode('plasma')"><div class="icon">🌊</div><div>波浪</div></button>
                        <button class="mode-btn" data-mode="warp" onclick="setMode('warp')"><div class="icon">🌌</div><div>星空</div></button>
                        <button class="mode-btn" data-mode="aurora" onclick="setMode('aurora')"><div class="icon">🌈</div><div>极光</div></button>
                        <button class="mode-btn" data-mode="ripple" onclick="setMode('ripple')"><div class="icon">💧</div><div>水波</div></button>
                        <button class="mode-btn" data-mode="cube" onclick="setMode('cube')"><div class="icon">📦</div><div>方块</div></button>
                        <button class="mode-btn" data-mode="bounce" onclick="setMode('bounce')"><div class="icon">🏀</div><div>弹球</div></button>
                    </div>
                </div>

            </div>

            <div class="col-stack">
                <div class="card">
                    <h2>📺 预览</h2>
                    <div class="preview-box">
                        <img id="previewImg" src="/api/preview" alt="Preview">
                    </div>
                </div>

                <div class="card">
                    <h2>⚙️ 通用设置</h2>
                    <div class="control-row">
                        <label>亮度</label>
                        <input type="range" id="brightness" min="10" max="255" value="200" oninput="updateBrightness(this.value)">
                        <span id="brightnessVal">200</span>
                    </div>
                    <div class="control-row">
                        <label>速度</label>
                        <input type="range" id="speed" min="0.1" max="3.0" step="0.1" value="1.0" oninput="updateSpeed(this.value)">
                        <span id="speedVal">1.0</span>
                    </div>
                    <div class="hint" style="margin-top:4px;">这两项对所有主题生效。</div>
                </div>
            </div>
        </div>

        <div class="card" id="themePanelCard">
            <h2 class="panel-head">
                <span>🎛️ 主题设置 · <span id="themePanelName">—</span></span>
                <span class="tag" id="themePanelTag">—</span>
            </h2>
            <div id="themePanels">
                <div class="tpanel" data-themes="text" style="display:none;">
                    <h3>📝 滚动文字</h3>
                    <div class="field-label">内容</div>
                    <input type="text" class="fld" id="customText" placeholder="输入滚动文字...">
                    <div class="row tight">
                        <div>
                            <div class="field-label">字体</div>
                            <select class="fld" id="textFont">
                                <option value="quan">quan.ttf</option>
                                <option value="hzk12">HZK12</option>
                                <option value="hzk16">HZK16</option>
                            </select>
                        </div>
                        <button class="btn" onclick="sendText()" style="flex:0 0 auto;">发送</button>
                    </div>
                    <div class="hint" style="margin-top:8px;">发送后自动切到「文字」主题。</div>
                </div>

                <div class="tpanel" data-themes="gif" style="display:none;">
                    <h3>🎞️ GIF / 图片</h3>
                    <div class="upload-zone" onclick="document.getElementById('gifFile').click()">
                        <input type="file" id="gifFile" accept="image/gif,.gif" onchange="uploadGif(this.files[0])">
                        <div style="font-size:13px;">📁 点击上传 GIF</div>
                        <div id="uploadStatus" class="chip" style="margin-top:6px;"></div>
                    </div>
                    <div class="hint" style="margin-top:8px;">上传成功后自动播放，支持多帧动画。</div>
                </div>

                <div class="tpanel stock-config" data-themes="stock" style="display:none;">
                    <h3>📈 A股行情</h3>
                    <div class="field-label">股票代码（每行一个，6 位数字）</div>
                    <div class="hint" style="margin-bottom:6px;">沪市以 6 开头，深市以 0 / 3 开头</div>
                    <textarea id="stockCodes" class="fld mono" rows="4" placeholder="600036&#10;000858&#10;601318"></textarea>
                    <div class="row" style="margin-top:8px;">
                        <button class="btn-primary" onclick="saveStockCodes()" style="flex:1;">💾 保存</button>
                        <button class="btn" onclick="switchStock()" style="flex:1;background:#2a2a4a;">⏭ 切换</button>
                    </div>
                    <div id="stockStatus" class="chip" style="margin-top:6px;"></div>
                </div>

                <div class="tpanel" data-themes="pearl" style="display:none;">
                    <h3>⛏️ Pearl 挖矿数据</h3>
                    <div id="pearlStatus" class="hint">读取中…</div>
                    <button class="btn" style="margin-top:8px;" onclick="refreshPearl()">🔄 刷新</button>
                    <div class="hint" style="margin-top:10px;">
                        这个主题没有可写入的设置项：数据由浏览器端脚本从矿池页面提取后推送
                        <code>/api/pearl-data</code>（worker 数 / 算力 / 余额 / 币价），面板只做展示。
                    </div>
                </div>

                <div class="tpanel" data-themes="gifclock" style="display:none;">
                    <h3>🖼️ GIF 时钟</h3>
                    <div style="margin-top:8px;">
                        <div class="upload-zone" style="padding:10px;margin-bottom:10px;" onclick="document.getElementById('gifclockFile').click()">
                            <input type="file" id="gifclockFile" accept="image/gif,.gif" style="display:none" onchange="uploadGifClock(this.files[0])">
                            <div style="font-size:12px;">📁 上传 GIF 背景</div>
                            <div id="gifclockUploadStatus" class="chip" style="margin-top:4px;"></div>
                        </div>
                    <div style="font-size:12px;color:#aaa;margin-bottom:6px;">时间显示</div>
                    <div style="display:flex;gap:8px;margin-bottom:6px;">
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">大小</label>
                            <input type="number" id="gc_time_size" value="12" min="6" max="32" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">X位置</label>
                            <input type="number" id="gc_time_x" value="0" min="0" max="64" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">Y位置</label>
                            <input type="number" id="gc_time_y" value="20" min="0" max="64" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;box-sizing:border-box;">
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                        <label style="font-size:10px;color:#666;width:50px;">颜色</label>
                        <input type="color" id="gc_time_color" value="#ffffff" style="width:50px;height:24px;border:none;cursor:pointer;">
                        <label style="font-size:10px;color:#666;margin-left:10px;">阴影</label>
                        <input type="checkbox" id="gc_time_shadow" checked style="cursor:pointer;">
                    </div>

                    <div style="font-size:12px;color:#aaa;margin-bottom:6px;margin-top:10px;">日期显示</div>
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                        <input type="checkbox" id="gc_date_show" checked style="cursor:pointer;">
                        <input type="text" id="gc_date_format" value="%Y-%m-%d" placeholder="日期格式" style="flex:1;background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;">
                    </div>
                    <div style="display:flex;gap:8px;margin-bottom:6px;">
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">大小</label>
                            <input type="number" id="gc_date_size" value="8" min="6" max="24" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">颜色</label>
                            <input type="color" id="gc_date_color" value="#c8c8c8" style="width:100%;height:24px;border:none;cursor:pointer;">
                        </div>
                    </div>

                    <div style="font-size:12px;color:#aaa;margin-bottom:6px;margin-top:10px;">星期显示</div>
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                        <input type="checkbox" id="gc_weekday_show" checked style="cursor:pointer;">
                    </div>
                    <div style="display:flex;gap:8px;margin-bottom:8px;">
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">大小</label>
                            <input type="number" id="gc_weekday_size" value="8" min="6" max="24" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:10px;color:#666;">颜色</label>
                            <input type="color" id="gc_weekday_color" value="#9696ff" style="width:100%;height:24px;border:none;cursor:pointer;">
                        </div>
                    </div>

                    <button class="btn-primary" onclick="saveGifClockConfig()" style="width:100%;">💾 保存设置</button>
                    </div>
                </div>

                <div class="tpanel" data-themes="pixellife" style="display:none;" id="llmCard">
                    <h3>🧠 AI 大脑
                        <span id="llmDot" style="float:right;font-size:11px;color:#666;">—</span></h3>
                    <div style="margin-top:8px;">
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                        <label style="font-size:12px;color:#aaa;">启用 LLM</label>
                        <input type="checkbox" id="llm_enabled" style="cursor:pointer;">
                        <label style="font-size:12px;color:#aaa;margin-left:8px;">小人决策</label>
                        <input type="checkbox" id="llm_decide" checked style="cursor:pointer;">
                        <label style="font-size:12px;color:#aaa;margin-left:8px;">NPC 对话</label>
                        <input type="checkbox" id="llm_chat" checked style="cursor:pointer;">
                    </div>
                    <div style="font-size:12px;color:#aaa;margin-bottom:4px;">API 地址（OpenAI 兼容 /v1）</div>
                    <input type="text" id="llm_url" placeholder="http://127.0.0.1:8080/v1" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;">
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">API Key</div>
                            <input type="password" id="llm_key" placeholder="留空 = 不修改" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">模型（留空=自动）</div>
                            <input type="text" id="llm_model" list="llmModelList" placeholder="自动探测" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;">
                            <datalist id="llmModelList"></datalist>
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">单次最大 tokens</div>
                            <input type="number" id="llm_max_tokens" value="256" min="16" max="4096" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">上下文总 tokens</div>
                            <input type="number" id="llm_ctx" value="128000" min="1024" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">并发路数</div>
                            <input type="number" id="llm_conc" value="4" min="1" max="8" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;align-items:center;">
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">超时（秒）</div>
                            <input type="number" id="llm_timeout" value="25" min="3" max="120" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1.4;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">温度</div>
                            <input type="number" id="llm_temp" value="0.85" min="0" max="2" step="0.05" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:12px;color:#aaa;">思考模式</label>
                            <input type="checkbox" id="llm_thinking" style="cursor:pointer;display:block;margin-top:4px;">
                        </div>
                    </div>
                    <div style="margin-top:10px;display:flex;gap:8px;">
                        <button class="btn-primary" onclick="saveLLMConfig()" style="flex:1;">💾 保存</button>
                        <button class="btn" onclick="testLLM()" style="flex:1;background:#2a2a4a;">🔍 测试连接</button>
                    </div>
                    <div style="margin-top:10px;padding:8px 10px;background:#101018;border:1px solid #2a2a3a;border-radius:6px;">
                        <div style="font-size:12px;color:#8fd18f;margin-bottom:6px;">🔢 Token 消耗（累计）</div>
                        <div style="display:flex;gap:22px;">
                            <div style="font-size:12px;color:#aaa;">总量
                                <b id="tokTotal" style="color:#fff;font-size:14px;">—</b>
                                <span style="color:#666;font-size:10px;">tokens</span></div>
                            <div style="font-size:12px;color:#aaa;">次数
                                <b id="tokCalls" style="color:#fff;font-size:14px;">—</b>
                                <span style="color:#666;font-size:10px;">次</span></div>
                        </div>
                        <div id="tokExtra" style="font-size:10px;color:#666;margin-top:5px;line-height:1.5;"></div>
                    </div>
                    <div id="llmStatus" style="margin-top:6px;font-size:11px;color:#aaa;line-height:1.5;"></div>
                    <div style="margin-top:12px;padding-top:10px;border-top:1px solid #26263a;">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <span style="font-size:12px;color:#8fd18f;font-weight:bold;">📡 外部信息源</span>
                            <span id="feedsMeta" style="margin-left:auto;font-size:11px;color:#666;">—</span>
                        </div>
                        <div style="font-size:10px;color:#666;margin-top:2px;line-height:1.5;">
                            新闻、天气、每日热榜都会喂给小人当聊天与决策的参考，并存进世界日志。
                        </div>
                        <div style="display:flex;align-items:center;gap:12px;margin-top:8px;flex-wrap:wrap;">
                            <label style="font-size:12px;color:#aaa;">启用</label>
                            <input type="checkbox" id="feeds_enabled" style="cursor:pointer;">
                            <label style="font-size:12px;color:#aaa;">新闻</label>
                            <input type="checkbox" id="feeds_news_on" style="cursor:pointer;">
                            <label style="font-size:12px;color:#aaa;">天气</label>
                            <input type="checkbox" id="feeds_wx_on" style="cursor:pointer;">
                            <label style="font-size:12px;color:#aaa;">每日热榜</label>
                            <input type="checkbox" id="feeds_hot_on" style="cursor:pointer;">
                        </div>

                        <div style="font-size:12px;color:#aaa;margin-bottom:4px;">新闻 API（默认 60s.viki.moe：每天 15 条国内外精选，免 key）</div>
                        <input type="text" id="feeds_news_url" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;"">
                        <div style="display:flex;gap:8px;margin-top:8px;">
                            <div style="flex:1.2;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">新闻 API Key（选填）</div>
                                <input type="password" id="feeds_news_key" placeholder="默认源不需要" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">给模型看几条</div>
                                <input type="number" id="feeds_news_count" min="1" max="30" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">拉取间隔（秒）</div>
                                <input type="number" id="feeds_news_iv" min="300" max="86400" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                        </div>

                        <div style="display:flex;gap:8px;margin-top:10px;">
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">天气源</div>
                                <select id="feeds_wx_provider" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                                    <option value="open-meteo">Open-Meteo（免 key，推荐）</option>
                                    <option value="wttr">wttr.in（免 key，备选）</option>
                                    <option value="custom">自定义（Open-Meteo 兼容格式）</option>
                                </select>
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">城市</div>
                                <input type="text" id="feeds_city" placeholder="北京" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                        </div>
                        <div style="display:flex;gap:8px;margin-top:8px;">
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">纬度（留空=按城市自动定位）</div>
                                <input type="text" id="feeds_lat" placeholder="自动" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;"">
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">经度</div>
                                <input type="text" id="feeds_lon" placeholder="自动" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;"">
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">天气间隔（秒）</div>
                                <input type="number" id="feeds_wx_iv" min="300" max="86400" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                        </div>

                        <div style="display:flex;align-items:center;gap:8px;margin-top:12px;">
                            <span style="font-size:12px;color:#c9a227;font-weight:bold;">🔥 每日热榜</span>
                            <span style="font-size:10px;color:#666;">三家都免 key；实测 60s.viki.moe 的 B站接口会 500，所以 B站 直接走官方</span>
                        </div>
                        <div style="display:flex;gap:8px;margin-top:8px;">
                            <div style="flex:1.6;">
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <input type="checkbox" id="feeds_dy_on" style="cursor:pointer;">
                                    <span style="font-size:12px;color:#aaa;">抖音</span>
                                </div>
                                <input type="text" id="feeds_dy_url" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;"margin-top:4px;">
                            </div>
                            <div style="flex:1.6;">
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <input type="checkbox" id="feeds_xhs_on" style="cursor:pointer;">
                                    <span style="font-size:12px;color:#aaa;">小红书</span>
                                </div>
                                <input type="text" id="feeds_xhs_url" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;"margin-top:4px;">
                            </div>
                        </div>
                        <div style="display:flex;gap:8px;margin-top:8px;">
                            <div style="flex:2.2;">
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <input type="checkbox" id="feeds_bili_on" style="cursor:pointer;">
                                    <span style="font-size:12px;color:#aaa;">B站热搜</span>
                                </div>
                                <input type="text" id="feeds_bili_url" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;font-family:monospace;font-size:12px;"margin-top:4px;">
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">每平台看几条</div>
                                <input type="number" id="feeds_hot_count" min="1" max="20" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:12px;color:#aaa;margin-bottom:4px;">热榜间隔（秒）</div>
                                <input type="number" id="feeds_hot_iv" min="300" max="86400" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                            </div>
                        </div>

                        <div style="margin-top:8px;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">热榜 API Key（三家默认都不需要，留空即可）</div>
                            <input type="password" id="feeds_hot_key" placeholder="留空" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                        </div>

                        <div style="margin-top:10px;display:flex;gap:8px;">
                            <button class="btn-primary" onclick="saveFeedsConfig()" style="flex:1;">💾 保存</button>
                            <button class="btn" onclick="refreshFeedsNow()" style="flex:1;background:#2a2a4a;">🔄 立即刷新</button>
                        </div>
                        <div id="feedsPreview" style="margin-top:10px;padding:8px;background:#101018;border:1px solid #26263a;border-radius:6px;font-size:11px;color:#aab;line-height:1.7;max-height:240px;overflow-y:auto;"></div>
                        <div id="feedsStatus" style="margin-top:6px;font-size:11px;color:#aaa;"></div>

                        <div style="margin-top:14px;padding-top:10px;border-top:1px solid #26263a;">
                            <div style="font-size:12px;color:#8fd18f;font-weight:bold;">🎬 底部字幕</div>
                            <div style="font-size:10px;color:#666;margin-top:2px;line-height:1.5;">
                                屏幕最下面那行滚动播报的速度。慢的话往右拉，1.0× 是原来的速度。
                            </div>
                            <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
                                <input type="range" id="sub_speed" min="0.5" max="4" step="0.1" value="1.6"
                                       oninput="subSpeedSlide(this.value)" style="flex:1;">
                                <span id="sub_speedVal" style="font-size:12px;color:#fff;width:44px;text-align:right;">1.6×</span>
                                <button class="btn" onclick="saveSubSpeed()" style="width:82px;background:#2a2a4a;">💾 保存</button>
                            </div>
                            <div id="subSpeedStatus" style="margin-top:6px;font-size:11px;color:#aaa;"></div>
                        </div>
                    </div>
                </div>
                </div>

                <div class="tpanel" data-themes="pixellife" style="display:none;" id="peopleCard">
                    <h3>👥 像素居民档案
                        <span id="peopleMeta" style="float:right;font-size:11px;color:#666;">—</span></h3>
                    <div id="heroPanel" style="margin-top:8px;"></div>
                    <div id="peopleList" style="margin-top:8px;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px;"></div>
                </div>
                <div class="tpanel" data-themes="pixellife" style="display:none;" id="memoryCard">
                    <h3>🧾 长期记忆
                        <span id="memMeta" style="float:right;font-size:11px;color:#666;">—</span></h3>
                    <div id="memStat" style="margin-top:8px;font-size:12px;color:#aaa;line-height:1.7;"></div>
                    <div style="display:flex;align-items:center;gap:10px;margin:10px 0 2px;">
                        <label style="font-size:12px;color:#aaa;">启用记忆</label>
                        <input type="checkbox" id="mem_enabled" style="cursor:pointer;">
                        <label style="font-size:12px;color:#aaa;margin-left:8px;">每日经历（跨天用 LLM 生成）</label>
                        <input type="checkbox" id="mem_daily" style="cursor:pointer;">
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">聊天记录上限（MB）</div>
                            <input type="number" id="mem_chat_max" min="1" max="2048" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">上下文取最近（条）</div>
                            <input type="number" id="mem_tail" min="10" max="100000" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">每人日志上限（条）</div>
                            <input type="number" id="mem_day_max" min="100" max="1000000" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">愿望清单上限（条）</div>
                            <input type="number" id="mem_wish_max" min="10" max="100000" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;align-items:flex-end;">
                        <div style="flex:1.4;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">注入原话条数（0=关闭，&gt;0 可能复读）</div>
                            <input type="number" id="mem_tail_lines" min="0" max="10" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;">
                        </div>
                        <button class="btn-primary" onclick="saveMemoryConfig()" style="flex:1;">💾 保存</button>
                    </div>
                    <div id="memWishes" style="margin-top:8px;font-size:11px;color:#c9a227;line-height:1.6;"></div>
                    <div id="memStatus" style="margin-top:6px;font-size:11px;color:#aaa;line-height:1.5;"></div>
                </div>
                <div class="tpanel" data-themes="pixellife" style="display:none;" id="chatCard">
                    <h3>💬 和主角说话
                        <span id="chatMeta" style="float:right;font-size:11px;color:#666;">—</span></h3>
                    <div id="chatLog" style="margin-top:8px;height:260px;overflow-y:auto;background:#0c0c14;border:1px solid #26263a;border-radius:8px;padding:10px;font-size:12px;line-height:1.7;"></div>
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <input type="text" id="chatInput" placeholder="跟他说点什么，他会记在心上…" style="flex:1;background:#1a1a2e;border:1px solid #333;color:#fff;padding:8px;border-radius:6px;box-sizing:border-box;">
                        <button class="btn-primary" onclick="sendHeroChat()" id="chatSend" style="width:76px;">发送</button>
                    </div>
                    <div style="margin-top:6px;font-size:11px;color:#888;line-height:1.5;">他的回答会出现在屏幕下方的滚动播报里；让他做的事写进愿望清单，心情也会跟着变。</div>
                    <div id="chatStatus" style="margin-top:4px;font-size:11px;color:#aaa;"></div>
                </div>
                <div class="tpanel" data-themes="pixellife" style="display:none;" id="worldlogCard">
                    <h3>🌍 世界日志
                        <span id="wlMeta" style="float:right;font-size:11px;color:#666;">—</span></h3>
                    <div style="font-size:10px;color:#666;margin-top:2px;line-height:1.5;">
                        天气、新闻、每日热榜按天归档，一条就是一天（默认可存 10000 天）。
                        小人做决定、聊天、写日记都会先看一眼这里。每个平台每天一个文件，写入只动今天那个。
                    </div>
                    <div id="wlStat" style="margin-top:8px;font-size:12px;color:#aaa;line-height:1.7;"></div>
                    <div style="display:flex;gap:8px;margin-top:10px;">
                        <div style="flex:1.2;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">保存天数上限（1 条 = 1 天）</div>
                            <input type="number" id="wl_max_days" min="1" max="10000" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">每天留几条新闻</div>
                            <input type="number" id="wl_news_per_day" min="5" max="200" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:12px;color:#aaa;margin-bottom:4px;">每平台留几条热榜</div>
                            <input type="number" id="wl_hot_per_day" min="3" max="100" style="style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:6px;border-radius:4px;box-sizing:border-box;"">
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
                        <label style="font-size:12px;color:#aaa;">启用世界日志</label>
                        <input type="checkbox" id="wl_enabled" style="cursor:pointer;">
                        <button class="btn-primary" onclick="saveWorldLogConfig()" style="margin-left:auto;width:110px;">💾 保存</button>
                    </div>
                    <div id="wlPreview" style="margin-top:10px;padding:8px;background:#101018;border:1px solid #26263a;border-radius:6px;font-size:11px;color:#aab;line-height:1.7;max-height:300px;overflow-y:auto;"></div>
                    <div id="wlStatus" style="margin-top:6px;font-size:11px;color:#aaa;"></div>
                </div>
            </div>
            <div id="noThemePanel" class="hint" style="display:none;">
                这个主题没有专属设置，用上面的通用设置就够了。
            </div>
        </div>
    </div>

    <script>
        const ALL_MODES = ['openclaw_status','demo','rainbow','text','clock','matrix','pulse','kitten','vocab','calendar','bitcoin','fortune','stock','pearl','pixellife','gif','fireworks','lava','snow','plasma','warp','aurora','ripple','cube','bounce','cyberclock','cyberclock2','gifclock'];

        const MODE_NAMES = {
            'openclaw_status':'🖥️ 状态','demo':'🎨 演示','rainbow':'🌈 彩虹','text':'📝 文字','clock':'🕐 时钟',
            'matrix':'💻 代码雨','pulse':'💓 脉冲','kitten':'😺 小猫','vocab':'📚 单词','calendar':'📅 日历',
            'bitcoin':'₿ 比特币','fortune':'☘️ 运势','stock':'📈 A股','pearl':'⛏️ Pearl','pixellife':'🧍 像素人生',
            'gif':'🎞️ GIF','fireworks':'🎆 烟花','lava':'🔥 熔岩灯','snow':'❄️ 雪花','plasma':'🌊 波浪',
            'warp':'🌌 星空','aurora':'🌈 极光','ripple':'💧 水波','cube':'📦 方块','bounce':'🏀 弹球',
            'cyberclock':'🤖 赛博钟','cyberclock2':'🌧️ 雨钟','gifclock':'🖼️ 图钟'
        };

        // ── 每个主题真正需要的设置面板（v6.4） ──────────────────────
        // 没列在这里的主题没有专属设置，只显示通用设置即可。
        const THEME_PANELS = {
            'text':      ['text'],        // 滚动文字 + 字体
            'gif':       ['gif'],         // GIF 上传
            'stock':     ['stock'],       // 股票代码
            'gifclock':  ['gifclock'],    // 背景图 + 时间/日期/星期
            'pearl':     ['pearl'],       // 只读：数据源状态
            'pixellife': ['pixellife'],   // AI 大脑 + 居民档案
        };

        let _themeShown = null;

        function applyThemePanel(mode) {
            if (mode === _themeShown) return;
            _themeShown = mode;
            const want = THEME_PANELS[mode] || [];
            let shown = 0;
            document.querySelectorAll('#themePanels .tpanel').forEach(el => {
                const mine = (el.dataset.themes || '').split(' ').filter(Boolean);
                const on = mine.some(t => want.indexOf(t) >= 0);
                el.style.display = on ? '' : 'none';
                if (on) shown++;
            });
            document.getElementById('noThemePanel').style.display = shown ? 'none' : 'block';
            document.getElementById('themePanelName').textContent = MODE_NAMES[mode] || mode;
            document.getElementById('themePanelTag').textContent =
                shown ? (shown + ' 项专属设置') : '无专属设置';
            if (mode === 'gifclock') loadGifClockConfig();
            if (mode === 'pearl') refreshPearl();
            if (mode === 'pixellife') { refreshPeople(); loadLLMConfig(); refreshMemory(); refreshFeeds(); refreshHeroChat();
                refreshWorldLog(); refreshSubSpeed(); }
        }

        async function refreshClients() {
            try {
                const res = await fetch('/api/clients');
                const data = await res.json();
                const card = document.getElementById('clientCard');
                const list = document.getElementById('clientList');
                if (!data.clients || data.clients.length === 0) {
                    card.style.display = 'block';
                    list.innerHTML = '<div style="color:#666;font-size:12px;padding:10px 0;">暂无客户端连接</div>';
                    return;
                }
                card.style.display = 'block';
                list.innerHTML = data.clients.map(c => {
                    const btnList = ALL_MODES.map(m =>
                        `<button class="thm-btn ${c.mode === m ? 'active' : ''}" onclick="setClientMode('${c.addr}','${m}')" title="${MODE_NAMES[m]||m}">${MODE_NAMES[m]||m}</button>`
                    ).join('');
                    return `<div style="margin-bottom:12px;padding:8px;background:#111;border-radius:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="color:#888;font-size:12px;">${c.addr}</span>
                            <span style="color:#0f9;font-size:11px;">● 在线</span>
                        </div>
                        <div style="font-size:11px;color:#555;margin-bottom:6px;">当前: <span style="color:#aaa;" id="cur-${c.addr.replace(/[^a-zA-Z0-9]/g,'')}">${MODE_NAMES[c.mode]||c.mode}</span></div>
                        <div style="display:flex;flex-wrap:wrap;gap:4px;">${btnList}</div>
                    </div>`;
                }).join('');
            } catch(e) { console.log('refreshClients error:', e); }
        }

        async function setClientMode(addr, mode) {
            try {
                await fetch(`/api/client/${addr}/mode`, {
                    method: 'PUT',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({mode})
                });
                // 更新显示的文字 + 高亮按钮
                const shortAddr = addr.replace(/[^a-zA-Z0-9]/g,'');
                const cur = document.getElementById('cur-' + shortAddr);
                if (cur) cur.textContent = MODE_NAMES[mode] || mode;
                document.querySelectorAll(`[onclick^="setClientMode('${addr}'"]`).forEach(b => {
                    b.classList.toggle('active', b.textContent.trim() === (MODE_NAMES[mode] || mode));
                });
                // 切换预览到该模式（setMode 会同步主题专属设置面板）
                await setMode(mode);
            } catch(e) { console.error('setClientMode error:', e); }
        }

        async function setAllClientsMode(mode) {
            if (!mode) return;
            try {
                await fetch('/api/clients/mode', {
                    method: 'PUT',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({mode})
                });
                refreshClients();
                updatePreview();
            } catch(e) { console.error('setAllClientsMode error:', e); }
        }

        async function setMode(mode) {
            console.log('setMode called with:', mode);
            try {
                const res = await fetch('/api/mode', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({mode})
                });
                console.log('Response status:', res.status);
                const data = await res.json();
                console.log('Response data:', data);
                if (data.success) {
                    updateStatus();
                    updatePreview();
                    // 只显示当前主题的专属设置
                    applyThemePanel(mode);
                }
            } catch(e) { console.error('切换失败:', e); alert('切换失败: ' + e.message); }
        }

        function updateBrightness(val) {
            document.getElementById('brightnessVal').textContent = val;
            fetch('/api/brightness', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({brightness: parseInt(val)})
            });
        }

        function updateSpeed(val) {
            document.getElementById('speedVal').textContent = val;
            fetch('/api/speed', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({speed: parseFloat(val)})
            });
        }

        function sendText() {
            const text = document.getElementById('customText').value;
            const font = document.getElementById('textFont').value;
            fetch('/api/mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: 'text', text, font})
            });
        }

        async function updateStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('curMode').textContent = data.mode || '-';
                document.getElementById('fpsDisplay').textContent = data.fps ? data.fps.toFixed(1) : '-';
                document.getElementById('clientsDisplay').textContent = data.clients || 0;
                // 更新 CPU 和内存
                fetch('/api/openclaw-status')
                    .then(r => r.json())
                    .then(s => {
                        document.getElementById('cpuDisplay').textContent = s.cpu_load ? Math.round(s.cpu_load * 100) + '%' : '-';
                        document.getElementById('memDisplay').textContent = s.memory_usage ? Math.round(s.memory_usage * 100) + '%' : '-';
                    });
                document.getElementById('brightness').value = data.brightness || 200;
                document.getElementById('brightnessVal').textContent = data.brightness || 200;
                document.getElementById('speed').value = data.speed || 1.0;
                document.getElementById('speedVal').textContent = data.speed || 1.0;
                // Update active button (exact match on data-mode)
                document.querySelectorAll('.mode-btn').forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.mode === data.mode);
                });
                // 面板跟随真实模式（含客户端切走的情况）
                applyThemePanel(data.mode);
            } catch(e) { console.log('Status update error:', e); }
        }

        function updatePreview() {
            document.getElementById('previewImg').src = '/api/preview?t=' + Date.now();
        }

        function saveStockCodes() {
            const text = document.getElementById('stockCodes').value;
            const codes = text.split('\\n').map(c => c.trim()).filter(c => c);
            fetch('/api/stock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({codes})
            }).then(r => r.json()).then(data => {
                document.getElementById('stockStatus').textContent =
                    '✅ 已保存 ' + codes.length + ' 只，当前: ' + data.current;
            }).catch(e => {
                document.getElementById('stockStatus').textContent = '❌ 保存失败: ' + e.message;
            });
        }

        function switchStock() {
            fetch('/api/stock/next', {method:'POST'})
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stockStatus').textContent = '⏭ 当前: ' + data.current;
                    updatePreview();
                });
        }

        function loadStockCodes() {
            fetch('/api/stock')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stockCodes').value = data.codes.join('\\n');
                    document.getElementById('stockStatus').textContent = '当前: ' + data.current;
                });
        }

        // ── PixelLife 长期记忆 ──────────────────────────────────────
        async function refreshMemory() {
            try {
                const res = await fetch('/api/pixellife/memory');
                const d = await res.json();
                if (d.error) { document.getElementById('memStatus').textContent = '❌ ' + d.error; return; }
                const c = d.config || {}, ch = d.chat || {}, dy = d.days || {}, wi = d.wishes || {};
                document.getElementById('mem_enabled').checked = !!c.enabled;
                document.getElementById('mem_daily').checked = !!c.daily_enabled;
                document.getElementById('mem_chat_max').value = c.chat_max_mb;
                document.getElementById('mem_tail').value = c.chat_context_tail;
                document.getElementById('mem_day_max').value = c.day_max_per_who;
                document.getElementById('mem_wish_max').value = c.wish_max;
                document.getElementById('mem_tail_lines').value = c.chat_recall_lines;
                const mb = ((ch.bytes || 0) / 1048576).toFixed(2);
                document.getElementById('memMeta').textContent =
                    (ch.records || 0) + ' 条对话 · ' + mb + ' MB';
                const pend = (d.pending || []).length;
                document.getElementById('memStat').innerHTML =
                    '对话记录 <b>' + (ch.records || 0) + '</b> 条，' + mb + ' / ' + c.chat_max_mb + ' MB' +
                    '　（满了自动淘汰最旧的）<br>' +
                    '每日经历 <b>' + (dy.total || 0) + '</b> 条，覆盖 <b>' +
                    (dy.people || []).length + '</b> 人' +
                    (pend ? '　· 生成中 ' + pend : '') + '<br>' +
                    '愿望清单 <b>' + (wi.count || 0) + '</b> 条（给后续版本更新当线索）';
                const ws = (wi.recent || []).slice(-8).reverse();
                document.getElementById('memWishes').innerHTML = ws.length
                    ? '最近愿望：' + ws.map(w => '「' + w.text + '」').join(' ') : '';
                const errs = d.errors || [];
                document.getElementById('memStatus').textContent = errs.length ? ('⚠️ ' + errs.slice(-2).join(' / ')) : '';
            } catch(e) { console.log('memory load error', e); }
        }

        async function saveMemoryConfig() {
            const body = {
                enabled: document.getElementById('mem_enabled').checked,
                daily_enabled: document.getElementById('mem_daily').checked,
                chat_max_mb: +document.getElementById('mem_chat_max').value,
                chat_context_tail: +document.getElementById('mem_tail').value,
                day_max_per_who: +document.getElementById('mem_day_max').value,
                wish_max: +document.getElementById('mem_wish_max').value,
                chat_recall_lines: +document.getElementById('mem_tail_lines').value
            };
            try {
                const res = await fetch('/api/pixellife/memory', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
                const d = await res.json();
                document.getElementById('memStatus').textContent = d.error ? ('❌ ' + d.error) : '✅ 已保存';
                refreshMemory();
            } catch(e) { document.getElementById('memStatus').textContent = '❌ ' + e; }
        }

        // ── PixelLife 新闻与天气 ───────────────────────────────────
        function esc(s) {
            return String(s ?? '').replace(/[&<>"']/g, m => (
                {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
        }

        function ago(sec) {
            if (sec == null) return '从未';
            if (sec < 60) return sec + '秒';
            if (sec < 3600) return Math.round(sec / 60) + '分钟';
            return Math.round(sec / 3600) + '小时';
        }

        async function refreshFeeds() {
            try {
                const res = await fetch('/api/pixellife/feeds');
                const d = await res.json();
                if (d.error) { document.getElementById('feedsStatus').textContent = '❌ ' + d.error; return; }
                const c = d.config || {};
                document.getElementById('feeds_enabled').checked = !!c.enabled;
                document.getElementById('feeds_news_on').checked = !!c.news_enabled;
                document.getElementById('feeds_wx_on').checked = !!c.weather_enabled;
                document.getElementById('feeds_news_url').value = c.news_url || '';
                document.getElementById('feeds_news_count').value = c.news_count ?? 8;
                document.getElementById('feeds_news_iv').value = c.news_interval ?? 1800;
                document.getElementById('feeds_wx_provider').value = c.weather_provider || 'open-meteo';
                document.getElementById('feeds_city').value = c.city || '';
                document.getElementById('feeds_lat').value = c.lat ?? '';
                document.getElementById('feeds_lon').value = c.lon ?? '';
                document.getElementById('feeds_wx_iv').value = c.weather_interval ?? 1800;
                document.getElementById('feeds_hot_on').checked = !!c.hot_enabled;
                document.getElementById('feeds_dy_on').checked = !!c.douyin_enabled;
                document.getElementById('feeds_dy_url').value = c.douyin_url || '';
                document.getElementById('feeds_xhs_on').checked = !!c.xhs_enabled;
                document.getElementById('feeds_xhs_url').value = c.xhs_url || '';
                document.getElementById('feeds_bili_on').checked = !!c.bili_enabled;
                document.getElementById('feeds_bili_url').value = c.bili_url || '';
                document.getElementById('feeds_hot_count').value = c.hot_count ?? 6;
                document.getElementById('feeds_hot_iv').value = c.hot_interval ?? 3600;
                const w = d.weather, n = d.news;
                let html = '';
                if (w) {
                    html += '<div style="color:#8fd18f;">🌤 ' + esc(w.city) + ' ' + esc(w.text) +
                            ' ' + (w.tmin ?? '?') + '~' + (w.tmax ?? '?') + '℃ · 湿度' +
                            (w.humidity ?? '?') + '% · 源 ' + esc(w.provider) +
                            '（' + ago(d.weather_age) + '前）</div>';
                } else {
                    html += '<div style="color:#666;">天气还没拉到</div>';
                }
                if (n && n.items && n.items.length) {
                    html += '<div style="margin-top:6px;color:#c9a227;">📰 ' + esc(n.date || '') +
                            ' ' + n.total + ' 条（' + ago(d.news_age) + '前）</div>';
                    html += n.items.slice(0, 8).map(t => '<div>· ' + esc(t) + '</div>').join('');
                } else {
                    html += '<div style="color:#666;margin-top:4px;">新闻还没拉到</div>';
                }
                const h = d.hot || {};
                const hk = Object.keys(h);
                if (hk.length) {
                    html += '<div style="margin-top:6px;color:#7fc9e8;">🔥 每日热榜</div>';
                    hk.forEach(k => {
                        const it = h[k] || {};
                        html += '<div>· ' + esc(k) + ' ' + (it.total || 0) + ' 条' +
                                (it.age != null ? '（' + ago(it.age) + '前）' : '') + '</div>';
                        (it.items || []).slice(0, 4).forEach(x =>
                            html += '<div style="padding-left:10px;color:#99a;">- ' +
                                    esc(x.title) + (x.hot != null ?
                                    ' <span style="color:#666;">' + esc(String(x.hot)) +
                                    '</span>' : '') + '</div>');
                    });
                } else {
                    html += '<div style="color:#666;margin-top:4px;">热榜还没拉到</div>';
                }
                if (d.worldlog) {
                    html += '<div style="margin-top:6px;color:#8fd18f;">🌍 世界日志已存 ' +
                            (d.worldlog.days || 0) + ' 天（上限 ' +
                            (d.worldlog.max_days || 0) + ' 天，' +
                            (d.worldlog.size_kb || 0) + ' KB）</div>';
                }
                const errs = d.errors || [];
                if (errs.length) html += '<div style="color:#e8a13c;margin-top:4px;">⚠️ ' +
                                         esc(errs[errs.length - 1]) + '</div>';
                document.getElementById('feedsPreview').innerHTML = html;
                document.getElementById('feedsMeta').textContent =
                    w ? (w.text + ' ' + w.tmin + '~' + w.tmax + '℃') : '—';
            } catch(e) { console.log('feeds load error', e); }
        }

        function feedsNum(id, def) {
            const v = parseFloat(document.getElementById(id).value);
            return isNaN(v) ? def : v;
        }

        function feedsPayload() {
            const lat = document.getElementById('feeds_lat').value.trim();
            const lon = document.getElementById('feeds_lon').value.trim();
            return {
                enabled: document.getElementById('feeds_enabled').checked,
                news_enabled: document.getElementById('feeds_news_on').checked,
                news_url: document.getElementById('feeds_news_url').value.trim(),
                news_api_key: document.getElementById('feeds_news_key').value.trim(),
                news_count: feedsNum('feeds_news_count', 8),
                news_interval: feedsNum('feeds_news_iv', 1800),
                weather_enabled: document.getElementById('feeds_wx_on').checked,
                weather_provider: document.getElementById('feeds_wx_provider').value,
                city: document.getElementById('feeds_city').value.trim(),
                lat: lat === '' ? '' : feedsNum('feeds_lat', null),
                lon: lon === '' ? '' : feedsNum('feeds_lon', null),
                weather_interval: feedsNum('feeds_wx_iv', 1800),
                hot_enabled: document.getElementById('feeds_hot_on').checked,
                douyin_enabled: document.getElementById('feeds_dy_on').checked,
                douyin_url: document.getElementById('feeds_dy_url').value.trim(),
                xhs_enabled: document.getElementById('feeds_xhs_on').checked,
                xhs_url: document.getElementById('feeds_xhs_url').value.trim(),
                bili_enabled: document.getElementById('feeds_bili_on').checked,
                bili_url: document.getElementById('feeds_bili_url').value.trim(),
                hot_count: feedsNum('feeds_hot_count', 6),
                hot_interval: feedsNum('feeds_hot_iv', 3600),
                hot_api_key: document.getElementById('feeds_hot_key').value.trim(),
            };
        }

        async function saveFeedsConfig() {
            const st = document.getElementById('feedsStatus');
            try {
                const res = await fetch('/api/pixellife/feeds', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(feedsPayload())
                });
                const d = await res.json();
                if (d.error) { st.textContent = '❌ ' + d.error; return; }
                st.textContent = '✅ 已保存，正在按新配置重拉…';
                refreshFeedsNow(true);
            } catch(e) { st.textContent = '❌ ' + e.message; }
        }

        async function refreshFeedsNow(silent) {
            const st = document.getElementById('feedsStatus');
            if (!silent) st.textContent = '⏳ 正在拉取…';
            try {
                const res = await fetch('/api/pixellife/feeds/refresh', {method: 'POST'});
                const d = await res.json();
                if (d.error) { st.textContent = '❌ ' + d.error; return; }
                st.textContent = silent ? '✅ 已保存并刷新' : '✅ 已刷新';
                refreshFeeds();
            } catch(e) { st.textContent = '❌ ' + e.message; }
        }

        // ── PixelLife 和主角说话 ───────────────────────────────────
        function renderChatLog(log, name) {
            const el = document.getElementById('chatLog');
            if (!el) return;
            if (!log || !log.length) {
                el.innerHTML = '<div style="color:#555;">还没聊过。说点什么，他会用自己的性格回你。</div>';
                return;
            }
            el.innerHTML = log.map(m => {
                const mine = m.who === 'you';
                const t = m.ts ? new Date(m.ts * 1000) : null;
                const hh = t ? ('0' + t.getHours()).slice(-2) + ':' +
                              ('0' + t.getMinutes()).slice(-2) : '';
                return '<div style="margin-bottom:8px;' + (mine ? 'text-align:right;' : '') + '">' +
                    '<div style="display:inline-block;max-width:82%;padding:6px 10px;border-radius:10px;' +
                    (mine ? 'background:#2b3a5e;color:#dfe8ff;' : 'background:#232336;color:#e8e8f0;') +
                    '">' + esc(m.text) + '</div>' +
                    '<div style="font-size:10px;color:#555;margin-top:2px;">' +
                    (mine ? '你' : esc(name || '主角')) + ' ' + hh + '</div></div>';
            }).join('');
            el.scrollTop = el.scrollHeight;
        }

        async function refreshHeroChat() {
            try {
                const res = await fetch('/api/pixellife/hero_chat');
                const d = await res.json();
                if (d.error) { document.getElementById('chatStatus').textContent = '❌ ' + d.error; return; }
                document.getElementById('chatMeta').textContent = d.name || '—';
                renderChatLog(d.log, d.name);
            } catch(e) { console.log('hero chat load error', e); }
        }

        async function sendHeroChat() {
            const input = document.getElementById('chatInput');
            const st = document.getElementById('chatStatus');
            const btn = document.getElementById('chatSend');
            const text = (input.value || '').trim();
            if (!text || btn.disabled) return;
            input.value = '';
            btn.disabled = true;
            const old = btn.textContent;
            btn.textContent = '…';
            st.textContent = '⏳ 他在想怎么回你…';
            try {
                const res = await fetch('/api/pixellife/hero_chat', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text})
                });
                const d = await res.json();
                if (d.error) { st.textContent = '❌ ' + d.error; }
                else {
                    st.textContent = '✅ ' + (d.name || '主角') + '回了你' +
                        (d.mood ? '（心情' + (d.mood > 0 ? '+' : '') + d.mood + '）' : '') +
                        '，这句话也进了屏幕播报';
                }
                if (d.log) renderChatLog(d.log, d.name);
            } catch(e) { st.textContent = '❌ ' + e.message; }
            btn.disabled = false;
            btn.textContent = old;
        }

        // ── PixelLife LLM brain ─────────────────────────────────────
        // ── PixelLife 底栏字幕速度 ─────────────────────────────────
        async function refreshSubSpeed() {
            try {
                const res = await fetch('/api/pixellife/display');
                const d = await res.json();
                if (d.error) {
                    document.getElementById('subSpeedStatus').textContent = '❌ ' + d.error;
                    return;
                }
                const el = document.getElementById('sub_speed');
                el.min = d.min_speed; el.max = d.max_speed;
                el.value = d.subtitle_speed;
                subSpeedSlide(d.subtitle_speed);
            } catch(e) { console.log('display load error', e); }
        }

        function subSpeedSlide(v) {
            document.getElementById('sub_speedVal').textContent =
                Number(v).toFixed(1) + '×';
        }

        async function saveSubSpeed() {
            const st = document.getElementById('subSpeedStatus');
            const v = parseFloat(document.getElementById('sub_speed').value);
            st.textContent = '⏳ 保存…';
            try {
                const res = await fetch('/api/pixellife/display', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({subtitle_speed: v})
                });
                const d = await res.json();
                if (d.error) { st.textContent = '❌ ' + d.error; return; }
                st.textContent = '✅ 字幕速度 ' + Number(d.subtitle_speed).toFixed(1) +
                                 '×（立即生效，屏幕下一帧就变）';
            } catch(e) { st.textContent = '❌ ' + e.message; }
        }

        // ── PixelLife 世界日志 ─────────────────────────────────────
        function hotCountText(hot) {
            hot = hot || {};
            const ks = Object.keys(hot);
            if (!ks.length) return '—';
            return ks.map(k => k + ' ' + hot[k]).join(' / ');
        }

        async function refreshWorldLog() {
            try {
                const res = await fetch('/api/pixellife/worldlog?days=40');
                const d = await res.json();
                if (d.error) {
                    document.getElementById('wlStatus').textContent = '❌ ' + d.error;
                    return;
                }
                const c = d.config || {};
                document.getElementById('wl_enabled').checked = !!c.enabled;
                document.getElementById('wl_max_days').value = c.max_days ?? 10000;
                document.getElementById('wl_news_per_day').value = c.news_per_day ?? 30;
                document.getElementById('wl_hot_per_day').value = c.hot_per_day ?? 20;
                document.getElementById('wlMeta').textContent = (d.days || 0) + ' 天';
                let html = '<div style="color:#8fd18f;">📅 已存 <b>' + (d.days || 0) +
                    '</b> 天（上限 ' + (c.max_days ?? 10000) + ' 天）· ' +
                    (d.size_kb || 0) + ' KB</div>';
                if (d.first) {
                    html += '<div style="color:#666;">最早 ' + esc(d.first) +
                            ' · 最新 ' + esc(d.last || '') + '</div>';
                }
                const t = d.today_record;
                if (t) {
                    const w2 = t.weather || {};
                    html += '<div style="margin-top:6px;color:#c9a227;">今天（' +
                            esc(d.today) + '）</div>';
                    if (w2.text) {
                        html += '<div>· 天气 ' + esc(w2.city || '') + ' ' + esc(w2.text) +
                                ' ' + (w2.tmin ?? '?') + '~' + (w2.tmax ?? '?') +
                                '℃ · 湿度' + (w2.humidity ?? '?') + '%</div>';
                    }
                    html += '<div>· 新闻 ' + ((t.news || []).length) +
                            ' 条 · 热榜 ' + hotCountText(t.hot) + '</div>';
                }
                const rows = d.recent || [];
                if (rows.length) {
                    html += '<div style="margin-top:6px;color:#7fc9e8;">最近 ' +
                            rows.length + ' 天</div>';
                    html += rows.map(r => '<div>· ' + esc(r.line || r.date) +
                                          '</div>').join('');
                } else {
                    html += '<div style="color:#666;margin-top:4px;">还没有记录 —— ' +
                            '等外部信息源抓到第一批内容就会出现。</div>';
                }
                const errs = d.errors || [];
                if (errs.length) {
                    html += '<div style="color:#e8a13c;margin-top:4px;">⚠️ ' +
                            esc(errs[errs.length - 1]) + '</div>';
                }
                document.getElementById('wlPreview').innerHTML = html;
            } catch(e) { console.log('worldlog load error', e); }
        }

        async function saveWorldLogConfig() {
            const st = document.getElementById('wlStatus');
            st.textContent = '⏳ 保存…';
            try {
                const res = await fetch('/api/pixellife/worldlog', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        enabled: document.getElementById('wl_enabled').checked,
                        max_days: feedsNum('wl_max_days', 10000),
                        news_per_day: feedsNum('wl_news_per_day', 30),
                        hot_per_day: feedsNum('wl_hot_per_day', 20),
                    })
                });
                const d = await res.json();
                if (d.error) { st.textContent = '❌ ' + d.error; return; }
                st.textContent = '✅ 已保存：上限 ' +
                                 ((d.config || {}).max_days) + ' 天';
                refreshWorldLog();
            } catch(e) { st.textContent = '❌ ' + e.message; }
        }
        async function loadLLMConfig() {
            try {
                const res = await fetch('/api/pixellife/llm');
                const d = await res.json();
                if (d.error) { document.getElementById('llmStatus').textContent = '❌ ' + d.error; return; }
                document.getElementById('llm_url').value = d.url || '';
                document.getElementById('llm_model').value = d.model || '';
                document.getElementById('llm_max_tokens').value = d.max_tokens || 256;
                document.getElementById('llm_ctx').value = d.ctx_tokens || 128000;
                document.getElementById('llm_conc').value = d.concurrency || 4;
                document.getElementById('llm_timeout').value = d.timeout || 25;
                document.getElementById('llm_temp').value = d.temperature ?? 0.85;
                document.getElementById('llm_enabled').checked = !!d.enabled;
                document.getElementById('llm_decide').checked = d.decide !== false;
                document.getElementById('llm_chat').checked = d.chat !== false;
                document.getElementById('llm_thinking').checked = !!d.thinking;
                if (Array.isArray(d.models) && d.models.length) {
                    document.getElementById('llmModelList').innerHTML =
                        d.models.map(m => '<option value="' + m + '">').join('');
                }
                updateLLMDot(d);
                renderTokenUsage(d);
            } catch(e) { console.log('llm config load error', e); }
        }

        function fmtNum(v) {
            v = Math.round(Number(v) || 0);
            const s = String(v);
            let out = '', c = 0;
            for (let i = s.length - 1; i >= 0; i--) {
                out = s.charAt(i) + out;
                c++;
                if (c % 3 === 0 && i > 0) out = ',' + out;
            }
            return out;
        }

        function renderTokenUsage(d) {
            const tot = document.getElementById('tokTotal');
            const cnt = document.getElementById('tokCalls');
            if (!tot || !cnt) return;
            const calls = d.token_calls || 0, total = d.tokens_total || 0;
            tot.textContent = fmtNum(total);
            cnt.textContent = fmtNum(calls);
            const extra = document.getElementById('tokExtra');
            if (!extra) return;
            if (!calls) { extra.textContent = '还没有调用过 LLM'; return; }
            let ts = '';
            if (d.tokens_since) {
                const dt = new Date(d.tokens_since * 1000);
                const p2 = x => ('0' + x).slice(-2);
                ts = ' · 自 ' + (dt.getMonth() + 1) + '/' + dt.getDate() + ' ' +
                     p2(dt.getHours()) + ':' + p2(dt.getMinutes()) + ' 起';
            }
            extra.textContent = '输入 ' + fmtNum(d.tokens_prompt) +
                                ' · 输出 ' + fmtNum(d.tokens_completion) +
                                ' · 平均 ' + fmtNum(Math.round(total / calls)) + ' /次' + ts;
        }

        function updateLLMDot(d) {
            const dot = document.getElementById('llmDot');
            if (!dot) return;
            if (d.enabled && d.healthy) {
                dot.textContent = '● 已连接 ' + (d.last_latency ? d.last_latency + 's' : '');
                dot.style.color = '#4caf50';
            } else if (d.enabled) {
                dot.textContent = d.last_error ? '● ' + d.last_error.slice(0, 40) : '● 未验证';
                dot.style.color = '#e8a13c';
            } else {
                dot.textContent = '● 未启用';
                dot.style.color = '#666';
            }
        }

        function llmPayload() {
            const p = {
                url: document.getElementById('llm_url').value.trim(),
                model: document.getElementById('llm_model').value.trim(),
                max_tokens: parseInt(document.getElementById('llm_max_tokens').value) || 256,
                ctx_tokens: parseInt(document.getElementById('llm_ctx').value) || 128000,
                concurrency: parseInt(document.getElementById('llm_conc').value) || 4,
                timeout: parseInt(document.getElementById('llm_timeout').value) || 25,
                temperature: parseFloat(document.getElementById('llm_temp').value) || 0.85,
                enabled: document.getElementById('llm_enabled').checked,
                decide: document.getElementById('llm_decide').checked,
                chat: document.getElementById('llm_chat').checked,
                thinking: document.getElementById('llm_thinking').checked,
            };
            const key = document.getElementById('llm_key').value.trim();
            if (key) p.api_key = key;
            return p;
        }

        async function saveLLMConfig() {
            const st = document.getElementById('llmStatus');
            try {
                const res = await fetch('/api/pixellife/llm', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(llmPayload())
                });
                const d = await res.json();
                if (d.error) { st.textContent = '❌ ' + d.error; return; }
                st.textContent = '✅ 已保存' + (d.model_hint ? '，模型: ' + d.model_hint.split('/').pop() : '');
                updateLLMDot(d);
                document.getElementById('llm_key').value = '';
            } catch(e) { st.textContent = '❌ 保存失败: ' + e.message; }
        }

        async function testLLM() {
            const st = document.getElementById('llmStatus');
            st.textContent = '⏳ 正在连接…';
            try {
                const res = await fetch('/api/pixellife/llm/test', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(llmPayload())
                });
                const d = await res.json();
                if (d.error && !d.reply) { st.textContent = '❌ ' + d.error; return; }
                if (d.error) st.textContent = '⚠️ 连接成功但测试对话失败: ' + d.error;
                else st.textContent = '✅ 连接正常' + (d.reply ? '，回复: ' + d.reply : '');
                if (Array.isArray(d.models) && d.models.length) {
                    document.getElementById('llmModelList').innerHTML =
                        d.models.map(m => '<option value="' + m + '">').join('');
                    st.textContent += ' | 模型: ' + d.models[0].split('/').pop();
                }
                loadLLMConfig();
            } catch(e) { st.textContent = '❌ 测试失败: ' + e.message; }
        }

        // ─── 像素居民档案 ───────────────────────────────────────────
        function statBar(label, v, color) {
            const pct = Math.max(0, Math.min(100, Number(v) || 0));
            return `<div style="display:flex;align-items:center;gap:4px;font-size:10px;color:#99a;">
                        <span style="width:26px;">${label}</span>
                        <div style="flex:1;height:6px;background:#181822;border-radius:3px;overflow:hidden;">
                            <div style="width:${pct}%;height:100%;background:${color};"></div>
                        </div>
                        <span style="width:20px;text-align:right;color:#ccc;">${Math.round(pct)}</span>
                    </div>`;
        }

        function personCard(p, isHero) {
            const rel = p.relation || {};
            const st = p.stats || {};
            const hobbies = (p.hobbies || []).join('、');
            const badge = isHero
                ? '<span style="background:#3a2a12;color:#fc0;border-radius:4px;padding:1px 6px;font-size:10px;">主角</span>'
                : `<span style="background:#1c2a3a;color:#8cf;border-radius:4px;padding:1px 6px;font-size:10px;">关系 ${rel.rank||'陌生人'} ${Math.round(rel.score||0)}</span>`;
            return `<div style="background:#14141f;border:1px solid #26263a;border-radius:8px;padding:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-size:13px;color:#fff;font-weight:bold;display:flex;align-items:center;gap:7px;">
                        <img src="/api/pixellife/char_icon/${p.key}" alt=""
                             style="width:20px;height:40px;image-rendering:pixelated;flex:none;"
                             onerror="this.style.display='none'">
                        <span>${p.cn || p.key}
                            <span style="font-size:10px;color:#889;font-weight:normal;">${p.job || ''}${p.title ? ' · ' + p.title : ''}</span></span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                        ${badge}
                        <button onclick="openEditor('${isHero ? 'hero' : p.key}')"
                                title="编辑角色"
                                style="background:#223; border:1px solid #448; color:#acf; border-radius:5px;
                                       padding:1px 6px; font-size:11px; cursor:pointer;">✏️</button>
                    </div>
                </div>
                <div style="font-size:10px;color:#889;margin-top:2px;">
                    ${p.gender || ''} ${p.age || ''}岁 · ${p.mbti || ''} · ${p.pace || ''} · ${p.social || ''}
                    ${p.mood ? ' · ' + p.mood : ''}
                </div>
                <div style="margin:5px 0 3px;">
                    ${statBar('健康', st.health, '#e5485f')}
                    ${statBar('心情', st.happiness, '#f4b63c')}
                    ${statBar('精力', st.energy, '#48acec')}
                </div>
                <div style="font-size:10px;color:#aab;line-height:1.5;margin-top:4px;">${p.intro || ''}</div>
                <div style="font-size:10px;color:#667;margin-top:3px;">
                    ${hobbies ? '爱好: ' + hobbies : ''}${rel.met ? ' · 见过' + rel.met + '次' : ''}${rel.gifts ? ' · 收礼' + rel.gifts + '份' : ''}</div>
            </div>`;
        }

        // ─── 角色编辑器 ─────────────────────────────────────────────
        const EDIT_MBTI = ['INTJ','INTP','ENTJ','ENTP','INFJ','INFP','ENFJ','ENFP',
                           'ISTJ','ISFJ','ESTJ','ESFJ','ISTP','ISFP','ESTP','ESFP'];
        const EDIT_PACE = ['早鸟型','夜猫型','工作狂','佛系','张弛有度'];
        const EDIT_SOCIAL = ['社牛','外向','选择性社交','内向','独来独往'];
        const EDIT_CONSUME = ['奢靡主义','实用至上','科技尝鲜','潮流跟风','极简断舍离','吃货本货','收藏癖'];
        const EDIT_STOCK = ['激进追涨','稳健价值','成长赛道','短线博弈','长期持有','指数定投'];
        let SPRITES = null;          // char id list, lazy loaded
        let editKey = null;          // 'hero' or sprite id

        async function loadSprites() {
            if (SPRITES) return;
            try {
                const res = await fetch('/api/pixellife/chars');
                const d = await res.json();
                SPRITES = (d.chars || []).map(c => c.id);
            } catch(e) { SPRITES = []; }
        }

        function sel(id, opts, cur) {
            return `<select id="${id}" style="flex:1;background:#101018;color:#dde;border:1px solid #334;border-radius:5px;padding:3px 5px;font-size:11px;">` +
                opts.map(o => `<option ${o === cur ? 'selected' : ''}>${o}</option>`).join('') + '</select>';
        }

        function fld(label, inner) {
            return `<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
                        <span style="width:44px;flex:none;font-size:11px;color:#889;">${label}</span>${inner}</div>`;
        }

        async function openEditor(key, cardEl) {
            await loadSprites();
            editKey = key;
            // pull fresh values from the live panel API
            let p = null, isHero = (key === 'hero');
            try {
                const res = await fetch('/api/pixellife/people');
                const d = await res.json();
                p = isHero ? (d.hero || {}) :
                    (d.relationships || []).find(r => r.key === key);
            } catch(e) {}
            if (!p) { alert('找不到该角色'); return; }
            const curSprite = isHero ? p.key : key;
            const v = f => (p[f] === undefined || p[f] === null) ? '' : p[f];
            const txt = (id, val, ph) =>
                `<input id="${id}" value="${String(val).replace(/"/g,'&quot;')}" placeholder="${ph || ''}"
                        style="flex:1;background:#101018;color:#dde;border:1px solid #334;border-radius:5px;padding:3px 6px;font-size:11px;">`;
            const grid = SPRITES.map(id =>
                `<div class="spr-opt" data-id="${id}" onclick="pickSprite('${id}')"
                      style="cursor:pointer;border:2px solid ${id === curSprite ? '#fc0' : '#26263a'};
                             border-radius:6px;background:#101018;padding:3px;text-align:center;">
                    <img src="/api/pixellife/char_icon/${id}" style="width:24px;height:48px;image-rendering:pixelated;">
                 </div>`).join('');
            const overlay = document.createElement('div');
            overlay.id = 'editorOverlay';
            overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:99;' +
                'display:flex;align-items:center;justify-content:center;';
            overlay.innerHTML = `<div style="background:#191926;border:1px solid #344;border-radius:12px;
                    padding:14px;width:420px;max-height:88vh;overflow-y:auto;">
                <div style="font-size:14px;color:#fff;font-weight:bold;margin-bottom:10px;">
                    ✏️ 编辑角色 <span style="color:#889;font-weight:normal;font-size:11px;">${isHero ? '主角' : p.cn || key}</span></div>
                ${fld('名字', txt('ed_cn', v('cn') || v('key'), '中文名'))}
                ${fld('性别', sel('ed_gender', ['男','女'], v('gender') || '男'))}
                ${fld('年龄', txt('ed_age', v('age'), '岁'))}
                ${fld('职业', txt('ed_job', v('job'), '如 咖啡师'))}
                ${fld('MBTI', sel('ed_mbti', EDIT_MBTI, v('mbti')))}
                ${fld('节奏', sel('ed_pace', EDIT_PACE, v('pace')))}
                ${fld('社交', sel('ed_social', EDIT_SOCIAL, v('social')))}
                ${fld('消费', sel('ed_consume', EDIT_CONSUME, v('consume')))}
                ${fld('炒股', sel('ed_stock', EDIT_STOCK, v('stock')))}
                ${fld('爱好', txt('ed_hobbies', (p.hobbies || []).join(', '), '逗号分隔, 最多4个'))}
                ${fld('口头禅', txt('ed_catch', v('catch')))}
                ${fld('怪癖', txt('ed_quirk', v('quirk')))}
                <div style="font-size:11px;color:#889;margin:8px 0 4px;">形象（点击选择）</div>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(40px,1fr));gap:5px;">${grid}</div>
                <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
                    <button onclick="closeEditor()" style="background:#223;color:#99a;border:1px solid #445;
                            border-radius:6px;padding:5px 14px;font-size:12px;cursor:pointer;">取消</button>
                    <button onclick="saveEditor()" style="background:#284722;color:#cfc;border:1px solid #4a4;
                            border-radius:6px;padding:5px 14px;font-size:12px;cursor:pointer;">保存</button>
                </div>
                <div id="ed_msg" style="font-size:11px;color:#faa;margin-top:6px;"></div>
            </div>`;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', e => { if (e.target === overlay) closeEditor(); });
        }

        function pickSprite(id) {
            window._pickedSprite = id;
            document.querySelectorAll('.spr-opt').forEach(el => {
                el.style.borderColor = (el.dataset.id === id) ? '#fc0' : '#26263a';
            });
        }

        function closeEditor() {
            window._pickedSprite = null;
            const el = document.getElementById('editorOverlay');
            if (el) el.remove();
        }

        async function saveEditor() {
            const g = id => { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
            const body = {
                key: editKey,
                cn: g('ed_cn'), gender: g('ed_gender'),
                age: g('ed_age'), job: g('ed_job'),
                mbti: g('ed_mbti'), pace: g('ed_pace'), social: g('ed_social'),
                consume: g('ed_consume'), stock: g('ed_stock'),
                hobbies: g('ed_hobbies'), catch: g('ed_catch'), quirk: g('ed_quirk'),
            };
            if (window._pickedSprite) body.sprite = window._pickedSprite;
            try {
                const res = await fetch('/api/pixellife/people/edit', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body)
                });
                const d = await res.json();
                if (d.success) { closeEditor(); refreshPeople(); }
                else document.getElementById('ed_msg').textContent = '❌ ' + (d.message || d.error || '保存失败');
            } catch(e) {
                document.getElementById('ed_msg').textContent = '❌ ' + e.message;
            }
        }

        async function refreshPeople() {
            try {
                const res = await fetch('/api/pixellife/people');
                const d = await res.json();
                if (d.error) { document.getElementById('peopleMeta').textContent = d.error; return; }
                const hero = d.hero || {};
                document.getElementById('peopleMeta').textContent =
                    `${d.relationships.length} 位居民 · 净资产 ${hero.net_worth || 0}`;
                document.getElementById('heroPanel').innerHTML = personCard(hero, true) +
                    `<div style="font-size:10px;color:#778;margin-top:4px;">
                        岗位 ${hero.title || hero.job || ''} · 时薪 ${hero.wage ?? '-'} · 技能 ${hero.skill ?? '-'} ·
                        存款 ${hero.savings ?? 0} · 衣柜 ${(hero.wardrobe || []).length} 件</div>` +
                    brainCard(d);
                document.getElementById('peopleList').innerHTML =
                    (d.relationships || []).map(p => personCard(p, false)).join('');
            } catch(e) {
                document.getElementById('peopleMeta').textContent = '加载失败: ' + e.message;
            }
        }

        // ─── AI 大脑：决策流 / 内心活动 / 变卦 ──────────────────────
        function brainCard(d) {
            const b = d.brain || {};
            const act = d.action || {};
            const pct = act.total ? Math.max(0, Math.min(100, (act.total - act.left) * 100 / act.total)) : 0;
            const m = Math.max(0, Math.round((act.left || 0) / 60));
            const dec = (d.decisions || []).slice(-6).reverse();
            const th  = (d.thoughts || []).slice(-5).reverse();
            const imp = (d.impulses || []).slice(-3).reverse();
            const srcTag = s => s === 'ai'
                ? '<span style="color:#8cf;font-size:9px;">AI</span>'
                : '<span style="color:#889;font-size:9px;">生成</span>';
            const now = Math.max(0, Math.round((b.total || 0)));
            return `<div style="margin-top:8px;background:#111119;border:1px solid #26263a;border-radius:8px;padding:9px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-size:12px;color:#bcd;font-weight:bold;">🧠 AI 大脑</div>
                    <button onclick="pokeDecide()" style="background:#22304a;border:1px solid #4a6fa5;color:#9cf;
                            border-radius:5px;padding:2px 8px;font-size:11px;cursor:pointer;">🔄 重新思考</button>
                </div>
                <div style="font-size:10px;color:#889;margin-top:4px;">
                    当前：<span style="color:#ddd;">${act.label || act.key || '-'}</span>
                    ${act.total ? `（还剩 ${m} 分）` : ''} ·
                    决策 ${now} 次（AI ${b.ai || 0} / 规则 ${b.rule || 0}） ·
                    模型 ok ${b.ok || 0} / fail ${b.fail || 0} · 延迟 ${b.last_latency || 0}s
                    ${b.last_error ? ` · <span style="color:#f99;">${String(b.last_error).slice(0,42)}</span>` : ''}
                </div>
                <div style="height:5px;background:#181822;border-radius:3px;overflow:hidden;margin:5px 0 7px;">
                    <div style="width:${pct}%;height:100%;background:#4a8fd4;"></div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                    <div>
                        <div style="font-size:10px;color:#7a8;margin-bottom:2px;">最近决策</div>
                        ${dec.length ? dec.map(x => `<div style="font-size:10px;color:#99a;line-height:1.45;">
                            <span style="color:#667;">${x.at || ''}</span>
                            <span style="color:#cda;">${(x.action || '')}</span>
                            ${String(x.reason || '').startsWith('AI：') ? '<span style="color:#8cf;font-size:9px;">AI</span>' : ''}
                            ${String(x.reason || '').replace('AI：','').slice(0,20)}</div>`).join('')
                            : '<div style="font-size:10px;color:#556;">暂无</div>'}
                    </div>
                    <div>
                        <div style="font-size:10px;color:#7a8;margin-bottom:2px;">内心活动 ${b.thought_source === 'ai' ? '（模型）' : '（生成器）'}</div>
                        ${th.length ? th.map(x => `<div style="font-size:10px;color:#99a;line-height:1.45;">
                            <span style="color:#667;">${x.at || ''}</span> ${x.text} ${srcTag(x.src)}</div>`).join('')
                            : '<div style="font-size:10px;color:#556;">暂无</div>'}
                        ${imp.length ? `<div style="font-size:10px;color:#7a8;margin:6px 0 2px;">临时变卦</div>` +
                            imp.map(x => `<div style="font-size:10px;color:#a99;line-height:1.45;">
                                <span style="color:#667;">${x.at || ''}</span> ${x.text}</div>`).join('') : ''}
                    </div>
                </div>
            </div>`;
        }

        async function pokeDecide() {
            const meta = document.getElementById('peopleMeta');
            meta.textContent = '⏳ 让小人重新思考…';
            try {
                const res = await fetch('/api/pixellife/decide', {method: 'POST'});
                const d = await res.json();
                if (d.success) { refreshPeople(); }
                else meta.textContent = '❌ ' + (d.error || '失败');
            } catch(e) { meta.textContent = '❌ ' + e.message; }
        }

        async function uploadGif(file) {
            if (!file) return;
            const status = document.getElementById('uploadStatus');
            status.textContent = '⏳ 上传中...';
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/api/upload', {method:'POST', body: formData});
                const data = await resp.json();
                if (data.success) {
                    status.textContent = '✅ 已加载 ' + (data.frames || 1) + ' 帧';
                    await setMode('gif');
                    updatePreview();
                } else {
                    status.textContent = '❌ ' + (data.error || '上传失败');
                }
            } catch(e) {
                status.textContent = '❌ ' + e.message;
            }
        }

        async function uploadGifClock(file) {
            if (!file) return;
            const status = document.getElementById('gifclockUploadStatus');
            status.textContent = '⏳ 上传中...';
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/api/gifclock/gif', {method:'POST', body: formData});
                const data = await resp.json();
                if (data.success) {
                    status.textContent = '✅ 已加载 ' + (data.frames || 1) + ' 帧';
                } else {
                    status.textContent = '❌ ' + (data.error || '上传失败');
                }
            } catch(e) {
                status.textContent = '❌ ' + e.message;
            }
        }

        async function loadGifClockConfig() {
            try {
                const resp = await fetch('/api/gifclock/config');
                const data = await resp.json();
                if (data.success && data.config) {
                    const cfg = data.config;
                    document.getElementById('gc_time_size').value = cfg.time_size || 12;
                    document.getElementById('gc_time_x').value = cfg.time_x || 0;
                    document.getElementById('gc_time_y').value = cfg.time_y || 20;
                    document.getElementById('gc_time_shadow').checked = cfg.time_shadow !== false;
                    document.getElementById('gc_time_color').value = rgbToHex(cfg.time_color || [255,255,255]);
                    document.getElementById('gc_date_show').checked = cfg.date_show !== false;
                    document.getElementById('gc_date_format').value = cfg.date_format || '%Y-%m-%d';
                    document.getElementById('gc_date_size').value = cfg.date_size || 8;
                    document.getElementById('gc_date_color').value = rgbToHex(cfg.date_color || [200,200,200]);
                    document.getElementById('gc_weekday_show').checked = cfg.weekday_show !== false;
                    document.getElementById('gc_weekday_size').value = cfg.weekday_size || 8;
                    document.getElementById('gc_weekday_color').value = rgbToHex(cfg.weekday_color || [150,150,255]);
                }
            } catch(e) { console.error('loadGifClockConfig error:', e); }
        }

        async function saveGifClockConfig() {
            const config = {
                time_size: parseInt(document.getElementById('gc_time_size').value) || 12,
                time_x: parseInt(document.getElementById('gc_time_x').value) || 0,
                time_y: parseInt(document.getElementById('gc_time_y').value) || 20,
                time_shadow: document.getElementById('gc_time_shadow').checked,
                time_color: hexToRgb(document.getElementById('gc_time_color').value),
                date_show: document.getElementById('gc_date_show').checked,
                date_format: document.getElementById('gc_date_format').value || '%Y-%m-%d',
                date_size: parseInt(document.getElementById('gc_date_size').value) || 8,
                date_color: hexToRgb(document.getElementById('gc_date_color').value),
                weekday_show: document.getElementById('gc_weekday_show').checked,
                weekday_size: parseInt(document.getElementById('gc_weekday_size').value) || 8,
                weekday_color: hexToRgb(document.getElementById('gc_weekday_color').value),
            };
            try {
                const resp = await fetch('/api/gifclock/config', {
                    method: 'PUT',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(config)
                });
                const data = await resp.json();
                if (data.success) {
                    alert('✅ 设置已保存');
                }
            } catch(e) { console.error('saveGifClockConfig error:', e); }
        }

        function rgbToHex(rgb) {
            if (typeof rgb === 'string') return rgb;
            return '#' + rgb.map(c => c.toString(16).padStart(2,'0')).join('');
        }

        function hexToRgb(hex) {
            const r = parseInt(hex.slice(1,3), 16);
            const g = parseInt(hex.slice(3,5), 16);
            const b = parseInt(hex.slice(5,7), 16);
            return [r, g, b];
        }

        async function refreshPearl() {
            const el = document.getElementById('pearlStatus');
            if (!el) return;
            try {
                const r = await fetch('/api/pearl-debug');
                const d = await r.json();
                if (d.error) { el.textContent = '⚠️ ' + d.error; return; }
                const m = d.miner || {};
                const bits = [];
                if (m._worker_count != null) bits.push('矿机 ' + m._worker_count + ' 台');
                if (m._total_live_ths != null) bits.push('实时 ' + Number(m._total_live_ths).toFixed(1) + ' TH/s');
                if (m._total_1h_ths != null) bits.push('1h ' + Number(m._total_1h_ths).toFixed(1) + ' TH/s');
                if (m.shares24h != null) bits.push('24h 份额 ' + m.shares24h);
                if (d.price != null) bits.push('币价 $' + d.price);
                let line = bits.length ? '✅ 数据在线：' + bits.join(' · ') : '⚠️ 还没有数据';
                if (d.miner_ts) line += '（' + new Date(d.miner_ts * 1000).toLocaleTimeString() + ' 更新）';
                el.textContent = line;
            } catch(e) { el.textContent = '❌ ' + e.message; }
        }

        // Init
        updateStatus();
        loadStockCodes();
        refreshClients();  // 立即加载一次
        setInterval(updateStatus, 2000);
        setInterval(refreshClients, 5000);  // 每5秒刷新客户端列表
        setInterval(updatePreview, 500);
        // 只在对应主题可见时轮询，避免无谓请求
        setInterval(() => {
            if (document.getElementById('llmCard').style.display !== 'none') loadLLMConfig();
        }, 15000);
        setInterval(() => {
            // feedsCard 现在住在 llmCard 里面，所以看 llmCard 的可见性
            const el = document.getElementById('llmCard');
            if (el && el.style.display !== 'none') {
                refreshFeeds();
                refreshWorldLog();
            }
        }, 30000);
        setInterval(() => {
            if (document.getElementById('peopleCard').style.display !== 'none') refreshPeople();
        }, 10000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return HTML_TEMPLATE


@app.after_request
def _no_store(resp):
    """The panel polls /api/* every couple of seconds -- never let the browser
    or a proxy hand back a stale mode / config (that made the theme panels
    follow the previous theme)."""
    if request.path.startswith('/api/'):
        resp.headers['Cache-Control'] = 'no-store, max-age=0'
    return resp


@app.route('/api/status')
def api_status():
    with led_server.lock:
        client_list = []
        for addr, client in led_server.clients.items():
            client_list.append({
                'addr': f"{addr[0]}:{addr[1]}",
                'info': client['info'],
                'frames': client.get('frame_count', 0),
                'mode': client.get('mode', DEFAULT_MODE),
            })

        return jsonify({
            'mode': led_server.current_mode,
            'brightness': led_server.brightness,
            'fps': led_server.fps,
            'clients': len(led_server.clients),
            'frame_count': led_server.frame_count,
            'client_list': client_list,
            'speed': led_server.animation_speed
        })


@app.route('/api/openclaw-status')
def api_openclaw_status():
    return jsonify(led_server.get_openclaw_status())


@app.route('/api/openclaw-status', methods=['POST'])
def api_openclaw_status_update():
    data = request.json
    led_server.update_openclaw_status(data)
    return jsonify({'success': True})


# Preview 缓存
_preview_cache = {'data': None, 'time': 0}
_PREVIEW_CACHE_TTL = 0.2  # 200ms 缓存


@app.route('/api/preview')
def api_preview():
    import time
    now = time.time()
    # 缓存有效则直接返回
    if _preview_cache['data'] and (now - _preview_cache['time']) < _PREVIEW_CACHE_TTL:
        return send_file(io.BytesIO(_preview_cache['data']), mimetype='image/png')

    frame = led_server._generate_frame()
    img = Image.fromarray(frame)
    img = img.resize((256, 256), Image.NEAREST)

    io_buf = io.BytesIO()
    img.save(io_buf, format='PNG')
    io_buf.seek(0)
    _preview_cache['data'] = io_buf.read()
    _preview_cache['time'] = now
    io_buf.seek(0)
    return send_file(io_buf, mimetype='image/png')


@app.route('/api/clients/mode', methods=['PUT'])
def api_clients_set_mode():
    """批量设置所有客户端的主题"""
    data = request.json
    mode = data.get('mode', DEFAULT_MODE)
    with led_server.lock:
        for client in led_server.clients.values():
            client['mode'] = mode
    return jsonify({'success': True, 'mode': mode, 'clients': len(led_server.clients)})


@app.route('/api/client/<addr>/mode', methods=['PUT'])
def api_client_set_mode(addr):
    """设置指定客户端的主题 addr 格式: ip:port"""
    data = request.json
    mode = data.get('mode', DEFAULT_MODE)

    # 解析 addr 找到对应客户端
    try:
        ip, port_str = addr.rsplit(':', 1)
        port = int(port_str)
        target_addr = (ip, port)
    except:
        return jsonify({'success': False, 'error': 'Invalid addr format'}), 400

    success = led_server.set_client_mode(target_addr, mode)
    if success:
        return jsonify({'success': True, 'addr': addr, 'mode': mode})
    else:
        return jsonify({'success': False, 'error': 'Client not found'}), 404


@app.route('/api/clients', methods=['GET'])
def api_clients():
    """获取所有客户端及其当前主题"""
    with led_server.lock:
        clients = []
        for addr, client in led_server.clients.items():
            clients.append({
                'addr': f"{addr[0]}:{addr[1]}",
                'info': client['info'],
                'frames': client.get('frame_count', 0),
                'mode': client.get('mode', DEFAULT_MODE),
                'connected_at': client.get('connected_at', 0),
            })
    return jsonify({'clients': clients, 'modes': ALL_MODES})


@app.route('/api/mode', methods=['POST'])
def api_mode():
    data = request.json
    mode = data.get('mode', 'openclaw_status')
    text = data.get('text')
    font = data.get('font')
    speed = data.get('speed')
    if text is not None:
        led_server.custom_text = text
    if font in ('hzk12', 'hzk16', 'quan'):
        led_server.text_font = font
    if speed is not None:
        led_server.text_speed = max(10, min(100, int(speed)))
    led_server.set_mode(mode)
    return jsonify({'success': True, 'mode': mode})


@app.route('/api/brightness', methods=['POST'])
def api_brightness():
    data = request.json
    brightness = data.get('brightness', 253)
    led_server.set_brightness(brightness)
    return jsonify({'success': True, 'brightness': brightness})


@app.route('/api/speed', methods=['POST'])
def api_speed():
    data = request.json
    speed = data.get('speed', 1.0)
    led_server.animation_speed = max(0.1, min(3.0, speed))
    return jsonify({'success': True, 'speed': led_server.animation_speed})


@app.route('/api/pixellife')
def api_pixellife():
    """PixelLife 后台：12 维属性、当前行为、决策日志。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        if th is None:
            return jsonify({'error': 'pixellife theme not loaded'}), 503
        data = th.summary()
        st = getattr(th, 'sim', None)
        if st is not None:
            now = datetime.now()
            data['clock'] = {'time': now.strftime('%H:%M'), 'weekday': now.weekday(),
                             'market_open': st.world.market_open(now),
                             'night': st.world.is_night(now)}
            data['rooms'] = st.renderer.a.room_ids()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/rooms')
def api_pixellife_rooms():
    """房间清单，供 APP/网页选择展示。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        if th is None:
            return jsonify({'error': 'not loaded'}), 503
        idx = th.sim.renderer.a.index['rooms']
        return jsonify({k: {'floor': v['floor'], 'wall': v['wall'],
                            'label': v.get('label', k)} for k, v in idx.items()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/llm', methods=['GET', 'POST'])
def api_pixellife_llm():
    """像素小人 LLM 大脑配置：地址/密钥/模型/单次与上下文 token/并发。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        if th is None or getattr(th, 'sim', None) is None:
            return jsonify({'error': 'pixellife not loaded'}), 503
        if request.method == 'POST':
            patch = request.json or {}
            # never let a blank key field wipe a stored one
            if patch.get('api_key') == '':
                patch.pop('api_key', None)
            th.sim.set_llm(patch)
        return jsonify(th.sim.llm_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/llm/test', methods=['POST'])
def api_pixellife_llm_test():
    """Probe the configured endpoint: models list + one tiny chat call."""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        if th is None or getattr(th, 'sim', None) is None:
            return jsonify({'error': 'pixellife not loaded'}), 503
        patch = request.json or {}
        if patch:
            if patch.get('api_key') == '':
                patch.pop('api_key', None)
            th.sim.set_llm(patch)
        return jsonify(th.sim.test_llm())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/memory', methods=['GET', 'POST'])
def api_pixellife_memory():
    """长期记忆：对话记录 / 每日经历 / 愿望清单，以及各项上限设置。

    GET  -> 配置 + 统计（面板用）
    POST -> 改上限（写 pixellife/memory_config.json，立即生效）
    """
    try:
        from pixellife import memory as mem
        if request.method == 'POST':
            mem.update_config(request.json or {})
        return jsonify(mem.stats())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/feeds', methods=['GET', 'POST'])
def api_pixellife_feeds():
    """外部信息源：新闻 + 天气。

    GET  -> 配置 + 当前内容（面板的预览）
    POST -> 改配置（写 pixellife/feeds_config.json，后台线程立刻重拉）
    """
    try:
        from pixellife import feeds as pf
        f = pf.get_feeds()
        if request.method == 'POST':
            f.update(request.json or {})
        return jsonify(f.status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/display', methods=['GET', 'POST'])
def api_pixellife_display():
    """屏幕显示项：底栏字幕速度（v6.17 起可调）。

    GET  -> 当前值 + 合法区间（面板的滑块上下限跟着它走）
    POST -> 改值（写进 world state，下一帧渲染立即生效）
    """
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        if th is None or getattr(th, 'sim', None) is None:
            return jsonify({'error': 'pixellife not loaded'}), 503
        if request.method == 'POST':
            th.sim.set_display(request.json or {})
        return jsonify(th.sim.display_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/worldlog', methods=['GET', 'POST'])
def api_pixellife_worldlog():
    """世界日志：天气 / 新闻 / 每日热榜按天归档（上限默认 10000 天）。

    GET  -> ?days=N 返回最近 N 天的摘要（默认 30）
    POST -> 改归档设置（写 pixellife/worldlog_config.json）
    """
    try:
        from pixellife import worldlog
        log = worldlog.get_log()
        if request.method == 'POST':
            log.update(request.json or {})
        n = request.args.get('days', type=int) or 30
        return jsonify(log.status(n))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/feeds/refresh', methods=['POST'])
def api_pixellife_feeds_refresh():
    """面板的「立即刷新」：同步重拉两个源（各 1-2 秒）。"""
    try:
        from pixellife import feeds as pf
        return jsonify(pf.get_feeds().refresh_now())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/hero_chat', methods=['GET', 'POST'])
def api_pixellife_hero_chat():
    """和主角说话。

    GET  -> 聊天记录（旧 -> 新）
    POST -> 主人发一句 {text}，LLM 以主角的性格回一句，并顺手改心情 /
            记愿望 / 必要时改主意换动作。
    """
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        sim = getattr(th, 'sim', None)
        if sim is None:
            return jsonify({'error': 'pixellife not loaded'}), 503
        from pixellife import herochat
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            return jsonify(herochat.send(sim.world, data.get('text')))
        return jsonify(herochat.view(sim.world))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/people')
def api_pixellife_people():
    """像素居民：主角 + 全体 NPC 的人设、实时属性与关系网。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        if th is None or getattr(th, 'sim', None) is None:
            return jsonify({'error': 'pixellife not loaded'}), 503
        return jsonify(th.sim.people())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/chars')
def api_pixellife_chars():
    """全部可用形象（角色编辑面板的形象选择器）。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        sim = getattr(th, 'sim', None)
        if sim is None:
            return jsonify({'error': 'pixellife not loaded'}), 503
        a = sim.renderer.a
        hero = sim.world.state.get('avatar')
        out = []
        for n in a.char_names():
            tags = a.char_info(n).get('tags', [])
            if 'retired' in tags:
                continue
            out.append({'id': n, 'tags': tags, 'is_hero': n == hero})
        return jsonify({'chars': out})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pixellife/char_icon/<name>')
def api_pixellife_char_icon(name):
    """一个形象的立绘（16x32 原图，前端用 CSS 放大保持像素感）。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        sim = getattr(th, 'sim', None)
        if sim is None:
            return '', 503
        a = sim.renderer.a
        if not a.has_char(name):
            return '', 404
        p = os.path.join(a.dir, 'chars', name, 'idle.png')
        if not os.path.exists(p):
            return '', 404
        resp = send_file(p, mimetype='image/png')
        resp.headers['Cache-Control'] = 'max-age=86400'
        return resp
    except Exception:
        return '', 404


@app.route('/api/pixellife/decide', methods=['POST'])
def api_pixellife_decide():
    """逼小人在此刻重新思考一次（面板上的「重新思考」按钮）。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        sim = getattr(th, 'sim', None)
        if sim is None:
            return jsonify({'success': False, 'error': 'pixellife not loaded'}), 503
        w = sim.world
        w.state["action_left"] = 1.0        # the next tick re-decides
        w.state["last_reconsider"] = 0.0
        now = datetime.now()
        try:
            txt = w.spin_thought(now, force=True)
        except Exception:                   # noqa: BLE001
            txt = None
        # let the sim catch up immediately so the panel sees the new action
        try:
            w.tick(now)
        except Exception:                   # noqa: BLE001
            pass
        w.save()
        return jsonify(dict(success=True, thought=txt,
                            action=w.state.get("action")))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pixellife/people/edit', methods=['POST'])
def api_pixellife_people_edit():
    """编辑主角或 NPC：名字/性格/职业/年龄/形象等。"""
    try:
        th = getattr(led_server, 'pixellife_theme', None)
        sim = getattr(th, 'sim', None)
        if sim is None:
            return jsonify({'success': False, 'error': 'pixellife not loaded'}), 503
        data = request.get_json(silent=True) or {}
        key = data.pop('key', None)
        if not key:
            return jsonify({'success': False, 'error': '缺少 key'}), 400
        from pixellife import people as pxp
        a = sim.renderer.a
        ok, msg = pxp.edit_person(sim.world.state, key, data,
                                  valid_sprites=a.char_names())
        if ok:
            sim.world.save()
        return jsonify({'success': ok, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pearl-data', methods=['GET', 'POST'])
def api_pearl_data():
    """接收来自浏览器的PEARL矿机数据（浏览器提取JS变量后GET/POST到此处）"""
    try:
        if request.method == 'POST':
            data = request.json
        else:
            # GET 方式：数据在 query string 中
            data = {
                '_worker_count': request.args.get('workers', type=int),
                '_total_live_ths': request.args.get('live_ths', type=float),
                '_total_1h_ths': request.args.get('h1_ths', type=float),
                'balance_prl': request.args.get('balance', type=float),
                'total_paid_prl': request.args.get('total_paid', type=float),
                'shares24h': request.args.get('shares', type=int),
                'price': request.args.get('price', type=float),
            }
            # 移除 None 值
            data = {k: v for k, v in data.items() if v is not None}
        
        if data:
            try:
                from themes.pearl import _data_cache as pd
                # 价格单独存储
                if 'price' in data:
                    pd['price'] = data.pop('price')
                    pd['price_ts'] = time.time()
                # miner 数据
                if any(k in data for k in ['_worker_count', '_total_live_ths']):
                    pd['miner'] = data
                    pd['miner_ts'] = time.time()
                    print(f'[PEARL] Updated: workers={data.get("_worker_count")}, live={data.get("_total_live_ths")} TH/s, 1h={data.get("_total_1h_ths")} TH/s, price={pd.get("price")}')
            except Exception as e:
                print(f'[PEARL] cache update error: {e}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/pearl-debug', methods=['GET'])
def api_pearl_debug():
    """调试：查看当前 PEARL 缓存数据"""
    try:
        from themes.pearl import _data_cache as pd
        return jsonify({
            'miner': pd.get('miner'),
            'miner_ts': pd.get('miner_ts'),
            'pool': pd.get('pool') is not None,
            'price': pd.get('price'),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stock', methods=['GET', 'POST'])
def api_stock():
    """获取或设置股票代码列表"""
    from themes.stock import StockTheme
    if request.method == 'POST':
        data = request.json
        codes = data.get('codes', [])
        if codes:
            StockTheme.set_stock_codes(codes)
        return jsonify({'success': True, 'codes': StockTheme.get_stock_codes()})
    else:
        return jsonify({
            'codes': StockTheme.get_stock_codes(),
            'current': StockTheme.get_current_code(),
        })


@app.route('/api/stock/next', methods=['POST'])
def api_stock_next():
    """切换到下一只股票"""
    from themes.stock import StockTheme
    StockTheme.next_stock()
    return jsonify({'current': StockTheme.get_current_code()})



@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传 GIF 或视频文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({'success': False, 'error': 'No filename'})

    filename = uploaded_file.filename.lower()
    suffix = filename.split('.')[-1] if '.' in filename else ''

    import tempfile, os
    fd, tmppath = tempfile.mkstemp(suffix=f'.{suffix}')
    os.close(fd)
    uploaded_file.save(tmppath)

    mode = request.form.get('mode', 'auto')

    try:
        if suffix in ['gif', 'png', 'jpg', 'jpeg', 'bmp']:
            led_server.load_gif(tmppath)
            if led_server.gif_loaded:
                led_server.set_mode('gif')
                return jsonify({'success': True, 'type': 'gif', 'frames': len(led_server.gif_frames)})
            else:
                led_server.set_mode('image')
                return jsonify({'success': True, 'type': 'image'})

        elif suffix in ['mp4', 'avi', 'mov', 'mkv', 'webm']:
            if led_server.load_video(tmppath):
                led_server.set_mode('video')
                return jsonify({'success': True, 'type': 'video', 'frames': len(led_server.video_frames)})
            else:
                return jsonify({'success': False, 'error': 'Video requires ffmpeg'})

        else:
            return jsonify({'success': False, 'error': f'Unsupported format: {suffix}'})
    finally:
        os.unlink(tmppath)


@app.route('/api/gifclock/gif', methods=['POST'])
def api_gifclock_upload():
    """上传GIF作为gifclock背景"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({'success': False, 'error': 'No filename'})

    import tempfile, os, shutil
    suffix = uploaded_file.filename.lower().split('.')[-1]
    fd, tmppath = tempfile.mkstemp(suffix=f'.{suffix}')
    os.close(fd)
    uploaded_file.save(tmppath)

    try:
        # 先复制到持久化路径
        shutil.copy(tmppath, led_server._gifclock_gif_path)
        # 再加载
        if led_server.gifclock_theme and led_server.gifclock_theme.load_gif(led_server._gifclock_gif_path):
            return jsonify({'success': True, 'frames': len(led_server.gifclock_theme._gif_frames)})
        else:
            return jsonify({'success': False, 'error': 'Failed to load GIF - may not be a valid GIF'})
    except Exception as e:
        print(f"GIF upload error: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        os.unlink(tmppath)


@app.route('/api/gifclock/config', methods=['GET'])
def api_gifclock_get_config():
    """获取gifclock配置"""
    if led_server.gifclock_theme is None:
        return jsonify({'success': False, 'error': 'GifClock not available'})
    return jsonify({'success': True, 'config': led_server.gifclock_theme.get_config()})


@app.route('/api/gifclock/config', methods=['PUT'])
def api_gifclock_set_config():
    """设置gifclock配置"""
    if led_server.gifclock_theme is None:
        return jsonify({'success': False, 'error': 'GifClock not available'})

    try:
        config = request.get_json()
        if config:
            led_server.gifclock_theme.set_config(**config)
            # 持久化保存
            with open(led_server._gifclock_config_path, 'w') as f:
                json.dump(config, f)
        return jsonify({'success': True, 'config': led_server.gifclock_theme.get_config()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def main():
    global led_server

    parser = argparse.ArgumentParser(description='LED Matrix Web Server')
    parser.add_argument('--tcp-port', type=int, default=8080, help='TCP port for ESP32')
    parser.add_argument('--web-port', type=int, default=5050, help='Web interface port')
    parser.add_argument('--web-host', default='0.0.0.0', help='Web interface bind host')
    parser.add_argument('--width', type=int, default=64, help='Panel width')
    parser.add_argument('--height', type=int, default=64, help='Panel height')

    args = parser.parse_args()

    global led_server
    led_server = LEDMatrixServer(
        tcp_port=args.tcp_port,
        web_port=args.web_port,
        web_host=args.web_host,
        width=args.width,
        height=args.height
    )

    print(f"""
    ╔══════════════════════════════════════════╗
    ║       LED Matrix Server Started          ║
    ╠══════════════════════════════════════════╣
    ║  Web界面: http://localhost:{args.web_port:<5}       ║
    ║  TCP端口: {args.tcp_port:<5}                      ║
    ║  分辨率:  {args.width}×{args.height:<5}                    ║
    ║  默认模式: OpenClaw Status                ║
    ╚══════════════════════════════════════════╝
    """)

    try:
        led_server.start()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    finally:
        led_server.stop()


if __name__ == '__main__':
    main()
