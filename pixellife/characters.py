#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The pixel person's on-screen presence: position, facing and animation state.

v2: actors live in WORLD coordinates on the big room canvas (up to 176x80) and
the camera follows them; the 64px screen is just a window. Movement is the same
stroll logic as before -- pick a spot, walk there, idle, repeat -- but the spots
now span the whole map, so a trip across the room takes real time and the camera
has something to do.

Sprite sources (pack.json carries the geometry per character):
  kind "mi": 16-wide strips, foot at row 31, facing via mirroring.
  kind "xp": idle.png (facing viewer) + walk.png (0..3 right, 4..7 left).
"""
import random

from .assets import FEET_HALF_W, FEET_H

from PIL import Image


def _sit_pose(im):
    """v6.9 坐下：下半身纵向压缩到 50%，整个人保留（裁剪会只剩半个身子）。"""
    w, h = im.size
    split = int(h * 0.625)               # 腰线：32px 素材约在第 20 行
    low_h = h - split
    squash = max(2, low_h // 2)          # 下半身压到一半
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y0 = h - (split + squash)            # 底边仍贴地，top_left 无需改动
    out.alpha_composite(im.crop((0, 0, w, split)), (0, y0))
    low = im.crop((0, split, w, h)).resize((w, squash), Image.NEAREST)
    out.alpha_composite(low, (0, y0 + split))
    return out


def _lie_pose(im):
    """v6.8 躺下：侧转 90°，头朝左，背贴地面线。"""
    return im.transpose(Image.ROTATE_90)


class Actor(object):
    FPS = 12

    def __init__(self, name, rng=None):
        self.name = name
        self.rng = rng or random.Random()
        self.x = 32.0          # centre x, world pixels
        self.y = 54.0          # FOOT y, world pixels
        self.facing = 0        # 0 right, 1 left
        self.mode = "idle"     # idle | run
        self.action = "idle_anim"
        self.frame = 0.0
        self.target_x = None
        self.target_y = None
        self.hold = 1.2
        self.speed = 11.0      # px per second
        self.pose = "stand"    # v6.8: move | stand | sit | lie
        self._frame_size = None
        self.bounds = (6.0, 58.0, 26.0, 55.0)
        self.blocks = ()       # solid furniture boxes, set with the room

    # the room's walk band and solid furniture both come straight from the pack,
    # so adding a room never means touching this file
    def set_room_bounds(self, room_id, assets=None):
        if assets is not None:
            try:
                x0, x1, y0, y1 = assets.walk_bounds(room_id)
                self.bounds = (float(x0), float(x1), float(y0), float(y1))
                self.blocks = assets.blockers(room_id)
                return
            except Exception:
                pass
        self.bounds = self.bounds

    # ─── collision ─────────────────────────────────────────────────
    def blocked(self, x, y):
        """True if the feet box at (x, y) overlaps solid furniture."""
        fx0, fx1 = x - FEET_HALF_W, x + FEET_HALF_W
        fy0, fy1 = y - FEET_H, y
        for (x0, y0, x1, y1) in self.blocks:
            if fx1 > x0 and fx0 < x1 and fy1 > y0 and fy0 < y1:
                return True
        return False

    def _pick_target(self, x0, x1, y0, y1):
        """Find a reachable spot: neither the goal nor the path may clip props."""
        for _ in range(12):
            tx = self.rng.uniform(x0, x1)
            ty = self.rng.uniform(y0, y1)
            if self.blocked(tx, ty):
                continue
            # sample the straight-line path; a blocked midpoint means we would
            # walk straight through a bookshelf on the way there
            if any(self.blocked(self.x + (tx - self.x) * f,
                                self.y + (ty - self.y) * f)
                   for f in (0.3, 0.6, 0.85)):
                continue
            return tx, ty
        return None

    def nudge(self, x, y):
        """Shove out of a prop (used right after a room change / spawn).

        Wide pieces (a shop counter) can swallow the spawn point entirely, so the
        last resort is a coarse scan of the walk band for the nearest free spot.
        """
        if not self.blocked(x, y):
            return x, y
        for dx, dy in ((0, 4), (0, 8), (-8, 0), (8, 0), (0, 14), (-14, 0), (14, 0)):
            if not self.blocked(x + dx, y + dy):
                return x + dx, y + dy
        x0, x1, y0, y1 = self.bounds
        best, bestd = None, None
        gx = x0 + FEET_HALF_W
        while gx <= x1 - FEET_HALF_W:
            gy = y0
            while gy <= y1:
                if not self.blocked(gx, gy):
                    d = (gx - x) ** 2 + (gy - y) ** 2
                    if bestd is None or d < bestd:
                        bestd, best = d, (gx, gy)
                gy += 4
            gx += 6
        return best if best else (x, y)

    def pin(self, x=None, y=None):
        """Freeze in place (used while asleep)."""
        self.target_x = None
        self.target_y = None
        self.mode = "idle"
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y

    def update(self, dt, action_key, pose=None):
        """v6.8: 增加体态。pose 显式传入（主角，由 POSE_PLAN 驱动）；
        不传则自动：走路=move，到站后三成概率坐下（NPC）。"""
        if pose is not None:
            self.pose = pose
        elif self.mode == "run" or self.target_x is not None:
            self.pose = "move"
        seated = self.pose in ("sit", "lie")
        if pose is None and seated:
            # 自动体态的人坐一会儿要起来走走
            self.hold -= dt
            if self.hold <= 0:
                self.pose = "stand"
                self.hold = self.rng.uniform(1.5, 4.0)
                seated = False
        if seated and self.target_x is not None:
            self.target_x = self.target_y = None
            self.mode = "idle"
        moving = action_key not in ("sleep",) and not seated
        if not moving:
            self.action = "idle"
            self.frame = (self.frame + dt * self.FPS) % 4
            return

        if self.mode == "run" and self.target_x is not None:
            dx = self.target_x - self.x
            dy = (self.target_y - self.y) if self.target_y is not None else 0.0
            dist = max(1e-6, (dx * dx + dy * dy) ** 0.5)
            if dist < 1.2:
                self.mode = "idle"
                self.hold = self.rng.uniform(1.5, 4.5)
                self.target_x = self.target_y = None
                # v6.8: 到站歇脚，三成概率坐下（NPC 坐姿的来源）
                self.pose = "sit" if self.rng.random() < 0.3 else "stand"
            else:
                step = min(dist, self.speed * dt)
                nx = self.x + dx / dist * step
                ny = self.y + dy / dist * step
                # axis-separated: slide along a wall instead of stopping dead,
                # but give up on the goal if both axes are blocked
                moved = False
                if not self.blocked(nx, self.y):
                    self.x = nx
                    moved = True
                if not self.blocked(self.x, ny):
                    self.y = ny
                    moved = True
                if not moved:
                    self.mode = "idle"
                    self.hold = self.rng.uniform(0.6, 1.6)
                    self.target_x = self.target_y = None
                elif abs(dx) > 0.8:
                    self.facing = 0 if dx > 0 else 1
        else:
            self.hold -= dt
            if self.pose == "move" and self.hold > 0.6:
                self.hold = 0.4          # 体态是“移动”就尽快起步
            if self.hold <= 0:
                x0, x1, y0, y1 = self.bounds
                got = self._pick_target(x0, x1, y0, y1)
                if got is None:
                    self.hold = 1.5          # boxed in; try again shortly
                else:
                    self.target_x, self.target_y = got
                    self.mode = "run"

        if self.mode == "run":
            self.action = "run"
            self.frame = (self.frame + dt * self.FPS) % 8
        else:
            self.action = "idle_anim"
            self.frame = (self.frame + dt * self.FPS) % 4

    def sprite(self, assets):
        fr = self.frame
        im = assets.char_frame(self.name, self.action, self.facing, fr)
        if im is None:
            im = assets.char_frame(self.name, "idle_anim", self.facing, fr)
        if im is not None:
            self._frame_size = im.size
            if self.pose == "sit":
                im = _sit_pose(im)
            elif self.pose == "lie":
                im = _lie_pose(im)
        return im

    def top_left(self, assets=None):
        """Sprite origin so the FOOT lands on (x, y)."""
        foot = assets.char_foot(self.name) if assets is not None else 31
        sp_w = assets.char_info(self.name).get("fw", 16) if assets is not None else 16
        if self.pose == "lie" and self._frame_size:
            # 躺姿画布是旋转过的：宽=原高、高=原宽；整体右偏一点，
            # 让头（旋转后在左侧）不被 64px 窗口裁掉
            fw_, fh_ = self._frame_size
            return (int(round(self.x)) - fh_ // 2 + (fh_ - fw_) // 4,
                    int(round(self.y)) - fw_ + 1)
        return int(round(self.x)) - sp_w // 2, int(round(self.y)) - foot
