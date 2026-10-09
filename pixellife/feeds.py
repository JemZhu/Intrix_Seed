#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""外面世界的两个信息源：新闻 + 天气。

小人原本活在一个封闭的盒子里 —— 他知道的只有自己的钱包和邻居，外面的世界
（今天下雨、隔壁城市在办展会、国际上出了什么大事）对他来说不存在。这个模块
把那份信息接进来，作为聊天与决策的上下文：

* **新闻**：默认用 60s.viki.moe（免 key，每天 15 条国内外精选 + 一句微语）。
  解析器对常见返回形状都做了兼容，"日更 15 条" 和 "一次性拉 100 条" 都能吃，
  所以后台把 URL 换成 newsapi.org / freenewsapi 之类也能直接用（见 _parse_news）。
* **天气**：默认用 Open-Meteo（免 key、免费商用、直接给 daily max/min 和 WMO
  天气码，正好够画左上角那个小图标和雨雪特效）；wttr.in 作为备源自动降级。
* **每日热榜**（v6.17）：抖音 / 小红书 / B站 三家当日热点。三家都是免 key 的
  公开接口 —— 抖音和小红书走 60s.viki.moe 的 /v2/douyin 与 /v2/rednote，B站
  直接问官方 web-interface/search/square（要带 Referer）。三家在后台都能单独
  关掉或换成自己的地址。
* **世界日志**（v6.17）：上面三路内容抓到之后会并进 worldlog（天气/新闻/热榜
  按天归档），于是小人除了"此刻外面"，还多了"前几天外面"这层记忆。

设计约束（和 llm.py 一致，因为同样要跑在 mac 的 /usr/bin/python3 上）：

* 只用标准库；
* 网络请求全部在后台线程里做，永不阻塞渲染循环；
* 拿不到数据就沿用上一份，实在没有就让上层字段为空 —— 面板绝不能因此变空。

配置落盘 feeds_config.json，后台可改，改完立即生效（不需要重启）。
"""
import json
import os
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "feeds_config.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

DEFAULTS = dict(
    enabled=True,
    # ── 新闻 ────────────────────────────────────────────────────────
    news_enabled=True,
    news_url="https://60s.viki.moe/v2/60s",
    news_api_key="",
    news_count=8,             # 给 LLM 看几条
    news_interval=1800,       # 秒，拉取间隔
    # ── 天气 ────────────────────────────────────────────────────────
    weather_enabled=True,
    weather_provider="open-meteo",   # open-meteo | wttr | custom
    weather_url="",                  # provider=custom 时用
    weather_api_key="",
    city="北京",
    lat=39.9042,              # None -> 用城市名去地理编码
    lon=116.4074,
    weather_interval=1800,
    # ── 每日热榜（抖音 / 小红书 / B站）──────────────────────────────
    hot_enabled=True,
    hot_interval=3600,        # 秒；热榜是日更的，不必像新闻那么勤
    hot_count=6,              # 每个平台给模型看几条
    hot_api_key="",           # 默认三家都不需要
    douyin_enabled=True,
    douyin_url="https://60s.viki.moe/v2/douyin",
    xhs_enabled=True,
    xhs_url="https://60s.viki.moe/v2/rednote",
    bili_enabled=True,
    bili_url=("https://api.bilibili.com/x/web-interface/search/square"
              "?limit=20"),
)

# ─── 天气码归一化 ────────────────────────────────────────────────────
# 内部只留 7 种，够画图标 + 决定特效；右上角那个小图标认的就是这个 key。
ICONS = ("sun", "sun_cloud", "cloud", "fog", "rain", "snow", "storm")
ICON_CN = {"sun": "晴", "sun_cloud": "多云", "cloud": "阴", "fog": "雾",
           "rain": "雨", "snow": "雪", "storm": "雷雨"}

# WMO 4677（Open-Meteo 用的就是它）
WMO = [
    ((0, 0), "sun"),
    ((1, 2), "sun_cloud"),
    ((3, 3), "cloud"),
    ((45, 48), "fog"),
    ((51, 57), "rain"),      # 毛毛雨 / 冻毛毛雨
    ((61, 67), "rain"),
    ((71, 77), "snow"),
    ((80, 82), "rain"),      # 阵雨
    ((85, 86), "snow"),      # 阵雪
    ((95, 99), "storm"),
]

# WWO（wttr.in 用的那套）
WWO = [
    ((113, 113), "sun"),
    ((116, 116), "sun_cloud"),
    ((119, 122), "cloud"),
    ((143, 143), "fog"), ((248, 248), "fog"), ((260, 260), "fog"),
    ((176, 176), "rain"), ((263, 263), "rain"), ((266, 266), "rain"),
    ((293, 296), "rain"), ((299, 302), "rain"), ((305, 308), "rain"),
    ((311, 314), "rain"), ((353, 353), "rain"), ((356, 359), "rain"),
    ((179, 182), "snow"), ((185, 185), "snow"), ((227, 227), "snow"),
    ((230, 230), "snow"), ((317, 320), "snow"), ((323, 326), "snow"),
    ((329, 332), "snow"), ((335, 338), "snow"), ((350, 350), "snow"),
    ((362, 365), "snow"), ((368, 371), "snow"), ((374, 377), "snow"),
    ((200, 200), "storm"), ((386, 386), "storm"), ((389, 389), "storm"),
    ((392, 392), "snow"), ((395, 395), "snow"),
]


def _lookup(table, code):
    try:
        code = int(code)
    except Exception:                                       # noqa: BLE001
        return None
    for (lo, hi), key in table:
        if lo <= code <= hi:
            return key
    return None


def norm_code(provider, code):
    """把各家天气码收敛到 ICONS 里的一种。"""
    if code is None:
        return None
    if provider == "wttr":
        got = _lookup(WWO, code)
        return got or "cloud"
    return _lookup(WMO, code) or "cloud"


def effect_of(icon):
    """户外特效：只看雨雪雷，别的都不画。"""
    if icon in ("rain", "storm"):
        return "rain"
    if icon == "snow":
        return "snow"
    return None


# ─── HTTP ───────────────────────────────────────────────────────────
def _get_json(url, timeout=10, api_key=None, extra=None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + str(api_key)
    if extra:
        headers.update(extra)
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw)


def _first_str_list(obj, depth=0):
    """兜底解析：在任意 JSON 里找一串"像新闻标题"的字符串。"""
    if depth > 4:
        return None
    if isinstance(obj, list):
        strs = [x for x in obj if isinstance(x, str) and len(x.strip()) > 6]
        if len(strs) >= 3:
            return strs
        for it in obj:
            got = _first_str_list(it, depth + 1)
            if got:
                return got
        return None
    if isinstance(obj, dict):
        for v in obj.values():
            got = _first_str_list(v, depth + 1)
            if got:
                return got
    return None


def _parse_news(payload, url=""):
    """兼容几种常见新闻返回：60s / newsapi.org / freenewsapi / 通用。"""
    items, source, date, tip = [], None, None, None
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else None
        # 1) 60s.viki.moe
        if data and isinstance(data.get("news"), list):
            items = [str(x) for x in data["news"] if isinstance(x, str)]
            date = data.get("date")
            tip = data.get("tip")
        # 2) newsapi.org  {articles:[{title:}]}
        elif isinstance(payload.get("articles"), list):
            items = [str(a.get("title") or "") for a in payload["articles"]
                     if isinstance(a, dict)]
            source = (payload.get("source") or {}).get("name") if \
                isinstance(payload.get("source"), dict) else None
        # 3) freenewsapi / 其它 {results:[{title:}]}
        elif isinstance(payload.get("results"), list):
            items = [str(a.get("title") or "") for a in payload["results"]
                     if isinstance(a, dict)]
        elif isinstance(payload.get("news"), list):
            items = [str(x) for x in payload["news"] if isinstance(x, str)]
    elif isinstance(payload, list):
        items = _first_str_list(payload) or []
    if not items:
        items = _first_str_list(payload) or []
    # 去掉序号前缀（"1、xxx" / "1. xxx"）
    clean = []
    for s in items:
        s = " ".join(str(s).split())
        i = 0
        while i < len(s) and (s[i].isdigit() or s[i] in "、.．)） "):
            i += 1
        if i and i < len(s):
            s = s[i:]
        if s:
            clean.append(s)
    if not source:
        try:
            from urllib.parse import urlparse
            source = urlparse(url).hostname
        except Exception:                                   # noqa: BLE001
            source = None
    return dict(items=clean, source=source, date=date, tip=tip)


# ─── 每日热榜：抖音 / 小红书 / B站 ──────────────────────────────────
# 实测（2026-10-09，从本机直连）：
#   抖音   https://60s.viki.moe/v2/douyin   -> data[] {title, hot_value, link}
#   小红书 https://60s.viki.moe/v2/rednote  -> data[] {rank, title, score:"947.5w"}
#   B站    api.bilibili.com/x/web-interface/search/square?limit=20
#          -> data.trending.list[] {keyword, show_name, heat_score}（官方接口，
#             免登录，但缺 Referer 会吃 -412）
# 三家都不需要 key。B站官方这个接口比 60s 的 /v2/bili 稳（后者实测 500）。
HOT_SOURCES = (
    ("douyin", "抖音", "https://60s.viki.moe/v2/douyin"),
    ("xhs", "小红书", "https://60s.viki.moe/v2/rednote"),
    ("bili", "B站",
     "https://api.bilibili.com/x/web-interface/search/square?limit=20"),
)
HOT_CN = dict((k, cn) for k, cn, _u in HOT_SOURCES)
HOT_DEFAULT_URL = dict((k, u) for k, _cn, u in HOT_SOURCES)
HOT_EXTRA_HEADERS = {
    "bili": {"Referer": "https://www.bilibili.com",
             "Origin": "https://www.bilibili.com"},
}

_HOT_TITLE_KEYS = ("keyword", "show_name", "title", "name", "word", "query")
_HOT_VALUE_KEYS = ("hot_value", "heat_score", "score", "hot", "views", "num")


def _host(url):
    try:
        from urllib.parse import urlparse
        return urlparse(str(url)).hostname
    except Exception:                                           # noqa: BLE001
        return None


def _hot_item(d):
    """把任意一家的一条记录压成 {title, hot, rank, link}。"""
    if not isinstance(d, dict):
        return None
    title = None
    for k in _HOT_TITLE_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            title = " ".join(v.split())
            break
    if not title:
        return None
    hot = None
    for k in _HOT_VALUE_KEYS:
        v = d.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            hot = int(v)
            break
        if isinstance(v, str) and v.strip():
            hot = v.strip()
            break
    link = d.get("url") or d.get("link") or d.get("uri") or ""
    rank = d.get("rank") or d.get("index")
    return dict(title=title[:80], hot=hot,
                rank=(int(rank) if isinstance(rank, (int, float)) else None),
                link=str(link)[:180])


def _first_dict_list(obj, depth=0):
    """兜底：在任意 JSON 里找第一串"有标题的字典"。"""
    if depth > 5:
        return None
    if isinstance(obj, list):
        got = [x for x in obj if _hot_item(x)]
        if len(got) >= 3:
            return got
        for it in obj:
            found = _first_dict_list(it, depth + 1)
            if found:
                return found
        return None
    if isinstance(obj, dict):
        for v in obj.values():
            found = _first_dict_list(v, depth + 1)
            if found:
                return found
    return None


def _parse_hot(payload):
    """各家热榜 -> [{title, hot, rank, link}]，保序去重。"""
    out, seen = [], set()
    for d in (_first_dict_list(payload) or []):
        it = _hot_item(d)
        if not it:
            continue
        key = it["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        it["rank"] = it.get("rank") or (len(out) + 1)
        out.append(it)
    return out


# ─── the feed box ───────────────────────────────────────────────────
class Feeds(object):
    """新闻 + 天气的持有者：后台刷新，前台只读。"""

    START_DELAY = 3.0         # 让渲染循环先起来，别在启动瞬间抢网络
    POLL = 20.0               # 后台检查间隔

    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self.data = dict(DEFAULTS)
        self.load()
        self._thread = None
        self._stop = False
        self._wake = threading.Event()
        self._news = None         # parse result
        self._news_ts = 0.0
        self._news_try = 0.0
        self._weather = None
        self._weather_ts = 0.0
        self._weather_try = 0.0
        self._hot = {}            # kind -> dict(items=, ts=, url=, source=)
        self._hot_ts = {}
        self._hot_try = {}
        self._errors = []
        self._geo = None          # 城市名 -> 经纬度（缓存，永远复用）
        self._net_calls = 0
        self.start()

    # -- config ------------------------------------------------------
    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                with self._lock:
                    for k, v in saved.items():
                        if k in DEFAULTS:
                            self.data[k] = v
        except Exception:                                   # noqa: BLE001
            pass
        return self.data

    def save(self):
        with self._lock:
            blob = json.dumps(self.data, ensure_ascii=False, indent=1)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(blob)
        os.replace(tmp, self.path)
        return self.data

    def get(self, key=None):
        with self._lock:
            return dict(self.data) if key is None else self.data.get(key)

    def update(self, patch):
        """面板保存钩子：只认已知键，改完叫醒后台线程立刻重拉。"""
        patch = patch or {}
        with self._lock:
            for k, v in patch.items():
                if k not in DEFAULTS:
                    continue
                cur = DEFAULTS[k]
                if isinstance(cur, bool):
                    self.data[k] = bool(v)
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    try:
                        self.data[k] = int(v)
                    except Exception:                       # noqa: BLE001
                        continue
                elif isinstance(cur, float):
                    if v in ("", None):
                        self.data[k] = None
                        continue
                    try:
                        self.data[k] = float(v)
                    except Exception:                       # noqa: BLE001
                        continue
                else:
                    self.data[k] = str(v or "").strip()
            self.data["news_count"] = max(1, min(30, int(self.data["news_count"])))
            self.data["hot_count"] = max(1, min(20, int(self.data["hot_count"] or 6)))
            for kind, _cn, _u in HOT_SOURCES:
                if not str(self.data.get("%s_url" % kind) or "").strip():
                    self.data["%s_url" % kind] = HOT_DEFAULT_URL[kind]
            for key in ("news_interval", "weather_interval", "hot_interval"):
                try:
                    self.data[key] = max(300, min(86400, int(self.data[key])))
                except Exception:                           # noqa: BLE001
                    self.data[key] = DEFAULTS[key]
            if self.data.get("weather_provider") not in ("open-meteo", "wttr", "custom"):
                self.data["weather_provider"] = "open-meteo"
            if not self.data.get("city"):
                self.data["city"] = DEFAULTS["city"]
        self.save()
        self._geo = None                 # 城市可能换了
        self._news_ts = 0.0
        self._weather_ts = 0.0
        self._hot_ts = {}                # 热榜源可能换了，全部重拉
        self._wake.set()
        return self.get()

    # -- worker ------------------------------------------------------
    def start(self):
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._loop, name="pixellife-feeds",
                                            daemon=True)
        self._thread.start()

    def _loop(self):
        time.sleep(self.START_DELAY)
        while not self._stop:
            try:
                self.refresh()
            except Exception as e:                          # noqa: BLE001
                self._note("%s: %s" % (type(e).__name__, e))
            self._wake.wait(self.POLL)
            self._wake.clear()

    def _note(self, msg):
        with self._lock:
            self._errors = (self._errors + [str(msg)[:120]])[-4:]

    def refresh(self, force=False):
        """到点就拉；force=True 时无视间隔（面板的"立即刷新"）。"""
        cfg = self.get()
        if not cfg.get("enabled"):
            return
        now = time.time()
        want = []
        if cfg.get("news_enabled") and (force or
                                        now - self._news_ts >= float(cfg["news_interval"])):
            want.append("news")
        if cfg.get("weather_enabled") and (force or
                                           now - self._weather_ts >= float(cfg["weather_interval"])):
            want.append("weather")
        want.extend(self._hot_due(force))
        for what in want:
            try:
                if what == "news":
                    self.fetch_news()
                elif what == "weather":
                    self.fetch_weather()
                else:                                        # hot:<kind>
                    self.fetch_hot(what.split(":", 1)[1])
            except Exception as e:                          # noqa: BLE001
                if what == "news":
                    self._news_try = time.time()
                elif what == "weather":
                    self._weather_try = time.time()
                else:
                    self._hot_try[what.split(":", 1)[1]] = time.time()
                self._note("%s 拉取失败 %s: %s" % (what, type(e).__name__, e))

    def refresh_now(self, what=None):
        """同步强制刷新，返回给面板的 status。"""
        cfg = self.get()
        try:
            if what in (None, "news") and cfg.get("news_enabled"):
                self.fetch_news()
        except Exception as e:                              # noqa: BLE001
            self._note("news 拉取失败 %s: %s" % (type(e).__name__, e))
        try:
            if what in (None, "weather") and cfg.get("weather_enabled"):
                self.fetch_weather()
        except Exception as e:                              # noqa: BLE001
            self._note("weather 拉取失败 %s: %s" % (type(e).__name__, e))
        if what in (None, "hot") and cfg.get("hot_enabled"):
            for kind, cn, _u in HOT_SOURCES:
                if not cfg.get("%s_enabled" % kind):
                    continue
                try:
                    self.fetch_hot(kind)
                except Exception as e:                      # noqa: BLE001
                    self._note("%s 热榜拉取失败 %s: %s"
                               % (cn, type(e).__name__, e))
        return self.status()

    # -- news --------------------------------------------------------
    def fetch_news(self):
        cfg = self.get()
        url = (cfg.get("news_url") or "").strip()
        if not url:
            raise ValueError("新闻 API 地址为空")
        self._net_calls += 1
        payload = _get_json(url, timeout=12, api_key=cfg.get("news_api_key"))
        parsed = _parse_news(payload, url)
        with self._lock:
            self._news = parsed
            self._news_ts = time.time()
            self._news_try = self._news_ts
            self._errors = [e for e in self._errors if "news" not in e]
        self._log_world()
        return parsed

    def news(self, n=None):
        """最近一批新闻标题（最新在前，最多 n 条）。"""
        cfg = self.get()
        n = int(n or cfg.get("news_count") or 8)
        with self._lock:
            got = self._news or {}
        return list(got.get("items") or [])[:max(1, n)]

    # -- weather -----------------------------------------------------
    def _geocode(self, city):
        if not city:
            return None
        with self._lock:
            if self._geo and self._geo.get("city") == city:
                return self._geo
        urls = [
            "https://geocoding-api.open-meteo.com/v1/search?"
            "name=%s&count=1&language=zh&format=json" % _quote(city),
            "https://geocoding-api.open-meteo.com/v1/search?"
            "name=%s&count=1&format=json" % _quote(city),
        ]
        for u in urls:
            try:
                data = _get_json(u, timeout=10)
            except Exception:                               # noqa: BLE001
                continue
            res = (data or {}).get("results") or []
            if res:
                r0 = res[0]
                geo = dict(city=city, lat=r0.get("latitude"), lon=r0.get("longitude"),
                           name=r0.get("name"), admin=r0.get("admin1"),
                           country=r0.get("country"))
                with self._lock:
                    self._geo = geo
                return geo
        return None

    def fetch_weather(self):
        cfg = self.get()
        provider = cfg.get("weather_provider") or "open-meteo"
        out = None
        if provider == "custom":
            url = (cfg.get("weather_url") or "").strip()
            if not url:
                raise ValueError("自定义天气 API 地址为空")
            out = self._weather_from_openmeteo_url(url, cfg)
        elif provider == "wttr":
            out = self._weather_from_wttr(cfg)
        else:
            out = self._weather_from_openmeteo(cfg)
        if out is None:
            raise ValueError("天气接口没有返回可用数据")
        with self._lock:
            self._weather = out
            self._weather_ts = time.time()
            self._weather_try = self._weather_ts
            self._errors = [e for e in self._errors if "weather" not in e]
        self._log_world()
        return out

    def _weather_from_openmeteo(self, cfg):
        lat, lon = cfg.get("lat"), cfg.get("lon")
        city = cfg.get("city") or "北京"
        if lat is None or lon is None:
            geo = self._geocode(city)
            if not geo:
                raise ValueError("无法定位城市 %s" % city)
            lat, lon, city = geo["lat"], geo["lon"], (geo.get("name") or city)
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
               "&current=temperature_2m,weather_code,relative_humidity_2m,"
               "wind_speed_10m,apparent_temperature"
               "&daily=temperature_2m_max,temperature_2m_min,weather_code,"
               "precipitation_probability_max"
               "&timezone=Asia%%2FShanghai&forecast_days=1") % (lat, lon)
        self._net_calls += 1
        data = _get_json(url, timeout=12)
        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        tmax = _pick(daily.get("temperature_2m_max"))
        tmin = _pick(daily.get("temperature_2m_min"))
        code = _pick(daily.get("weather_code"))
        if code is None:
            code = cur.get("weather_code")
        icon = norm_code("open-meteo", code)
        return dict(provider="open-meteo", city=city,
                    text=ICON_CN.get(icon, "—"), icon=icon, code=code,
                    effect=effect_of(icon),
                    temp=_r(cur.get("temperature_2m")),
                    feels=_r(cur.get("apparent_temperature")),
                    tmax=_r(tmax), tmin=_r(tmin),
                    humidity=_r(cur.get("relative_humidity_2m")),
                    wind=_r(cur.get("wind_speed_10m")),
                    rain_p=(_pick(daily.get("precipitation_probability_max"))),
                    ts=time.time())

    def _weather_from_openmeteo_url(self, url, cfg):
        """自定义端点：把它当 open-meteo 形状来读，读不动就抛错由上层降级。"""
        self._net_calls += 1
        data = _get_json(url, timeout=12, api_key=cfg.get("weather_api_key"))
        cur = data.get("current") or data
        daily = data.get("daily") or {}
        code = cur.get("weather_code", cur.get("code"))
        icon = norm_code("open-meteo", code)
        return dict(provider="custom", city=cfg.get("city") or "",
                    text=ICON_CN.get(icon, "—"), icon=icon, code=code,
                    effect=effect_of(icon),
                    temp=_r(cur.get("temperature_2m", cur.get("temp"))),
                    feels=_r(cur.get("apparent_temperature")),
                    tmax=_r(_pick(daily.get("temperature_2m_max"))),
                    tmin=_r(_pick(daily.get("temperature_2m_min"))),
                    humidity=_r(cur.get("relative_humidity_2m")),
                    wind=_r(cur.get("wind_speed_10m")),
                    rain_p=None, ts=time.time())

    def _weather_from_wttr(self, cfg):
        city = cfg.get("city") or "Beijing"
        url = "https://wttr.in/%s?format=j1&lang=zh" % _quote(city)
        self._net_calls += 1
        data = _get_json(url, timeout=14)
        cur = (data.get("current_condition") or [{}])[0]
        day = (data.get("weather") or [{}])[0]
        code = cur.get("weatherCode")
        icon = norm_code("wttr", code)
        return dict(provider="wttr", city=city,
                    text=ICON_CN.get(icon, "—"), icon=icon, code=code,
                    effect=effect_of(icon),
                    temp=_r(cur.get("temp_C")), feels=_r(cur.get("FeelsLikeC")),
                    tmax=_r(day.get("maxtempC")), tmin=_r(day.get("mintempC")),
                    humidity=_r(cur.get("humidity")), wind=_r(cur.get("windspeedKmph")),
                    rain_p=_r(((day.get("hourly") or [{}])[0]).get("chanceofrain")),
                    ts=time.time())

    # -- 每日热榜 -----------------------------------------------------
    def _hot_due(self, force=False):
        cfg = self.get()
        if not cfg.get("hot_enabled"):
            return []
        now = time.time()
        iv = float(cfg.get("hot_interval") or 3600)
        out = []
        for kind, _cn, _u in HOT_SOURCES:
            if not cfg.get("%s_enabled" % kind):
                continue
            ts = self._hot_ts.get(kind) or 0.0
            if force or now - ts >= iv:
                out.append("hot:" + kind)
        return out

    def fetch_hot(self, kind):
        cfg = self.get()
        label = HOT_CN.get(kind, kind)
        url = str(cfg.get("%s_url" % kind) or "").strip() or \
            HOT_DEFAULT_URL.get(kind, "")
        if not url:
            raise ValueError("%s 热榜地址为空" % label)
        self._net_calls += 1
        payload = _get_json(url, timeout=12, api_key=cfg.get("hot_api_key"),
                            extra=HOT_EXTRA_HEADERS.get(kind))
        items = _parse_hot(payload)
        if not items:
            raise ValueError("%s 热榜没有解析出标题" % label)
        now = time.time()
        with self._lock:
            self._hot[kind] = dict(items=items, ts=now, url=url,
                                   source=_host(url))
            self._hot_ts[kind] = now
            self._hot_try[kind] = now
            self._errors = [e for e in self._errors if label not in e]
        self._log_world()
        return items

    def hot(self, kind, n=None):
        """某个平台的热榜条目（已是最热在前）。"""
        cfg = self.get()
        try:
            n = int(n or cfg.get("hot_count") or 6)
        except Exception:                                       # noqa: BLE001
            n = 6
        with self._lock:
            got = dict(self._hot.get(kind) or {})
        return list(got.get("items") or [])[:max(1, n)]

    def hot_all(self, n=None):
        """{抖音: [标题…], 小红书: […], B站: […]} —— 给模型看的那一份。

        每个平台最多 min(n, 6) 条：三家一起塞进 prompt 很容易把正文挤掉。
        """
        cfg = self.get()
        if not cfg.get("hot_enabled"):
            return {}
        try:
            cap = min(int(n), 6) if n else None
        except Exception:                                       # noqa: BLE001
            cap = None
        out = {}
        for kind, cn, _u in HOT_SOURCES:
            if not cfg.get("%s_enabled" % kind):
                continue
            vals = [_clip(it.get("title"), 24) for it in self.hot(kind, cap)]
            vals = [v for v in vals if v]
            if vals:
                out[cn] = vals
        return out

    def hot_status(self, n=10):
        cfg = self.get()
        now = time.time()
        out = {}
        for kind, cn, _u in HOT_SOURCES:
            with self._lock:
                got = dict(self._hot.get(kind) or {})
            ts = self._hot_ts.get(kind) or 0.0
            out[cn] = dict(
                key=kind,
                enabled=bool(cfg.get("%s_enabled" % kind)),
                url=str(cfg.get("%s_url" % kind) or ""),
                items=(got.get("items") or [])[:max(1, n)],
                total=len(got.get("items") or []),
                source=got.get("source"),
                age=(int(now - ts) if ts else None),
            )
        return out

    # -- 世界日志 -----------------------------------------------------
    def _log_world(self):
        """一次成功抓取之后，把内容并进世界日志。失败绝不往上抛。"""
        try:
            from . import worldlog
            hot = {}
            for kind, _cn, _u in HOT_SOURCES:
                with self._lock:
                    got = dict(self._hot.get(kind) or {})
                titles = [it.get("title") for it in (got.get("items") or [])]
                titles = [t for t in titles if t]
                if titles:
                    hot[kind] = titles
            worldlog.get_log().record(weather=self.weather(),
                                      news=self.news(99), hot=hot)
        except Exception as e:                                  # noqa: BLE001
            self._note("世界日志写入失败 %s: %s" % (type(e).__name__, e))

    def log_brief(self, days=2):
        """近几天的世界日志（不含今天 —— 今天的内容上面那段已经有了）。"""
        try:
            from . import worldlog
            return worldlog.get_log().brief(days)
        except Exception:                                       # noqa: BLE001
            return []

    def day_line(self, day):
        """指定那一天的那一行世界日志（补日记时用：要的是"那天"，不是"最近"）。"""
        try:
            from . import worldlog
            log = worldlog.get_log()
            return worldlog.WorldLog.line_of(log.get_day(day), day)
        except Exception:                                       # noqa: BLE001
            return ""

    def _log_stats(self):
        try:
            from . import worldlog
            s = worldlog.get_log().stats()
            return dict(days=s.get("days"),
                        max_days=(s.get("config") or {}).get("max_days"),
                        first=s.get("first"), last=s.get("last"),
                        size_kb=s.get("size_kb"))
        except Exception:                                       # noqa: BLE001
            return None

    def weather(self):
        with self._lock:
            return dict(self._weather) if self._weather else None

    def effect(self):
        """当前户外该下的特效：rain / snow / None。"""
        w = self.weather()
        if not w:
            return None
        return w.get("effect")

    # -- for the LLM -------------------------------------------------
    def brief(self, n=None):
        """塞进 prompt 的那一小块：今天什么天、外面在发生什么。"""
        out = {}
        w = self.weather()
        if w:
            bits = "%s %s" % (w.get("city") or "", w.get("text") or "")
            if w.get("tmax") is not None and w.get("tmin") is not None:
                bits += " %d~%d℃" % (w["tmin"], w["tmax"])
            elif w.get("temp") is not None:
                bits += " %d℃" % w["temp"]
            if w.get("humidity") is not None:
                bits += " 湿度%d%%" % w["humidity"]
            out["天气"] = bits.strip()
        news = self.news(n)
        if news:
            out["新闻"] = [_clip(x, 26) for x in news]
        hot = self.hot_all(n)
        if hot:
            out["热榜"] = hot
        log = self.log_brief(2)
        if log:
            out["世界日志"] = log
        return out

    def one_liner(self, n=2):
        """给我自己看的一行摘要（面板 / 日志）。"""
        w = self.weather()
        bits = []
        if w:
            bits.append("%s %s %s" % (w.get("city") or "", w.get("text") or "",
                                      ("%d~%d℃" % (w["tmin"], w["tmax"]))
                                      if w.get("tmin") is not None and
                                      w.get("tmax") is not None else ""))
        news = self.news(n)
        if news:
            bits.append("｜".join(_clip(x, 18) for x in news))
        return "  ".join(b for b in bits if b.strip())

    # -- panel -------------------------------------------------------
    def status(self):
        cfg = self.get()
        now = time.time()
        with self._lock:
            news = dict(self._news) if self._news else None
            weather = dict(self._weather) if self._weather else None
            errs = list(self._errors)
            geo = dict(self._geo) if self._geo else None
        return dict(
            config=cfg,
            weather=weather,
            news=(dict(items=(news or {}).get("items", [])[:16],
                       total=len((news or {}).get("items") or []),
                       source=(news or {}).get("source"),
                       date=(news or {}).get("date"),
                       tip=(news or {}).get("tip")) if news else None),
            geo=geo,
            hot=self.hot_status(10),
            worldlog=self._log_stats(),
            errors=errs,
            news_age=int(now - self._news_ts) if self._news_ts else None,
            weather_age=int(now - self._weather_ts) if self._weather_ts else None,
            hot_age=dict((k, int(now - ts) if ts else None)
                         for k, ts in self._hot_ts.items()),
            net_calls=self._net_calls,
            brief=self.brief(),
        )


def _quote(s):
    try:
        from urllib.parse import quote
        return quote(str(s))
    except Exception:                                       # noqa: BLE001
        return str(s)


def _pick(v):
    """open-meteo 的 daily 字段都是数组，取第一个。"""
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def _r(v):
    try:
        return int(round(float(v)))
    except Exception:                                       # noqa: BLE001
        return None


def _clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


_FEEDS = None


def get_feeds():
    global _FEEDS
    if _FEEDS is None:
        _FEEDS = Feeds()
    return _FEEDS
