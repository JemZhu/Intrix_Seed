#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The little person's brain.

Two tiers, deliberately:
  1. a deterministic desire-scoring engine that ALWAYS works and encodes circadian
     rhythm, personal style, physiology -- and, since v5, a set of *self-preserving
     guard rails*: do not spend the wallet to zero, do not let health slide into
     illness, do not let the mood rot. Plus the social drives that make the
     relationship network something the hero actively tends.
  2. an LLM tier that, when an endpoint is configured, looks at the same digest and
     decides what the person *wants* to do next. It runs on the shared worker pool
     and its answer is cached, so rendering is never blocked.

Everything the LLM sees is a compact JSON digest of the world -- including the
relationship network, the career ladder, savings and today's story so far; every-
thing it returns must be a single action key from the vocabulary it was offered,
and that key is re-checked against the clock before it is applied.
"""
import json
import time

from . import people
from .world import ACTIONS, PARTTIME

# What "too poor to be picky" and "too sick to push" mean, in one place.
CASH_POOR = 320          # below this, luxuries get suppressed
CASH_BROKE = 120         # below this, earning is the only plan
HEALTH_WEAK = 50         # below this, the body starts having opinions
HEALTH_SICK = 32         # below this, the clinic is the answer
MOOD_LOW = 50            # below this, fun and company climb the list
MOOD_SAD = 32            # below this, fun is basically mandatory

# Actions that cost real money (drives carry a negative wealth so the scorer can
# see the price tag without a second lookup). The clinic is never a luxury, so
# it stays affordable even at the bottom of the wallet.
PRICEY = [k for k, a in ACTIONS.items()
          if a["drives"].get("wealth", 0) <= -90 and k != "sick"]
NEVER_BLOCK = ("sick", "cook", "sleep", "takeout")
# Actions that strain the body.
STRENUOUS = ("overtime", "delivery", "hike", "cycle", "party", "drink",
             "karaoke", "gaming", "night_out", "freelance")
# Free/cheap ways to feel better.
CHEER = ("entertain", "social", "listen", "stroll", "walk_pet", "boardgame",
         "movie", "karaoke", "gaming", "sing", "paint", "volunteer", "exhibit",
         "window_shop", "garden", "fish", "photo", "party", "call_friend")
# Ways to bring money in.
EARNERS = ("work", "overtime", "freelance", "delivery", "flyer", "convenience",
           "tutor", "stall", "live_stream")


def _scores(world, now):
    """Return {action: weight}. Higher = more likely, 0 = not now."""
    s = world.state
    r = world.rng
    w = {}
    night = world.is_night(now)
    workday = now.weekday() < 5
    work_hours = world.is_work_hours(now)
    market = world.market_open(now)
    weekend = now.weekday() >= 5
    hour = now.hour

    energy, hunger = s["energy"], s["hunger"]
    happy, health = s["happiness"], s["health"]
    cash = float(s.get("wealth", 0))
    net = world.net_worth()
    goal = (s.get("goal") or {}).get("save", 5000)

    poor = cash < CASH_POOR
    broke = cash < CASH_BROKE
    weak = health < HEALTH_WEAK
    sick = health < HEALTH_SICK
    low_mood = happy < MOOD_LOW
    sad = happy < MOOD_SAD

    # ---- physiology has veto power ----
    if energy < 16:
        # during the day a nap is the civilised answer; at night, bed
        w["nap" if 11 <= hour <= 16 else "sleep"] = 100
        return w
    if hunger < 18:
        if cash < 90:
            w["cook"] = 100                      # eating out is not an option
        else:
            w["cook" if r.random() < 0.6 else "eat_out"] = 100
        return w
    if sick:
        w["sick"] = 120

    # ---- schedule ----
    if night:
        w["sleep"] = 40 + max(0, (60 - energy))
        late = hour >= 23 or hour < 1
        w["movie"] = 5 if late else 16
        w["karaoke"] = 3 if late else 13
        w["drink"] = 5 if late else 15
        w["stargaze"] = 12
        w["gaming"] = 6 if late else 12
        w["read"] = 10
        w["listen"] = 10
        w["entertain"] = 14
        w["journal"] = 10
        w["freelance"] = 14
        w["live_stream"] = 10
        if s["life_pace"] == "夜猫型":
            w["entertain"] = 20
            w["study"] = 10
            w["gaming"] = 18
            w["live_stream"] = 16
            w["sleep"] *= 0.7
        if not broke:
            w["boardgame"] = 9
            w["watch_game"] = 8 if hour >= 19 else 0
        return _guard(world, w, s, now, poor, broke, weak, sick,
                      low_mood, sad, cash, net, goal)

    if market and cash > 300:
        w["stock"] = 26 + (30 if "炒股" in s["hobbies"] else 0)
        if s["stock_style"] in ("激进追涨", "短线博弈"):
            w["stock"] += 14

    if workday and work_hours:
        if energy > 35:
            w["work"] = 52
            if s["life_pace"] == "工作狂" or happy > 70:
                w["overtime"] = 12
        else:
            w["work"] = 18

    # ---- discretionary ----
    w["cook"] = max(0, 30 - hunger * 0.25)
    w["eat_out"] = 16 if cash > 200 else 4
    w["entertain"] = max(0, 44 - happy) * 0.9
    w["gym"] = (26 if "健身" in s["hobbies"] else 12) * (1.4 if health < 62 else 0.7)
    w["bath"] = 14 + (10 if s["charm"] < 45 else 0)
    w["study"] = 18 if "阅读" in s["hobbies"] else 11
    w["shop"] = (20 if s["consume_style"] in ("奢靡主义", "潮流跟风", "收藏癖") else 9) \
        * (2.0 if cash > 3000 else 0.3)
    w["decorate"] = (18 if "装修" in s["hobbies"] else 7) * (1.8 if cash > 6000 else 0.2)
    w["travel"] = (26 if "旅行" in s["hobbies"] else 8) * (2.2 if weekend else 0.4) \
        * (1.6 if cash > 5000 else 0.2)
    w["social"] = {"社牛": 34, "外向": 26, "选择性社交": 16,
                   "内向": 9, "独来独往": 4}.get(s["social_tendency"], 14) \
        * (1.5 if low_mood else 1.0)
    w["stroll"] = (18 if "遛狗" in s["hobbies"] or "摄影" in s["hobbies"] else 8) \
        * (1.6 if weekend else 0.8)
    w["idle"] = 8

    # ---- recruits from the new rooms ----
    w["sing"] = (22 if "音乐" in s["hobbies"] else 9) * (1.4 if low_mood else 0.9)
    w["paint"] = (20 if "画画" in s["hobbies"] else 7) * (1.3 if low_mood else 0.9)
    w["party"] = (24 if s["social_tendency"] in ("社牛", "外向") else 6) \
        * (1.9 if (weekend or hour >= 19) else 0.4)
    w["trick"] = 6 + (10 if happy > 70 else 0)
    if s.get("pet"):
        w["walk_pet"] = 15 + (8 if weekend else 0)
    if health < 40:
        w["sick"] = max(w.get("sick", 0), 110)

    # ---- v3 venues: errands by day, city lights by night ----
    if workday and 7 <= hour <= 9:
        w["commute"] = 48
    if 12 <= hour <= 14 and energy < 62:
        w["nap"] = 22 + (62 - energy) * 0.7
    w["coffee"] = (24 if "咖啡" in s["hobbies"] else 11) \
        * (1.5 if energy < 55 else 0.8) * (1.3 if hour >= 13 else 1.0) \
        * (1.6 if cash > 200 else 0.4)
    w["read"] = (20 if "阅读" in s["hobbies"] else 8) * (1.3 if hour >= 19 else 1.0)
    w["class"] = 18 if (workday and 9 <= hour <= 17) else 3
    w["movie"] = (20 if "电影" in s["hobbies"] else 9) \
        * (1.8 if (weekend or hour >= 19) else 0.4) \
        * (1.6 if cash > 300 else 0.3)
    w["grocery"] = 12 + (20 if hunger < 48 else 0)
    w["gaming"] = (22 if "游戏" in s["hobbies"] else 9) * (1.3 if low_mood else 0.9)
    w["drink"] = (18 if s["social_tendency"] in ("社牛", "外向") else 7) \
        * (2.0 if hour >= 19 else 0.2) * (1.5 if cash > 300 else 0.3)
    w["swim"] = (18 if "游泳" in s["hobbies"] else 7) * (1.4 if health < 68 else 0.9)
    w["garden"] = (16 if "园艺" in s["hobbies"] else 5) \
        * (1.6 if weekend else 0.6) * (1.5 if 8 <= hour <= 17 else 0.2)
    w["bank"] = 16 if (workday and 9 <= hour <= 16) else 3
    w["takeout"] = 9 + (26 if hunger < 45 else 0) \
        * (1.4 if cash > 150 else 0.4)
    w["clean"] = (12 if weekend else 5) + (10 if low_mood else 0)
    w["photo"] = (14 if "摄影" in s["hobbies"] else 5) * (1.5 if 8 <= hour <= 17 else 0.2)
    w["fish"] = (14 if "钓鱼" in s["hobbies"] else 4) * (1.8 if weekend else 0.3)
    w["karaoke"] = (18 if ("唱歌" in s["hobbies"] or "音乐" in s["hobbies"]) else 7) \
        * (1.9 if (weekend or hour >= 19) else 0.3)
    w["date"] = (20 if (s["charm"] > 52 and s["social_tendency"] in
                        ("社牛", "外向", "选择性社交")) else 4) \
        * (1.6 if (weekend or hour >= 18) else 0.5)

    # ---- v5: body, home, culture, side income, and other people ----
    w["jog"] = (16 if "健身" in s["hobbies"] else 7) * (1.6 if weak else 0.7)
    w["yoga"] = (14 if health < 70 else 7) * (1.3 if low_mood else 0.9)
    w["cycle"] = (12 if "骑行" in s["hobbies"] else 5) * (1.7 if weekend else 0.5)
    w["hike"] = (16 if "露营" in s["hobbies"] else 5) \
        * (2.0 if weekend else 0.15) * (1.4 if cash > 400 else 0.4)
    w["massage"] = (8 + (14 if energy < 45 or health < 60 else 0)) * \
        (1.4 if cash > 900 else 0.3)
    w["checkup"] = (20 if weak else 4) * (1.5 if workday else 0.6)
    w["bake"] = (14 if "烘焙" in s["hobbies"] else 6) * (1.5 if weekend else 0.8)
    w["listen"] = 9 + (14 if low_mood else 0)
    w["journal"] = 8 + (12 if sad else 0)
    w["laundry"] = 8 + (8 if weekend else 0)
    w["ship"] = 5
    w["exhibit"] = (14 if "画画" in s["hobbies"] else 6) * (1.6 if weekend else 0.4)
    w["window_shop"] = (12 if s["consume_style"] in ("潮流跟风", "奢靡主义") else 6) \
        * (1.4 if 11 <= hour <= 20 else 0.3)
    w["boardgame"] = (16 if "桌游" in s["hobbies"] else 5) \
        * (1.6 if weekend else 0.5) * (1.4 if low_mood else 0.9)
    w["watch_game"] = 8 * (1.6 if weekend else 0.6)
    w["volunteer"] = (10 if "社牛" == s["social_tendency"] else 5) \
        * (1.5 if sad else 0.8) * (1.4 if weekend else 0.5)
    w["blind_date"] = (14 if s["social_tendency"] in ("社牛", "外向", "选择性社交")
                       else 3) * (1.5 if weekend else 0.6) * (1.4 if s["charm"] > 55 else 0.5)
    w["haircut"] = 6 + (16 if s["charm"] < 48 else 0)
    w["buy_clothes"] = (16 if s["consume_style"] in ("潮流跟风", "奢靡主义", "科技尝鲜")
                        else 7) * (1.8 if cash > 2500 else 0.2)

    # side income: always an option, but the pay gap is what sells it
    w["delivery"] = 10 + (34 if cash < 600 else 0)
    w["flyer"] = 8 + (22 if cash < 400 else 0)
    w["convenience"] = 12 + (24 if cash < 700 else 0)
    w["tutor"] = 18 + (22 if cash < 900 else 0)
    w["freelance"] = 14 + (30 if cash < 1200 else 0) \
        * (1.0 if hour >= 18 or weekend else 0.3)
    w["live_stream"] = (10 + s["charm"] * 0.16) * (1.4 if hour >= 19 else 0.4)
    w["stall"] = 10 + (18 if weekend else 0)
    w["save_money"] = (22 if cash > 1200 else 4) * (1.8 if net < goal else 0.6)
    w["invest"] = (18 if int(s.get("savings", 0)) > 800 else 2) \
        * (1.6 if "炒股" in s["hobbies"] else 0.7)

    # ---- the relationship network is something you have to tend ----
    rel = people.panel(s)
    warm = rel[0]["relation"]["score"] if rel else 0
    inner = [p for p in rel if p.get("social") in ("内向", "选择性社交", "独来独往")]
    clique = [p for p in rel if p["relation"]["score"] >= 55]
    w["visit_friend"] = (6 + len(clique) * 4) \
        * (1.5 if (weekend or hour >= 18) else 0.5) \
        * (1.5 if low_mood else 1.0)
    w["call_friend"] = (10 if low_mood else 5) + (8 if warm >= 40 else 0)
    w["gift"] = (6 if cash > 700 else 0) * (1.3 if weekend else 1.0)
    if inner and r.random() < 0.5:
        w["visit_friend"] = w.get("visit_friend", 0) * 1.2

    # ---- money guard rails ------------------------------------------
    if poor:
        # when the wallet is thin, only cheap fun survives -- and earning wins
        for k in PRICEY:
            if k in w:
                w[k] *= 0.12 if not broke else 0.0
        for k in EARNERS:
            w[k] = w.get(k, 0) * (2.2 if not broke else 3.4)
        w["cook"] = w.get("cook", 10) * 1.6
        w["grocery"] = w.get("grocery", 10) * 1.5
        w["stroll"] = w.get("stroll", 8) * 1.4
        w["listen"] = w.get("listen", 10) * 1.3

    return _guard(world, w, s, now, poor, broke, weak, sick,
                  low_mood, sad, cash, net, goal)


def _guard(world, w, s, now, poor, broke, weak, sick, low_mood, sad,
           cash, net, goal):
    """Apply the self-preservation layer, then personality, then the clock.

    Keeping it in one place means the night branch and the day branch obey the
    same rules -- a tired, broke, unhappy person behaves like one at 3am and at
    3pm alike.
    """
    r = world.rng
    happy, health = s["happiness"], s["health"]

    # ---- health: back off the body, invest in it ----
    if weak:
        for k in STRENUOUS:
            if k in w:
                w[k] *= 0.25
        for k in ("gym", "yoga", "jog", "cook", "sleep", "nap", "checkup",
                  "swim", "bath", "massage"):
            if k in w:
                w[k] *= 1.9
        w["checkup"] = w.get("checkup", 6) * 1.6
    if sick or health < 40:
        w["sick"] = max(w.get("sick", 0), 120)

    # ---- mood: a bad day needs fixing, and fun is cheap ----
    if low_mood:
        for k in CHEER:
            if k in w:
                w[k] *= 1.75
        for k in ("overtime", "delivery", "flyer", "convenience", "freelance"):
            if k in w:
                w[k] *= 0.55
    if sad:
        for k in ("entertain", "social", "listen", "boardgame", "volunteer",
                  "call_friend", "visit_friend", "pet", "walk_pet", "journal"):
            if k in w:
                w[k] *= 1.5
        w["idle"] = w.get("idle", 8) * 1.2

    # ---- money: build a cushion, but do not starve the fun budget ----
    if net < goal:
        w["save_money"] = w.get("save_money", 4) * 1.5
    if cash > 6000 and int(s.get("savings", 0)) < 1500:
        w["save_money"] = w.get("save_money", 4) * 1.8

    # ---- personality shaping ----
    if s["mbti"].startswith("I"):
        w["social"] = w.get("social", 10) * 0.7
        w["study"] = w.get("study", 10) * 1.3
        w["listen"] = w.get("listen", 8) * 1.2
    if s["mbti"].startswith("E"):
        w["social"] = w.get("social", 10) * 1.4
        w["party"] = w.get("party", 5) * 1.3
    if s["life_pace"] == "佛系":
        for k in ("work", "overtime", "gym", "delivery", "freelance"):
            w[k] = w.get(k, 0) * 0.6
        w["idle"] = w.get("idle", 8) * 2.2
    if s["life_pace"] == "工作狂":
        w["work"] = w.get("work", 0) * 1.25
        w["overtime"] = w.get("overtime", 0) * 1.4
    if s["life_pace"] == "早鸟型" and now.hour < 9:
        w["wake"] = 40

    weekend = now.weekday() >= 5
    if weekend:
        w["work"] = 0
        w["overtime"] = 0
        for k in ("entertain", "travel", "social", "gym", "hike", "cycle",
                  "boardgame", "exhibit", "volunteer", "stall"):
            w[k] = w.get(k, 0) * 1.5

    # keep only viable positive weights -- and never offer something the clock
    # forbids, so the LLM cannot talk us into working at midnight
    out = {}
    for k, v in w.items():
        if v <= 0 or k not in ACTIONS:
            continue
        if not world.action_allowed(k, now):
            continue
        if k in PARTTIME and not world.can_parttime(k):
            continue
        if k not in NEVER_BLOCK and k in PRICEY and \
                cash < ACTIONS[k]["drives"].get("wealth", 0) * -0.4:
            continue
        out[k] = v * repeat_factor(world, k)     # novelty pressure
    return out or {"idle": 1.0}


def _weighted_pick(world, scores):
    r = world.rng
    items = sorted(scores.items(), key=lambda kv: -kv[1])[:6]
    total = sum(v for _, v in items)
    x = r.random() * total
    for k, v in items:
        x -= v
        if x <= 0:
            return k
    return items[0][0]


# ─── novelty: doing the same thing all day is not a personality ──────
# The first version of the LLM tier would happily answer "coffee" for hours on
# end: the model sees "正在做=喝咖啡，还剩2分钟" and decides to keep going. A
# real person does not. Repetition now costs weight, and a repeat inside the
# freshness window is refused outright.
REPEAT_EXEMPT = ("sleep", "wake", "sick", "cook", "eat_out", "takeout",
                 "nap", "commute", "work", "overtime")
FRESH_MIN = 45 * 60.0            # "just did that" window, seconds

# Same-flavoured actions, so a person does not spend an afternoon doing three
# variations of the same thing (nap -> nap -> listen -> bath).
FAMILIES = {
    "nap": "rest", "sleep": "rest", "yoga": "rest", "massage": "rest",
    "listen": "chill", "read": "chill", "movie": "chill", "entertain": "chill",
    "gaming": "chill", "karaoke": "chill", "stargaze": "chill", "bath": "chill",
    "journal": "chill", "sing": "chill", "paint": "chill",
    "social": "social", "party": "social", "visit_friend": "social",
    "call_friend": "social", "boardgame": "social", "date": "social",
    "blind_date": "social", "volunteer": "social", "drink": "social",
    "coffee": "cafe", "bake": "cafe", "takeout": "cafe", "eat_out": "food",
    "cook": "food", "grocery": "food", "shop": "shop", "buy_clothes": "shop",
    "window_shop": "shop",
}


def family_of(key):
    return FAMILIES.get(key)


def recent_actions(world, limit=14):
    """[(action, ts)] newest last, straight from the decision journal."""
    out = []
    for d in (world.state.get("decisions") or [])[-limit:]:
        if d.get("action"):
            out.append((d["action"], float(d.get("ts") or 0)))
    return out


def repeat_factor(world, key, now_ts=None):
    """<1 when the action was just done, so the day stops looping."""
    t = now_ts or time.time()
    f = 1.0
    if key not in REPEAT_EXEMPT and key == world.state.get("action"):
        f *= 0.20
    hits = 0
    for act, ts in recent_actions(world):
        if act != key:
            continue
        hits += 1
        age = max(0.0, t - ts)
        if key in REPEAT_EXEMPT:
            continue                 # the body may insist; only mildly hedged
        if age < FRESH_MIN:
            f *= 0.25
        elif age < 2 * 3600:
            f *= 0.50
        elif age < 4 * 3600:
            f *= 0.75
    if hits >= 2 and key not in REPEAT_EXEMPT:
        f *= 0.60
    # same flavour twice in a row reads as a rut; a third needs a real reason
    fam = family_of(key)
    if fam:
        fam_hits = len([1 for act, ts in recent_actions(world)
                        if act != key and family_of(act) == fam
                        and (t - ts) < 5400])
        if fam_hits:
            f *= max(0.40, 0.70 ** fam_hits)
    return max(0.03, f)


def too_soon(world, key, now_ts=None):
    """True if choosing this again would look obsessive."""
    if key in REPEAT_EXEMPT:
        return False
    t = now_ts or time.time()
    if key == world.state.get("action"):
        return True
    for act, ts in recent_actions(world):
        if act == key and t - ts < FRESH_MIN:
            return True
    return False


def candidates(world, now, top=9, extra=3):
    """The shortlist handed to the LLM: a slate of equally viable ideas.

    A 2B model cannot weigh 72 options; it can weigh a dozen. Two details make
    the difference between "tastes" and "always takes the first line":

      * the head is drawn by WEIGHTED SAMPLING from the strongest fourteen
        scored actions, so the slate is not always the same deterministic
        ranking the rule engine would have produced anyway;
      * the slate is shuffled afterwards, because otherwise a small model just
        answers with candidate #1 forever (that is how one probe produced six
        identical "listen" decisions in a row).

    Everything on the slate is legal right now and something the person
    plausibly wants, so any pick is sane; the model's job is choosing the one
    that fits the personality and the story.
    """
    sc = _scores(world, now)
    ranked = [(k, v) for k, v in sorted(sc.items(), key=lambda kv: -kv[1])
              if not too_soon(world, k)]
    if not ranked:
        return ["idle"]
    pool = list(ranked[:14])
    picks = []
    while pool and len(picks) < top:
        total = sum(v for _, v in pool)
        x = world.rng.random() * total
        chosen = len(pool) - 1
        for i, (_k, v) in enumerate(pool):
            x -= v
            if x <= 0:
                chosen = i
                break
        picks.append(pool.pop(chosen)[0])
    tail_pool = [k for k, _ in ranked[14:]]
    tail = world.rng.sample(tail_pool, min(extra, len(tail_pool))) if tail_pool else []
    slate = picks + [k for k in tail if k not in picks]
    world.rng.shuffle(slate)          # position must carry no signal
    return slate


def reconsider(world, now):
    """A reason to abandon the current plan early, or None.

    Booked actions used to be prisons: "coffee" at 08:53 meant coffee until
    11:53. Life does not work that way -- hunger, exhaustion, a collapsing mood
    or a suddenly more attractive idea all end a plan early.

    Two tiers again: hard body needs always win, while a mere *want* has to
    beat the current plan by a wide margin and passes a coin flip, so the
    character looks spontaneous instead of fickle. Work shifts are only ever
    interrupted by the body, never by mood.
    """
    s = world.state
    r = world.rng
    cur = s.get("action")
    if cur in ("sleep", "wake", "sick"):
        return None
    label = ACTIONS.get(cur, {}).get("label", cur)
    # emergencies win, but they still pass a die roll so the character reads as
    # considerate rather than twitchy
    if s["hunger"] < 26 and cur not in ("cook", "eat_out", "takeout", "grocery") \
            and r.random() < 0.5:
        return "饿了，%s先放一放" % label
    if s["energy"] < 15 and cur != "nap" and r.random() < 0.45:
        return "困得不行了，先歇会儿"
    if s["health"] < HEALTH_SICK and cur not in ("checkup", "gym", "yoga",
                                                 "jog", "bath", "cook", "sick") \
            and r.random() < 0.6:
        return "身体在抗议，先顾身体"
    if s["happiness"] < MOOD_SAD and cur in STRENUOUS and r.random() < 0.5:
        return "心情太差，这活干不下去了"
    if cur in ("work", "overtime", "class", "commute"):
        return None                    # a shift is not abandoned on a whim
    sc = _scores(world, now)
    if not sc:
        return None
    best_k, best_v = max(sc.items(), key=lambda kv: kv[1])
    cur_v = sc.get(cur, 0.0)
    if best_k == cur or best_v < 35 or best_v <= max(18.0, cur_v * 1.9):
        return None
    if too_soon(world, best_k):
        return None
    # give the current plan a fair go: no flitting away after two minutes
    total = float(s.get("action_total") or 0)
    elapsed = max(0.0, total - float(s.get("action_left") or 0))
    if elapsed < min(600.0, total * 0.3):
        return None
    # and do not keep swinging back to the same idea either
    try:
        stamp = float(now.timestamp())
    except Exception:                                   # noqa: BLE001
        stamp = time.time()
    for key, ts in (s.get("cut_targets") or [])[-6:]:
        if key == best_k and stamp - float(ts or 0) < 5400:
            return None
    if r.random() >= 0.15:
        return None
    s["cut_targets"] = ((s.get("cut_targets") or [])[-9:] +
                        [(best_k, stamp)])
    return "突然更想%s" % ACTIONS[best_k]["label"]


def _fit(world, key):
    """Why this option suits THIS person -- a hint the small model can use."""
    s = world.state
    a = ACTIONS.get(key) or {}
    label = a.get("label") or key
    tags = []
    for h in (s.get("hobbies") or []):
        if h and (h in label or label in h):
            tags.append("爱好")
            break
    if key in EARNERS:
        tags.append("赚钱")
    if key in CHEER:
        tags.append("解压")
    if key in STRENUOUS:
        tags.append("费体力")
    if a.get("drives", {}).get("wealth", 0) <= -90:
        tags.append("花钱")
    if key in ("visit_friend", "call_friend", "gift"):
        tags.append("社交")
    if s.get("social_tendency") in ("内向", "独来独往") and key in ("social", "party"):
        tags.append("不太像你")
    return "/".join(tags[:2])


REASONS = {
    "sleep": "精力见底，该睡了", "wake": "睡饱了，新一天开始",
    "work": "工作日白天，去上班", "overtime": "想多赚点，留下来加班",
    "stock": "开盘了，看看持仓", "study": "想提升一下自己",
    "cook": "肚子饿了，自己做", "eat_out": "懒得做饭，出去吃",
    "entertain": "心情需要放松", "gym": "该练练了",
    "bath": "想清爽一下", "decorate": "手痒想改改家的样子",
    "shop": "看中了点东西", "travel": "想出去走走",
    "social": "想找人聊聊天", "idle": "暂时什么都不想干",
    "sing": "手痒想弹两首", "paint": "想画点东西", "party": "热闹一下也不错",
    "trick": "今天想点刺激的", "sick": "身体在抗议，得看医生",
    "walk_pet": "该带宠物出门转转了", "stroll": "天气不错，出去走走",
    "coffee": "困了，来杯咖啡", "date": "想见见那个人",
    "read": "想安静看会儿书", "class": "报了课，去上",
    "commute": "赶着去上班", "movie": "想看场电影",
    "stargaze": "想吹风看夜景", "grocery": "冰箱空了，去补货",
    "gaming": "手痒想打两局", "drink": "想喝一杯放松",
    "swim": "想去水里泡一泡", "garden": "该给花浇浇水了",
    "bank": "去银行办手续", "nap": "午后有点困",
    "takeout": "懒得动，点外卖", "clean": "家里该收拾了",
    "photo": "想拍几张照片", "fish": "去海边钓会儿鱼",
    "karaoke": "想吼两嗓子",
    # v5
    "jog": "想跑一跑出出汗", "yoga": "想安静地舒展一下",
    "cycle": "想骑车兜一圈", "hike": "想走远一点",
    "massage": "肩颈太紧了", "checkup": "该给身体做次检查",
    "bake": "想烤点什么", "listen": "想听一会儿歌",
    "journal": "有情绪想写下来", "laundry": "衣服堆成山了",
    "ship": "有个包裹要寄", "exhibit": "想去看个展",
    "window_shop": "想逛逛，不一定买", "boardgame": "想和人玩一局",
    "watch_game": "想看场球", "volunteer": "想做点有用的事",
    "blind_date": "被安排去见个人", "haircut": "头发该剪了",
    "buy_clothes": "想给自己换身新行头",
    "delivery": "缺钱，去跑几单", "flyer": "先挣点现钱",
    "convenience": "便利店缺人手", "tutor": "接了两节课",
    "freelance": "晚上的活最赚钱", "live_stream": "想开播聊聊天",
    "stall": "想把摊子支起来",
    "save_money": "该给自己攒点底气", "invest": "想让存款动起来",
    "gift": "想给朋友挑个礼物", "visit_friend": "想去朋友家坐坐",
    "call_friend": "有点想老朋友了",
}


def rule_choice(world, now):
    sc = _scores(world, now)
    if not sc:
        return "idle", "没有别的选择", None
    # the same novelty rule the LLM path obeys: if something was just done it
    # is off the table entirely, unless it is all that is left
    fresh = dict((k, v) for k, v in sc.items() if not too_soon(world, k))
    pool = fresh or sc
    key = _weighted_pick(world, pool)
    top = sorted(sc.items(), key=lambda kv: -kv[1])[:3]
    why = "%s（候选：%s）" % (REASONS.get(key, ""),
                              ", ".join("%s=%.0f" % (k, v) for k, v in top))
    return key, why, None


# ─── tier 2: LLM ────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "你是像素小人的内心。你就是这个人本人，不是旁白。\n"
    "你会收到：现在几点、周几、身体状态、钱包与存款、目标和职业、人际关系、"
    "性格、正在做什么、今天做过什么，以及此刻真正能做的候选行动"
    "（候选已按真实营业时间与能力过滤，比如深夜不会给你“上班”这个选项；"
    "候选顺序没有含义，都是此刻可行的，每条附了“契合”标签说明是否贴合你的爱好与性格）。\n"
    "请你像一个真实的普通人那样权衡“该做的”和“想做的”，选一个。判断要点：\n"
    "1. 时间要合乎常理——深夜回家睡觉或夜生活，白天才上班办事；\n"
    "2. 身体先于享乐——很饿就去吃，很累就去睡，生病去看医生，"
    "健康低时别选熬夜加班的活；\n"
    "3. 钱要留住——存款少时优先赚钱和省钱的选项，别把钱包花空；"
    "有余钱时可以考虑存钱、理财、买件像样的东西；\n"
    "4. 心情要养——心情差时优先能让自己开心的事，或找朋友聊聊，"
    "不要一直苦干；\n"
    "5. 朋友要维系——关系是要花时间的，想起来就去见见、打个电话、送个礼物；\n"
    "6. 保持人设——内向的别天天社交，佛系的别拼命加班，"
    "每个决定都该像“这个人”会做的；\n"
    "7. 一天要有变化——刚做过的事不会出现在候选里，别去重复，"
    "也别把同一件事连着做两遍；优先挑“契合”贴合你的爱好与性格的那一个；\n"
    "8. 时长要合理——minutes 参考候选里的“分钟”区间，"
    "喝咖啡是二十分钟的事，不是三小时；\n"
    "只输出一行 JSON，不要解释，不要 markdown，禁止复述输入：\n"
    '{"action":"英文键名","reason":"不超过12字的原因","caption":"此刻一句内心独白，'
    '中文不超过14字，口语化","minutes":预计分钟数}\n'
    "例：深夜很累时 → {\"action\":\"sleep\",\"reason\":\"夜深了精力见底\","
    "\"caption\":\"眼皮已经开始打架\",\"minutes\":420}\n"
    "例：心情低又没钱时 → {\"action\":\"listen\",\"reason\":\"想一个人静静\","
    "\"caption\":\"算了，听会儿歌吧\",\"minutes\":40}\n"
    "action 必须原样写候选里的英文 key（如 sleep、cook、stargaze），不要写中文，"
    "minutes 是整数；拿不准就填 0。"
)

# Small models love answering with the Chinese label instead of the key.
_LABEL_TO_KEY = dict((a["label"], k) for k, a in ACTIONS.items())


def resolve_action(raw):
    """key -> key; Chinese label -> key; anything else -> None."""
    if raw in ACTIONS:
        return raw
    r = str(raw or "").strip()
    if r in _LABEL_TO_KEY:
        return _LABEL_TO_KEY[r]
    for label, key in _LABEL_TO_KEY.items():
        if label and label in r:
            return key
    return None


def _mood_word(v, hi, mid, low):
    if v >= hi:
        return "很好"
    if v >= mid:
        return "还行"
    if v >= low:
        return "有点差"
    return "很差"


def _world_brief(n=5):
    """新闻 + 天气 —— 给模型一个"外面在发生什么"的参照。"""
    try:
        from . import feeds
        return feeds.get_feeds().brief(n)
    except Exception:                                       # noqa: BLE001
        return None


def _world_log(n=5):
    """世界日志的最近 n 天（不含今天）—— 决策看的是"这几天外面什么样"。

    feeds.brief 里那一眼是"此刻外面"，这里补的是"前几天外面"：小人的判断
    于是能带上一点连续性（连着下了三天雨、这几天全在聊同一件事）。
    """
    try:
        from . import feeds
        return feeds.get_feeds().log_brief(n)
    except Exception:                                       # noqa: BLE001
        return []


def _master_line(s):
    """主人最近的一句 + 想让他做的事（唯一从屏幕外进来的指令）。"""
    try:
        from . import herochat
        line = herochat.last_user_line(s)
        wants = herochat.hero_wants(s)
        if line or wants:
            return dict(刚说=line, 期待=wants)
    except Exception:                                       # noqa: BLE001
        pass
    return None


class LLMBrain(object):
    """Async advisor on the shared pool. Never blocks; falls back silently."""

    MIN_GAP = 45.0          # seconds between two decisions requests
    READY_TTL = 240.0       # an answer older than this is thrown away

    def __init__(self):
        self._job = None
        self._result = None          # (action, reason, caption, minutes)
        self._result_ts = 0.0
        self._last_fire = 0.0
        self.last_error = None
        self.last_text = None

    # -- context -----------------------------------------------------
    def digest(self, world, now, slate):
        s = world.state
        cur = s.get("action")
        left = int(max(0, s.get("action_left", 0)) // 60)
        today = [d.get("text") or d.get("action")
                 for d in s.get("decisions", [])[-5:]]
        rel = people.panel(s)[:5]
        warm = [dict(名字=r["cn"], 关系=r["relation"]["rank"],
                     好感=round(r["relation"]["score"]),
                     对方心情=r.get("mood"),
                     爱好=r.get("hobbies", [])[:2],
                     见面=r["relation"]["met"]) for r in rel]
        led = s.get("last_money") or {}
        return dict(
            时间="%s %s" % (["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                            world.time_label(now)),
            时段=world.daypart(now),
            开盘=world.market_open(now),
            状态=dict(
                精力="%d(%s)" % (round(s["energy"]), _mood_word(s["energy"], 70, 45, 25)),
                饥饿="%d(%s)" % (round(s["hunger"]), _mood_word(s["hunger"], 70, 45, 25)),
                心情="%d(%s)" % (round(s["happiness"]), _mood_word(s["happiness"], 70, 45, 25)),
                健康="%d(%s)" % (round(s["health"]), _mood_word(s["health"], 75, 50, 30)),
                魅力=round(s["charm"]), 身体=world._body_line(),
            ),
            钱=dict(现金=round(s["wealth"]),
                    存款=int(s.get("savings", 0)),
                    净资产=world.net_worth(),
                    目标=(s.get("goal") or {}).get("save", 5000),
                    最近=("%s %+d" % (led.get("reason"), int(led.get("delta", 0)))
                         if led else None)),
            职业=dict(岗位=(s.get("career") or {}).get("title", s.get("job")),
                      时薪=round(world.wage()),
                      技能=round(float((s.get("career") or {}).get("skill", 0))),
                      可做兼职=[PARTTIME[k]["label"] for k in PARTTIME
                                if world.can_parttime(k)]),
            性格=dict(MBTI=s["mbti"], 生活节奏=s["life_pace"], 社交=s["social_tendency"],
                      炒股=s["stock_style"], 消费=s["consume_style"],
                      爱好=s["hobbies"], 口头禅=s.get("catch"), 简介=s.get("intro")),
            人际关系=warm or "还没有熟人",
            宠物=("%s(%s)" % (s.get("pet_name"), s.get("pet"))) if s.get("pet") else "无",
            衣柜=s.get("wardrobe", [])[-4:],
            正在做="%s，还剩%d分钟" % (ACTIONS.get(cur, {}).get("label", cur), left),
            最近做过=today,
            刚做过=[ACTIONS[k]["label"] for k, _ts in recent_actions(world)[-4:]
                    if k in ACTIONS],
            外面=_world_brief(5),
            世界日志=_world_log(5),
            主人的话=_master_line(s),
            备注="候选顺序没有含义，它们此刻都能做；挑一个最像你会做的",
            候选=[dict(key=k, 名称=ACTIONS[k]["label"],
                       说明=ACTIONS[k]["caption"],
                       契合=_fit(world, k),
                       分钟="%d-%d" % (ACTIONS[k]["dur"][0] // 60,
                                       ACTIONS[k]["dur"][1] // 60),
                       耗钱=ACTIONS[k]["drives"].get("wealth", 0))
                  for k in slate],
        )

    # -- fire / collect ----------------------------------------------
    def request(self, world, now, slate):
        from . import llm
        cfg = llm.get_config()
        if not cfg.get("enabled") or not cfg.get("decide"):
            return None
        if not slate:
            return None
        if time.time() - self._last_fire < self.MIN_GAP:
            return self._job
        pool = llm.get_pool()
        job = pool.submit(
            "decide",
            [dict(role="system", content=SYSTEM_PROMPT),
             dict(role="user", content=json.dumps(
                 self.digest(world, now, slate), ensure_ascii=False))],
            temperature=cfg.get("temperature"),
        )
        if job is not None:
            self._job = job
            self._last_fire = time.time()
        return self._job

    def poll(self):
        """Move a finished job's answer into the cache. Cheap, call per tick."""
        job = self._job
        if job is None or not job.done:
            return
        self._job = None
        if job.error:
            self.last_error = job.error
            return
        from . import llm
        obj = llm.json_from(job.result)
        self.last_text = (job.result or "")[:200]
        if not obj:
            self.last_error = "unparsable reply"
            return
        act = resolve_action(obj.get("action"))
        if act is None:
            self.last_error = "unknown action %r" % obj.get("action")
            return
        try:
            mins = int(float(obj.get("minutes") or 0))
        except Exception:                                   # noqa: BLE001
            mins = 0
        self._result = (act,
                        str(obj.get("reason") or "")[:24],
                        str(obj.get("caption") or "")[:20],
                        max(0, min(720, mins)))
        self._result_ts = time.time()

    def take(self, allowed):
        """Consume a fresh answer, but only if it is still a legal choice."""
        if not self._result:
            return None
        if time.time() - self._result_ts > self.READY_TTL:
            self._result = None
            return None
        act, reason, caption, mins = self._result
        if allowed is not None and act not in allowed:
            # the clock moved on while the model was thinking -- drop it
            self.last_error = "%s 不在当前时间可做的范围" % act
            self._result = None
            return None
        self._result = None
        return act, reason, caption, mins


_BRAIN = None


def get_brain():
    global _BRAIN
    if _BRAIN is None:
        _BRAIN = LLMBrain()
    return _BRAIN


def choose_action(world, now):
    """Synchronous decision: prefer a fresh LLM answer, else the rule engine."""
    from . import llm
    sc = _scores(world, now)
    brain = get_brain()
    brain.poll()
    cfg = llm.get_config()
    if cfg.get("enabled") and cfg.get("decide"):
        got = brain.take(set(sc))
        if got:
            act, reason, caption, mins = got
            if too_soon(world, act):
                # the model defaulted to "more of the same" -- exactly how the
                # hero ended up drinking coffee from 08:23 until lunch
                brain.last_error = "AI 想再做%s，刚做过，改由规则决定" % act
                world.log("brain", "AI 想继续%s，但刚做过，换个别的"
                          % ACTIONS[act]["label"])
            else:
                if caption:
                    world.state["llm_caption"] = caption
                    world.state["llm_caption_ts"] = time.time()
                return act, "AI：%s" % (reason or "自己拿主意"), (mins * 60) or None
    key, why, _ = rule_choice(world, now)
    return key, why, None


def prefetch(world, now):
    """Ask early, so the answer is usually ready when the action runs out."""
    from . import llm
    cfg = llm.get_config()
    if not cfg.get("enabled") or not cfg.get("decide"):
        return
    brain = get_brain()
    brain.poll()
    if brain._job is not None or brain._result:             # noqa: SLF001
        return
    brain.request(world, now, candidates(world, now))


# ─── tier 3: the inner voice ────────────────────────────────────────
# The decision tier runs occasionally; a person thinks constantly. This is a
# small, cheap "what is on my mind right now" call on the same pool. When it is
# slow or unavailable the world falls back to its generated thoughts, so the
# marquee always has something human to say.
THOUGHT_SYSTEM = (
    "你是像素小人的内心。第一人称，一句心里冒出来的念头，"
    "像自言自语，不要旁白、不要解释、不要标点堆砌、不要复述输入。\n"
    "只输出一行 JSON：{\"thought\":\"...\"}，中文不超过14字。\n"
    "例：{\"thought\":\"这咖啡有点苦\"}\n"
    "例：{\"thought\":\"钱花得有点快啊\"}"
)


class LLMThoughts(object):
    GAP = 180.0          # seconds between two genuine LLM thoughts

    def __init__(self):
        self._job = None
        self._last = 0.0

    def _context(self, world, now):
        s = world.state
        a = ACTIONS.get(s.get("action"), {})
        left = int(max(0, s.get("action_left", 0)) // 60)
        warm = people.warmest(s, 1)
        led = s.get("last_money") or {}
        return dict(
            时间="%s %s" % (["周一", "周二", "周三", "周四", "周五", "周六",
                             "周日"][now.weekday()], world.time_label(now)),
            我正在="%s，还剩%d分钟" % (a.get("label", s.get("action")), left),
            身体=world._body_line(),
            钱="现金%d 存款%d 目标%d" % (round(s.get("wealth", 0)),
                                        int(s.get("savings", 0)),
                                        (s.get("goal") or {}).get("save", 5000)),
            心情="%d" % round(s.get("happiness", 60)),
            性格="%s·%s" % (s.get("mbti"), s.get("life_pace")),
            想的人=(warm[0].get("cn") if warm else None),
            最近金钱=(led.get("reason") if led else None),
            最近做过=[ACTIONS[d["action"]]["label"]
                      for d in (s.get("decisions") or [])[-3:]
                      if d.get("action") in ACTIONS],
            外面=_world_brief(3),
            世界日志=_world_log(3),
        )

    def request(self, world, now):
        from . import llm
        cfg = llm.get_config()
        if not cfg.get("enabled"):
            return
        job = self._job
        if job is not None and not job.done:
            return
        if time.time() - self._last < self.GAP:
            return
        self._job = llm.get_pool().submit(
            "think",
            [dict(role="system", content=THOUGHT_SYSTEM),
             dict(role="user", content=json.dumps(self._context(world, now),
                                                  ensure_ascii=False))],
            temperature=min(1.1, float(cfg.get("temperature") or 0.85) + 0.15),
        )
        if self._job is not None:
            self._last = time.time()

    def take(self, world):
        from . import llm
        job = self._job
        if job is None or not job.done:
            return None
        self._job = None
        if job.error:
            return None
        obj = llm.json_from(job.result)
        txt = None
        if isinstance(obj, dict):
            txt = obj.get("thought") or obj.get("text") or obj.get("caption")
        if not txt:
            txt = llm.clean_line(job.result or "", 14)
        txt = " ".join(str(txt or "").split())[:16]
        return txt or None


_THOUGHTS = None


def get_thoughts():
    global _THOUGHTS
    if _THOUGHTS is None:
        _THOUGHTS = LLMThoughts()
    return _THOUGHTS


def request_thought(world, now):
    try:
        get_thoughts().request(world, now)
    except Exception:                                   # noqa: BLE001
        pass


def take_thought(world):
    try:
        return get_thoughts().take(world)
    except Exception:                                   # noqa: BLE001
        return None
