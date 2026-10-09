#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Intrix Seed - Android entry point (python-for-android, webview bootstrap).

The real work (Flask panel on :5000, TCP :8080 for the ESP32 panel, the pixel
life world simulation) runs inside the sticky foreground service declared in
buildozer.spec:  android/intrix_service.py

This module only makes sure that service is up, then idles, because the
WebView built by the bootstrap loads http://127.0.0.1:5000 and needs a
backend that outlives the Activity.

On a desktop this file prints a hint and exits - run `python server.py`.
"""

import os
import time

__version__ = "6.17.1"

SERVICE_CLASS = "com.jem.intrix.ServiceIntrix"


def _on_android():
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_APP_PATH" in os.environ


def _ensure_service():
    """Start the foreground service. Android reuses the running instance."""
    from jnius import autoclass

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    mActivity = PythonActivity.mActivity
    service = autoclass(SERVICE_CLASS)
    service.start(mActivity, "")
    print("[intrix] service start requested")


def main():
    if not _on_android():
        print("This is the Android entry point. On a desktop run: python server.py")
        return

    try:
        _ensure_service()
    except Exception as e:
        print("[intrix] service start failed: %r" % (e,))

    # Keep the interpreter alive: the bootstrap's WebView lives on the Java
    # side, the Python thread only has to stay around.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
