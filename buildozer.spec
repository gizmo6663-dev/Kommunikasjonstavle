[app]

# ─── Identifikasjon ───────────────────────────────────────────────
title = Kommunikasjonstavle
package.name = kommunikasjonstavle
package.domain = no.askapp
source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,kv,json,ttf,otf,xml,md
source.include_patterns = assets/*

# ─── Versjon ──────────────────────────────────────────────────────
version = 1.2

# ─── Avhengigheter ────────────────────────────────────────────────
requirements = python3,kivy==2.3.0,pillow,android,qrcode

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
# READ_MEDIA_IMAGES:  Android 13+ (API 33+) – vise bilder i filvelger.
#                     Utløser en vanlig "Gi tilgang til bilder"-dialog.
# WRITE_EXTERNAL_STORAGE: Android <= 12 – skrive til /sdcard/.
# MANAGE_EXTERNAL_STORAGE er IKKE inkludert: den gir unødvendig bred
# tilgang og utløser en skremmende "Tilgang til alle filer"-advarsel.
#
android.permissions = \
    android.permission.READ_EXTERNAL_STORAGE, \
    android.permission.WRITE_EXTERNAL_STORAGE, \
    android.permission.READ_MEDIA_IMAGES

# ─── SDK-lisens ───────────────────────────────────────────────────
android.accept_sdk_license = True

# Bruk appens private lagringsmappe (user_data_dir) for all data.
# Tilsvarer Eldritch Portals oppsett – garantert skrivbar uten
# lagringstillatelser på Android 10+ (API 29+).
android.private_storage = True

# Intent-filter: gjør appen til mottaker for bildedeling fra galleri/andre apper.
# Brukeren kan åpne et bilde i Galleri, trykke Del, og velge Kommunikasjonstavle.
android.manifest.intent_filters = intent_filters.xml

# singleTask: gjenbruk eksisterende Activity ved mottak av delt bilde
android.manifest.activity_attributes = android:launchMode="singleTask"

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
