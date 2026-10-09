#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Residents: a persona sheet + a live stat block for every character.

Why this module exists
----------------------
Before this, only the hero had a personality. Everybody else was a sprite that
walked around and said "hi". Now every character -- hero, friends, the chef in
the cafe, the kid in the park -- owns:

  * an identity      : Chinese name, gender, age, job, catchphrase
  * a personality    : MBTI, life pace, social tendency, stock style, spending
                       style, three hobbies, one quirk
  * a written blurb  : a one-sentence description assembled from the above
  * the same stat panel as the hero (health / mood / hunger / energy / charm /
    wealth) that drifts on its own clock and reacts to their own traits
  * a relationship record with the hero: 0-100 score, rank name, how many times
    they have met, gifts exchanged, and the last few interactions

Everything is derived from `zlib.crc32(name)` rather than Python's `hash()`,
because `hash()` is salted per process: a restart would otherwise hand Alex a
brand new childhood every time the service bounced. Same name -> same person,
forever.

The relationship score is what makes the network matter: it gates how warm a
greeting is, it decides who shows up when the hero goes looking for company,
and it drifts down if you never visit.
"""
import random
import time
import zlib

# ─── name material ──────────────────────────────────────────────────
SURNAMES = list("李王张刘陈杨黄赵吴周徐孙马朱胡林何郭高罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任")
GIVEN_F = ["雨桐", "思琪", "佳怡", "若曦", "静姝", "梦瑶", "子萱", "嘉宁",
           "雅静", "欣然", "可儿", "念安", "书瑶", "一诺", "柔嘉", "文静"]
GIVEN_M = ["子轩", "浩然", "俊杰", "宇轩", "晨曦", "文博", "嘉树", "斯年",
           "亦辰", "明轩", "志远", "建国", "怀安", "望舒", "行舟", "青野"]

JOBS = ["程序员", "咖啡师", "中学老师", "护士", "健身教练", "图书管理员",
        "平面设计师", "会计", "厨师", "快递员", "理发师", "记者", "宠物医生",
        "调酒师", "牙医", "插画师", "产品经理", "大学生", "超市店长", "摄影师",
        "乐队鼓手", "游戏策划", "花艺师", "编剧", "药剂师", "翻译"]
KID_JOBS = ["小学生", "初中生"]
ELDER_JOBS = ["退休教师", "早点铺老板", "小区保安", "花店老板"]

MBTI = ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"]
LIFE_PACES = ["早鸟型", "夜猫型", "工作狂", "佛系", "张弛有度"]
SOCIAL_TEND = ["社牛", "外向", "选择性社交", "内向", "独来独往"]
STOCK_STYLES = ["激进追涨", "稳健价值", "成长赛道", "短线博弈", "长期持有", "指数定投"]
CONSUME_STYLES = ["奢靡主义", "实用至上", "科技尝鲜", "潮流跟风", "极简断舍离", "吃货本货", "收藏癖"]
HOBBIES = ["炒股", "装修", "旅行", "阅读", "健身", "追剧", "做饭", "摄影", "游戏",
           "咖啡", "音乐", "画画", "遛狗", "手工", "电影", "游泳", "园艺", "钓鱼",
           "唱歌", "桌游", "骑行", "烘焙", "拳击", "露营"]

CATCH_PHRASES = ["随缘啦", "问题不大", "先干为敬", "缓缓就过去了", "我请你",
                 "这个我熟", "明天再说", "稳住别浪", "有意思", "让我想想",
                 "走一个", "干就完了", "别急嘛", "再睡五分钟", "成交"]
QUIRKS = ["兜里常备一块黑巧", "下雨天一定带伞", "认路全靠手机", "只喝手冲不喝速溶",
          "手机壳换了十七个", "养了盆快死的绿萝", "收藏每一张电影票",
          "走路数地砖", "煮泡面要掐秒表", "口袋里永远有耳机", "喝汤必须配勺子",
          "书看到一半就睡着", "会把剩饭做成蛋炒饭", "冬天也吃冰淇淋",
          "给所有流浪猫起名字", "拍照一定比耶"]
REL_TAGS = ["邻居", "同事", "大学同学", "高中同学", "健身房认识的", "网友",
            "表亲", "同一个小区", "老同学", "读书会认识的", "同行", "发小"]

# ─── relationship ranks ─────────────────────────────────────────────
RANKS = [(96, "知己"), (86, "挚友"), (70, "好朋友"), (50, "朋友"),
         (30, "熟人"), (12, "点头之交"), (0, "陌生人")]

# interaction kinds -> base score movement
KIND_DELTA = {
    "greet": 2, "chat": 3, "help": 6, "gift": 9, "date": 7,
    "party": 4, "work": 2, "visit": 5, "argue": -6, "ignore": -2,
    "gift_bad": 1,
}


def _seed(name):
    """Stable 32-bit seed: survives restarts (unlike hash())."""
    return zlib.crc32(("pxp:" + str(name)).encode("utf-8")) & 0xFFFFFFFF


def rank_of(score):
    for lo, label in RANKS:
        if score >= lo:
            return label
    return RANKS[-1][1]


def _blurb(p):
    """One written sentence, assembled from the traits."""
    bits = []
    bits.append("%d岁的%s" % (p["age"], p["job"]))
    bits.append("%s·%s" % (p["mbti"], p["pace"]))
    bits.append(p["social"])
    bits.append("花销上%s" % p["consume"])
    hobby = "、".join(p["hobbies"][:2])
    tail = "%s爱%s；%s。" % ("平时" if hobby else "", hobby or "发呆", p["quirk"])
    return "，".join(bits) + "。" + tail


def make(name, rng=None):
    """Build a brand new resident from a sprite name."""
    r = rng or random.Random(_seed(name))
    kid = "Kid" in str(name) or "Zombie" in str(name)
    witch = "Witch" in str(name)
    gender = "女" if (r.random() < 0.5 or witch) else "男"
    given = r.choice(GIVEN_F if gender == "女" else GIVEN_M)
    if witch:
        given = "月姬"
    cn = r.choice(SURNAMES) + given
    if kid:
        age = r.randint(8, 13)
        job = r.choice(KID_JOBS)
    elif witch:
        age = r.randint(300, 900)
        job = "药师"
    else:
        age = r.randint(21, 44)
        job = r.choice(JOBS)
        if r.random() < 0.12:
            age = r.randint(55, 71)
            job = r.choice(ELDER_JOBS)
    p = dict(
        name=name, cn=cn, gender=gender, age=age, job=job,
        mbti=r.choice(MBTI), pace=r.choice(LIFE_PACES),
        social=r.choice(SOCIAL_TEND), stock=r.choice(STOCK_STYLES),
        consume=r.choice(CONSUME_STYLES),
        hobbies=r.sample(HOBBIES, 3),
        catch=r.choice(CATCH_PHRASES), quirk=r.choice(QUIRKS),
        stats=dict(
            health=r.randint(55, 95), happiness=r.randint(42, 90),
            hunger=r.randint(35, 85), energy=r.randint(45, 95),
            charm=r.randint(28, 82), wealth=r.choice([0, 600, 2200, 5400, 12000, 31000]),
        ),
        rel=dict(score=0, met=0, gifts=0, first=time.time(), last=0.0,
                 tag=r.choice(REL_TAGS), notes=[]),
        born=time.time(), seen=time.time(), mood="平静",
    )
    p["intro"] = _blurb(p)
    return p


# ─── storage ────────────────────────────────────────────────────────
def ensure(state, name, rng=None):
    """Return the resident record, creating it on first sight."""
    if not name:
        return None
    book = state.setdefault("people", {})
    rec = book.get(name)
    if rec is None:
        rec = make(name, rng)
        book[name] = rec
    rec.setdefault("stats", {})
    for k, v in make(name).get("stats", {}).items():
        rec["stats"].setdefault(k, v)
    rec.setdefault("rel", dict(score=0, met=0, gifts=0, first=time.time(),
                               last=0.0, tag="邻居", notes=[]))
    rec["rel"].setdefault("notes", [])
    rec.setdefault("intro", _blurb(rec))
    return rec


def ensure_many(state, names, rng=None):
    return [ensure(state, n, rng) for n in (names or [])]


def all_names(state):
    return sorted((state.get("people") or {}).keys())


# ─── hero side ──────────────────────────────────────────────────────
HERO_JOBS = ["程序员", "产品经理", "设计师", "会计", "编辑", "摄影师"]


def build_hero(state, rng):
    """Give the hero the same identity fields the NPCs get."""
    r = rng
    gender = r.choice(["男", "女"])
    given = r.choice(GIVEN_M if gender == "男" else GIVEN_F)
    state.setdefault("cn", r.choice(SURNAMES) + given)
    state.setdefault("gender", gender)
    state.setdefault("age", r.randint(22, 34))
    state.setdefault("job", r.choice(HERO_JOBS))
    state.setdefault("catch", r.choice(CATCH_PHRASES))
    state.setdefault("quirk", r.choice(QUIRKS))
    state.setdefault("career", dict(level=1, hours=0.0, skill=r.randint(28, 46),
                                    title="初级" + state["job"], parttime=None))
    state.setdefault("savings", 0)
    state.setdefault("wardrobe", [])
    state.setdefault("journal", [])
    state.setdefault("social_note", None)
    state.setdefault("interest_day", int(time.time() // 86400))
    state.setdefault("people", {})
    state.setdefault("goal", dict(save=5000, level=1))
    # the hero's blurb is derived the same way, so the panel looks uniform
    hero = dict(cn=state["cn"], age=state["age"], job=state["job"],
                mbti=state["mbti"], pace=state["life_pace"],
                social=state["social_tendency"], consume=state["consume_style"],
                hobbies=state.get("hobbies") or [], quirk=state["quirk"])
    state.setdefault("intro", _blurb(hero))


# ─── relationship bookkeeping ───────────────────────────────────────
def meet(state, name, kind="greet", rng=None):
    """Record an interaction. Returns (delta, score, rank)."""
    rec = ensure(state, name, rng)
    if rec is None:
        return 0, 0, "陌生人"
    rel = rec["rel"]
    base = KIND_DELTA.get(kind, 1)
    score = float(rel.get("score", 0))
    # climbing the last stretch is slower: being someone's 知己 should cost time
    if base > 0:
        scale = 1.0 - min(0.62, score / 150.0)
        delta = base * scale
        if kind == "gift":
            # a gift lands harder on an introvert, and hard on a stranger
            if rec.get("social") in ("内向", "独来独往", "选择性社交"):
                delta *= 1.35
            rel["gifts"] = int(rel.get("gifts", 0)) + 1
    else:
        delta = float(base)
    rel["score"] = max(0.0, min(100.0, score + delta))
    rel["met"] = int(rel.get("met", 0)) + 1
    rel["last"] = time.time()
    note = {"kind": kind, "ts": time.time(), "delta": round(delta, 1)}
    rel["notes"] = (rel.get("notes") or [])[-7:] + [note]
    return round(delta, 1), round(rel["score"], 1), rank_of(rel["score"])


def decay(state, seconds):
    """People you never visit slowly drift out of your life."""
    h = seconds / 3600.0
    if h <= 0:
        return
    now = time.time()
    for rec in (state.get("people") or {}).values():
        rel = rec.get("rel") or {}
        last = rel.get("last") or rel.get("first") or now
        if now - last < 6 * 3600:
            continue
        rel["score"] = max(0.0, float(rel.get("score", 0)) - 0.35 * h)


def drift(state, seconds, rng=None):
    """Let the residents live a little: stats wander, moods follow traits."""
    h = seconds / 3600.0
    if h <= 0:
        return
    r = rng or random.Random(int(time.time()) & 0xFFFF)
    for rec in (state.get("people") or {}).values():
        st = rec.get("stats") or {}
        if not st:
            continue
        st["hunger"] = _clamp(st.get("hunger", 60) + 3.0 * h)
        st["energy"] = _clamp(st.get("energy", 70) - 2.0 * h)
        # a personality has a homeostatic mood it keeps returning to
        base = {"社牛": 68, "外向": 64, "选择性社交": 58,
                "内向": 54, "独来独往": 50}.get(rec.get("social"), 58)
        if rec.get("pace") == "佛系":
            base += 4
        if rec.get("pace") == "工作狂":
            base -= 3
        st["happiness"] = _clamp(st.get("happiness", 60) +
                                 (base - st.get("happiness", 60)) * min(1.0, 0.25 * h))
        if st.get("hunger", 0) > 82 or st.get("energy", 100) < 22:
            st["health"] = _clamp(st.get("health", 70) - 1.2 * h)
        rec["mood"] = mood_word(st)      # a label, not a stat -- keep stats numeric
        rec["seen"] = time.time()


def mood_word(st):
    if not st:
        return "平静"
    hp, en = st.get("happiness", 60), st.get("energy", 70)
    if hp >= 78:
        return "雀跃"
    if hp >= 62:
        return "还不错"
    if hp >= 46:
        return "平静"
    if hp >= 32:
        return "有点低落"
    return "蔫了"


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


# ─── editing (web panel) ────────────────────────────────────────────
NPC_FIELDS = ("cn", "gender", "age", "job", "mbti", "pace", "social",
              "stock", "consume", "catch", "quirk")
# NPC record key -> hero state field
HERO_FIELDS = {"cn": "cn", "gender": "gender", "age": "age", "job": "job",
               "mbti": "mbti", "pace": "life_pace", "social": "social_tendency",
               "stock": "stock_style", "consume": "consume_style",
               "catch": "catch", "quirk": "quirk"}


def _clean_hobbies(v):
    if isinstance(v, str):
        v = [h.strip() for h in v.replace("，", ",").split(",") if h.strip()]
    if not isinstance(v, list):
        return None
    v = [str(h)[:8] for h in v][:4]
    return v or None


def edit_person(state, key, fields, valid_sprites=None):
    """Apply panel edits to the hero (key == state name/avatar) or an NPC.

    Changing the sprite moves the NPC record to the new key (the record key IS
    the sprite name) and rewrites any references. Returns (ok, message).
    """
    fields = fields or {}
    if not isinstance(fields, dict) or not fields:
        return False, "没有要修改的字段"
    names = set(valid_sprites or ())

    if key in (state.get("name"), state.get("avatar"), "hero"):
        for f, target in HERO_FIELDS.items():
            if f in fields and fields[f] not in (None, ""):
                v = fields[f]
                if f == "age":
                    try:
                        v = max(1, min(120, int(v)))
                    except Exception:
                        continue
                if f == "cn" and not str(v).strip():
                    continue
                state[target] = v
        hv = _clean_hobbies(fields.get("hobbies"))
        if hv:
            state["hobbies"] = hv
        sprite = fields.get("sprite")
        if sprite and sprite != state.get("avatar"):
            if names and sprite not in names:
                return False, "形象 %s 不存在" % sprite
            if sprite in (state.get("people") or {}):
                return False, "形象 %s 已有居民在用" % sprite
            state["name"] = sprite
            state["avatar"] = sprite
        # rebuild the written blurb from the new traits
        hero = dict(cn=state["cn"], age=state["age"], job=state["job"],
                    mbti=state["mbti"], pace=state["life_pace"],
                    social=state["social_tendency"],
                    consume=state["consume_style"],
                    hobbies=state.get("hobbies") or [], quirk=state["quirk"])
        state["intro"] = _blurb(hero)
        return True, "主角已更新"

    book = state.setdefault("people", {})
    rec = book.get(key)
    if rec is None:
        return False, "没有这个居民"

    for f in NPC_FIELDS:
        if f in fields and fields[f] not in (None, ""):
            v = fields[f]
            if f == "age":
                try:
                    v = max(1, min(120, int(v)))
                except Exception:
                    continue
            if f == "cn" and not str(v).strip():
                continue
            rec[f] = v
    hv = _clean_hobbies(fields.get("hobbies"))
    if hv:
        rec["hobbies"] = hv

    sprite = fields.get("sprite")
    hero_sprite = state.get("avatar") or state.get("name")
    if sprite and sprite != key:
        if names and sprite not in names:
            return False, "形象 %s 不存在" % sprite
        if sprite in book or sprite == hero_sprite:
            return False, "形象 %s 已有人在用" % sprite
        # move the record: the key is the sprite name
        del book[key]
        rec["name"] = sprite
        book[sprite] = rec
        friends = state.get("friends") or []
        state["friends"] = [sprite if f == key else f for f in friends]
    rec["intro"] = _blurb(rec)
    return True, "%s 已更新" % rec.get("cn", rec.get("name", key))


# ─── read-outs for the console ──────────────────────────────────────
def panel(state, limit=None):
    """Every resident with persona + stats + relationship, for the web UI."""
    out = []
    for name, rec in sorted((state.get("people") or {}).items(),
                            key=lambda kv: -kv[1].get("rel", {}).get("score", 0)):
        rel = rec.get("rel") or {}
        st = rec.get("stats") or {}
        out.append(dict(
            key=name, cn=rec.get("cn", name), gender=rec.get("gender"),
            age=rec.get("age"), job=rec.get("job"), mbti=rec.get("mbti"),
            pace=rec.get("pace"), social=rec.get("social"), stock=rec.get("stock"),
            consume=rec.get("consume"), hobbies=rec.get("hobbies", []),
            catch=rec.get("catch"), quirk=rec.get("quirk"),
            intro=rec.get("intro", ""), mood=rec.get("mood") or mood_word(st),
            stats=dict((k, round(v)) for k, v in st.items()
                       if isinstance(v, (int, float))),
            relation=dict(score=round(rel.get("score", 0), 1),
                          rank=rank_of(rel.get("score", 0)),
                          met=int(rel.get("met", 0)),
                          gifts=int(rel.get("gifts", 0)),
                          tag=rel.get("tag"), last=rel.get("last", 0)),
        ))
        if limit and len(out) >= limit:
            break
    return out


def warmest(state, n=3):
    """The people the hero would actually go out of their way to see."""
    rows = panel(state)
    return rows[:n]


def hero_panel(state):
    return dict(
        key=state.get("avatar"), cn=state.get("cn"), gender=state.get("gender"),
        age=state.get("age"), job=state.get("job"),
        title=(state.get("career") or {}).get("title"),
        skill=round((state.get("career") or {}).get("skill", 0)),
        level=(state.get("career") or {}).get("level", 1),
        mbti=state.get("mbti"), pace=state.get("life_pace"),
        social=state.get("social_tendency"), stock=state.get("stock_style"),
        consume=state.get("consume_style"), hobbies=state.get("hobbies", []),
        catch=state.get("catch"), quirk=state.get("quirk"),
        intro=state.get("intro", ""),
        stats=dict(health=round(state.get("health", 0)),
                   happiness=round(state.get("happiness", 0)),
                   hunger=round(state.get("hunger", 0)),
                   energy=round(state.get("energy", 0)),
                   charm=round(state.get("charm", 0)),
                   wealth=round(state.get("wealth", 0))),
        net_worth=round(state.get("wealth", 0) + state.get("savings", 0)),
        savings=round(state.get("savings", 0)),
        wardrobe=state.get("wardrobe", []),
    )


def story(state, name, now=None):
    """A short 'met at X, we are now Y' line for the marquee."""
    rec = (state.get("people") or {}).get(name)
    if not rec:
        return ""
    rel = rec.get("rel") or {}
    return "%s(%s·%s)" % (rec.get("cn", name), rank_of(rel.get("score", 0)),
                          rec.get("mood") or mood_word(rec.get("stats") or {}))
