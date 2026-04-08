#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水波纹主题 - 涟漪扩散效果
多重同心圆环，numpy 直接绘制，更亮更清晰
"""

import math
import random
import time
import numpy as np
from PIL import Image


class RippleTheme:
    """
    水波纹效果
    随机滴水 → 多重同心圆涟漪扩散
    """

    MAX_RIPPLES = 6

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.ripples = []
        self.next_drop = 0.0
        self.t = 0.0

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()
        self.t = t

        w, h = self.width, self.height

        # 背景：深水蓝
        bg = np.zeros((h, w, 3), dtype=np.float64)
        bg[:, :, 0] = 8
        bg[:, :, 1] = 28
        bg[:, :, 2] = 60

        # 微弱背景波浪纹理
        x = np.arange(w, dtype=np.float64)
        y = np.arange(h, dtype=np.float64)
        xx, yy = np.meshgrid(x, y)
        wave = (
            np.sin(xx / w * math.pi * 5 + t * 0.5) * 0.4 +
            np.sin(yy / h * math.pi * 4 - t * 0.35) * 0.3
        ) * 2.5
        bg[:, :, 0] += wave * 0.15
        bg[:, :, 1] += wave * 0.9
        bg[:, :, 2] += wave * 1.8

        # 随机产生新涟漪
        if t >= self.next_drop:
            self._add_ripple()
            self.next_drop = t + random.uniform(1.5, 3.0)

        # 预计算全图每个像素到每个涟漪中心的距离
        result = bg.copy()

        for rip in self.ripples[:]:
            age = t - rip['start']
            if age < 0 or age > rip['duration']:
                self.ripples.remove(rip)
                continue

            # 当前扩散半径
            radius = age * rip['speed']
            if radius > rip['max_r']:
                continue

            life = 1.0 - (age / rip['duration']) ** 1.2

            cx, cy = rip['cx'], rip['cy']

            # 计算全图到圆心的距离
            dx = xx - cx
            dy = yy - cy
            dist = np.sqrt(dx**2 + dy**2)

            # 涟漪环参数：每 4px 一个环，最亮在 ring_peak
            ring_peak = max(2.0, radius * 0.6)
            ring_period = 4.0
            # 计算每个像素到最近涟漪环的距离
            ring_phase = (dist - ring_peak) % ring_period
            # 用 smoothstep 把环变成有一定宽度的亮线
            ring_dist_norm = np.minimum(ring_phase, ring_period - ring_phase) / (ring_period * 0.5)
            ring_width = 0.6  # 环宽度（归一化）
            ring_mask = np.maximum(0.0, 1.0 - ring_dist_norm / ring_width)

            # 外圈淡出
            outer_fade = np.maximum(0.0, 1.0 - dist / max(1.0, radius))

            # 组合强度
            intensity = ring_mask * outer_fade * life * rip['strength']

            # 颜色：外圈青蓝 → 内圈白
            # 越靠近中心越白
            inner_fade = np.clip(dist / max(1.0, ring_peak), 0.0, 1.0)
            r_c = 30 + inner_fade * 200
            g_c = 80 + inner_fade * 170
            b_c = 160 + inner_fade * 95

            # 加到结果上
            for c in range(3):
                result[:, :, c] += r_c[c] * intensity * 0.85

            # 中心泛白点（扩散中的水滴）
            center_intensity = life * rip['strength'] * 0.6
            if center_intensity > 0.01:
                center_mask = np.exp(-dist**2 / 4.0)
                result[:, :, 0] += 200 * center_mask * center_intensity
                result[:, :, 1] += 240 * center_mask * center_intensity
                result[:, :, 2] += 255 * center_mask * center_intensity

        result = np.clip(result, 0, 255).astype(np.uint8)
        return result

    def _add_ripple(self):
        if len(self.ripples) >= self.MAX_RIPPLES:
            self.ripples.pop(0)
        self.ripples.append({
            'cx': random.uniform(8, self.width - 8),
            'cy': random.uniform(8, self.height - 8),
            'start': self.t,
            'speed': random.uniform(10.0, 16.0),
            'max_r': random.uniform(24.0, 38.0),
            'strength': random.uniform(0.8, 1.0),
            'duration': random.uniform(3.5, 5.5),
        })


if __name__ == '__main__':
    ripple = RippleTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(30):
        t = i * 0.15
        frame = ripple.generate_frame(t=t)
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/ripple_{i:02d}.png')
    print("Saved 30 frames")
    print(f"Stats: max={frame.max()}, mean={frame.mean():.1f}")
