#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PixelLife 长期记忆：对话记录 / 每日经历 / 愿望清单。

三层存储，全部 JSONL（一行一条），追加写、满了淘汰最旧：

    memory/chat.jsonl          主角与所有居民的每一轮对话   （默认上限 100 MB）
    memory/days/<who>.jsonl    每个角色（含主角）的每日经历 （每人默认 10000 条）
    memory/wishes.jsonl        主角想做的新鲜事             （默认 2000 条）

为什么对话原话**不**进 prompt
------------------------------
v6.5 的实测教训：把「最近说过的话」塞进摘要，2B 模型会把它们当成本场该说的
台词原样复读（唯一率 24% → 7 种）。所以这里的分工是——

  * 原话：只落盘，供面板回看 + 客户端判重（social.py 已有）用；
  * 「旧事」：喂给模型的是每日经历里**第三人称**写下的近况（recall()），
    它是叙述不是台词，模型不会照抄。

淘汰策略
--------
严格按「淘汰最旧一条」的语义实现，但一次多腾一点空间：100 MB 的日志如果
每写一条就重写一遍整个文件，会在满盘后把游戏卡死。所以超限时保留尾部
``keep_ratio``（默认 0.95），最旧的 5% 一次性丢掉——丢的仍然是最旧的那些。
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(HERE, "memory")
CONFIG_PATH = os.path.join(HERE, "memory_config.json")

DEFAULTS = {
    "enabled": True,
    "chat_max_mb": 100,          # 对话记录文件大小上限（MB）
    "chat_context_tail": 1000,   # 每次喂给模型的候选池：最近多少条
    "chat_recall_lines": 0,      # 注入 prompt 的该 NPC **原话**条数（默认 0=关）
    "day_max_per_who": 10000,    # 每人每日经历上限
    "wish_max": 2000,            # 愿望清单上限
    "day_recall": 2,             # 注入 prompt 的「旧事」条数
    "daily_enabled": True,       # 跨天时用 LLM 生成每日经历
    "daily_min_hour": 4,         # 跨天后至少等到几点才生成（避免午夜抢资源）
}

_LOCK = threading.RLock()
_CFG = None
_PENDING = {}                    # who -> {"job":..., "day":..., "kind":...}
_STATE = {"last_day": None, "last_run": 0.0, "errors": [], "generated": 0,
          "wishes_added": 0, "last_wish_day": None}


# ─── config ─────────────────────────────────────────────────────────
def get_config():
    global _CFG
    with _LOCK:
        if _CFG is None:
            _CFG = dict(DEFAULTS)
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    _CFG.update(json.load(f) or {})
            except Exception:                                # noqa: BLE001
                pass
        return dict(_CFG)


def update_config(patch):
    cfg = get_config()
    for k, v in (patch or {}).items():
        if k in DEFAULTS:
            if isinstance(DEFAULTS[k], bool):
                cfg[k] = bool(v)
            elif isinstance(DEFAULTS[k], int):
                try:
                    cfg[k] = int(v)
                except (TypeError, ValueError):
                    continue
            else:
                cfg[k] = v
    global _CFG
    with _LOCK:
        _CFG = cfg
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONFIG_PATH)
    return cfg


# ─── ring store ─────────────────────────────────────────────────────
class Ring(object):
    """JSONL 追加存储，满了淘汰最旧。按字节或按条数设上限。"""

    def __init__(self, path, max_bytes=0, max_records=0, keep_ratio=0.95):
        self.path = path
        self.max_bytes = int(max_bytes or 0)
        self.max_records = int(max_records or 0)
        self.keep_ratio = float(keep_ratio)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    # -- io ---------------------------------------------------------
    def _lines(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return [ln for ln in f.read().splitlines() if ln.strip()]
        except FileNotFoundError:
            return []

    def _rewrite(self, lines):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines) + "\n")
        os.replace(tmp, self.path)

    def size_bytes(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def count(self):
        return len(self._lines())

    # -- write ------------------------------------------------------
    def append(self, rec):
        line = json.dumps(rec, ensure_ascii=False)
        with _LOCK:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._evict()

    def _evict(self):
        """超限则保留尾部 keep_ratio，丢掉的永远是最旧的记录。"""
        over = (self.max_bytes and self.size_bytes() > self.max_bytes) or \
               (self.max_records and self.count() > self.max_records)
        if not over:
            return 0
        lines = self._lines()
        keep = max(1, int(len(lines) * self.keep_ratio))
        gone = len(lines) - keep
        self._rewrite(lines[gone:])
        return gone

    # -- read -------------------------------------------------------
    def tail(self, n):
        if n <= 0:
            return []
        lines = self._lines()
        out = []
        for ln in lines[-n:]:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        return out

    def clear(self):
        with _LOCK:
            self._rewrite([])


def _chat_ring():
    cfg = get_config()
    return Ring(os.path.join(DB_DIR, "chat.jsonl"),
                max_bytes=int(cfg["chat_max_mb"]) * 1024 * 1024)


def _day_ring(who):
    cfg = get_config()
    safe = "".join(ch for ch in str(who) if ch.isalnum() or ch in "_-") or "unknown"
    return Ring(os.path.join(DB_DIR, "days", "%s.jsonl" % safe),
                max_records=int(cfg["day_max_per_who"]))


def _wish_ring():
    cfg = get_config()
    return Ring(os.path.join(DB_DIR, "wishes.jsonl"),
                max_records=int(cfg["wish_max"]))


# ─── chat log ───────────────────────────────────────────────────────
def record_chat(npc, npc_cn, says, reply, room=None, emote=None, day=None):
    """记一轮对话。says/reply 可以是字符串或字符串列表。"""
    if not get_config()["enabled"]:
        return None
    if isinstance(says, (list, tuple)):
        says = " ".join(str(s) for s in says if s)
    if isinstance(reply, (list, tuple)):
        reply = " ".join(str(s) for s in reply if s)
    rec = dict(ts=round(time.time(), 3), day=day or time.strftime("%Y-%m-%d"),
               npc=npc, npc_cn=npc_cn or npc, room=room,
               say=(says or "").strip(), reply=(reply or "").strip(),
               emote=emote or "")
    if not rec["say"]:
        return None
    _chat_ring().append(rec)
    return rec


def recent_chat(n=None):
    """候选池：最近 n 条（默认取配置里的 chat_context_tail）。"""
    n = int(n or get_config()["chat_context_tail"])
    return _chat_ring().tail(n)


def chat_for(npc, n=3, pool=None):
    """在「最近 pool 条」里挑出与某个 NPC 的最近 n 轮。

    语料是全部历史，但模型只看得到最近 pool 条构成的窗口——这就是
    「记录全部、上下文只取最近 N 条」的落地方式。
    """
    rows = recent_chat(pool)
    hits = [r for r in rows if r.get("npc") == npc]
    return hits[-int(n):] if n else hits


def chat_count(npc=None):
    ring = _chat_ring()
    if npc is None:
        return ring.count()
    return len([r for r in ring.tail(20000) if r.get("npc") == npc])


# ─── daily experience ───────────────────────────────────────────────
def record_day(who, day, text, meta=None):
    if not text:
        return None
    rec = dict(ts=round(time.time(), 3), who=who, day=day,
               text=str(text).strip()[:400])
    if meta:
        rec["meta"] = meta
    _day_ring(who).append(rec)
    return rec


def days_of(who, n=3):
    return _day_ring(who).tail(n)


def last_day_of(who):
    rows = _day_ring(who).tail(1)
    return rows[0]["day"] if rows else None


def recall(npc, n=None):
    """喂给对话模型「旧事」用的第三人称摘要（不是台词）。"""
    n = int(n or get_config()["day_recall"])
    rows = days_of(npc, n)
    out = []
    for r in rows:
        txt = (r.get("text") or "").strip()
        if txt:
            out.append("%s（%s）" % (txt[:90], r.get("day", "")))
    return out


# ─── wish list ──────────────────────────────────────────────────────
def add_wish(text, source=None, day=None, kind="chat"):
    text = (text or "").strip()
    if not text:
        return None
    if any(r.get("text") == text for r in wishes(30)):        # 同一愿望不重复记
        return None
    rec = dict(ts=round(time.time(), 3), day=day or time.strftime("%Y-%m-%d"),
               text=text[:120], source=source or "", kind=kind,
               status="new")
    _wish_ring().append(rec)
    _STATE["wishes_added"] += 1
    return rec


def wishes(n=50):
    return _wish_ring().tail(n)


def wish_count():
    return _wish_ring().count()


# ─── daily generation (lazy, off the tick thread) ───────────────────
_SYS_DAY = (
    "你在给一个像素生活模拟游戏写角色日记。用第三人称写这个人这一天过得"
    "怎么样：2 句话，40 到 70 个字，具体一点，可以提到心情和小事。"
    "不要写台词，不要用引号，不要提“游戏”或“玩家”。"
)

_SYS_WISH = (
    "你在帮一个像素生活模拟里的主角做愿望清单。根据给你的聊天片段，写出"
    "主角由此想尝试的新事情。每行一条，必须以“想做：”开头，每条 6 到 14 个字，"
    "要具体、带动作和对象（例如“想做：学做一锅红烧肉”），写 1 到 3 条，"
    "不要解释，不要编号。"
)


def _text_of(res):
    """不同调用路径的返回值形状不一样：
    Pool.call_sync() 返回 ``(result, error)`` 元组；Job.result 直接是文本
    （llm._perform 里 job.finish(text.strip(), ...)）。这里统一成 (文本, 错误)。
    """
    err = None
    if isinstance(res, tuple):
        res, err = (list(res) + [None, None])[:2]
    if isinstance(res, dict):
        res = res.get("text") or res.get("content") or ""
    return ("" if res is None else str(res)).strip(), err


def _llm_text(messages, timeout=45.0):
    try:
        from . import llm
        pool = llm.get_pool()
        res = pool.call_sync(messages, timeout=timeout, temperature=0.95,
                             frequency_penalty=0.4, presence_penalty=0.3)
        return _text_of(res)[0]
    except Exception as exc:                                 # noqa: BLE001
        _STATE["errors"].append("llm: %r" % (exc,))
        _STATE["errors"] = _STATE["errors"][-8:]
        return ""


def _profile_line(rec):
    """把 people.py 的档案压成一行给 LLM 当人设。"""
    if not rec:
        return ""
    bits = [str(rec.get("cn") or rec.get("name") or "")]
    for key, tag in (("job", "职业"), ("mbti", "性格"), ("age", "年龄")):
        if rec.get(key):
            bits.append("%s%s" % (tag, rec[key]))
    if rec.get("hobbies"):
        bits.append("爱好" + "/".join(rec["hobbies"][:3]))
    if rec.get("intro"):
        bits.append(str(rec["intro"])[:70])
    return "，".join(b for b in bits if b)


def _build_day_messages(who, day, world, people_rec):
    """主角用真实行程，居民用档案 + 与主角的互动。"""
    st = getattr(world, "state", {}) or {}
    if str(who) in (st.get("name"), st.get("avatar"), "hero"):
        acts = [d.get("reason") or d.get("action")
                for d in (st.get("decisions") or [])[-14:]]
        used = [r for r in recent_chat(400) if r.get("day") == day]
        body = ["角色：主角 %s" % st.get("name"),
                "今天的行程：%s" % "；".join([a for a in acts if a][-10:]),
                "心情%d 精力%d 健康%d" % (round(st.get("happiness", 50)),
                                        round(st.get("energy", 50)),
                                        round(st.get("health", 50)))]
        if used:
            body.append("今天和别人的对话片段：%s"
                        % " / ".join("%s说%s" % (r.get("npc_cn"), r.get("say"))
                                     for r in used[-4:]))
        try:
            from . import feeds as _feeds
            w = _feeds.get_feeds().brief(3)
            # 补的是"那天"的日记，所以世界日志也按那一天取，别拿今天的充数
            day_line = _feeds.get_feeds().day_line(day)
            if day_line:
                w = dict(w or {})
                w["世界日志"] = day_line
            if w:
                body.append("那天外面：%s" % json.dumps(w, ensure_ascii=False))
        except Exception:                                   # noqa: BLE001
            pass
        hc = [m.get("text") for m in (st.get("hero_chat") or [])
              if m.get("who") == "you"][-2:]
        if hc:
            body.append("主人对他说过：%s" % "；".join(hc))
    else:
        used = [r for r in recent_chat(600)
                if r.get("npc") == who and r.get("day") == day]
        body = ["角色：%s" % _profile_line(people_rec)]
        if used:
            body.append("今天和主角的对话片段：%s"
                        % " / ".join("主角说%s，他答%s" % (r.get("reply"), r.get("say"))
                                     for r in used[-4:]))
        else:
            body.append("今天没有遇到主角，按自己的日程过日子。")
    return [dict(role="system", content=_SYS_DAY),
            dict(role="user", content="%s\n日期：%s\n请写日记。" % ("\n".join(body), day))]


def _clean_day(text):
    text = (text or "").strip().replace("\n", " ")
    for bad in ("日记", "“", "”", '"', "：", ":"):
        if text.startswith(bad):
            text = text[len(bad):].strip()
    return text[:200]


def _parse_wishes(text):
    """解析模型输出。若整段里出现过「想做：」就只认带前缀的行，
    否则把所有非空行都当愿望（小模型经常忘写前缀）。"""
    raw = [ln.strip().strip("-•*0123456789.、#＃ ") for ln in (text or "").splitlines()]
    raw = [ln for ln in raw if ln]
    pref = [ln for ln in raw if "想做：" in ln or "想做:" in ln]
    pool = pref if pref else raw
    out = []
    for ln in pool:
        if "想做：" in ln:
            ln = ln.split("想做：", 1)[1]
        elif "想做:" in ln:
            ln = ln.split("想做:", 1)[1]
        ln = ln.strip(" 　\"“”'》」").strip()
        if 4 <= len(ln) <= 30:
            out.append(ln)
    return out[:3]


def _who_list(world):
    st = getattr(world, "state", {}) or {}
    hero = st.get("name") or st.get("avatar")
    book = st.get("people") or {}
    out = [(hero, book.get(hero))] if hero else []
    for name, rec in book.items():
        if name != hero:
            out.append((name, rec))
    return out


def maybe_daily(world, now=None):
    """跨天时把「昨天」的每日经历排进后台队列。不阻塞调用方。"""
    cfg = get_config()
    if not cfg["enabled"] or not cfg["daily_enabled"]:
        return 0
    now = now or time.localtime()
    if hasattr(now, "strftime"):
        today = now.strftime("%Y-%m-%d")
        hour = int(now.strftime("%H"))
    else:
        today = time.strftime("%Y-%m-%d", now)
        hour = int(time.strftime("%H", now))
    if hour < int(cfg["daily_min_hour"]):
        return 0
    last = _STATE["last_day"]
    if last is None:
        _STATE["last_day"] = today
        return 0
    if today == last:
        _STATE["last_run"] = time.time()
        return 0
    if not cfg["enabled"]:
        return 0
    # 给「昨天」（以及中间漏掉的日子）补日记
    from . import llm as _llm
    queued = 0
    for who, rec in _who_list(world):
        if not who or who in _PENDING:
            continue
        if last_day_of(who) == last:       # 那天已经写过了，别重复追加
            continue
        msgs = _build_day_messages(who, last, world, rec)
        job = _llm.get_pool().submit("memory_day", msgs, temperature=0.95,
                                     frequency_penalty=0.4, presence_penalty=0.3)
        if job is not None:
            _PENDING[who] = {"job": job, "day": last, "kind": "day"}
            queued += 1
    _STATE["last_day"] = today
    if queued and _STATE.get("last_wish_day") != last:
        msgs = _build_wish_messages(last)
        job = _llm.get_pool().submit("memory_wish", msgs, temperature=1.0,
                                     frequency_penalty=0.5, presence_penalty=0.4)
        if job is not None:
            _PENDING["__wish__"] = {"job": job, "day": last, "kind": "wish"}
            _STATE["last_wish_day"] = last
    return queued


def _build_wish_messages(day):
    rows = [r for r in recent_chat(300) if r.get("day") == day][-12:]
    if not rows:
        rows = recent_chat(12)
    body = " / ".join("%s说%s，主角答%s" % (r.get("npc_cn"), r.get("say"),
                                          r.get("reply")) for r in rows)
    return [dict(role="system", content=_SYS_WISH),
            dict(role="user", content="聊天片段：%s" % (body or "（今天没怎么说话）"))]


def poll_pending():
    """把已完成的生成任务落盘。每次 tick 调一次即可。"""
    done = []
    for key, item in list(_PENDING.items()):
        job = item["job"]
        if not job.done:
            continue
        done.append(key)
        if job.error:
            _STATE["errors"].append("%s: %r" % (key, job.error))
            _STATE["errors"] = _STATE["errors"][-8:]
            continue
        try:
            res, _err = _text_of(job.result)
        except Exception:                                    # noqa: BLE001
            res = ""
        if not res:
            continue
        if item["kind"] == "day":
            text = _clean_day(res)
            if len(text) >= 8:
                record_day(key, item["day"], text)
                _STATE["generated"] += 1
        else:
            for w in _parse_wishes(res):
                add_wish(w, source="对话", day=item["day"])
    with _LOCK:
        for key in done:
            _PENDING.pop(key, None)
    if done:
        _STATE["last_run"] = time.time()
    return len(done)


# ─── introspection ──────────────────────────────────────────────────
def tick_hook(world, now=None):
    """world.tick() 每帧调用一次。自带节流，不会拖慢渲染。"""
    t = time.time()
    if t - _STATE.get("_tick_at", 0.0) < 3.0:
        return 0
    _STATE["_tick_at"] = t
    n = poll_pending()
    try:
        maybe_daily(world, now)
    except Exception as exc:                                 # noqa: BLE001
        _STATE["errors"].append("daily: %r" % (exc,))
        _STATE["errors"] = _STATE["errors"][-8:]
    return n


def stats():
    cfg = get_config()
    chat = _chat_ring()
    who = []
    ddir = os.path.join(DB_DIR, "days")
    if os.path.isdir(ddir):
        for fn in sorted(os.listdir(ddir)):
            if fn.endswith(".jsonl"):
                who.append({"who": fn[:-6],
                            "days": Ring(os.path.join(ddir, fn)).count()})
    last_all = {}
    for w in who:
        rows = _day_ring(w["who"]).tail(1)
        if rows:
            w["last_day"] = rows[0].get("day")
            last_all[w["who"]] = w["last_day"]
    return dict(
        enabled=bool(cfg["enabled"]),
        config=cfg,
        chat={"records": chat.count(),
              "bytes": chat.size_bytes(),
              "max_bytes": int(cfg["chat_max_mb"]) * 1024 * 1024,
              "day": (chat.tail(1) or [{}])[0].get("day")},
        days={"people": who, "total": sum(w["days"] for w in who),
              "max_per_who": int(cfg["day_max_per_who"])},
        wishes={"count": wish_count(), "max": int(cfg["wish_max"]),
                "recent": wishes(12)},
        pending=sorted(_PENDING.keys()),
        state=dict(_STATE),
        errors=_STATE["errors"][-5:],
    )


def reset_errors():
    _STATE["errors"] = []
