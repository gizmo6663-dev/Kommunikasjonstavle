[app]

# ─── Identifikasjon ───────────────────────────────────────────────
title = Kommunikasjonstavle
package.name = kommunikasjonstavle
package.domain = no.askapp
source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,kv,json,ttf,otf

# ─── Versjon ──────────────────────────────────────────────────────
version = 1.2

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
#
# READ_EXTERNAL_STORAGE / WRITE_EXTERNAL_STORAGE: Android <= 12
# READ_MEDIA_IMAGES:      Android 13+ (API 33+) – tilgang til bilder
# MANAGE_EXTERNAL_STORAGE: Android 11+ (API 30+) – full /sdcard-tilgang.
#   Nødvendig for å lese brukerens bilder og skrive til
#   /sdcard/Documents/ uten scoped-storage-begrensninger.
#   (Tilsvarer Eldritch Portals tillatelsessett.)
#   Merk: krever at brukeren godtar manuelt i Settings ved første kjøring.
#
android.permissions = \
    android.permission.READ_EXTERNAL_STORAGE, \
    android.permission.WRITE_EXTERNAL_STORAGE, \
    android.permission.READ_MEDIA_IMAGES, \
    android.permission.MANAGE_EXTERNAL_STORAGE

# ─── SDK-lisens ───────────────────────────────────────────────────
android.accept_sdk_license = True

# ─── AndroidX ─────────────────────────────────────────────────────
android.enable_androidx = True

# ─── UI ───────────────────────────────────────────────────────────
orientation = portrait
fullscreen = 0

# ─── Ikoner og splash ─────────────────────────────────────────────
# android.icon       = assets/icon.png
# android.presplash  = assets/presplash.png
# android.presplash_color = #4D96FF

# ─── Buildozer ────────────────────────────────────────────────────
[buildozer]
log_level = 2
warn_on_root = 0
