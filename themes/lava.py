#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
熔岩灯主题 - 华丽的向上升腾火焰/熔岩效果
使用 FBM 噪声 + 谐波叠加实现有机流动
色彩从底部的白黄热色 → 橙红 → 紫蓝冷色向上过渡
"""

import math
import random
import time
import numpy as np
from PIL import Image, ImageDraw

class LavaTheme:
    """
    熔岩灯 / 火焰效果
    底部热源 → 向上升腾 → 顶部冷却 → 循环下沉
    """

    # 火焰色板：从热到冷
    # 每行定义: (R, G, B, threshold)
    # threshold 表示该色层在 Y 轴上的位置（0=底，1=顶）
    FLAME_PALETTE = [
        (255, 255, 220, 0.00),  # 白热（最热，底部）
        (255, 240, 80,  0.10),  # 亮黄
        (255, 160, 20,  0.25),  # 橙
        (255, 60,  0,   0.45),  # 红橙
        (200, 20,  60,  0.60),  # 红色
        (120, 10,  100, 0.75),  # 深红紫
        (50,  5,   80,  0.88),  # 暗紫
        (10,  2,   40,  1.00),  # 近黑（最冷，顶部）
    ]

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.t = 0.0

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()
        self.t = t

        img = Image.new('RGB', (self.width, self.height), (5, 2, 10))
        draw = ImageDraw.Draw(img)

        # 用向量化方式计算噪声 + 渲染
        arr = self._render_flame()
        return arr

    def _render_flame(self) -> np.ndarray:
        """用 FBM 噪声 + 行波叠加渲染火焰"""
        w, h = self.width, self.height
        t = self.t

        # ── 多层噪声参数 ──
        # 每层: (scale_x, scale_y, speed, amplitude, offset)
        layers = [
            (0.15, 0.25, 0.40, 14.0, 0.0),   # 大尺度慢流动
            (0.30, 0.50, 0.70, 8.0,  3.7),   # 中等波动
            (0.60, 0.90, 1.10, 4.0,  1.3),   # 小尺度细节
            (1.10, 1.80, 1.80, 2.0,  5.9),   # 微小抖动
        ]

        # 构建温度场 T[y, x]
        temp = np.zeros((h, w), dtype=np.float64)

        for sx, sy, speed, amp, off in layers:
            tx = sx * np.arange(w, dtype=np.float64) + t * speed + off
            ty = sy * np.arange(h, dtype=np.float64) + t * speed * 0.7 + off * 1.3
            # 垂直波动：向上升腾的感觉
            ty = ty - t * 0.6  # 向上偏移，制造升腾效果

            # 2D 谐波噪声（不用 numpy 复杂函数，用简单叠加）
            wave = (
                np.sin(tx / w * 2 * math.pi * 2 + ty / h * 1.5) * 0.5 +
                np.sin(tx / w * 3 * math.pi * 1.3 - ty / h * 2.0) * 0.3 +
                np.sin(tx / w * 5 * math.pi * 0.8 + ty / h * 3.0) * 0.2
            )
            temp += wave * amp

        # 归一化到 0~1
        temp = (temp - temp.min()) / (temp.max() - temp.min() + 1e-9)

        # ── 垂直色层：底部热，顶部冷 ──
        # 每列底部的热源强度不同（模拟不均匀加热）
        bottom_heat = np.random.rand(w) * 0.15 + 0.85  # 每列底部热度

        # Y 轴升温权重：从底向上逐渐降温
        y_factor = np.linspace(1.0, 0.0, h).reshape(h, 1)  # shape (h,1)
        x_factor = bottom_heat.reshape(1, w)               # shape (1,w)

        # 温度场叠加垂直梯度（底部额外加热）
        temp = temp + (1.0 - y_factor) * x_factor * 0.4
        temp = np.clip(temp, 0.0, 1.0)

        # ── 色彩映射 ──
        result = np.zeros((h, w, 3), dtype=np.uint8)
        for i in range(len(self.FLAME_PALETTE) - 1):
            c0, c1 = self.FLAME_PALETTE[i], self.FLAME_PALETTE[i + 1]
            t0, t1 = c0[3], c1[3]
            r0, g0, b0 = c0[0], c0[1], c0[2]
            r1, g1, b1 = c1[0], c1[1], c1[2]

            # 当前色层的 mask
            mask = (temp >= t0) & (temp < t1)
            if i == len(self.FLAME_PALETTE) - 2:
                mask = (temp >= t0)  # 最后一层用 >=

            # 层内插值
            alpha = (temp - t0) / max(t1 - t0, 0.001)
            alpha = np.clip(alpha, 0.0, 1.0)

            r = ((r0 * (1 - alpha) + r1 * alpha) * mask).astype(np.uint8)
            g = ((g0 * (1 - alpha) + g1 * alpha) * mask).astype(np.uint8)
            b = ((b0 * (1 - alpha) + b1 * alpha) * mask).astype(np.uint8)

            result[:, :, 0] |= r
            result[:, :, 1] |= g
            result[:, :, 2] |= b

        return result


if __name__ == '__main__':
    lava = LavaTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(20):
        t = i * 0.12
        frame = lava.generate_frame(t=t)
        from PIL import Image
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/lava_{i:02d}.png')
    print("Saved 20 frames")
    import numpy as np
    print(f"Frame stats: max={frame.max()}, mean={frame.mean():.1f}")
