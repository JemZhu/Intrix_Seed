#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Theme - A股实时行情 (64x64)
显示股票名称、当前价（红涨绿跌）、涨跌幅、成交量、换手率
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import urllib.request
import json
import time
import os


# ─── HZK12 点阵汉字渲染 ──────────────────────────────────────────
_HZK12_PATH = '/home/jem/Intrix_Seed/HZK12'

def _hzk12_bytes():
    if not os.path.exists(_HZK12_PATH):
        return None
    with open(_HZK12_PATH, 'rb') as f:
        return f.read()

def draw_hzk12(draw, x, y, text, color, bg=None):
    """用 HZK12 在 PIL ImageDraw 上绘制一行汉字（12px 高）"""
    hzk = _hzk12_bytes()
    if hzk is None:
        return x
    for ch in text:
        try:
            ch_bytes = ch.encode('gb2312')
        except (UnicodeEncodeError, LookupError):
            continue
        if len(ch_bytes) != 2:
            continue
        q = ch_bytes[0] - 0xA1
        w = ch_bytes[1] - 0xA1
        off = 24 * (94 * q + w)
        if off < 0 or off + 24 > len(hzk):
            continue
        bmp = hzk[off:off + 24]
        for row in range(12):
            for col in range(12):
                byte_idx = row * 2 + (col // 8)
                bit_idx = 7 - (col % 8)
                if byte_idx < len(bmp) and (bmp[byte_idx] >> bit_idx) & 1:
                    draw.point((x + col, y + row), fill=color)
                elif bg is not None:
                    draw.point((x + col, y + row), fill=bg)
        x += 12
    return x


# ─── 实心像素数字渲染（3×5 bitmap，无抗锯齿）──────────────────────
# 每个数字: 3px宽, 5px高, digits排列时 4px 宽(含1px间距)
_DIGIT_BITS = {
    '0': [1,1,1, 1,0,1, 1,0,1, 1,0,1, 1,1,1],
    '1': [0,1,0, 1,1,0, 0,1,0, 0,1,0, 1,1,1],
    '2': [1,1,1, 0,0,1, 1,1,1, 1,0,0, 1,1,1],
    '3': [1,1,1, 0,0,1, 1,1,1, 0,0,1, 1,1,1],
    '4': [1,0,1, 1,0,1, 1,1,1, 0,0,1, 0,0,1],
    '5': [1,1,1, 1,0,0, 1,1,1, 0,0,1, 1,1,1],
    '6': [1,1,1, 1,0,0, 1,1,1, 1,0,1, 1,1,1],
    '7': [1,1,1, 0,0,1, 0,0,1, 0,0,1, 0,0,1],
    '8': [1,1,1, 1,0,1, 1,1,1, 1,0,1, 1,1,1],
    '9': [1,1,1, 1,0,1, 1,1,1, 0,0,1, 1,1,1],
}

def draw_digit(draw, x, y, ch, color, scale=1):
    """绘制单个像素数字（3×5），可缩放"""
    bits = _DIGIT_BITS.get(ch)
    if not bits:
        return
    for row in range(5):
        for col in range(3):
            if bits[row * 3 + col]:
                for sy in range(scale):
                    for sx in range(scale):
                        draw.point((x + col * scale + sx, y + row * scale + sy), fill=color)

def draw_price(draw, x, y, price_str, color, scale=1):
    """绘制价格数字串（小数点占用1px），可缩放"""
    for ch in price_str:
        if ch == '.':
            sy = scale
            draw.point((x, y + 3 * scale), fill=color)
            x += 2 * scale
        elif ch == '-':
            for sx in range(3 * scale):
                draw.point((x + sx, y + 2 * scale), fill=color)
            x += 4 * scale
        else:
            draw_digit(draw, x, y, ch, color, scale)
            x += 4 * scale   # digit 3px + 1px间距

def draw_5digit(draw, x, y, text, color, scale=1):
    """用像素数字渲染纯数字字符串（时间、代码等）"""
    for ch in text:
        if ch == ':' or ch == '-':
            draw.point((x, y + 2 * scale), fill=color)
            x += 2 * scale
        else:
            draw_digit(draw, x, y, ch, color, scale)
            x += 4 * scale


# ─── StockTheme ──────────────────────────────────────────────────
class StockTheme:
    _stock_codes = ['600036']
    _current_index = 0
    _cache = {}
    _cache_ttl = 30

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.C = {
            'bg':      (10, 5, 25),
            'gold':    (255, 215, 0),
            'red':     (255, 60, 60),
            'green':   (50, 200, 80),
            'white':   (255, 255, 255),
            'black':   (0, 0, 0),
            'dim':     (90, 90, 130),
            'div':     (45, 38, 75),
            'skyblue': (0, 180, 255),
        }
        self._f8 = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 8)
        self._f7 = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 7)
        self._f6 = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 6)

    @classmethod
    def set_stock_codes(cls, codes):
        cleaned = []
        for c in codes:
            c = c.strip()
            c = c.removeprefix('sh').removeprefix('sz').removeprefix('SH').removeprefix('SZ')
            if c:
                cleaned.append(c)
        cls._stock_codes = cleaned
        cls._current_index = 0

    @classmethod
    def get_stock_codes(cls):
        return cls._stock_codes

    @classmethod
    def get_current_code(cls):
        return cls._stock_codes[cls._current_index] if cls._stock_codes else None

    @classmethod
    def next_stock(cls):
        if cls._stock_codes:
            cls._current_index = (cls._current_index + 1) % len(cls._stock_codes)

    def _fetch_stock_data(self, code):
        now = time.time()
        cached = self._cache.get(code)
        if cached and (now - cached['timestamp']) < self._cache_ttl:
            return cached['data']
        try:
            raw = code.strip().lstrip('sh').lstrip('sz').lstrip('SH').lstrip('SZ')
            stock_num = raw[-6:]
            market = '1' if stock_num.startswith(('6', '9')) else '0'
            secid = f'{market}.{stock_num}'
            fields = 'f43,f44,f45,f46,f47,f48,f57,f58,f103,f104,f105,f106,f107,f108,f116,f117,f152,f168,f169,f170,f171'
            url = f'http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields={fields}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                text = resp.read().decode('utf-8')
            obj = json.loads(text)
            data = obj.get('data', {}) or {}
            self._cache[code] = {'data': data, 'timestamp': now}
            return data
        except Exception:
            cached = self._cache.get(code)
            return cached['data'] if cached else None

    def _fw(self, text, font):
        return font.getbbox(text)[2]

    def _t(self, d, x, y, text, color, font):
        try:
            d.text((x, y), text, fill=color, font=font)
        except:
            pass

    def _tri_up(self, d, x, y, color, size=4):
        d.polygon([(x, y), (x - size, y + size), (x + size, y + size)], fill=color)

    def _tri_down(self, d, x, y, color, size=4):
        d.polygon([(x, y), (x - size, y - size), (x + size, y - size)], fill=color)

    def _price_width(self, s):
        """计算像素数字串的像素宽度"""
        w = 0
        for ch in s:
            if ch == '.':
                w += 2
            else:
                w += 4
        return w

    def generate_frame(self, status=None, t=None):
        import time as _time
        if t is None:
            t = _time.time()

        img = Image.new('RGB', (self.width, self.height), self.C['bg'])
        d = ImageDraw.Draw(img)

        code = self.get_current_code()
        if not code:
            self._t(d, 10, 28, '---', self.C['dim'], self._f8)
            return np.array(img)

        data = self._fetch_stock_data(code)
        self._bg_gradient(d)

        # 布局（y坐标）：
        #  0~10  : 股票名称 (HZK12)
        #  11    : 分隔线
        #  13~24 : 股价 + 背景框（实心像素数字）
        #  25    : 分隔线
        #  27~34 : 涨跌幅 + 三角（无+-号）
        #  36    : 分隔线
        #  38~45 : 成交量
        #  47    : 分隔线
        #  49~56 : 换手率
        #  58~63 : 股票代码(天蓝) + 时间(金)

        self._divider(d, 11)
        self._divider(d, 25)
        self._divider(d, 36)
        self._divider(d, 47)

        self._name_row(d, code, data, t)
        self._price_row(d, data)
        self._change_row(d, data)
        self._vol_row(d, data)
        self._turnover_row(d, data)
        self._footer(d, code)

        return np.array(img)

    def _bg_gradient(self, d):
        for y in range(self.height):
            r = int(10 + y / self.height * 8)
            g = int(5 + y / self.height * 4)
            b = int(25 + y / self.height * 12)
            d.rectangle([(0, y), (63, y)], fill=(r, g, b))

    def _divider(self, d, y):
        d.line([(4, y), (60, y)], fill=self.C['div'], width=1)

    def _name_row(self, d, code, data, t=0):
        import math
        name = data.get('f58', code) if data else code
        if len(name) > 4:
            name = name[:4]
        name_w = len(name) * 12
        x = (64 - name_w) // 2
        # 颜色渐变：每个字符在金色范围内呼吸闪烁
        for i, ch in enumerate(name):
            phase = t * 2 + i * 0.5
            brightness = int(180 + 75 * (math.sin(phase) * 0.5 + 0.5))  # 180~255
            color = (brightness, int(brightness * 0.84), 0)  # 金色渐变 R~255, G~180~215
            draw_hzk12(d, x + i * 12, 0, ch, color)
        return name

    def _price_row(self, d, data):
        """股价：HZK12标签 + 实心像素数字（放大2倍=10px高）"""
        if not data:
            draw_hzk12(d, 4, 13, '价--.--', self.C['dim'])
            return

        price = data.get('f43', 0)
        change_pct = data.get('f170', 0) / 100.0

        price_str = f'{price / 100:.2f}' if price else '---.--'

        if change_pct > 0:
            bg_c, fg_c = self.C['red'], self.C['white']
        elif change_pct < 0:
            bg_c, fg_c = self.C['green'], self.C['white']
        else:
            bg_c, fg_c = self.C['white'], self.C['black']

        # 用像素数字量宽度（scale=2: 每数字8px宽）
        pw = sum(4 if ch.isdigit() else (2 if ch == '.' else 0) for ch in price_str) * 2
        pad = 1
        total_w = pw + pad * 2
        rect_l = max(0, (64 - total_w) // 2 - pad)
        rect_r = min(63, rect_l + total_w + pad * 2)
        d.rectangle([rect_l, 13, rect_r, 24], fill=bg_c)

        # 实心像素数字（scale=2 → 10px高），y=14（底部在y=24）
        draw_price(d, rect_l + pad + 1, 14, price_str, fg_c, scale=2)

    def _change_row(self, d, data):
        """涨跌幅 + 三角，无+-号"""
        if not data:
            self._t(d, 4, 27, '--%', self.C['dim'], self._f8)
            return

        change_pct = data.get('f170', 0) / 100.0
        is_up = (change_pct > 0)
        color = self.C['red'] if is_up else self.C['green']

        pct_str = f'{abs(change_pct):.2f}%'   # 无+-号

        tri_size = 3
        gap = 2
        # pct_str 数字宽度估算：每字符6px
        pct_w = len(pct_str) * 6
        total_w = tri_size + gap + pct_w
        start_x = max(1, (64 - total_w) // 2)

        tri_x = start_x
        tri_y = 27 + 4   # y=31 附近（三角高6px，中心在y=31）
        if is_up:
            self._tri_up(d, tri_x, tri_y, color, tri_size)
        else:
            self._tri_down(d, tri_x, tri_y, color, tri_size)

        # 数字从三角右侧 gap 处开始
        self._t(d, tri_x + tri_size + gap, 27, pct_str, color, self._f8)

    def _vol_row(self, d, data):
        """成交量，y=38"""
        if not data:
            self._t(d, 4, 38, '量', self.C['dim'], self._f8)
            self._t(d, 4 + 8, 38, '---', self.C['dim'], self._f8)
            return

        vol = data.get('f47', 0)
        if vol >= 100000000:
            vol_str = f'{vol / 100000000:.1f}亿'
        elif vol >= 10000:
            vol_str = f'{vol / 10000:.1f}万'
        else:
            vol_str = str(vol)

        self._t(d, 4, 38, '量', self.C['dim'], self._f8)
        self._t(d, 4 + 8, 38, vol_str, self.C['white'], self._f8)

    def _turnover_row(self, d, data):
        """换手率，y=49"""
        if not data:
            self._t(d, 4, 49, '换', self.C['dim'], self._f8)
            self._t(d, 4 + 8, 49, '---', self.C['dim'], self._f8)
            return

        turnover = data.get('f168', 0) / 100.0
        turnover_str = f'{turnover:.2f}%' if turnover else '-.--%'

        self._t(d, 4, 49, '换', self.C['dim'], self._f8)
        self._t(d, 4 + 8, 49, turnover_str, self.C['white'], self._f8)

    def _footer(self, d, code):
        now = datetime.now()
        time_str = f'{now.hour:02d}:{now.minute:02d}'

        # 股票代码（6位）：天蓝色，像素数字 scale=1 (5px高)
        code_str = code[-6:]
        draw_5digit(d, 2, 58, code_str, self.C['skyblue'], scale=1)

        # 时间 HH:MM:SS：金色，像素数字，x=36 固定位置
        time_str = f'{now.hour:02d}:{now.minute:02d}:{now.second:02d}'
        draw_5digit(d, 36, 58, time_str, self.C['gold'], scale=1)


if __name__ == '__main__':
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    from PIL import Image
    theme = StockTheme()
    StockTheme.set_stock_codes(['600036', '000858', '601318'])
    for i, code in enumerate(StockTheme._stock_codes):
        data = theme._fetch_stock_data(code)
        pct = data.get('f170', 0) / 100 if data else 0
        print(f'{code}: {pct:+.2f}%')
        frame = theme.generate_frame()
        Image.fromarray(frame).save(f'/home/jem/Intrix_Seed/themes/test_frames/stock_{i}.png')
    print('Done')
