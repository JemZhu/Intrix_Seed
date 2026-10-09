[app]

# (str) Title of your application
title = Intrix Seed

# (str) Package name
package.name = intrix

# (str) Package domain (needed for android/ios packaging)
package.domain = com.jem

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let-empty to include all the files)
source.include_exts = py,png,jpg,jpeg,gif,json,ttf,otf,ttc,md,txt,xml,csv

# (list) List of directories to exclude
source.exclude_dirs = venv,venv_new,logs,preview,client,screenshots,themes_backup_2026-04-21,t618,__pycache__,.git

# (list) List of exclusions using pattern matching
source.exclude_patterns = *NotoSansCJK*,*wqy-zenhei*,*.bak_*,patch_v*.py,smoke_v*.py,probe_*.py,fetch_pearl*,led_status_updater.py,openclaw_monitor.py,*.bak

# (str) Application versioning (method 1)
version = 6.17.0

# (list) Application requirements
# flask recipe pulls jinja2/werkzeug/click/itsdangerous; flask-cors is pure
# python and installed by pip. pillow + numpy have real p4a recipes.
requirements = python3,flask,flask-cors,pillow,numpy,pyjnius

# (str) Custom source folders for requirements
# (list) Garden requirements

# (str) Presplash of the application
# (str) Icon of the application
# (str) Supported orientation
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,POST_NOTIFICATIONS

# (str) Android bootstrap: webview loads http://127.0.0.1:5000 (default port)
android.bootstrap = webview

# (list) Services: foreground + sticky so the world survives the panel closing
services = Intrix:android/intrix_service.py:foreground:sticky:foregroundServiceType=dataSync

# (int) Target Android API
android.api = 34

# (int) Minimum API your APK will support (numpy recipe requires >= 24)
android.minapi = 24

# (str) Android archs to build for
android.archs = arm64-v8a

# (bool) Accept the Android SDK license non-interactively (needed on CI)
android.accept_sdk_license = True

# (bool) Enable AndroidX
android.enable_androidx = True

#
# Python for android (p4a) specific
#

# (str) python-for-android git clone branch
# p4a.branch = develop

# (str) python-for-android git clone directory
# p4a.source_dir =

#
# Android specific
#

# (list) The Android archs to build for, choose from: armeabi-v7a, arm64-v8a,
# x86, x86_64

[buildozer]

# (int) Log level: 0 debug, 1 info, 2 warning, 3 error, 4 critical
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 0
