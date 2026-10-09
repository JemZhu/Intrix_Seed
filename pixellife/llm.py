#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared OpenAI-compatible LLM client for every pixel person.

The backend is a single llama.cpp / vLLM style endpoint that multiplexes a
128k context over at most 4 parallel streams, so this module owns three things:

  * the *configuration* (endpoint, key, model, per-reply max tokens, total
    context, concurrency) -- persisted to llm_config.json so the web console
    can edit it at any time without a restart;
  * the *budget* -- every request is trimmed so that prompt + reply fits in
    ``ctx_tokens // concurrency``;
  * the *pool* -- a fixed number of worker threads. Callers never block: they
    submit a job and poll it later, so a slow or dead endpoint can never stall
    the 12 FPS render loop.

If anything at all goes wrong the job simply resolves to None and the caller
falls back to its deterministic behaviour. The panel must never go blank.
"""
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "llm_config.json")

DEFAULTS = dict(
    enabled=True,
    url="",                   # e.g. "http://127.0.0.1:8080/v1"
    api_key="",               # 填在这里，或写进 llm_config.json（该文件不入库）
    model="",                 # blank -> first id reported by /models
    max_tokens=256,           # cap on a single reply
    ctx_tokens=128000,        # total context the backend shares
    concurrency=4,            # parallel streams the backend allows
    timeout=25,               # seconds per request
    temperature=0.85,
    thinking=False,           # reasoning models: off is ~3x faster and enough
    decide=True,              # let the LLM pick the hero's next action
    chat=True,                # let NPCs talk through the LLM
)


# ─── config ─────────────────────────────────────────────────────────
class Config(object):
    """Thread-safe, file-backed settings."""

    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                with self._lock:
                    self.data.update({k: v for k, v in saved.items()
                                      if k in DEFAULTS})
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
        """Merge a partial dict of known keys; returns the saved config."""
        with self._lock:
            for k, v in (patch or {}).items():
                if k not in DEFAULTS:
                    continue
                if isinstance(DEFAULTS[k], bool):
                    self.data[k] = bool(v)
                elif isinstance(DEFAULTS[k], int):
                    try:
                        self.data[k] = int(v)
                    except Exception:                       # noqa: BLE001
                        continue
                elif isinstance(DEFAULTS[k], float):
                    try:
                        self.data[k] = float(v)
                    except Exception:                       # noqa: BLE001
                        continue
                else:
                    self.data[k] = str(v).strip()
            # sanity: never let a bad number break the budget maths
            self.data["max_tokens"] = max(16, min(4096, int(self.data["max_tokens"])))
            self.data["ctx_tokens"] = max(1024, min(1 << 21, int(self.data["ctx_tokens"])))
            self.data["concurrency"] = max(1, min(8, int(self.data["concurrency"])))
            self.data["timeout"] = max(3, min(120, int(self.data["timeout"])))
            self.data["temperature"] = max(0.0, min(2.0, float(self.data["temperature"])))
        return self.save()


CONFIG = Config()


def get_config():
    return CONFIG


# ─── token 账本 ─────────────────────────────────────────────────────
USAGE_PATH = os.path.join(HERE, "llm_usage.json")


class Usage(object):
    """累计 token 消耗（总量 + 次数），落盘持久化，重启不清零。

    每次成功拿到回复后 ``add(prompt, completion)``；写盘做了节流，
    但 ``snapshot()`` 会先补一次落盘，所以面板读到的永远是最新值。
    """

    def __init__(self, path=USAGE_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.calls = 0
        self.tokens_total = 0
        self.tokens_prompt = 0
        self.tokens_completion = 0
        self.since = 0.0
        self.updated = 0.0
        self._dirty = 0
        self._last_flush = 0.0
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.calls = max(0, int(d.get("calls") or 0))
                self.tokens_total = max(0, int(d.get("tokens_total") or 0))
                self.tokens_prompt = max(0, int(d.get("tokens_prompt") or 0))
                self.tokens_completion = max(0, int(d.get("tokens_completion") or 0))
                self.since = float(d.get("since") or 0.0)
                self.updated = float(d.get("updated") or 0.0)
        except Exception:                                   # noqa: BLE001
            pass
        return self

    def _blob(self):
        return json.dumps(dict(calls=self.calls,
                               tokens_total=self.tokens_total,
                               tokens_prompt=self.tokens_prompt,
                               tokens_completion=self.tokens_completion,
                               since=self.since, updated=self.updated),
                          ensure_ascii=False, indent=1)

    def flush(self, force=False):
        with self._lock:
            if not self._dirty:
                return
            if not (force or time.time() - self._last_flush >= 3.0):
                return
            blob = self._blob()
            self._dirty = 0
            self._last_flush = time.time()
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(blob)
            os.replace(tmp, self.path)
        except Exception:                                   # noqa: BLE001
            pass

    def add(self, prompt_tokens=0, completion_tokens=0):
        now = time.time()
        p = max(0, int(prompt_tokens or 0))
        c = max(0, int(completion_tokens or 0))
        with self._lock:
            self.calls += 1
            self.tokens_prompt += p
            self.tokens_completion += c
            self.tokens_total += p + c
            self.updated = now
            if not self.since:
                self.since = now
            self._dirty += 1
            due = self._dirty >= 10 or (now - self._last_flush) >= 3.0
        if due:
            self.flush(force=True)

    def snapshot(self):
        if self._dirty:
            self.flush(force=True)
        with self._lock:
            return dict(calls=self.calls, tokens_total=self.tokens_total,
                        tokens_prompt=self.tokens_prompt,
                        tokens_completion=self.tokens_completion,
                        since=self.since, updated=self.updated)


USAGE = Usage()


def get_usage():
    return USAGE


# ─── token estimation ───────────────────────────────────────────────


# ─── token estimation ───────────────────────────────────────────────
def est_tokens(text):
    """Rough token count: CJK costs about a token a character, latin less."""
    if not text:
        return 0
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    return int(cjk * 1.05 + (len(text) - cjk) * 0.30) + 1


def prompt_budget():
    """How many tokens a single stream may spend on its prompt."""
    per = max(2048, int(CONFIG.get("ctx_tokens")) // max(1, int(CONFIG.get("concurrency"))))
    return max(512, per - int(CONFIG.get("max_tokens")) - 256)


def fit_messages(messages, budget=None):
    """Trim a chat list to the budget, always keeping system + last user."""
    budget = budget or prompt_budget()
    msgs = [m for m in messages if m.get("content")]
    if not msgs:
        return msgs
    total = sum(est_tokens(m["content"]) for m in msgs)
    if total <= budget:
        return msgs
    head = msgs[0] if msgs[0].get("role") == "system" else None
    tail = msgs[-1]
    middle = msgs[1:-1] if head is not None else msgs[:-1]
    # drop the oldest middle turns first
    while middle and total > budget:
        gone = middle.pop(0)
        total -= est_tokens(gone["content"])
    if total > budget:                       # still fat: clip the last user msg
        keep = max(200, int(len(tail["content"]) * budget / float(max(1, total))))
        tail = dict(tail, content=tail["content"][-keep:])
        total = sum(est_tokens(m["content"])
                    for m in ([head] if head else []) + middle + [tail])
    return ([head] if head else []) + middle + [tail]


# ─── jobs ───────────────────────────────────────────────────────────
class Job(object):
    __slots__ = ("tag", "payload", "done", "result", "error", "latency",
                 "submitted", "_ev")

    def __init__(self, tag, payload):
        self.tag = tag
        self.payload = payload
        self.done = False
        self.result = None
        self.error = None
        self.latency = 0.0
        self.submitted = time.time()
        self._ev = threading.Event()

    def wait(self, timeout=0.0):
        self._ev.wait(timeout)
        return self.result if self.done else None

    def finish(self, result, error=None, latency=0.0):
        self.result = result
        self.error = error
        self.latency = latency
        self.done = True
        self._ev.set()


class Pool(object):
    """Fixed-size worker pool. Submitting never blocks."""

    MAX_QUEUED = 12

    def __init__(self, config=CONFIG):
        self.cfg = config
        self.q = queue.Queue()
        self.workers = []
        self._n = 0
        self._lock = threading.Lock()
        self.stats = dict(calls=0, ok=0, fail=0, last_latency=0.0,
                          last_error=None, last_ok=0.0, inflight=0)
        self._model = None
        self._model_ts = 0.0
        self.reballance()

    # -- worker management -------------------------------------------
    def reballance(self):
        want = max(1, int(self.cfg.get("concurrency")))
        with self._lock:
            if want == self._n:
                return
            self._n = want
        for t in list(self.workers):
            t._stop = True                                  # noqa: SLF001
        self.q = queue.Queue()                              # drop stale jobs
        self.workers = []
        for i in range(want):
            t = threading.Thread(target=self._run, name="pixellife-llm-%d" % i,
                                 daemon=True)
            t._stop = False                                 # noqa: SLF001
            t.start()
            self.workers.append(t)

    def _run(self):
        me = threading.current_thread()
        while not getattr(me, "_stop", True):
            try:
                job = self.q.get(timeout=1.0)
            except Exception:                               # noqa: BLE001
                continue
            if job is None:
                continue
            try:
                self.stats["inflight"] += 1
                self._perform(job)
            finally:
                self.stats["inflight"] -= 1
                self.q.task_done()

    # -- the actual HTTP call ----------------------------------------
    def auto_model(self, base=None, cfg=None):
        """Pick the first model the endpoint advertises (cached 10 minutes)."""
        now = time.time()
        if self._model and now - self._model_ts < 600:
            return self._model
        cfg = cfg or self.cfg.get()
        base = base or (cfg.get("url") or "").rstrip("/")
        ids, err = self.models() if base else ([], "no endpoint")
        if ids:
            self._model = ids[0]
            self._model_ts = now
            return self._model
        if err:
            self.stats["last_error"] = err
        return "default"

    def _perform(self, job):
        cfg = self.cfg.get()
        base = (cfg.get("url") or "").rstrip("/")
        if not base:
            job.finish(None, "no endpoint configured")
            return
        url = base + "/chat/completions"
        payload = dict(job.payload)
        payload["model"] = cfg.get("model") or payload.get("model") or self.auto_model(base, cfg)
        payload.setdefault("temperature", cfg.get("temperature"))
        payload["max_tokens"] = int(cfg.get("max_tokens"))
        if not cfg.get("thinking"):
            # reasoning models (MiniCPM5 / Qwen3) otherwise spend the whole
            # budget on a monologue and return an empty answer
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            payload["messages"] = fit_messages(payload.get("messages", []))
        except Exception:                                   # noqa: BLE001
            pass
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if cfg.get("api_key"):
            headers["Authorization"] = "Bearer " + str(cfg["api_key"])
        req = urllib.request.Request(url, data=body, headers=headers,
                                     method="POST")
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=float(cfg.get("timeout"))) as r:
                raw = r.read().decode("utf-8", "replace")
            data = json.loads(raw)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            text = msg.get("content") or choice.get("text") or ""
            self.stats["calls"] += 1
            self.stats["ok"] += 1
            self.stats["last_latency"] = round(time.time() - t0, 2)
            self.stats["last_ok"] = time.time()
            self._record_usage(data, payload, text)
            job.finish(text.strip(), None, self.stats["last_latency"])
        except Exception as e:                              # noqa: BLE001
            self.stats["calls"] += 1
            self.stats["fail"] += 1
            self.stats["last_error"] = "%s: %s" % (type(e).__name__, e)
            job.finish(None, self.stats["last_error"])

    # -- usage bookkeeping -------------------------------------------
    def _record_usage(self, data, payload, text):
        """一次成功调用的 token 用量：优先用服务端 usage，否则本地估算。"""
        try:
            u = data.get("usage") if isinstance(data, dict) else None
            pt = ct = None
            if isinstance(u, dict):
                pt = u.get("prompt_tokens")
                ct = u.get("completion_tokens")
                if pt is None and ct is None and u.get("total_tokens") is not None:
                    pt = int(u.get("total_tokens") or 0)
                    ct = 0
            if pt is None:
                pt = est_tokens(" ".join(str((m or {}).get("content") or "")
                                         for m in (payload.get("messages") or [])))
            if ct is None:
                ct = est_tokens(text)
            USAGE.add(pt, ct)
        except Exception:                                   # noqa: BLE001
            pass

    # -- public API ---------------------------------------------------
    def submit(self, tag, messages, **kw):
        """Queue a chat job. Returns the Job, or None if the LLM is off/busy."""
        cfg = self.cfg.get()
        if not cfg.get("enabled"):
            return None
        if self.q.qsize() >= self.MAX_QUEUED:
            return None
        payload = dict(messages=messages)
        payload.update(kw)
        job = Job(tag, payload)
        try:
            self.q.put_nowait(job)
        except Exception:                                   # noqa: BLE001
            return None
        return job

    def call_sync(self, messages, timeout=None, **kw):
        """Blocking helper for the console's 'test' button."""
        cfg = self.cfg.get()
        if not cfg.get("enabled"):
            return None, "LLM 未启用"
        job = Job("sync", dict(messages=messages, **kw))
        self._perform(job)
        if not job.done:
            job.wait(timeout or 1)
        return job.result, job.error

    def models(self, timeout=8):
        """Probe /models -- used to populate the model dropdown."""
        cfg = self.cfg.get()
        base = (cfg.get("url") or "").rstrip("/")
        if not base:
            return [], "no endpoint configured"
        headers = {}
        if cfg.get("api_key"):
            headers["Authorization"] = "Bearer " + str(cfg["api_key"])
        try:
            req = urllib.request.Request(base + "/models", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            ids = []
            for m in (data.get("data") or []):
                mid = m.get("id") if isinstance(m, dict) else m
                if mid:
                    ids.append(mid)
            return ids, None
        except Exception as e:                              # noqa: BLE001
            return [], "%s: %s" % (type(e).__name__, e)

    def status(self):
        cfg = self.cfg.get()
        with self._lock:
            st = dict(self.stats)
        us = USAGE.snapshot()
        st.update(
            enabled=bool(cfg.get("enabled")),
            url=cfg.get("url"), model=cfg.get("model"),
            has_key=bool(cfg.get("api_key")),
            max_tokens=cfg.get("max_tokens"), ctx_tokens=cfg.get("ctx_tokens"),
            concurrency=cfg.get("concurrency"), timeout=cfg.get("timeout"),
            temperature=cfg.get("temperature"), thinking=cfg.get("thinking"),
            decide=cfg.get("decide"), chat=cfg.get("chat"),
            per_stream=int(cfg.get("ctx_tokens")) // max(1, int(cfg.get("concurrency"))),
            prompt_budget=prompt_budget(),
            queued=self.q.qsize(),
            model_hint=self._model,
            healthy=bool(st.get("last_ok")) and
                    (time.time() - st.get("last_ok", 0)) < 600,
            tokens_total=us["tokens_total"],
            token_calls=us["calls"],
            tokens_prompt=us["tokens_prompt"],
            tokens_completion=us["tokens_completion"],
            tokens_since=us["since"],
            tokens_updated=us["updated"],
        )
        return st


POOL = Pool()


def get_pool():
    return POOL


def reload():
    """Re-read the config file and resize the pool (console 'save' hook)."""
    CONFIG.load()
    POOL.reballance()
    return CONFIG.get()


# ─── parsing helpers ────────────────────────────────────────────────
def json_from(text):
    """Pull the first JSON object out of a (possibly chatty) reply."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = text[start:end + 1]
    try:
        return json.loads(blob)
    except Exception:                                       # noqa: BLE001
        pass
    # tolerate a trailing comma / truncated reply
    for cut in (end, end - 1, end - 2):
        try:
            return json.loads(text[start:cut + 1])
        except Exception:                                   # noqa: BLE001
            continue
    return None


def clean_line(text, limit=8):
    """A bubble-safe single line: no punctuation noise, short."""
    if not text:
        return ""
    s = str(text).strip()
    for bad in ("\n", "\r", '"', "'", "“", "”", "「", "」"):
        s = s.replace(bad, " ")
    s = " ".join(s.split())
    for ch in "。，！？、,.!?~…；;：:":
        s = s.replace(ch, "")
    return s[:limit]
