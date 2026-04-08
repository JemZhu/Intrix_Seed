#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
霓虹三角立方体主题
用多个三角形组成的几何体，带 RGB 霓虹发光效果
"""

import math
import time
import numpy as np
from PIL import Image, ImageDraw


class CubeTheme:
    """
    霓虹三角立方体
    多个三角形拼接成立方体轮廓，RGB 三色交替，
    带向外扩散的发光效果，看起来像发光体
    """

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

    def generate_frame(self, status=None, t=None) -> np.ndarray:
        if t is None:
            t = time.time()

        w, h = self.width, self.height
        cx, cy = w // 2, h // 2

        # 背景
        img = Image.new('RGB', (w, h), (5, 5, 18))
        draw = ImageDraw.Draw(img)

        angle = t * 1.8

        # 立方体顶点
        s = 24
        verts_local = [
            [-s, -s, -s], [ s, -s, -s], [ s, s, -s], [-s, s, -s],
            [-s, -s,  s], [ s, -s,  s], [ s, s,  s], [-s, s,  s],
        ]

        def rot_y(v, a):
            x, y, z = v
            ca, sa = math.cos(a), math.sin(a)
            return (x * ca + z * sa, y, -x * sa + z * ca)

        def rot_x(v, a):
            x, y, z = v
            ca, sa = math.cos(a), math.sin(a)
            return (x, y * ca - z * sa, y * sa + z * ca)

        def proj(v):
            x, y, z = v
            sx = cx + int(x * 0.80)
            sy = cy + int(y * 0.45 - z * 0.30)
            return sx, sy

        verts = [rot_x(rot_y(v, angle), angle * 0.4) for v in verts_local]

        # 三角面（每个正方形面拆成2个三角形）
        tris = [
            # 前
            (0,1,2), (0,2,3),
            # 后
            (5,4,7), (5,7,6),
            # 左
            (4,0,3), (4,3,7),
            # 右
            (1,5,6), (1,6,2),
            # 上
            (3,2,6), (3,6,7),
            # 下
            (4,5,1), (4,1,0),
        ]
        # 每组三角形的颜色（R/G/B 循环）
        tri_colors = [
            (255, 30, 30), (255, 60, 30),
            (30, 255, 60), (60, 255, 30),
            (30, 60, 255), (30, 90, 255),
            (255, 30, 255), (255, 60, 180),
            (255, 220, 30), (255, 200, 60),
            (30, 255, 255), (60, 220, 255),
        ]

        # 按平均深度排序
        depths = []
        for i, tri in enumerate(tris):
            avg_z = sum(verts[vi][2] for vi in tri) / 3.0
            depths.append((avg_z, i))
        depths.sort(reverse=True)

        # 画每个三角形
        for avg_z, ti in depths:
            tri = tris[ti]
            pts = [proj(verts[vi]) for vi in tri]
            cr, cg, cb = tri_colors[ti]
            # 亮度随深度变化
            bright = max(0.35, min(1.0, 0.6 + avg_z / (s * 3)))
            dr, dg, db = int(cr * bright), int(cg * bright), int(cb * bright)
            draw.polygon(pts, fill=(dr, dg, db))

        # 外发光层（所有边画一圈粗的淡色）
        edges = [
            (0,1),(1,2),(2,3),(3,0),
            (4,5),(5,6),(6,7),(7,4),
            (0,4),(1,5),(2,6),(3,7),
        ]
        for a, b in edges:
            pa = proj(verts[a])
            pb = proj(verts[b])
            # 粗发光
            draw.line([pa, pb], fill=(60, 60, 120), width=4)
            draw.line([pa, pb], fill=(150, 160, 255), width=2)
            draw.line([pa, pb], fill=(230, 240, 255), width=1)

        # 顶点亮点
        for v in verts:
            px, py = proj(v)
            if 0 <= px < w and 0 <= py < h:
                draw.ellipse([px-2, py-2, px+2, py+2], fill=(255, 255, 255))

        return np.array(img)


if __name__ == '__main__':
    cube = CubeTheme()
    import os
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(24):
        t = i * 0.08
        frame = cube.generate_frame(t=t)
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/cube_{i:02d}.png')
    print("Saved 24 frames")
    print(f"Stats: max={frame.max()}, mean={frame.mean():.1f}")
