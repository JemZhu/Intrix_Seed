#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Top HUD band: weather + two stat gauges + money, 64x7.

v6.16 重排：左上角让给"外面什么天"——一个 5x5 的天气符号加当天最高/最低温
（外面下雨还是下雪，小人自己该看得见）。原本五个仪表横排的长度放不下，
所以精简成两个最要紧的：体力与心情。其余三个（健康/饱腹/魅力）仍在底栏
播报和后台面板里，只是不再挤在头顶这条 7 像素的带子上。

Layout (7 rows, y=0..6):
    x 1..5     天气符号 5x5
    x 6..~25   最高/最低温，如 26/14（3x5 微字体）
    x ~27..44  两个仪表 [icon 4px | 1px gap | bar 4px]：体力、心情
    x 48..63   金钱，最多 4 个字形
"""
import time

from PIL import Image, ImageDraw

HUD_H = 7
BG = (10, 10, 16, 214)

# 表头只留这两个（v6.16）。顺序即绘制顺序。
HUD_GAUGE_KEYS = ("energy", "happiness")

# stat key -> 图标色 / 条色。底栏播报也按这张表取关键词颜色，别再重复定义。
GAUGE_COLOURS = {
    "health":    (240, 84, 96),
    "happiness": (248, 196, 80),
    "hunger":    (120, 205, 96),
    "energy":    (96, 186, 240),
    "charm":     (232, 122, 204),
}

# stat key, icon colour, bar colour
GAUGES = [
    ("health",    GAUGE_COLOURS["health"],    (235, 72, 88)),
    ("happiness", GAUGE_COLOURS["happiness"], (244, 182, 60)),
    ("hunger",    GAUGE_COLOURS["hunger"],    (104, 192, 84)),
    ("energy",    GAUGE_COLOURS["energy"],    (72, 172, 236)),
    ("charm",     GAUGE_COLOURS["charm"],     (222, 104, 194)),
]
GAUGE_BY_KEY = {k: (i, b) for k, i, b in GAUGES}

BAR_BORDER = (58, 58, 70, 255)
BAR_EMPTY = (28, 28, 36, 255)
GOLD = (252, 208, 92)
GOLD_DIM = (196, 156, 64)
TEMP_COL = (216, 222, 232)

# ─── 3x5 micro font ─────────────────────────────────────────────────
GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ".": ("000", "000", "000", "000", "010"),
    "k": ("000", "101", "110", "101", "101"),
    "m": ("000", "111", "111", "101", "101"),
    "h": ("100", "110", "101", "101", "101"),
    "i": ("010", "000", "010", "010", "010"),
    "!": ("010", "010", "010", "000", "010"),
    "?": ("111", "001", "011", "000", "010"),
    "o": ("010", "101", "101", "101", "010"),
    "e": ("111", "100", "110", "100", "111"),
    "y": ("101", "101", "111", "001", "111"),
    "a": ("111", "101", "111", "101", "101"),
    "u": ("101", "101", "101", "101", "111"),
    "n": ("110", "101", "101", "101", "101"),
    "s": ("111", "100", "111", "001", "111"),
    "t": ("111", "010", "010", "010", "010"),
    "+": ("000", "010", "111", "010", "000"),
    "-": ("000", "000", "111", "000", "000"),
    # v6.16：天气那块用得到，横杠比斜杠更省位置（26/14 好认）
    "/": ("001", "001", "010", "100", "100"),
    "~": ("000", "010", "101", "000", "000"),
}

# ─── 4x4 stat icons ────────────────────────────────────────────────
ICONS = {
    "health":    ("#..#", "####", ".##.", "...."),      # heart
    "happiness": (".##.", "#..#", "#..#", ".##."),      # face
    "hunger":    ("#.#.", "#.#.", ".#..", ".#.."),      # fork
    "energy":    ("..##", ".##.", "##..", "#..."),      # bolt
    "charm":     (".##.", "####", ".##.", "...."),      # gem
}

# ─── 5x5 weather glyphs ('#' = ink) ────────────────────────────────
WEATHER_ICONS = {
    "sun":       ("..#..", ".###.", "#####", ".###.", "..#.."),
    "sun_cloud": ("...#.", "..##.", "###..", "####.", "....."),
    "cloud":     (".....", ".##..", "#####", "#####", "....."),
    "fog":       (".....", "#####", ".....", "####.", "....."),
    "rain":      (".###.", "#####", ".....", ".#.#.", "#.#.."),
    "snow":      (".###.", "#####", ".....", "#.#.#", ".#.#."),
    "storm":     (".###.", "#####", "..#..", ".##..", "#...."),
}
WEATHER_COLOURS = {
    "sun":       (255, 210, 74),
    "sun_cloud": (255, 214, 120),
    "cloud":     (196, 204, 214),
    "fog":       (170, 178, 188),
    "rain":      (108, 176, 240),
    "snow":      (222, 240, 255),
    "storm":     (168, 150, 244),
}


def weather_temp_text(w):
    """最高/最低，如 26/14；只有实时温度就只显示那一个。"""
    if not w:
        return ""
    tmax, tmin = w.get("tmax"), w.get("tmin")
    if tmax is not None and tmin is not None:
        return "%d/%d" % (tmax, tmin)
    if w.get("temp") is not None:
        return "%d" % w["temp"]
    return ""


def format_money(v):
    """<=4 glyphs: 8420 / 12k / 1.2M."""
    try:
        v = int(round(float(v)))
    except Exception:                                       # noqa: BLE001
        v = 0
    v = max(0, v)
    if v < 10000:
        return str(v)
    if v < 1000000:
        return "%dk" % round(v / 1000.0)
    if v < 10000000:
        return "%.1fM" % (v / 1000000.0)
    return "%dM" % round(v / 1000000.0)


def _glyph_img(ch, colour):
    rows = GLYPHS.get(ch)
    im = Image.new("RGBA", (4, 5), (0, 0, 0, 0))
    if not rows:
        return im
    px = im.load()
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != "0":
                px[x, y] = colour + (255,)
    return im


def glyph_img(ch, colour):
    """Public alias -- the renderer draws bubbles with the same micro font."""
    return _glyph_img(ch, colour)


def text_img(s, colour, spacing=1):
    """A one-line RGBA strip of micro glyphs, for speech / money bubbles."""
    s = (s or "").lower()
    if not s:
        return Image.new("RGBA", (0, 5), (0, 0, 0, 0))
    out = Image.new("RGBA", (len(s) * (3 + spacing), 5), (0, 0, 0, 0))
    x = 0
    for ch in s:
        out.alpha_composite(_glyph_img(ch, colour), (x, 0))
        x += 3 + spacing
    return out


def _draw_weather(d, band, w, x0=1):
    """画天气块，返回下一个可用 x。"""
    if not w:
        return x0
    icon = w.get("icon") if w.get("icon") in WEATHER_ICONS else "cloud"
    rows = WEATHER_ICONS[icon]
    col = WEATHER_COLOURS.get(icon, (200, 206, 216))
    for gy, row in enumerate(rows):
        for gx, c in enumerate(row):
            if c == "#":
                d.point((x0 + gx, 1 + gy), fill=col + (255,))
    x = x0 + 6
    txt = weather_temp_text(w)
    for ch in txt:
        band.alpha_composite(_glyph_img(ch, TEMP_COL), (x, 1))
        x += 4
    return x + 2 if txt else x + 1


def _draw_gauge(d, x, key, value):
    icol, bcol = GAUGE_BY_KEY.get(key, ((200, 200, 200), (180, 180, 180)))
    rows = ICONS.get(key, ICONS["health"])
    for gy, row in enumerate(rows):
        for gx, c in enumerate(row):
            if c == "#":
                d.point((x + gx, 1 + gy), fill=icol + (255,))
    bx = x + 5
    d.rectangle([bx, 1, bx + 3, 5], fill=BAR_EMPTY, outline=BAR_BORDER)
    fill = int(round(value / 100.0 * 3))
    if value > 4 and fill == 0:
        fill = 1
    if fill > 0:
        d.rectangle([bx + 1, 5 - fill, bx + 2, 4], fill=bcol + (255,))


def draw_hud(frame, state, weather=None):
    """Composite the 7px HUD band onto the top of a 64x64 RGB frame."""
    band = Image.new("RGBA", (frame.size[0], HUD_H), BG)
    d = ImageDraw.Draw(band)

    # ---- 天气（左上角）---------------------------------------------
    x = _draw_weather(d, band, weather) if weather else 1

    # ---- 两个仪表：体力、心情 ---------------------------------------
    # 金钱占最右，天气块可能把位置吃掉，所以按剩余宽度决定画几个
    room = frame.size[0] - x - 17
    slots = max(1, min(len(HUD_GAUGE_KEYS), room // 9))
    for key in HUD_GAUGE_KEYS[:slots]:
        v = state.get(key, 50)
        try:
            v = float(v)
        except Exception:                                   # noqa: BLE001
            v = 50.0
        _draw_gauge(d, x, key, max(0.0, min(100.0, v)))
        x += 9

    # ---- money ------------------------------------------------------
    # A fresh ledger entry flashes the readout and shows a red UP / green DOWN
    # pip (Chinese market colour convention: red = gain, green = spend).
    lm = state.get("last_money") or {}
    fresh = lm and (time.time() - lm.get("ts", 0)) < 5.0
    delta = int(lm.get("delta", 0) or 0) if fresh else 0
    txt = format_money(state.get("wealth", 0))
    gx = frame.size[0] - len(txt) * 4 - 1
    col = GOLD if state.get("wealth", 0) else GOLD_DIM
    if fresh:
        col = (255, 240, 160) if delta > 0 else (150, 214, 150)
        if not (int(time.time() * 4) % 2):        # 4 Hz blink
            col = (255, 255, 220) if delta > 0 else (188, 236, 188)
        pipx = gx - 4
        if delta > 0:
            d.point((pipx + 1, 2), fill=(240, 90, 90, 255))
            d.line([pipx, 3, pipx + 2, 3], fill=(240, 90, 90, 255))
        else:
            d.point((pipx + 1, 4), fill=(110, 200, 110, 255))
            d.line([pipx, 3, pipx + 2, 3], fill=(110, 200, 110, 255))
    for ch in txt:
        band.alpha_composite(_glyph_img(ch, col), (gx, 1))
        gx += 4

    frame.paste(band, (0, 0), band)
    return frame
