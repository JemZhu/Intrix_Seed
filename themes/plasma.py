#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
等离子/波浪主题 - 流动的彩色波纹
使用多层正弦波叠加 + 色相轮换实现迷幻等离子效果
"""

import math
import time
import numpy as np
from PIL import Image

class PlasmaTheme:
    """
    等离子波浪效果
    多层正弦波干涉 + HSV 色相旋转
    """

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()

        w, h = self.width, self.height

        # 向量化坐标
        x = np.arange(w, dtype=np.float64)
        y = np.arange(h, dtype=np.float64)
        xx, yy = np.meshgrid(x, y)

        # ── 多层正弦波叠加 ──
        # 每层: (freq_x, freq_y, speed_x, speed_y, phase, amplitude)
        waves = [
            # 大尺度慢波
            (0.05, 0.08,  0.3,  0.2, 0.0,  1.0),
            (0.07, 0.04, -0.2,  0.3, 1.5,  0.8),
            # 中尺度波
            (0.12, 0.15,  0.4, -0.3, 2.7,  0.6),
            (0.09, 0.11, -0.3,  0.4, 0.9,  0.7),
            # 小尺度快波
            (0.20, 0.25,  0.6,  0.5, 3.2,  0.4),
            (0.18, 0.22, -0.5, -0.4, 1.1,  0.35),
            # 细微纹理
            (0.35, 0.30,  0.8,  0.7, 4.5,  0.2),
            (0.30, 0.38, -0.7,  0.6, 2.3,  0.18),
        ]

        v = np.zeros((h, w), dtype=np.float64)
        for fx, fy, sx, sy, ph, amp in waves:
            v += np.sin(fx * xx + sx * t + ph) * amp
            v += np.sin(fy * yy + sy * t + ph * 1.3) * amp * 0.8

        # ── 圆形波（从中心向外扩散）──
        cx, cy = w / 2, h / 2
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        # 多个同心圆波
        for i, (fr, sp, ph) in enumerate([(0.12, 0.5, 0), (0.18, 0.7, 2), (0.25, 0.4, 4)]):
            v += np.sin(fr * dist - sp * t + ph) * 0.6

        # ── 归一化 ──
        v_min, v_max = v.min(), v.max()
        v = (v - v_min) / (v_max - v_min + 1e-9)

        # ── HSV → RGB 色相映射 ──
        # 色相随 v 值变化 + 整体时间旋转
        hue = (v + t * 0.05) % 1.0

        # 饱和度：中等偏高
        sat = np.full((h, w), 0.85, dtype=np.float64)
        # 亮度：较高的 value
        val = np.clip(v * 1.2, 0.0, 1.0)

        # HSV → RGB（向量化）
        i_h = (hue * 6.0).astype(np.int32)
        f = (hue * 6.0) - i_h
        p = val * (1.0 - sat)
        q = val * (1.0 - f * sat)
        t_i = val * (1.0 - (1.0 - f) * sat)

        i = i_h % 6
        r = np.where(i == 0, val,
               np.where(i == 1, q,
               np.where(i == 2, p,
               np.where(i == 3, p,
               np.where(i == 4, t_i, val)))))
        g = np.where(i == 0, t_i,
               np.where(i == 1, val,
               np.where(i == 2, val,
               np.where(i == 3, q,
               np.where(i == 4, p, p)))))
        b = np.where(i == 0, p,
               np.where(i == 1, p,
               np.where(i == 2, t_i,
               np.where(i == 3, val,
               np.where(i == 4, val, q)))))

        rgb = np.stack([
            (r * 255).astype(np.uint8),
            (g * 255).astype(np.uint8),
            (b * 255).astype(np.uint8),
        ], axis=-1)

        return rgb


if __name__ == '__main__':
    plasma = PlasmaTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(24):
        t = i * 0.1
        frame = plasma.generate_frame(t=t)
        from PIL import Image
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/plasma_{i:02d}.png')
    print("Saved 24 frames")
    import numpy as np
    print(f"Stats: max={frame.max()}, mean={frame.mean():.1f}")
