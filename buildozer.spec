[app]

# ─── Identifikasjon ───────────────────────────────────────────────
title = Kommunikasjonstavle
package.name = kommunikasjonstavle
package.domain = no.askapp
source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,kv,json,ttf,otf,xml,md

# Widget: Java-kildefiler og Android-ressurser
source.include_patterns = assets/*

# ─── Versjon ──────────────────────────────────────────────────────
version = 1.2

# ─── Avhengigheter ────────────────────────────────────────────────
requirements = python3,kivy==2.3.0,pillow,android,qrcode,plyer

# ─── Android-mål ──────────────────────────────────────────────────
android.api = 34
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a

# ─── Python for Android ───────────────────────────────────────────
p4a.branch = v2024.01.21
p4a.hook   = p4a_hooks.py

# ─── Tillatelser ──────────────────────────────────────────────────
android.permissions = \
    android.permission.READ_EXTERNAL_STORAGE, \
    android.permission.WRITE_EXTERNAL_STORAGE, \
    android.permission.READ_MEDIA_IMAGES, \
    android.permission.VIBRATE

# ─── SDK-lisens ───────────────────────────────────────────────────
android.accept_sdk_license = True

android.private_storage = True

android.manifest.intent_filters = intent_filters.xml

android.manifest.activity_attributes = android:launchMode="singleTask"

# ─── AndroidX ─────────────────────────────────────────────────────
android.enable_androidx = True

# ─── UI ───────────────────────────────────────────────────────────
orientation = portrait
fullscreen = 0

# ─── Ikoner og splash ─────────────────────────────────────────────
icon.filename = %(source.dir)s/icon.png
android.presplash       = assets/splash.png
android.presplash_color = #12183A

# ─── Buildozer ────────────────────────────────────────────────────
[buildozer]
log_level = 2
warn_on_root = 0
