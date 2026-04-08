#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极光主题 - 缓慢流动的彩色光带
流式梯度方案：用 X 方向的慢变色相/亮度产生斜向流动
无 Y 方向正弦波 → 彻底消除横纹和竖条
"""

import math
import time
import numpy as np
from PIL import Image


class AuroraTheme:
    """
    极光效果
    缓慢斜向流动的彩色渐变，无网格噪声，无水平/竖直条带
    """

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()

        w, h = self.width, self.height
        x = np.arange(w, dtype=np.float64)
        y = np.arange(h, dtype=np.float64)
        xx, yy = np.meshgrid(x, y)

        # ── 核心：用 X 方向慢变 + Y 方向小扰动 产生自然流动 ──
        # X 方向相位（慢）
        x_phase = xx / w * math.pi * 5.0
        # Y 方向微小扰动，让流动有斜向弯曲
        y_bend = yy / h * math.pi * 1.5

        # 主流动：两个频率叠加，形成有机变化
        flow = (
            np.sin(x_phase + t * 0.20 + y_bend * 0.6) * 0.5 +
            np.sin(x_phase * 1.7 - t * 0.14 + y_bend * 0.4 + 1.3) * 0.3 +
            np.sin(x_phase * 0.8 + t * 0.09 + y_bend * 0.9 + 2.7) * 0.2
        )

        # 全局亮度：Y 方向缓慢渐变（顶部和底部偏暗，中间偏亮）
        y_grad = 1.0 - np.abs(yy / h - 0.5) * 1.2
        y_grad = np.clip(y_grad, 0.0, 1.0)

        # 组合强度
        intensity = (flow * 0.4 + 0.6) * y_grad
        intensity = np.clip(intensity, 0.05, 1.0)

        # ── 色彩 ──
        base_hue = (t * 0.010) % 1.0

        # 色相由 X 相位慢变 + Y 小偏移 共同决定
        hue = (base_hue
               + xx / w * 0.25
               + flow * 0.08
               + (yy / h - 0.5) * 0.10) % 1.0

        # 饱和度：中等
        sat = np.full((h, w), 0.60, dtype=np.float64)

        # 亮度
        val = np.clip(intensity * 1.5, 0.0, 0.95)

        # HSV → RGB
        i_h = (hue * 6.0).astype(np.int32)
        f_h = (hue * 6.0) - i_h
        p = val * (1.0 - sat)
        q = val * (1.0 - f_h * sat)
        t_i = val * (1.0 - (1.0 - f_h) * sat)
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
    aurora = AuroraTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(24):
        t = i * 0.12
        frame = aurora.generate_frame(t=t)
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/aurora_{i:02d}.png')
    print("Saved 24 frames")
    print(f"Stats: max={frame.max()}, mean={frame.mean():.1f}")
