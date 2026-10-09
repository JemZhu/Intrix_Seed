#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Intrix Seed background service (python-for-android, foreground + sticky).

Runs the whole server inside an Android service so the world keeps living
when the panel Activity is closed:

  * Flask web panel   -> 127.0.0.1:5000   (the WebView bootstrap opens this)
  * TCP panel push    -> 0.0.0.0:8080     (ESP32 connects to the phone IP)

Data (state.json, memory, worldlog, ...) is written to INTRIX_HOME, which
defaults to the app's external files dir so it can be pulled with adb / a
file manager. Set the INTRIX_HOME env var to override.
"""

import os
import sys
import time

__version__ = "6.17.0"

WEB_PORT = int(os.environ.get("INTRIX_WEB_PORT", "5000"))
TCP_PORT = int(os.environ.get("INTRIX_TCP_PORT", "8080"))


def _app_dir():
    """Where the apk unpacked our sources."""
    for key in ("ANDROID_APP_PATH", "ANDROID_ARGUMENT", "ANDROID_PRIVATE"):
        val = os.environ.get(key)
        if val and os.path.isdir(val):
            return val
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _data_dir(service):
    """Optional writable home override.

    By default everything stays inside the unpacked app dir, which Android
    gives us read-write, so server.py and pixellife/ agree on one location.
    Set INTRIX_HOME (e.g. /sdcard/Documents/Intrix_Seed) to move the saves
    somewhere you can reach with a file manager.
    """
    forced = os.environ.get("INTRIX_HOME")
    if forced:
        try:
            os.makedirs(forced, exist_ok=True)
            return forced
        except Exception as e:
            print("[intrix] INTRIX_HOME unusable: %r" % (e,))
    return None


def _service():
    from jnius import autoclass

    return autoclass("org.kivy.android.PythonService").mService


def _hold(service):
    """Foreground service + wifi lock: no doze killing the world."""
    try:
        service.setAutoRestartService(True)
    except Exception as e:
        print("[intrix] setAutoRestartService: %r" % (e,))
    try:
        from jnius import autoclass as _ac

        Context = _ac("android.content.Context")
        WifiManager = _ac("android.net.wifi.WifiManager")
        mgr = service.getSystemService(Context.WIFI_SERVICE)
        if mgr:
            lock = mgr.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF,
                                      "IntrixSeed")
            lock.setReferenceCounted(False)
            lock.acquire()
            print("[intrix] wifi lock acquired")
    except Exception as e:
        print("[intrix] wifi lock failed: %r" % (e,))


def main():
    app_dir = _app_dir()
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    try:
        os.chdir(app_dir)
    except Exception:
        pass

    try:
        service = _service()
        _hold(service)
        home = _data_dir(service)
    except Exception as e:
        print("[intrix] android hooks unavailable: %r" % (e,))
        home = None

    if home:
        os.environ["INTRIX_HOME"] = home
    print("[intrix] app_dir=%s home=%s" % (app_dir, home or "<app dir>"))

    sys.argv = ["server.py",
                "--web-port", str(WEB_PORT),
                "--tcp-port", str(TCP_PORT)]

    import server

    print("[intrix] starting server on :%d (tcp %d)" % (WEB_PORT, TCP_PORT))
    server.main()


if __name__ == "__main__":
    main()
