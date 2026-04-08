#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
星空 Warp Speed 主题 - 虫洞隧道效果
同心椭圆环从中心向外扩张 + 飞散粒子，模拟 hyperspace 跳跃
"""

import math
import random
import time
import numpy as np
from PIL import Image, ImageDraw


class WarpTheme:
    """
    Warp Speed 虫洞隧道效果
    - 多个同心椭圆环从中心向外扩张（透视拉伸感）
    - 少量粒子沿隧道壁飞过
    - 中心白/青色光芒
    """

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.rings = []     # (radius, speed, thickness, brightness, color, angle_offset)
        self.particles = []
        self.t = 0.0
        self._init_rings()
        self._init_particles()

    def _init_rings(self):
        """初始化隧道环"""
        self.rings = []
        for i in range(12):
            self.rings.append({
                'radius': 2.0 + i * 2.5,    # 初始半径
                'speed': 1.2 + i * 0.18,     # 扩张速度
                'thickness': max(1, 3 - i // 4),
                'brightness': 0.9 - i * 0.05,
                'phase': random.uniform(0, math.pi * 2),
                # 颜色：内圈白，外圈蓝紫
                'hue': i * 0.06,  # 0=白，渐变到蓝紫
            })

    def _init_particles(self):
        """初始化飞散粒子"""
        self.particles = []
        for _ in range(50):
            self.particles.append(self._new_particle())

    def _new_particle(self, initial=False):
        angle = random.uniform(0, math.pi * 2)
        z = random.uniform(0.0, 1.0) if initial else 0.01
        return {
            'angle': angle,
            'z': z,
            'speed': random.uniform(0.018, 0.035),
            'brightness': random.uniform(0.5, 1.0),
            'size': 1 if random.random() > 0.3 else 2,
            # 粒子在隧道壁位置（椭圆半径比例）
            'ring_ratio': random.uniform(0.15, 0.95),
            'angle_drift': random.uniform(-0.003, 0.003),
        }

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()
        self.t = t

        w, h = self.width, self.height
        cx, cy = w // 2, h // 2

        # 背景：深空黑
        img = Image.new('RGB', (w, h), (1, 0, 6))
        draw = ImageDraw.Draw(img)

        # ── 中心光芒 ──
        for r in range(8, 0, -1):
            alpha = (9 - r) / 8.0
            intensity = int(180 * alpha)
            draw.ellipse([cx-r, cy-r*0.6, cx+r, cy+r*0.6],
                         fill=(int(intensity*0.6), int(intensity*0.85), intensity))

        # ── 隧道环（从中心向外扩张）──
        for ring in self.rings:
            # 推进环半径
            ring['radius'] += ring['speed'] * 0.15
            if ring['radius'] > max(w, h):
                # 重置到中心附近
                ring['radius'] = 2.0
                ring['phase'] = random.uniform(0, math.pi * 2)

            r = ring['radius']
            # 透视椭圆压缩
            rx = r
            ry = r * 0.62

            # 亮度闪烁
            flicker = 0.7 + 0.3 * math.sin(t * 3 + ring['phase'])
            brightness = ring['brightness'] * flicker

            # 颜色：内白(0)→青(0.3)→蓝(0.7)→紫(1.0)
            h = ring['hue']
            if h < 0.3:
                t2 = h / 0.3
                cr = int((100 + 155 * t2) * brightness)
                cg = int((100 + 155 * t2) * brightness)
                cb = int(255 * brightness)
            elif h < 0.7:
                t2 = (h - 0.3) / 0.4
                cr = int((255 - 155 * t2) * brightness)
                cg = int((255 - 75 * t2) * brightness)
                cb = int(255 * brightness)
            else:
                t2 = (h - 0.7) / 0.3
                cr = int((100 - 55 * t2) * brightness)
                cg = int((180 - 130 * t2) * brightness)
                cb = int((255 - 55 * t2) * brightness)

            # 画椭圆环
            if rx > 1 and ry > 1:
                try:
                    draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry],
                                 outline=(cr, cg, cb),
                                 width=ring['thickness'])
                except Exception:
                    pass

        # ── 飞散粒子 ──
        for p in self.particles[:]:
            p['z'] += p['speed']
            p['angle'] += p['angle_drift']

            if p['z'] > 1.0:
                self.particles.remove(p)
                self.particles.append(self._new_particle())
                continue

            # 粒子位置：沿隧道壁飞行
            fly_r = p['z'] * max(w, h) * 0.55
            r_total = fly_r * p['ring_ratio']
            px = cx + int(r_total * math.cos(p['angle']))
            py = cy + int(r_total * 0.62 * math.sin(p['angle']))

            # 近处更亮
            brightness = p['z'] * p['brightness']
            cr = int(220 * brightness)
            cg = int(240 * brightness)
            cb = int(255 * brightness)

            if 0 <= px < w and 0 <= py < h:
                draw.point((px, py), fill=(cr, cg, cb))
                if p['size'] == 2:
                    for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nx, ny = px+dx, py+dy
                        if 0 <= nx < w and 0 <= ny < h:
                            draw.point((nx, ny), fill=(cr//2, cg//2, cb//2))

        return np.array(img)


if __name__ == '__main__':
    warp = WarpTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(24):
        t = i * 0.08
        frame = warp.generate_frame(t=t)
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/warp_{i:02d}.png')
    print("Saved 24 frames")
    print(f"Last frame: max={frame.max()}")
