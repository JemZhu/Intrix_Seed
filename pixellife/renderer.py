#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Frame compositor v2: big room canvas -> camera window -> cast -> HUD -> marquee.

The world no longer fits on the panel. Each room is a MAP_W x MAP_H canvas
(176x80 by default); the camera is a 64x49 window that eases after the hero and
clamps to the map edges. Output is still one 64x64 RGB frame whose top 7 rows
are the stat/money HUD and whose bottom 8 rows are the marquee.
"""
import os
import random
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

from .assets import (Assets, get_assets, SCREEN, HUD_H, VIEW_Y, VIEW_H, VIEW_W)
from .characters import Actor
from .pets import Pet
from .subtitle import Subtitle
from .hud import draw_hud, text_img
from . import people
from . import icons
from .world import ACTIONS
from .social import default_emote as social_default

HERE = os.path.dirname(os.path.abspath(__file__))

# how dark the room gets at night, per hour (0 = noon, 1 = deepest night)
NIGHT_TINT = (16, 22, 48)

# v6.16: 会淋到雨的屋子。室内房间一律无特效 —— 隔着墙看不见雨。
OUTDOOR_ROOMS = ("outdoor", "beach", "rooftop", "garden")

# ─── who else is in the shot ────────────────────────────────────────
# Probability a second person shares the room. Cast is picked once per
# (room, action) pair and cached, so it never flickers between frames.
NPC_ROOMS = {
    "office": 0.85, "shop": 0.80, "gym": 0.45, "party": 0.95, "gallery": 0.45,
    "music": 0.35, "outdoor": 0.55, "beach": 0.40, "clinic": 0.80, "spooky": 0.30,
    "living": 0.20, "study": 0.12, "kitchen": 0.10,
    # v3 venues: crowded where crowds make sense, quiet in the reading room
    "cafe": 0.70, "library": 0.35, "classroom": 0.70, "subway": 0.85,
    "cinema": 0.65, "bank": 0.70, "market": 0.55, "arcade": 0.60,
    "bar": 0.80, "pool": 0.35, "rooftop": 0.25, "garden": 0.30,
}
# Actions that basically guarantee company.
SOCIAL_ACTIONS = ("social", "party", "travel", "shop", "walk_pet", "eat_out",
                  "date", "karaoke", "drink", "movie", "gaming", "coffee",
                  "class", "swim")

# Where the household critter hangs out.
PET_ROOMS = {
    "bedroom": 0.85, "living": 0.85, "kitchen": 0.50, "outdoor": 0.80,
    "beach": 0.75, "study": 0.40, "party": 0.45, "bath": 0.15, "gym": 0.20,
    "gallery": 0.20,
    # v3: the dog waits outside the bank, never in the pool
    "garden": 0.60, "cafe": 0.20, "market": 0.08, "subway": 0.10,
    "rooftop": 0.10, "arcade": 0.05, "classroom": 0.05, "library": 0.05,
}

# Character tags that only belong in the spooky room (pack.json "tags").
SPOOKY_TAG = "spooky"

# ─── speech bubbles ────────────────────────────────────────────────
# Two people within hailing distance stop, turn to each other and pop a bubble.
# One greeting per (visitor, 45s bucket), lasting 4 seconds, so they never
# stand there spamming "hi" forever.
GREET_RANGE_X, GREET_RANGE_Y = 26, 12
GREET_SECONDS = 6.0        # long enough to read a 4-character Chinese line
GREET_BUCKET = 45
# v6.6: 一句话说不完就连说 2-3 个气泡，谁说话谁冒泡，依次弹出。
# 每个气泡仍然只有 6 个汉字，所以 pop 出来的一定是完整的一句话。
BUBBLE_SECONDS = 2.6       # 一个气泡停留多久（够读完 6 个汉字）
MAX_BUBBLES = 3            # 每个人最多几个气泡（v6.7 起按人算，全场合计最多 6 个）
REGREET_GAP = 6.0          # 刚聊完就翻页的话，这个桶算聊过，别马上又来一轮
# relationship credit is granted far more slowly than the visual greeting
REL_BUCKET = 300
GREET_KINDS = ("heart", "note", "!", "dots", "hi", "?")
_ART = {
    "heart": (".##.##", "######", "######", ".####.", "..##.."),
    "note":  ("..##.", ".###.", ".###.", "###..", "##..."),
    "dots":  (".....", ".....", ".....", ".....", "#.#.#"),
}


def _art_img(rows, colour):
    h = len(rows)
    w = max(len(r) for r in rows)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != ".":
                px[x, y] = colour + (255,)
    return im


def _greet_inner(kind):
    if kind in ("hi", "!", "?"):
        return text_img(kind, (44, 38, 58))
    rows = _ART.get(kind) or _ART["dots"]
    colour = {"heart": (226, 74, 92), "note": (64, 132, 212)}.get(kind, (70, 70, 88))
    return _art_img(rows, colour)


_CJK_FONT = None


def cn_img(text, colour=(44, 38, 58), size=8):
    """Render a short Chinese line with the pixel TTF, for speech bubbles."""
    global _CJK_FONT
    text = (text or "").strip()
    if not text:
        return Image.new("RGBA", (0, 5), (0, 0, 0, 0))
    try:
        from PIL import ImageFont
        if _CJK_FONT is None:
            from .subtitle import FONT
            _CJK_FONT = ImageFont.truetype(FONT, size)
        box = _CJK_FONT.getbbox(text)
        w = max(1, box[2] - box[0])
        h = max(1, box[3] - box[1])
        im = Image.new("RGBA", (w + 1, h + 1), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((-box[0] + 1, -box[1]), text,
                                font=_CJK_FONT, fill=colour + (255,))
        return im
    except Exception:                                       # noqa: BLE001
        return Image.new("RGBA", (0, 5), (0, 0, 0, 0))


def bubble_img(inner, tint=None, body=(250, 250, 252)):
    """Wrap content in a speech bubble with a keyline and a small tail.

    `tint` recolours the outline so two people talking at once can be told apart
    at a glance. `body` recolours the fill -- v6.8 uses a pale yellow for the
    pose/state bubble so it never reads as speech.
    """
    w, h = inner.size
    edge = tint or (28, 24, 34)
    im = Image.new("RGBA", (w + 6, h + 7), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w + 5, h + 3], fill=body + (255,),
                outline=edge + (255,))
    im.alpha_composite(inner, (3, 2))
    d.line([2, h + 4, 6, h + 4], fill=body + (255,))
    d.point((3, h + 5), fill=body + (255,))
    for px_, py_ in ((2, h + 4), (6, h + 4), (1, h + 3), (7, h + 3)):
        if 0 <= px_ < im.size[0] and 0 <= py_ < im.size[1]:
            d.point((px_, py_), fill=edge + (255,))
    return im


# ─── v6.10: 动作气泡 ───────────────────────────────────────────────
# 浅黄色小气泡 = 像素小图标（2-4 帧循环动画）+ 黑色动作名，一眼可读。
# 走/站/坐/躺只是隐藏的体态属性，不再上气泡。优先级最低，给一切对话让路。
STATE_BODY = (255, 246, 196)
STATE_EDGE = (222, 178, 74)
STATE_TEXT = (0, 0, 0)


def state_bubble_img(text, action=None, t=0.0):
    glyph = icons.frame_at(action, t)
    label = cn_img(text, STATE_TEXT)
    gap = 2
    h = max(glyph.size[1], label.size[1])
    inner = Image.new("RGBA",
                      (glyph.size[0] + gap + label.size[0], h), (0, 0, 0, 0))
    inner.alpha_composite(glyph, (0, (h - glyph.size[1]) // 2))
    inner.alpha_composite(label,
                          (glyph.size[0] + gap, (h - label.size[1]) // 2))
    return bubble_img(inner, STATE_EDGE, body=STATE_BODY)


def speaker_tint(name):
    """A stable, muted outline colour per person (readable under any lamp)."""
    pal = [(196, 84, 96), (80, 132, 196), (96, 160, 104), (186, 132, 72),
           (146, 108, 186), (86, 158, 168), (176, 96, 150)]
    h = 0
    for ch in str(name):
        h = (h * 131 + ord(ch)) & 0xFFFF
    return pal[h % len(pal)]


def night_factor(now):
    """0.0 in full daylight, up to 0.62 in the small hours."""
    h = now.hour + now.minute / 60.0
    if 8.0 <= h < 17.0:
        return 0.0
    if h >= 21.0 or h < 5.0:
        return 0.62
    if 17.0 <= h < 21.0:
        return (h - 17.0) / 4.0 * 0.62
    return (8.0 - h) / 3.0 * 0.28


def _outline(sprite, colour=(20, 16, 26)):
    """Wrap a sprite in a 1px dark keyline.

    Without it the little person disappears into dark furniture (bookshelves, the
    gym rig) because both are drawn at the same brightness. Every decent pixel game
    does this; it costs one dilate pass.
    """
    a = np.asarray(sprite)[:, :, 3]
    solid = a > 40
    grown = solid.copy()
    grown[1:, :] |= solid[:-1, :]
    grown[:-1, :] |= solid[1:, :]
    grown[:, 1:] |= solid[:, :-1]
    grown[:, :-1] |= solid[:, 1:]
    ring = grown & ~solid
    out = Image.new("RGBA", sprite.size, colour + (255,))
    ring_im = Image.fromarray(np.where(ring, 255, 0).astype(np.uint8), "L")
    out.putalpha(ring_im)
    out.alpha_composite(sprite)
    return out


class Camera(object):
    """A 64x49 window that eases toward its target and clamps to the map."""

    def __init__(self):
        self.x = 0.0
        self.y = 0.0

    def snap(self, tx, ty, mw, mh):
        self.x = max(0.0, min(mw - VIEW_W, tx))
        self.y = max(0.0, min(mh - VIEW_H, ty))

    def follow(self, tx, ty, mw, mh, dt):
        gx = max(0.0, min(mw - VIEW_W, tx))
        gy = max(0.0, min(mh - VIEW_H, ty))
        k = min(1.0, dt * 3.2)
        self.x += (gx - self.x) * k
        self.y += (gy - self.y) * k
        if abs(gx - self.x) < 0.4:
            self.x = gx
        if abs(gy - self.y) < 0.4:
            self.y = gy

    def int_window(self, mw, mh):
        x = int(round(self.x))
        y = int(round(self.y))
        x = max(0, min(int(mw) - VIEW_W, x))
        y = max(0, min(int(mh) - VIEW_H, y))
        return x, y


class Renderer(object):
    def __init__(self, pack_dir=None, subtitle_speed=1):
        self.a = Assets(pack_dir) if pack_dir else get_assets()
        self.sub = Subtitle(SCREEN, 8, speed=subtitle_speed)
        self.cam = Camera()
        self.actor = None
        self.npc = None
        self.npc2 = None
        self.pet = None
        self._cast_key = None
        self._pet_key = None
        self._last_room = None
        self._zclock = 0.0
        self._greet = {}           # visitor name -> (bucket, kind, expiry)
        self._bubble_at = {}       # visitor name -> (bucket, 开讲时刻)
        self._rel_log = {}         # visitor name -> last relationship bucket
        self._rel_pip = None       # (expiry, delta, rank) for the "+3" bubble
        # v6.17: 忙里抽空 —— (名字, 45s桶) -> 这一轮要不要抽空聊，以及本帧结论
        self._busy_ok = {}
        self._frame_open = False

    # ─── bubbles ───────────────────────────────────────────────────
    # Several bubbles can be on screen at once (two visitors plus the hero plus a
    # money pip). Dropping them all "above the head" made them overlap into an
    # unreadable pile, so they are placed as a small packing problem instead:
    # highest priority wins the best slot, everything else steps around it.
    HEAD_H = 32

    @staticmethod
    def _hits(rect, reserved):
        x, y, w, h = rect
        for (rx, ry, rw, rh) in reserved:
            if x < rx + rw and rx < x + w and y < ry + rh and ry < y + h:
                return True
        return False

    def _layout_bubbles(self, view, items):
        """Place (priority, anchor_x, anchor_y, img) bubbles without overlaps.

        Highest priority picks first (money > relationship pip > speech), and
        each bubble scores every slot it could occupy: overlapping an already
        placed bubble costs heavily, drifting away from "right above the head"
        costs a little. That combination keeps speech where the eye expects it
        while still guaranteeing a legible layout when three people talk at once
        inside a 64x49 window.
        """
        placed = []
        reserved = []
        for prio, ax, ay, img in sorted(items, key=lambda e: -e[0]):
            w, h = img.size
            top = ay - self.HEAD_H - h
            cands = set()
            for k in range(0, 4):
                cands.add((ax - w // 2, top - k * (h - 2)))
            for dx in (-16, 16, -28, 28, -38, 38):
                cands.add((ax - w // 2 + dx, top))
                cands.add((ax - w // 2 + dx, ay - h - 4))
            for dx in (-14, 14):
                cands.add((ax - w // 2 + dx, ay - h // 2 - 6))
            cands.add((ax - w // 2, ay - 6 + 2))
            for gx in range(0, max(1, VIEW_W - w + 1), 8):
                for gy in range(0, max(1, VIEW_H - h + 1), 5):
                    cands.add((gx, gy))

            best, best_score = None, None
            best_overlap = 0
            for (cx, cy) in cands:
                cx = max(0, min(VIEW_W - w, int(round(cx))))
                cy = max(0, min(VIEW_H - h, int(round(cy))))
                overlap = 0
                for (rx, ry, rw, rh) in reserved:
                    ox = min(cx + w, rx + rw) - max(cx, rx)
                    oy = min(cy + h, ry + rh) - max(cy, ry)
                    if ox > 0 and oy > 0:
                        overlap += ox * oy
                if overlap:
                    # (has_overlap, cost): the two units must never mix, or a
                    # two-pixel graze (16) outranks a clean slot 27px away and
                    # the bubble gets dropped by the rule below.
                    score = (1, overlap * 8.0)
                else:
                    dx = (cx + w / 2.0) - ax
                    dy = (cy + h) - (ay - self.HEAD_H)
                    score = (0, (dx * dx + dy * dy) ** 0.5)
                if best_score is None or score < best_score:
                    best, best_score, best_overlap = (cx, cy), score, overlap
            if best is None:
                continue
            # Readability beats completeness: if even the best slot would cover
            # somebody else's words, this bubble simply does not appear. Only the
            # top-priority one is allowed to draw over anything.
            if best_overlap and reserved:
                continue
            placed.append((best, img))
            reserved.append((best[0], best[1], w, h))
        for (px, py), img in placed:
            view.alpha_composite(img, (px, py))
        return list(reserved)          # (x, y, w, h) for tests / debugging

    # kept for callers/tests that want a single bubble with the old semantics
    def _paste_bubble(self, view, img, sx, sy, head=None):
        self._layout_bubbles(view, [(0, sx, sy, img)])

    def _bubble_turn(self, npc, cur, seq, t):
        """Which bubble of this encounter is on screen right now.

        v6.6: a remark that does not fit one bubble is delivered as 2-3 short
        ones instead of a truncated line. v6.7: the 3-bubble budget is *per
        speaker*, so a chatty resident can finish all three of their lines and
        the encounter stretches to fit however many bubbles came back (up to
        six). The speaking clock starts the first frame the text is actually
        available -- the model answers ~1s after the two of them meet.
        """
        rec = self._bubble_at.get(npc.name)
        if rec is None or rec[0] != cur[0]:
            rec = (cur[0], t)
            self._bubble_at[npc.name] = rec
            need = t + len(seq) * BUBBLE_SECONDS + 0.8
            if cur[2] < need:
                self._greet[npc.name] = (cur[0], cur[1], need)
        idx = int(max(0.0, t - rec[1]) / BUBBLE_SECONDS)
        return seq[max(0, min(idx, len(seq) - 1))]

    # ─── LLM small talk ────────────────────────────────────────────
    def _gate_for(self, name, bucket, gate):
        """这一轮对这个人的实际对话门限。

        v6.17：`brief`（在上班 / 在专心做事）的时候，主角有 BUSY_CHAT_CHANCE
        的概率忙里抽空跟人搭两句 —— 那就按 open 走，让模型写真对话，而不是
        那句固定的「正忙着呢」。同一次偶遇只掷一次骰子（按 45s 桶缓存），
        否则同一轮里几个气泡之间会翻烧饼。
        """
        if gate != "brief":
            return gate
        rec = self._busy_ok.get(name)
        if rec is not None and rec[0] == bucket:
            return "open" if rec[1] else gate
        try:
            from .world import LifeWorld
            chance = float(LifeWorld.BUSY_CHAT_CHANCE)
        except Exception:                                       # noqa: BLE001
            chance = 0.5
        ok = self._roll(name, "busywork", bucket).random() < chance
        self._busy_ok[name] = (bucket, ok)
        if ok:
            self._frame_open = True
        return "open" if ok else gate

    @staticmethod
    def _request_line(world, now, npc_name, bucket, action, busy=False):
        """Ask the LLM for both sides of this encounter. Fire-and-forget.

        The prompt gets the resident's full persona + live stats + the current
        relationship score, which is what makes the same sprite behave like a
        different person in every save file.
        """
        try:
            from .social import chatter, greet_context
            from .world import ACTIONS, ROOM_CN
            st = world.state
            room = ROOM_CN.get(st.get("room"), st.get("room") or "")
            person = people.ensure(st, npc_name, world.rng) or {}
            score = float((person.get("rel") or {}).get("score", 0))
            rank = people.rank_of(score)
            if rank in ("知己", "挚友", "好朋友"):
                relation = "很熟的朋友"
            elif rank == "朋友":
                relation = "朋友"
            elif rank == "熟人":
                relation = "熟人"
            elif rank == "点头之交":
                relation = "认识但不熟"
            else:
                relation = "陌生人"
            label = ACTIONS.get(action, {}).get("label", action)
            if action in ("gift", "boardgame", "watch_game", "party", "date",
                          "visit_friend", "blind_date"):
                intent = "一起玩/一起待着"
            elif action in ("delivery", "flyer", "convenience", "tutor",
                            "convenience", "stall"):
                intent = "一起干活"
            elif action in ("work", "overtime", "commute", "class"):
                intent = "同事/同学碰面"
            else:
                intent = "路上偶遇"
            if busy:
                # v6.17: 掷到了"忙里抽空"——手上有活，但还是搭两句话，
                # 别让模型写成礼拒（那句由 brief_reply 兜底，不归它管）
                intent = "他手上有事在忙，这一轮是忙里抽空跟人搭两句话"
            else:
                try:
                    if world.chat_gate(action) == "brief":
                        intent = "他正专注做事，只简短打个招呼就好"
                except Exception:                           # noqa: BLE001
                    pass
            ctx = greet_context(world, now or datetime.now(), npc_name, room,
                                label, relation, person=person, intent=intent)
            chatter().ensure(npc_name, bucket, ctx,
                             forbidden=tuple(st.get("friends") or []) +
                                       (st.get("name") or "",))
        except Exception:                                   # noqa: BLE001
            pass

    @staticmethod
    def _greet_line(name, bucket):
        try:
            from .social import chatter
            return chatter().get(name, bucket)
        except Exception:                                   # noqa: BLE001
            return None

    def _persona(self, world, name):
        try:
            return people.ensure(world.state, name, world.rng) or {}
        except Exception:                                   # noqa: BLE001
            return {}

    def _social(self, t, action, world=None, now=None):
        """Bump into someone: stop, turn, say hi, and log the relationship.

        A greet is worth a little goodwill, but only once every few minutes per
        person -- otherwise standing next to somebody would farm the score.
        """
        hero_kind = None
        gate = "open"
        if world is not None:
            try:
                gate = world.chat_gate(action)
            except Exception:                               # noqa: BLE001
                gate = "open"
        if gate == "none":
            # v6.8: 睡觉/午睡/洗澡/看病/按摩不打扰，NPC 也不上前搭话
            self.actor.hold = max(self.actor.hold, 0.5)
            return None
        for npc in (self.npc, self.npc2):
            if npc is None:
                continue
            if (abs(npc.x - self.actor.x) > GREET_RANGE_X or
                    abs(npc.y - self.actor.y) > GREET_RANGE_Y):
                continue
            person = self._persona(world, npc.name) if world is not None else {}
            bucket = int(t // GREET_BUCKET)
            npc_gate = self._gate_for(npc.name, bucket, gate)
            cur = self._greet.get(npc.name)
            talk_again = cur is None
            if cur is not None and cur[0] != bucket:
                # 45 秒桶翻页了。v6.6 的一句话可能要拆成 2-3 个气泡说上八秒，
                # 所以翻页有三种处理方式，别让「这也太挤」在屏幕上说两遍。
                if t < cur[2]:
                    # 还在说：不打断，顺手把这轮记到新桶上，气泡节拍一起搬过去
                    self._greet[npc.name] = (bucket, cur[1], cur[2])
                    was = self._bubble_at.get(npc.name)
                    if was is not None:
                        self._bubble_at[npc.name] = (bucket, was[1])
                    cur = self._greet[npc.name]
                elif t <= cur[2] + REGREET_GAP:
                    # 刚散场就翻页：这个桶算聊过了，别马上又凑上来
                    self._greet[npc.name] = (bucket, cur[1], t)
                    cur = self._greet[npc.name]
                else:
                    talk_again = True
            if talk_again:
                r = self._roll(npc.name, "greet", bucket)
                # an introvert with a flat battery does not always stop to chat
                social = person.get("social")
                energy = (person.get("stats") or {}).get("energy", 70)
                skip = (social == "独来独往" and r.random() < 0.35) or \
                       (energy < 30 and r.random() < 0.4)
                kind = (r.choice(("dots", "?", "hi")) if skip
                        else (social_default(person) if person
                              else r.choice(GREET_KINDS)))
                self._greet[npc.name] = (bucket, kind, t + GREET_SECONDS)
                cur = self._greet[npc.name]
                if world is not None and not skip:
                    self._request_line(world, now, npc.name, bucket, action,
                                       busy=(gate == "brief" and
                                             npc_gate == "open"))
                    rl_bucket = int(t // REL_BUCKET)
                    if self._rel_log.get(npc.name) != rl_bucket:
                        self._rel_log[npc.name] = rl_bucket
                        try:
                            delta, score, rank, _before = world.meet(
                                npc.name, "chat" if action in SOCIAL_ACTIONS
                                else "greet")
                            if delta:
                                self._rel_pip = (t + 5.0, delta, rank)
                        except Exception:                   # noqa: BLE001
                            pass
            if t < cur[2]:                       # still talking
                kind = cur[1]
                hero_kind = "hi" if kind != "hi" else "!"
                npc.mode = "idle"
                npc.hold = 2.0
                npc.target_x = npc.target_y = None
                self.actor.mode = "idle"
                self.actor.hold = 2.0
                self.actor.target_x = self.actor.target_y = None
                npc.facing = 1 if npc.x > self.actor.x else 0
                self.actor.facing = 0 if npc.x > self.actor.x else 1
        return hero_kind

    # ─── setup ──────────────────────────────────────────────────────
    def ensure_actor(self, name):
        """Bind the hero. Old saves may name somebody who is no longer in the
        pack (the cast has been swapped twice); fall back instead of blanking."""
        if name and not self.a.has_char(name):
            name = self.a.default_char()
        if self.actor is None or self.actor.name != name:
            self.actor = Actor(name, random.Random(hash(name) & 0xFFFF))
            self._last_room = None           # force a camera snap

    def _roll(self, key, salt, bucket):
        """Seeded per cast slot. The bucket rolls over every few minutes so
        visitors come and go, while staying stable frame-to-frame (nothing
        flickers mid-conversation)."""
        return random.Random((hash((key, salt, bucket)) ^ 0x5F3A) & 0xFFFFFFFF)

    def _cast_people(self, world, room_id, action, bucket):
        r = self._roll(room_id, action, bucket)
        st = world.state
        mw, mh = self.a.map_size(room_id)
        x0, x1, y0, y1 = self.a.walk_bounds(room_id)

        self.npc = None
        self.npc2 = None
        # v6.12: 串门到居民家里时主人一定在场
        host = self._home_host(room_id)
        chance = 1.0 if host else NPC_ROOMS.get(room_id, 0.0)
        if action in SOCIAL_ACTIONS:
            chance = max(chance, 0.85)
        if action == "sleep":
            chance = 0.0
        if r.random() < chance:
            pool = self.a.char_names()
            if room_id == "spooky":
                tagged = self.a.char_names(SPOOKY_TAG)
                pool = tagged + [n for n in pool
                                 if SPOOKY_TAG not in self.a.char_info(n).get("tags", [])
                                 and "retired" not in self.a.char_info(n).get("tags", [])][:6]
            else:
                pool = [n for n in pool
                        if not self.a.char_info(n).get("tags", [])]
            options = [n for n in pool if n != st.get("avatar")]
            friends = [n for n in options if n in st.get("friends", [])]
            pick = host if (host in options) else self._pick_person(r, options, friends)
            if pick:
                people.ensure(st, pick, world.rng)
                self.npc = self._spawn_actor(r, pick, room_id, mw, x0, x1, y0, y1)
                # a second body only where a crowd makes sense -- never in a
                # resident's home, where the host is the whole point
                if not host and (action in ("party", "social")
                                 or room_id in ("office", "shop", "party")):
                    options = [n for n in options if n != pick]
                    pick2 = self._pick_person(r, options,
                                              [f for f in friends if f != pick])
                    if pick2 and r.random() < 0.55:
                        people.ensure(st, pick2, world.rng)
                        self.npc2 = self._spawn_actor(r, pick2, room_id, mw,
                                                      x0, x1, y0, y1)

    def _cast_pet(self, world, room_id, action, bucket):
        self.pet = None
        species = world.state.get("pet")
        chance = 1.0 if action == "walk_pet" else PET_ROOMS.get(room_id, 0.0)
        if action == "sleep":
            chance *= 0.5
        if not species:
            return
        r = self._roll(room_id, "pet", bucket)
        if r.random() < chance:
            p = Pet(species, r)
            mw, mh = self.a.map_size(room_id)
            _, _, y0, y1 = self.a.walk_bounds(room_id)
            ground = float(y1) - 1.0
            p.place(r.uniform(16.0, mw - 16.0), ground,
                    band=(10.0, mw - 10.0))
            self.pet = p

    def _home_host(self, room_id):
        """room 'home_lucy' -> 'Lucy'. 串门拜访时主人固定在场。"""
        if not room_id or not room_id.startswith("home_"):
            return None
        want = room_id[5:].lower()
        for n in self.a.char_names():
            if n.lower() == want:
                return n
        return None

    @staticmethod
    def _pick_person(r, options, friends):
        if not options:
            return None
        if friends and r.random() < 0.7:
            return r.choice(friends)
        return r.choice(options)

    def _spawn_actor(self, r, name, room_id, mw, x0, x1, y0, y1):
        act = Actor(name, r)
        act.bounds = (float(x0), float(x1), float(y0), float(y1))
        act.blocks = self.a.blockers(room_id)
        act.x = r.uniform(x0, x1)
        act.y = r.uniform(y0, y1)
        act.x, act.y = act.nudge(act.x, act.y)     # never spawn inside a shelf
        act.hold = r.uniform(0.5, 3.0)
        act.speed = r.uniform(9.0, 15.0)
        return act

    # ─── ambience overlays ──────────────────────────────────────────
    # ─── v6.16: 户外的雨雪 ──────────────────────────────────────────
    def _weather_fx(self, frame, kind, t):
        """雨/雪粒子，画在场景之上。

        用屏幕空间而不是世界坐标：雨雪本来就充满整个视野，跟着镜头平移反而
        会看出"贴图在动"。位置全部由 t 和粒子序号算出来，不需要保存状态，
        所以掉帧、重启都不会让雨滴跳位置。
        """
        if kind not in ("rain", "snow"):
            return frame
        d = ImageDraw.Draw(frame)
        W, H = frame.size
        if kind == "rain":
            for i in range(30):
                h = (i * 37) % 97
                spd = 130 + (h % 60)
                x = (i * 53 + int(t * 26)) % (W + 20) - 10
                y = int((t * spd + h * 11) % (H + 16)) - 8
                col = (132, 172, 220) if (i % 3) else (168, 200, 240)
                d.line([(x, y), (x - 1, y + 4)], fill=col)
            return frame
        for i in range(22):
            h = (i * 41) % 89
            spd = 14 + (h % 12)
            sway = ((i * 7 + int(t * 2)) % 5) - 2      # 不引 math，能飘就行
            x = (i * 37 + int(t * 6)) % (W + 12) - 6 + sway
            y = int((t * spd + h * 9) % (H + 10)) - 5
            col = (236, 242, 252) if (i % 4) else (206, 224, 244)
            d.point((x, y), fill=col)
            if i % 5 == 0:
                d.point((x + 1, y), fill=col)
        return frame

    def _apply_night(self, img, now, t, ax, ay):
        """Night tint; the lamp glow follows the hero's SCREEN position."""
        f = night_factor(now)
        if f <= 0.01:
            return img
        a = np.asarray(img.convert("RGB"), dtype=np.float32)
        tint = np.array(NIGHT_TINT, dtype=np.float32)
        a = a * (1.0 - f) + tint * f
        yy, xx = np.mgrid[0:VIEW_H, 0:VIEW_W]
        d = np.sqrt(((xx - ax) / 26.0) ** 2 + ((yy - ay) / 22.0) ** 2)
        glow = np.clip(1.0 - d, 0, 1) * 0.22 * (f / 0.62)
        a = np.clip(a + glow[:, :, None] * 255.0 * 0.9, 0, 255)
        return Image.fromarray(a.astype(np.uint8), "RGB")

    def _sick_mark(self, img, sx, sy, t):
        """A little pulsing thermometer pill above their head."""
        d = ImageDraw.Draw(img)
        x, y = int(sx) + 6, int(sy) - 12
        if not (0 <= x and x + 8 < SCREEN and 0 <= y and y + 12 < VIEW_H):
            return img
        d.rectangle([x, y, x + 8, y + 12], fill=(238, 238, 240))
        d.rectangle([x + 1, y + 1, x + 7, y + 11], fill=(224, 96, 96))
        bob = int(2 + 2 * (1 + (t * 2) % 2))
        d.rectangle([x + 3, y + 12 - bob, x + 5, y + 12], fill=(238, 238, 240))
        d.point((x + 2, y + 3), fill=(255, 255, 255))
        return img

    def _sleep_z(self, img, sx, sy, t):
        """Three drifting 'z' pixels while asleep."""
        base_x, base_y = int(sx) + 8, int(sy) - 2
        for i in range(3):
            ph = (t * 0.5 + i * 0.33) % 1.0
            x = base_x + int(ph * 8)
            y = base_y - int(ph * 10) - i * 2
            if 0 <= x < SCREEN - 1 and 0 <= y < VIEW_H:
                img.putpixel((x, y), (210, 220, 255))
                img.putpixel((x + 1, y), (140, 150, 190))
        return img

    # ─── cast drawing ───────────────────────────────────────────────
    def _draw_cast(self, view, kind, obj, camx, camy):
        """Paste one actor / pet with its keyline and contact shadow."""
        ox, oy = camx, camy
        if kind == "pet":
            sp = obj.sprite()
            x, y = obj.top_left()
            sp = _outline(sp)
            sh_w = max(6, sp.size[0] - 3)
            sh = Image.new("RGBA", (sh_w, 2), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([0, 0, sh_w - 1, 1], fill=(0, 0, 0, 80))
            view.alpha_composite(sh, (int(obj.x) - ox + 1, int(obj.y) - oy - 1))
            view.paste(sp, (x - ox, y - oy), sp)
            return

        sp = obj.sprite(self.a)
        if sp is None:
            return
        sp = _outline(sp)
        x, y = obj.top_left(self.a)
        # contact shadow so the sprite reads as standing ON the floor
        sh = Image.new("RGBA", (12, 3), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([0, 0, 11, 2], fill=(0, 0, 0, 90))
        view.alpha_composite(sh, (int(obj.x) - ox + 2, int(obj.y) - oy - 1))
        view.paste(sp, (x - ox, y - oy), sp)

    # ─── main ───────────────────────────────────────────────────────
    def build(self, world, now=None, dt=0.05, t=None):
        """Compose one frame. The caller owns world.tick(); this only draws."""
        now = now or datetime.now()
        t = time.time() if t is None else t
        st = world.state
        # v6.16: 外面的天气 —— 左上角那个小图标和户外的雨雪都从这里取。
        # feeds 拿不到数据时 weather 为 None，画面退化成原样，不会空。
        weather = None
        try:
            from . import feeds
            weather = feeds.get_feeds().weather()
        except Exception:                                   # noqa: BLE001
            weather = None

        room_id = st.get("room", "bedroom")
        if room_id not in self.a.room_ids():
            room_id = self.a.room_ids()[0]
        action = st.get("action", "idle")
        try:
            gate = world.chat_gate(action)
        except Exception:                                   # noqa: BLE001
            gate = "open"
        mw, mh = self.a.map_size(room_id)

        # visitors rotate every 10 min, the pet every 30
        people_key = (room_id, action, int(t) // 600)
        if people_key != self._cast_key:
            self._cast_people(world, room_id, action, int(t) // 600)
            self._cast_key = people_key
        pet_key = (room_id, int(t) // 1800)
        if pet_key != self._pet_key:
            self._cast_pet(world, room_id, action, int(t) // 1800)
            self._pet_key = pet_key

        for extra in (self.npc, self.npc2):
            if extra is not None:
                extra.update(dt, action)

        self.ensure_actor(st.get("avatar", st.get("name", "Alex")))
        if room_id != self._last_room:
            # new room: adopt its walk band + solid furniture, and shove out of
            # anything the current spot happens to sit inside
            self.actor.set_room_bounds(room_id, self.a)
            self.actor.x, self.actor.y = self.actor.nudge(self.actor.x, self.actor.y)
            self.actor.target_x = self.actor.target_y = None
            self.actor.mode = "idle"
            self._greet = {}
            self._bubble_at = {}
        try:
            hero_pose = world.pose_now()
        except Exception:                                   # noqa: BLE001
            hero_pose = None
        self._frame_open = False        # v6.17: 本帧有没有掷到"忙里抽空"
        hero_kind = self._social(t, action, world, now)
        if hero_pose == "move" and hero_kind:
            hero_pose = "stand"       # 打招呼时停下来，别边走边聊
        self.actor.update(dt, action, hero_pose)

        if self.pet is not None:
            self.pet.update(dt)

        if action in ("sleep", "nap"):
            # tuck them into the bed corner of the big map
            self.actor.pin(x=14.0, y=48.0)

        # ---- camera -------------------------------------------------
        tx = self.actor.x - VIEW_W / 2.0
        # 0.72 keeps the full 32px sprite (head included) inside the window at
        # the top of the walk band; 0.62 was tuned for the shorter XP sprites.
        ty = self.actor.y - VIEW_H * 0.72
        if room_id != self._last_room:
            self.cam.snap(tx, ty, mw, mh)
            self._last_room = room_id
        else:
            self.cam.follow(tx, ty, mw, mh, dt)
        camx, camy = self.cam.int_window(mw, mh)

        # ---- world window -------------------------------------------
        view = self.a.map(room_id).crop((camx, camy, camx + VIEW_W, camy + VIEW_H))

        # ---- depth-sorted cast: further up = further back ------------
        layers = []
        if self.pet is not None:
            layers.append((self.pet.y, "pet", self.pet))
        for extra in (self.npc, self.npc2):
            if extra is not None:
                layers.append((extra.y, "npc", extra))
        layers.append((self.actor.y, "actor", self.actor))
        for _y, kind, obj in sorted(layers, key=lambda e: e[0]):
            self._draw_cast(view, kind, obj, camx, camy)

        # ---- bubbles: greetings, then fresh money news ----------------
        # Everything that wants a bubble is collected first, then laid out with
        # collision avoidance, so two visitors talking at once stay legible.
        hero_line = None
        seq_talking = False
        items = []
        for npc in (self.npc, self.npc2):
            if npc is None:
                continue
            cur = self._greet.get(npc.name)
            if not cur or t >= cur[2]:
                continue
            npc_gate = self._gate_for(npc.name, cur[0], gate)
            tint = speaker_tint(npc.name)
            line = self._greet_line(npc.name, cur[0])
            seq = (line or {}).get("seq") or ()
            if seq:
                # v6.7: 谁说话谁冒泡，每人最多 3 个，依次弹出
                seq_talking = True
                turn = self._bubble_turn(npc, cur, seq, t)
                hero_turn = turn.get("who") == "hero"
                if hero_turn and npc_gate == "brief":
                    inner = cn_img(world.brief_reply(t))
                else:
                    inner = cn_img(turn.get("text") or "")
                if inner.size[0]:
                    ax = (self.actor.x if hero_turn else npc.x) - camx
                    ay = (self.actor.y if hero_turn else npc.y) - camy
                    items.append((2, ax, ay,
                                  bubble_img(inner,
                                             (86, 110, 176) if hero_turn
                                             else tint)))
                continue
            if line and line.get("hero") and not seq_talking:
                hero_line = (world.brief_reply(t) if npc_gate == "brief"
                             else line["hero"])
            inner = _greet_inner(cur[1])
            if inner.size[0]:
                items.append((1, npc.x - camx, npc.y - camy,
                              bubble_img(inner, tint)))
        led = st.get("last_money") or {}
        money_bubble = None
        if led and (t - led.get("ts", 0)) < 6.0:
            delta = int(led.get("delta", 0) or 0)
            if delta:
                col = (232, 78, 78) if delta > 0 else (86, 186, 96)
                money_bubble = bubble_img(text_img("%+d" % delta, col))
        if money_bubble is not None:
            # money is the headline: it takes the slot right above the head and
            # pushes the greeting line up rather than replacing it
            items.append((3, self.actor.x - camx, self.actor.y - camy - 6,
                          money_bubble))
        pip = self._rel_pip
        if pip and t < pip[0]:
            items.append((2, self.actor.x - camx, self.actor.y - camy,
                          bubble_img(text_img("+%d" % int(round(pip[1])),
                                              (236, 120, 168)),
                                     (196, 84, 120))))
        elif not seq_talking and hero_line:
            # 没有台词（或模型没答上来）时，退回两个人各冒一个表情图标
            inner = cn_img(hero_line)
            if inner.size[0]:
                items.append((2, self.actor.x - camx, self.actor.y - camy,
                              bubble_img(inner, (86, 110, 176))))
        elif not seq_talking and hero_kind:
            # 忙里抽空：这一帧只要掷到过一次"抽空聊两句"，就别再冒那句礼拒
            if gate == "brief" and not self._frame_open:
                items.append((2, self.actor.x - camx, self.actor.y - camy,
                              bubble_img(cn_img(world.brief_reply(t)),
                                         (86, 110, 176))))
            else:
                items.append((2, self.actor.x - camx, self.actor.y - camy,
                              bubble_img(_greet_inner(hero_kind),
                                         (86, 110, 176))))
        # v6.11: 动作气泡只给主角 —— 访客不挂动作气泡，画面才不拥挤
        # （访客的寒暄/对话气泡走上面那条路径，不受影响）
        act_label = ACTIONS.get(action, {}).get("label") or "活动"
        items.append((0, self.actor.x - camx, self.actor.y - camy,
                      state_bubble_img(act_label, action, t)))
        if items:
            self._layout_bubbles(view, items)

        frame = view.convert("RGB")

        # ---- v6.16: 户外的雨雪 ---------------------------------------
        if weather and st.get("room") in OUTDOOR_ROOMS:
            frame = self._weather_fx(frame, weather.get("effect"), t)

        # ---- overlays anchored to the hero's screen position --------
        ax = int(round(self.actor.x)) - camx
        ay = int(round(self.actor.y)) - camy          # y inside the VIEW crop
        frame = self._apply_night(frame, now, t, ax, max(8, ay - 14))
        if action == "sleep":
            frame = self._sleep_z(frame, ax, ay, t)
        elif action == "sick":
            frame = self._sick_mark(frame, ax, ay - 16, t)

        # ---- assemble the 64x64 panel -------------------------------
        panel = Image.new("RGB", (SCREEN, SCREEN), (12, 11, 16))
        panel.paste(frame, (0, VIEW_Y))

        # ---- top 7px: stat gauges + money ---------------------------
        draw_hud(panel, st, weather)

        # ---- bottom 8px: marquee ------------------------------------
        # The band must ALWAYS carry the clock. Every line therefore comes out
        # of world.status_caption(), which folds the LLM's inner monologue in as
        # one of its six rotation phases -- with the HH:MM prefix intact.
        # Reading st["llm_caption"] straight into the marquee (as an earlier
        # version did) replaced the whole line, so once the model had written
        # anything the time vanished from the panel for hours.
        if action == "sleep":
            caption = "%s 睡着了，梦里还在算收益" % world.time_label(now)
        elif action == "sick":
            caption = "%s 身体不太舒服，来看看医生" % world.time_label(now)
        else:
            caption = world.status_caption(now)
        cap_col = (238, 242, 248)
        try:
            from .world import CAP_COLOURS
            cap_col = CAP_COLOURS.get(world.caption_colour(now), cap_col)
        except Exception:                                   # noqa: BLE001
            pass
        # v6.17: 底栏字幕速度可调（面板滑块，值存在 world.state 里）
        try:
            self.sub.speed = world.sub_speed()
        except Exception:                                       # noqa: BLE001
            pass
        self.sub.set_text(caption, cap_col)
        self.sub.tick()
        panel.paste(self.sub.render(), (0, VIEW_Y + VIEW_H))
        return panel

    def render_rgb565(self, world, now=None, dt=0.05, t=None):
        img = self.build(world, now, dt, t)
        a = np.asarray(img, dtype=np.uint16)
        v = ((a[:, :, 0] >> 3) << 11) | ((a[:, :, 1] >> 2) << 5) | (a[:, :, 2] >> 3)
        return v.astype("<u2").tobytes()
