#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bitcoin Theme - 虚拟货币主题
显示实时比特币价格，LED 矩阵风格
"""

import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime
import time
import threading


class BitcoinTheme:
    """比特币主题 - 64x64 LED 矩阵显示"""

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

        # 调色板 - 比特币橙色系
        self.COLORS = {
            'bg': (5, 5, 15),
            'btc_orange': (240, 160, 0),
            'btc_dark': (200, 120, 0),
            'btc_bright': (255, 200, 50),
            'green': (0, 255, 120),
            'red': (255, 60, 60),
            'white': (255, 255, 255),
            'dim': (100, 100, 120),
            'bar_bg': (20, 20, 35),
        }

        self.anim_frame = 0
        self._btc_price = 0
        self._btc_change = 0
        self._btc_high = 0
        self._btc_low = 0
        self._btc_volume = 0
        self._last_fetch = 0
        self._fetch_error = None
        self._price_history = []
        self._fetch_lock = threading.Lock()

        # 启动后台刷新线程
        self._stop_event = threading.Event()
        self._fetch_thread = threading.Thread(target=self._background_fetch, daemon=True)
        self._fetch_thread.start()

    def _background_fetch(self):
        """后台线程：每3秒刷新一次价格"""
        while not self._stop_event.is_set():
            self._fetch_price_sync()
            # 等待3秒或直到停止
            self._stop_event.wait(3)

    def _fetch_price_sync(self):
        """同步获取比特币价格"""
        with self._fetch_lock:
            try:
                import urllib.request
                import json
                url = 'https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    if data and len(data) > 0:
                        ticker = data[0]
                        self._btc_price = float(ticker['last'])
                        self._btc_change = float(ticker['change_percentage'])
                        self._btc_high = float(ticker['high_24h'])
                        self._btc_low = float(ticker['low_24h'])
                        self._btc_volume = float(ticker['quote_volume'])
                        self._fetch_error = None
                        # 更新历史
                        self._price_history.append(self._btc_price)
                        if len(self._price_history) > 30:
                            self._price_history.pop(0)
            except Exception as e:
                # 网络失败时使用演示数据
                import time
                self._fetch_error = str(e)
                t = time.time()
                # 模拟价格波动
                base_price = 67500.0
                noise = (np.sin(t * 0.5) * 500 + np.sin(t * 1.3) * 200)
                self._btc_price = base_price + noise
                self._btc_change = 2.35 if np.sin(t) > 0 else -1.82
                self._btc_high = self._btc_price * 1.015
                self._btc_low = self._btc_price * 0.985
                self._btc_volume = 28.5e9
                # 更新历史
                self._price_history.append(self._btc_price)
                if len(self._price_history) > 30:
                    self._price_history.pop(0)

    def __del__(self):
        """清理后台线程"""
        self._stop_event.set()

    def generate_frame(self, status: dict = None, t: float = None) -> np.ndarray:
        """
        生成一帧比特币主题画面
        """
        import time
        if t is None:
            t = time.time()
            
        if status is None:
            status = {}

        self.anim_frame += 1

        img = Image.new('RGB', (self.width, self.height), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        # 价格由后台线程自动获取，这里直接使用缓存数据

        # 顶部：BTC 标志 + 闪烁动画
        self._draw_btc_logo(draw, t)

        # 中部：价格显示（带闪烁效果）
        self._draw_price(draw, t)

        # 24h 涨跌显示
        self._draw_change(draw, t)

        # 高/低价
        self._draw_high_low(draw)

        # 迷你走势图
        self._draw_sparkline(draw, t)

        return np.array(img)

    def _draw_btc_logo(self, draw: ImageDraw, t: float):
        """绘制 BTC 标志"""
        # 橙色方块背景
        glow = int((np.sin(t * 3) + 1) / 2 * 50 + 50)
        orange = (
            min(255, self.COLORS['btc_orange'][0] + glow // 3),
            min(255, self.COLORS['btc_orange'][1] + glow // 3),
            min(255, self.COLORS['btc_orange'][2])
        )
        
        # 绘制简化的 BTC 符号
        cx, cy = 32, 12
        # 圆形背景
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=orange)
        
        # B 字符（简化的）
        draw.rectangle([cx - 3, cy - 5, cx + 4, cy + 5], fill=(20, 20, 35))
        # 竖线
        draw.rectangle([cx - 3, cy - 5, cx - 1, cy + 5], fill=orange)
        draw.rectangle([cx + 2, cy - 5, cx + 4, cy + 5], fill=orange)

    def _draw_price(self, draw: ImageDraw, t: float):
        """绘制价格"""
        if self._btc_price <= 0:
            price_str = "--------"
            color = self.COLORS['dim']
        else:
            price_str = f"{self._btc_price:,.0f}"
            # 价格变化闪烁
            if len(self._price_history) >= 2:
                if self._btc_price > self._price_history[-2]:
                    color = self.COLORS['red']   # 红涨
                elif self._btc_price < self._price_history[-2]:
                    color = self.COLORS['green'] # 绿跌
                else:
                    color = self.COLORS['btc_bright']
            else:
                color = self.COLORS['btc_bright']

        # 价格数字 - 大号显示
        y = 22
        x = 2
        
        # $ 符号
        self._draw_text_3x5(draw, x, y, "$", self.COLORS['dim'])
        x += 5

        # 数字（每3位一组）
        digits = price_str.replace(",", "")
        for i, ch in enumerate(digits):
            if ch.isdigit():
                self._draw_text_3x5(draw, x, y, ch, color)
            elif ch == '.':
                draw.rectangle([x + 1, y + 2, x + 1, y + 2], fill=color)
            x += 4
            if (len(digits) - i) % 3 == 0 and i < len(digits) - 1 and ch != '.':
                pass  # 逗号可以省略

    def _draw_change(self, draw: ImageDraw, t: float):
        """绘制 24h 涨跌（三角箭头 + 涨跌幅）"""
        y = 32

        if self._btc_change == 0:
            change_str = "--"
            color = self.COLORS['dim']
            triangle_color = self.COLORS['dim']
        elif self._btc_change > 0:
            change_str = f"+{self._btc_change:.2f}%"
            color = self.COLORS['red']     # 红涨
            triangle_color = self.COLORS['red']
        else:
            change_str = f"{self._btc_change:.2f}%"
            color = self.COLORS['green']   # 绿跌
            triangle_color = self.COLORS['green']

        # 绘制三角箭头
        x = 2
        if abs(self._btc_change) > 0:
            if self._btc_change > 0:
                # 上涨红色三角朝上
                draw.polygon([(x + 4, y), (x, y + 8), (x + 8, y + 8)], fill=triangle_color)
            else:
                # 下跌绿色三角朝下
                draw.polygon([(x, y), (x + 8, y), (x + 4, y + 8)], fill=triangle_color)
        x += 8 + 4  # 三角形宽度 + 4像素间距

        # 百分比数字
        for ch in change_str:
            if ch.isdigit() or ch == '.' or ch == '-':
                self._draw_text_3x5(draw, x, y + 3, ch, color)
                x += 4
            elif ch == '+':
                self._draw_text_3x5(draw, x, y + 3, "+", color)
                x += 4

    def _draw_high_low(self, draw: ImageDraw):
        """绘制高/低价"""
        y = 42
        
        if self._btc_high > 0:
            high_str = f"H:{self._btc_high:,.0f}"
            low_str = f"L:{self._btc_low:,.0f}"
            
            # High
            x = 2
            self._draw_text_3x5(draw, x, y, "H", self.COLORS['dim'])
            x += 4
            for ch in f"{self._btc_high:,.0f}"[:6]:
                if ch.isdigit():
                    self._draw_text_3x5(draw, x, y, ch, self.COLORS['btc_orange'])
                    x += 4
            
            # Low
            x = 34
            self._draw_text_3x5(draw, x, y, "L", self.COLORS['dim'])
            x += 4
            for ch in f"{self._btc_low:,.0f}"[:6]:
                if ch.isdigit():
                    self._draw_text_3x5(draw, x, y, ch, self.COLORS['dim'])
                    x += 4
        else:
            self._draw_text_3x5(draw, 2, y, "H:------", self.COLORS['dim'])
            self._draw_text_3x5(draw, 34, y, "L:------", self.COLORS['dim'])

    def _draw_sparkline(self, draw: ImageDraw, t: float):
        """绘制迷你走势图"""
        if len(self._price_history) < 2:
            return

        y_base = 54
        min_p = min(self._price_history)
        max_p = max(self._price_history)
        range_p = max_p - min_p if max_p > min_p else 1

        points = []
        for i, p in enumerate(self._price_history[-20:]):
            x = int((i / 19) * 60) + 2
            y = y_base + int(((max_p - p) / range_p) * 8)
            points.append((x, y))

        if len(points) >= 2:
            # 颜色根据涨跌
            if self._price_history[-1] >= self._price_history[0]:
                line_color = self.COLORS['red']   # 红涨
            else:
                line_color = self.COLORS['green'] # 绿跌
            
            draw.line(points, fill=line_color, width=1)

    def _draw_message_bar(self, draw: ImageDraw, t: float, status: dict):
        """绘制底部滚动消息"""
        msg_y = 56

        # 分隔线
        draw.line([(0, msg_y - 2), (63, msg_y - 2)], fill=(50, 50, 80), width=1)

        # 构建消息
        segments = []
        
        if self._btc_price > 0:
            # 音量信息
            vol = self._btc_volume
            if vol >= 1e9:
                vol_str = f"VOL ${vol/1e9:.1f}B"
            elif vol >= 1e6:
                vol_str = f"VOL ${vol/1e6:.1f}M"
            else:
                vol_str = f"VOL ${vol/1e3:.1f}K"
            
            for ch in vol_str:
                segments.append((ch, self.COLORS['dim']))

        last_msg = status.get('last_message', '') or ""
        if last_msg:
            if segments:
                segments.append((' ', self.COLORS['dim']))
            for ch in last_msg:
                segments.append((ch, self.COLORS['white']))

        if not segments:
            segments = [('B', self.COLORS['btc_orange']), ('T', self.COLORS['btc_orange']), ('C', self.COLORS['btc_orange']), 
                       (' ', self.COLORS['dim']), ('L', self.COLORS['dim']), ('I', self.COLORS['dim']), ('V', self.COLORS['dim']), ('E', self.COLORS['dim'])]

        # 计算滚动位置
        def char_width(ch):
            return 12 if ord(ch) > 127 else 8
        total_width = sum(char_width(ch) + 6 for ch, _ in segments)
        stride = 14
        scroll_pos = int(t * 8) % (total_width + 64)
        x = 64 - scroll_pos

        for char, color in segments:
            w = char_width(char)
            if x < -w or x > 64:
                x += stride
                continue
            if ord(char) > 127:
                self._draw_hzk12_char(draw, x, msg_y, char, color)
            else:
                self._draw_text_12(draw, x, msg_y, char, color)
            x += stride

    def _draw_text_3x5(self, draw: ImageDraw, x: int, y: int, text: str, color: tuple):
        """绘制 3x5 像素风格的文字"""
        font_3x5 = {
            'M': [[1,0,1],[1,1,1],[1,0,1],[1,0,1],[1,0,1]],
            'E': [[1,1,1],[1,0,1],[1,1,0],[1,0,1],[1,1,1]],
            'C': [[1,1,1],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],
            'P': [[1,1,0],[1,0,1],[1,1,0],[1,0,0],[1,0,0]],
            'U': [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],
            'B': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,1,0]],
            'I': [[0,1,0],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],
            'D': [[1,1,0],[1,0,1],[1,0,1],[1,0,1],[1,1,0]],
            'L': [[1,0,0],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],
            'S': [[1,1,1],[1,0,0],[1,1,1],[0,0,1],[1,1,1]],
            'Y': [[1,0,1],[1,0,1],[0,1,0],[0,1,0],[0,1,0]],
            'A': [[0,1,0],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],
            'T': [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],
            'W': [[1,0,1],[1,0,1],[1,0,1],[1,1,1],[0,1,0]],
            'N': [[1,0,1],[1,1,1],[1,1,1],[1,0,1],[1,0,1]],
            'O': [[1,1,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],
            'H': [[1,0,1],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],
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
            'F': [[1,1,1],[1,0,0],[1,1,0],[1,0,0],[1,0,0]],
            'R': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,0,1]],
            'K': [[1,0,1],[1,1,0],[1,0,0],[1,1,0],[1,0,1]],
            ':': [[0,0,0],[0,1,0],[0,0,0],[0,1,0],[0,0,0]],
            '.': [[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,1,0]],
            '-': [[0,0,0],[0,0,0],[1,1,1],[0,0,0],[0,0,0]],
            '+': [[0,1,0],[0,1,0],[1,1,1],[0,1,0],[0,1,0]],
            '$': [[0,1,0],[1,1,1],[0,1,0],[0,1,0],[1,1,1]],
            'V': [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[0,1,0]],
            'G': [[1,1,1],[1,0,0],[1,0,1],[1,0,1],[1,1,1]],
        }

        cx = x
        for char in text.upper():
            if char in font_3x5:
                bitmap = font_3x5[char]
                for row in range(5):
                    for col in range(3):
                        if bitmap[row][col]:
                            draw.rectangle([cx + col, y + row, cx + col, y + row], fill=color)
            cx += 4

    def _draw_text_12(self, draw: ImageDraw, x: int, y: int, char: str, color: tuple):
        """绘制 12像素高的ASCII字符"""
        font_12 = {
            '0': [0x38,0x44,0xc4,0xc6,0x86,0x96,0x96,0x86,0xc6,0xc4,0x44,0x38],
            '1': [0x70,0xb0,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0xfc],
            '2': [0x78,0xc4,0x06,0x06,0x06,0x04,0x0c,0x18,0x30,0x60,0xc0,0xfe],
            '3': [0x78,0x84,0x06,0x06,0x04,0x38,0x0c,0x06,0x02,0x06,0x8c,0xf8],
            '4': [0x0c,0x0c,0x14,0x14,0x24,0x64,0x44,0x84,0xff,0x04,0x04,0x04],
            '5': [0x7c,0x40,0x40,0x40,0x78,0x04,0x06,0x02,0x02,0x06,0x8c,0xf8],
            '6': [0x3c,0x60,0x40,0x80,0xb8,0xc4,0xc6,0xc2,0xc2,0xc6,0x44,0x38],
            '7': [0xfe,0x06,0x04,0x04,0x0c,0x08,0x18,0x10,0x10,0x30,0x20,0x20],
            '8': [0x38,0x44,0xc6,0xc6,0x44,0x38,0x44,0x86,0x82,0x86,0xc4,0x38],
            '9': [0x38,0x44,0xc6,0x86,0x86,0xc6,0x46,0x3a,0x02,0x04,0x0c,0x78],
            'A': [0x18,0x18,0x18,0x24,0x24,0x24,0x66,0x7e,0x7e,0x42,0xc3,0x81],
            'B': [0xf8,0x84,0x86,0x86,0x84,0xf8,0x84,0x86,0x82,0x86,0x86,0xf8],
            'C': [0x1c,0x62,0x40,0xc0,0xc0,0x80,0x80,0xc0,0xc0,0x40,0x62,0x1c],
            'D': [0xf0,0x8c,0x84,0x86,0x86,0x86,0x86,0x86,0x86,0x84,0x8c,0xf0],
            'E': [0xfe,0x80,0x80,0x80,0x80,0xfe,0x80,0x80,0x80,0x80,0x80,0xfe],
            'F': [0xfc,0x80,0x80,0x80,0x80,0xfc,0x80,0x80,0x80,0x80,0x80,0x80],
            'G': [0x1c,0x62,0x40,0xc0,0x80,0x80,0x8e,0x82,0xc2,0x42,0x62,0x1c],
            'H': [0x82,0x82,0x82,0x82,0x82,0xfe,0x82,0x82,0x82,0x82,0x82,0x82],
            'I': [0xfc,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0xfc],
            'J': [0x3c,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x8c,0x78],
            'K': [0x82,0x84,0x8c,0x98,0xb0,0xf0,0xd0,0x88,0x8c,0x84,0x86,0x83],
            'L': [0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0xfe],
            'M': [0xc3,0xc3,0xa5,0xa5,0xa5,0x99,0x99,0x99,0x81,0x81,0x81,0x81],
            'N': [0xc2,0xc2,0xa2,0xa2,0xa2,0x92,0x92,0x9a,0x8a,0x8a,0x86,0x86],
            'O': [0x38,0x44,0xc6,0x82,0x82,0x82,0x82,0x82,0x82,0xc6,0x44,0x38],
            'P': [0xf8,0x86,0x86,0x82,0x86,0x86,0xfc,0x80,0x80,0x80,0x80,0x80],
            'Q': [0x30,0x48,0x84,0x84,0x84,0x84,0x84,0x84,0xcc,0x78,0x18,0x08],
            'R': [0xf8,0x8c,0x86,0x86,0x86,0x84,0xf8,0x8c,0x84,0x86,0x82,0x83],
            'S': [0x3c,0x44,0x80,0x80,0xc0,0x78,0x1c,0x06,0x02,0x02,0x86,0x78],
            'T': [0xff,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18],
            'U': [0x82,0x82,0x82,0x82,0x82,0x82,0x82,0x82,0x82,0xc2,0x44,0x38],
            'V': [0xc1,0xc3,0x42,0x42,0x42,0x66,0x24,0x24,0x24,0x3c,0x18,0x18],
            'W': [0x81,0x81,0x83,0x9a,0x5a,0x5a,0x5a,0x4a,0x62,0x66,0x66,0x64],
            'X': [0x42,0x42,0x24,0x24,0x18,0x18,0x18,0x3c,0x24,0x46,0x42,0x83],
            'Y': [0xc3,0x42,0x66,0x24,0x24,0x18,0x18,0x18,0x18,0x18,0x18,0x18],
            'Z': [0xfe,0x06,0x04,0x0c,0x18,0x10,0x30,0x20,0x60,0x40,0x80,0xfe],
            '$': [0x20,0x20,0xa0,0xa0,0xa0,0x70,0x28,0x28,0x28,0xf0,0x20,0x20],
            ':': [0x00,0x00,0x00,0x00,0x00,0x30,0x30,0x00,0x00,0x00,0x30,0x30],
            '.': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x30,0x30],
            '+': [0x18,0x18,0x18,0x18,0x18,0xff,0xff,0x18,0x18,0x18,0x18,0x18],
            '-': [0xff,0xff,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff],
            '/': [0x04,0x08,0x08,0x18,0x10,0x10,0x20,0x20,0x40,0x40,0xc0,0x80],
            '=': [0xff,0xff,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff,0x00],
            '!': [0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x00,0x00,0x80,0x80],
            ' ': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
            '▲': [0x18,0x3c,0x7e,0xdb,0xff,0x18,0x18,0x18,0x18,0x18,0x18,0x18],
            '▼': [0x18,0x18,0x18,0x18,0x18,0x18,0x18,0xff,0x7e,0x3c,0x18,0x00],
        }

        if char not in font_12:
            return

        bitmap = font_12[char]
        for row in range(12):
            bits = bitmap[row]
            for col in range(8):
                if bits & (0x80 >> col):
                    draw.rectangle([x + col, y + row, x + col, y + row], fill=color)

    def _draw_hzk12_char(self, draw, x, y, char, color):
        """绘制 HZK12 中文字符"""
        try:
            if not hasattr(self, 'hzk12_data'):
                with open('/home/jem/Intrix_Seed/HZK12', 'rb') as f:
                    self.hzk12_data = f.read()

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


# 独立测试
if __name__ == '__main__':
    import time
    theme = BitcoinTheme()
    
    print("🪙 测试 Bitcoin Theme...")
    print("生成 10 帧测试图像到 /home/jem/Intrix_Seed/themes/test_frames/")

    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)

    # 模拟价格数据
    theme._btc_price = 67432.50
    theme._btc_change = 2.35
    theme._btc_high = 68000.00
    theme._btc_low = 65000.00
    theme._btc_volume = 28500000000
    theme._price_history = [66000, 66500, 67000, 66800, 67200, 67432]

    for i in range(10):
        frame = theme.generate_frame({}, t=time.time() + i * 0.1)
        
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/btc_frame_{i:02d}.png')
        print(f"  帧 {i:02d} 已保存")

    print("✅ 测试完成！")
