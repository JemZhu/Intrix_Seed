# -*- coding: utf-8 -*-
"""TLS 根证书兜底 —— 安卓 / 精简容器专用。

python-for-android 编出来的 Python，其 OpenSSL 默认证书路径是编译期写死的
（类似 /usr/local/ssl/cert.pem），安卓上不存在，于是所有 https 请求都会报：

    URLError: <urlopen error> [SSL: CERTIFICATE_VERIFY_FAILED]
              unable to get local issuer certificate (_ssl.c:xxxx)

修复办法：把一份 cacert.pem 打进 APK，启动时指给 OpenSSL。
桌面端（macOS / Linux）系统证书库本来就在，install() 什么都不做。

用法：进程启动时调用一次 install()，之后所有 urllib/requests 的 https
都会走这里；需要显式 context 的地方用 https_context()。
"""

import os
import ssl

UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")

_SOURCE = "unknown"     # system | certifi | bundled | android | none
_CAFILE = None
_CADIR = None


# ─── 内部小工具 ────────────────────────────────────────────────────
def _is_file(p):
    try:
        return bool(p) and os.path.isfile(p)
    except Exception:
        return False


def _is_dir(p):
    try:
        return bool(p) and os.path.isdir(p)
    except Exception:
        return False


def _project_root():
    """pixellife/ 的上一级 = 项目根（APK 里就是源码解包目录）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _system_ca_ok():
    """系统默认证书库是否真的存在（桌面端一定为真，安卓上通常为假）。"""
    try:
        vp = ssl.get_default_verify_paths()
    except Exception:
        return False
    for p in (getattr(vp, "openssl_cafile", None), getattr(vp, "cafile", None)):
        if _is_file(p):
            return True
    for d in (getattr(vp, "openssl_capath", None), getattr(vp, "capath", None)):
        if _is_dir(d):
            return True
    return False


# ─── 候选证书来源（按优先级）────────────────────────────────────────
def certifi_bundle():
    try:
        import certifi
        p = certifi.where()
        return p if _is_file(p) else None
    except Exception:
        return None


def bundled_bundle():
    """仓库根目录随包发布的 cacert.pem（不依赖 p4a 是否认得 certifi）。"""
    for base in (os.environ.get("INTRIX_HOME"), _project_root()):
        if not base:
            continue
        p = os.path.join(base, "cacert.pem")
        if _is_file(p):
            return p
    return None


ANDROID_CA_DIRS = (
    "/system/etc/security/cacerts",
    "/apex/com.android.conscrypt/cacerts",
    "/etc/security/cacerts",
)


def android_ca_dir():
    for d in ANDROID_CA_DIRS:
        if _is_dir(d):
            return d
    return None


# ─── 安装 ──────────────────────────────────────────────────────────
def _patch_ssl(cafile=None, capath=None):
    """让 urllib / http.client 默认就用这份证书。

    http.client.HTTPSConnection 走 ssl._create_default_https_context()，
    换掉它就能一次性覆盖所有 urlopen，不用逐个改调用点。
    """
    def _ctx():
        return ssl.create_default_context(cafile=cafile, capath=capath)

    try:
        ssl._create_default_https_context = _ctx
    except Exception:
        pass
    try:
        import http.client as _hc
        _hc._create_https_context = lambda _vsn: _ctx()
    except Exception:
        pass


def install(force=False):
    """挑一份可用的根证书库装上。返回实际使用的路径（None = 用系统的）。"""
    global _SOURCE, _CAFILE, _CADIR

    if not force and _SOURCE != "unknown":
        return _CAFILE or _CADIR

    if not force and _system_ca_ok():
        _SOURCE = "system"
        _CAFILE = _CADIR = None
        return None

    path = certifi_bundle() or bundled_bundle()
    if path:
        _CAFILE = path
        _CADIR = os.path.dirname(path)
        _SOURCE = "certifi" if path == certifi_bundle() else "bundled"
        os.environ["SSL_CERT_FILE"] = path
        os.environ["SSL_CERT_DIR"] = _CADIR
        _patch_ssl(cafile=path)
        return path

    d = android_ca_dir()
    if d:
        _CAFILE = None
        _CADIR = d
        _SOURCE = "android"
        os.environ["SSL_CERT_DIR"] = d
        os.environ.pop("SSL_CERT_FILE", None)
        _patch_ssl(capath=d)
        return d

    _SOURCE = "none"
    _CAFILE = _CADIR = None
    return None


def https_context():
    """给 urlopen(..., context=) 用；系统库可用时返回 None（走默认行为）。"""
    if _SOURCE in ("certifi", "bundled", "android"):
        try:
            return ssl.create_default_context(cafile=_CAFILE, capath=_CADIR)
        except Exception:
            return None
    return None


def info():
    return dict(source=_SOURCE, cafile=_CAFILE, cadir=_CADIR,
                system_ok=_system_ca_ok(),
                env_file=os.environ.get("SSL_CERT_FILE"),
                env_dir=os.environ.get("SSL_CERT_DIR"))


# ─── 自检 ──────────────────────────────────────────────────────────
def _short(e):
    try:
        import ssl as _s
        if isinstance(e, _s.SSLError):
            return "SSL: %s" % (e.reason or e,)
    except Exception:
        pass
    return "%s: %s" % (type(e).__name__, e)


def probe(targets, timeout=12):
    """targets = [(名字, url), ...] —— 真发一次请求，看看到底通不通。"""
    import urllib.request

    out = []
    for name, url in targets:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=https_context()) as r:
                code = r.getcode()
                n = len(r.read())
            out.append(dict(name=name, url=url, ok=True, status=code, bytes=n))
        except Exception as e:
            out.append(dict(name=name, url=url, ok=False, error=_short(e)))
    return out


DEFAULT_TARGETS = (
    ("抖音热榜", "https://60s.viki.moe/v2/douyin"),
    ("B站热榜", "https://api.bilibili.com/x/web-interface/"
                "search/square?limit=5"),
    ("新闻60s", "https://60s.viki.moe/v2/60s"),
    ("天气", "https://api.open-meteo.com/v1/forecast"
             "?latitude=31.23&longitude=121.47&current=temperature_2m"),
)
