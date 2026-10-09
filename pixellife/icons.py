#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v6.10: 动作小图标 —— 8x8 像素图，每个图标 2~4 帧循环动画。

Every action gets a small pictogram so the pale-yellow bubble reads at a
glance: [icon] 上班 instead of just 上班.  The art is plain ASCII so it can
be edited without any tooling; frames are produced by shifting the base
art one pixel (bob / sway / pulse), which keeps every frame exactly 8x8 --
that matters because the bubble layout engine caches widths per frame and
would jitter if the icon changed size.
"""
from PIL import Image

# ─── palette ────────────────────────────────────────────────────────
PAL = {
    "k": (18, 16, 24),        # outline / black
    "w": (252, 250, 248),     # white
    "y": (250, 206, 84),      # yellow
    "o": (240, 150, 60),      # orange
    "r": (216, 86, 80),       # red
    "g": (104, 178, 104),     # green
    "b": (92, 138, 206),      # blue
    "c": (98, 190, 200),      # cyan
    "n": (152, 104, 64),      # brown
    "s": (242, 196, 152),     # skin
    "m": (234, 142, 170),     # pink
    "p": (152, 112, 190),     # purple
}

# ─── art ────────────────────────────────────────────────────────────
# 8 rows of 8 chars each. "." is transparent.
ART = {
    "bed": """
........
.kkkkkk.
.kwwwww.
.knnnnn.
.knnnnn.
.kkkkkk.
.k....k.
........
""",
    "sun": """
...y....
.y.y.y..
..yyy...
.yyyyy..
.yyyyy..
..yyy...
.y.y.y..
...y....
""",
    "laptop": """
........
.kkkkkk.
.kwwwwk.
.kwkkwk.
.kwkkwk.
.kkkkkk.
.kkkkkk.
........
""",
    "chart": """
........
.....r..
.....r..
...r.r..
...r.r..
.r.r.r..
.r.r.r..
........
""",
    "coins": """
........
..kkkk..
..kyyk..
..kkkk..
.kkkkkk.
.kyyyyk.
.kkkkkk.
........
""",
    "book": """
........
.kkkkkk.
.kwwwwk.
.kwkkwk.
.kwwwwk.
.kkkkkk.
........
........
""",
    "openbook": """
........
.kk..kk.
.kwk.kwk
.kwk.kwk
.kwk.kwk
.kkkkkk.
........
........
""",
    "blackboard": """
kkkkkkkk
kwwwwwwk
kwwkkwwk
kwwwwwwk
kwwwwwkk
kkkkkkkk
..k..k..
........
""",
    "pen": """
......k.
.....kk.
....kk..
...kk...
..kk....
.kk.....
kk......
........
""",
    "picture": """
........
.kkkkkk.
.kyybbk.
.kyybbk.
.krrogk.
.kkkkkk.
........
........
""",
    "pan": """
........
..kkk...
.kkkkk..
.kwkwwk.
.kkkkk..
..kkk.k.
......k.
........
""",
    "bowl": """
........
.k....k.
.k....k.
.kkkkkk.
.kwwwwk.
..kkkk..
........
........
""",
    "tv": """
........
.kkkkkk.
.kbbbbk.
.kbwwbk.
.kbbbbk.
.kkkkkk.
..k..k..
........
""",
    "ball": """
........
..kkkk..
.kwwwwk.
.kwkkwk.
.kwkkwk.
.kwwwwk.
..kkkk..
........
""",
    "dumbbell": """
........
........
.kk..kk.
.kkkkkk.
.kkkkkk.
.kk..kk.
........
........
""",
    "shower": """
........
.kkkkk..
.k...k..
..kkkk..
.c.c.c..
.c.c.c..
........
........
""",
    "hammer": """
........
.kkkk...
.kkkk...
..kk....
..kk....
..kk....
..kk....
........
""",
    "bag": """
........
..k..k..
.kkkkkk.
.kbbbbk.
.kbbbbk.
.kkkkkk.
........
........
""",
    "mountain": """
........
.....ww.
....ggg.
...gggg.
..ggggg.
.gggggg.
........
........
""",
    "footprint": """
........
..kk....
..kk....
........
...kk...
...kk...
........
........
""",
    "paw": """
........
.n.n.n..
..nnnn..
..nnnn..
..nnnn..
........
........
........
""",
    "bike": """
........
........
.kk..kk.
k..kk..k
k..kk..k
.kk..kk.
........
........
""",
    "run": """
........
...kk...
..kkk...
.kkk....
..kkk...
...kk...
........
........
""",
    "chat": """
........
kkkkkk..
kwwwwk..
kwwwk...
kkkkk...
..k.k...
........
........
""",
    "house": """
........
...rr...
..rrrr..
.rrrrrr.
.kwwwk..
.kwnwk..
.kkkkkk.
........
""",
    "balloon": """
........
..rrrr..
.rrrrrr.
.rrrrrr.
..rrrr..
...k....
...k....
........
""",
    "heart": """
........
.mm..mm.
mmmmmmmm
mmmmmmmm
.mmmmmm.
..mmmm..
...mm...
........
""",
    "dots": """
........
........
........
..k.k.k.
........
........
........
........
""",
    "star": """
........
...w....
..www...
.wwwww..
...w....
..w.w...
.w...w..
........
""",
    "note": """
........
....kk..
....kk..
....kk..
..kkkk..
.kkkk...
.kk.....
........
""",
    "brush": """
......y.
.....yy.
....kk..
...kk...
..kk....
.kk.....
kk......
........
""",
    "ghost": """
........
..kkkk..
.kwwwwk.
.kk..kk.
.kwwwwk.
.kwwwwk.
.k.kk.k.
........
""",
    "cross": """
........
...rr...
...rr...
.rrrrrr.
.rrrrrr.
...rr...
...rr...
........
""",
    "hand": """
........
..s.s...
.sssss..
.sssss..
.sssss..
..sss...
........
........
""",
    "cup": """
........
.kkkkk..
.knnnk..
.knnnkk.
.knnnk..
.kkkkk..
........
........
""",
    "bus": """
........
.kkkkkk.
.kcccck.
.kcccck.
.kcccck.
.kkkkkk.
..k..k..
........
""",
    "gamepad": """
........
........
.kkkkkk.
.krkkbk.
.kkkkkk.
..k..k..
........
........
""",
    "wave": """
........
........
.cc..cc.
c..cc..c
........
.cc..cc.
c..cc..c
........
""",
    "flower": """
........
..mmm...
.mmmmm..
..mmm...
...g....
.g.g....
..g.....
........
""",
    "broom": """
........
....kk..
...kk...
..kk....
.kkk....
kyyk....
.yyk....
........
""",
    "camera": """
........
..kkk...
.kkkkkk.
.kwwwwk.
.kwkkwk.
.kkkkkk.
........
........
""",
    "fish": """
........
........
..cccc..
.cccccc.
..cccc..
.cc..cc.
........
........
""",
    "parcel": """
........
.kkkkkk.
.knnnnk.
.knkknk.
.knnnnk.
.kkkkkk.
........
........
""",
    "stall": """
........
...kk...
.rwrwrw.
kkkkkkkk
...kk...
...kk...
...kk...
........
""",
    "phone": """
........
..kkkk..
..kwwk..
..kwwk..
..kwwk..
..kkkk..
........
........
""",
    "guest": """
........
.kkkk...
.kwwk.k.
.kwwkkk.
.kwwkk..
.kkkk...
........
........
""",
    "default": """
........
...kk...
...kk...
...kk...
........
...kk...
........
........
""",
}

# ─── animation ──────────────────────────────────────────────────────
# (axis, offsets) -- axis "y" bobs vertically, "x" sways horizontally.
# Offsets are one-pixel steps; 2..4 entries keep every icon at 2-4 frames.
ANIM = {
    "bed": ("y", (0, 1)),
    "sun": ("y", (0, -1, 0, 1)),
    "laptop": ("x", (0, 1)),
    "chart": ("y", (0, -1)),
    "coins": ("y", (0, 1)),
    "book": ("y", (0, -1)),
    "openbook": ("x", (0, 1)),
    "blackboard": ("y", (0, 1)),
    "pen": ("x", (0, 1)),
    "picture": ("y", (0, 1)),
    "pan": ("x", (0, 1)),
    "bowl": ("y", (0, 1)),
    "tv": ("y", (0, -1, 0, 1)),
    "ball": ("y", (0, -1)),
    "dumbbell": ("y", (0, -1, 0, 1)),
    "shower": ("y", (0, 1)),
    "hammer": ("y", (0, -1, 0, 1)),
    "bag": ("y", (0, 1)),
    "mountain": ("x", (0, 1)),
    "footprint": ("y", (0, -1)),
    "paw": ("x", (0, 1)),
    "bike": ("y", (0, 1)),
    "run": ("y", (0, -1)),
    "chat": ("y", (0, -1, 0, 1)),
    "house": ("y", (0, 1)),
    "balloon": ("y", (0, -1, 0, 1)),
    "heart": ("y", (0, -1, 0, 1)),
    "dots": ("x", (0, 1)),
    "star": ("y", (0, -1, 0, 1)),
    "note": ("x", (0, 1)),
    "brush": ("x", (0, 1)),
    "ghost": ("x", (0, 1)),
    "cross": ("y", (0, 1)),
    "hand": ("y", (0, -1)),
    "cup": ("y", (0, -1)),
    "bus": ("y", (0, 1)),
    "gamepad": ("y", (0, -1)),
    "wave": ("x", (0, 1)),
    "flower": ("y", (0, -1, 0, 1)),
    "broom": ("x", (0, 1)),
    "camera": ("y", (0, 1)),
    "fish": ("x", (0, 1)),
    "parcel": ("y", (0, 1)),
    "stall": ("y", (0, -1)),
    "phone": ("y", (0, -1)),
    "guest": ("y", (0, -1)),
    "default": ("y", (0, 1)),
}

# ─── action -> icon ─────────────────────────────────────────────────
ACTION_ICON = {
    "sleep": "bed", "nap": "bed", "wake": "sun",
    "work": "laptop", "overtime": "laptop", "freelance": "laptop",
    "stock": "chart", "invest": "chart",
    "save_money": "coins", "bank": "coins",
    "study": "book", "read": "openbook",
    "class": "blackboard", "tutor": "blackboard",
    "journal": "pen", "flyer": "pen",
    "exhibit": "picture",
    "cook": "pan", "bake": "pan",
    "eat_out": "bowl", "takeout": "bowl",
    "entertain": "tv", "movie": "tv",
    "watch_game": "ball",
    "gym": "dumbbell", "yoga": "dumbbell",
    "bath": "shower", "laundry": "shower",
    "decorate": "hammer",
    "shop": "bag", "grocery": "bag", "window_shop": "bag",
    "gift": "bag", "buy_clothes": "bag", "convenience": "bag",
    "travel": "mountain", "hike": "mountain",
    "stroll": "footprint",
    "walk_pet": "paw",
    "cycle": "bike", "delivery": "bike",
    "jog": "run",
    "social": "chat",
    "visit_friend": "house",
    "party": "balloon", "boardgame": "balloon",
    "date": "heart", "blind_date": "heart",
    "idle": "dots", "stargaze": "star",
    "sing": "note", "karaoke": "note", "listen": "note",
    "paint": "brush",
    "trick": "ghost",
    "sick": "cross", "checkup": "cross",
    "massage": "hand",
    "coffee": "cup", "drink": "cup",
    "commute": "bus",
    "gaming": "gamepad",
    "swim": "wave",
    "garden": "flower", "volunteer": "flower",
    "clean": "broom",
    "photo": "camera", "live_stream": "camera",
    "fish": "fish",
    "ship": "parcel",
    "stall": "stall",
    "call_friend": "phone",
}

DEFAULT_ICON = "default"

_cache = {}


def _rows(block):
    rows = [ln for ln in block.split("\n") if ln.strip()]
    if len(rows) != 8 or any(len(r) != 8 for r in rows):
        raise ValueError("bad icon art: %r" % (rows,))
    return rows


def _base(name):
    rows = _rows(ART.get(name) or ART[DEFAULT_ICON])
    im = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            col = PAL.get(ch)
            if col:
                px[x, y] = col + (255,)
    return im


def frames(name):
    """All animation frames of one icon (2-4 of them), 8x8, cached."""
    if name in _cache:
        return _cache[name]
    base = _base(name)
    axis, offs = ANIM.get(name, ANIM[DEFAULT_ICON])
    out = []
    for off in offs:
        if not off:
            out.append(base)
            continue
        im = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        dx = off if axis == "x" else 0
        dy = off if axis == "y" else 0
        # shift by cropping the strip and re-pasting: keeps the canvas 8x8
        box = (max(0, dx), max(0, dy), min(8, 8 + dx), min(8, 8 + dy))
        part = base.crop(box)
        im.alpha_composite(part, (-min(0, dx), -min(0, dy)))
        out.append(im)
    _cache[name] = out
    return out


def icon_name(action):
    return ACTION_ICON.get(action, DEFAULT_ICON)


def frame_at(action, t=0.0, fps=3.0):
    """Icon image for *action* at wall-clock t (cycles through its frames)."""
    if not action:
        return frames(DEFAULT_ICON)[0]
    name = icon_name(action)
    fr = frames(name)
    idx = int(max(0.0, t) * fps) % len(fr)
    return fr[idx]


def coverage():
    """Icons referenced by ACTION_ICON but missing ASCII art (tests)."""
    return sorted(set(ACTION_ICON.values()) - set(ART))
