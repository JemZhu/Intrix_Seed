#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
烟花主题 - 华丽的 LED 矩阵烟花表演
粒子物理引擎 + 彩虹爆炸 + 火箭尾焰
"""

import math
import random
import time
import numpy as np
from PIL import Image, ImageDraw

class FireworksTheme:
    """烟花主题：支持多烟花同时发射、粒子爆炸、重力衰减、彩虹色彩"""

    GRAVITY = 0.06
    TRAIL_LENGTH = 12
    MAX_PARTICLES = 200
    MAX_ROCKETS = 4

    # 彩虹色板
    PALETTES = [
        # 热烈红橙黄
        [(255, 60, 20), (255, 140, 0), (255, 220, 0), (255, 255, 100)],
        # 浪漫粉紫
        [(255, 50, 120), (200, 50, 255), (120, 80, 255), (255, 150, 255)],
        # 清新蓝绿
        [(0, 200, 255), (0, 255, 180), (50, 255, 100), (200, 255, 50)],
        # 金色庆典
        [(255, 215, 0), (255, 190, 50), (255, 170, 0), (255, 255, 150)],
        # 冰蓝白
        [(150, 200, 255), (200, 230, 255), (255, 255, 255), (100, 180, 255)],
    ]

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.rockets = []    # 正在升空的火箭
        self.particles = []  # 爆炸后的粒子
        self.trails = []     # 尾焰轨迹
        self.t = 0.0
        self.next_launch = 0.0
        self.launch_interval = 0.6  # 每隔多久发射一个

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()
        self.t = t

        img = Image.new('RGB', (self.width, self.height), (0, 0, 5))
        draw = ImageDraw.Draw(img)

        # 发射新火箭
        if t >= self.next_launch and len(self.rockets) < self.MAX_ROCKETS:
            self._launch_rocket()
            self.next_launch = t + self.launch_interval + random.uniform(-0.1, 0.3)

        # 偶尔双发
        if random.random() < 0.02 and len(self.rockets) < self.MAX_ROCKETS - 1:
            self._launch_rocket()

        # 更新并绘制火箭
        for rocket in self.rockets[:]:
            rocket['y'] -= rocket['vy']
            rocket['vy'] -= 0.01  # 减速
            rocket['x'] += random.uniform(-0.3, 0.3)
            rocket['age'] += 1

            # 添加尾焰
            self.trails.append({
                'x': rocket['x'] + random.uniform(-1, 1),
                'y': rocket['y'] + random.uniform(0, 3),
                'life': 1.0,
                'decay': 0.15,
                'color': (255, 150, 50),
                'size': random.uniform(1.5, 2.5),
            })

            # 到达最高点或超时报废
            if rocket['vy'] <= 0.1 or rocket['y'] < 8 or rocket['age'] > 80:
                self._explode(rocket)
                self.rockets.remove(rocket)

        # 更新并绘制粒子
        for p in self.particles[:]:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += self.GRAVITY
            p['life'] -= p['decay']
            p['size'] = max(0.5, p['size'] - 0.02)

            if p['life'] <= 0:
                self.particles.remove(p)
                continue

            # 绘制粒子（带辉光）
            self._draw_glow_pixel(draw, int(p['x']), int(p['y']), p['color'], p['life'], p['size'])

        # 绘制尾焰轨迹
        for trail in self.trails[:]:
            trail['y'] += 1.5  # 尾焰下落
            trail['life'] -= trail['decay']
            if trail['life'] <= 0:
                self.trails.remove(trail)
                continue
            alpha = trail['life']
            c = trail['color']
            col = (int(c[0] * alpha), int(c[1] * alpha * 0.6), int(c[2] * alpha * 0.2))
            size = int(trail['size'])
            x, y = int(trail['x']), int(trail['y'])
            if 0 <= x < self.width and 0 <= y < self.height:
                draw.ellipse([x - size, y - size, x + size, y + size], fill=col)

        return np.array(img)

    def _launch_rocket(self):
        """发射一枚火箭"""
        palette = random.choice(self.PALETTES)
        self.rockets.append({
            'x': random.randint(8, self.width - 8),
            'y': self.height - 2,
            'vy': random.uniform(3.5, 5.5),  # 上升速度
            'color': palette,
            'age': 0,
        })

    def _explode(self, rocket):
        """烟花爆炸，产生大量粒子"""
        palette = rocket['color']
        cx, cy = rocket['x'], rocket['y']
        count = random.randint(50, 80)

        # 决定爆炸类型
        style = random.choice(['sphere', 'ring', 'heart', 'double'])

        for i in range(count):
            angle = (i / count) * 2 * math.pi
            if style == 'sphere':
                speed = random.uniform(1.5, 3.5)
            elif style == 'ring':
                speed = random.uniform(2.5, 3.0)
                angle += random.uniform(-0.1, 0.1)
            elif style == 'heart':
                # 心形分布
                t_angle = angle
                speed = random.uniform(1.5, 3.0) * (1 + 0.5 * math.sin(t_angle * 2))
            else:  # double
                speed = random.uniform(1.5, 3.5)
                if i % 2 == 0:
                    angle += 0.2

            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed

            color = random.choice(palette)
            # 部分粒子白色闪烁
            if random.random() < 0.1:
                color = (255, 255, 255)

            self.particles.append({
                'x': cx,
                'y': cy,
                'vx': vx,
                'vy': vy,
                'life': 1.0,
                'decay': random.uniform(0.012, 0.025),
                'color': color,
                'size': random.uniform(1.0, 2.2),
            })

    def _draw_glow_pixel(self, draw, x, y, color, alpha, size=1.0):
        """绘制带辉光的像素点"""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        alpha = max(0.0, min(1.0, alpha))
        r = int(color[0] * alpha)
        g = int(color[1] * alpha)
        b = int(color[2] * alpha)
        s = max(1, int(size))

        # 主点
        draw.ellipse([x - s, y - s, x + s, y + s], fill=(r, g, b))
        # 辉光（周围4点较暗）
        glow_colors = [
            (int(r * 0.5), int(g * 0.5), int(b * 0.5)),
            (int(r * 0.3), int(g * 0.3), int(b * 0.3)),
        ]
        for dx, dy, ci in [(-1,0,0), (1,0,0), (0,-1,0), (0,1,0), (-1,-1,0), (1,1,0), (-1,1,0), (1,-1,0)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                gc = glow_colors[0] if abs(dx) + abs(dy) == 1 else glow_colors[1]
                draw.point((nx, ny), fill=gc)


if __name__ == '__main__':
    # 测试：生成10帧保存
    fw = FireworksTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(10):
        t = i * 0.15
        frame = fw.generate_frame(t=t)
        from PIL import Image
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/fw_{i:02d}.png')
    print("Saved 10 frames to themes/test_frames/")
