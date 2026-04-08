#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fortune Theme - 今日运势 (64x64)
quan.ttf 精确间距布局
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import random, math

class FortuneTheme:
    LUCKY_COLORS = [
        ('红',(255,80,80)), ('橙',(255,160,50)), ('金',(255,215,0)),
        ('黄',(255,255,100)), ('绿',(80,200,120)), ('青',(0,210,210)),
        ('蓝',(80,160,255)), ('紫',(180,100,255)), ('粉',(255,150,200)),
        ('白',(255,255,255)),
    ]
    LUCKY_NUMBERS = list(range(1, 100))
    LUCKY_ACCESSORIES = ['翡翠','玉佩','珍珠','红绳','朱砂','金饰','银镯','琥珀','珊瑚','碧玺']
    ZODIAC_ANIMALS = ['鼠','牛','虎','兔','龙','蛇','马','羊','猴','鸡','狗','猪']
    ZODIAC_SIGNS = ['白羊','金牛','双子','巨蟹','狮子','处女','天秤','天蝎','射手','摩羯','水瓶','双鱼']
    ZODIAC_SYMBOLS = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓']
    KEYWORD_SYMBOLS = ['☆','✦','◆','◇','♣','▣','★','◎']
    # 8×8 pixel icons for 12 zodiac signs
    # Row index = y (0=top, 7=bottom), Col index = x (0=left, 7=right)
    _ZODIAC_PIXEL = {
        # ♈ 白羊 (Aries) — V-shaped ram horns, horns flare outward at top
        '白羊': [
            [0,0,1,0,0,1,0,0],
            [0,1,0,1,1,0,1,0],
            [1,0,0,0,0,0,0,1],
            [1,0,0,0,0,0,0,1],
            [0,1,0,0,0,0,1,0],
            [0,1,0,0,0,0,1,0],
            [0,0,1,0,0,1,0,0],
            [0,0,0,1,1,0,0,0],
        ],
        # ♉ 金牛 (Taurus) — circle body + upward horns
        '金牛': [
            [0,0,1,0,0,1,0,0],
            [0,1,0,1,1,0,1,0],
            [0,1,0,1,1,0,1,0],
            [1,0,1,0,0,1,0,1],
            [1,0,1,0,0,1,0,1],
            [0,1,0,1,1,0,1,0],
            [0,0,1,0,0,1,0,0],
            [0,0,0,0,0,0,0,0],
        ],
        # ♊ 双子 (Gemini) — two vertical pillars
        '双子': [
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,0,0,1,0,0],
        ],
        # ♋ 巨蟹 (Cancer) — two facing arcs (crab claws facing inward)
        '巨蟹': [
            [0,1,0,0,0,0,1,0],
            [0,1,1,0,0,1,1,0],
            [0,0,1,1,1,1,0,0],
            [0,0,1,0,0,1,0,0],
            [0,0,1,1,1,1,0,0],
            [0,1,1,0,0,1,1,0],
            [0,1,0,0,0,0,1,0],
            [0,0,0,0,0,0,0,0],
        ],
        # ♌ 狮子 (Leo) — fire mane S-curve (simplified: mane outline)
        '狮子': [
            [0,1,0,0,0,0,1,0],
            [1,0,1,0,0,1,0,1],
            [1,0,1,1,1,1,0,1],
            [0,1,0,1,1,0,1,0],
            [0,1,0,0,0,0,1,0],
            [1,0,1,1,1,1,0,1],
            [1,0,1,0,0,1,0,1],
            [0,1,0,0,0,0,1,0],
        ],
        # ♍ 处女 (Virgo) — Greek cross
        '处女': [
            [0,0,0,1,1,0,0,0],
            [0,0,0,1,1,0,0,0],
            [0,0,0,1,1,0,0,0],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [0,0,0,1,1,0,0,0],
            [0,0,0,1,1,0,0,0],
            [0,0,0,1,1,0,0,0],
        ],
        # ♎ 天秤 (Libra) — Ω/horseshoe shape with crossbar at bottom
        '天秤': [
            [0,0,1,1,1,1,0,0],
            [0,1,0,0,0,0,1,0],
            [1,0,0,0,0,0,0,1],
            [1,0,0,0,0,0,0,1],
            [1,0,0,0,0,0,0,1],
            [0,1,0,0,0,0,1,0],
            [1,1,1,1,1,1,1,1],
            [0,0,0,0,0,0,0,0],
        ],
        # ♏ 天蝎 (Scorpio) — M shape + downward tail stinger
        '天蝎': [
            [1,0,0,0,0,0,0,1],
            [1,1,0,0,0,0,1,1],
            [0,1,1,0,0,1,1,0],
            [0,0,1,1,1,1,0,0],
            [0,0,1,1,1,1,0,0],
            [0,1,1,0,0,1,1,0],
            [1,1,0,0,0,0,1,1],
            [1,0,0,0,0,0,0,1],
        ],
        # ♐ 射手 (Sagittarius) — arrow pointing right + wings
        '射手': [
            [0,0,1,0,0,1,0,0],
            [1,0,0,1,1,0,0,1],
            [0,0,1,0,0,1,0,0],
            [1,1,1,1,1,1,1,1],
            [0,0,1,0,0,1,0,0],
            [1,0,0,1,1,0,0,1],
            [0,0,1,0,0,1,0,0],
            [0,0,0,0,0,0,0,0],
        ],
        # ♑ 摩羯 (Capricorn) — U shape body + upward horns
        '摩羯': [
            [1,0,0,0,0,0,0,1],
            [1,1,0,0,0,0,1,1],
            [0,1,0,0,0,0,1,0],
            [0,1,0,0,0,0,1,0],
            [0,1,0,0,0,0,1,0],
            [0,1,0,0,0,0,1,0],
            [0,0,1,1,1,1,0,0],
            [0,0,0,0,0,0,0,0],
        ],
        # ♒ 水瓶 (Aquarius) — wave pattern
        '水瓶': [
            [0,0,0,0,0,0,0,0],
            [0,1,0,1,0,1,0,0],
            [1,0,1,0,1,0,1,0],
            [0,1,0,1,0,1,0,0],
            [0,0,1,0,1,0,1,0],
            [1,0,1,0,1,0,1,0],
            [0,1,0,1,0,1,0,0],
            [0,0,0,0,0,0,0,0],
        ],
        # ♓ 双鱼 (Pisces) — two fish oval bodies facing opposite directions
        '双鱼': [
            [0,0,1,0,0,1,0,0],
            [0,1,0,1,1,0,1,0],
            [1,0,0,0,0,0,0,1],
            [1,0,0,1,1,0,0,1],
            [1,0,0,1,1,0,0,1],
            [1,0,0,0,0,0,0,1],
            [0,1,0,1,1,0,1,0],
            [0,0,1,0,0,1,0,0],
        ],
    }

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.C = {
            'bg':(10,5,25), 'bg2':(18,8,35),
            'gold':(255,215,0), 'gold_d':(160,140,0),
            'pink':(255,150,200), 'cyan':(0,210,210),
            'purple':(180,100,255), 'white':(255,255,255),
            'dim':(90,90,130), 'dim2':(60,60,90), 'div':(45,38,75),
        }
        # f9: 9px wide per Chinese char, text height 8px (oy=0 for CJK, oy=-1 for numbers)
        # f8: 8px wide per Chinese char, text height 7px (oy=0)
        self._f9 = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 9)
        self._f8 = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 8)
        self._f6 = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 6)

        self._fortune = {}
        self._seed = None
        self._init_fortune()

    def _init_fortune(self):
        now = datetime.now()
        self._seed = now.year * 10000 + now.month * 100 + now.day
        rng = random.Random(self._seed)
        cname, crgb = rng.choice(self.LUCKY_COLORS)
        numbers = sorted(rng.sample(self.LUCKY_NUMBERS, 3))
        accessories = rng.sample(self.LUCKY_ACCESSORIES, 2)

        # 生肖: 2026=马年 → 以马年index=6为基准 (year-4)%12
        zodiac = self.ZODIAC_ANIMALS[(now.year - 4) % 12]
        zodiac_sign = self._zodiac_sign(now.month, now.day)
        keyword = rng.choice(self.KEYWORD_SYMBOLS)
        score = rng.randint(60, 98)
        self._fortune = {
            'color_name': cname, 'color_rgb': crgb,
            'numbers': numbers, 'accessories': accessories,
            'zodiac': zodiac, 'zodiac_sign': zodiac_sign,
            'keyword': keyword, 'score': score,
            'date': f'{now.month}/{now.day:02d}',
        }

    def _zodiac_sign(self, month, day):
        """返回标准星座（西方天文边界）"""
        if   month==3:  return '双鱼' if day<21 else '白羊'
        elif month==4:  return '白羊' if day<20 else '金牛'
        elif month==5:  return '金牛' if day<21 else '双子'
        elif month==6:  return '双子' if day<22 else '巨蟹'
        elif month==7:  return '巨蟹' if day<23 else '狮子'
        elif month==8:  return '狮子' if day<23 else '处女'
        elif month==9:  return '处女' if day<23 else '天秤'
        elif month==10: return '天秤' if day<24 else '天蝎'
        elif month==11: return '天蝎' if day<22 else '射手'
        elif month==12: return '射手' if day<22 else '摩羯'
        elif month==1:  return '摩羯' if day<20 else '水瓶'
        elif month==2:  return '水瓶' if day<19 else '双鱼'
        return '白羊'

    def _draw_zodiac_symbol(self, draw, x, y, sign, color):
        """用8x8像素图绘制星座符号"""
        grid = self._ZODIAC_PIXEL.get(sign)
        if not grid:
            return
        for row in range(8):
            for col in range(8):
                if grid[row][col]:
                    draw.rectangle([x+col, y+row, x+col, y+row], fill=color)

    def generate_frame(self, status=None, t=None):
        import time
        if t is None: t = time.time()
        img = Image.new('RGB', (self.width, self.height), self.C['bg'])
        d = ImageDraw.Draw(img)
        self._bg(d)
        self._stars(d, t)
        self._title(d, t)           # y=2
        self._div(d, 11)            # divider
        self._zodiac_row(d)         # y=13
        self._div(d, 22)            # divider
        self._color_row(d)          # y=24
        self._div(d, 34)            # divider
        self._numbers_row(d)         # y=36
        self._div(d, 45)             # divider
        self._acc_row(d)             # y=47
        self._div(d, 56)             # divider
        self._score_bar(d)           # y=58, 6px bar with centered score
        return np.array(img)

    def _bg(self, d):
        for y in range(self.height):
            r = int(10 + y/self.height*8)
            g = int(5 + y/self.height*4)
            b = int(25 + y/self.height*12)
            d.rectangle([(0,y),(63,y)], fill=(r,g,b))

    def _stars(self, d, t):
        rng = random.Random(self._seed + 99)
        for i,(sx,sy) in enumerate([(3,3),(58,4),(10,8),(54,10),(6,6),(57,8)]):
            g = int((math.sin(t*3+i*1.3)+1)*70+90)
            d.rectangle([sx,sy,sx,sy], fill=(g,g,min(255,g+20)))

    def _title(self, d, t):
        p = int((math.sin(t*2)+1)*40+200)  # brightness range 200-255
        g = (p, int(p*0.85), 0)
        self._t(d, 14, 2, '今日运势', g)
        d.line([(4,11),(13,11)], fill=g, width=1)
        d.line([(51,11),(60,11)], fill=self.C['pink'], width=1)

    def _div(self, d, y):
        d.line([(4,y),(60,y)], fill=self.C['div'], width=1)

    # ── Row: Zodiac + Constellation + Symbol ──────────────────────────
    def _zodiac_row(self, d):
        f = self._fortune
        # 生肖 box at left (x=4)
        d.rectangle([4,13,12,20], fill=self.C['gold_d'])
        self._t(d, 5, 14, f['zodiac'], self.C['gold'], self._f8)
        # 星座 + 座标 at x=15
        self._t(d, 15, 14, f['zodiac_sign'], self.C['cyan'], self._f8)
        self._t(d, 15 + len(f['zodiac_sign'])*8 + 2, 14, '座', self.C['dim2'], self._f8)
        # 星座符号（小图形）at x=50, y=13 (8x8 pixel box)
        d.rectangle([50,13,58,21], fill=self.C['bg2'])
        self._draw_zodiac_symbol(d, 50, 13, f['zodiac_sign'], self.C['gold'])

    # ── Row: Lucky Color + Date ─────────────────────────────────────────
    def _color_row(self, d):
        f = self._fortune
        rgb = f['color_rgb']
        # "色" label at y=24 (f8 → rows 24-31)
        self._t(d, 4, 24, '色', self.C['dim'], self._f8)
        # Color swatch: 8x8 box rows 24-31, outline white
        d.rectangle([12,24,19,31], fill=rgb)
        d.rectangle([12,24,19,31], outline=self.C['white'], width=1)
        # Color name at y=24 (f9 → rows 24-31), oy=0
        self._t(d, 22, 24, f['color_name'], rgb)
        # Date on RIGHT at y=24 (f9 → rows 24-31), oy=0
        date_str = f['date']
        date_w = self._fw(date_str)  # ~22px
        self._t(d, 64 - date_w - 4, 24, date_str, self.C['white'])

    # ── Score Bar (at bottom, 6px tall, centered number inside) ─────────
    def _score_bar(self, d):
        f = self._fortune
        sc = f['score']
        bx, by, bw = 4, 58, 56        # bar at y=58, height=6px
        bh = 6

        # Bar background
        d.rectangle([bx, by, bx+bw, by+bh], fill=self.C['bg2'])
        # Bar fill
        fw = int(bw * sc / 100)
        bc = self._lp(self.C['purple'], self.C['gold'], sc/100)
        d.rectangle([bx, by, bx+fw, by+bh], fill=bc)
        # Score number ON TOP, centered in bar (f6: 6px tall, oy=0)
        sc_str = str(sc)
        sc_w = self._f6.getbbox(sc_str)[2]
        sc_x = bx + (bw - sc_w) // 2
        d.text((sc_x, by), sc_str, fill=self.C['white'], font=self._f6)

    # ── Row: Lucky Numbers ──────────────────────────────────────────────
    def _numbers_row(self, d):
        f = self._fortune
        # Label at y=36 (f8 → rows 36-42)
        self._t(d, 4, 36, '数', self.C['dim'], self._f8)
        # 3 boxes: each 14px wide, box rows 35-43 (8px tall), number at y=36 (f9 → rows 36-43)
        xs = [15, 31, 47]  # x positions for each box start
        for i, (x, n) in enumerate(zip(xs, f['numbers'])):
            d.rectangle([x-1,35,x+13,43], fill=self.C['gold'], outline=self.C['gold_d'], width=1)
            self._t(d, x+1, 36, str(n), (0, 0, 0))  # f9 oy=-1: rows 35-43

    # ── Row: Accessories ────────────────────────────────────────────────
    def _acc_row(self, d):
        f = self._fortune
        # Label at y=47 (f8 → rows 47-53)
        self._t(d, 4, 47, '饰', self.C['dim'], self._f8)
        # 2 accessories, each: dot(4px) + name
        x = 15
        for acc in f['accessories']:
            d.ellipse([x,49,x+3,52], fill=self.C['purple'])
            x += 5
            self._t(d, x, 47, acc, self.C['purple'])  # f8: rows 47-53
            x += len(acc)*8 + 6

    # ── Row: Date + Zodiac at bottom ────────────────────────────────────
    def _date_row(self, d):
        f = self._fortune
        now = datetime.now()
        wds = ['一','二','三','四','五','六','日']
        wd = wds[now.weekday()]
        wdc = self.C['pink'] if now.weekday()>=5 else self.C['dim']
        date_str = f['date']
        # Date + weekday at y=58 (f9 → rows 58-65, fits in 64)
        self._t(d, 4, 58, date_str, self.C['white'])
        self._t(d, 4 + self._fw(date_str) + 4, 58, '周', self.C['dim'])
        self._t(d, 4 + self._fw(date_str) + 4 + 9 + 2, 58, wd, wdc)
        # Zodiac box at right: rows 58-62, text at y=59 with f8
        d.rectangle([52,58,60,63], fill=self.C['gold_d'])
        self._t(d, 53, 59, f['zodiac'], self.C['gold'], self._f8)

    def _lp(self, c1, c2, t):
        return tuple(int(c1[i]+(c2[i]-c1[i])*t) for i in range(3))

    def _fw(self, text):
        """Get pixel width of text rendered in f9"""
        return self._f9.getbbox(text)[2]

    def _t(self, d, x, y, text, color, font=None):
        if font is None: font = self._f9
        try: d.text((x,y), text, fill=color, font=font)
        except: pass


if __name__ == '__main__':
    import time, os
    theme = FortuneTheme()
    f = theme._fortune
    print(f'🧧 {datetime.now().strftime("%Y-%m-%d")} | 数:{f["numbers"]} | 色:{f["color_name"]} | 饰:{",".join(f["accessories"])} | {f["zodiac"]}{f["zodiac_sign"]} | {f["score"]}分')
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(3):
        img = Image.fromarray(theme.generate_frame({}, t=time.time()+i*0.2))
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/fortune_{i:02d}.png')
    print('✅ 完成')
