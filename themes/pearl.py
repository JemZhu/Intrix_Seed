#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEARL Mining Dashboard Theme - 64x64 LED Matrix
显示: 当前算力、Worker在线数、Total Paid PRL、Pending Balance、PRL币价
每2分钟更新数据，数据面板每8秒轮换一页
"""
# --- deploy: resolve project assets relative to this file (macOS-safe) ---
import os as _os
BASE_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import urllib.request
import json
import time
import os
import math
import socket

# ─── 常量 & 配置 ─────────────────────────────────────────────────
_WALLET = 'prl1pd3wxf4cxzm9yevy0ffcw9h2z0khadlqu83w8q9ej6nuxzfgjlyjqdq6tk0'
_POOL_API = f'https://pearl.alphapool.tech/api/miner/{_WALLET}'
_POOL_STATS_API = 'https://pearl.alphapool.tech/api/stats'
_DATA_TTL = 120 # 数据缓存TTL: 2分钟
_PANEL_DURATION = 8  # 每面板显示秒数
_NUM_PANELS = 5

_THEME_DIR = os.path.join(BASE_DIR, '')
_FONT_PATH = f'{_THEME_DIR}/quan.ttf'


# ─── 数据缓存 ─────────────────────────────────────────────────────
_data_cache = {
    'miner': None,
    'price': None,
    'pool': None,
    'miner_ts': 0,
    'price_ts': 0,
    'pool_ts': 0,
}


# ─── API 获取 ─────────────────────────────────────────────────────
def fetch_miner_data():
    now = time.time()
    if _data_cache['miner'] is not None and (now - _data_cache['miner_ts']) < _DATA_TTL:
        return _data_cache['miner']
    try:
        req = urllib.request.Request(_POOL_API, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode('utf-8')
        obj = json.loads(text)
        _data_cache['miner'] = obj
        _data_cache['miner_ts'] = now
        return obj
    except Exception as e:
        print(f'[PEARL] fetch_miner_data error: {e}')
        return _data_cache['miner']


def fetch_pool_stats():
    """获取 Pool 全局数据（从 /api/stats）"""
    now = time.time()
    if _data_cache['pool'] is not None and (now - _data_cache['pool_ts']) < _DATA_TTL:
        return _data_cache['pool']
    try:
        req = urllib.request.Request(_POOL_STATS_API, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode('utf-8')
        obj = json.loads(text)
        _data_cache['pool'] = obj
        _data_cache['pool_ts'] = now
        return obj
    except Exception as e:
        print(f'[PEARL] fetch_pool_stats error: {e}')
        return _data_cache['pool']


def fetch_prl_price():
    now = time.time()
    if _data_cache['price'] is not None and (now - _data_cache['price_ts']) < _DATA_TTL:
        return _data_cache['price']
    
    # ── 从 prlscan 获取 PRL 价格（与 Pearl 官方 Dashboard 同源） ──────
    # Dashboard 显示 "$0.4095 via SafeTrade"，数据实际走 prlscan 的 safetrade 源
    try:
        url = 'https://api.prlscan.com/v1/market/prl'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode('utf-8')
        obj = json.loads(text)
        price = float(obj.get('price_usd', 0))
    except Exception as e:
        print(f'[PEARL] prlscan price error: {e}')
        price = None

    if price is not None and price > 0:
        _data_cache['price'] = price
        _data_cache['price_ts'] = now
    
    return _data_cache['price'] if _data_cache['price'] is not None else 0.0


# ─── 字体工具 ──────────────────────────────────────────────────────
def make_font(size=8):
    return ImageFont.truetype(_FONT_PATH, size)


# ─── 像素数字渲染（3×5 bitmap）─────────────────────────────────────
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
    '.': [0,0,0, 0,0,0, 0,0,0, 0,0,0, 1,0,0],
    '-': [0,0,0, 0,0,0, 1,1,1, 0,0,0, 0,0,0],
}


def draw_digit(draw, x, y, ch, color, scale=1):
    bits = _DIGIT_BITS.get(ch)
    if not bits:
        return
    for row in range(5):
        for col in range(3):
            if bits[row * 3 + col]:
                for sy in range(scale):
                    for sx in range(scale):
                        draw.point((x + col * scale + sx, y + row * scale + sy), fill=color)


def draw_number(draw, x, y, text, color, scale=1):
    """绘制数字字符串，小数点占2px，scale放大"""
    for ch in text:
        if ch == '.':
            draw.point((x, y + 3 * scale), fill=color)
            x += 2 * scale
        elif ch == '-':
            for sx in range(3 * scale):
                draw.point((x + sx, y + 2 * scale), fill=color)
            x += 4 * scale
        else:
            draw_digit(draw, x, y, ch, color, scale)
            x += 4 * scale


def number_width(text, scale=1):
    """计算数字字符串像素宽度"""
    w = 0
    for ch in text:
        if ch == '.':
            w += 2
        else:
            w += 4
    return w * scale


# ─── PRL 算力解析 ─────────────────────────────────────────────────
def parse_hashrate(s):
    """解析 '12.5 TH/s' -> (12.5, 'TH/s')"""
    if not s or s == '0 H/s':
        return 0.0, 'H/s'
    parts = s.strip().split()
    if len(parts) < 2:
        return 0.0, 'H/s'
    try:
        val = float(parts[0])
        unit = parts[1]
        return val, unit
    except:
        return 0.0, 'H/s'


def fmt_hashrate(val, unit):
    if val >= 1000 and unit == 'H/s':
        val /= 1000
        unit = 'KH/s'
    if val >= 1000 and unit == 'KH/s':
        val /= 1000
        unit = 'MH/s'
    if val >= 1000 and unit == 'MH/s':
        val /= 1000
        unit = 'GH/s'
    if val >= 1000 and unit == 'GH/s':
        val /= 1000
        unit = 'TH/s'
    return f'{val:.2f}', unit


# ─── 颜色主题 ──────────────────────────────────────────────────────
C = {
    'bg':       (5, 5, 18),
    'bg2':      (10, 10, 30),
    'pearl':    (255, 180, 220),   # 珍珠粉
    'pearl2':   (255, 220, 240),   # 浅粉高光
    'gold':     (255, 215, 0),
    'gold2':    (255, 255, 100),
    'cyan':     (0, 220, 255),
    'cyan2':    (100, 240, 255),
    'green': (50, 255, 150),
    'red':      (255, 80, 80),
    'white':    (255, 255, 255),
    'dim':      (100, 100, 140),
    'div':      (40, 40, 80),
    'panel':    (15, 10, 35),
    'glow':     (255, 200, 240),
}


# ─── PearlTheme ───────────────────────────────────────────────────
class PearlTheme:
    _panel = 0          # 当前面板索引
    _last_rotate = 0    # 上次轮换时间
    _miner_cache = {}
    _price_cache = 0.0

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self._f8 = make_font(8)
        self._f7 = make_font(7)
        self._f6 = make_font(6)

    def _t(self, d, x, y, text, color, font):
        try:
            d.text((x, y), text, fill=color, font=font)
        except:
            pass

    def _bg_gradient(self, d, t):
        """珍珠色渐变背景 + 微光呼吸"""
        phase = math.sin(t * 0.8) * 0.5 + 0.5
        for y in range(self.height):
            r = int(5 + y / self.height * 8 + phase * 3)
            g = int(5 + y / self.height * 4 + phase * 2)
            b = int(18 + y / self.height * 20 + phase * 8)
            d.rectangle([(0, y), (63, y)], fill=(min(255,r), min(255,g), min(255,b)))

    def _divider(self, d, y):
        d.line([(3, y), (61, y)], fill=C['div'], width=1)

    def _panel_header(self, d, label, y, color):
        """面板顶部标题栏"""
        d.rectangle([(2, y), (62, y + 9)], fill=color)
        self._t(d, 4, y + 1, label, C['bg'], self._f7)

    def _value_large(self, d, x, y, text, color, scale=2):
        """放大像素数字显示"""
        draw_number(d, x, y, text, color, scale=scale)

    def _value_small(self, d, x, y, text, color):
        """小字体文本显示"""
        self._t(d, x, y, text, color, self._f7)

    def _draw_worker_row(self, d, worker_list, t):
        """显示 workers 在线状态行（最多显示5个）"""
        active = [w for w in worker_list if w.get('online')]
        total = len(worker_list)
        active_count = len(active)
        
        # 显示: "Workers: 2/3" 形式
        label = f'{active_count}/{total}'
        
        # 颜色：全部在线=绿色，有离线=金色，全部离线=红色
        if active_count == total and total > 0:
            color = C['green']
        elif active_count > 0:
            color = C['gold2']
        else:
            color = C['red']
        
        self._t(d, 4, 28, 'Workers', C['dim'], self._f7)
        
        # 数字显示
        scale = 2
        label_str = label
        nw = number_width(label_str, scale=scale)
        start_x = max(0, (64 - nw) // 2 - 2)
        draw_number(d, start_x, 28, label_str, color, scale=scale)

    def _get_data(self):
        now = time.time()
        # 缓存为空 或 TTL 已过期时主动拉取
        if _data_cache.get('miner') is None or (now - _data_cache.get('miner_ts', 0)) >= _DATA_TTL:
            fetch_miner_data()
        if _data_cache.get('price') is None or (now - _data_cache.get('price_ts', 0)) >= _DATA_TTL:
            fetch_prl_price()
        if _data_cache.get('pool') is None or (now - _data_cache.get('pool_ts', 0)) >= _DATA_TTL:
            fetch_pool_stats()
        
        cache = _data_cache.get('miner') or {}
        
        # 检查是否有个人 miner 数据（API 直接返回的）
        workers_list = cache.get('workers', [])
        est_hash = cache.get('estHash1h', '')
        
        if workers_list or est_hash:
            # 使用个人 miner 数据（来自 API）
            workers = len(workers_list)
            total_paid = cache.get('total_paid_prl', 0.0)
            pending = cache.get('balance_prl', 0.0)
            
            # 解析 estHash1h 字符串如 "605.83 TH/s"
            if est_hash:
                parts = est_hash.strip().split()
                if len(parts) >= 2:
                    try:
                        h_val = float(parts[0])
                        h_unit = parts[1]
                    except:
                        h_val, h_unit = 0.0, 'TH/s'
                else:
                    h_val, h_unit = 0.0, 'TH/s'
            else:
                h_val, h_unit = 0.0, 'TH/s'
            
            h_str, h_unit = fmt_hashrate(h_val, h_unit)
            pool_price = _data_cache.get('price')
        else:
            # Fallback: 从 Python urllib 获取 pool 全局数据
            pool = fetch_pool_stats()
            price = fetch_prl_price()
            
            if pool is not None:
                pool_info = pool.get('pool', {})
                h_raw = pool_info.get('hashrate', '0 H/s')
                h_val, h_unit = parse_hashrate(h_raw)
                h_str, h_unit = fmt_hashrate(h_val, h_unit)
                workers = pool_info.get('workers', 0)
                pool_price = price
            else:
                h_str = '0'
                h_unit = 'EH/s'
                workers = 0
                pool_price = price
            
            total_paid = 0.0
            pending = 0.0
        
        return {
            'hashrate': h_str,
            'hashrate_unit': h_unit,
            'workers': workers,
            'workers_total': workers,
            'total_paid': total_paid,
            'pending': pending,
            'price': pool_price,
        }

    def generate_frame(self, status=None, t=None):
        if t is None:
            t = time.time()

        # 轮换面板
        elapsed = t - self._last_rotate
        if elapsed >= _PANEL_DURATION:
            self._panel = (self._panel + 1) % _NUM_PANELS
            self._last_rotate = t

        img = Image.new('RGB', (self.width, self.height), C['bg'])
        d = ImageDraw.Draw(img)

        self._bg_gradient(d, t)
        
        # 获取数据
        info = self._get_data()

        # ── 面板内容 ──────────────────────────────────────────────
        if self._panel == 0:
            self._panel_hashrate(d, info, t)
        elif self._panel == 1:
            self._panel_workers(d, info, t)
        elif self._panel == 2:
            self._panel_total_paid(d, info, t)
        elif self._panel == 3:
            self._panel_pending(d, info, t)
        elif self._panel == 4:
            self._panel_price(d, info, t)

        # ── 底部状态栏 ───────────────────────────────────────────
        self._status_bar(d, t)

        # ── 面板指示点 ───────────────────────────────────────────
        self._panel_indicators(d, t)

        return np.array(img)

    # ── 各面板 ────────────────────────────────────────────────────

    def _panel_hashrate(self, d, info, t):
        """算力面板"""
        self._divider(d, 10)
        self._divider(d, 38)
        self._panel_header(d, 'HASH RATE', 2, C['pearl'])
        
        # 算力值（大字）
        h_str = info['hashrate']
        h_unit = info['hashrate_unit']
        
        scale = 2
        nw = number_width(h_str, scale=scale)
        color = C['pearl2']
        start_x = max(1, (64 - nw) // 2)
        self._value_large(d, start_x, 14, h_str, color, scale=scale)
        
        # 单位
        self._t(d,4, 40, h_unit, C['cyan'], self._f7)
        
        # 时间戳
        self._t(d, 36, 40, datetime.now().strftime('%H:%M'), C['dim'], self._f7)

    def _panel_workers(self, d, info, t):
        """Workers 在线面板"""
        self._divider(d, 10)
        self._divider(d, 38)
        self._panel_header(d, 'WORKERS', 2, C['cyan'])
        
        workers = info['workers']
        
        # Pool 级别：直接显示 workers 数量（online = total）
        workers_str = f'{workers:,}' if workers >= 1000 else str(workers)
        scale = 2
        nw = number_width(workers_str, scale=scale)
        
        color = C['green'] if workers > 0 else C['red']
        start_x = max(1, (64 - nw) // 2)
        self._value_large(d, start_x, 14, workers_str, color, scale=scale)
        
        # POOL 标签
        label_color = C['green'] if workers > 0 else C['red']
        self._t(d, 4, 40, 'POOL', label_color, self._f7)
        self._t(d, 36, 40, datetime.now().strftime('%H:%M'), C['dim'], self._f7)

    def _panel_total_paid(self, d, info, t):
        """Total Paid PRL 面板"""
        self._divider(d, 10)
        self._divider(d, 38)
        self._panel_header(d, 'TOTAL PAID', 2, C['gold'])
        
        paid = info['total_paid']
        # PRL 保留2位小数
        if paid >= 1000:
            paid_str = f'{paid / 1000:.1f}K'
        else:
            paid_str = f'{paid:.2f}'
        
        scale = 2
        nw = number_width(paid_str, scale=scale)
        start_x = max(1, (64 - nw) // 2)
        self._value_large(d, start_x, 14, paid_str, C['gold2'], scale=scale)
        
        self._t(d, 4, 40, 'PRL', C['gold'], self._f7)
        self._t(d, 36, 40, datetime.now().strftime('%H:%M'), C['dim'], self._f7)

    def _panel_pending(self, d, info, t):
        """Pending Balance 面板"""
        self._divider(d, 10)
        self._divider(d, 38)
        self._panel_header(d, 'PENDING', 2, C['pearl'])
        
        pending = info['pending']
        if pending >= 1000:
            pending_str = f'{pending / 1000:.1f}K'
        elif pending >= 1:
            pending_str = f'{pending:.2f}'
        else:
            pending_str = f'{pending:.4f}'
        
        scale = 2
        nw = number_width(pending_str, scale=scale)
        start_x = max(1, (64 - nw) // 2)
        self._value_large(d, start_x, 14, pending_str, C['pearl2'], scale=scale)
        
        self._t(d, 4, 40, 'PRL', C['pearl'], self._f7)
        self._t(d, 36, 40, datetime.now().strftime('%H:%M'), C['dim'], self._f7)

    def _panel_price(self, d, info, t):
        """PRL 币价面板"""
        self._divider(d, 10)
        self._divider(d, 38)
        self._panel_header(d, 'PRL/USD', 2, C['green'])
        
        price = info['price']
        if price > 0:
            if price >= 1:
                price_str = f'{price:.4f}'
            else:
                price_str = f'{price:.6f}'
            color = C['green']
        else:
            price_str = 'N/A'
            color = C['dim']
        
        scale = 2
        nw = number_width(price_str, scale=scale)
        start_x = max(1, (64 - nw) // 2)
        self._value_large(d, start_x, 14, price_str, color, scale=scale)
        
        self._t(d, 4, 40, 'USD', C['green'], self._f7)
        
        # 更新倒计时
        fetch_ts = _data_cache.get('price_ts', 0)
        if fetch_ts > 0:
            remain = max(0, _DATA_TTL - (t - fetch_ts))
            self._t(d, 36, 40, f'{int(remain)}s', C['dim'], self._f7)
        else:
            self._t(d, 36, 40, '--', C['dim'], self._f7)

    # ── 底部状态栏 ────────────────────────────────────────────────
    def _status_bar(self, d, t):
        """底部状态栏: PEARL logo + 更新时间"""
        d.rectangle([(0, 56), (63, 63)], fill=C['panel'])
        
        # PEARL 文字
        phase = math.sin(t * 1.5) * 0.5 + 0.5
        r = int(255)
        g = int(180 + 40 * phase)
        b = int(220 - 20 * phase)
        self._t(d, 3, 57, 'PEARL', (r, g, b), self._f7)
        
        # 数据来源
        self._t(d, 36, 57, 'AlphaPool', C['dim'], self._f6)

    # ── 面板指示点 ────────────────────────────────────────────────
    def _panel_indicators(self, d, t):
        """底部5个指示点，标识当前面板"""
        dot_y = 54
        for i in range(_NUM_PANELS):
            cx = 8 + i * 10
            if i == self._panel:
                # 亮色呼吸
                phase = math.sin(t * 3) * 0.5 + 0.5
                brightness = int(200 + 55 * phase)
                color = (brightness, brightness, brightness)
                d.ellipse([(cx - 2, dot_y - 2), (cx + 2, dot_y + 2)], fill=color)
            else:
                d.ellipse([(cx - 2, dot_y - 2), (cx + 2, dot_y + 2)], fill=C['div'])


# ─── 测试入口 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(os.path.join(BASE_DIR, 'themes/test_frames'), exist_ok=True)
    from PIL import Image as Img

    theme = PearlTheme()
    
    print('Fetching data...')
    data = theme._get_data()
    print(f'Miner data: {data}')
    
    price = fetch_prl_price()
    print(f'PRL price: {price}')
    
    print('Generating5 panel frames...')
    for p in range(5):
        theme._panel = p
        theme._last_rotate = 0
        frame = theme.generate_frame(t=time.time() + p * 10)
        Img.fromarray(frame).save(fos.path.join(BASE_DIR, 'themes/test_frames/pearl_p{p}.png'))
    
    print('Done!')