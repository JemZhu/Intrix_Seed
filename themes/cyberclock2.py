"""
CyberClock 赛博朋克时钟主题
- 大号像素数字时钟（霓虹色）
- 斜向雨滴粒子效果
- 底部渐变光晕
- 可选日期/星期显示
"""
# --- deploy: resolve project assets relative to this file (macOS-safe) ---
import os as _os
import os
BASE_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


import time
import random
import numpy as np
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ─── Pixel digit segments (5x5 grid = 25 values) ───
# Each digit: 5 rows x 5 cols, value=1 means pixel on
SEGMENTS = {
    '0': [1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1],
    '1': [0,0,0,0,1, 0,0,0,1,1, 0,0,1,0,1, 0,1,0,0,1, 0,0,0,0,1],
    '2': [1,1,1,1,1, 0,0,0,0,1, 1,1,1,1,1, 1,0,0,0,0, 1,1,1,1,1],
    '3': [1,1,1,1,1, 0,0,0,0,1, 1,1,1,1,1, 0,0,0,0,1, 1,1,1,1,1],
    '4': [1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1, 0,0,0,0,1, 0,0,0,0,1],
    '5': [1,1,1,1,1, 1,0,0,0,0, 1,1,1,1,1, 0,0,0,0,1, 1,1,1,1,1],
    '6': [1,1,1,1,1, 1,0,0,0,0, 1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1],
    '7': [1,1,1,1,1, 0,0,0,0,1, 0,0,0,1,0, 0,0,1,0,0, 0,0,1,0,0],
    '8': [1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1],
    '9': [1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1, 0,0,0,0,1, 1,1,1,1,1],
    ':': [0,0,0,0,0, 0,0,1,0,0, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0,0],
    'A': [1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1],
    'B': [1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1],
    'C': [1,1,1,1,1, 1,0,0,0,0, 1,0,0,0,0, 1,0,0,0,0, 1,1,1,1,1],
    'D': [1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1],
    'E': [1,1,1,1,1, 1,0,0,0,0, 1,1,1,1,0, 1,0,0,0,0, 1,1,1,1,1],
    'F': [1,1,1,1,1, 1,0,0,0,0, 1,1,1,1,0, 1,0,0,0,0, 1,0,0,0,0],
    'G': [1,1,1,1,1, 1,0,0,0,0, 1,0,1,1,1, 1,0,0,0,1, 1,1,1,1,1],
    'H': [1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1],
    'I': [1,1,1,1,1, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0, 1,1,1,1,1],
    'J': [0,0,0,0,1, 0,0,0,0,1, 0,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1],
    'K': [1,0,0,0,1, 1,0,0,1,0, 1,1,1,0,0, 1,0,0,1,0, 1,0,0,0,1],
    'L': [1,0,0,0,0, 1,0,0,0,0, 1,0,0,0,0, 1,0,0,0,0, 1,1,1,1,1],
    'M': [1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1],
    'N': [1,0,0,0,1, 1,1,0,0,1, 1,0,1,0,1, 1,0,0,1,1, 1,0,0,0,1],
    'O': [1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1],
    'P': [1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,0, 1,0,0,0,0],
    'Q': [1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,1,1, 1,1,1,1,1],
    'R': [1,1,1,1,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,1,0, 1,0,0,0,1],
    'S': [1,1,1,1,1, 1,0,0,0,0, 1,1,1,1,1, 0,0,0,0,1, 1,1,1,1,1],
    'T': [1,1,1,1,1, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0],
    'U': [1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1],
    'V': [1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 0,1,1,0,0],
    'W': [1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1],
    'X': [1,0,0,0,1, 0,1,0,1,0, 0,0,1,0,0, 0,1,0,1,0, 1,0,0,0,1],
    'Y': [1,0,0,0,1, 0,1,0,1,0, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0],
    'Z': [1,1,1,1,1, 0,0,0,1,0, 0,0,1,0,0, 0,1,0,0,0, 1,1,1,1,1],
    ' ': [0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0],
    '-': [0,0,0,0,0, 0,0,0,0,0, 1,1,1,1,1, 0,0,0,0,0, 0,0,0,0,0],
    '.': [0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,1,0,0],
    '/': [0,0,0,0,1, 0,0,0,1,0, 0,0,1,0,0, 0,1,0,0,0, 1,0,0,0,0],
}


def _draw_pixel_char(pixels, x, y, char, color, scale=1):
    """在像素数组上绘制单个像素字符"""
    seg = SEGMENTS.get(char.upper(), SEGMENTS[' '])
    for row in range(5):
        for col in range(5):
            if seg[row * 5 + col]:
                for sy in range(scale):
                    for sx in range(scale):
                        px, py = x + col * scale + sx, y + row * scale + sy
                        if 0 <= px < 64 and 0 <= py < 64:
                            pixels[py, px] = color


def _hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


class CyberClockTheme:
    """赛博朋克时钟主题"""

    DEFAULTS = {
        'time_color': '#00ffff',
        'shadow_color': '#ff00ff',
        'glow_color': '#0044ff',
        'rain_color': '#3366ff',
        'bg_color': '#050510',
        'time_show': True,
        'date_show': True,
        'weekday_show': True,
        'time_size': 1,
        'date_size': 1,
        'weekday_size': 1,
        'rain_density': 60,
    }

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self._rain_drops = []
        self._ticks = 0
        for k, v in self.DEFAULTS.items():
            setattr(self, k, v)
        for _ in range(80):
            self._rain_drops.append(self._new_drop())

    def _new_drop(self):
        return {
            'x': random.randint(0, 63),
            'y': random.randint(-63, 0),
            'speed': random.uniform(1.5, 4.0),
            'len': random.randint(3, 8),
            'brightness': random.randint(100, 255),
        }

    def set_config(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.DEFAULTS or hasattr(self, k):
                setattr(self, k, v)

    def _draw_rain(self, pixels):
        density = getattr(self, 'rain_density', 60) / 100.0
        rain_color = _hex_to_rgb(getattr(self, 'rain_color', '#3366ff'))
        drops_to_draw = int(80 * density)

        for drop in self._rain_drops[:drops_to_draw]:
            b = int(drop['brightness'])
            c = (min(255, b), min(255, b // 2), min(255, b // 4))
            for i in range(drop['len']):
                dy = int(drop['y'] + i)
                dx = int(drop['x'] + i * 0.3)
                if 0 <= dy < 64 and 0 <= dx < 64:
                    pixels[dy, dx] = c
                else:
                    break

            drop['y'] += drop['speed']
            drop['x'] += drop['speed'] * 0.3
            drop['brightness'] = max(80, drop['brightness'] - 1)

            if drop['y'] > 63 or drop['x'] > 63:
                if random.random() < 0.3:
                    new_drop = self._new_drop()
                    new_drop['y'] = random.randint(-10, -1)
                    new_drop['x'] = random.randint(0, 63)
                    drop.update(new_drop)

    def _draw_digit(self, pixels, x, y, digit_str, color, scale=3):
        cx = x
        for ch in digit_str:
            _draw_pixel_char(pixels, cx, y, ch, color, scale)
            cx += 6 * scale

    def _draw_text(self, pixels, text, x, y, color, shadow=None, size=8):
        """用 quan.ttf 在指定位置绘制文字"""
        font_paths = [
            os.path.join(BASE_DIR, 'fonts/quan.ttf'),
            os.path.join(BASE_DIR, 'font/quan.ttf'),
            './fonts/quan.ttf',
            './quan.ttf',
        ]
        font = None
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, size)
                break
            except:
                pass
        if font is None:
            # fallback: 用位图方式
            self._draw_digit(pixels, x, y, text, color, 1)
            return

        # 用 PIL 绘制到 numpy 数组
        img = Image.new('RGB', (self.width, self.height))
        ImageDraw.Draw(img).text((x + 1, y + 1), text, font=font, fill=shadow or (0,0,0))
        img_arr = np.array(img)
        for row in range(self.height):
            for col in range(self.width):
                px = img_arr[row, col]
                if any(c > 0 for c in px):  # 非黑色像素
                    pixels[row, col] = px

    def _draw_glitch(self, pixels):
        if random.random() > 0.05:
            return
        time_color = _hex_to_rgb(getattr(self, 'time_color', '#00ffff'))
        shadow_color = _hex_to_rgb(getattr(self, 'shadow_color', '#ff00ff'))
        row = random.randint(10, 40)
        dy = random.randint(-1, 1)
        for x in range(0, 64, 2):
            px = random.randint(0, 63)
            c = shadow_color if random.random() > 0.5 else time_color
            py = row + dy
            if 0 <= py < 64 and 0 <= px < 64:
                pixels[py, px] = c

    def _draw_bottom_glow(self, pixels):
        glow = _hex_to_rgb(getattr(self, 'glow_color', '#0044ff'))
        for y in range(50, 64):
            alpha = (y - 50) / 14.0 * 0.4
            r = int(glow[0] * alpha)
            g = int(glow[1] * alpha)
            b = int(glow[2] * alpha)
            for x in range(64):
                orig = pixels[y, x]
                pixels[y, x] = (
                    min(255, orig[0] + r),
                    min(255, orig[1] + g),
                    min(255, orig[2] + b),
                )

    def _draw_scanline(self, pixels):
        scan_y = (self._ticks % 64)
        if scan_y < 64:
            for x in range(64):
                orig = pixels[scan_y, x]
                pixels[scan_y, x] = (
                    min(255, orig[0] + 10),
                    min(255, orig[1] + 10),
                    min(255, orig[2] + 20),
                )

    def generate_frame(self) -> np.ndarray:
        self._ticks += 1
        bg = _hex_to_rgb(getattr(self, 'bg_color', '#050510'))
        pixels = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        for y in range(self.height):
            for x in range(self.width):
                pixels[y, x] = bg

        time_color = _hex_to_rgb(getattr(self, 'time_color', '#00ffff'))
        shadow_color = _hex_to_rgb(getattr(self, 'shadow_color', '#ff00ff'))
        scale = getattr(self, 'time_size', 3)

        self._draw_rain(pixels)
        self._draw_bottom_glow(pixels)

        now = datetime.now()

        if getattr(self, 'time_show', True):
            h = now.hour
            m = now.minute
            s = now.second
            time_str = f"{h:02d}:{m:02d}:{s:02d}"
            char_w = 6 * scale
            total_w = len(time_str) * char_w
            tx = max(0, (64 - total_w) // 2)
            ty = 12

            self._draw_glitch(pixels)
            self._draw_digit(pixels, tx + 1, ty + 1, time_str, shadow_color, scale)
            self._draw_digit(pixels, tx, ty, time_str, time_color, scale)
            self._draw_scanline(pixels)

        if getattr(self, 'date_show', True):
            date_str = now.strftime('%Y-%m-%d')
            dscale = getattr(self, 'date_size', 1)
            dw = len(date_str) * 6 * dscale
            dx = max(0, (64 - dw) // 2)
            dy = 38
            self._draw_digit(pixels, dx + 1, dy + 1, date_str, shadow_color, dscale)
            self._draw_digit(pixels, dx, dy, date_str, time_color, dscale)

        if getattr(self, 'weekday_show', True):
            labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            wd = labels[now.weekday()]
            wscale = getattr(self, 'weekday_size', 1)
            ww = len(wd) * 6 * wscale
            wx = max(0, (64 - ww) // 2)
            wy = 47
            self._draw_digit(pixels, wx + 1, wy + 1, wd, shadow_color, wscale)
            self._draw_digit(pixels, wx, wy, wd, time_color, wscale)

        return pixels
