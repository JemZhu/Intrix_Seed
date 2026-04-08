#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹跳球主题 - 无重力恒速版
球以恒定速度运动，碰边/碰球反弹，速度不减
"""

import math
import random
import numpy as np
from PIL import Image, ImageDraw


class BounceTheme:
    """
    无重力弹跳：
    - 无重力，速度大小恒定
    - 碰地面/天花板/墙壁反弹（速度反向）
    - 球间碰撞反弹
    - squash 落地时轻微压扁
    """

    BALL_COUNT = 3
    SPEED = 2.5  # 恒定速度大小

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.colors = [
            (255, 55, 55),
            (55, 180, 255),
            (255, 220, 55),
            (255, 100, 255),
            (255, 140, 55),
            (100, 255, 130),
        ]
        self.balls = []
        self._spawn_all()

    def _spawn_all(self):
        self.balls = [self._make_ball(i) for i in range(self.BALL_COUNT)]

    def _make_ball(self, idx=-1):
        i = idx if idx >= 0 else random.randint(0, len(self.colors)-1)
        w, h = self.width, self.height
        r = random.randint(5, 8)
        # 随机方向（单位向量）
        angle = random.uniform(0, 2 * math.pi)
        vx = math.cos(angle) * self.SPEED
        vy = math.sin(angle) * self.SPEED  # 向上 vy < 0
        return dict(
            x=random.randint(r + 4, w - r - 4),
            y=random.randint(r + 4, int(h * 0.75) - r),
            vx=vx,
            vy=vy,
            r=r,
            color=self.colors[i % len(self.colors)],
            squash=1.0,
            was_ground=False,
        )

    def _bounce_edge(self, ball, w, h, ground):
        """处理边缘反弹，返回是否碰过地面"""
        r = ball['r']
        touched = False

        # 左右墙
        if ball['x'] - r <= 0:
            ball['x'] = r
            ball['vx'] = abs(ball['vx'])
            touched = True
        if ball['x'] + r >= w:
            ball['x'] = w - r
            ball['vx'] = -abs(ball['vx'])
            touched = True

        # 天花板
        if ball['y'] - r <= 0:
            ball['y'] = r
            ball['vy'] = abs(ball['vy'])
            touched = True

        # 地面
        if ball['y'] + r >= ground:
            ball['y'] = ground - r
            ball['vy'] = -abs(ball['vy'])
            touched = True

        return touched

    def _collide_balls(self):
        """球间碰撞检测"""
        balls = self.balls
        for i in range(len(balls)):
            for j in range(i + 1, len(balls)):
                a, b = balls[i], balls[j]
                dx = b['x'] - a['x']
                dy = b['y'] - a['y']
                dist = math.sqrt(dx**2 + dy**2)
                min_d = a['r'] + b['r']
                if dist < min_d and dist > 0.001:
                    # 法向量
                    nx, ny = dx / dist, dy / dist
                    # 相对速度
                    dvx = a['vx'] - b['vx']
                    dvy = a['vy'] - b['vy']
                    dvn = dvx * nx + dvy * ny
                    # 只处理相向运动
                    if dvn > 0:
                        # 反弹：交换速度分量（等质量弹性碰撞）
                        a['vx'] -= dvn * nx
                        a['vy'] -= dvn * ny
                        b['vx'] += dvn * nx
                        b['vy'] += dvn * ny
                        # 分离
                        overlap = (min_d - dist) * 0.5
                        a['x'] -= nx * overlap
                        a['y'] -= ny * overlap
                        b['x'] += nx * overlap
                        b['y'] += ny * overlap

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        w, h = self.width, self.height
        ground = int(h * 0.85)

        img = Image.new('RGB', (w, h), (8, 10, 22))
        draw = ImageDraw.Draw(img)

        # 地面
        for gy in range(ground, h):
            a = (gy - ground) / max(1, h - ground)
            sh = int(8 + a * 20)
            draw.rectangle([(0, gy), (w-1, gy)], fill=(sh, sh+2, sh+10))
        draw.rectangle([(0, ground), (w-1, ground)], fill=(25, 30, 55))

        for ball in self.balls:
            # 移动
            ball['x'] += ball['vx']
            ball['y'] += ball['vy']

            # squash 恢复
            if ball['squash'] != 1.0:
                ball['squash'] += (1.0 - ball['squash']) * 0.25

            # 边缘反弹
            touched = self._bounce_edge(ball, w, h, ground)
            if touched and ball['vy'] < 0:  # 碰地面且正在向上
                ball['squash'] = 0.75

        # 球间碰撞
        self._collide_balls()

        for ball in self.balls:
            r = ball['r']
            cr, cg, cb = ball['color']
            rx = max(1, int(r * (2.0 - ball['squash'])))
            ry = max(1, int(r * ball['squash']))
            cx, cy = int(ball['x']), int(ball['y'])
            x0, x1 = max(0, cx - rx), min(w, cx + rx + 1)
            y0, y1 = max(0, cy - ry), min(h, cy + ry + 1)
            if x1 > x0 and y1 > y0:
                draw.ellipse([x0, y0, x1-1, y1-1], fill=(cr, cg, cb))
                hx = cx - rx // 2
                hy = cy - ry // 2
                if 0 <= hx < w and 0 <= hy < h:
                    draw.point((hx, hy),
                              fill=(min(255, cr+100), min(255, cg+100), min(255, cb+100)))

        return np.array(img)


if __name__ == '__main__':
    b = BounceTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(24):
        frame = b.generate_frame(t=i*0.06)
        Image.fromarray(frame).save(f'/home/jem/Intrix_Seed/themes/test_frames/bounce_{i:02d}.png')
    print("Saved 24 frames")
