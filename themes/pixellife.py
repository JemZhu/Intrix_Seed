#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PixelLife -- AI 驱动的像素养成游戏主题（64x64 RGB565）

一块 64x64 像素屏 = 一个永远活着的像素小人：它按真实时间作息、上班、炒股、
购物、装修、旅行、睡觉，全部由本地欲望引擎（可选云端 LLM 增强）自主决策。

渲染契约与其它主题一致：generate_frame(status=None, t=None) -> (H, W, 3) uint8
"""
import os
import sys
import time

import numpy as np

# --- deploy: resolve project assets relative to this file (macOS-safe) ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from pixellife import LifeSim
    HAS_PIXELLIFE = True
except Exception as e:                                     # noqa: BLE001
    HAS_PIXELLIFE = False
    _IMPORT_ERROR = e


class PixelLifeTheme(object):
    FPS = 12                 # within the 10-15 FPS budget for long-running panels
    SAVE_EVERY = 60.0        # seconds between state snapshots

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self._frame = None
        self._last_draw = 0.0
        self._last_save = time.time()
        self.sim = None
        if HAS_PIXELLIFE:
            try:
                self.sim = LifeSim()
                print("🧍 PixelLife 已启动: %s | %s | %s"
                      % (self.sim.world.state["name"],
                         self.sim.world.state["mbti"],
                         self.sim.world.state["life_pace"]))
            except Exception as e:                         # noqa: BLE001
                print("⚠️  PixelLife 初始化失败: %s" % e)

    # ---- required theme interface ----
    def generate_frame(self, status=None, t=None):
        now = time.time()
        if self.sim is None:
            return np.full((self.height, self.width, 3), 18, dtype=np.uint8)
        if self._frame is None or (now - self._last_draw) >= (1.0 / self.FPS):
            self._frame = np.asarray(self.sim.frame(), dtype=np.uint8)
            self._last_draw = now
            if now - self._last_save > self.SAVE_EVERY:
                self._last_save = now
                try:
                    self.sim.save()
                except Exception:                          # noqa: BLE001
                    pass
        return self._frame

    # ---- extras used by the back office API ----
    def summary(self):
        return self.sim.summary() if self.sim else {"error": "not initialised"}

    def rgb565(self):
        from pixellife.subtitle import to_rgb565_bytes
        from PIL import Image
        return to_rgb565_bytes(Image.fromarray(self.generate_frame(), "RGB"))

    def save(self):
        if self.sim:
            self.sim.save()
