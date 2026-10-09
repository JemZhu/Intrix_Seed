#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""NPC small talk, written by the LLM.

One encounter = one request that produces BOTH sides of the exchange, so a
chance meeting costs a single call on the shared pool:

    {"say":"这么巧", "reply":"来一杯？", "emote":"note"}

Since v5 the prompt carries the *whole* person on the other side of the
conversation -- their name, job, personality blurb, mood, energy and the
current relationship score with the hero -- so a stranger nods, a friend teases,
and a 知己 asks how the week went.

While the request is in flight (or if the endpoint is off) `get()` returns None
and the renderer falls back to its little pixel emote, so nothing ever stalls
waiting for the network.

v6.5 -- "为什么有些人对话很固定" 的三处修复:
  1. 提示词不再提供任何可以照抄的完整例句。2B 模型会把 few-shot 例子原样
     复读（实测「天不错/跑两圈」「这么巧啊/来一杯」直接出现在线上输出里），
     现在只描述语气与风格，不给可抄的句子。
  2. Chatter 为每个 NPC 记住最近说过的 MAX_RECENT 句话，作为【最近说过】
     注入下一次请求，返回后做去重判定（全等 + 短句字符重合度），重复则
     提高温度重试；三轮仍重复才勉强接受。
  3. greet_context 补上「距上次相遇」，让同一地点同一动作的输入不再完全一样。

v6.6 -- 一句话说不完就分几个气泡说:
  每个气泡只有 6 个汉字，轮到谁说话谁才冒泡，renderer 依次弹出 —— 模型偶尔
  写超 6 个字时，是"分成第二个气泡"而不是"把第 7 个字以后砍掉"，屏幕上
  看不到「嘿今」这种半截话了。
  提示词刻意保持原样：实测 2B 模型对"可以多说一点"的措辞极其敏感，
  一提就写成二三十个字的长句（交替采样里 v6.5 均 15 字 → 改了变 25 字，
  合法率 19/24 → 13/24），所以分句全部放在客户端做。

v6.7 -- 气泡上限按人算:
  v6.6 是"一次偶遇全场最多 3 个"，预算紧张时先牺牲主角 —— 但客人本来就
  可能要说三句（12-18 个汉字），被裁掉第三句等于又把内容丢掉。现在每个
  说话的人各算各的：客人最多 3 个气泡，主角最多 3 个，一次偶遇理论上最多 6 个。
  渲染端不变，仍然是说完一个再冒下一个。
"""
import json
import random
import re
import threading
import time

from . import llm

SYSTEM = (
    "你是像素游戏里的对话生成器。每次偶遇会给你两个人、当时的时间地点、"
    "两人的性格与心情、以及他们的关系程度，请写出这俩人当场的一来一往。\n"
    "只输出一行 JSON，不要解释，不要 markdown，不要复述输入，不要用书名号：\n"
    '{"say":"对方说的话","reply":"主角回的话","emote":"heart|note|!|dots|hi|?"}\n'
    "say 是“对方”说的，reply 是“主角”回的，一人一句，各 1-6 个汉字。\n"
    "写作要求：\n"
    "1. 语气跟关系走——陌生人短、客气、点头即走；熟人随口一句家常；"
    "朋友会开玩笑、吐槽、提起两个人的共同经历；知己直接问近况；\n"
    "2. 语气跟性格与心情走——社牛主动热络、话多；内向只回三五个字；"
    "精力低会敷衍；心情差会抱怨或叹气；\n"
    "3. 贴着此刻的时间、地点和两人正在做的事来写，要能看出是谁在什么场合说的，"
    "不要写放之四海皆可的客套话；\n"
    "4. 严禁出现任何人名或称呼。"
)

MAX_CACHE = 64

SEG_CHARS = 6             # 一个气泡最多几个汉字（小屏的极限）
# v6.7: 上限是"每个说话的人最多几个气泡"，不是全场合计 —— 客人有话要说时
# 不该被主角的回复挤掉第二、第三句；主角照旧只会回一小句。
MAX_BUBBLES = 3
# 断句用的标点；逗号是主角，模型被要求在这里分两个气泡
_CLAUSE = re.compile(r"[，,、；;。.！!？?~…：:\s]+")
# 万不得已要硬切时，尽量切在这些字前面，别把词砍碎
_BREAK_BEFORE = "我你他她它这那谁咱大家再还就又都很太真好不对没别"

EMOTES = ("heart", "note", "!", "dots", "hi", "?")
GENERIC_EMOTES = ("hi", "!", "note")

# personality -> the emote that reads as "this person"
EMOTE_BY_TRAIT = {
    "社牛": "heart", "外向": "note", "选择性社交": "hi",
    "内向": "dots", "独来独往": "?",
}


def default_emote(person):
    """A plausible pixel emote when the LLM has not answered yet.

    Mostly the personality's signature emote, but not always -- otherwise the
    same resident would wear the same icon for the whole save file.
    """
    if not person:
        return random.choice(GENERIC_EMOTES)
    if person.get("stats", {}).get("happiness", 60) < 38:
        return "dots"
    if person.get("social") == "独来独往":
        return "?"
    pick = EMOTE_BY_TRAIT.get(person.get("social"), "hi")
    if random.random() < 0.6:
        return pick
    return random.choice(GENERIC_EMOTES + (pick,))


def gap_label(last):
    """「距上次相遇」写得像人话，而不是一串秒数。"""
    if not last:
        return "初次见面"
    try:
        d = max(0.0, time.time() - float(last))
    except (TypeError, ValueError):
        return "初次见面"
    if d < 3600:
        return "%d分钟前" % max(1, int(d / 60))
    if d < 86400:
        return "%d小时前" % int(d / 3600)
    return "%d天前" % int(d / 86400)


def _chop(chunk, seg=SEG_CHARS, min_tail=3):
    """把过长的句子切成 <= seg 个汉字的块。

    优先切在「我/你/这」这种能起句的字前面；要是尾巴只剩一两个字，就把切点
    往前挪一点 —— 宁可前一块短些，也别让孤零零一个「么」独占一个气泡。
    """
    if len(chunk) <= seg:
        return [chunk]
    cut = seg
    for k in range(seg, max(1, seg - 3), -1):
        if k < len(chunk) and chunk[k] in _BREAK_BEFORE:
            cut = k
            break
    if len(chunk) - cut < min_tail:
        cut = max(2, min(cut, len(chunk) - min_tail))
    return [chunk[:cut]] + _chop(chunk[cut:], seg, min_tail)


def _split_line(val, limit=MAX_BUBBLES, seg=SEG_CHARS):
    """把一句台词切成 1-3 个气泡，每个 <= 6 个汉字。

    模型自己用逗号断句时（"这么巧，你也来这"）就按逗号切；它一口气写了
    七八个字、十个字、十八个字的（线上很常见），就在 6 个字处切 —— 内容是
    分开说完的，不是被砍掉的。上限是"这个人最多说几句"。
    """
    if isinstance(val, (list, tuple)):                    # 模型偶尔还是给数组
        val = "，".join(x for x in val if isinstance(x, str))
    elif not isinstance(val, str):
        return []
    text = str(val or "").strip()
    if not text:
        return []
    for bad in ("\n", "\r", '"', "'", "“", "”", "「", "」"):
        text = text.replace(bad, " ")
    parts = []
    for chunk in _CLAUSE.split(text):
        chunk = chunk.strip()
        if chunk:
            parts.extend(_chop(chunk, seg))
    out = []
    for p in parts:
        if p not in out:                                  # 内部重复只留一句
            out.append(p)
        if len(out) >= limit:
            break
    return out


def _bubble_plan(npc_segs, hero_segs):
    """每个说话的人最多 MAX_BUBBLES 个气泡，客人先说完，主角再回。

    v6.7: 上限按人算（v6.6 是全场一共 3 个）。客人一句 12-18 个汉字的话本
    就该分三个气泡说完，之前会被主角那句挤掉一截 —— 现在各算各的预算，
    客人最多 3 个、主角最多 3 个，谁也不用给谁让位。
    """
    return ([dict(who="npc", text=s) for s in npc_segs[:MAX_BUBBLES]] +
            [dict(who="hero", text=s) for s in hero_segs[:MAX_BUBBLES]])


class Chatter(object):
    MAX_TRY = 3               # 解析失败或说重复了，就换温度再来
    MAX_RECENT = 6            # 每个 NPC 记住最近说过的句子（按句，不按气泡组）

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {}          # (npc, bucket) -> dict(npc=, hero=, emote=)
        self._jobs = {}           # (npc, bucket) -> (Job, forbidden, attempt, ctx)
        self._recent = {}         # npc -> [已经说过的句子]
        self.last_error = None
        self.dups = 0             # 判重拦截（会触发重试）
        self.accepted_dups = 0    # 三轮仍然重复，认了

    # -- memory --------------------------------------------------------
    def _recent_of(self, npc):
        with self._lock:
            return list(self._recent.get(npc) or [])

    def _remember(self, npc, *says):
        with self._lock:
            rec = self._recent.setdefault(npc, [])
            rec.extend(s for s in says if s)
            del rec[:-self.MAX_RECENT]

    @staticmethod
    def _strip_names(text, forbidden):
        """A 2B model loves squeezing a name into the line, and it truncates
        ("你也是Luc"), so every prefix of every name goes too."""
        for nm in forbidden:
            if not nm or len(nm) < 2:
                continue
            for k in range(len(nm), 1, -1):
                text = text.replace(nm[:k], "").replace(nm[:k].lower(), "")
        return text.strip()

    @staticmethod
    def _repeat(say, recent):
        """True if this line is essentially something the NPC just said."""
        if not say or not recent:
            return False
        a = set(say)
        for old in recent:
            if say == old:
                return True
            if len(say) < 2 or len(old) < 2:
                continue
            b = set(old)
            # 短句里大部分字都一样（「天不错」vs「天气不错」）算复读
            if len(a & b) / float(max(len(a), len(b))) >= 0.75:
                return True
        return False

    # -- request -------------------------------------------------------
    def ensure(self, npc, bucket, ctx, forbidden=()):
        """Fire once per (npc, 45s bucket). Never blocks."""
        cfg = llm.get_config()
        if not cfg.get("enabled") or not cfg.get("chat"):
            return
        key = (npc, int(bucket))
        with self._lock:
            if key in self._cache or key in self._jobs:
                return
        self._fire(key, ctx, forbidden, 0)

    def _fire(self, key, ctx, forbidden, attempt):
        pool = llm.get_pool()
        cfg = llm.get_config()
        # NOTE: 千万不要把「最近说过的话」塞进 prompt。实测 2B 模型会把它们
        # 当成该说的内容照抄（生成「你刚说 我请你」这种句子），越去重越重复。
        # 去重交给下面的客户端判重 + 升温重试，以及 penalty。
        job = pool.submit(
            "greet",
            [dict(role="system", content=SYSTEM),
             dict(role="user", content=json.dumps(ctx, ensure_ascii=False))],
            temperature=min(1.3, float(cfg.get("temperature")) + 0.15
                            + 0.12 * attempt),
            frequency_penalty=0.7,
            presence_penalty=0.5,
        )
        if job is not None:
            with self._lock:
                self._jobs[key] = (job, tuple(forbidden) + (key[0],), attempt, ctx)

    # -- collect --------------------------------------------------------
    def get(self, npc, bucket):
        key = (npc, int(bucket))
        with self._lock:
            entry = self._jobs.get(key)
        if entry is None:
            with self._lock:
                return self._cache.get(key)
        job, forbidden, attempt, ctx = entry
        if not job.done:
            return None
        with self._lock:
            self._jobs.pop(key, None)
        if job.error:
            self.last_error = job.error
            return None
        obj = llm.json_from(job.result)
        npc_segs = []
        hero_segs = []
        emote = "hi"
        if obj and (obj.get("say") or obj.get("npc")):
            code = str(obj.get("emote") or "hi").strip()
            emote = code if code in EMOTES else "hi"
            banned = tuple(forbidden)
            npc_segs = [self._strip_names(s, banned)
                        for s in _split_line(obj.get("say") or obj.get("npc"))]
            hero_segs = [self._strip_names(s, banned)
                         for s in _split_line(obj.get("reply") or obj.get("hero"))]
            npc_segs = [s[:SEG_CHARS] for s in npc_segs if s]
            hero_segs = [s[:SEG_CHARS] for s in hero_segs if s]
        seq = _bubble_plan(npc_segs, hero_segs)
        say = " ".join(npc_segs)
        reply = " ".join(hero_segs)
        if any(self._repeat(s, self._recent_of(npc)) for s in npc_segs):
            self.dups += 1
            if attempt + 1 < self.MAX_TRY:
                self._fire(key, ctx, forbidden, attempt + 1)
                return None
            # 三轮都是同一句，宁可有台词也别让屏幕空着
            self.accepted_dups += 1
        if not npc_segs:
            if attempt + 1 < self.MAX_TRY:
                self._fire(key, ctx, forbidden, attempt + 1)
            return None
        line = dict(npc=say, hero=reply, emote=emote, seq=seq, ts=time.time())
        with self._lock:
            self._cache[key] = line
            while len(self._cache) > MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))
        self._remember(npc, *npc_segs)
        # v6.13: 每一轮对话都进长期记忆（面板可回看，也供日记取材）
        try:
            from . import memory
            memory.record_chat(npc, ((ctx or {}).get("对方") or {}).get("名字"),
                               npc_segs, hero_segs,
                               room=(ctx or {}).get("地点"), emote=emote)
        except Exception:                                  # noqa: BLE001
            pass
        return line

    def stats(self):
        with self._lock:
            return dict(cached=len(self._cache), pending=len(self._jobs),
                        last_error=self.last_error, dups=self.dups,
                        accepted_dups=self.accepted_dups,
                        tracked=len(self._recent))


_CHATTER = None


def chatter():
    global _CHATTER
    if _CHATTER is None:
        _CHATTER = Chatter()
    return _CHATTER


def _world_brief(n=5):
    """新闻 + 天气 —— 给模型一个"外面在发生什么"的参照。"""
    try:
        from . import feeds
        return feeds.get_feeds().brief(n)
    except Exception:                                       # noqa: BLE001
        return None


def _world_log(n=3):
    """世界日志的最近 n 天 —— 偶遇聊天也得知道这几天外面在聊什么。"""
    try:
        from . import feeds
        return feeds.get_feeds().log_brief(n)
    except Exception:                                       # noqa: BLE001
        return []


def greet_context(world, now, npc_name, room_label, hero_action, relation,
                  person=None, intent="偶遇"):
    """The digest the dialogue model reads.

    `person` is the resident record from people.py: passing it is what lets the
    model answer *as that character* instead of as a generic NPC.
    """
    s = world.state
    st = (person or {}).get("stats") or {}
    rel = (person or {}).get("rel") or {}
    score = float(rel.get("score", 0))
    ctx = dict(
        时间="%s %s" % (["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                        world.time_label(now)),
        时段=world.daypart(now),
        地点=room_label,
        场景=intent,
        我=dict(名字=s.get("name"), 正在做=hero_action,
                心情=round(s.get("happiness", 50)),
                精力=round(s.get("energy", 50)),
                健康=round(s.get("health", 50)),
                性格=dict(MBTI=s.get("mbti"), 社交=s.get("social_tendency"),
                          节奏=s.get("life_pace")),
                爱好=s.get("hobbies", [])[:3]),
        对方=dict(名字=(person or {}).get("cn") or npc_name,
                  性别=(person or {}).get("gender"),
                  年龄=(person or {}).get("age"),
                  职业=(person or {}).get("job"),
                  性格=dict(MBTI=(person or {}).get("mbti"),
                            社交=(person or {}).get("social"),
                            节奏=(person or {}).get("pace")),
                  简介=(person or {}).get("intro"),
                  爱好=(person or {}).get("hobbies", [])[:3],
                  心情=round(st.get("happiness", 60)) if st else None,
                  精力=round(st.get("energy", 70)) if st else None,
                  现在的情绪=(person or {}).get("mood")),
        关系=dict(称呼=relation, 好感度=round(score),
                  认识次数=int(rel.get("met", 0)),
                  送过礼物=int(rel.get("gifts", 0)),
                  距上次相遇=gap_label(rel.get("last"))),
        外面=_world_brief(2),
        世界日志=_world_log(3),
    )
    # v6.13: 「旧事」= 记忆库里这位居民的近况摘要（第三人称叙述）。
    # 刻意不塞原话：v6.5 实测把"最近说过的话"放进 prompt，2B 模型会把它
    # 当成本场台词照抄（唯一率 24%→7）。要打开原话注入就把配置里的
    # chat_recall_lines 调成 >0，并接受复读风险。
    try:
        from . import memory
        old = memory.recall(npc_name)
        if old:
            ctx["旧事"] = old
        n_orig = int(memory.get_config().get("chat_recall_lines") or 0)
        if n_orig > 0:
            seen = memory.chat_for(npc_name, n=n_orig)
            if seen:
                ctx["聊过"] = [dict(哪天=r.get("day"), 他说=r.get("say"),
                                    我答=r.get("reply")) for r in seen]
    except Exception:                                      # noqa: BLE001
        pass
    return ctx
