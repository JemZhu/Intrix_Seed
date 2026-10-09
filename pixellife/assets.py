#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PixelLife asset loader.

Reads the pack produced by build_pack.py. Deliberately dependency-light (PIL +
json only) because it has to run on the macOS box under /usr/bin/python3.

v2: rooms are now MAP_W x MAP_H canvases the camera pans across; characters
come in two flavours ("mi" = old 16x32 side-view strips, "xp" = RMXP sheets
pre-scaled to 16px wide with idle.png + walk.png).
"""
import os
import json

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, "pack")

SCREEN = 64
HUD_H = 7          # top status band
SUB_H = 8          # bottom marquee band
VIEW_Y = HUD_H
VIEW_H = SCREEN - HUD_H - SUB_H        # 49 -- the camera window height
VIEW_W = SCREEN
WALL_H = 16
MAP_W = 176        # world canvas per room (>= 2x the viewport)
MAP_H = 80
PLAY_H = VIEW_Y + VIEW_H               # 56 -- legacy alias (scene + hud rows)

# Collision: a walker's feet box is ~10x6 px, drawn just above its foot line.
FEET_HALF_W = 5
FEET_H = 6
FEET_REACH = 26                        # props whose bottom ends above this are wall decor
FLAT_DECOR = ("rug_", "i_win", "i_door", "rug", "plant2")


class Assets(object):
    def __init__(self, pack_dir=PACK):
        self.dir = pack_dir
        with open(os.path.join(pack_dir, "pack.json"), encoding="utf-8") as f:
            self.index = json.load(f)
        self.meta = self.index["meta"]
        self._rooms = {}
        self._maps = {}
        self._chars = {}
        self._props = {}
        self._blockers = {}

    # ---- rooms ----
    def room_ids(self):
        return sorted(self.index["rooms"].keys())

    def room(self, rid):
        """Top-left 64x64 of the room map (kept for previews / old callers)."""
        if rid not in self._rooms:
            self._rooms[rid] = self.map(rid).crop((0, 0, SCREEN, SCREEN)).copy()
        return self._rooms[rid]

    def map(self, rid):
        """Full MAP_W x MAP_H room canvas, cached."""
        if rid not in self._maps:
            p = os.path.join(self.dir, "maps", "%s.png" % rid)
            if not os.path.exists(p):                    # pack predates maps
                p = os.path.join(self.dir, "rooms", "%s.png" % rid)
            self._maps[rid] = Image.open(p).convert("RGBA").copy()
        return self._maps[rid]

    def room_info(self, rid):
        return self.index["rooms"].get(rid)

    def walk_bounds(self, rid):
        info = self.room_info(rid) or {}
        w = info.get("walk") or [6, 58, 26, 55]
        return tuple(w)

    def map_size(self, rid):
        info = self.room_info(rid) or {}
        return (info.get("map_w", MAP_W), info.get("map_h", MAP_H))

    # ---- collision ------------------------------------------------
    # Wall-mounted / flat decorations must NOT block: the walker only ever
    # collides with its feet box, so anything whose bottom edge never reaches
    # the floor band (or which is explicitly a rug) is filtered out.
    def blockers(self, rid):
        """Solid furniture boxes [(x0, y0, x1, y1), ...] for one room."""
        if rid in self._blockers:
            return self._blockers[rid]
        out = []
        for p in (self.room_info(rid) or {}).get("props", []):
            key = "%s/%s" % (p.get("theme", ""), p.get("idx", ""))
            if any(k in key for k in FLAT_DECOR):
                continue
            x, y = int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)
            w, h = int(p.get("w", 0) or 0), int(p.get("h", 0) or 0)
            if w <= 1 or h <= 1:
                continue
            if y + h < FEET_REACH:        # hangs on the wall, feet never get there
                continue
            if w * h > 2600:              # full-screen deco (sky, sand, pool fill)
                continue
            out.append((x, y, x + w, y + h))
        self._blockers[rid] = out
        return out

    # ---- characters ----
    def char_names(self, tag=None):
        names = sorted(self.index["chars"].keys())
        if tag is None:
            return names
        return [n for n in names if tag in self.index["chars"][n].get("tags", [])]

    def char_info(self, name):
        return self.index["chars"].get(name) or {}

    def has_char(self, name):
        return bool(name) and name in self.index["chars"]

    def default_char(self):
        """A cast member that definitely exists (for unknown save names)."""
        for pref in ("Alex", "Lucy", "Molly", "Dan", "Rob", "Roki"):
            if pref in self.index["chars"]:
                return pref
        return self.char_names()[0]

    def char_sheet(self, name, action):
        key = (name, action)
        if key not in self._chars:
            p = os.path.join(self.dir, "chars", name, "%s.png" % action)
            if not os.path.exists(p):
                return None
            self._chars[key] = Image.open(p).convert("RGBA").copy()
        return self._chars[key]

    def char_frame(self, name, action, facing, frame):
        """One sprite. Dispatches on the pack entry kind.

        mi: strips are 16 wide, row-less; facing by mirroring.
        xp: idle.png = 4 facing-viewer frames; walk.png = 8 frames
            (0..3 right, 4..7 left).
        """
        info = self.char_info(name)
        if info.get("kind") == "xp":
            act = "walk" if action in ("run", "walk") else "idle"
            sh = self.char_sheet(name, act)
            if sh is None:
                return None
            fw = info.get("fw", 16)
            fh = info.get("fh", sh.size[1])
            n = sh.size[0] // fw
            if n <= 0:
                return None
            fr = int(frame) % n
            im = sh.crop((fr * fw, 0, fr * fw + fw, fh))
            if act == "idle" and facing:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            return im

        sh = self.char_sheet(name, action)
        if sh is None:
            return None
        fw = info.get("fw", 16)
        n = sh.size[0] // fw
        if n <= 0:
            return None
        fr = int(frame) % n
        im = sh.crop((fr * fw, 0, fr * fw + fw, sh.size[1]))
        if facing:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        return im

    def char_frame_count(self, name, action):
        sh = self.char_sheet(name, action)
        if sh is None:
            return 0
        fw = self.char_info(name).get("fw", 16)
        return sh.size[0] // fw

    def char_foot(self, name):
        """Foot line (y offset inside the frame) for world anchoring."""
        info = self.char_info(name)
        return info.get("foot", 31)

    # ---- free props ---- (for room decoration / shopping)
    def prop(self, key):
        if key not in self._props:
            p = os.path.join(self.dir, "props", "%s.png" % key)
            if not os.path.exists(p):
                return None
            self._props[key] = Image.open(p).convert("RGBA").copy()
        return self._props[key]

    def prop_keys(self):
        return sorted(self.index["props"].keys())


_INSTANCE = None


def get_assets():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Assets()
    return _INSTANCE
