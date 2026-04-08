#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雪花主题 - 华丽的雪花飘落效果
大小雪花错落，带飘动轨迹和微光效果
"""

import math
import random
import time
import numpy as np
from PIL import Image, ImageDraw

class SnowTheme:
    """
    雪花飘落主题
    - 多层视差：远/中/近三层雪花，不同大小和速度
    - 每片雪花有轻微水平摆动
    - 大雪花带对角线拖尾
    - 背景渐变：深夜蓝 → 浅蓝
    """

    MAX_SNOWFLAKES = 120

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.snowflakes = []
        self.t = 0.0

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()
        self.t = t

        # 背景：垂直渐变深夜蓝
        img = Image.new('RGB', (self.width, self.height), (3, 5, 20))
        draw = ImageDraw.Draw(img)

        # 绘制背景星星（随机闪烁）
        self._draw_stars(draw, t)

        # 生成/更新雪花
        self._update_snowflakes(t)

        # 绘制雪花（分两层：大雪花在上层先画，小雪花在下层后画）
        # 先画小雪花（远景）
        for s in self.snowflakes:
            if s['size'] < 2.5:
                self._draw_snowflake(draw, s)
        # 再画大雪花（近景，带拖尾）
        for s in self.snowflakes:
            if s['size'] >= 2.5:
                self._draw_snowflake(draw, s)

        return np.array(img)

    def _draw_stars(self, draw, t):
        """绘制闪烁的背景星星"""
        # 用 t 的小数部分做伪随机，保证星星位置固定但闪烁
        seed = int(t * 3)  # 每 ~333ms 切换闪烁状态
        for i in range(40):
            sx = (i * 7919 + 1) % self.width   # 伪随机 x
            sy = (i * 6271 + 1) % self.height  # 伪随机 y
            # 用 sin 产生闪烁效果
            flicker = 0.3 + 0.7 * (math.sin(t * 2 + i * 1.7) * 0.5 + 0.5)
            brightness = int(120 * flicker)
            draw.point((sx, sy), fill=(brightness, brightness + 10, brightness + 40))

    def _update_snowflakes(self, t):
        """更新所有雪花位置，补充新雪花"""
        dt = 1.0 / 15.0  # 假设 15 FPS

        for s in self.snowflakes[:]:
            # 垂直下落
            s['y'] += s['speed'] * dt * 15

            # 水平正弦摆动
            s['x'] += math.sin(t * s['wobble'] + s['phase']) * 0.4

            # 超出底部则移除
            if s['y'] > self.height + 4:
                self.snowflakes.remove(s)

        # 补充新雪花（从顶部或左右边缘飘入）
        target = self.MAX_SNOWFLAKES - len(self.snowflakes)
        for _ in range(target):
            self._spawn_snowflake( entering=True)

    def _spawn_snowflake(self, entering=False):
        """生成一片新雪花"""
        # 随机层：0=远(小慢)、1=中、2=近(大快)
        layer = random.choices([0, 1, 2], weights=[0.4, 0.4, 0.2])[0]

        size_map = {0: (0.8, 2.0), 1: (1.5, 2.8), 2: (2.5, 3.8)}
        speed_map = {0: (0.4, 0.8), 1: (0.9, 1.6), 2: (1.8, 2.8)}

        size = random.uniform(*size_map[layer])
        speed = random.uniform(*speed_map[layer])

        if entering:
            # 从顶部或左右侧进入
            edge = random.random()
            if edge < 0.75:
                x = random.uniform(0, self.width)
                y = -3
            elif edge < 0.85:
                x = -3
                y = random.uniform(0, self.height * 0.5)
            else:
                x = self.width + 3
                y = random.uniform(0, self.height * 0.5)
        else:
            x = random.uniform(0, self.width)
            y = random.uniform(-self.height, self.height)

        self.snowflakes.append({
            'x': x,
            'y': y,
            'size': size,
            'speed': speed,
            'wobble': random.uniform(0.8, 2.2),
            'phase': random.uniform(0, math.pi * 2),
            'layer': layer,
        })

    def _draw_snowflake(self, draw, s):
        """绘制单片雪花（带发光效果）"""
        x, y = int(s['x']), int(s['y'])
        size = s['size']
        brightness = int(180 + size * 20)

        # 远近颜色：远景偏蓝灰，近景偏白亮
        layer = s['layer']
        if layer == 0:
            color = (brightness // 3, brightness // 3 + 10, brightness + 20)
        elif layer == 1:
            color = (brightness // 2, brightness // 2 + 15, brightness + 35)
        else:
            color = (brightness, brightness, brightness + 20)

        r, g, b = color

        # 大雪花带对角线拖尾（近景雪花）
        if size >= 2.5 and layer == 2:
            for trail_y, trail_x in [
                (1, 0), (2, 0), (3, 1),
                (1, -1), (2, -1), (3, -1)
            ]:
                tx, ty = x + trail_x, y + trail_y
                if 0 <= tx < self.width and 0 <= ty < self.height:
                    alpha = (6 - abs(trail_y)) / 6.0
                    ta = int(r * alpha * 0.5), int(g * alpha * 0.5), int(b * alpha * 0.4)
                    draw.point((tx, ty), fill=ta)

        # 雪花主体
        if size >= 2.0:
            # 较大雪花：画 3x3 或 5x5 光晕
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        dist = abs(dx) + abs(dy)
                        if dist == 0:
                            draw.point((nx, ny), fill=(r, g, b))
                        elif dist == 1:
                            draw.point((nx, ny), fill=(r // 2, g // 2, b // 2))
        else:
            # 小雪花：单像素
            if 0 <= x < self.width and 0 <= y < self.height:
                draw.point((x, y), fill=(r // 2, g // 2, b // 2))


if __name__ == '__main__':
    snow = SnowTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(24):
        t = i * 0.12
        frame = snow.generate_frame(t=t)
        from PIL import Image
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/snow_{i:02d}.png')
    print("Saved 24 frames")
