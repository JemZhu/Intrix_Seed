#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
老黄历主题 - 传统农历历法
64x64 像素紧凑布局（忌分两行）
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, date


_TIANGAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
_DIZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
_ZODIAC = ['鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪']
_LUNAR_MONTHS = ['正', '二', '三', '四', '五', '六', '七', '八', '九', '十', '冬', '腊']
_LUNAR_DAYS = ['初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
               '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
               '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十']

_SOLAR_TERMS = [
    (1, 6, '小寒'), (1, 20, '大寒'), (2, 4, '立春'), (2, 19, '雨水'),
    (3, 6, '惊蛰'), (3, 21, '春分'), (4, 5, '清明'), (4, 20, '谷雨'),
    (5, 6, '立夏'), (5, 21, '小满'), (6, 6, '芒种'), (6, 21, '夏至'),
    (7, 7, '小暑'), (7, 23, '大暑'), (8, 8, '立秋'), (8, 23, '处暑'),
    (9, 8, '白露'), (9, 23, '秋分'), (10, 8, '寒露'), (10, 23, '霜降'),
    (11, 7, '立冬'), (11, 22, '小雪'), (12, 7, '大雪'), (12, 22, '冬至'),
]

_SHI_CHEN_NAMES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

_YI_ITEMS = ['嫁娶', '出行', '移徙', '开市', '动土', '修造', '竖柱', '上梁',
             '纳采', '订盟', '祭祀', '祈福', '安香', '会友', '纳财', '作灶',
             '入学', '求职', '装修', '治病', '针灸', '扫舍', '栽种', '安葬']

_JI_ITEMS = ['破土', '安葬', '行丧', '伐木', '塞穴', '入宅', '开光', '会友',
             '订婚', '竖柱', '上梁', '动土', '修造', '祈福', '求医', '扫舍']

_PENGZU = {
    '子': '不北', '丑': '不冠', '寅': '不北', '卯': '不西',
    '辰': '不东', '巳': '不南', '午': '不西', '未': '不东',
    '申': '不安', '酉': '不见', '戌': '不南', '亥': '不北',
}


def get_solar_term(d: date) -> str:
    for m, day, name in _SOLAR_TERMS:
        if d.month == m and abs(d.day - day) <= 1:
            return name
    return None


def get_lunar_info(d: date) -> tuple:
    gan_idx = (d.year - 4) % 10
    zhi_idx = (d.year - 4) % 12
    gan_zhi = _TIANGAN[gan_idx] + _ZODIAC[zhi_idx]
    month_map = {1:'正',2:'二',3:'三',4:'四',5:'五',6:'六',
                 7:'七',8:'八',9:'九',10:'十',11:'冬',12:'腊'}
    lm = month_map[d.month]
    ld = _LUNAR_DAYS[min(d.day - 1, 29)]
    return gan_zhi, lm, ld


def get_daily_yi_ji(d: date) -> tuple:
    seed = d.year * 10000 + d.month * 100 + d.day
    rng = seed % 100
    yi = [_YI_ITEMS[(rng * 7 + i) % len(_YI_ITEMS)] for i in range(4)]
    ji = [_JI_ITEMS[((rng * 11) + 5 + i) % len(_JI_ITEMS)] for i in range(4)]
    return yi, ji


def get_current_shi_chen() -> str:
    return _SHI_CHEN_NAMES[(datetime.now().hour + 1) // 2 % 12]


class CalendarTheme:
    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height

        self.COLORS = {
            'bg': (6, 3, 2),
            'title': (220, 180, 50),
            'yi': (50, 200, 100),
            'ji': (200, 80, 80),
            'term': (255, 160, 60),
            'lunar': (210, 190, 150),
            'shi': (180, 140, 90),
            'pengzu': (130, 110, 70),
            'date': (255, 210, 130),
            'red': (220, 60, 60),
        }

        self._font = ImageFont.truetype('/home/jem/Intrix_Seed/quan.ttf', 8)

    def generate_frame(self, status: dict = None, t: float = None) -> np.ndarray:
        import time
        if t is None:
            t = time.time()

        img = Image.new('RGB', (self.width, self.height), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        now = datetime.now()
        today = now.date()
        yi_list, ji_list = get_daily_yi_ji(today)

        # ── y=1 ── 公历月日 | 星期
        self._text(draw, 2, 1, f"{today.month}月{today.day}日", self.COLORS['date'])
        wd_cn = ['一', '二', '三', '四', '五', '六', '日'][today.weekday()]
        wd_color = self.COLORS['red'] if today.weekday() >= 5 else self.COLORS['lunar']
        self._text(draw, 48, 1, f"周{wd_cn}", wd_color)

        # ── y=10 ── 农历年 月 日
        gan_zhi, lm, ld = get_lunar_info(today)
        self._text(draw, 2, 10, gan_zhi, self.COLORS['title'])
        self._text(draw, 24, 10, f"{lm}月", self.COLORS['lunar'])
        self._text(draw, 42, 10, ld, self.COLORS['lunar'])

        # ── y=19 ── 节气（居中）
        st = get_solar_term(today)
        if st:
            self._text(draw, 26, 19, st, self.COLORS['term'])

        # ── y=28 ── 宜 第1行 + 时辰（右）
        self._text(draw, 2, 28, "宜", self.COLORS['yi'])
        self._text(draw, 10, 28, yi_list[0], self.COLORS['yi'])
        self._text(draw, 26, 28, yi_list[1], self.COLORS['yi'])

        # ── y=37 ── 宜 第2行
        self._text(draw, 10, 37, yi_list[2], self.COLORS['yi'])
        self._text(draw, 26, 37, yi_list[3], self.COLORS['yi'])

        # ── y=46 ── 忌 第1行 + 时辰（右）
        self._text(draw, 2, 46, "忌", self.COLORS['ji'])
        self._text(draw, 10, 46, ji_list[0], self.COLORS['ji'])
        self._text(draw, 26, 46, ji_list[1], self.COLORS['ji'])

        # ── y=55 ── 忌 第2行 + 彭祖（右）
        self._text(draw, 10, 55, ji_list[2], self.COLORS['ji'])
        self._text(draw, 26, 55, ji_list[3], self.COLORS['ji'])

        # ── 右侧：时辰 + 彭祖 ──
        shi = get_current_shi_chen()
        pz = _PENGZU.get(shi, '')
        self._text(draw, 48, 28, f"{shi}时", self.COLORS['shi'])
        if pz:
            self._text(draw, 48, 37, pz, self.COLORS['pengzu'])

        return np.array(img)

    def _text(self, draw: ImageDraw, x: int, y: int, text: str, color: tuple):
        draw.text((x, y), text, font=self._font, fill=color)


if __name__ == '__main__':
    import time, os
    theme = CalendarTheme()
    os.makedirs('/home/jem/Intrix_Seed/themes/test_frames', exist_ok=True)
    for i in range(10):
        frame = theme.generate_frame({}, t=time.time() + i * 0.1)
        img = Image.fromarray(frame)
        img.save(f'/home/jem/Intrix_Seed/themes/test_frames/cal_frame_{i:02d}.png')
    print("✅ 老黄历布局测试完成")