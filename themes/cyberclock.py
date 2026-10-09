#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CyberClock Theme - 赛博朋克风格时钟主题
霓虹灯光效果 + 网格背景 + 故障艺术时钟
"""
# --- deploy: resolve project assets relative to this file (macOS-safe) ---
import os as _os
import os
BASE_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime


class CyberClockTheme:
    """赛博朋克时钟主题 - 64x64 LED 矩阵"""

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

        # 赛博朋克调色板
        self.COLORS = {
            'bg': (5, 5, 15),
            'bg_grid': (15, 15, 35),
            'neon_cyan': (0, 255, 255),
            'neon_pink': (255, 0, 170),
            'neon_yellow': (255, 255, 0),
            'neon_green': (0, 255, 120),
            'neon_red': (255, 50, 50),
            'neon_orange': (255, 150, 0),
            'dim_cyan': (0, 150, 180),
            'glitch_red': (255, 0, 50),
            'glitch_blue': (0, 100, 255),
            'white': (255, 255, 255),
            'scanline': (0, 0, 0, 80),
        }

        self._glitch_offset = 0
        self._pulse_phase = 0

    def generate_frame(self, status: dict = None, t: float = None) -> np.ndarray:
        """生成赛博朋克时钟帧"""
        import time
        if t is None:
            t = time.time()
            
        if status is None:
            status = {
                'is_busy': False,
                'memory_usage': 0.5,
                'cpu_load': 0.3,
                'last_message': '',
            }

        self._glitch_offset = int(2 * np.sin(t * 15)) if int(t * 8) % 6 == 0 else 0
        self._pulse_phase = (t * 2) % (2 * np.pi)

        img = Image.new('RGB', (self.width, self.height), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        # 背景网格
        self._draw_grid(draw, t)

        # 扫描线效果
        self._draw_scanlines(draw)

        # 主时钟区域
        self._draw_main_clock(draw, t)

        # 日期显示
        self._draw_date(draw, t)

        # 底部状态栏
        self._draw_status_bar(draw, status, t)

        # 装饰元素
        self._draw_decorations(draw, t)

        # 故障效果
        if int(t * 5) % 7 == 0:
            self._draw_glitch(draw, t)

        return np.array(img)

    def _draw_grid(self, draw: ImageDraw, t: float):
        """绘制背景网格"""
        # 垂直线
        pulse = int(50 + 30 * np.sin(self._pulse_phase))
        for x in range(0, 64, 8):
            alpha = pulse if x in [16, 32, 48] else 20
            draw.line([(x, 0), (x, 64)], fill=(15, 15, alpha), width=1)

        # 水平线
        for y in range(0, 64, 8):
            alpha = pulse if y in [24, 40] else 20
            draw.line([(0, y), (64, y)], fill=(15, 15, alpha), width=1)

        # 边缘霓虹边框
        glow_intensity = int(100 + 100 * np.sin(self._pulse_phase * 2))
        draw.rectangle([0, 0, 63, 63], outline=(0, glow_intensity // 3, glow_intensity), width=1)

    def _draw_scanlines(self, draw: ImageDraw):
        """绘制扫描线"""
        for y in range(0, 64, 2):
            draw.line([(0, y), (63, y)], fill=(0, 0, 0, 40), width=1)

    def _draw_main_clock(self, draw: ImageDraw, t: float):
        """绘制主时钟 - HH:MM:SS 大字体"""
        now = datetime.now()
        hours = f"{now.hour:02d}"
        minutes = f"{now.minute:02d}"
        seconds = f"{now.second:02d}"

        # 脉冲效果
        pulse = int(255 * (0.7 + 0.3 * np.sin(self._pulse_phase * 3)))

        # 故障偏移
        glitch = self._glitch_offset

        # 时钟颜色 - 粉/青渐变
        base_color = self.COLORS['neon_pink'] if int(t * 2) % 2 == 0 else self.COLORS['neon_cyan']

        # 时分秒分三行显示
        y_h = 8
        y_m = 22
        y_s = 36

        # 时
        self._draw_digit_8x12(draw, 4 + glitch, y_h, hours[0], base_color)
        self._draw_digit_8x12(draw, 14 + glitch, y_h, hours[1], base_color)

        # 分
        self._draw_digit_8x12(draw, 26, y_m, minutes[0], self.COLORS['neon_cyan'])
        self._draw_digit_8x12(draw, 36, y_m, minutes[1], self.COLORS['neon_cyan'])

        # 秒 (带闪烁)
        sec_color = tuple(min(255, c + pulse // 4) for c in self.COLORS['neon_yellow'])
        self._draw_digit_8x12(draw, 48, y_s, seconds[0], sec_color)
        self._draw_digit_8x12(draw, 58, y_s, seconds[1], sec_color)

        # 分隔符
        blink = int(t * 4) % 2 == 0
        if blink:
            draw.rectangle([23, y_h + 2, 24, y_h + 4], fill=self.COLORS['neon_pink'])
            draw.rectangle([23, y_m + 2, 24, y_m + 4], fill=self.COLORS['neon_pink'])
            draw.rectangle([45, y_m + 2, 46, y_m + 4], fill=self.COLORS['neon_cyan'])
            draw.rectangle([45, y_s + 2, 46, y_s + 4], fill=self.COLORS['neon_yellow'])

    def _draw_digit_8x12(self, draw: ImageDraw, x: int, y: int, digit: str, color: tuple):
        """绘制 8x12 像素风格的数字"""
        font_8x12 = {
            '0': [0x3C,0x66,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0x66,0x3C],
            '1': [0x18,0x38,0x78,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x7E],
            '2': [0x3C,0x66,0xC6,0x06,0x06,0x0C,0x18,0x30,0x60,0xC0,0xC0,0xFF],
            '3': [0x3C,0x66,0xC6,0x06,0x06,0x1C,0x06,0x06,0x06,0xC6,0x66,0x3C],
            '4': [0x0C,0x1C,0x3C,0x6C,0xCC,0xFE,0x06,0x06,0x06,0x06,0x06,0x06],
            '5': [0xFE,0xC0,0xC0,0xC0,0xFC,0x06,0x06,0x06,0x06,0xC6,0x66,0x3C],
            '6': [0x3C,0x66,0xC6,0xC0,0xC0,0xFC,0xC6,0xC6,0xC6,0xC6,0x66,0x3C],
            '7': [0xFF,0x06,0x0C,0x18,0x30,0x30,0x30,0x60,0x60,0x60,0x60,0x60],
            '8': [0x3C,0x66,0xC6,0xC6,0x66,0x3C,0xC6,0xC6,0xC6,0xC6,0x66,0x3C],
            '9': [0x3C,0x66,0xC6,0xC6,0x66,0x3E,0x06,0x06,0x06,0x06,0x66,0x3C],
        }

        if digit not in font_8x12:
            return

        bitmap = font_8x12[digit]
        for row in range(12):
            bits = bitmap[row]
            for col in range(8):
                if bits & (0x80 >> col):
                    draw.rectangle([x + col, y + row, x + col, y + row], fill=color)

    def _draw_date(self, draw: ImageDraw, t: float):
        """绘制日期 - YYYY.MM.DD"""
        now = datetime.now()
        year_str = f"{now.year}"
        month_str = f"{now.month:02d}"
        day_str = f"{now.day:02d}"

        y = 2

        # 年份 (小字)
        self._draw_text_3x5(draw, 2, y, year_str, self.COLORS['dim_cyan'])

        # 月.日
        date_str = f"{month_str}.{day_str}"
        self._draw_text_3x5(draw, 20, y, date_str, self.COLORS['neon_cyan'])

        # 星期 (右对齐)
        weekdays = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        day_abbr = weekdays[now.weekday()]
        is_weekend = now.weekday() >= 5
        day_color = self.COLORS['neon_red'] if is_weekend else self.COLORS['neon_green']
        self._draw_text_3x5(draw, 50, y, day_abbr, day_color)

    def _draw_status_bar(self, draw: ImageDraw, status: dict, t: float):
        """绘制底部状态栏"""
        y = 52

        # MEM 进度条
        mem_pct = max(0, min(1, status.get('memory_usage', 0)))
        self._draw_text_3x5(draw, 1, y, "M", self.COLORS['dim_cyan'])
        self._draw_bar_8(draw, 5, y + 1, mem_pct, self._get_usage_color(mem_pct))

        # CPU 进度条
        cpu_pct = max(0, min(1, status.get('cpu_load', 0)))
        self._draw_text_3x5(draw, 19, y, "C", self.COLORS['dim_cyan'])
        self._draw_bar_8(draw, 23, y + 1, cpu_pct, self._get_usage_color(cpu_pct))

        # 忙碌状态指示
        is_busy = status.get('is_busy', False)
        busy_color = self.COLORS['neon_red'] if is_busy else self.COLORS['neon_green']
        busy_text = "BUSY" if is_busy else "IDLE"
        self._draw_text_3x5(draw, 36, y, busy_text, busy_color)

        # 滚动消息 (简化版)
        msg = status.get('last_message', '') or ''
        if msg:
            # 截断显示
            display = msg[:6] if len(msg) > 6 else msg
            color = self.COLORS['neon_pink']
            x = 54
            for ch in display:
                if ord(ch) > 127:
                    break
                self._draw_char_4x6(draw, x, y + 1, ch, color)
                x += 5
                if x > 62:
                    break

    def _draw_decorations(self, draw: ImageDraw, t: float):
        """绘制装饰元素 - 角落标记"""
        # 左上角
        draw.line([(0, 0), (6, 0)], fill=self.COLORS['neon_cyan'], width=1)
        draw.line([(0, 0), (0, 6)], fill=self.COLORS['neon_cyan'], width=1)

        # 右上角
        draw.line([(57, 0), (63, 0)], fill=self.COLORS['neon_pink'], width=1)
        draw.line([(63, 0), (63, 6)], fill=self.COLORS['neon_pink'], width=1)

        # 左下角
        draw.line([(0, 63), (6, 63)], fill=self.COLORS['neon_yellow'], width=1)
        draw.line([(0, 57), (0, 63)], fill=self.COLORS['neon_yellow'], width=1)

        # 右下角
        draw.line([(57, 63), (63, 63)], fill=self.COLORS['neon_green'], width=1)
        draw.line([(63, 57), (63, 63)], fill=self.COLORS['neon_green'], width=1)

        # 中间装饰 - 上下箭头
        pulse = int(100 + 100 * np.sin(self._pulse_phase * 2))
        draw.polygon([(31, 50), (29, 52), (33, 52)], fill=(pulse // 4, pulse // 2, pulse))
        draw.polygon([(31, 51), (29, 49), (33, 49)], fill=(pulse // 4, pulse // 2, pulse))

    def _draw_glitch(self, draw: ImageDraw, t: float):
        """绘制故障效果"""
        glitch_y = int(t * 30) % 50 + 5
        glitch_h = 3

        # 红色偏移层
        draw.rectangle([2, glitch_y, 63, glitch_y + glitch_h], fill=self.COLORS['glitch_red'] + (50,))

        # 蓝色偏移层
        draw.rectangle([0, glitch_y + 1, 63, glitch_y + glitch_h + 1], fill=self.COLORS['glitch_blue'] + (30,))

    def _draw_text_3x5(self, draw: ImageDraw, x: int, y: int, text: str, color: tuple):
        """绘制 3x5 像素文字"""
        font_3x5 = {
            'M': [[1,0,1],[1,1,1],[1,0,1],[1,0,1],[1,0,1]],
            'E': [[1,1,1],[1,0,1],[1,1,0],[1,0,1],[1,1,1]],
            'C': [[1,1,1],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],
            'P': [[1,1,0],[1,0,1],[1,1,0],[1,0,0],[1,0,0]],
            'I': [[0,1,0],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],
            'D': [[1,1,0],[1,0,1],[1,0,1],[1,0,1],[1,1,0]],
            'L': [[1,0,0],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],
            'S': [[1,1,1],[1,0,0],[1,1,1],[0,0,1],[1,1,1]],
            'Y': [[1,0,1],[1,0,1],[0,1,0],[0,1,0],[0,1,0]],
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
            '.': [[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,1,0]],
            ':': [[0,1,0],[0,1,0],[0,0,0],[0,1,0],[0,1,0]],
            'B': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,1,0]],
            'U': [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],
            'T': [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],
            'W': [[1,0,1],[1,0,1],[1,1,1],[1,0,1],[1,1,1]],
            'N': [[1,0,1],[1,1,1],[1,1,1],[1,0,1],[1,0,1]],
            'F': [[1,1,1],[1,0,0],[1,1,0],[1,0,0],[1,0,0]],
            'G': [[1,1,1],[1,0,0],[1,0,1],[1,0,1],[1,1,1]],
            'H': [[1,0,1],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],
            'K': [[1,0,1],[1,1,0],[1,0,0],[1,1,0],[1,0,1]],
            'R': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,0,1]],
            'O': [[1,1,1],[1,0,1],[1,0,1],[1,0,1],[1,1,1]],
            'A': [[0,1,0],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],
            'V': [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[0,1,0]],
            'X': [[1,0,1],[1,0,1],[0,1,0],[1,0,1],[1,0,1]],
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

    def _draw_char_4x6(self, draw: ImageDraw, x: int, y: int, char: str, color: tuple):
        """绘制 4x6 像素ASCII字符"""
        font_4x6 = {
            'A': [0x0E,0x11,0x11,0x1F,0x11,0x11],
            'B': [0x1E,0x11,0x11,0x1E,0x11,0x1E],
            'C': [0x0E,0x11,0x10,0x10,0x11,0x0E],
            'D': [0x1E,0x11,0x11,0x11,0x11,0x1E],
            'E': [0x1F,0x10,0x10,0x1E,0x10,0x1F],
            'F': [0x1F,0x10,0x10,0x1E,0x10,0x10],
            'G': [0x0E,0x11,0x10,0x17,0x11,0x0F],
            'H': [0x11,0x11,0x11,0x1F,0x11,0x11],
            'I': [0x1E,0x04,0x04,0x04,0x04,0x1E],
            'J': [0x0F,0x02,0x02,0x02,0x12,0x0C],
            'K': [0x11,0x12,0x14,0x18,0x14,0x12],
            'L': [0x10,0x10,0x10,0x10,0x10,0x1F],
            'M': [0x11,0x1B,0x15,0x15,0x11,0x11],
            'N': [0x11,0x19,0x15,0x13,0x11,0x11],
            'O': [0x0E,0x11,0x11,0x11,0x11,0x0E],
            'P': [0x1E,0x11,0x11,0x1E,0x10,0x10],
            'Q': [0x0E,0x11,0x11,0x11,0x15,0x0D],
            'R': [0x1E,0x11,0x11,0x1E,0x14,0x12],
            'S': [0x0E,0x11,0x10,0x0E,0x01,0x1E],
            'T': [0x1F,0x04,0x04,0x04,0x04,0x04],
            'U': [0x11,0x11,0x11,0x11,0x11,0x0E],
            'V': [0x11,0x11,0x11,0x11,0x0A,0x04],
            'W': [0x11,0x11,0x11,0x15,0x15,0x0A],
            'X': [0x11,0x11,0x0A,0x04,0x0A,0x11],
            'Y': [0x11,0x11,0x0A,0x04,0x04,0x04],
            'Z': [0x1F,0x02,0x04,0x08,0x10,0x1F],
            '0': [0x0E,0x11,0x13,0x15,0x19,0x0E],
            '1': [0x04,0x0C,0x04,0x04,0x04,0x0E],
            '2': [0x0E,0x11,0x01,0x0E,0x10,0x1F],
            '3': [0x0E,0x11,0x01,0x0E,0x01,0x1E],
            '4': [0x02,0x0E,0x1F,0x11,0x01,0x01],
            '5': [0x1F,0x10,0x1E,0x01,0x11,0x0E],
            '6': [0x06,0x08,0x10,0x1E,0x11,0x0E],
            '7': [0x1F,0x01,0x02,0x04,0x04,0x04],
            '8': [0x0E,0x11,0x0E,0x11,0x11,0x0E],
            '9': [0x0E,0x11,0x0F,0x01,0x02,0x0C],
            'a': [0x00,0x0E,0x11,0x1F,0x11,0x0E],
            'b': [0x10,0x10,0x12,0x1E,0x11,0x1E],
            'c': [0x00,0x0E,0x11,0x10,0x11,0x0E],
            'd': [0x01,0x01,0x0D,0x13,0x11,0x0F],
            'e': [0x00,0x0E,0x11,0x1F,0x10,0x0E],
            'f': [0x0C,0x12,0x10,0x1C,0x10,0x10],
            'g': [0x00,0x0E,0x11,0x0E,0x01,0x0E],
            'h': [0x10,0x10,0x16,0x19,0x11,0x11],
            'i': [0x04,0x00,0x0C,0x04,0x04,0x0E],
            'j': [0x02,0x00,0x06,0x02,0x02,0x0C],
            'k': [0x10,0x10,0x12,0x14,0x18,0x12],
            'l': [0x0C,0x04,0x04,0x04,0x04,0x0E],
            'm': [0x00,0x1B,0x15,0x15,0x11,0x11],
            'n': [0x00,0x16,0x19,0x11,0x11,0x11],
            'o': [0x00,0x0E,0x11,0x11,0x11,0x0E],
            'p': [0x00,0x1E,0x11,0x1E,0x10,0x10],
            'q': [0x00,0x0D,0x13,0x0D,0x01,0x01],
            'r': [0x00,0x16,0x18,0x10,0x10,0x10],
            's': [0x00,0x0F,0x10,0x0E,0x01,0x1E],
            't': [0x08,0x10,0x1C,0x10,0x12,0x0C],
            'u': [0x00,0x11,0x11,0x13,0x0D,0x06],
            'v': [0x00,0x11,0x11,0x11,0x0A,0x04],
            'w': [0x00,0x11,0x11,0x15,0x15,0x0A],
            'x': [0x00,0x11,0x0A,0x04,0x0A,0x11],
            'y': [0x00,0x11,0x11,0x0F,0x01,0x0E],
            'z': [0x00,0x1F,0x02,0x04,0x08,0x1F],
            ':': [0x00,0x0C,0x0C,0x00,0x0C,0x0C],
            '.': [0x00,0x00,0x00,0x00,0x0C,0x0C],
            '-': [0x00,0x00,0x1F,0x00,0x00,0x00],
            '_': [0x00,0x00,0x00,0x00,0x00,0x1F],
            '!': [0x0C,0x0C,0x0C,0x00,0x0C,0x0C],
            '?': [0x0E,0x11,0x01,0x0E,0x00,0x0E],
        }

        if char not in font_4x6:
            return

        bitmap = font_4x6[char]
        for row in range(6):
            bits = bitmap[row]
            for col in range(4):
                if bits & (0x08 >> col):
                    draw.rectangle([x + col, y + row, x + col, y + row], fill=color)

    def _draw_bar_8(self, draw: ImageDraw, x: int, y: int, pct: float, color: tuple):
        """绘制8像素宽进度条"""
        fill = max(1, int(8 * pct))
        draw.rectangle([x, y, x + 7, y + 3], fill=(30, 30, 50))
        draw.rectangle([x, y, x + fill - 1, y + 3], fill=color)

    def _get_usage_color(self, pct: float) -> tuple:
        """根据使用率获取霓虹色"""
        if pct < 0.5:
            return self.COLORS['neon_green']
        elif pct < 0.8:
            return self.COLORS['neon_orange']
        else:
            return self.COLORS['neon_red']


# 独立测试
if __name__ == '__main__':
    import time
    import os

    theme = CyberClockTheme()

    print("🧪 测试 CyberClock Theme...")
    print(f"生成 10 帧测试图像到 {BASE_DIR}/themes/test_frames/")

    os.makedirs(os.path.join(BASE_DIR, 'themes/test_frames'), exist_ok=True)

    for i in range(10):
        frame = theme.generate_frame({
            'is_busy': i % 3 == 0,
            'memory_usage': 0.3 + (i % 5) * 0.1,
            'cpu_load': 0.2 + (i % 4) * 0.15,
            'last_message': 'CyberClock'
        }, t=time.time() + i * 0.1)

        img = Image.fromarray(frame)
        img.save(fos.path.join(BASE_DIR, 'themes/test_frames/cyber_{i:02d}.png'))
        print(f"  帧 {i:02d} 已保存")

    print("✅ 测试完成！")
