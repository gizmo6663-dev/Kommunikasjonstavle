[app]

# ─── Identifikasjon ───────────────────────────────────────────────
title = Kommunikasjonstavle
package.name = kommunikasjonstavle
package.domain = no.askapp
source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,kv,json,ttf,otf

# ─── Versjon ──────────────────────────────────────────────────────
version = 1.0
version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/main.py

# ─── Avhengigheter ────────────────────────────────────────────────
requirements = python3,kivy==2.3.0,pillow,android

# ─── Android-mål ──────────────────────────────────────────────────
android.api = 34
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a

# ─── Python for Android ───────────────────────────────────────────
p4a.branch = v2024.01.21

# ─── Tillatelser ──────────────────────────────────────────────────
# READ_EXTERNAL_STORAGE og WRITE_EXTERNAL_STORAGE (Android < 13)
# READ_MEDIA_IMAGES brukes av Android 13+
android.permissions = \
    android.permission.READ_EXTERNAL_STORAGE, \
    android.permission.WRITE_EXTERNAL_STORAGE, \
    android.permission.READ_MEDIA_IMAGES

# ─── AndroidX ─────────────────────────────────────────────────────
android.enable_androidx = True

# ─── UI ───────────────────────────────────────────────────────────
orientation = portrait
fullscreen = 0

# ─── Ikoner og splash ─────────────────────────────────────────────
# Kommenter inn og legg til egne ikoner i assets/:
# android.icon       = assets/icon.png
# android.presplash  = assets/presplash.png
# android.presplash_color = #4D96FF

# ─── Buildozer ────────────────────────────────────────────────────
[buildozer]
log_level = 2
warn_on_root = 1
