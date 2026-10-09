#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hand-built pixel pets.

The Modern Interiors library has furniture and people but no animals, so the
cat / dog / bird are modelled here with plain draw primitives at pixel scale.
Each species is a tiny 4-frame loop: sitting idle, plus either a tail flick
(cat), a head bob (dog) or a hop (bird).  Keeping them under 14px wide matters --
anything bigger crowds the little person out of a 64px frame.
"""
import random

from PIL import Image, ImageDraw


class Pet(object):
    SPECIES = ("cat", "dog", "bird")
    SIZE = dict(cat=(12, 11), dog=(13, 10), bird=(9, 8))

    def __init__(self, species=None, rng=None):
        self.rng = rng or random.Random()
        self.species = species or self.rng.choice(self.SPECIES)
        self.frame = 0.0
        self.facing = 0                      # 0 right, 1 left
        self.x = 20.0
        self.y = 56.0                        # GROUND y (bottom of sprite)
        self.home = 20.0
        self.band = (8.0, 54.0)
        self.mode = "idle"
        self.timer = self.rng.uniform(1.5, 4.0)
        self.target = None
        self.speed = 5.0

    # ─── placement ──────────────────────────────────────────────────
    def place(self, x, y, band=(8.0, 54.0)):
        self.home = float(x)
        self.x = float(x)
        self.y = float(y)
        self.band = band

    # ─── behaviour ──────────────────────────────────────────────────
    def update(self, dt):
        self.frame = (self.frame + dt * 4.0) % 4
        self.timer -= dt
        if self.target is not None:
            d = self.target - self.x
            if abs(d) < 0.6:
                self.target = None
                self.timer = self.rng.uniform(2.0, 5.0)
            else:
                step = self.speed * dt
                self.x += step if d > 0 else -step
                self.facing = 0 if d > 0 else 1
        elif self.timer <= 0:
            ox = self.rng.uniform(-7.0, 7.0)
            lo, hi = self.band
            self.target = max(lo, min(hi, self.home + ox))
            self.timer = self.rng.uniform(3.0, 7.0)

    def sprite(self):
        im = getattr(self, "_draw_" + self.species)(int(self.frame) % 4)
        if self.facing == 1:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        return im

    def top_left(self):
        w, h = self.SIZE[self.species]
        return int(round(self.x)) - w // 2, int(round(self.y)) - h

    # ─── sprite builders ────────────────────────────────────────────
    @staticmethod
    def _draw_cat(f):
        im = Image.new("RGBA", (12, 11), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fur, dark, cream, eye = (233, 152, 74), (188, 108, 50), (250, 214, 168), (32, 24, 22)
        bob = 1 if f in (1, 3) else 0
        d.ellipse([1, 5 + bob, 8, 10], fill=fur)                     # body
        d.ellipse([1, 8, 8, 9], fill=cream)                          # chest light
        d.ellipse([5, 1 + bob, 10, 6 + bob], fill=fur)               # head
        d.polygon([(5, 3 + bob), (5, 0 + bob), (7, 2 + bob)], fill=fur)   # ears
        d.polygon([(8, 3 + bob), (10, 0 + bob), (10, 2 + bob)], fill=fur)
        d.point((7, 3 + bob), fill=eye)
        d.point((9, 3 + bob), fill=eye)
        d.point((8, 5 + bob), fill=(226, 138, 138))                  # nose
        tail = [(0, 9), (1, 8), (2, 7), (3, 6)] if f % 2 else [(1, 10), (2, 9), (3, 8), (4, 7)]
        d.line(tail, fill=dark, width=1)
        return im

    @staticmethod
    def _draw_dog(f):
        im = Image.new("RGBA", (13, 10), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fur, dark, cream, eye = (154, 108, 68), (112, 74, 42), (206, 170, 128), (32, 24, 22)
        bob = 1 if f % 2 else 0
        d.ellipse([1, 4, 9, 9], fill=fur)                            # body
        d.ellipse([1, 7, 9, 9], fill=cream)
        d.ellipse([7, 1 + bob, 12, 6 + bob], fill=fur)               # head
        d.polygon([(6, 2 + bob), (7, 6 + bob), (8, 4 + bob)], fill=dark)   # floppy ear
        d.ellipse([10, 4 + bob, 12, 6 + bob], fill=cream)            # snout
        d.point((11, 4 + bob), fill=eye)
        d.point((9, 3 + bob), fill=eye)
        wag = [(0, 7), (1, 5), (2, 4)] if f % 2 else [(0, 8), (1, 8), (2, 6)]
        d.line(wag, fill=dark, width=1)
        d.line([(3, 9), (3, 10)], fill=dark)                         # hind leg
        d.line([(7, 9), (7, 10)], fill=dark)
        return im

    @staticmethod
    def _draw_bird(f):
        im = Image.new("RGBA", (9, 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        body, wing, beak, eye = (86, 170, 214), (52, 122, 178), (240, 190, 70), (28, 24, 24)
        hop = 1 if f % 2 else 0
        d.ellipse([1, 2 + hop, 6, 7], fill=body)
        wingup = [(2, 4 + hop), (4, 2 + hop), (5, 5 + hop)] if f % 2 else [(2, 5 + hop), (4, 6 + hop), (5, 5 + hop)]
        d.polygon(wingup, fill=wing)
        d.ellipse([5, 1 + hop, 8, 4 + hop], fill=body)               # head
        d.polygon([(8, 2 + hop), (8, 3 + hop), (6, 3 + hop)], fill=beak)
        d.point((6, 2 + hop), fill=eye)
        d.line([(3, 7), (3, 7 + 0)], fill=beak)
        d.point((3, 7), fill=beak)
        d.point((5, 7), fill=beak)
        return im
