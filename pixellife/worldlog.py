#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""世界日志 —— 把「外面世界」发生过的事按天记下来，能记一万天。

小人读到的新闻、看到的天气、刷到的热榜，全都落在 worldlog/ 下一堆以日期命名
的 JSON 里。**一条 = 一天**，所以 10000 条就是 27 年。

为什么按天拆文件，而不是攒一个大 JSON：

* 一次写入只重写「今天」那一个文件（一两 KB），历史一个字都不动；
* 清理最老的一天 = 删一个文件，不用重写几十 MB；
* 要看某一天的记录，直接开那天的文件，不用把整本日志读进内存。

世界日志是「小人的常识」：决策时看一眼前几天外面什么样，聊天时知道这几天
外面在聊什么，写日记时知道那天是晴是雨 —— 这些都是同一份数据。

约束和 feeds.py / llm.py 一样：只用标准库、磁盘操作极小、任何异常只记一笔
不往上抛 —— 日志写不进去也绝不能影响渲染循环。
"""
import json
import os
import re
import threading
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "worldlog")
CONFIG_PATH = os.path.join(HERE, "worldlog_config.json")

DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.json$")

# 热榜平台：key 落盘，名字给人看
HOT_KEYS = ("douyin", "xhs", "bili")
HOT_CN = {"douyin": "抖音", "xhs": "小红书", "bili": "B站"}

MAX_TITLE = 64             # 单条标题上限，防某个源塞进来一整段正文
MAX_LINE = 88              # 给模型看的单行上限
PRUNE_EVERY = 3600.0       # 最多一小时清一次老文件，别每次写都列目录

DEFAULTS = dict(
    enabled=True,
    max_days=10000,        # 一条 = 一天，所以这就是"一万天"
    news_per_day=30,       # 每天最多留几条新闻
    hot_per_day=20,        # 每个平台每天最多留几条热榜
)


def _clean(s):
    s = " ".join(str(s or "").split())
    return s[:MAX_TITLE]


def _clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _merge_list(old, new, cap):
    """新的在前、老的在后，去重、截断 —— 同一天的多次抓取只做增量。"""
    out, seen = [], set()
    for s in list(new or []) + list(old or []):
        s = _clean(s)
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _weather_row(w):
    """天气只留画图和说话用得上的字段（别把整个 open-meteo 响应抄进来）。"""
    if not isinstance(w, dict):
        return None
    out = {}
    for k in ("city", "text", "icon", "code", "tmin", "tmax", "temp",
              "humidity", "wind", "provider"):
        v = w.get(k)
        if v is not None and v != "":
            out[k] = v
    return out or None


class WorldLog(object):
    """按天归档的世界内容。写小、读快、永不抛。"""

    def __init__(self, dir_path=DIR, config_path=CONFIG_PATH):
        self.dir = dir_path
        self.cfg_path = config_path
        self._lock = threading.RLock()
        self.data = dict(DEFAULTS)
        self._errors = []
        self._last_prune = 0.0
        self._cache = {}          # day -> record（只缓存今天，省磁盘）
        self.load()

    # ── config ──────────────────────────────────────────────────────
    def _clamp(self):
        d = self.data
        for key, lo, hi in (("max_days", 1, 10000),
                            ("news_per_day", 5, 200),
                            ("hot_per_day", 3, 100)):
            try:
                v = int(d.get(key))
            except Exception:                                   # noqa: BLE001
                v = DEFAULTS[key]
            # 注意别写成 `d.get(key) or 默认值`：0 是 falsy，会把"夹到 1"变成
            # "夹回默认值"（离线自测就是这么抓到的）。
            d[key] = max(lo, min(hi, v))
        d["enabled"] = bool(d.get("enabled", True))

    def load(self):
        try:
            with open(self.cfg_path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                with self._lock:
                    for k, v in saved.items():
                        if k in DEFAULTS:
                            self.data[k] = v
        except Exception:                                       # noqa: BLE001
            pass
        self._clamp()
        return self.data

    def save(self):
        with self._lock:
            blob = json.dumps(self.data, ensure_ascii=False, indent=1)
        tmp = self.cfg_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(blob)
        os.replace(tmp, self.cfg_path)
        return self.data

    def get(self, key=None):
        with self._lock:
            return dict(self.data) if key is None else self.data.get(key)

    def update(self, patch):
        """面板保存钩子：只认已知键，改完顺手清一次超龄文件。"""
        patch = patch or {}
        with self._lock:
            for k, v in patch.items():
                if k not in DEFAULTS:
                    continue
                if k == "enabled":
                    self.data[k] = bool(v)
                else:
                    try:
                        self.data[k] = int(v)
                    except Exception:                           # noqa: BLE001
                        continue
            self._clamp()
        self.save()
        self.prune()
        return self.get()

    def _note(self, msg):
        with self._lock:
            self._errors = (self._errors + [str(msg)[:140]])[-4:]

    # ── day files ───────────────────────────────────────────────────
    def _path(self, day):
        return os.path.join(self.dir, "%s.json" % day)

    @staticmethod
    def _today():
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _blank(day):
        return dict(date=day, rev=0, first_ts=time.time(), last_ts=0.0,
                    weather=None, news=[], hot={})

    def _read_day(self, day):
        with self._lock:
            if self._cache and self._cache.get("date") == day:
                return json.loads(json.dumps(self._cache))
        p = self._path(day)
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
            return rec if isinstance(rec, dict) else None
        except Exception as e:                                  # noqa: BLE001
            self._note("读 %s 失败: %s" % (day, e))
            return None

    def _write_day(self, day, rec):
        try:
            os.makedirs(self.dir, exist_ok=True)
            tmp = self._path(day) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._path(day))
            return True
        except Exception as e:                                  # noqa: BLE001
            self._note("写 %s 失败: %s" % (day, e))
            return False

    # ── writing ─────────────────────────────────────────────────────
    def record(self, weather=None, news=None, hot=None, day=None):
        """把一批世界内容并进那一天的记录。任何一项为 None 就跳过。"""
        if not self.data.get("enabled"):
            return None
        if weather is None and not news and not hot:
            return None                   # 什么都没带就别建空文件
        day = day or self._today()
        need_prune = False
        with self._lock:
            rec = self._read_day(day) or self._blank(day)
            now = time.time()
            changed = False
            row = _weather_row(weather)
            if row:
                if rec.get("weather") != row:
                    changed = True
                rec["weather"] = row
            if news:
                merged = _merge_list(rec.get("news"), news,
                                     int(self.data["news_per_day"]))
                if merged != (rec.get("news") or []):
                    changed = True
                rec["news"] = merged
            if hot:
                box = rec.get("hot") or {}
                for k in HOT_KEYS:
                    vals = hot.get(k)
                    if not vals:
                        continue
                    merged = _merge_list(box.get(k), vals,
                                         int(self.data["hot_per_day"]))
                    if merged != (box.get(k) or []):
                        changed = True
                    if merged:
                        box[k] = merged
                rec["hot"] = box
            # 热榜那半段也要参与 changed 判定：漏掉它的话，先落新闻、再落热榜
            # 的第二次调用会被当成"没变化"直接跳过，热榜就永远写不进去。
            if not changed and rec.get("rev"):
                return rec                    # 同一批内容，别白写一次磁盘
            rec["last_ts"] = now
            rec["date"] = day
            rec["rev"] = int(rec.get("rev") or 0) + 1
            self._write_day(day, rec)
            self._cache = rec
            need_prune = (now - self._last_prune) > PRUNE_EVERY
        if need_prune:
            self.prune()
        return rec

    # ── reading ─────────────────────────────────────────────────────
    def list_days(self):
        """所有有记录的日子，新 -> 旧。"""
        try:
            names = os.listdir(self.dir)
        except Exception:                                       # noqa: BLE001
            return []
        out = [nm[:-5] for nm in names if DAY_RE.match(nm)]
        out.sort(reverse=True)
        return out

    def get_day(self, day=None):
        day = day or self._today()
        return self._read_day(day)

    def days(self, n=30):
        """最近 n 天的完整记录（新 -> 旧）。"""
        out = []
        for d in self.list_days()[:max(1, int(n))]:
            rec = self._read_day(d)
            if rec:
                out.append(rec)
        return out

    def recent(self, n=30):
        """给面板的轻量列表：每天一行摘要 + 计数。"""
        rows = []
        for d in self.list_days()[:max(1, int(n))]:
            rec = self._read_day(d) or {}
            hot = rec.get("hot") or {}
            rows.append(dict(
                date=d,
                line=self.line_of(rec, d),
                weather=(rec.get("weather") or {}).get("text") or "",
                news=len(rec.get("news") or []),
                hot=dict((k, len(hot.get(k) or [])) for k in HOT_KEYS),
                rev=int(rec.get("rev") or 0),
            ))
        return rows

    # ── for the LLM ─────────────────────────────────────────────────
    @staticmethod
    def line_of(rec, day):
        """一天压成一行：`10-08 阴16~24℃｜新闻12条｜热榜 抖音A、B/小红书C｜头条`。"""
        if not rec:
            return ""
        parts = []
        w = rec.get("weather") or {}
        if w:
            wx = str(w.get("text") or "")
            if w.get("tmin") is not None and w.get("tmax") is not None:
                wx += "%d~%d℃" % (w["tmin"], w["tmax"])
            if wx:
                parts.append(wx)
        news = rec.get("news") or []
        if news:
            parts.append("新闻%d条" % len(news))
        hot = rec.get("hot") or {}
        hs = []
        for k in HOT_KEYS:
            vals = hot.get(k) or []
            if vals:
                hs.append("%s%s" % (HOT_CN[k], _clip("、".join(vals[:2]), 20)))
        if hs:
            parts.append("热榜 " + "/".join(hs))
        if news:
            parts.append(_clip(news[0], 22))
        if not parts:
            return ""
        return _clip("%s %s" % (str(day)[5:], "｜".join(parts)), MAX_LINE)

    def brief(self, n=3, skip_today=True):
        """给模型看的近几天提要（默认不含今天 —— 今天的内容已经在外面那段里）。

        遇到没有内容的日子（服务关着、那天没抓），跳过它继续往前找，最多
        翻 3n 天，凑够 n 行就用 —— 免得空一天就把"前几天"整段吃掉。
        """
        today = self._today()
        days = self.list_days()
        if skip_today:
            days = [d for d in days if d != today]
        out = []
        for d in days[:max(1, int(n)) * 3]:
            line = self.line_of(self._read_day(d), d)
            if line:
                out.append(line)
            if len(out) >= max(1, int(n)):
                break
        return out

    # ── housekeeping ────────────────────────────────────────────────
    def count(self):
        return len(self.list_days())

    def size_kb(self):
        total = 0
        try:
            for nm in os.listdir(self.dir):
                p = os.path.join(self.dir, nm)
                if os.path.isfile(p):
                    total += os.path.getsize(p)
        except Exception:                                       # noqa: BLE001
            pass
        return int(total / 1024)

    def prune(self):
        """超过 max_days 就删最老的。一天一个文件，删除很便宜。"""
        with self._lock:
            self._last_prune = time.time()
            keep = int(self.data.get("max_days") or 10000)
            gone = self.list_days()[keep:]
        removed = 0
        for d in gone:
            try:
                os.remove(self._path(d))
                removed += 1
            except Exception as e:                              # noqa: BLE001
                self._note("清理 %s 失败: %s" % (d, e))
        if removed:
            self._note("日志已满 %d 天，清掉最老的 %d 天" % (keep, removed))
        return removed

    def stats(self):
        days = self.list_days()
        today = self._today()
        return dict(
            config=self.get(),
            days=len(days),
            first=(days[-1] if days else None),
            last=(days[0] if days else None),
            today=today,
            today_record=self.get_day(today),
            size_kb=self.size_kb(),
            errors=list(self._errors),
        )

    def status(self, n=30):
        out = self.stats()
        out["recent"] = self.recent(n)
        out["brief"] = self.brief(5)
        return out


_LOG = None


def get_log():
    global _LOG
    if _LOG is None:
        _LOG = WorldLog()
    return _LOG
