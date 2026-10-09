#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""LifeWorld -- the simulated life of one pixel person.

Design notes
------------
* Game time IS wall-clock time (1:1). Nothing is accelerated, so the little
  person lives the same Wednesday afternoon you do.
* Twelve attributes drive everything: six physical/mood stats plus six
  personality dials. Only the renderer ever reads them; the panel shows life,
  not numbers.
* The simulation is *event-driven*: an action has a duration in real seconds and
  holds the screen while it runs. Attributes drift continuously and the brain is
  consulted when an action ends (or when the schedule forces a change).
* Everything is JSON-serialisable so the state can be synced to the cloud and
  shown in the web/app back office.
"""
import json
import os
import random
import time
from datetime import datetime

from . import people

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "state.json")

# ─── economy ───────────────────────────────────────────────────────
# One pay cheque per hour of work; living costs drain the same clock. Numbers
# are tuned so a normal week nets slightly positive and a spree actually hurts:
#   a 6h shift @78 = ~470, living 10/h = 240/day  ->  ~+230 on a workday,
#   -240 at the weekend. A 900 holiday or a 380 doctor bill really shows up.
WAGE_PER_HOUR = 78
LIVING_COST_PER_HOUR = 10
# what the ledger calls each cash movement (defaults to the action label)
MONEY_LABEL = {
    "eat_out": "下馆子", "shop": "购物", "travel": "旅行", "decorate": "装修",
    "party": "派对开销", "sick": "医药费", "coffee": "咖啡", "date": "约会",
    "movie": "电影票", "grocery": "买菜", "gaming": "游戏币", "drink": "酒水",
    "bank": "手续费", "takeout": "外卖", "commute": "地铁票", "stock": "股市",
    # v5
    "bake": "烘焙材料", "exhibit": "展览门票", "window_shop": "逛街",
    "haircut": "理发", "massage": "按摩", "checkup": "体检费", "boardgame": "桌游",
    "watch_game": "球赛门票", "ship": "快递费", "hike": "远足开销",
    "blind_date": "约会开销", "stall": "进货成本", "live_stream": "直播打赏",
}
PAY_LABEL = {"work": "工资", "overtime": "加班费", "freelance": "私活款",
             "delivery": "跑单收入", "tutor": "课时费", "flyer": "日结工资",
             "convenience": "兼职工资", "stall": "摆摊收入", "live_stream": "直播收入"}

# ─── career, part-time work and savings ─────────────────────────────
# The day job pays WAGE_PER_HOUR * this, and climbs a rung every so often so a
# working week actually compounds instead of flatlining.
CAREER_TITLES = ["初级", "中级", "高级", "资深", "技术专家"]
CAREER_WAGE = [1.0, 1.25, 1.55, 1.9, 2.4]
PROMOTE_HOURS = 26.0            # hours of work per rung

# side jobs: each has an hourly rate, a window and a minimum skill to qualify.
PARTTIME = {
    "delivery":    dict(hourly=46, skill=0,  label="送外卖"),
    "flyer":       dict(hourly=32, skill=0,  label="发传单"),
    "convenience": dict(hourly=40, skill=10, label="便利店兼职"),
    "tutor":       dict(hourly=92, skill=45, label="家教"),
    "freelance":   dict(hourly=120, skill=60, label="接私活"),
}
SAVINGS_RATE = 0.0006           # per day, ~22%/yr -- enough to feel worth it
SAVE_FRACTION = 0.30            # share of the wallet moved to the bank
SAVE_MIN_KEEP = 300             # always keep walking-around money

# gear you can own; each piece adds charm and has to be worn to count
WARDROBE = [
    ("基础T恤", 120, 2), ("牛仔外套", 320, 4), ("帆布鞋", 260, 3),
    ("羊毛大衣", 880, 7), ("运动跑鞋", 620, 5), ("复古夹克", 740, 6),
    ("素色衬衫", 400, 4), ("工装裤", 460, 4), ("贝雷帽", 180, 3),
    ("皮质腕表", 1500, 8),
]

# ─── behaviour library ──────────────────────────────────────────────
# dur is a (min, max) range in real seconds. room must exist in the asset pack.
ACTIONS = {
    "sleep":      dict(room="bedroom", dur=(6 * 3600, 9 * 3600), label="睡觉",
                       drives=dict(energy=+55, health=+6, happiness=+4, hunger=-14),
                       caption="眼皮打架了，钻进被窝"),
    "wake":       dict(room="bedroom", dur=(300, 900), label="起床",
                       drives=dict(energy=+6, happiness=+2),
                       caption="新的一天，先伸个懒腰"),
    # wages are paid per hour actually worked (see `hourly`), not as a flat bonus
    "work":       dict(room="office", dur=(4 * 3600, 8 * 3600), label="上班",
                       hourly=WAGE_PER_HOUR,
                       drives=dict(energy=-26, hunger=-22, happiness=-6, charm=+1),
                       caption="工位上敲代码，时间就是钱"),
    "overtime":   dict(room="office", dur=(2 * 3600, 4 * 3600), label="加班",
                       hourly=int(WAGE_PER_HOUR * 1.5),
                       drives=dict(energy=-22, health=-8, hunger=-16, happiness=-8),
                       caption="加班换钱，头发换加班"),
    "stock":      dict(room="office", dur=(1800, 5400), label="看盘",
                       drives=dict(energy=-5, happiness=-3),
                       caption="盯着A股分时图"),
    "study":      dict(room="study", dur=(1800, 5400), label="学习",
                       drives=dict(energy=-10, hunger=-6, charm=+3, happiness=+3),
                       caption="啃书提升自己"),
    "cook":       dict(room="kitchen", dur=(900, 2400), label="做饭",
                       drives=dict(energy=-8, hunger=+34, happiness=+5, charm=+1),
                       caption="自己下厨，省钱又香"),
    "eat_out":    dict(room="kitchen", dur=(1200, 2700), label="下馆子",
                       drives=dict(hunger=+40, happiness=+10, wealth=-68),
                       caption="今天不想做饭，出门搓一顿"),
    "entertain":  dict(room="living", dur=(1800, 5400), label="追剧",
                       drives=dict(happiness=+16, energy=-6, hunger=-8),
                       caption="窝在沙发上刷剧"),
    "gym":        dict(room="gym", dur=(2400, 4800), label="健身",
                       drives=dict(health=+14, energy=-20, hunger=-16, charm=+4, happiness=+6),
                       caption="撸铁中，汗水换线条"),
    "bath":       dict(room="bath", dur=(900, 1800), label="洗澡",
                       drives=dict(health=+4, happiness=+8, charm=+3),
                       caption="冲个热水澡，整个人活了"),
    "decorate":   dict(room="living", dur=(1800, 5400), label="装修",
                       drives=dict(happiness=+12, energy=-12, wealth=-260),
                       caption="给家里添置新家具"),
    "shop":       dict(room="shop", dur=(1200, 3600), label="购物",
                       drives=dict(happiness=+13, wealth=-180, charm=+3),
                       caption="逛商场，买了点好东西"),
    "travel":     dict(room="beach", dur=(4 * 3600, 10 * 3600), label="旅行",
                       drives=dict(happiness=+30, energy=-24, health=+6, wealth=-900, charm=+5),
                       caption="出发去海边度假"),
    "stroll":     dict(room="outdoor", dur=(1200, 3600), label="散步",
                       drives=dict(happiness=+10, health=+5, energy=-6),
                       caption="去公园里走走，看看喷泉"),
    "social":     dict(room="living", dur=(1800, 5400), label="社交",
                       drives=dict(happiness=+18, energy=-8, charm=+2),
                       caption="和朋友聊天，心情不错"),
    "idle":       dict(room="living", dur=(300, 1500), label="发呆",
                       drives=dict(happiness=+2, energy=+2),
                       caption="什么都不做，放空一会儿"),
    "sing":       dict(room="music", dur=(1800, 4200), label="练琴",
                       drives=dict(happiness=+18, energy=-10, charm=+4),
                       caption="弹琴唱歌，自我陶醉"),
    "paint":      dict(room="gallery", dur=(1800, 4500), label="画画",
                       drives=dict(happiness=+17, energy=-9, charm=+5),
                       caption="涂涂画画，灵感来了"),
    "party":      dict(room="party", dur=(2400, 5400), label="开派对",
                       drives=dict(happiness=+26, energy=-18, wealth=-320, charm=+3),
                       caption="邀请朋友来家里开派对"),
    "trick":      dict(room="spooky", dur=(1200, 3000), label="探险",
                       drives=dict(happiness=+15, energy=-12),
                       caption="搞点刺激的小冒险"),
    "sick":       dict(room="clinic", dur=(1800, 5400), label="看病",
                       drives=dict(health=+22, wealth=-380, energy=-6, happiness=-4),
                       caption="身体不舒服，来看医生"),
    "walk_pet":   dict(room="outdoor", dur=(1200, 3000), label="遛宠物",
                       drives=dict(happiness=+14, health=+4, energy=-8),
                       caption="带着宠物出门溜达"),

    # ─── v3: more places to go, more things to do ───────────────────
    "coffee":     dict(room="cafe", dur=(900, 2400), label="喝咖啡",
                       drives=dict(energy=+16, happiness=+9, wealth=-32, hunger=+4),
                       caption="在咖啡馆磨一杯手冲"),
    "date":       dict(room="cafe", dur=(2400, 5400), label="约会",
                       drives=dict(happiness=+22, charm=+4, wealth=-180, energy=-8),
                       caption="约了人喝咖啡聊天"),
    "read":       dict(room="library", dur=(1800, 4500), label="看书",
                       drives=dict(happiness=+12, charm=+3, energy=-8),
                       caption="在图书馆泡一会儿"),
    "class":      dict(room="classroom", dur=(2400, 5400), label="上课",
                       drives=dict(charm=+4, energy=-14, hunger=-8, happiness=+5),
                       caption="去上课给自己充电"),
    "commute":    dict(room="subway", dur=(600, 1800), label="通勤",
                       drives=dict(energy=-6, happiness=-2, wealth=-8),
                       caption="挤地铁，通勤路上"),
    "movie":      dict(room="cinema", dur=(3600, 7200), label="看电影",
                       drives=dict(happiness=+20, wealth=-90, energy=-8),
                       caption="买票进场看场电影"),
    "stargaze":   dict(room="rooftop", dur=(1200, 3000), label="看夜景",
                       drives=dict(happiness=+14, energy=-4),
                       caption="上天台吹风看夜景"),
    "grocery":    dict(room="market", dur=(900, 2400), label="买菜",
                       drives=dict(hunger=+12, wealth=-60, happiness=+4),
                       caption="去超市囤点食材"),
    "gaming":     dict(room="arcade", dur=(1800, 4500), label="打游戏",
                       drives=dict(happiness=+18, energy=-10, wealth=-40),
                       caption="在电玩城打到通关"),
    "drink":      dict(room="bar", dur=(1800, 4200), label="小酌",
                       drives=dict(happiness=+16, wealth=-120, energy=-8, health=-3),
                       caption="下班小酌一杯"),
    "swim":       dict(room="pool", dur=(1800, 3600), label="游泳",
                       drives=dict(health=+12, energy=-18, hunger=-12, happiness=+8),
                       caption="去泳池游几个来回"),
    "garden":     dict(room="garden", dur=(1200, 3000), label="园艺",
                       drives=dict(happiness=+13, energy=-9, health=+3),
                       caption="在花园里修剪花枝"),
    "bank":       dict(room="bank", dur=(600, 1800), label="去银行",
                       drives=dict(wealth=-20, happiness=+2, energy=-3),
                       caption="去银行办点业务"),
    "nap":        dict(room="bedroom", dur=(1200, 3000), label="午睡",
                       drives=dict(energy=+22, health=+2),
                       caption="午后眯一会儿"),
    "takeout":    dict(room="living", dur=(900, 1800), label="点外卖",
                       drives=dict(hunger=+28, wealth=-45, happiness=+6),
                       caption="外卖到了，开吃"),
    "clean":      dict(room="living", dur=(1200, 2700), label="打扫",
                       drives=dict(happiness=+6, energy=-10, health=+2),
                       caption="收拾屋子，心情也清爽"),
    "photo":      dict(room="outdoor", dur=(1200, 3000), label="拍照",
                       drives=dict(happiness=+12, charm=+2, energy=-5),
                       caption="在公园里拍几张照片"),
    "fish":       dict(room="beach", dur=(1800, 4200), label="钓鱼",
                       drives=dict(happiness=+16, hunger=+10, energy=-8),
                       caption="海边钓鱼，等一条上钩"),
    "karaoke":    dict(room="music", dur=(1800, 4200), label="唱歌",
                       drives=dict(happiness=+20, energy=-10, wealth=-80, charm=+3),
                       caption="约人去唱两首"),

    # ─── v5: a fuller life, and a wallet that has to survive it ───────
    # sport & body
    "jog":        dict(room="outdoor", dur=(1200, 2700), label="跑步",
                       drives=dict(health=+10, energy=-12, happiness=+8, hunger=-10, charm=+1),
                       caption="沿着公园跑几圈"),
    "yoga":       dict(room="gym", dur=(1800, 3600), label="瑜伽",
                       drives=dict(health=+8, happiness=+10, energy=-9, charm=+3),
                       caption="在垫子上静一静"),
    "cycle":      dict(room="outdoor", dur=(2400, 5400), label="骑行",
                       drives=dict(health=+12, happiness=+12, energy=-16, hunger=-14, charm=+2),
                       caption="骑车去更远的地方"),
    "hike":       dict(room="outdoor", dur=(4 * 3600, 8 * 3600), label="远足",
                       drives=dict(health=+14, happiness=+18, energy=-26, hunger=-20,
                                   charm=+3, wealth=-60),
                       caption="走一段野路，值了"),
    "massage":    dict(room="shop", dur=(1800, 3600), label="按摩",
                       drives=dict(health=+6, happiness=+12, energy=+12, wealth=-160),
                       caption="把肩颈的结按开"),
    "checkup":    dict(room="clinic", dur=(1800, 3600), label="体检",
                       drives=dict(health=+9, energy=-6, wealth=-260),
                       caption="做一次全面体检"),
    # home life
    "bake":       dict(room="kitchen", dur=(1800, 3600), label="烘焙",
                       drives=dict(hunger=+22, happiness=+14, energy=-10, charm=+2, wealth=-40),
                       caption="烤箱里飘出黄油香"),
    "listen":     dict(room="living", dur=(900, 2400), label="听音乐",
                       drives=dict(happiness=+11, energy=+4),
                       caption="戴上耳机，世界安静了"),
    "journal":    dict(room="study", dur=(900, 1800), label="写日记",
                       drives=dict(happiness=+8, energy=-3, charm=+1),
                       caption="把今天写进本子里"),
    "laundry":    dict(room="bath", dur=(900, 1800), label="洗衣服",
                       drives=dict(happiness=+5, energy=-8, health=+2),
                       caption="把衣服洗完晾上"),
    "ship":       dict(room="market", dur=(600, 1500), label="寄快递",
                       drives=dict(energy=-3, happiness=+2, wealth=-18),
                       caption="把包裹寄出去"),
    # culture & leisure
    "exhibit":    dict(room="gallery", dur=(1800, 3600), label="看展",
                       drives=dict(happiness=+14, charm=+5, energy=-6, wealth=-50),
                       caption="在展厅里慢慢走"),
    "window_shop": dict(room="shop", dur=(1200, 3000), label="逛街",
                        drives=dict(happiness=+9, charm=+2, energy=-8, wealth=-20),
                        caption="只逛不买，也很开心"),
    "boardgame":  dict(room="party", dur=(2400, 5400), label="玩桌游",
                       drives=dict(happiness=+20, energy=-10, charm=+3, wealth=-60),
                       caption="一局桌游笑到肚子疼"),
    "watch_game": dict(room="bar", dur=(3600, 5400), label="看球赛",
                       drives=dict(happiness=+20, energy=-8, wealth=-70),
                       caption="和一屋子人看球"),
    "volunteer":  dict(room="garden", dur=(2400, 5400), label="做志愿",
                       drives=dict(happiness=+16, charm=+4, energy=-12, health=+3),
                       caption="去社区花园帮忙"),
    "blind_date": dict(room="cafe", dur=(2400, 5400), label="相亲",
                       drives=dict(happiness=+10, charm=+4, energy=-10),
                       caption="被安排见了一个人"),
    # earning a living
    "freelance":  dict(room="study", dur=(3600, 7200), label="接私活",
                       drives=dict(energy=-24, hunger=-14, happiness=-4, charm=+2),
                       caption="接了个外包，熬夜交付"),
    "live_stream": dict(room="study", dur=(2400, 5400), label="开直播",
                        drives=dict(charm=+6, energy=-14, happiness=+8),
                        caption="开播和粉丝唠一会儿"),
    "stall":      dict(room="market", dur=(3600, 7200), label="摆摊",
                       drives=dict(energy=-20, hunger=-12, charm=+4, happiness=+6),
                       caption="支起小摊，吆喝一晚上"),
    "delivery":   dict(room="outdoor", dur=(3600, 7200), label="送外卖",
                       hourly=46,
                       drives=dict(energy=-22, hunger=-14, health=-3, happiness=-4),
                       caption="跑单中，多跑一单多一份钱"),
    "tutor":      dict(room="classroom", dur=(3600, 5400), label="家教",
                       hourly=92,
                       drives=dict(energy=-16, happiness=+2, charm=+2),
                       caption="给孩子补两节课"),
    "flyer":      dict(room="subway", dur=(3600, 7200), label="发传单",
                       hourly=32,
                       drives=dict(energy=-18, happiness=-6, charm=+1),
                       caption="在地铁口发传单"),
    "convenience": dict(room="shop", dur=(3600, 7200), label="便利店兼职",
                        hourly=40,
                        drives=dict(energy=-16, happiness=-3, charm=+2),
                        caption="站在收银台后面"),
    # money management
    "save_money": dict(room="bank", dur=(600, 1500), label="存钱",
                       drives=dict(happiness=+4, energy=-2),
                       caption="把钱存进定期"),
    "invest":     dict(room="bank", dur=(900, 2100), label="理财",
                       drives=dict(energy=-3),
                       caption="对比了一下理财产品的收益"),
    # people
    "gift":       dict(room="shop", dur=(1200, 2700), label="买礼物",
                       drives=dict(happiness=+6, energy=-5, charm=+1),
                       caption="给朋友挑了份礼物"),
    "buy_clothes": dict(room="shop", dur=(1800, 3600), label="买衣服",
                        drives=dict(happiness=+16, charm=+8, energy=-6),
                        caption="试了半天的衣服，值"),
    "visit_friend": dict(room="living", dur=(2400, 5400), label="串门",
                         drives=dict(happiness=+20, energy=-8, charm=+2),
                         caption="去朋友家坐坐"),
    "call_friend": dict(room="living", dur=(900, 1800), label="打电话",
                        drives=dict(happiness=+10, energy=-2),
                        caption="跟老朋友聊了半小时"),
}

# ─── v6.8: body poses ───────────────────────────────────────────────
# 每个动作拆成体态节拍：动作时长按占比切成若干段，段内保持同一体态。
# pose_now() 按动作进度返回当前体态；渲染端据此决定走/站/坐/躺的画法。
POSE_CN = {"move": "移动", "stand": "站立", "sit": "坐下", "lie": "躺下"}
DEFAULT_PLAN = (("move", 0.10), ("stand", 0.20), ("sit", 0.70))
POSE_PLAN = {
    "sleep":        (("lie", 1.0),),
    "wake":         (("lie", 0.30), ("stand", 0.50), ("move", 0.20)),
    "work":         (("move", 0.12), ("stand", 0.18), ("sit", 0.70)),
    "overtime":     (("move", 0.10), ("stand", 0.20), ("sit", 0.70)),
    "stock":        (("stand", 0.30), ("sit", 0.70)),
    "study":        (("move", 0.08), ("stand", 0.17), ("sit", 0.75)),
    "cook":         (("move", 0.55), ("stand", 0.45)),
    "eat_out":      (("move", 0.15), ("sit", 0.85)),
    "entertain":    (("move", 0.08), ("sit", 0.72), ("lie", 0.20)),
    "gym":          (("move", 0.20), ("stand", 0.50), ("lie", 0.15), ("sit", 0.15)),
    "bath":         (("stand", 0.80), ("move", 0.20)),
    "decorate":     (("move", 0.55), ("stand", 0.45)),
    "shop":         (("move", 0.60), ("stand", 0.40)),
    "travel":       (("move", 0.45), ("stand", 0.35), ("sit", 0.20)),
    "stroll":       (("move", 0.85), ("stand", 0.15)),
    "social":       (("stand", 0.55), ("move", 0.25), ("sit", 0.20)),
    "idle":         (("stand", 0.60), ("move", 0.25), ("sit", 0.15)),
    "sing":         (("stand", 0.70), ("move", 0.20), ("sit", 0.10)),
    "paint":        (("stand", 0.65), ("move", 0.20), ("sit", 0.15)),
    "party":        (("move", 0.35), ("stand", 0.50), ("sit", 0.15)),
    "trick":        (("move", 0.60), ("stand", 0.30), ("lie", 0.10)),
    "sick":         (("sit", 0.50), ("lie", 0.50)),
    "walk_pet":     (("move", 0.80), ("stand", 0.20)),
    "coffee":       (("move", 0.10), ("sit", 0.90)),
    "date":         (("move", 0.10), ("sit", 0.75), ("stand", 0.15)),
    "read":         (("sit", 0.80), ("stand", 0.15), ("move", 0.05)),
    "class":        (("move", 0.10), ("sit", 0.75), ("stand", 0.15)),
    "commute":      (("move", 0.70), ("stand", 0.30)),
    "movie":        (("move", 0.08), ("sit", 0.92)),
    "stargaze":     (("stand", 0.50), ("sit", 0.35), ("lie", 0.15)),
    "grocery":      (("move", 0.65), ("stand", 0.35)),
    "gaming":       (("stand", 0.60), ("move", 0.25), ("sit", 0.15)),
    "drink":        (("sit", 0.60), ("stand", 0.40)),
    "swim":         (("move", 0.75), ("stand", 0.25)),
    "garden":       (("move", 0.40), ("stand", 0.35), ("sit", 0.25)),
    "bank":         (("move", 0.30), ("stand", 0.55), ("sit", 0.15)),
    "nap":          (("lie", 1.0),),
    "takeout":      (("move", 0.15), ("sit", 0.85)),
    "clean":        (("move", 0.70), ("stand", 0.30)),
    "photo":        (("move", 0.60), ("stand", 0.40)),
    "fish":         (("sit", 0.75), ("stand", 0.25)),
    "karaoke":      (("stand", 0.80), ("move", 0.15), ("sit", 0.05)),
    "jog":          (("move", 0.90), ("stand", 0.10)),
    "yoga":         (("stand", 0.35), ("lie", 0.35), ("sit", 0.30)),
    "cycle":        (("move", 0.85), ("stand", 0.15)),
    "hike":         (("move", 0.80), ("stand", 0.20)),
    "massage":      (("lie", 0.85), ("stand", 0.15)),
    "checkup":      (("sit", 0.40), ("stand", 0.40), ("lie", 0.20)),
    "bake":         (("move", 0.40), ("stand", 0.60)),
    "listen":       (("sit", 0.55), ("lie", 0.25), ("stand", 0.20)),
    "journal":      (("sit", 0.90), ("stand", 0.10)),
    "laundry":      (("move", 0.45), ("stand", 0.55)),
    "ship":         (("move", 0.60), ("stand", 0.40)),
    "exhibit":      (("move", 0.60), ("stand", 0.40)),
    "window_shop":  (("move", 0.75), ("stand", 0.25)),
    "boardgame":    (("sit", 0.85), ("move", 0.15)),
    "watch_game":   (("stand", 0.45), ("sit", 0.45), ("move", 0.10)),
    "volunteer":    (("move", 0.50), ("stand", 0.50)),
    "blind_date":   (("move", 0.08), ("sit", 0.80), ("stand", 0.12)),
    "freelance":    (("move", 0.06), ("sit", 0.79), ("stand", 0.15)),
    "live_stream":  (("sit", 0.80), ("stand", 0.20)),
    "stall":        (("stand", 0.70), ("move", 0.30)),
    "delivery":     (("move", 0.80), ("stand", 0.20)),
    "tutor":        (("sit", 0.70), ("stand", 0.30)),
    "flyer":        (("move", 0.75), ("stand", 0.25)),
    "convenience":  (("stand", 0.85), ("move", 0.15)),
    "save_money":   (("move", 0.20), ("stand", 0.70), ("sit", 0.10)),
    "invest":       (("sit", 0.70), ("stand", 0.30)),
    "gift":         (("move", 0.55), ("stand", 0.45)),
    "buy_clothes":  (("move", 0.40), ("stand", 0.55), ("sit", 0.05)),
    "visit_friend": (("move", 0.15), ("sit", 0.60), ("stand", 0.25)),
    "call_friend":  (("move", 0.30), ("stand", 0.50), ("sit", 0.20)),
}

# 状态栏（底部字幕）按类着色：内心独白淡青 / 身体绿 / 人际粉 / 收入红支出绿 /
# 剩余时间灰蓝 / 今日回顾米黄 / 财富档案金
CAP_COLOURS = {
    "thought":     (168, 226, 232),
    "vitals":      (126, 210, 110),
    "social":      (244, 156, 196),
    "money_in":    (238, 96, 96),
    "money_out":   (110, 200, 120),
    "money_sheet": (252, 208, 92),
    "time_left":   (152, 172, 214),
    "today":       (236, 216, 162),
    "sheet":       (252, 208, 92),
    "plain":       (238, 242, 248),
}

# ─── personality generators ─────────────────────────────────────────
STOCK_STYLES = ["激进追涨", "稳健价值", "成长赛道", "短线博弈", "长期持有", "指数定投"]
CONSUME_STYLES = ["奢靡主义", "实用至上", "科技尝鲜", "潮流跟风", "极简断舍离", "吃货本货", "收藏癖"]
LIFE_PACES = ["早鸟型", "夜猫型", "工作狂", "佛系", "张弛有度"]
SOCIAL_TEND = ["社牛", "外向", "选择性社交", "内向", "独来独往"]
HOBBY_POOL = ["炒股", "装修", "旅行", "阅读", "健身", "追剧", "做饭", "摄影",
              "游戏", "咖啡", "音乐", "画画", "遛狗", "手工", "电影", "游泳",
              "园艺", "钓鱼", "唱歌", "桌游"]
MBTI = ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"]

# v3: the house cast is the Modern-Interiors 16x32 sprites again.
FIRST = ["Alex", "Lucy", "Molly", "Dan", "Rob", "Roki"]

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# Chinese labels for each room, used by the longer subtitle variant.
ROOM_CN = {
    "bedroom": "卧室", "kitchen": "厨房", "study": "书房", "gym": "健身房",
    "living": "客厅", "bath": "浴室", "office": "公司", "shop": "商店",
    "outdoor": "公园", "beach": "海边", "music": "琴房", "gallery": "画廊",
    "party": "派对房", "spooky": "怪趣屋", "clinic": "诊所",
    "cafe": "咖啡馆", "library": "图书馆", "classroom": "教室",
    "subway": "地铁站", "cinema": "影院", "bank": "银行", "market": "超市",
    "arcade": "电玩城", "bar": "酒吧", "pool": "游泳馆", "rooftop": "天台",
    "garden": "花园",
    # v6.12: 15 位居民的家 —— 串门的目的地（地图 pack/maps/home_*.png）
    "home_lucy": "朱望舒家", "home_molly": "田怀安家", "home_dan": "朱柔嘉家",
    "home_rob": "陈书瑶家", "home_roki": "马文静家", "home_chef_alex": "袁望舒家",
    "home_chef_pier": "彭柔嘉家", "home_chef_rob": "郑可儿家",
    "home_halloween_kid_1": "陈青野家", "home_halloween_kid_2": "程子萱家",
    "home_old_1": "张可儿家", "home_old_2": "任志远家", "home_old_3": "徐子轩家",
    "home_old_4": "韩子轩家", "home_old_5": "杜俊杰家",
}


# who else shows up in the public rooms, and the critter they keep at home
PET_NAMES = ["豆豆", "团子", "咖啡", "奶昔", "花生", "芝麻", "布丁", "雪球"]
FRIEND_POOL = ["Lucy", "Molly", "Dan", "Rob", "Roki", "Chef_Alex", "Chef_Pier",
               "Chef_Rob", "Halloween_Kid_1", "Halloween_Kid_2",
               # v6: the chibi "Old characters" set joins the neighbourhood
               "Old_1", "Old_2", "Old_3", "Old_4", "Old_5"]

# Every alias an older save file might carry, mapped onto the current cast.
# Anything still unknown is replaced by the renderer's fallback character.
CAST_MIGRATE = {
    "alex": "Alex", "lucy": "Lucy", "molly": "Molly", "dan": "Dan",
    "rob": "Rob", "roki": "Roki",
    "kid_1": "Halloween_Kid_1", "kid_2": "Halloween_Kid_2",
    "kid_3": "Halloween_Kid_1", "kid_4": "Halloween_Kid_2", "kid_5": "Halloween_Kid_1",
    "npc_01": "Chef_Alex", "npc_02": "Dan", "npc_05": "Chef_Rob",
    "npc_10": "Chef_Alex", "npc_12": "Chef_Rob", "npc_14": "Chef_Pier",
    "npc_18": "Rob", "npc_20": "Molly", "npc_22": "Lucy",
}


# ─── opening hours ──────────────────────────────────────────────────
# Places are not open all night and you cannot work a shift that ends at
# midnight. Each entry is a tuple of allowed windows (weekday_only, start_min,
# end_min); an end earlier than the start wraps past midnight. Actions absent
# from this table are fine at any hour.
#
# This is what stops the 23:09 "still at the office" bug: work simply stops
# being legal after 18:00, both when choosing and while it is running.
ACTION_WINDOWS = {
    "work":      ((True, 9 * 60, 18 * 60),),
    "overtime":  ((True, 18 * 60, 22 * 60 + 30),),
    "stock":     ((True, 9 * 60 + 15, 15 * 60),),
    "commute":   ((True, 6 * 60 + 30, 10 * 60), (True, 17 * 60, 20 * 60)),
    "class":     ((True, 9 * 60, 17 * 60),),
    "bank":      ((True, 9 * 60, 16 * 60 + 30),),
    "shop":      ((False, 10 * 60, 21 * 60 + 30),),
    "grocery":   ((False, 8 * 60, 21 * 60 + 30),),
    "eat_out":   ((False, 10 * 60 + 30, 22 * 60),),
    "coffee":    ((False, 7 * 60, 21 * 60),),
    "garden":    ((False, 7 * 60, 18 * 60 + 30),),
    "swim":      ((False, 9 * 60, 21 * 60),),
    "photo":     ((False, 7 * 60, 19 * 60),),
    "fish":      ((False, 6 * 60, 19 * 60),),
    "stroll":    ((False, 6 * 60, 22 * 60),),
    "walk_pet":  ((False, 6 * 60, 22 * 60 + 30),),
    "movie":     ((False, 10 * 60, 24 * 60),),
    "karaoke":   ((False, 18 * 60, 2 * 60),),
    "drink":     ((False, 18 * 60, 2 * 60),),
    "stargaze":  ((False, 20 * 60, 4 * 60),),
    "party":     ((False, 19 * 60, 3 * 60),),
    "date":      ((False, 17 * 60, 24 * 60),),
    "nap":       ((False, 12 * 60, 17 * 60),),
    "sleep":     ((False, 21 * 60, 9 * 60),),
    "gym":       ((False, 6 * 60, 23 * 60),),
    "gaming":    ((False, 10 * 60, 24 * 60),),
    "travel":    ((False, 6 * 60, 22 * 60),),
    "sick":      ((False, 7 * 60, 21 * 60),),
    # ─── v5 ───
    "jog":       ((False, 6 * 60, 21 * 60),),
    "yoga":      ((False, 7 * 60, 22 * 60),),
    "cycle":     ((False, 6 * 60, 19 * 60),),
    "hike":      ((False, 6 * 60, 15 * 60),),
    "massage":   ((False, 10 * 60, 22 * 60),),
    "checkup":   ((True, 8 * 60 + 30, 16 * 60 + 30),),
    "bake":      ((False, 8 * 60, 23 * 60),),
    "laundry":   ((False, 8 * 60, 23 * 60),),
    "ship":      ((False, 9 * 60, 19 * 60),),
    "exhibit":   ((False, 10 * 60, 18 * 60),),
    "window_shop": ((False, 10 * 60, 21 * 60 + 30),),
    "haircut":   ((False, 10 * 60, 20 * 60),),
    "boardgame": ((False, 14 * 60, 24 * 60),),
    "watch_game": ((False, 19 * 60, 24 * 60),),
    "volunteer": ((False, 8 * 60, 17 * 60),),
    "blind_date": ((False, 10 * 60, 21 * 60),),
    "live_stream": ((False, 19 * 60, 1 * 60),),
    "stall":     ((False, 17 * 60, 23 * 60),),
    "delivery":  ((False, 10 * 60, 22 * 60), (False, 17 * 60, 21 * 60)),
    "tutor":     ((False, 15 * 60, 21 * 60), (False, 9 * 60, 12 * 60)),
    "flyer":     ((False, 9 * 60, 18 * 60),),
    "convenience": ((False, 8 * 60, 23 * 60),),
    "freelance": ((False, 18 * 60, 2 * 60),),
    "save_money": ((True, 9 * 60, 16 * 60 + 30),),
    "invest":    ((True, 9 * 60, 16 * 60 + 30),),
    "gift":      ((False, 10 * 60, 21 * 60 + 30),),
    "buy_clothes": ((False, 10 * 60, 21 * 60 + 30),),
    "visit_friend": ((False, 10 * 60, 22 * 60 + 30),),
    "call_friend": ((False, 8 * 60, 23 * 60),),
    "listen":    ((False, 6 * 60, 24 * 60),),
    "journal":   ((False, 7 * 60, 24 * 60),),
}

# Needs that override the clock: a starving or exhausted person does not wait
# for the shop to open.
_SURVIVAL = {
    "sleep": ("energy", 25),
    "sick": ("health", 45),
    "cook": ("hunger", 30),
    "eat_out": ("hunger", 30),
    "takeout": ("hunger", 30),
}


def _in_window(now, weekday_only, start, end):
    if weekday_only and now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    if start <= end:
        return start <= m <= end
    return m >= start or m <= end


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _kfmt(v):
    """Compact money: 840 / 12k / 1.4M -- keeps marquee lines short."""
    v = int(round(v))
    if abs(v) >= 1000000:
        return "%.1fM" % (v / 1000000.0)
    if abs(v) >= 10000:
        return "%dk" % round(v / 1000.0)
    return str(v)


def _norm_cast(name):
    """Any historical spelling of a cast member -> a name in the current pack.

    Saves have gone MI -> XP -> MI again; unknown leftovers are caught by the
    renderer's fallback, so this only needs to be best-effort.
    """
    if not name:
        return name
    if name.startswith("mi_"):
        name = name[3:]
    return CAST_MIGRATE.get(name, name)


class LifeWorld(object):
    def __init__(self, seed=None, state_path=STATE_PATH):
        self.state_path = state_path
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.state = self._load() or self._birth()
        if self.state.pop("_dirty", False):
            self.save()                  # persist one-off save migrations
        self._advance_offline()

    # ─── creation ───────────────────────────────────────────────────
    def _birth(self):
        r = self.rng
        name = r.choice(FIRST)
        s = dict(
            version=1,
            name=name,
            born=time.time(),
            avatar=name,
            health=r.randint(58, 92),
            happiness=r.randint(48, 86),
            hunger=r.randint(40, 80),
            energy=r.randint(55, 95),
            wealth=r.choice([0, 1200, 3800, 8600, 24000]),
            charm=r.randint(30, 75),
            stock_style=r.choice(STOCK_STYLES),
            consume_style=r.choice(CONSUME_STYLES),
            life_pace=r.choice(LIFE_PACES),
            social_tendency=r.choice(SOCIAL_TEND),
            hobbies=r.sample(HOBBY_POOL, 3),
            mbti=r.choice(MBTI),
            pet=r.choice(["cat", "dog", "bird"]),
            pet_name=r.choice(PET_NAMES),
            friends=r.sample([f for f in FRIEND_POOL if f != name], 3),
            action="wake",
            action_left=r.randint(300, 900),
            room=ACTIONS["wake"]["room"],
            holding=[],
            log=[],
            decisions=[],
            last_decision=0.0,
            thought=None,
            thought_ts=0.0,
            thoughts=[],
            last_reconsider=0.0,
            stocks={},
            events=[],
            money_log=[],
            last_money=None,
            hero_chat=[],
            hero_wants=None,
            subtitle_speed=LifeWorld.SUB_SPEED_DEFAULT,
            cost_hour=int(time.time() // 3600),
        )
        s["log"].append(dict(ts=time.time(), kind="birth",
                             text="%s 出生了" % s["name"]))
        # identity + the whole resident book: everybody gets a persona sheet
        people.build_hero(s, r)
        book = s["people"]
        for n in list(FRIEND_POOL):
            people.ensure(s, n, r)
        for f in s["friends"]:
            rec = people.ensure(s, f, r)
            if rec:
                # friends start warm, not at zero -- they are already friends
                rec["rel"]["score"] = r.randint(56, 78)
                rec["rel"]["tag"] = "老朋友"
        return s

    def _load(self):
        if not os.path.exists(self.state_path):
            return None
        try:
            with open(self.state_path, encoding="utf-8") as f:
                s = json.load(f)
            if s.get("version") != 1:
                return None
            # migration: these arrived later, older saves simply lack them
            s.setdefault("pet", random.choice(["cat", "dog", "bird"]))
            s.setdefault("pet_name", random.choice(PET_NAMES))
            s.setdefault("friends", random.sample(FRIEND_POOL, 3))
            s["friends"] = [f for f in s["friends"] if f != s.get("avatar")]
            s.setdefault("hobbies", [])
            s.setdefault("money_log", [])
            s.setdefault("last_money", None)
            s.setdefault("hero_chat", [])
            s.setdefault("hero_wants", None)
            s.setdefault("subtitle_speed", LifeWorld.SUB_SPEED_DEFAULT)
            # A cash movement is announced exactly once, so an old save's
            # pending entry must not be replayed after a restart.
            if isinstance(s.get("last_money"), dict) and \
                    "announced" not in s["last_money"]:
                s["last_money"]["announced"] = True
                s["_dirty"] = True
            s.pop("_cap", None)                     # transient marquee state
            s.setdefault("cost_hour", int(time.time() // 3600))
            # v6.2: inner life + impulse bookkeeping
            s.setdefault("thought", None)
            s.setdefault("thought_ts", 0.0)
            s.setdefault("thoughts", [])
            s.setdefault("last_reconsider", 0.0)
            # the cast has been renamed twice; pull old saves onto today's names
            for key in ("avatar", "name"):
                if s.get(key):
                    s[key] = _norm_cast(s[key])
            s["friends"] = [_norm_cast(f) for f in s.get("friends", [])]
            # v5: personas, career, savings, wardrobe, network
            people.build_hero(s, self.rng)
            for f in s.get("friends", []) + list(FRIEND_POOL):
                rec = people.ensure(s, f, self.rng)
                # the hero's existing friends start warm, as they would in life
                if rec and f in s.get("friends", []) and \
                        rec["rel"].get("score", 0) < 20:
                    rec["rel"]["score"] = self.rng.randint(56, 78)
                    rec["rel"]["tag"] = "老朋友"
            return s
        except Exception:
            return None

    def save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state_path)

    # ─── clock helpers ──────────────────────────────────────────────
    @staticmethod
    def market_open(now):
        if now.weekday() >= 5:
            return False
        m = now.hour * 60 + now.minute
        return (9 * 60 + 30 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)

    @staticmethod
    def is_work_hours(now):
        return now.weekday() < 5 and 9 <= now.hour < 18

    @staticmethod
    def is_night(now):
        return now.hour >= 22 or now.hour < 6

    @staticmethod
    def time_label(now):
        return "%02d:%02d" % (now.hour, now.minute)

    @staticmethod
    def daypart(now):
        h = now.hour
        for lo, hi, name in ((0, 5, "深夜"), (5, 8, "清晨"), (8, 11, "上午"),
                             (11, 13, "中午"), (13, 17, "下午"), (17, 19, "傍晚"),
                             (19, 22, "晚上"), (22, 24, "夜里")):
            if lo <= h < hi:
                return name
        return "深夜"

    # ─── opening hours ──────────────────────────────────────────────
    def action_allowed(self, action, now=None):
        """Is this action legal right now? Used by the brain and by tick()."""
        now = now or datetime.now()
        windows = ACTION_WINDOWS.get(action)
        if not windows:
            return True
        for wd, start, end in windows:
            if _in_window(now, wd, start, end):
                return True
        need = _SURVIVAL.get(action)
        if need and self.state.get(need[0], 100) < need[1]:
            return True                      # survival beats the clock
        return False

    def window_seconds_left(self, action, now=None):
        """Seconds until the current window closes, or None if unrestricted."""
        now = now or datetime.now()
        windows = ACTION_WINDOWS.get(action)
        if not windows:
            return None
        m = now.hour * 60 + now.minute
        best = None
        for wd, start, end in windows:
            if not _in_window(now, wd, start, end):
                continue
            end_m = end if end >= start else end + 1440
            cur_m = m if (end >= start or m >= start) else m + 1440
            left = (end_m - cur_m) * 60.0
            best = left if best is None else max(best, left)
        return best

    # ─── simulation ─────────────────────────────────────────────────
    def _advance_offline(self):
        """Catch up after a restart: never fast-forward more than one action."""
        last = self.state.get("last_tick")
        now = time.time()
        self.state["last_tick"] = now
        if last is None:
            return
        gap = now - last
        if gap < 0:
            return
        self.drift(gap)
        self.state["action_left"] = max(0, self.state.get("action_left", 0) - gap)

    def drift(self, seconds):
        """Continuous attribute decay, scaled from a per-hour baseline."""
        s = self.state
        h = seconds / 3600.0
        s["hunger"] = _clamp(s["hunger"] - 4.2 * h)
        s["energy"] = _clamp(s["energy"] - 2.6 * h)
        if s["hunger"] < 18:
            s["health"] = _clamp(s["health"] - 3.0 * h)
            s["happiness"] = _clamp(s["happiness"] - 2.0 * h)
        if s["energy"] < 15:
            s["health"] = _clamp(s["health"] - 2.2 * h)
        if s["health"] < 30:
            s["happiness"] = _clamp(s["happiness"] - 1.6 * h)
        if s["hunger"] > 62:
            s["health"] = _clamp(s["health"] + 0.6 * h)
        # ---- peace of mind is a function of the bank balance -------------
        if self.net_worth() < 300:
            s["happiness"] = _clamp(s["happiness"] - 1.8 * h)     # money worries
        elif self.net_worth() > 40000:
            s["happiness"] = _clamp(s["happiness"] + 0.5 * h)
        # ---- feelings fade back toward a personal set point --------------
        base = {"社牛": 66, "外向": 62, "选择性社交": 56,
                "内向": 53, "独来独往": 50}.get(s.get("social_tendency"), 56)
        if s.get("life_pace") == "佛系":
            base += 5
        if s.get("life_pace") == "工作狂":
            base -= 4
        s["happiness"] = _clamp(s["happiness"] +
                                (base - s["happiness"]) * min(1.0, 0.06 * h))

    # ─── money ─────────────────────────────────────────────────────
    def _money(self, delta, reason):
        """Every cash movement goes through here, so it can be announced."""
        s = self.state
        delta = int(round(float(delta)))
        if not delta:
            return 0
        before = s["wealth"]
        s["wealth"] = max(0, s["wealth"] + delta)
        real = int(round(s["wealth"] - before))       # clamped at zero
        entry = dict(ts=time.time(), delta=real, reason=reason,
                     balance=int(round(s["wealth"])), announced=False)
        s["money_log"].append(entry)
        s["money_log"] = s["money_log"][-80:]
        s["last_money"] = entry
        s["_cap"] = None                 # let the band interrupt with the news
        self.log("money", "%s %+d（余额 %d）" % (reason, real, s["wealth"]))
        return real

    def settle_living_cost(self):
        """Charge rent/food once per wall-clock hour and put it on the ledger."""
        s = self.state
        hr = int(time.time() // 3600)
        last = s.get("cost_hour")
        if last is None:
            s["cost_hour"] = hr
            return
        if hr > last:
            hours = min(24, hr - last)                # never bill a whole holiday at once
            self._money(-LIVING_COST_PER_HOUR * hours, "生活开销")
            s["cost_hour"] = hr

    def trade(self):
        """One A-share session: position size and swing follow their style."""
        s = self.state
        style = s.get("stock_style", "")
        swing = {"激进追涨": 0.085, "短线博弈": 0.065}.get(style, 0.032)
        if style in ("长期持有", "指数定投"):
            swing = 0.022
        pos = max(400.0, s["wealth"] * 0.25)
        pnl = pos * self.rng.uniform(-swing, swing * 1.15)
        self._money(pnl, "股市")

    # ─── career, savings, wardrobe ──────────────────────────────────
    @property
    def career(self):
        return self.state.setdefault(
            "career", dict(level=1, hours=0.0, skill=30, title="初级", parttime=None))

    def wage(self):
        """Hourly pay at the current rung of the ladder."""
        lv = max(1, min(len(CAREER_WAGE), int(self.career.get("level", 1))))
        return WAGE_PER_HOUR * CAREER_WAGE[lv - 1]

    def parttime_rate(self, key):
        job = PARTTIME.get(key)
        if not job:
            return 0
        # skill above the requirement pays a little better
        extra = max(0.0, (self.career.get("skill", 30) - job["skill"]) / 100.0)
        return int(round(job["hourly"] * (1.0 + extra)))

    def can_parttime(self, key):
        job = PARTTIME.get(key)
        return bool(job) and self.career.get("skill", 30) >= job["skill"]

    def work_hours(self, secs, wage):
        """Called through _money(); also advances the career ladder."""
        s = self.state
        self._money(wage * secs / 3600.0, PAY_LABEL.get("work", "工资"))
        c = self.career
        c["hours"] = float(c.get("hours", 0)) + secs / 3600.0
        c["skill"] = min(100.0, float(c.get("skill", 30)) + secs / 3600.0 * 0.9)
        level = int(c.get("level", 1))
        need = PROMOTE_HOURS * level
        if level < len(CAREER_TITLES) and c["hours"] >= need:
            c["level"] = level + 1
            c["title"] = CAREER_TITLES[level] + s.get("job", "")
            s["wealth"] = s["wealth"]                       # no-op, clarity
            self.log("career", "升职了：%s（时薪 %d）" % (c["title"], self.wage()))
            s["social_note"] = "升职加薪，%s" % c["title"]
            s["social_note_ts"] = time.time()

    def save_to_bank(self):
        """Move a slice of the wallet into the savings account."""
        s = self.state
        keep = max(SAVE_MIN_KEEP, s["wealth"] * 0.25)
        move = int(max(0.0, (s["wealth"] - keep) * SAVE_FRACTION))
        if move < 100:
            self.log("money", "没什么可存的，先攒一攒")
            return 0
        s["wealth"] -= move
        s["savings"] = int(s.get("savings", 0)) + move
        s["last_money"] = dict(ts=time.time(), delta=-move, reason="转入储蓄",
                               balance=int(s["wealth"]), announced=False)
        s["money_log"] = (s.get("money_log") or [])[-79:] + [s["last_money"]]
        s["_cap"] = None                 # let the band interrupt with the news
        self.log("money", "存了 %d 进储蓄（定期 %d）" % (move, s["savings"]))
        return move

    def invest_savings(self):
        """Park savings in a product whose risk follows the stock style."""
        s = self.state
        pot = int(s.get("savings", 0))
        if pot < 800:
            self.log("money", "本金太少，先多存点再理财")
            return 0
        style = s.get("stock_style", "")
        swing = {"激进追涨": 0.035, "短线博弈": 0.028, "成长赛道": 0.03}.get(style, 0.012)
        if style in ("长期持有", "指数定投"):
            swing = 0.008
        gain = int(pot * self.rng.uniform(-swing * 0.7, swing))
        s["savings"] = max(0, pot + gain)
        entry = dict(ts=time.time(), delta=gain, reason="理财收益",
                     balance=int(s["wealth"]), announced=False)
        s["last_money"] = entry
        s["money_log"] = (s.get("money_log") or [])[-79:] + [entry]
        s["_cap"] = None
        s["social_note"] = "理财%s %+d" % ("赚了" if gain >= 0 else "亏了", gain)
        s["social_note_ts"] = time.time()
        self.log("money", "理财 %+d（储蓄 %d）" % (gain, s["savings"]))
        return gain

    def interest(self):
        """Daily interest on savings. Small, but it rewards actually saving."""
        s = self.state
        day = int(time.time() // 86400)
        if s.get("interest_day") == day:
            return 0
        s["interest_day"] = day
        pot = int(s.get("savings", 0))
        if pot <= 0:
            return 0
        gain = int(pot * SAVINGS_RATE)
        if gain <= 0:
            return 0
        s["savings"] = pot + gain
        self.log("money", "存款利息 +%d" % gain)
        return gain

    def buy_gear(self):
        """Add one affordable piece to the wardrobe and let it lift charm."""
        s = self.state
        owned = set(s.get("wardrobe") or [])
        options = [w for w in WARDROBE if w[0] not in owned and w[1] <= s["wealth"] - 150]
        if not options:
            self.log("money", "想买件新的，但钱包不允许")
            return None
        name, price, charm = self.rng.choice(options)
        self._money(-price, "买衣服")
        s["wardrobe"] = (s.get("wardrobe") or []) + [name]
        s["charm"] = _clamp(s["charm"] + charm)
        s["social_note"] = "买了%s，魅力 +%d" % (name, charm)
        s["social_note_ts"] = time.time()
        return name

    def buy_gift(self):
        """Buy a present and hand it to somebody the hero is close to."""
        s = self.state
        budget = max(0, int(s["wealth"]) - SAVE_MIN_KEEP)
        price = int(min(budget * 0.25, max(60, self.rng.randint(60, 260))))
        if budget < 80 or price < 40:
            self.log("money", "想送礼，可钱包不允许")
            return None
        self._money(-price, "礼物")
        rec = self._pick_friend()
        if rec is None:
            return None
        delta, score, rank = people.meet(s, rec["name"], "gift", self.rng)
        s["social_note"] = "给%s送了礼物(%d) 关系+%.0f→%s" % (
            rec.get("cn", rec["name"]), price, delta, rank)
        s["social_note_ts"] = time.time()
        self.log("social", "送%s一份礼物，关系 %s(%.0f)" % (
            rec.get("cn", rec["name"]), rank, score))
        return rec["name"]

    def _pick_friend(self):
        """Whoever is warmest right now -- that is who you buy a present for."""
        book = self.state.get("people") or {}
        cands = [r for r in book.values() if r.get("name") != self.state.get("avatar")]
        if not cands:
            return None
        return max(cands, key=lambda r: r.get("rel", {}).get("score", 0))

    def _pick_visit_target(self):
        """v6.12 串门对象：优先熟人，其次任何已认识的居民，随机挑一个。

        刻意不用 _pick_friend()——那是「给最亲近的人买礼物」，每次都会选中
        同一个人，串门就会天天去同一家。
        """
        s = self.state
        book = s.get("people") or {}
        me = s.get("avatar")
        cands = [r for n, r in book.items() if n != me and r.get("name")]
        if not cands:
            return None
        friends = [r for r in cands if r["name"] in (s.get("friends") or [])]
        pool = friends if (friends and self.rng.random() < 0.75) else cands
        return self.rng.choice(pool)

    def meet(self, name, kind="greet"):
        """Public hook used by the renderer when two people bump into each other."""
        s = self.state
        before = ((s.get("people") or {}).get(name) or {}).get("rel", {}).get("score", 0)
        delta, score, rank = people.meet(s, name, kind, self.rng)
        if kind != "greet" or delta >= 3:
            s["social_note"] = "%s关系+%.0f→%s" % (
                people.ensure(s, name, self.rng).get("cn", name), delta, rank)
            s["social_note_ts"] = time.time()
        return delta, score, rank, before

    def net_worth(self):
        s = self.state
        return int(round(s.get("wealth", 0) + s.get("savings", 0)))

    def cheapest_outing(self):
        """Floor on spending: refuse luxuries until there is a cushion."""
        return max(150, int(self.state.get("wealth", 0) * 0.05))

    # ─── simulation ─────────────────────────────────────────────────
    def apply(self, action_key, secs=None):
        s = self.state
        a = ACTIONS[action_key]
        if secs is None:
            secs = self.rng.randint(*a["dur"])
        else:
            # v6.2: the LLM may suggest a length, but it stays inside the
            # action's own envelope -- a "coffee" is 15-40 minutes, never the
            # three hours a small model will happily write down.
            lo, hi = a["dur"]
            secs = int(max(int(lo), min(int(secs), int(hi))))
        # never run past closing time: a shift picked at 17:00 ends at 18:00
        left = self.window_seconds_left(action_key)
        if left is not None:
            secs = int(max(240, min(int(secs), int(left))))
        else:
            secs = int(secs)
        secs = int(max(120, min(secs, 10 * 3600)))
        for k, v in a["drives"].items():
            if k == "wealth":
                self._money(v, MONEY_LABEL.get(action_key, a["label"]))
            else:
                s[k] = _clamp(s.get(k, 50) + v)
        # ---- pay, by kind of work ------------------------------------
        if action_key in ("work", "overtime"):
            rate = self.wage() * (1.5 if action_key == "overtime" else 1.0)
            self.work_hours(secs, rate)
        elif a.get("hourly"):
            rate = self.parttime_rate(action_key) or a["hourly"]
            self._money(rate * secs / 3600.0,
                        PAY_LABEL.get(action_key, "收入"))
            c = self.career
            c["hours"] = float(c.get("hours", 0)) + secs / 3600.0 * 0.6
            c["skill"] = min(100.0, float(c.get("skill", 30)) +
                             secs / 3600.0 * (1.4 if action_key == "tutor" else 0.7))
        # ---- special money / life moves ------------------------------
        if action_key == "stock":
            self.trade()
        elif action_key == "save_money":
            self.save_to_bank()
        elif action_key == "invest":
            self.invest_savings()
        elif action_key == "buy_clothes":
            self.buy_gear()
        elif action_key == "gift":
            self.buy_gift()
        elif action_key == "live_stream":
            tip = int(round((30 + s["charm"] * 2.6) * secs / 3600.0 *
                            self.rng.uniform(0.5, 1.7)))
            self._money(tip, "直播收入")
            s["charm"] = _clamp(s["charm"] + 1)
        elif action_key == "stall":
            self._money(-int(60 + self.rng.randint(0, 90)), "进货成本")
            self._money(int(self.rng.randint(120, 420) * secs / 5400.0), "摆摊收入")
        elif action_key == "freelance":
            skill = float(self.career.get("skill", 30))
            fee = int((180 + skill * 4.2) * self.rng.uniform(0.8, 1.3))
            self._money(fee, "私活款")
        elif action_key == "blind_date":
            rec = self._meet_someone_new()
            if rec:
                s["social_note"] = "认识了%s(%s)" % (rec.get("cn"), rec.get("job"))
                s["social_note_ts"] = time.time()
        elif action_key in ("visit_friend", "call_friend", "boardgame",
                            "watch_game", "party", "date"):
            rec = self._pick_friend()
            if action_key == "visit_friend":
                # v6.12: 串门是去某位居民家里，不是在自己客厅
                rec = self._pick_visit_target() or rec
            if rec:
                people.meet(s, rec["name"], "chat", self.rng)
                if action_key == "visit_friend":
                    s["visit_who"] = rec["name"]
                    s["visit_who_cn"] = rec.get("cn") or rec["name"]
        elif action_key in ("delivery", "flyer", "convenience", "tutor"):
            rec = self._pick_friend()
            if rec and self.rng.random() < 0.5:
                people.meet(s, rec["name"], "work", self.rng)
        # ---- the diary only keeps things worth rereading -------------
        if action_key in ("journal", "freelance", "live_stream", "blind_date",
                          "volunteer", "hike"):
            self.state["journal"] = (self.state.get("journal") or [])[-40:] + [
                dict(ts=time.time(), at=self.time_label(datetime.now()),
                     text=a["caption"])]
        s["action"] = action_key
        s["room"] = a["room"]
        if action_key == "visit_friend":
            _home = "home_%s" % str(s.get("visit_who") or "").lower()
            if _home in ROOM_CN:
                s["room"] = _home
            elif s.get("visit_who"):
                s.pop("visit_who", None)      # 目标没有家 -> 老实待在客厅
        s["action_left"] = secs
        s["action_total"] = secs
        s["action_started"] = time.time()
        s["cut_done"] = False
        self.log("action", "%s（%s）" % (a["label"], a["caption"]))
        return a

    def _meet_someone_new(self):
        """A blind date introduces somebody the hero has not met yet."""
        s = self.state
        book = s.get("people") or {}
        pool = [n for n in FRIEND_POOL
                if n != s.get("avatar") and n not in book]
        if not pool:
            pool = [n for n, r in book.items()
                    if n != s.get("avatar") and
                    r.get("rel", {}).get("met", 0) == 0]
        if not pool:
            return None
        rec = people.ensure(s, self.rng.choice(pool), self.rng)
        people.meet(s, rec["name"], "date", self.rng)
        return rec

    def _people_clock(self, dt):
        """Throttled: let the residents' own lives tick along beside the hero's."""
        if dt <= 0:
            return
        acc = float(self.state.get("_pple_acc", 0)) + dt
        if acc < 15.0:
            self.state["_pple_acc"] = acc
            return
        self.state["_pple_acc"] = 0.0
        people.drift(self.state, acc, self.rng)
        people.decay(self.state, acc)

    def log(self, kind, text):
        self.state["log"].append(dict(ts=time.time(), kind=kind, text=text))
        self.state["log"] = self.state["log"][-400:]

    # ─── main tick ──────────────────────────────────────────────────
    def tick(self, now=None, seconds=None):
        """Advance the world. Returns the current action descriptor."""
        now = now or datetime.now()
        t = time.time()
        last = self.state.get("last_tick", t)
        dt = seconds if seconds is not None else max(0.0, t - last)
        self.state["last_tick"] = t

        if dt > 0:
            self.drift(dt)
            self.state["action_left"] = self.state.get("action_left", 0) - dt
        self.settle_living_cost()
        self.interest()
        self._people_clock(dt)

        # ---- closing time: wrap up whatever is no longer legal ----------
        act = self.state.get("action", "idle")
        if not self.action_allowed(act, now):
            if self.state.get("action_left", 0) > 120:
                self.state["action_left"] = self.rng.uniform(20, 100)
            if not self.state.get("cut_done"):
                self.state["cut_done"] = True
                self.log("schedule", "%s 到点了，%s 收工"
                         % (self.time_label(now), ACTIONS[act]["label"]))
        else:
            # ---- ask the LLM early so the answer is ready when we need it --
            total = float(self.state.get("action_total") or 0)
            left = float(self.state.get("action_left") or 0)
            if total <= 0 or left < min(180.0, total * 0.25):
                try:
                    from .brain import prefetch
                    prefetch(self, now)
                except Exception:                          # noqa: BLE001
                    pass

        # ---- inner voice: a thought every few minutes, LLM or not ---------
        try:
            self.spin_thought(now)
        except Exception:                                  # noqa: BLE001
            pass

        # ---- second thoughts: cut a plan short when life gets in the way --
        if self.state["action_left"] > 300:
            try:
                self._reconsider(now)
            except Exception:                              # noqa: BLE001
                pass

        if self.state["action_left"] <= 0:
            self._decide(now)

        # ---- v6.13: 长期记忆（日记收割 + 跨天生成），自带 3 秒节流 ----
        try:
            from . import memory
            memory.tick_hook(self, now)
        except Exception:                                  # noqa: BLE001
            pass

        return ACTIONS[self.state["action"]]

    # ─── impulse / second thoughts ──────────────────────────────────
    RECONSIDER_GAP = 1500.0     # at most one change of heart per 25 minutes

    def _reconsider(self, now):
        """Let a strong new need interrupt whatever they were doing.

        Without this a 40-minute plan is a 40-minute prison: the hero would sit
        in the cafe from 08:53 to 11:53 because that is what "coffee" was
        booked for. Here a genuine change (getting hungry, crashing, the mood
        falling apart) ends the action early, so the next tick re-decides.

        The rate limit is measured on the SIMULATED clock, not wall time, so
        offline catch-up behaves exactly like the live 1:1 run.
        """
        from .brain import reconsider
        s = self.state
        try:
            stamp = float(now.timestamp())
        except Exception:                                  # noqa: BLE001
            stamp = time.time()
        if stamp - float(s.get("last_reconsider") or 0) < self.RECONSIDER_GAP:
            return False
        reason = reconsider(self, now)
        if not reason:
            return False
        s["last_reconsider"] = stamp
        s["cut_done"] = True                 # the schedule-closing line stays quiet
        s["action_left"] = 1.0
        s["impulse"] = reason
        self.log("brain", "临时变卦：%s" % reason)
        history = (s.get("impulses") or [])[-79:] + [
            dict(ts=time.time(), at=self.time_label(now), text=reason)]
        s["impulses"] = history
        return True

    def _decide(self, now):
        """Pick the next action. brain.py may override this with an LLM choice."""
        from .brain import choose_action
        key, why, secs = choose_action(self, now)
        self.state["decisions"].append(
            dict(ts=time.time(), action=key, reason=why,
                 at=self.time_label(now)))
        self.state["decisions"] = self.state["decisions"][-200:]
        self.state["last_decision"] = time.time()
        self.apply(key, secs)

    # ─── derived readouts for the panel / API ───────────────────────
    # ─── inner life ─────────────────────────────────────────────────
    # A person is not only what they do; the marquee used to repeat the action
    # caption and the money line forever, which read as "no inner life at all".
    # Now a fresh line every few minutes, from the LLM when it is around and
    # from a state-driven generator when it is not -- so there is ALWAYS
    # something going on behind the eyes.
    THOUGHT_GAP = 150.0      # seconds between two inner lines

    def _set_thought(self, text, now, source="me"):
        s = self.state
        text = " ".join(str(text or "").split())[:18]
        if not text:
            return None
        s["thought"] = text
        s["thought_ts"] = time.time()
        s["thought_source"] = source
        s["thoughts"] = ((s.get("thoughts") or [])[-29:] +
                         [dict(ts=time.time(), at=self.time_label(now),
                               text=text, src=source)])
        return text

    def spin_thought(self, now=None, force=False):
        """Produce a new inner line (LLM if one is ready, else generated)."""
        s = self.state
        now = now or datetime.now()
        if not force and time.time() - float(s.get("thought_ts") or 0) < \
                self.THOUGHT_GAP:
            return s.get("thought")
        try:
            from . import brain
            got = brain.take_thought(self)
            if got:
                return self._set_thought(got, now, "ai")
            brain.request_thought(self, now)          # keep the pipe warm
        except Exception:                             # noqa: BLE001
            pass
        return self._set_thought(self.idle_thought(now), now, "me")

    def idle_thought(self, now):
        """A weighted, state-driven inner voice. Never empty, rarely the same."""
        s = self.state
        r = self.rng
        a = ACTIONS.get(s.get("action"), {})
        left = int(max(0, s.get("action_left", 0)) // 60)
        cash = float(s.get("wealth", 0))
        save = int(s.get("savings", 0))
        goal = (s.get("goal") or {}).get("save", 5000)
        net = self.net_worth()
        career = s.get("career") or {}
        warm = people.warmest(s, 1)
        led = s.get("last_money") or {}
        hour = now.hour
        cand = []

        def add(w, txt):
            if txt:
                cand.append((max(0.0, w), txt))

        # ---- body ----
        if s["hunger"] < 30:
            add(9, "肚子在叫了，得先吃")
        elif s["hunger"] < 50:
            add(5, "有点饿，忍一忍")
        if s["energy"] < 20:
            add(9, "眼皮沉，撑不住了")
        elif s["energy"] < 40:
            add(6, "有点累，缓缓")
        elif s["energy"] > 80:
            add(4, "现在精神真好")
        if s["health"] < 40:
            add(9, "身体在报警了")
        elif s["health"] < 62:
            add(5, "最近身子发虚")
        else:
            add(2, "身体还行")
        if s["charm"] < 45:
            add(4, "该打理下自己了")

        # ---- money ----
        if cash < 200:
            add(9, "钱包见底了，慌")
        elif cash < 600:
            add(6, "钱得省着花")
        elif cash > 6000:
            add(5, "手头还算宽裕")
        if save and net < goal:
            add(6, "离目标还差%d" % max(0, goal - net))
        elif net >= goal:
            add(5, "攒够目标了，踏实")
        if led and time.time() - float(led.get("ts", 0)) < 3600:
            add(7, "刚%s%+d" % (str(led.get("reason"))[:5],
                                int(led.get("delta", 0))))

        # ---- work ----
        lvl = career.get("level", 1)
        skill = round(float(career.get("skill", 0)))
        add(4, "%s，技能%d" % (str(career.get("title") or s.get("job"))[:6], skill))
        if lvl < 3 and skill > 55:
            add(5, "再熬熬该升职了")
        if career.get("parttime"):
            add(5, "兼职也得顾着")

        # ---- people ----
        if warm:
            w = warm[0]
            add(7, "想起%s了" % str(w.get("cn", w["key"]))[:4])
            if w["relation"]["score"] >= 70:
                add(6, "%s最近怎么样" % str(w.get("cn"))[:4])
        rel = people.panel(s)
        stale = [p for p in rel if p["relation"]["score"] < 30 and
                 p["relation"]["met"]]
        if stale:
            add(5, "好久没找%s了" % str(stale[0].get("cn"))[:4])
        if not rel:
            add(4, "还没什么熟人")

        # ---- mood ----
        if s["happiness"] < 35:
            add(9, "心里堵得慌")
        elif s["happiness"] < 52:
            add(6, "有点提不起劲")
        elif s["happiness"] > 80:
            add(6, "今天心情真好")

        # ---- what I'm doing right now ----
        if a and left > 0:
            add(8, "%s，还剩%d分" % (str(a.get("label"))[:4], left))
        if s.get("impulse"):
            add(6, str(s["impulse"])[:14])

        # ---- wants & plans ----
        for h in (s.get("hobbies") or [])[:3]:
            add(3, "想%s" % str(h)[:6])
        if len(s.get("wardrobe") or []) < 4:
            add(3, "想添身新衣服")
        if int(s.get("savings", 0)) > 2000:
            add(4, "存款动起来才有用")

        # ---- time & ambience ----
        if hour < 7:
            add(5, "天还没亮")
        elif hour >= 23:
            add(6, "夜深了，该收了")
        elif 12 <= hour <= 13:
            add(5, "中午了")
        if now.weekday() >= 5:
            add(4, "周末啊，松快点")

        # ---- the last decisions, reflected on ----
        # (skip the decision that started the CURRENT action -- you do not think
        # "I just did X" about the thing you are still doing)
        ds = s.get("decisions") or []
        prev_act = None
        for d in reversed(ds):
            act = d.get("action")
            if act and act != s.get("action"):
                prev_act = act
                break
        if prev_act and prev_act in ACTIONS:
            add(4, "刚才%s，还行" % str(ACTIONS[prev_act]["label"])[:4])
        add(2, str(s.get("catch") or ""))          # the catchphrase, rarely
        add(2, str(s.get("quirk") or "")[:14])

        if not cand:
            return "发会儿呆"
        total = sum(w for w, _ in cand)
        x = r.random() * total
        for w, txt in cand:
            x -= w
            if x <= 0:
                return txt
        return cand[-1][1]

    # marquee geometry: the band is 64px wide and crawls at ~1px per frame
    # (12-15 fps on the panel), so one full sweep is (2*64 + text) / 13 seconds.
    CAP_W = 64
    CAP_PX_PER_S = 13.0
    CAP_HOLD_MAX = 26.0

    # ─── v6.17: 底栏字幕速度（像素/帧）─────────────────────────────
    # 存在 state 里跟着存档走，面板一个滑块就能改，下一帧立刻生效。
    # CAP_PX_PER_S 是速度 1.0 时的实测值，所以 hold 时长按速度等比缩放。
    SUB_SPEED_MIN = 0.5
    SUB_SPEED_MAX = 4.0
    SUB_SPEED_DEFAULT = 1.6
    # 忙着手上的活时，仍然忙里抽空跟人搭话的概率
    BUSY_CHAT_CHANCE = 0.5

    def sub_speed(self, value=None):
        """底栏字幕速度。给值就写回 state（夹到合法区间），不给就读。

        面板和渲染器都走这一个口子，省得两边各有一套夹取逻辑。
        """
        if value is None:
            try:
                v = float(self.state.get("subtitle_speed"))
            except Exception:                                   # noqa: BLE001
                v = self.SUB_SPEED_DEFAULT
        else:
            try:
                v = float(value)
            except Exception:                                   # noqa: BLE001
                v = self.SUB_SPEED_DEFAULT
            v = max(self.SUB_SPEED_MIN, min(self.SUB_SPEED_MAX, v))
            self.state["subtitle_speed"] = round(v, 2)
        return max(self.SUB_SPEED_MIN, min(self.SUB_SPEED_MAX, v))

    # ─── v6.8: body pose & chat gating ──────────────────────────────
    def pose_now(self):
        """体态节拍：按动作进度从 POSE_PLAN 取当前段。"""
        s = self.state
        plan = POSE_PLAN.get(s.get("action")) or DEFAULT_PLAN
        total = float(s.get("action_total") or 0)
        left = max(0.0, float(s.get("action_left") or 0))
        p = 0.0 if total <= 0 else min(1.0, max(0.0, 1.0 - left / total))
        acc = 0.0
        n = len(plan)
        for i, (pose, share) in enumerate(plan):
            acc += share
            if p < acc or i == n - 1:
                return pose
        return plan[-1][0]

    # 对话门控：none 不触发偶遇；brief 只 NPC 打招呼、主角礼拒；open 正常聊
    CHAT_NONE = ("sleep", "nap", "bath", "sick", "massage", "checkup")
    CHAT_BRIEF = ("work", "overtime", "stock", "study", "class", "commute",
                  "freelance", "live_stream", "stall", "delivery", "tutor",
                  "flyer", "convenience", "read", "journal", "cook", "bake",
                  "clean", "laundry", "garden", "fish", "paint", "sing",
                  "gaming", "movie", "photo", "ship", "invest", "save_money",
                  "grocery")
    BRIEF_REPLIES = ("在上班", "等会儿聊", "先不打扰", "正忙着呢", "回头说")

    def chat_gate(self, action=None):
        a = action or self.state.get("action")
        if a in self.CHAT_NONE:
            return "none"
        if a in self.CHAT_BRIEF:
            return "brief"
        return "open"

    def brief_reply(self, t=None):
        """专注时主角的固定礼拒句，每个 45s 桶换一句（确定性）。"""
        b = int((t if t is not None else time.time()) // 45)
        return self.BRIEF_REPLIES[b % len(self.BRIEF_REPLIES)]

    def caption_colour(self, now=None):
        """当前字幕行的类别色键（v6.8 状态栏按类着色）。"""
        kind = (self.state.get("_cap") or {}).get("kind")
        return kind if kind in CAP_COLOURS else "plain"

    def status_caption(self, now=None):
        """The one-liner that scrolls in the bottom 8px band.

        Every branch starts with ``HH:MM`` -- the band's whole job is to tell
        you what time it is for them, and without the prefix a short line just
        sits inside the 64px width and never scrolls.

        Two rules keep it readable:

        * a line HOLDS long enough to sweep the panel once (``_cap_hold``), so
          a longer line is never cut off mid-word by the phase rotation;
        * a cash movement is announced EXACTLY ONCE.  Spinning "工资 +532" for
          a quarter of an hour made a single payday look like five of them.

        Eight phases rotate: what they are doing, what they are THINKING, the
        vitals as numbers, who is on their mind, where the money is heading,
        how much of the plan is left, what today looked like, and how they are
        doing socially and financially.
        """
        now = now or datetime.now()
        s = self.state
        clock = self.time_label(now)
        held = s.get("_cap") or {}
        if held.get("body") and \
                (time.time() - float(held.get("since") or 0)) < \
                float(held.get("hold") or 0):
            return "%s %s" % (clock, held["body"])
        body, kind = self._caption_body(now)
        s["_cap"] = dict(since=time.time(), hold=self.cap_hold(body), body=body,
                         kind=kind)
        return "%s %s" % (clock, body)

    def cap_hold(self, body):
        """Seconds to keep one marquee line: one full sweep of the band.

        v6.17: 字幕速度可调之后这一行也必须跟着缩放 —— 否则加速的只有滚动的
        字，换行还按老节奏掐，快语速下每句都会被切掉尾巴。
        """
        w = 0
        for ch in body:
            w += 8 if ord(ch) > 0x2E80 else 5       # CJK vs half-width glyphs
        w += 35                                     # the "HH:MM " prefix
        speed = max(self.SUB_SPEED_MIN, self.sub_speed())
        return min(self.CAP_HOLD_MAX,
                   3.0 + (2 * self.CAP_W + w) / (self.CAP_PX_PER_S * speed))

    def _caption_body(self, now):
        """The rotating text, without the clock prefix."""
        s = self.state
        a = ACTIONS[s["action"]]
        phase = int(time.time() // 18) % 8

        # ---- a cash movement grabs the band once, then never again -------
        led = s.get("last_money") or {}
        if led and not led.get("announced"):
            led["announced"] = True
            led["announced_ts"] = time.time()
            body = "%s %+d" % (led.get("reason", "收支"),
                               int(led.get("delta", 0)))
            if led.get("balance") is not None:
                body += " 余%d" % int(led["balance"])
            return body, ("money_in" if int(led.get("delta", 0) or 0) > 0
                          else "money_out")

        if phase == 1:
            # inner voice first: LLM line if fresh, then the generated one
            cap = s.get("llm_caption")
            if cap and (time.time() - float(s.get("llm_caption_ts", 0))) < 900:
                return str(cap), "thought"
            th = s.get("thought")
            if th:
                return str(th), "thought"
            return str(a["caption"]), "thought"

        if phase == 2:
            return self._vitals_line(), "vitals"

        if phase == 3:
            note = s.get("social_note")
            if note and (time.time() - float(s.get("social_note_ts", 0))) < 1800:
                return str(note), "social"
            warm = people.warmest(s, 1)
            if warm:
                w = warm[0]
                return ("想起%s(%s)" % (w.get("cn", w["key"]),
                                        w["relation"]["rank"]), "social")

        if phase == 4:
            return self._money_line(), "money_sheet"

        if phase == 5:
            left = int(max(0, s.get("action_left", 0)) // 60)
            if s["action"] not in ("sleep", "wake") and left > 0:
                return "%s还剩%d分" % (a["label"], max(1, left)), "time_left"
            return self._body_line(), "vitals"

        if phase == 6:
            today = [ACTIONS[d["action"]]["label"]
                     for d in (s.get("decisions") or [])[-4:]
                     if d.get("action") in ACTIONS]
            if today:
                return "今天%s" % "、".join(today[-3:]), "today"
            return self._body_line(), "vitals"

        if phase == 7:
            return self._sheet_line(), "sheet"

        return str(a["label"]), "plain"

    def _vitals_line(self):
        """The four vitals as plain numbers -- the day at a glance."""
        s = self.state
        return "健康%d 心情%d 精力%d 饱腹%d" % (
            round(s["health"]), round(s["happiness"]),
            round(s["energy"]), round(s["hunger"]))

    def _sheet_line(self):
        """Social + financial sheet, matching the panel's gauges."""
        s = self.state
        bits = ["魅力%d" % round(s["charm"]),
                "钱包%d" % round(s["wealth"])]
        sav = int(s.get("savings", 0))
        if sav:
            bits.append("存款%s" % _kfmt(sav))
        skill = s.get("career") or {}
        title = skill.get("title")
        if title:
            bits.append(str(title))
        return " ".join(bits)

    def _body_line(self):
        """A plain-language read of the four vitals."""
        s = self.state
        bits = []
        if s["hunger"] < 30:
            bits.append("饿得慌")
        elif s["hunger"] < 48:
            bits.append("有点饿")
        if s["energy"] < 22:
            bits.append("快撑不住了")
        elif s["energy"] < 42:
            bits.append("困")
        if s["health"] < 32:
            bits.append("身体发虚")
        elif s["health"] < 55:
            bits.append("状态一般")
        if s["happiness"] < 35:
            bits.append("心里堵")
        elif s["happiness"] < 52:
            bits.append("提不起劲")
        if not bits:
            if s["happiness"] > 74:
                bits.append("神清气爽")
            else:
                bits.append("状态还行")
        return "、".join(bits[:2])

    def _money_line(self):
        s = self.state
        net = self.net_worth()
        goal = (s.get("goal") or {}).get("save", 5000)
        if s["wealth"] < 200:
            return "钱包见底，得去挣钱"
        if net < goal:
            return "净资产 %s 离目标还差 %s" % (_kfmt(net), _kfmt(goal - net))
        if s["wealth"] < 400:
            return "现金只剩 %d，省着点" % round(s["wealth"])
        return "净资产 %s 存款 %s" % (_kfmt(net), _kfmt(int(s.get("savings", 0))))

    def tickline(self, now=None):
        """Explicit variant: clock + doing + place, always full width."""
        now = now or datetime.now()
        s = self.state
        return "%s %s %s" % (self.time_label(now),
                             ACTIONS[s["action"]]["label"],
                             ROOM_CN.get(s["room"], ""))

    def headline(self, now=None):
        now = now or datetime.now()
        s = self.state
        return "%s %s %s" % (WEEKDAY_CN[now.weekday()], self.time_label(now), s["name"])

    def summary(self):
        s = self.state
        warm = people.warmest(s, 5)
        return dict(
            name=s["name"], cn=s.get("cn"), mbti=s["mbti"], action=s["action"],
            action_label=ACTIONS[s["action"]]["label"], room=s["room"],
            pose=self.pose_now(), pose_label=POSE_CN[self.pose_now()],
            health=round(s["health"]), happiness=round(s["happiness"]),
            hunger=round(s["hunger"]), energy=round(s["energy"]),
            wealth=round(s["wealth"]), charm=round(s["charm"]),
            stock_style=s["stock_style"], consume_style=s["consume_style"],
            life_pace=s["life_pace"], social_tendency=s["social_tendency"],
            hobbies=s["hobbies"], holding=s["holding"],
            pet=s.get("pet"), pet_name=s.get("pet_name"),
            friends=s.get("friends", []),
            # v5 read-outs
            intro=s.get("intro"), job=s.get("job"), age=s.get("age"),
            career=dict(s.get("career") or {}),
            wage=round(self.wage()),
            savings=int(s.get("savings", 0)),
            net_worth=self.net_worth(),
            wardrobe=s.get("wardrobe", []),
            goal=s.get("goal"),
            body=self._body_line(),
            money_line=self._money_line(),
            relationships=warm,
            log=s["log"][-40:], decisions=s["decisions"][-20:],
            money_log=s.get("money_log", [])[-20:],
            last_money=s.get("last_money"),
            # v6.2: inner life + impulse history
            thought=s.get("thought"), thought_source=s.get("thought_source"),
            thoughts=(s.get("thoughts") or [])[-12:],
            action_left=int(max(0, s.get("action_left", 0))),
            action_total=int(max(0, s.get("action_total", 0))),
            impulse=s.get("impulse"),
            impulses=(s.get("impulses") or [])[-6:],
            brain=self.brain_stats(),
        )

    def brain_stats(self):
        """How the decisions are actually being made (for the panel)."""
        s = self.state
        ds = s.get("decisions") or []
        ai = len([d for d in ds if str(d.get("reason", "")).startswith("AI：")])
        out = dict(total=len(ds), ai=ai, rule=len(ds) - ai,
                   thought_source=s.get("thought_source"))
        try:
            from . import llm
            st = llm.get_pool().status()
            out.update(calls=st.get("calls"), ok=st.get("ok"),
                       fail=st.get("fail"), healthy=st.get("healthy"),
                       last_latency=st.get("last_latency"),
                       last_error=st.get("last_error"),
                       enabled=st.get("enabled"), decide=st.get("decide"))
        except Exception:                              # noqa: BLE001
            pass
        try:
            from . import brain
            out["brain_error"] = brain.get_brain().last_error
            out["brain_text"] = (brain.get_brain().last_text or "")[:120]
            out["pending"] = bool(brain.get_brain()._job)         # noqa: SLF001
        except Exception:                              # noqa: BLE001
            pass
        return out

    def people_panel(self):
        """Everything the residents page needs: hero + network + roster."""
        s = self.state
        return dict(hero=people.hero_panel(s),
                    relationships=people.panel(s),
                    roster=[r["key"] for r in people.panel(s)],
                    brain=self.brain_stats(),
                    thoughts=(s.get("thoughts") or [])[-10:],
                    decisions=(s.get("decisions") or [])[-10:],
                    impulses=(s.get("impulses") or [])[-5:],
                    action=dict(key=s.get("action"),
                                label=ACTIONS.get(s.get("action"), {}).get("label"),
                                room=s.get("room"),
                                left=int(max(0, s.get("action_left", 0))),
                                total=int(max(0, s.get("action_total", 0)))))
