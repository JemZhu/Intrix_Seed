#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""屏幕外的主人和屏幕里的主角说话。

这是整个小人世界唯一一条"从外面进来"的信息流：主人打一句话 → LLM 按主角的
性格、当下的状态、天气和新闻回话 → 回应顺手做三件事：

1. 改心情（夸他/关心他 +，凶他/催他 −）；
2. 记愿望（主人随口说的"去跑步""学做菜"会进愿望清单，给之后的版本更新当线索）；
3. 改行为（模型想换动作就记下 hero_wants，下一轮决策把这个念头带进 prompt，
   并把当前动作的剩余时间砍到 5 秒内，让世界尽快重新决定）。

回应本身还会写进底栏播报（llm_caption），所以主人发完话，屏幕上的小人真的
会"说"出那句回答。对话历史存 state（hero_chat），跟存档走。
"""
import json
import time
from datetime import datetime

from . import llm

MAX_KEEP = 60          # hero_chat 最多留几条（跟存档一起活）
CTX_TURNS = 10         # 每次带给模型最近几轮

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

SYSTEM = (
    "你是像素世界里的小人，此刻活在 LED 屏幕上。屏幕外的主人正在跟你说话，"
    "这是你能听见的唯一来自「外面」的声音。\n"
    "要求：\n"
    "1. 用你自己的性格说话：口语、短句，最多两句、30 个字以内；\n"
    "2. 主人的话会影响你的心情：夸你、关心你就开心，凶你、催你就委屈；\n"
    "3. 主人给了具体建议或愿望（「去跑步」「学做菜」「早点睡」），"
    "把它记进 note，并想想该对应哪个动作（act，用动作的英文 key，"
    "不知道就留空）；\n"
    "4. 结合你此刻的状态、时间、天气和最近新闻自然回应，像真的住在里面。\n"
    "只输出一行 JSON："
    '{"reply":"...","mood":-10到10的整数,"note":"想记住的事，没有就空","act":"动作key或空"}\n'
    '例：{"reply":"好呀，那我去公园跑两圈","mood":6,'
    '"note":"主人想让我多运动","act":"jog"}\n'
    '例：{"reply":"知道了知道了","mood":-2,"note":"","act":""}'
)


def log_of(state):
    return state.setdefault("hero_chat", [])


def last_user_line(state):
    for m in reversed(log_of(state)):
        if m.get("who") == "you":
            return m.get("text")
    return None


def hero_wants(state):
    return state.get("hero_wants") or None


def _context(world, now=None):
    from .world import ACTIONS
    from . import feeds
    now = now or datetime.now()
    s = world.state
    a = ACTIONS.get(s.get("action"), {})
    log = log_of(s)
    return dict(
        我=dict(名字=s.get("name"),
                性格=dict(MBTI=s.get("mbti"), 社交=s.get("social_tendency"),
                          节奏=s.get("life_pace"), 简介=s.get("intro")),
                口头禅=s.get("catch")),
        此刻=dict(时间="%s %s" % (WEEKDAY_CN[now.weekday()], world.time_label(now)),
                  正在=a.get("label") or s.get("action"),
                  身体=world._body_line(),
                  心情=round(s.get("happiness", 50)),
                  外面=feeds.get_feeds().brief(4)),
        聊天记录=[dict(谁="主人" if m.get("who") == "you" else "我",
                       说了=m.get("text")) for m in log[-CTX_TURNS:]],
    )


def send(world, text):
    """主人说一句 → 主角答一句。同步调用（面板的请求本来就在等）。"""
    s = world.state
    text = " ".join(str(text or "").split())[:120]
    if not text:
        return dict(error="消息为空")
    log = log_of(s)
    log.append(dict(who="you", text=text, ts=time.time()))
    del log[:-MAX_KEEP]

    pool = llm.get_pool()
    reply, err = pool.call_sync(
        [dict(role="system", content=SYSTEM),
         dict(role="user", content=json.dumps(_context(world),
                                              ensure_ascii=False))],
        timeout=40)
    if err:
        world.log("hero_chat", "主人说「%s」，但没答上来：%s" % (text, err))
        return dict(error=str(err), log=_view(s))
    obj = llm.json_from(reply) or {}
    out = str(obj.get("reply") or "").strip() or llm.clean_line(reply, 40)
    if not out:
        return dict(error="模型没有给出回应", log=_view(s))
    log.append(dict(who="hero", text=out, ts=time.time()))
    del log[:-MAX_KEEP]

    # 1) 心情
    try:
        mood = max(-10, min(10, int(obj.get("mood"))))
    except Exception:                                       # noqa: BLE001
        mood = 0
    if mood:
        s["happiness"] = max(0.0, min(100.0, float(s.get("happiness", 50)) + mood))

    # 2) 愿望
    note = " ".join(str(obj.get("note") or "").split())[:40]
    if note:
        try:
            from . import memory
            memory.add_wish(note, source="主人的话", kind="chat")
        except Exception:                                   # noqa: BLE001
            pass

    # 3) 行为
    act = str(obj.get("act") or "").strip()
    if act:
        try:
            from .brain import resolve_action
            key = resolve_action(act)
            if key and key != s.get("action"):
                s["hero_wants"] = key
                s["action_left"] = min(float(s.get("action_left") or 0), 5.0)
                world.log("hero_chat", "主人一句话，%s 打算改去%s"
                          % (s.get("name"), key))
        except Exception:                                   # noqa: BLE001
            pass

    # 底栏播报里说这句
    s["llm_caption"] = out
    s["llm_caption_ts"] = time.time()
    try:
        world.save()
    except Exception:                                       # noqa: BLE001
        pass
    return dict(reply=out, mood=mood, log=_view(s),
                name=s.get("name"))


def _view(s):
    """给面板的消息列表（旧→新）。"""
    return [{"who": m.get("who"), "text": m.get("text"), "ts": m.get("ts")}
            for m in log_of(s)[-MAX_KEEP:]]


def view(world):
    s = world.state
    return dict(log=_view(s), name=s.get("name"),
                action=(s.get("action")),
                hero_wants=hero_wants(s))
