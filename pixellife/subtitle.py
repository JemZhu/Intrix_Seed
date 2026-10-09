#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bottom subtitle band: 8px tall, quan.ttf (8x8 pixel font), horizontal marquee.

Scroll behaviour
----------------
The strip is laid out as   [W blank][glyphs][W blank]   and swept leftwards, so a
message ALWAYS enters from beyond the right edge of the panel -- never pops up in
the middle.  If the message is short enough to fit, the sweep pauses when it is
centred (a hold) and then carries it off to the left, leaving a clean gap before
the next pass.

Colour (v6.16)
--------------
一整行一个颜色看不出差别：「健康92 心情38 精力75 饱腹61」滚过去是一片同色的
数字，得逐字读完才知道哪个掉了。现在关键词用它自己那支仪表盘的颜色 —— 健康
红、心情黄、精力蓝、饱腹绿、魅力粉 —— 扫一眼就知道谁在报警。颜色表直接从
hud.py 拿，两边永远是同一套色。
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "pack", "quan.ttf")
if not os.path.exists(FONT):
    # the host project already ships this font one level up
    FONT = os.path.normpath(os.path.join(HERE, os.pardir, "quan.ttf"))

_FALLBACK_COLOURS = {
    "health": (240, 84, 96), "happiness": (248, 196, 80),
    "hunger": (120, 205, 96), "energy": (96, 186, 240),
    "charm": (232, 122, 204),
}


def _stat_colours():
    """仪表色，单一来源是 hud.GAUGE_COLOURS。"""
    try:
        from .hud import GAUGE_COLOURS
        return dict(GAUGE_COLOURS)
    except Exception:                                       # noqa: BLE001
        try:
            from hud import GAUGE_COLOURS                   # 独立运行时的兜底
            return dict(GAUGE_COLOURS)
        except Exception:                                   # noqa: BLE001
            return dict(_FALLBACK_COLOURS)


def keyword_colours():
    """播报里会被点亮的关键词 -> 颜色。"""
    c = _stat_colours()
    return {
        "健康": c.get("health"), "体力": c.get("energy"),
        "心情": c.get("happiness"), "精力": c.get("energy"),
        "饱腹": c.get("hunger"), "饥饿": c.get("hunger"),
        "魅力": c.get("charm"),
    }


def segmentize(text, default, table=None):
    """把一行切成 [(片段, 颜色)]：命中关键词的那几个字换成状态色。

    关键词后面紧跟的数字一起染色 —— 「健康72」整个是红的，比只红前面的
    两个字更好读。
    """
    table = table or keyword_colours()
    out = []
    i = 0
    n = len(text)
    buf = ""
    while i < n:
        hit = None
        for kw in table:
            if text.startswith(kw, i):
                hit = kw
                break
        if not hit:
            buf += text[i]
            i += 1
            continue
        if buf:
            out.append((buf, default))
            buf = ""
        j = i + len(hit)
        while j < n and (text[j].isdigit() or text[j] in "./%+-"):
            j += 1
        out.append((text[i:j], table[hit] or default))
        i = j
    if buf:
        out.append((buf, default))
    return out


class Subtitle(object):
    """Marquee band. `speed` is px per tick; ~15 ticks/s gives a calm read.

    v6.17: `speed` 不再是写死的 1 —— 面板上有个滑块（world.sub_speed()），
    渲染器每一帧把它按进来。字幕快了，停顿也得跟着变短，否则"读得完"
    和"滚得快"会互相拉扯。
    """

    HOLD_TICKS = 24          # how long a legible message rests before moving on

    def __init__(self, width=64, height=8, font_path=FONT, speed=1, fg=(238, 242, 248),
                 bg=(12, 11, 16)):
        self.w = width
        self.h = height
        self.speed = speed
        self.fg = fg
        self.bg = bg
        self.font = ImageFont.truetype(font_path, 8)
        self.text = None
        self.strip = None
        self.offset = 0.0
        self.hold = 0
        self.hold_at = None     # offset value at which to pause (None = never)

    # ─── text measurement ───────────────────────────────────────────
    def text_width(self, s):
        try:
            return int(self.font.getlength(s))
        except AttributeError:                                # very old Pillow
            return self.font.getmask(s).size[0]

    # ─── colouring ──────────────────────────────────────────────────
    def _paint(self, mask, text):
        """给一整段字形蒙版按字符区间上色，返回 RGB 长条。"""
        img = Image.new("RGB", mask.size, self.bg)
        xs = []
        x = self.w
        for ch in text:
            xs.append(x)
            x += self.text_width(ch)
        xs.append(x)
        pos = 0
        for seg, col in segmentize(text, self.fg):
            if not seg:
                continue
            a = xs[pos] if pos < len(xs) else xs[-1]
            b = xs[min(pos + len(seg), len(xs) - 1)]
            if b > a:
                sub = mask.crop((a, 0, b, self.h))
                img.paste(Image.new("RGB", sub.size, col), (a, 0),
                          sub.point(lambda v: 255 if v > 96 else 0))
            pos += len(seg)
        return img

    def set_text(self, text, colour=None):
        text = " ".join((text or "").split())
        if text == self.text and colour in (None, self.fg):
            return False
        if colour is not None:
            self.fg = colour
        self.text = text
        self.offset = 0.0
        self.hold = 0
        if not text:
            self.strip = None
            self.hold_at = None
            return True

        tw = self.text_width(text)
        # [right-entry pad][glyphs][exit pad]; the first pad guarantees the head
        # starts exactly at screen x == w, i.e. off the right edge.
        mask = Image.new("L", (self.w + tw + self.w, self.h), 0)
        ImageDraw.Draw(mask).text((self.w, 0), text, fill=255, font=self.font)
        self.strip = self._paint(mask, text)

        # pause when centred, but only if the whole line fits on the panel
        if tw <= self.w:
            self.hold_at = self.w - (self.w - tw) // 2
        else:
            self.hold_at = None
        return True

    # ─── animation ──────────────────────────────────────────────────
    def _hold_ticks(self):
        """停顿时长与速度成反比 —— 加速后停顿还是老长度会很别扭。

        下限 6 帧（约 0.4s）：再短就变成"扫过去连个停顿都没有"，读不全。
        """
        try:
            s = float(self.speed) or 1.0
        except Exception:                                       # noqa: BLE001
            s = 1.0
        return max(6, int(round(self.HOLD_TICKS / max(0.5, s))))

    def tick(self, speed=None):
        if self.strip is None:
            return
        if self.hold > 0:
            self.hold -= 1
            return
        self.offset += self.speed if speed is None else speed
        if self.hold_at is not None and self.offset >= self.hold_at:
            self.offset = self.hold_at
            self.hold = self._hold_ticks()
            self.hold_at = None          # only hold the first time round
        if self.offset >= self.strip.size[0]:
            self.offset = 0.0
            self.hold = 0

    # ─── draw ───────────────────────────────────────────────────────
    def render(self):
        out = Image.new("RGB", (self.w, self.h), self.bg)
        if self.strip is None:
            return out
        L = int(self.offset)
        R = min(self.strip.size[0], L + self.w)
        if R <= L:
            return out
        return self.strip.crop((L, 0, R, self.h))


def to_rgb565_bytes(frame_rgb):
    """64x64 RGB -> 8192-byte little-endian RGB565 payload for the firmware."""
    a = np.asarray(frame_rgb.convert("RGB"), dtype=np.uint16)
    v = ((a[:, :, 0] >> 3) << 11) | ((a[:, :, 1] >> 2) << 5) | (a[:, :, 2] >> 3)
    return v.astype("<u2").tobytes()
