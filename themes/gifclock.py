#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GifClock Theme - GIF背景时钟主题 (优化版)
使用预渲染点阵字体 + numpy直接操作像素，无PIL文字渲染
"""
# --- deploy: resolve project assets relative to this file (macOS-safe) ---
import os as _os
import os
BASE_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


import time
import numpy as np
from datetime import datetime


class GifClockTheme:
    """GIF背景时钟主题 - 优化版"""

    # 8x12 点阵字体 (数字和大写字母)
    FONT_8x12 = {
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
        'A': [0x18,0x18,0x18,0x24,0x24,0x24,0x7E,0x42,0x42,0x42,0x42,0x42],
        'B': [0xFC,0x42,0x42,0x42,0x42,0x7C,0x42,0x42,0x42,0x42,0x42,0xFC],
        'C': [0x3C,0x66,0xC2,0xC0,0xC0,0xC0,0xC0,0xC0,0xC0,0xC2,0x66,0x3C],
        'D': [0xF8,0x44,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x44,0xF8,0x00],
        'E': [0xFE,0x42,0x40,0x40,0x40,0x7C,0x40,0x40,0x40,0x40,0x42,0xFE],
        'F': [0xFE,0x42,0x40,0x40,0x40,0x7C,0x40,0x40,0x40,0x40,0x40,0x40],
        'G': [0x3C,0x66,0xC2,0xC0,0xC0,0xC0,0xDE,0xC2,0xC2,0xC2,0x66,0x3A],
        'H': [0x42,0x42,0x42,0x42,0x42,0x7E,0x42,0x42,0x42,0x42,0x42,0x42],
        'I': [0x7E,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x7E],
        'J': [0x3E,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x4C,0x4C,0x78,0x00],
        'K': [0x44,0x48,0x50,0x60,0x70,0x40,0x70,0x60,0x50,0x48,0x44,0x44],
        'L': [0x40,0x40,0x40,0x40,0x40,0x40,0x40,0x40,0x40,0x40,0x40,0xFE],
        'M': [0x42,0x66,0x6E,0x7E,0x7E,0xD6,0xD6,0xD6,0xC6,0xC6,0xC6,0xC6],
        'N': [0x62,0x62,0x72,0x7A,0x5A,0x4E,0x46,0x46,0x46,0x46,0x46,0x46],
        'O': [0x3C,0x66,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0x66,0x3C],
        'P': [0xFC,0x42,0x42,0x42,0x42,0x7C,0x40,0x40,0x40,0x40,0x40,0x40],
        'Q': [0x3C,0x66,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0xC6,0xD6,0x66,0x3C],
        'R': [0xFC,0x42,0x42,0x42,0x42,0x7C,0x48,0x50,0x60,0x50,0x48,0x44],
        'S': [0x3C,0x66,0xC6,0xC0,0xC0,0x7C,0x06,0x06,0x06,0xC6,0x66,0x3C],
        'T': [0xFE,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18],
        'U': [0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x66,0x3C,0x00],
        'V': [0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x24,0x24,0x18,0x00],
        'W': [0x82,0x82,0x82,0x82,0x82,0x92,0x92,0xAA,0xC6,0xC6,0xC6,0x00],
        'X': [0x42,0x42,0x24,0x24,0x18,0x18,0x18,0x24,0x24,0x42,0x42,0x00],
        'Y': [0x42,0x42,0x24,0x24,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x00],
        'Z': [0xFE,0x06,0x06,0x0C,0x18,0x30,0x30,0x60,0xC0,0x80,0x80,0xFE],
        ':': [0x00,0x18,0x18,0x18,0x00,0x18,0x18,0x00,0x00,0x00,0x00,0x00],
        '-': [0x00,0x00,0x00,0x00,0x00,0xFE,0x00,0x00,0x00,0x00,0x00,0x00],
        '.': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x18,0x18,0x00],
        '/': [0x02,0x06,0x06,0x0C,0x0C,0x18,0x18,0x30,0x30,0x60,0x60,0x00],
        ' ': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
    }

    # 5x7 点阵字体 (数字和符号)
    FONT_5x7 = {
        '0': [0x0E,0x11,0x13,0x15,0x19,0x11,0x0E],
        '1': [0x04,0x0C,0x04,0x04,0x04,0x04,0x0E],
        '2': [0x0E,0x11,0x01,0x0E,0x10,0x10,0x1F],
        '3': [0x0E,0x11,0x01,0x0E,0x01,0x11,0x0E],
        '4': [0x02,0x0E,0x1F,0x11,0x01,0x01,0x01],
        '5': [0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E],
        '6': [0x06,0x08,0x10,0x1E,0x11,0x11,0x0E],
        '7': [0x1F,0x01,0x02,0x04,0x08,0x08,0x08],
        '8': [0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E],
        '9': [0x0E,0x11,0x11,0x0F,0x01,0x02,0x0C],
        'M': [0x11,0x1F,0x1F,0x1B,0x1B,0x1B,0x1B],
        'O': [0x0E,0x11,0x13,0x15,0x19,0x11,0x0E],
        'N': [0x11,0x19,0x15,0x13,0x11,0x11,0x11],
        'T': [0x1F,0x04,0x04,0x04,0x04,0x04,0x04],
        'U': [0x11,0x11,0x11,0x11,0x11,0x11,0x0E],
        'W': [0x11,0x11,0x11,0x11,0x15,0x1B,0x0A],
        'F': [0x1F,0x10,0x10,0x1E,0x10,0x10,0x10],
        'R': [0x1E,0x11,0x11,0x1E,0x14,0x12,0x11],
        'I': [0x0E,0x04,0x04,0x04,0x04,0x04,0x0E],
        'D': [0x1E,0x11,0x11,0x11,0x11,0x11,0x1E],
        'E': [0x1F,0x10,0x1E,0x10,0x10,0x10,0x1F],
        'H': [0x11,0x11,0x11,0x1F,0x11,0x11,0x11],
        'S': [0x0E,0x11,0x10,0x0E,0x01,0x11,0x0E],
        'A': [0x0E,0x11,0x11,0x1F,0x11,0x11,0x11],
        '-': [0x00,0x00,0x00,0x1F,0x00,0x00,0x00],
        '/': [0x01,0x02,0x04,0x08,0x10,0x00,0x00],
        ':': [0x00,0x0C,0x0C,0x00,0x0C,0x0C,0x00],
    }

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

        # 默认配置
        self.config = {
            'time_size': 12,
            'time_color': (255, 255, 255),
            'time_shadow': True,
            'time_shadow_color': (50, 50, 50),  # 深灰色阴影
            'time_x': 0,
            'time_y': 18,
            'date_show': True,
            'date_size': 6,
            'date_color': (200, 200, 200),
            'date_format': '%m/%d',
            'date_x': 0,
            'date_y': 38,
            'weekday_show': True,
            'weekday_size': 6,
            'weekday_color': (150, 150, 255),
            'weekday_shadow_color': (30, 30, 30),
            'weekday_x': 0,
            'weekday_y': 50,
        }

        # GIF数据
        self._gif_frames = []
        self._gif_index = 0
        self._gif_loaded = False

        # 预分配numpy数组用于文字绘制（复用）
        self._text_layer = np.zeros((64, 64, 3), dtype=np.uint8)

    def load_gif(self, path: str) -> bool:
        """加载GIF文件"""
        try:
            from PIL import Image
            img = Image.open(path)
            if img.format != 'GIF':
                return False

            self._gif_frames = []
            try:
                while True:
                    frame = img.copy().convert('RGB')
                    frame = frame.resize((self.width, self.height), Image.NEAREST)
                    self._gif_frames.append(np.array(frame))
                    img.seek(img.tell() + 1)
            except EOFError:
                pass

            if len(self._gif_frames) == 0:
                return False

            self._gif_index = 0
            self._gif_loaded = True
            return True
        except Exception as e:
            print(f"GIF load error: {e}")
            self._gif_loaded = False
            return False

    def is_loaded(self) -> bool:
        return self._gif_loaded and len(self._gif_frames) > 0

    def set_config(self, **kwargs):
        self.config.update(kwargs)

    def get_config(self) -> dict:
        return self.config.copy()

    def _draw_char_8x12(self, layer: np.ndarray, x: int, y: int, char: str, color: tuple, shadow_color: tuple = None, shadow_offset: int = 1):
        """绘制8x12字符（数字和大写字母）"""
        char = char.upper()
        if char not in self.FONT_8x12:
            return 8  # 未知的字符返回宽度

        bitmap = self.FONT_8x12[char]

        # 绘制阴影
        if shadow_color:
            for row in range(12):
                bits = bitmap[row]
                for col in range(8):
                    if bits & (0x80 >> col):
                        px = x + col + shadow_offset
                        py = y + row + shadow_offset
                        if 0 <= px < self.width and 0 <= py < self.height:
                            layer[py, px] = shadow_color

        # 绘制字符
        for row in range(12):
            bits = bitmap[row]
            for col in range(8):
                if bits & (0x80 >> col):
                    px = x + col
                    py = y + row
                    if 0 <= px < self.width and 0 <= py < self.height:
                        layer[py, px] = color

        return 8  # 字符宽度

    def _draw_char_5x7(self, layer: np.ndarray, x: int, y: int, char: str, color: tuple, shadow_color: tuple = None, shadow_offset: int = 1):
        """绘制5x7字符"""
        char = char.upper()
        if char not in self.FONT_5x7:
            return 5

        bitmap = self.FONT_5x7[char]

        for row in range(7):
            bits = bitmap[row]
            for col in range(5):
                if bits & (0x10 >> col):
                    px = x + col
                    py = y + row
                    if shadow_color:
                        for sdy in range(shadow_offset + 1):
                            for sdx in range(shadow_offset + 1):
                                spx = px + sdx
                                spy = py + sdy
                                if 0 <= spx < self.width and 0 <= spy < self.height:
                                    if sdx > 0 or sdy > 0:
                                        layer[spy, spx] = shadow_color
                    if 0 <= px < self.width and 0 <= py < self.height:
                        layer[py, px] = color

        return 5 + 1  # 字符宽度+间距

    def _draw_text_8x12(self, layer: np.ndarray, x: int, y: int, text: str, color: tuple, shadow: bool = True, shadow_color: tuple = (0, 0, 0), center: bool = False):
        """绘制8x12文字串"""
        # 计算文字宽度（固定8像素/字符）
        total_width = len(text) * 8

        if center:
            x = (self.width - total_width) // 2

        for ch in text:
            if ch == ':' or ch == '-' or ch == '.' or ch == ' ':
                if ch == ':':
                    # 画两个点
                    for dy in [3, 8]:
                        # 阴影
                        if shadow:
                            if 0 <= x + 3 + 1 < self.width and 0 <= y + dy + 1 < self.height:
                                layer[y + dy + 1, x + 3 + 1] = shadow_color
                        # 前景
                        if 0 <= x + 3 < self.width and 0 <= y + dy < self.height:
                            layer[y + dy, x + 3] = color
                x += 8
            else:
                self._draw_char_8x12(layer, x, y, ch, color, shadow_color if shadow else None)
                x += 8

    def _draw_text_5x7(self, layer: np.ndarray, x: int, y: int, text: str, color: tuple, center: bool = False, shadow: bool = False, shadow_color: tuple = (0, 0, 0)):
        """绘制5x7文字串"""
        total_width = len(text) * 6  # 5宽 + 1间距

        if center:
            x = (self.width - total_width) // 2

        for ch in text:
            self._draw_char_5x7(layer, x, y, ch, color, shadow_color if shadow else None, 1)
            x += 6

    def generate_frame(self, status: dict = None, t: float = None) -> np.ndarray:
        """生成GIF时钟帧"""
        if t is None:
            t = time.time()

        # 获取背景
        if self._gif_loaded and len(self._gif_frames) > 0:
            frame = self._gif_frames[self._gif_index].copy()
            self._gif_index = (self._gif_index + 1) % len(self._gif_frames)
        else:
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # 清除文字层
        self._text_layer.fill(0)

        cfg = self.config
        now = datetime.now()

        # 绘制时间 HH:MM:SS
        time_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        time_x = cfg['time_x'] if cfg['time_x'] != 0 else 0
        time_color = tuple(cfg['time_color']) if isinstance(cfg['time_color'], list) else cfg['time_color']
        shadow_color = tuple(cfg['time_shadow_color']) if isinstance(cfg['time_shadow_color'], list) else cfg['time_shadow_color']

        self._draw_text_8x12(
            self._text_layer,
            time_x, cfg['time_y'],
            time_str,
            time_color,
            shadow=cfg['time_shadow'],
            shadow_color=shadow_color,
            center=(cfg['time_x'] == 0)
        )

        # 绘制日期
        if cfg['date_show']:
            date_str = now.strftime(cfg['date_format'])
            date_color = tuple(cfg['date_color']) if isinstance(cfg['date_color'], list) else cfg['date_color']
            self._draw_text_8x12(
                self._text_layer,
                cfg['date_x'], cfg['date_y'],
                date_str,
                date_color,
                shadow=False,
                center=(cfg['date_x'] == 0)
            )

        # 绘制星期
        if cfg['weekday_show']:
            weekdays = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
            day_str = weekdays[now.weekday()]
            day_color = tuple(cfg['weekday_color']) if isinstance(cfg['weekday_color'], list) else cfg['weekday_color']
            wshadow = tuple(cfg.get('weekday_shadow_color', (30, 30, 30)))
            self._draw_text_5x7(
                self._text_layer,
                cfg['weekday_x'], cfg['weekday_y'],
                day_str,
                day_color,
                center=(cfg['weekday_x'] == 0),
                shadow=True,
                shadow_color=wshadow
            )

        # 合并文字层到背景
        # 合并文字层到背景（使用亮度检测，非(0,0,0)的像素）
        brightness = self._text_layer.sum(axis=2)
        # 只要有任何像素被绘制过（非背景0,0,0），就复制所有通道
        # 阴影颜色是(1,1,1)虽然暗但会被检测到
        drawn = brightness > 0
        frame[drawn] = self._text_layer[drawn]

        return frame


if __name__ == '__main__':
    import os
    theme = GifClockTheme()
    print("Testing optimized GifClock...")

    os.makedirs(os.path.join(BASE_DIR, 'themes/test_frames'), exist_ok=True)

    # 测试生成10帧
    import time
    start = time.time()
    for i in range(30):
        frame = theme.generate_frame(t=time.time() + i * 0.1)
    elapsed = time.time() - start
    print(f"30 frames in {elapsed:.3f}s ({30/elapsed:.1f} fps)")

    # 保存一帧看看
    from PIL import Image
    frame = theme.generate_frame()
    img = Image.fromarray(frame)
    img.save(os.path.join(BASE_DIR, 'themes/test_frames/gifclock_opt.png'))
    print("Saved test frame")
