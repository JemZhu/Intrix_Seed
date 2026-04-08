#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32-S3 HUB75 LED Matrix Server with OpenClaw Status Display
带有OpenClaw状态显示的LED灯板服务端 - 精美像素风格
"""

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
    sys.path.insert(0, '/home/jem/Intrix_Seed')
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
    from themes.theme_manager import ThemeManager
    HAS_THEMES = True
except ImportError as e:
    HAS_THEMES = False
    print(f"⚠️  主题模块加载失败: {e}")

app = Flask(__name__)


class LEDMatrixServer:
    def __init__(self, tcp_host='0.0.0.0', tcp_port=8080, web_port=5000, width=64, height=64):
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.web_port = web_port
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
        app.run(host='0.0.0.0', port=self.web_port, debug=False, use_reloader=False)

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

            with self.lock:
                self.clients[addr] = {
                    'socket': client_sock,
                    'info': client_info,
                    'connected_at': time.time(),
                    'frame_count': 0
                }

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
        """广播图像数据"""
        render_interval = 0.050  # ~20fps 渲染
        last_render = 0
        cached_frame = None

        while self.running:
            if self.clients:
                try:
                    now = time.time()

                    # 每 render_interval 秒才重新生成一帧并发送
                    render_interval = 0.067 / max(0.5, self.animation_speed)
                    if now - last_render >= render_interval:
                        cached_frame = self._generate_frame()
                        self.preview_image = cached_frame.copy()
                        last_render = now
                        self._send_frame_to_all(cached_frame)

                        with self.lock:
                            self.frame_count += 1
                            self._fps_frames += 1
                            # 滑动窗口计算 FPS（最近1秒）
                            if now - self._fps_window_start >= self._fps_window_seconds:
                                self.fps = self._fps_frames / (now - self._fps_window_start)
                                self._fps_frames = 0
                                self._fps_window_start = now

                except Exception as e:
                    print(f"❌ Broadcast error: {e}")

                time.sleep(0.001 / self.animation_speed)
            else:
                # 没有客户端时降低帧率，避免空转耗电
                time.sleep(0.5)
                cached_frame = None
                last_render = 0

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
            font = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 8)
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
            font = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 10)
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
        hzk_path = '/home/jem/Intrix_Seed/HZK12'
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
        hzk_path = '/home/jem/Intrix_Seed/HZK16'
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
                with open('/home/jem/Intrix_Seed/HZK12', 'rb') as f:
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
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 5)
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
        """发送帧到所有客户端"""
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
                if addr in self.clients:
                    try:
                        self.clients[addr]['socket'].close()
                    except:
                        pass
                    del self.clients[addr]

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

    def set_brightness(self, brightness: int):
        self.brightness = max(0, min(253, brightness))  # 254/255 跳过，ESP32 库有 bug
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

        <div class="grid">
            <div class="card">
                <h2>🎭 主题</h2>
                <div class="mode-grid">
                    <button class="mode-btn" onclick="setMode('openclaw_status')">
                        <div class="icon">🖥️</div><div>状态</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('demo')">
                        <div class="icon">🎨</div><div>演示</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('rainbow')">
                        <div class="icon">🌈</div><div>彩虹</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('text')">
                        <div class="icon">📝</div><div>文字</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('clock')">
                        <div class="icon">🕐</div><div>时钟</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('matrix')">
                        <div class="icon">💻</div><div>代码雨</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('kitten')">
                        <div class="icon">😺</div><div>小猫</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('vocab')">
                        <div class="icon">📚</div><div>单词</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('calendar')">
                        <div class="icon">📅</div><div>日历</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('bitcoin')">
                        <div class="icon">₿</div><div>比特币</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('fortune')">
                        <div class="icon">☘</div><div>运势</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('stock')">
                        <div class="icon">📈</div><div>A股</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('gif')">
                        <div class="icon">🖼️</div><div>GIF</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('fireworks')">
                        <div class="icon">🎆</div><div>烟花</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('lava')">
                        <div class="icon">🔥</div><div>熔岩灯</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('snow')">
                        <div class="icon">❄️</div><div>雪花</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('plasma')">
                        <div class="icon">🌊</div><div>波浪</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('warp')">
                        <div class="icon">🌌</div><div>星空</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('aurora')">
                        <div class="icon">🌈</div><div>极光</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('ripple')">
                        <div class="icon">💧</div><div>水波</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('cube')">
                        <div class="icon">📦</div><div>方块</div>
                    </button>
                    <button class="mode-btn" onclick="setMode('bounce')">
                        <div class="icon">🏀</div><div>弹球</div>
                    </button>
                </div>
            </div>

            <div class="card">
                <h2>⚙️ 控制</h2>
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
                <div class="control-row">
                    <label>文字</label>
                    <input type="text" class="text-input" id="customText" placeholder="输入滚动文字..." style="flex:1;">
                    <button class="btn" onclick="sendText()">发送</button>
                </div>
                <div class="control-row">
                    <label>字体</label>
                    <select id="textFont" style="background:#1a1a2e;border:1px solid #333;color:#fff;padding:4px;border-radius:4px;flex:1;">
                        <option value="quan">quan.ttf</option>
                        <option value="hzk12">HZK12</option>
                        <option value="hzk16">HZK16</option>
                    </select>
                </div>
                <div class="upload-zone" id="uploadZone" style="margin-top:8px;border:2px dashed #333;border-radius:8px;padding:12px;text-align:center;cursor:pointer;" onclick="document.getElementById('gifFile').click()">
                    <input type="file" id="gifFile" accept="image/gif,.gif" style="display:none" onchange="uploadGif(this.files[0])">
                    <div style="color:#888;font-size:13px;">📁 点击上传 GIF 文件</div>
                    <div id="uploadStatus" style="margin-top:6px;font-size:12px;color:#aaa;"></div>
                </div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>📺 预览</h2>
                <div class="preview-box">
                    <img id="previewImg" src="/api/preview" alt="Preview">
                </div>
            </div>

            <div class="card stock-config" id="stockCard">
                <h2>📈 A股设置</h2>
                <div style="margin-top:8px;">
                    <div style="font-size:12px;color:#aaa;margin-bottom:4px;">股票代码（每行一个，6位数字）</div>
                    <div style="font-size:11px;color:#666;margin-bottom:6px;">沪市以6开头，深市以0/3开头</div>
                    <textarea id="stockCodes" rows="4" placeholder="600036&#10;000858&#10;601318" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;font-family:monospace;font-size:12px;padding:6px;border-radius:4px;resize:vertical;box-sizing:border-box;"></textarea>
                    <div style="margin-top:8px;display:flex;gap:8px;align-items:center;">
                        <button class="btn-primary" onclick="saveStockCodes()" style="flex:1;">💾 保存</button>
                        <button class="btn" onclick="switchStock()" style="flex:1;background:#2a2a4a;">⏭ 切换</button>
                    </div>
                    <div id="stockStatus" style="margin-top:6px;font-size:11px;color:#aaa;"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
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
                // Update active button
                document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.mode-btn').forEach(btn => {
                    if (btn.onclick.toString().includes(data.mode)) btn.classList.add('active');
                });
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

        // Init
        updateStatus();
        loadStockCodes();
        setInterval(updateStatus, 2000);
        setInterval(updatePreview, 500);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return HTML_TEMPLATE


@app.route('/api/status')
def api_status():
    with led_server.lock:
        client_list = []
        for addr, client in led_server.clients.items():
            client_list.append({
                'addr': f"{addr[0]}:{addr[1]}",
                'info': client['info'],
                'frames': client.get('frame_count', 0)
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

def main():
    global led_server

    parser = argparse.ArgumentParser(description='LED Matrix Web Server')
    parser.add_argument('--tcp-port', type=int, default=8080, help='TCP port for ESP32')
    parser.add_argument('--web-port', type=int, default=5000, help='Web interface port')
    parser.add_argument('--width', type=int, default=64, help='Panel width')
    parser.add_argument('--height', type=int, default=64, help='Panel height')

    args = parser.parse_args()

    global led_server
    led_server = LEDMatrixServer(
        tcp_port=args.tcp_port,
        web_port=args.web_port,
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
