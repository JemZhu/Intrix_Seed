#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kitten Theme - 可爱的像素小猫动画主题
从 server.py 提取的小猫显示逻辑，独立成主题文件
"""

import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime


class KittenTheme:
    """小猫主题 - 64x64 LED 矩阵显示"""

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

        # 调色板
        self.COLORS = {
            'bg': (5, 5, 15),
            'body': (255, 140, 150),       # 粉色猫身
            'body_light': (255, 200, 200), # 高光
            'body_dark': (200, 100, 100),  # 暗部
            'eye': (50, 200, 100),          # 绿色眼睛（空闲）
            'eye_busy': (255, 80, 80),      # 红色眼睛（忙碌）
            'nose': (255, 150, 150),        # 鼻子
            'mouth': (200, 100, 100),       # 嘴巴
            'whisker': (200, 200, 200),     # 胡须
            'inner_ear': (255, 180, 180),  # 耳朵内侧
            'paw': (255, 180, 180),         # 爪子
            'blush': (255, 180, 180, 100),  # 腮红
            'status_green': (0, 255, 150),
            'status_yellow': (255, 220, 0),
            'status_red': (255, 80, 80),
            'bar_bg': (20, 20, 35),
            'text_dim': (150, 150, 180),
            'text_bright': (255, 255, 255),
            'chart_line': (0, 200, 255),
        }

        self.anim_frame = 0
        self._history = []
        self._history_maxlen = 30

    def generate_frame(self, status: dict = None, t: float = None) -> np.ndarray:
        """
        生成一帧小猫主题画面
        
        Args:
            status: OpenClaw 状态字典，包含 is_busy, memory_usage, cpu_load, last_message
            t: 当前时间戳（用于动画），如果为 None 则自动获取
        """
        import time
        if t is None:
            t = time.time()
            
        if status is None:
            status = {
                'is_busy': False,
                'memory_usage': 0.5,
                'cpu_load': 0.3,
                'last_message': 'Kitten Mode',
            }

        self.anim_frame += 1

        img = Image.new('RGB', (self.width, self.height), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        # 记录历史
        if len(self._history) >= self._history_maxlen:
            self._history.pop(0)
        self._history.append({
            'memory': status.get('memory_usage', 0),
            'cpu': status.get('cpu_load', 0),
        })

        # 左上角：天气信息
        self._draw_weather(draw, status)

        # 右上角：缩小的像素小猫
        self._draw_cat(draw, t, status, ox=30, oy=0, scale=0.8)

        # 状态条下移（小猫在右上角，状态条左侧不受影响）
        self._draw_status_bar(draw, status, t)

        # 绘制底部滚动消息
        self._draw_message_bar(draw, status, t)

        return np.array(img)

    def _draw_cat(self, draw: ImageDraw, t: float, status: dict, ox: int = 0, oy: int = 0, scale: float = 1.0):
        """绘制像素小猫（支持偏移和缩放）"""
        def p(x, y):
            sx = int(round(ox + x * scale))
            sy = int(round(oy + y * scale))
            return (sx, sy)

        def dot(x, y, fill):
            sx, sy = p(x, y)
            draw.rectangle([sx, sy, sx, sy], fill=fill)

        def ll(x1, y1, x2, y2, fill, lw=None):
            """画线（缩放后）"""
            x1s, y1s = p(x1, y1)
            x2s, y2s = p(x2, y2)
            w = lw if lw else max(1, int(round(scale)))
            draw.line([(x1s, y1s), (x2s, y2s)], fill=fill, width=w)

        def el(x1, y1, x2, y2, fill):
            x1s, y1s = p(x1, y1)
            x2s, y2s = p(x2, y2)
            draw.ellipse([x1s, y1s, x2s, y2s], fill=fill)

        def poly(pts, fill):
            draw.polygon([p(x, y) for x, y in pts], fill=fill)

        cx, cy = 32, 16
        bounce = scale * int(round(2 * np.sin(t * 4)))
        breathe = (np.sin(t * 2) + 1) / 2
        ear_phase = int(round(t * 3)) % 2

        if status.get('is_busy', False):
            hue = (t * 0.3) % 1.0
            body_color = self._hsv_to_rgb(hue, 0.6, 1.0)
            eye_color = self.COLORS['eye_busy']
        else:
            body_color = self.COLORS['body']
            eye_color = self.COLORS['eye']

        offset_y = bounce

        # 尾巴
        tail_y = cy + 10 + offset_y
        tail_sway = int(3 * np.sin(t * 6))
        for i in range(5):
            ty = tail_y + i
            tx = cx + 4 + int(tail_sway * (i // 3))
            dot(tx, ty, body_color)

        # 身体
        body_top = cy - 2 + offset_y
        body_bottom = cy + 10 + offset_y
        body_left = cx - 6
        body_right = cx + 6
        body_scale = int(breathe)
        el(body_left - body_scale, body_top, body_right + body_scale, body_bottom, body_color)
        el(body_left + 1, body_top + 1, body_left + 3, body_top + 3, self.COLORS['body_light'])

        # 头部
        head_top = body_top - 8
        head_bottom = head_top + 8
        head_left = cx - 7
        head_right = cx + 7
        el(head_left, head_top, head_right, head_bottom, body_color)

        # 耳朵
        ear_wiggle = ear_phase * 2 - 1
        poly([(head_left + 1, head_top + 1), (head_left - 1 + ear_wiggle, head_top - 5), (head_left + 4, head_top)], body_color)
        poly([(head_left + 1, head_top + 1), (head_left + ear_wiggle, head_top - 3), (head_left + 3, head_top)], self.COLORS['inner_ear'])
        poly([(head_right - 1, head_top + 1), (head_right + 1 - ear_wiggle, head_top - 5), (head_right - 4, head_top)], body_color)
        poly([(head_right - 1, head_top + 1), (head_right - ear_wiggle, head_top - 3), (head_right - 3, head_top)], self.COLORS['inner_ear'])

        # 眼睛
        eye_blink = int(t * 2) % 8 == 0
        eye_y = head_top + 4
        lw = max(1, int(round(scale)))
        if not eye_blink:
            el(cx - 5, eye_y, cx - 2, eye_y + 3, eye_color)
            el(cx - 5, eye_y, cx - 4, eye_y + 1, (255, 255, 255))
            el(cx + 2, eye_y, cx + 5, eye_y + 3, eye_color)
            el(cx + 2, eye_y, cx + 3, eye_y + 1, (255, 255, 255))
        else:
            ll(cx - 5, eye_y + 1, cx - 2, eye_y + 1, eye_color, lw)
            ll(cx + 2, eye_y + 1, cx + 5, eye_y + 1, eye_color, lw)

        # 鼻子和嘴巴
        nose_y = eye_y + 4
        poly([(cx - 1, nose_y), (cx + 1, nose_y), (cx, nose_y + 2)], self.COLORS['nose'])
        ll(cx, nose_y + 2, cx - 2, nose_y + 4, self.COLORS['mouth'], lw)
        ll(cx, nose_y + 2, cx + 2, nose_y + 4, self.COLORS['mouth'], lw)

        # 胡须
        whisker_y = nose_y + 1
        ll(cx - 3, whisker_y, cx - 8, whisker_y - 1, self.COLORS['whisker'], lw)
        ll(cx - 3, whisker_y + 1, cx - 8, whisker_y + 1, self.COLORS['whisker'], lw)
        ll(cx - 3, whisker_y + 2, cx - 8, whisker_y + 3, self.COLORS['whisker'], lw)
        ll(cx + 3, whisker_y, cx + 8, whisker_y - 1, self.COLORS['whisker'], lw)
        ll(cx + 3, whisker_y + 1, cx + 8, whisker_y + 1, self.COLORS['whisker'], lw)
        ll(cx + 3, whisker_y + 2, cx + 8, whisker_y + 3, self.COLORS['whisker'], lw)

        # 前爪
        paw_y = body_bottom - 2
        el(body_left, paw_y, body_left + 3, paw_y + 3, body_color)
        el(body_left, paw_y + 3, body_left + 3, paw_y + 4, self.COLORS['paw'])
        el(body_right - 3, paw_y, body_right, paw_y + 3, body_color)
        el(body_right - 3, paw_y + 3, body_right, paw_y + 4, self.COLORS['paw'])

        # 腮红（空闲时）
        if not status.get('is_busy', False) and int(t * 3) % 4 == 0:
            el(cx - 6, eye_y + 1, cx - 4, eye_y + 3, (255, 180, 180))

    def _draw_weather(self, draw: ImageDraw, status: dict):
        """绘制天气信息 - 左上角"""
        weather = status.get('weather', {})
        if not weather:
            return

        temp = weather.get('temp', '--')
        code = weather.get('code', 0)

        # 温度
        temp_str = f"{temp}"
        x = 2
        for ch in temp_str:
            if ch.isdigit() or ch == '-':
                self._draw_text_3x5(draw, x, 1, ch, (100, 200, 255))
            x += 5
        # 度符号
        draw.ellipse([x + 2, 2, x + 4, 4], fill=(100, 200, 255))
        x += 7

        # 天气图标
        icon_y = 10
        icon_x = 2
        if code in [113]:
            # 太阳
            draw.ellipse([icon_x + 2, icon_y + 1, icon_x + 6, icon_y + 5], fill=(255, 220, 50))
            draw.ellipse([icon_x + 4, icon_y - 1, icon_x + 4, icon_y - 1], fill=(255, 220, 50))
        elif code in [116, 119]:
            # 云
            draw.ellipse([icon_x + 1, icon_y + 2, icon_x + 7, icon_y + 5], fill=(180, 180, 200))
            draw.ellipse([icon_x + 3, icon_y + 1, icon_x + 6, icon_y + 4], fill=(200, 200, 220))
        elif code in [296, 299, 389]:
            # 雨云
            draw.ellipse([icon_x + 1, icon_y + 1, icon_x + 7, icon_y + 4], fill=(120, 120, 160))
            draw.rectangle([icon_x + 2, icon_y + 5, icon_x + 2, icon_y + 5], fill=(80, 150, 255))
            draw.rectangle([icon_x + 4, icon_y + 6, icon_x + 4, icon_y + 6], fill=(80, 150, 255))
            draw.rectangle([icon_x + 6, icon_y + 5, icon_x + 6, icon_y + 5], fill=(80, 150, 255))
        else:
            # 默认
            draw.ellipse([icon_x + 2, icon_y + 2, icon_x + 6, icon_y + 5], fill=(150, 150, 170))

    def _draw_status_bar(self, draw: ImageDraw, status: dict, t: float):
        """绘制状态条 - 左侧 MEM/CPU，右侧时间"""
        y_start = 30

        # === 左侧：资源使用率 ===
        bar_x = 2
        bar_width = 28
        bar_height = 5

        # MEM
        mem_pct = max(0, min(1, status.get('memory_usage', 0)))
        mem_color = self._get_usage_color(mem_pct)
        self._draw_text_3x5(draw, bar_x, y_start, "MEM", self.COLORS['text_dim'])
        self._draw_bar(draw, bar_x + 12, y_start + 1, bar_width - 12, bar_height, mem_pct, mem_color)

        # CPU
        cpu_y = y_start + 9
        cpu_pct = max(0, min(1, status.get('cpu_load', 0)))
        cpu_color = self._get_usage_color(cpu_pct)
        self._draw_text_3x5(draw, bar_x, cpu_y, "CPU", self.COLORS['text_dim'])
        self._draw_bar(draw, bar_x + 12, cpu_y + 1, bar_width - 12, bar_height, cpu_pct, cpu_color)

        # === 右侧：日期时间 ===
        right_x = 40
        now = datetime.now()

        # 月.日 (纯白色)
        month_str = f"{now.month:02d}"
        day_str = f"{now.day:02d}"
        self._draw_text_3x5(draw, right_x, y_start, month_str, (255, 255, 255))
        draw.rectangle([right_x + 8, y_start + 2, right_x + 9, y_start + 2], fill=(255, 255, 255))
        self._draw_text_3x5(draw, right_x + 10, y_start, day_str, (255, 255, 255))

        # 星期 (周一至五白色，周六日红色)
        weekdays = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        day_abbr = weekdays[now.weekday()]
        is_weekend = now.weekday() >= 5
        day_color = (255, 80, 80) if is_weekend else (255, 255, 255)
        self._draw_text_3x5(draw, right_x + 2, y_start + 7, day_abbr, day_color)

        # 时间
        time_y = y_start + 13
        current_time = datetime.now().strftime("%H%M")
        self._draw_text_3x5(draw, right_x, time_y, current_time[:2], self.COLORS['text_bright'])
        if int(t * 2) % 2 == 0:
            draw.rectangle([right_x + 14, time_y + 1, right_x + 15, time_y + 1], fill=self.COLORS['text_bright'])
            draw.rectangle([right_x + 14, time_y + 3, right_x + 15, time_y + 3], fill=self.COLORS['text_bright'])
        self._draw_text_3x5(draw, right_x + 17, time_y, current_time[2:], self.COLORS['text_bright'])

    def _draw_message_bar(self, draw: ImageDraw, status: dict, t: float):
        """绘制底部滚动消息栏 - 分色渲染：Token绿色，$金色，状态白色"""
        msg_y = 51

        draw.rectangle([0, msg_y, 63, msg_y + 12], fill=(5, 5, 15))
        draw.line([(0, msg_y), (63, msg_y)], fill=(50, 50, 80), width=1)

        # 颜色定义
        COLOR_GREEN = (0, 255, 120)    # Token 数字
        COLOR_GOLD = (255, 200, 50)    # $ 符号
        COLOR_WHITE = (255, 255, 255)  # 状态文字

        # 构建分色字符列表: (char, color)
        segments = []

        token_usage = status.get('token_usage')
        if token_usage:
            total = token_usage.get('total_tokens', 0)
            cost = token_usage.get('total_cost', 0)
            if total >= 1000000:
                token_str = f"T:{total/1000000:.2f}M"
            elif total >= 1000:
                token_str = f"T:{total/1000:.1f}K"
            else:
                token_str = f"T:{total}"
            cost_str = f"${cost:.3f}" if cost else ""

            # Token 部分: T: 绿色，数字 绿色
            for ch in token_str:
                segments.append((ch, COLOR_GREEN))
            # $ 符号: 金色
            if cost_str.startswith('$'):
                for ch in cost_str:
                    segments.append((ch, COLOR_GOLD))
            else:
                for ch in cost_str:
                    segments.append((ch, COLOR_GOLD))

        last_msg = status.get('last_message', '') or ""
        if last_msg:
            if segments:
                segments.append((' ', COLOR_WHITE))
            for ch in last_msg:
                segments.append((ch, COLOR_WHITE))

        if not segments:
            segments = [('K', COLOR_WHITE), ('i', COLOR_WHITE), ('t', COLOR_WHITE), ('t', COLOR_WHITE), ('e', COLOR_WHITE), ('n', COLOR_WHITE)]

        # 计算滚动位置
        # 估算总像素宽度：中文12像素，ASCII 8像素
        def char_width(ch):
            return 12 if ord(ch) > 127 else 8
        total_width = sum(char_width(ch) + 6 for ch, _ in segments)  # stride = char_width + 6
        stride = 14
        scroll_pos = int(t * 10) % (total_width + 64)
        x = 64 - scroll_pos

        for char, color in segments:
            w = char_width(char)
            if x < -w or x > 64:
                x += stride
                continue
            if ord(char) > 127:
                self._draw_hzk12_char(draw, x, msg_y + 1, char, color)
            else:
                self._draw_text_12(draw, x, msg_y + 1, char, color)
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
        """绘制 12像素高的ASCII字符（8宽，配合HZK12中文字体）"""
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
            'a': [0x3c,0x7e,0x03,0x03,0x0f,0x7f,0xc1,0xc3,0x83,0xc3,0xfd,0x39],
            'b': [0xb0,0xc8,0x84,0x84,0x84,0x84,0x84,0x84,0xc8,0xb0,0x80,0x80],
            'c': [0x1e,0x3f,0x60,0xc0,0xc0,0xc0,0xc0,0xc0,0x60,0x3f,0x1e,0x00],
            'd': [0x34,0x4c,0x84,0x84,0x84,0x84,0x84,0x84,0x4c,0x34,0x04,0x04],
            'e': [0x1c,0x7e,0x43,0xc1,0x81,0xff,0xff,0x80,0xc0,0x40,0x7f,0x1c],
            'f': [0x1c,0x20,0x20,0xfc,0xfc,0x20,0x20,0x20,0x20,0x20,0x20,0x20],
            'g': [0x34,0x4c,0x84,0x84,0x84,0x84,0xc4,0x4c,0x34,0x04,0x48,0x78],
            'h': [0x98,0xcc,0x84,0x84,0x84,0x84,0x84,0x84,0x84,0x84,0x84,0x84],
            'i': [0x10,0x10,0x70,0x70,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0xfc],
            'j': [0x20,0x20,0x60,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0xc0,0x78],
            'k': [0x80,0x80,0x84,0x88,0x90,0xa0,0xd0,0x98,0x88,0x8c,0x86,0x83],
            'l': [0xe0,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0x30,0x1c],
            'm': [0xb6,0xf7,0x99,0x99,0x99,0x99,0x99,0x99,0x99,0x99,0x99,0x99],
            'n': [0x9c,0xbe,0xc3,0xc3,0xc3,0x83,0x83,0x83,0x83,0x83,0x83,0x83],
            'o': [0x3c,0x7e,0xc3,0xc3,0xc3,0xc1,0xc1,0xc3,0xc3,0xc3,0x7e,0x3c],
            'p': [0xb0,0xc8,0x84,0x84,0x84,0x84,0x84,0xc8,0xb0,0x80,0x80,0x80],
            'q': [0x34,0x4c,0x84,0x84,0x84,0x84,0x84,0x4c,0x74,0x04,0x04,0x04],
            'r': [0xce,0xff,0xe0,0xc0,0xc0,0xc0,0xc0,0xc0,0xc0,0xc0,0xc0,0xc0],
            's': [0x3c,0x7e,0xc0,0xc0,0xc0,0x7c,0x1e,0x03,0x03,0x03,0xfe,0x38],
            't': [0x30,0x30,0x30,0xfe,0x30,0x30,0x30,0x30,0x30,0x30,0x10,0x1e],
            'u': [0x83,0x83,0x83,0x83,0x83,0x83,0x83,0x83,0xc3,0xc3,0x7f,0x3b],
            'v': [0x81,0xc3,0x42,0x42,0x42,0x66,0x24,0x24,0x2c,0x3c,0x18,0x18],
            'w': [0x81,0x81,0x83,0x82,0x5a,0x5a,0x5a,0x4a,0x42,0x62,0x64,0x24],
            'x': [0xc3,0x42,0x24,0x24,0x18,0x18,0x18,0x3c,0x24,0x66,0x42,0xc3],
            'y': [0x82,0xc6,0x44,0x44,0x6c,0x28,0x28,0x10,0x10,0x10,0x20,0x60],
            'z': [0xff,0xff,0x02,0x06,0x0c,0x18,0x18,0x30,0x60,0x40,0xff,0xff],
            '$': [0x20,0x20,0xa0,0xa0,0xa0,0x70,0x28,0x28,0x28,0xf0,0x20,0x20],
            ':': [0x00,0x00,0x00,0x00,0x00,0x30,0x30,0x00,0x00,0x00,0x30,0x30],
            '.': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x30,0x30],
            '+': [0x18,0x18,0x18,0x18,0x18,0xff,0xff,0x18,0x18,0x18,0x18,0x18],
            '-': [0xff,0xff,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff],
            '/': [0x04,0x08,0x08,0x18,0x10,0x10,0x20,0x20,0x40,0x40,0xc0,0x80],
            '=': [0xff,0xff,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff,0x00],
            '!': [0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x00,0x00,0x80,0x80],
            ' ': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        }

        if char not in font_12:
            return

        bitmap = font_12[char]
        for row in range(12):
            bits = bitmap[row]
            for col in range(8):
                if bits & (0x80 >> col):
                    draw.rectangle([x + col, y + row, x + col, y + row], fill=color)

    def _draw_bar(self, draw: ImageDraw, x, y, width, height, pct, color):
        """绘制进度条"""
        draw.rectangle([x, y, x + width, y + height], fill=self.COLORS['bar_bg'])
        fill_w = max(1, int(width * pct))
        draw.rectangle([x, y, x + fill_w, y + height], fill=color)
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

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple:
        """HSV 转 RGB"""
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


# 独立测试
if __name__ == '__main__':
    import time
    theme = KittenTheme()
    
    print("🧪 测试 Kitten Theme...")
    print("生成 10 帧测试图像到 /home/jem/Intrix_Seed/themes/test_frames/")

    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)

    for i in range(10):
        frame = theme.generate_frame({
            'is_busy': i % 3 == 0,
            'memory_usage': 0.3 + (i % 5) * 0.1,
            'cpu_load': 0.2 + (i % 4) * 0.15,
            'last_message': 'Kitten!'
        }, t=time.time() + i * 0.1)
        
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/frame_{i:02d}.png')
        print(f"  帧 {i:02d} 已保存")

    print("✅ 测试完成！")
