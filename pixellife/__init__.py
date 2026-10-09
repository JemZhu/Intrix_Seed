#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PixelLife -- an AI-driven pixel life simulator for 64x64 RGB565 panels.

Quick start (host side):

    from pixellife import LifeSim
    sim = LifeSim()
    image = sim.frame()            # PIL 64x64 RGB
    payload = sim.frame_rgb565()   # 8192 bytes for the firmware
"""
import time
from datetime import datetime

from .assets import Assets, get_assets, SCREEN, PLAY_H, SUB_H, WALL_H
from .characters import Actor
from .renderer import Renderer
from .subtitle import Subtitle
from .world import LifeWorld, ACTIONS

__all__ = ["LifeSim", "LifeWorld", "Renderer", "Actor", "Subtitle", "Assets",
           "get_assets", "ACTIONS", "SCREEN", "PLAY_H", "SUB_H", "WALL_H"]


class LifeSim(object):
    """Top-level driver: advance the world, then draw it."""

    def __init__(self, pack_dir=None, state_path=None, seed=None):
        kw = {}
        if state_path:
            kw["state_path"] = state_path
        self.world = LifeWorld(seed=seed, **kw)
        self.renderer = Renderer(pack_dir)
        self._last = time.time()
        try:
            from . import feeds
            feeds.get_feeds()          # 后台线程开始拉新闻和天气
        except Exception:                                       # noqa: BLE001
            pass

    def tick(self, now=None):
        now = now or datetime.now()
        t = time.time()
        # cap dt so a long pause (service restart, laptop sleep) doesn't make the
        # simulation jump -- world handles the catch-up itself via _advance_offline
        dt = max(0.0, min(1.0, t - self._last))
        self._last = t
        self.world.tick(now, seconds=dt)
        return now, dt, t

    def frame(self, now=None):
        now, dt, t = self.tick(now)
        return self.renderer.build(self.world, now, dt, t)

    def frame_rgb565(self, now=None):
        now, dt, t = self.tick(now)
        return self.renderer.render_rgb565(self.world, now, dt, t)

    def save(self):
        self.world.save()

    def people(self):
        """Roster + relationship network, for the console's resident page."""
        return self.world.people_panel()

    def summary(self):
        out = self.world.summary()
        try:
            from . import llm, social
            out["llm"] = llm.get_pool().status()
            out["llm"]["chat"] = social.chatter().stats()
        except Exception:                                   # noqa: BLE001
            pass
        try:
            from . import feeds
            out["feeds"] = feeds.get_feeds().status()
        except Exception:                                   # noqa: BLE001
            pass
        try:
            from . import worldlog
            s = worldlog.get_log().stats()
            out["worldlog"] = dict(
                days=s.get("days"), first=s.get("first"), last=s.get("last"),
                size_kb=s.get("size_kb"),
                max_days=(s.get("config") or {}).get("max_days"))
        except Exception:                                   # noqa: BLE001
            pass
        return out

    def llm_status(self):
        from . import llm
        return llm.get_pool().status()

    # ── v6.17: 屏幕显示项（底栏字幕速度）──────────────────────────
    def display_status(self):
        """面板读：字幕速度的当前值 + 合法区间。"""
        w = self.world
        return dict(subtitle_speed=w.sub_speed(),
                    min_speed=w.SUB_SPEED_MIN,
                    max_speed=w.SUB_SPEED_MAX,
                    default_speed=w.SUB_SPEED_DEFAULT)

    def set_display(self, patch):
        """面板写：改完立即生效（下一帧渲染就读新值），顺手存一次档。"""
        patch = patch or {}
        if "subtitle_speed" in patch:
            self.world.sub_speed(patch.get("subtitle_speed"))
            try:
                self.world.save()
            except Exception:                               # noqa: BLE001
                pass
        return self.display_status()

    def set_llm(self, patch):
        """Console hook: update the endpoint config without restarting."""
        from . import llm
        cfg = llm.get_config().update(patch or {})
        llm.reload()
        return cfg

    def test_llm(self):
        """Console hook: one blocking probe call, returns (reply, error)."""
        from . import llm
        pool = llm.get_pool()
        reply, err = pool.call_sync(
            [dict(role="system", content="你是一个像素小人。"),
             dict(role="user", content="用不超过8个字说一句你现在想做的事。")],
            max_tokens=48)
        return dict(reply=reply, error=err, models=pool.models()[0],
                    status=pool.status())
