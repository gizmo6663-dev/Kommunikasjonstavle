#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kommunikasjonstavle v1.2
ASK-kommunikasjonsapp for barnehage og skole
Python 3 / Kivy 2.3.0  –  Buildozer / Android

Endringslogg v1.1:
  - KRITISK FIKS: DrawCanvas.color omdøpt til draw_color.
    Image-widgeten har en innebygd 'color'-egenskap (bilde-tint),
    som forårsaket bakgrunnsfargeendring og krasj ved touch.
  - Alle emojisymboler erstattet med vanlig tekst (Android mangler emoji-font).
  - try/except rundt alle PIL-operasjoner med logging til fil.
  - Koordinatsjekk (divisjon med null) i _kv2pil.
  - Verktøyrad delt i to rader; fargepalett i horisontal ScrollView.
  - Bedre dimensjoner og padding gjennom hele appen.
  - Fil-basert krasjlogg: /sdcard/Documents/Kommunikasjonstavle/crash.log
  - sys.excepthook fanger ubehandlede unntak til loggfil + ADB logcat.
"""

import os
import re
import sys
import json
import uuid
import time
import shutil
import logging
import functools
import traceback as _tb
from datetime import datetime

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.slider import Slider
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.animation import Animation
from kivy.graphics.texture import Texture
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import ListProperty, NumericProperty
from kivy.utils import platform
from kivy.core.text import LabelBase
import random
from kivy.uix.progressbar import ProgressBar


try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Moduler ───────────────────────────────────────────────────────
from kt_widgets import (
    RBtn, RBox, NavBar, BottomBar, TappableImage, LongPressImage,
    hex_k, hex_p, text_on, is_hc, hc, time_of_day_tint,
    apply_high_contrast, fsp, rdp, mk_btn, haptic_feedback, dominant_color,
    bind_card_pop, is_landscape,
)
from kt_data import (
    today_code, get_day_plan, is_paused, get_category,
    get_folder as _get_folder_data,
)

_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'assets', 'NotoSans-Regular.ttf')
if os.path.exists(_FONT_PATH):
    try:
        LabelBase.register(name='NotoSans', fn_regular=_FONT_PATH)
        # Sett som default font for alle Kivy Label/Button
        from kivy.config import Config
        Config.set('kivy', 'default_font', [
            'NotoSans', _FONT_PATH, _FONT_PATH, _FONT_PATH, _FONT_PATH,
        ])
    except Exception as _fe:
        pass  # Ikke kritisk – faller tilbake til Roboto


# ══════════════════════════════════════════════════════════════════
#  STILEDE WIDGET-KLASSER
# ══════════════════════════════════════════════════════════════════

APP_TITLE    = 'Kommunikasjonstavle'
DOWNLOAD_DIR = '/sdcard/Download'

# Disse settes i build() via App.user_data_dir
DATA_DIR    = None
IMG_DIR     = None
DRAW_DIR    = None
STRUCT_FILE = None
LOG_FILE    = None
DIAG_FILE   = None   # diagnoselogg – satt i build()


# ══════════════════════════════════════════════════════════════════
#  DIAGNOSELOGGING
#  Separat fra crash.log – skriver detaljerte tidsstemplede
#  hendelser for å diagnostisere oppstartsproblemer.
#  Leses via "Vis diagnoselogg" i Innstillinger.
# ══════════════════════════════════════════════════════════════════

_DIAG_SESSION = 0   # økes i build() per oppstart

def diag(msg: str) -> None:
    """
    Skriver én diagnoselinje til DIAG_FILE og til Python logging.

    Format:  [HH:MM:SS.mmm S#N] melding
    S#N = sesjonsnummer (1 = fersk installasjon/første start,
          2 = andre oppstart, osv.)

    Brukes i alle nøkkelfunksjoner for bildelasting og oppstart
    slik at vi kan sammenligne sesjon 1 (bilder usynlige) mot
    sesjon 2 (bilder synlige) og finne avviket.
    """
    ts   = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    line = f'[{ts} S#{_DIAG_SESSION}] {msg}\n'
    if DIAG_FILE:
        try:
            with open(DIAG_FILE, 'a', encoding='utf-8') as _f:
                _f.write(line)
        except Exception:
            pass
    logging.debug('[DIAG] %s', msg)


def diag_section(title: str) -> None:
    """Skriver en tydelig seksjonsseparator i diagnoseloggen."""
    sep = '─' * 60
    diag(f'\n{sep}\n  {title}\n{sep}')


def _fix_mojibake(s: str) -> str:
    """
    Reparerer mojibake i mappenavn fra assets/bilder/ på Android.

    Symptom: "Måltid" vises som "M[][]ltid" – bokstaven "å" blir til
    to firkanter uten glyf.

    Rotårsak: APK-pakkeprosessen lagrer asset-filnavn med æ/ø/å som
    UTF-8-bytes (f.eks. "å" = 0xC3 0xA5), men os.listdir() på Android
    kan ikke alltid dekode disse bytene som UTF-8. Python faller da
    tilbake til 'surrogateescape', som konverterer hver ugyldige byte
    til et eget surrogat-kodepunkt (U+DC80–U+DCFF). Disse kodepunktene
    har ingen glyf i noen font – derav de to firkantene.

    Fiks: hvis strengen inneholder slike surrogater, koder vi den
    tilbake til rå bytes (surrogateescape) og dekoder på nytt som
    UTF-8 – da gjenopprettes "å" korrekt.

    Funksjonen er trygg å kalle på allerede korrekte navn (norske
    bokstaver skrevet direkte i appen via tastaturet) – disse
    inneholder ingen surrogater og returneres uendret.
    """
    if not s:
        return s
    if any(0xDC80 <= ord(c) <= 0xDCFF for c in s):
        try:
            raw = s.encode('utf-8', 'surrogateescape')
            return raw.decode('utf-8')
        except (UnicodeError, UnicodeDecodeError):
            pass
    # Sekundær sjekk: "dobbel-dekodet" mojibake (UTF-8-bytes lest som
    # Latin-1/CP1252), f.eks. "Ã¥" i stedet for "å".
    if 'Ã' in s or 'Â' in s:
        try:
            fixed = s.encode('latin-1').decode('utf-8')
            if 'Ã' not in fixed and 'Â' not in fixed:
                return fixed
        except (UnicodeError, UnicodeDecodeError):
            pass
    return s


CANVAS_W = 960
CANVAS_H = 1280   # Portrettformat passer mobilskjerm

# FOLDER_COLORS – hentes fra PALETTE via indekser for å unngå duplisering.
# Indeksene refererer til PALETTE-listen nedenfor.
# Initialiseres etter PALETTE er definert.
FOLDER_COLOR_IDX = [6, 12, 14, 15, 17, 21, 23, 24]
FOLDER_COLORS: list = []  # fylles av _init_folder_colors() etter PALETTE

# ─── Ukedager for dagsplaner ──────────────────────────────────────
# ISO-baserte ukekoder (MO–SU). Python's datetime.weekday() gir 0=mandag,
# så DAY_CODES[weekday()] gir riktig kode direkte.
DAY_CODES     = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
DAY_LABEL_NO  = {'MO': 'Ma', 'TU': 'Ti', 'WE': 'On', 'TH': 'To',
                 'FR': 'Fr', 'SA': 'Lø', 'SU': 'Sø'}
DAY_FULL_NO   = {'MO': 'Mandag',  'TU': 'Tirsdag', 'WE': 'Onsdag',
                 'TH': 'Torsdag', 'FR': 'Fredag',  'SA': 'Lørdag',
                 'SU': 'Søndag'}

def time_of_day_tint():
    """
    Returnerer (r, g, b, a) for vindusbakgrunnen basert på klokkeslett.
    Bittesmå skift – ikke nok til å føles som temaskifte, men gjør at appen
    «lever» gjennom dagen. Beregnet å holde innenfor 5–8 % av basis.

    Tidsperioder (omtrentlig):
      06–10  morgen   – litt kjøligere blålig
      10–14  midt     – nøytral
      14–18  ettermiddag – litt varmere off-white
      18–22  kveld    – kjøligere igjen, dempet
      22–06  natt     – mer dempet
    """
    h    = datetime.now().hour
    base = 0.94  # vår vanlige bakgrunn ~ (0.94, 0.95, 0.98, 1.0)
    if   6  <= h < 10:   # morgen
        return (0.93, 0.95, 0.99, 1.0)
    elif 10 <= h < 14:   # midt
        return (0.94, 0.95, 0.98, 1.0)
    elif 14 <= h < 18:   # ettermiddag
        return (0.97, 0.96, 0.94, 1.0)
    elif 18 <= h < 22:   # kveld
        return (0.92, 0.93, 0.96, 1.0)
    else:                # natt
        return (0.90, 0.91, 0.94, 1.0)

# ─── Standard popup-størrelser ────────────────────────────────────
# Konsistente popup-størrelser gjør appen forutsigbar å bruke. Bruk
# disse fremfor å skrive size_hint=(...,...) direkte i hver popup.
#   POPUP_TOAST   – kortvarig melding (3 sek)
#   POPUP_CONFIRM – ja/nei-bekreftelse for destruktive handlinger
#   POPUP_SMALL   – få elementer, kompakt valg eller info
#   POPUP_MEDIUM  – skjemaer, hjelpetekst, lister med scroll
#   POPUP_LARGE   – store redigeringsskjemaer, fargevelger, søk
#   POPUP_FULL    – filvelger, full-bilde-zoom – nesten hele skjermen
POPUP_TOAST   = (0.78, 0.22)
POPUP_CONFIRM = (0.85, 0.42)
POPUP_SMALL   = (0.82, 0.55)
POPUP_MEDIUM  = (0.90, 0.78)
POPUP_LARGE   = (0.95, 0.92)
POPUP_FULL    = (0.97, 0.94)

# Bakgrunnsfarger for verktøyknapper (normal / aktiv)
TOOL_COLORS = {
    'pen':     '#4D96FF',
    'eraser':  '#78909C',
    'line':    '#2E7D32',
    'rect':    '#E65100',
    'ellipse': '#AD1457',
    'fill':    '#6A1B9A',
}
TOOL_ACTIVE = {
    'pen':     '#0D47A1',
    'eraser':  '#263238',
    'line':    '#1B5E20',
    'rect':    '#BF360C',
    'ellipse': '#880E4F',
    'fill':    '#4A148C',
}

BRUSH_COLORS = {
    'rund':         '#4D96FF',
    'myk':          '#C77DFF',
    'kalligrafisk': '#FF9F43',
    'spray':        '#6BCB77',
    'piksel':       '#FF6B6B',
}
BRUSH_ACTIVE = {
    'rund':         '#0D47A1',
    'myk':          '#7B2FBE',
    'kalligrafisk': '#B36800',
    'spray':        '#2E7D32',
    'piksel':       '#B71C1C',
}

# Fargepalett – 30 farger i 6×5-rutenett.
# Bevisst valgt for maksimal variasjon: ingen to farger er for like.
# Rad 1: svart/hvit og grå-spekter
# Rad 2: rødt, brunt, burgunder, mørk lilla, mørk blå, marineblå
# Rad 3: oransje, gul, lime, grønn, blågrønn, turkis
# Rad 4: lyseblå, lys lilla, rosa, laks, beige, sand
# Rad 5: elektrisk blå, neon grønn, magenta, korall, mint, guld
PALETTE = [
    # Nøytrale
    '#000000', '#444444', '#888888', '#BBBBBB', '#E8E8E8', '#FFFFFF',
    # Mørke varme/kalde
    '#B71C1C', '#6D4C41', '#880E4F', '#4A148C', '#1A237E', '#01579B',
    # Mellomtone primære
    '#E53935', '#FB8C00', '#FDD835', '#43A047', '#039BE5', '#8E24AA',
    # Lyse/pastel
    '#EF9A9A', '#FFE082', '#C8E6C9', '#B3E5FC', '#E1BEE7', '#FFCCBC',
    # Spesielle/levende
    '#00E5FF', '#76FF03', '#F50057', '#FF6D00', '#1DE9B6', '#FFD740',
]

# Initialiser FOLDER_COLORS fra PALETTE-indekser (unngår duplisering)
FOLDER_COLORS = [PALETTE[i] for i in FOLDER_COLOR_IDX]

# Standard aktivitetskategorier som brukes til fargekoding i dagsplaner.
# Hver aktivitet kan tilordnes én kategori; den vises som en tynn fargestripe
# på venstre kant av rad-elementene. Brukeren kan endre disse senere.
DEFAULT_CATEGORIES = [
    {'id': 'maltid',   'name': 'Måltid',   'color': '#FFB74D'},
    {'id': 'lek',      'name': 'Lek',      'color': '#FFD93D'},
    {'id': 'hvile',    'name': 'Hvile',    'color': '#9C7DCE'},
    {'id': 'utetid',   'name': 'Utetid',   'color': '#6BCB77'},
    {'id': 'samling',  'name': 'Samling',  'color': '#4D96FF'},
    {'id': 'overgang', 'name': 'Overgang', 'color': '#90A4AE'},
]

DEFAULT_STRUCT = {
    "folders": [],
    "sequences": [],
    "dagsrytme": [],
    "dagsplaner": {c: [] for c in DAY_CODES},
    "dagsoppsett": [],
    "notater":    {c: "" for c in DAY_CODES},
    "kategorier": list(DEFAULT_CATEGORIES),
    "pause":      None,    # {"since": "ISO timestamp"} eller None
    "settings": {
        "tts_enabled":            False,
        "font_scale":             1.0,
        "high_contrast":          False,
        "swipe_nav":              False,
        "onboarding_done":        False,
        "notifications_timer":    False,
        "notifications_dagsplan": False
    }
}

# ── Notifikasjon-ID-er (Android AlarmManager) ─────────────────────────────
# Unike heltall brukes som PendingIntent request codes i AlarmManager.
# Dagsplan støtter inntil 32 aktiviteter per dag (nok for en barnehagedag).
NOTIF_TIMER          = 9001          # tidsur ferdig
NOTIF_DAG_START_BASE = 9100          # 9100–9131: aktivitet starter
NOTIF_DAG_END_BASE   = 9200          # 9200–9231: aktivitet ferdig

# ══════════════════════════════════════════════════════════════════
#  KRASJLOGGING
# ══════════════════════════════════════════════════════════════════

def setup_logging():
    """
    Setter opp fil-basert logging til crash.log og ADB logcat (stdout).
    sys.excepthook fanger opp alle ubehandlede Python-unntak.
    """
    try:
        if DATA_DIR:
            os.makedirs(DATA_DIR, exist_ok=True)
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] %(funcName)s: %(message)s',
            encoding='utf-8',
        )
    except Exception:
        # Fallback: log til stderr hvis filen ikke kan opprettes
        logging.basicConfig(
            stream=sys.stderr,
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] %(funcName)s: %(message)s',
        )

    # Dupliser til stdout slik at ADB logcat fanger det
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter(
        '[KT] %(levelname)s %(funcName)s: %(message)s'
    ))
    logging.getLogger().addHandler(console)

    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical(
            'Ubehandlet unntak:\n%s',
            ''.join(_tb.format_exception(exc_type, exc_value, exc_tb)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    logging.info('Kommunikasjonstavle v1.2 starter. PIL_OK=%s', PIL_OK)


# ══════════════════════════════════════════════════════════════════
#  HJELPERE
# ══════════════════════════════════════════════════════════════════

def _schedule_widget_alarm():
    """
    Registrerer AlarmManager-alarm for widget-oppdatering hvert 15. min.
    Hele funksjonen er try/except – feiler den stille uten krasj.
    """
    if platform != 'android':
        return
    try:
        from jnius import autoclass
        from android import mActivity
        Context       = autoclass('android.content.Context')
        Intent        = autoclass('android.content.Intent')
        PendingIntent = autoclass('android.app.PendingIntent')
        AlarmManager  = autoclass('android.app.AlarmManager')
        ComponentName = autoclass('android.content.ComponentName')

        intent = Intent('android.appwidget.action.APPWIDGET_UPDATE')
        intent.setComponent(ComponentName(
            mActivity.getPackageName(),
            'no.askapp.kommunikasjonstavle.KtWidget'))

        pi = PendingIntent.getBroadcast(
            mActivity, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT |
            PendingIntent.FLAG_IMMUTABLE)

        am = mActivity.getSystemService(Context.ALARM_SERVICE)
        am.setInexactRepeating(
            0,           # ELAPSED_REALTIME = 0
            0,
            900000,      # 15 min i ms
            pi)
        logging.info('AlarmManager OK')
    except Exception as e:
        logging.debug('AlarmManager feilet (ikke kritisk): %s', e)


def _encode_img_b64(path, size=400):
    """
    Skalerer bilde til size×size og returnerer base64 JPEG-streng.
    Kalles FØR jnius-konteksten åpnes – PIL og io er rene Python.
    """
    import io as _io, base64 as _b64
    if not PIL_OK or not path or not os.path.exists(path):
        return ''
    try:
        img = PILImage.open(path).convert('RGBA')
        img.thumbnail((size, size), PILImage.LANCZOS)
        bg  = PILImage.new('RGB', (size, size), (244, 245, 250))
        ox  = (size - img.width)  // 2
        oy  = (size - img.height) // 2
        bg.paste(img.convert('RGB'), (ox, oy))
        buf = _io.BytesIO()
        bg.save(buf, format='JPEG', quality=70)
        return _b64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        logging.debug('_encode_img_b64 feilet: %s', e)
        return ''


def _update_widget(data):
    """
    Skriver aktivitetsnavn, tid og bilde (base64 JPEG) til SharedPreferences.
    Bildet enkodes i ren Python FØR jnius åpnes for stabilitet.
    Sjekker at data er gyldig dict før jnius-konteksten åpnes.
    """
    if platform != 'android':
        return
    if not isinstance(data, dict):
        return  # Kalt for tidlig – data ikke klar ennå
    try:
        import datetime as _dt
        from jnius import autoclass
        from android import mActivity

        # Pause-sjekk først – widget skal være helt tydelig på status
        if is_paused(data):
            line1 = '⏸  Dagsrytme på pause'
            line2 = 'Trykk for å gjenoppta'
            img_b64 = ''
            current = None
            upcoming = None
        else:
            # Bruk dagens plan fra dagsplaner. Faller tilbake til gammel dagsrytme-
            # liste for bakoverkompatibilitet med strukturer fra før migrering.
            plans = data.get('dagsplaner')
            if isinstance(plans, dict):
                entries = plans.get(today_code(), [])
            else:
                entries = data.get('dagsrytme', [])
            now       = _dt.datetime.now()
            now_total = now.hour * 60 + now.minute

            def to_min(t):
                try:
                    h, m = str(t).split(':')
                    return int(h)*60 + int(m)
                except Exception:
                    return -1

            current  = None
            upcoming = None
            for e in sorted(entries, key=lambda x: x.get('start', '00:00')):
                s = to_min(e.get('start', ''))
                t = to_min(e.get('end',   ''))
                if s < 0 or t < 0:
                    continue
                if s <= now_total < t:
                    current = e
                elif s > now_total and upcoming is None:
                    upcoming = e

            # Enkod bilde i ren Python FØR jnius
            img_b64 = _encode_img_b64(current.get('image', '') if current else '')

            if current:
                line1 = current['name']
                line2 = current.get('start','') + ' – ' + current.get('end','')
                # Hvis det er en kommende aktivitet, vis den som tilleggslinje.
                if upcoming:
                    nxt_start = upcoming.get('start','')
                    line2 += '   ·   Neste: ' + upcoming.get('name','') + ' kl. ' + nxt_start
            elif upcoming:
                # Sjekk om aktiviteten starter veldig snart (innen 2 min) –
                # da signaliserer vi det tydelig i teksten.
                nxt_start_min = to_min(upcoming.get('start',''))
                minutes_until = nxt_start_min - now_total if nxt_start_min >= 0 else 99
                if 0 <= minutes_until <= 2:
                    line1 = '⚠  Starter snart: ' + upcoming.get('name','')
                    line2 = 'kl. ' + upcoming.get('start','') + '  (om ' + str(minutes_until) + ' min)'
                else:
                    line1 = 'Neste: ' + upcoming.get('name','')
                    line2 = 'kl. ' + upcoming.get('start','')
                # Dempet bilde av kommende aktivitet
                img_b64 = _encode_img_b64(upcoming.get('image', ''))
            else:
                line1 = 'Ingen aktivitet nå'
                line2 = ''

        prefs  = mActivity.getSharedPreferences('kt_widget', 0)
        editor = prefs.edit()
        editor.putString('line1',   line1)
        editor.putString('line2',   line2)
        editor.putString('img_b64', img_b64)
        editor.apply()

        Intent        = autoclass('android.content.Intent')
        AppWidgetMgr  = autoclass('android.appwidget.AppWidgetManager')
        ComponentName = autoclass('android.content.ComponentName')
        broadcast = Intent(AppWidgetMgr.ACTION_APPWIDGET_UPDATE)
        broadcast.setComponent(ComponentName(
            mActivity.getPackageName(),
            'no.askapp.kommunikasjonstavle.KtWidget'))
        mActivity.sendBroadcast(broadcast)
        logging.info('Widget oppdatert OK')
    except Exception as e:
        logging.debug('_update_widget feilet: %s', e)
        return

    # Widget_log skrives ETTER at jnius-konteksten er lukket
    try:
        import datetime as _dt2
        _wlog = os.path.join(DATA_DIR, 'widget_log.txt') if DATA_DIR else None
        if _wlog:
            os.makedirs(os.path.dirname(_wlog), exist_ok=True)
            _ts = _dt2.datetime.now().strftime('%H:%M:%S')
            with open(_wlog, 'a', encoding='utf-8') as _wf:
                _wf.write(f'{_ts}  [PYTHON] _update_widget: {line1} | {line2}\n')
            with open(_wlog, 'r', encoding='utf-8') as _wf:
                _lines = _wf.readlines()
            if len(_lines) > 200:
                with open(_wlog, 'w', encoding='utf-8') as _wf:
                    _wf.writelines(_lines[-200:])
    except Exception:
        pass


_THUMB_CACHE = {}
_THUMB_CACHE_MAX = 200

def get_thumbnail(path, w, h):
    """
    Returnerer en PIL-basert Kivy Texture skalert til (w×h).

    Bruker en manuell cache (IKKE functools.lru_cache) som kun lagrer
    VELLYKKEDE resultater. Begrunnelse: like etter installasjon kan et
    nylig kopiert bilde (fra _init_bundled_assets) i sjeldne tilfeller
    feile på FØRSTE lesing (PIL rekker ikke åpne filen før den er
    ferdig flushet til disk). Med lru_cache ville dette None-resultatet
    bli cachet PERMANENT for resten av appsesjonen – bildet ville aldri
    vises før appen restartes. Med manuell cache prøver vi på nytt
    neste gang denne flisen tegnes (f.eks. ved _show_folder-refresh).
    """
    key = (path, int(w), int(h))
    if key in _THUMB_CACHE:
        diag(f'THUMB CACHE_HIT {os.path.basename(path)}')
        return _THUMB_CACHE[key]

    # ── Diagnose: logg filstatus FØR PIL prøver å åpne ──────────
    exists  = os.path.exists(path)
    fsize   = os.path.getsize(path) if exists else -1
    diag(f'THUMB START {os.path.basename(path)} exists={exists} size={fsize}B '
         f'PIL_OK={PIL_OK}')

    if not PIL_OK or not path or not exists:
        diag(f'THUMB SKIP (PIL_OK={PIL_OK} path={bool(path)} exists={exists})')
        return None

    t0 = time.time()
    try:
        img  = PILImage.open(path).convert('RGB')
        diag(f'THUMB PIL_OPEN OK {os.path.basename(path)} '
             f'src={img.width}×{img.height}')
        img.thumbnail((int(w), int(h)), PILImage.LANCZOS)
        # Pad til nøyaktig størrelse
        out  = PILImage.new('RGB', (int(w), int(h)), (255, 255, 255))
        ox   = (int(w) - img.width)  // 2
        oy   = (int(h) - img.height) // 2
        out.paste(img, (ox, oy))
        raw  = out.tobytes()
        tex  = Texture.create(size=(int(w), int(h)), colorfmt='rgb')
        tex.blit_buffer(raw, colorfmt='rgb', bufferfmt='ubyte')
        tex.flip_vertical()
        if len(_THUMB_CACHE) >= _THUMB_CACHE_MAX:
            _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
        _THUMB_CACHE[key] = tex
        diag(f'THUMB OK {os.path.basename(path)} t={time.time()-t0:.3f}s')
        return tex
    except Exception as _te:
        diag(f'THUMB FAIL {os.path.basename(path)} err={type(_te).__name__}: {_te} '
             f't={time.time()-t0:.3f}s')
        return None  # IKKE cachet – tillater retry neste gang


def _thumb_cache_clear():
    _THUMB_CACHE.clear()


get_thumbnail.cache_clear = _thumb_cache_clear



def _wlog_write(msg):
    """Skriv til widget_log.txt – synlig fra Innstillinger → Vis widget-logg."""
    try:
        import datetime as _wdt
        _wlog = os.path.join(DATA_DIR, 'widget_log.txt') if DATA_DIR else None
        if not _wlog:
            return
        os.makedirs(os.path.dirname(_wlog), exist_ok=True)
        ts = _wdt.datetime.now().strftime('%H:%M:%S')
        with open(_wlog, 'a', encoding='utf-8') as f:
            f.write(ts + '  ' + msg + '\n')
    except Exception:
        pass


def load_struct():
    if STRUCT_FILE and os.path.exists(STRUCT_FILE):
        try:
            with open(STRUCT_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            # Migrer eldre filer som mangler sequences-nøkkel
            if 'sequences' not in d:
                d['sequences'] = []
            # Migrer mapper uten subfolders-nøkkel
            for fo in d.get('folders', []):
                if 'subfolders' not in fo:
                    fo['subfolders'] = []
                if 'opens' not in fo:
                    fo['opens'] = 0
            if 'dagsrytme' not in d:
                d['dagsrytme'] = []
            # Migrer fra gammelt single-list dagsrytme til dagsplaner per ukedag.
            # Brukerens eksisterende aktiviteter blir kopiert til alle 7 dager
            # som startpunkt – de kan så tilpasse per dag etterpå.
            if 'dagsplaner' not in d:
                old = d.get('dagsrytme', [])
                d['dagsplaner'] = {
                    code: [dict(a) for a in old] for code in DAY_CODES
                }
            # Notater per ukedag – tomme strenger ved første migrering.
            if 'notater' not in d:
                d['notater'] = {code: '' for code in DAY_CODES}
            else:
                # Sørg for at alle 7 koder finnes (kan mangle hvis fil ble
                # delvis-redigert manuelt).
                for code in DAY_CODES:
                    d['notater'].setdefault(code, '')
            # Kategorier – brukes til fargekoding av aktiviteter.
            if 'kategorier' not in d:
                d['kategorier'] = list(DEFAULT_CATEGORIES)
            # Pause-status: None når ingen pause er aktiv.
            if 'pause' not in d:
                d['pause'] = None
            # Dagsoppsett (templates) – starter tomme, brukeren kan
            # lagre dagsplaner som maler å bytte til senere.
            if 'dagsoppsett' not in d:
                d['dagsoppsett'] = []
            if 'settings' not in d:
                d['settings'] = {'tts_enabled': False, 'font_scale': 1.0, 'high_contrast': False, 'swipe_nav': False, 'onboarding_done': False}
            else:
                # Brukere som migrerer fra eldre versjon har allerede appen
                # i bruk – ingen grunn til å vise omvisningen for dem.
                # Helt nye brukere (uten settings-dict) får derimot turen.
                d['settings'].setdefault('onboarding_done', True)
            return d
        except Exception as e:
            logging.error('Feil ved lasting av structure.json: %s', e)
    import copy
    return copy.deepcopy(DEFAULT_STRUCT)

_save_event = [None]

def save_struct(d, immediate=False):
    """
    Lagrer structure.json med 1 sekund debounce.
    immediate=True brukes ved app-pause og kritiske endringer.
    Reduserer I/O ved f.eks. opens-teller og sekvensielle endringer.
    Viser «Lagrer...»-label på skjermen i 0.5 sek ved lagring.
    """
    if not STRUCT_FILE:
        logging.error('save_struct: STRUCT_FILE ikke satt ennå')
        return

    def _show_save_indicator():
        """Viser «Lagrer...»-label i 0.5 sekunder nederst på skjermen."""
        try:
            from kivy.app import App as _App
            app = _App.get_running_app()
            if not app or not hasattr(app, '_content'):
                return
            lbl = Label(
                text='Lagrer...',
                font_size=sp(13),
                color=(0.3, 0.35, 0.5, 0.9),
                size_hint=(None, None),
                size=(dp(120), dp(30)),
                halign='center',
                bold=True,
            )
            # Plasser nederst i vinduet over navbar
            from kivy.core.window import Window as _Win
            lbl.pos = ((_Win.width - dp(120)) / 2, dp(76))
            _Win.add_widget(lbl)
            def _remove(*_):
                try:
                    _Win.remove_widget(lbl)
                except Exception:
                    pass
            Clock.schedule_once(_remove, 0.5)
        except Exception as _si_err:
            logging.debug('save indicator feilet: %s', _si_err)

    def _do_save(*_):
        # Synkroniser dagsrytme-feltet med dagens plan. Widgeten og annen
        # kode som leser dagsrytme får dermed alltid en korrekt liste,
        # uavhengig av hvilken dag brukeren redigerte sist.
        if isinstance(d.get('dagsplaner'), dict):
            d['dagsrytme'] = list(d['dagsplaner'].get(today_code(), []))
        os.makedirs(os.path.dirname(STRUCT_FILE), exist_ok=True)
        try:
            with open(STRUCT_FILE, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            logging.debug('structure.json lagret (%s)', STRUCT_FILE)
            Clock.schedule_once(lambda *_: _show_save_indicator(), 0)
        except Exception as e:
            logging.error('Feil ved lagring: %s', e)
        _save_event[0] = None
        # Oppdater widget kun ved debounced lagring (ikke immediate/on_pause)
        # for å unngå at jnius-kall forstyrrer activity_bind-registrering
        if not immediate:
            try:
                _update_widget(d)
            except Exception as _we:
                logging.debug('widget etter lagring feilet: %s', _we)

    if immediate:
        if _save_event[0]:
            _save_event[0].cancel()
            _save_event[0] = None
        _do_save()
        return

    if _save_event[0]:
        _save_event[0].cancel()
    _save_event[0] = Clock.schedule_once(_do_save, 1.0)


# get_folder: lokal implementasjon som wrapper rundt kt_data-versjonen,
# sikrer bakoverkompatibilitet med alle referanser i App-klassen.
def get_folder(d, fid):
    """Finner mappe med gitt id – søker rekursivt i subfolders."""
    for fo in d.get('folders', []):
        if fo['id'] == fid:
            return fo
        for sub in fo.get('subfolders', []):
            if sub['id'] == fid:
                return sub
    return None

def img_filter(folder, filename):
    """
    FileChooser-filter for bildefiler.
    1. Mapper vises alltid (nødvendig for navigasjon).
    2. Filendelser sjekkes case-insensitivt.
    3. os.path.isdir er innkapslet i try/except – på Android kan
       manglende tillatelse gi OSError/PermissionError, noe som
       ellers ville skjule alle oppføringer.
    """
    try:
        full = os.path.join(folder, filename)
        if os.path.isdir(full):
            return True
    except Exception:
        pass
    return filename.lower().endswith(
        ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
    )


def _plog(msg):
    """
    Minimal loggfunksjon for bruk FØR App er initialisert.
    Skriver direkte til crash.log slik at vi kan diagnostisere
    tillatelsesproblemeer uten å stole på logging-modulen.
    """
    try:
        if LOG_FILE:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f'[PERM] {msg}\n')
    except Exception:
        pass


def request_android_permissions():
    """
    Tillatelsesforespørsel – modul-nivå som EP, kalt via Clock fra build().

    Bruker strengbaserte tillatelser i stedet for Permission-konstantene
    fordi Permission.READ_MEDIA_IMAGES ikke finnes i p4a v2024.01.21
    (AttributeError), noe som fikk except:pass til å svelge hele kallet.

    Skriver til crash.log UTENFOR try/except slik at vi alltid ser
    om funksjonen i det hele tatt kjøres – uavhengig av hva som feiler.
    """
    _plog('request_android_permissions kalt, platform=' + str(platform))
    if platform != 'android':
        _plog('Ikke Android – hopper over.')
        return

    # Tillatelsene som strenger – fungerer i alle p4a-versjoner.
    # Android ignorerer tillatelser som allerede er innvilget.
    # Android 13+ (API 33): READ_EXTERNAL_STORAGE er utdatert og ignorert.
    # Vi må be om READ_MEDIA_IMAGES i stedet.
    # Android < 13: READ_EXTERNAL_STORAGE er korrekt.
    try:
        from android import mActivity
        sdk = mActivity.getApplicationInfo().targetSdkVersion
        api = mActivity.getPackageManager()                        .getApplicationInfo(mActivity.getPackageName(), 0)                        .targetSdkVersion
        # Enklere: sjekk Build.VERSION.SDK_INT
        from jnius import autoclass
        Build = autoclass('android.os.Build$VERSION')
        sdk_int = Build.SDK_INT
        _plog(f'SDK_INT={sdk_int}')
    except Exception as _e:
        sdk_int = 34  # anta Android 14 ved feil
        _plog(f'SDK_INT ukjent, antar {sdk_int}: {_e}')

    if sdk_int >= 33:
        PERMS = [
            'android.permission.READ_MEDIA_IMAGES',
        ]
    else:
        PERMS = [
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.WRITE_EXTERNAL_STORAGE',
        ]
    _plog(f'Ber om tillatelser (SDK {sdk_int}): {PERMS}')

    # Steg 1: prøv android.permissions-modulen (p4a standard)
    try:
        from android.permissions import request_permissions
        _plog('android.permissions importert OK – kaller request_permissions')
        request_permissions(PERMS)
        _plog('request_permissions kalt OK')
        return
    except Exception as e:
        _plog(f'android.permissions feilet: {e}')

    # Steg 2: direkte jnius-fallback (garantert tilgjengelig)
    _plog('Forsøker jnius-fallback ...')
    try:
        from jnius import autoclass
        from android import mActivity
        ArrayList = autoclass('java.util.ArrayList')
        lst = ArrayList()
        for p in PERMS:
            lst.add(p)
        mActivity.requestPermissions(lst.toArray(), 1001)
        _plog('jnius requestPermissions kalt OK')
    except Exception as e:
        _plog(f'jnius-fallback feilet: {e}')


# ══════════════════════════════════════════════════════════════════
#  BILDEIMPORT – TO METODER
#
#  Metode A – ACTION_OPEN_DOCUMENT (filvelger):
#    Trykk "Velg bilde" i appen → Androids innebygde filvelger åpnes.
#    Krever ingen tillatelser. Fungerer på alle Android-versjoner.
#
#  Metode B – Share intent (del fra Galleri):
#    Åpne bilde i Galleri → Del → Kommunikasjonstavle.
#    Appen mottar bildet via on_new_intent / _SHARE_PENDING.
#    Krever at intent_filters.xml er inkludert i APK-en (se buildozer.spec).
#
#  Vurdering: ACTION_OPEN_DOCUMENT er beholdt som primærmetode fordi den
#  er mer forutsigbar (brukeren ser hva som skjer i appen). Share-mottak
#  er lagt til som tilleggsmetode – begge bruker _copy_content_uri().
# ══════════════════════════════════════════════════════════════════

# Request-kode for ACTION_OPEN_DOCUMENT
_PICK_IMAGE_REQUEST  = 9742
_pick_image_callback = [None]

# Buffer for bilde mottatt via Share intent (behandles i build())
_SHARE_PENDING = [None]


def _handle_share_intent(intent):
    """
    Mottar et bilde delt fra Galleri eller annen app.
    Lagrer URI i _SHARE_PENDING[0]; appen henter den i on_start/on_resume
    og kaller _process_shared_image().
    """
    if intent is None:
        return
    try:
        from jnius import autoclass
        IntentC = autoclass('android.content.Intent')
        action  = intent.getAction()
        mtype   = intent.getType()
        if action == 'android.intent.action.SEND' and mtype and mtype.startswith('image/'):
            uri = intent.getParcelableExtra(IntentC.EXTRA_STREAM)
            if uri:
                _SHARE_PENDING[0] = uri
                _plog(f'Share-intent mottatt: {uri}')
    except Exception as e:
        _plog(f'_handle_share_intent feil: {e}')


def _copy_content_uri(uri, dst_path):
    """
    Kopierer en Android content-URI til lokal fil via FileHelper.java.
    """
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        from jnius import autoclass
        from android import mActivity
        _wlog_write('[COPY] laster FileHelper...')
        FileHelper = autoclass('no.askapp.kommunikasjonstavle.FileHelper')
        _wlog_write(f'[COPY] kaller copyUriToFile uri_type={type(uri).__name__}')
        n = FileHelper.copyUriToFile(mActivity, uri, dst_path)
        _wlog_write(f'[COPY] returnerte {n}')
        if n < 0:
            _wlog_write('[COPY] FEIL: FileHelper returnerte -1')
            return False
        _wlog_write(f'[COPY] OK: {n} bytes')
        _scale_image(dst_path)
        return True
    except Exception as e:
        _wlog_write(f'[COPY UNNTAK] {type(e).__name__}: {e}')
        _plog(f'_copy_content_uri UNNTAK: {type(e).__name__}: {e}')
        return False


def _scale_image(path):
    """Skalerer bilde til maks 512×512 ved import."""
    if not PIL_OK:
        return
    try:
        img = PILImage.open(path)
        W, H = img.size
        if W > 512 or H > 512:
            img.thumbnail((512, 512), PILImage.LANCZOS)
            img.save(path)
            _plog(f'Skalert: {W}x{H} → {img.size}')
    except Exception as e:
        _plog(f'Skalering feilet: {e}')


def _suggest_from_image(path):
    """
    Heuristikk-basert auto-tagging av nye bilder.

    Returnerer (foreslått navn, foreslått kategori-id). Begge kan være
    None hvis vi ikke har grunnlag for et godt forslag.

    Strategien er bevisst enkel og lokal – ingen ML-modell, ingen
    nettverkskall. Det reduserer kompleksitet, energibruk og
    personvernrisiko. Forslag er kun forslag: brukeren godkjenner
    før noe lagres.

    Navn-heuristikk: Cleaner opp filnavn (strip prefiks som "img_",
    erstatt understrek med mellomrom, capitalize første bokstav).

    Kategori-heuristikk: Analyserer dominant farge i bildets midtparti.
    HSV-mapping fra fargetone til kategorisom typisk passer det
    visuelle uttrykket (varme farger → måltid, grønne → utetid, osv.).
    Treffer ikke alltid, men er rimelig presis for typiske AAC-symboler
    som er fargesterke og enkle.
    """
    name = None
    cat  = None
    if not path or not os.path.exists(path):
        return (None, None)

    # ── Navn-forslag fra filnavn ─────────────────────────────────────
    try:
        base = os.path.basename(path)
        stem, _ = os.path.splitext(base)
        # Fjern vanlige prefiks fra galleri-apper og kameraer
        for prefix in ('img_', 'image_', 'photo_', 'pic_', 'screenshot_',
                       'IMG_', 'PHOTO_'):
            if stem.lower().startswith(prefix.lower()):
                stem = stem[len(prefix):]
                break
        # Drop trailing tall fra duplikater ("Spise(2)" → "Spise")
        stem = re.sub(r'\s*\(\d+\)\s*$', '', stem)
        # Erstatt understrek og bindestrek med mellomrom
        stem = stem.replace('_', ' ').replace('-', ' ').strip()
        # Drop rene tallnavn (typisk fra kamera: "20240501_125930")
        if re.match(r'^\d[\d\s:]*$', stem):
            name = None
        elif stem:
            # Capitalize første bokstav, behold resten
            name = stem[0].upper() + stem[1:]
    except Exception:
        pass

    # ── Kategori-forslag fra dominant farge ──────────────────────────
    try:
        if PIL_OK:
            img = PILImage.open(path).convert('RGB')
            # Krymp til en liten samplet versjon for hastighet,
            # analyser midtparti (unngå hvit/transparent kant typisk
            # i ARASAAC-symboler).
            img.thumbnail((64, 64), PILImage.LANCZOS)
            w, h = img.size
            # Midtområde: 50% midten av bildet
            cx0 = w // 4
            cy0 = h // 4
            crop = img.crop((cx0, cy0, cx0 + w//2, cy0 + h//2))
            # Hent dominante piksler ved å la PIL kvantisere
            pal = crop.quantize(colors=4).convert('RGB')
            pixels = list(pal.getdata())
            if pixels:
                # Tell og finn vanligste farge
                from collections import Counter
                most_common = Counter(pixels).most_common(1)[0][0]
                r, g, b = most_common
                # Konverter til HSV
                import colorsys
                h_, s_, v_ = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                # Lav metning = grå/hvit/svart → uklart, ingen kategori
                if s_ < 0.20:
                    cat = None
                else:
                    h_deg = h_ * 360
                    # Mapping basert på fargetone:
                    #  rød/oransje (0-45)        → måltid (varm, mat-assosiasjon)
                    #  gul (45-65)               → lek (energisk, lekent)
                    #  grønn (65-160)            → utetid (natur)
                    #  cyan/blå (160-260)        → samling/hvile (rolig)
                    #  lilla/rosa (260-330)      → hvile
                    #  rosa/magenta (330-360)    → måltid (rosa frukt etc.)
                    if h_deg < 45:
                        cat = 'maltid'
                    elif h_deg < 65:
                        cat = 'lek'
                    elif h_deg < 160:
                        cat = 'utetid'
                    elif h_deg < 260:
                        cat = 'samling'
                    elif h_deg < 330:
                        cat = 'hvile'
                    else:
                        cat = 'maltid'
    except Exception:
        pass

    return (name, cat)


def _open_android_picker(callback):
    """
    Åpner Androids innebygde bildevelger (ACTION_OPEN_DOCUMENT).
    callback(dst_path) kalles med lokal filsti etter at brukeren
    har valgt et bilde og det er kopiert til IMG_DIR.
    Ingen tillatelser nødvendig.
    """
    if platform != 'android':
        callback(None)
        return
    try:
        from jnius import autoclass
        from android import mActivity
        from android.activity import bind as activity_bind, unbind as activity_unbind

        _pick_image_callback[0] = callback

        Intent    = autoclass('android.content.Intent')
        intent    = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType('image/*')
        # Flervalg: brukeren kan velge flere bilder samtidig
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)

        def _uri_to_path(uri):
            """Kopierer én URI til IMG_DIR og returnerer lokal sti."""
            try:
                OpenableColumns = autoclass('android.provider.OpenableColumns')
                from android import mActivity as act
                cursor = act.getContentResolver().query(
                    uri, None, None, None, None)
                fname = 'bilde_' + str(uuid.uuid4())[:8] + '.jpg'
                if cursor and cursor.moveToFirst():
                    idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if idx >= 0:
                        fname = cursor.getString(idx)
                    cursor.close()
            except Exception as e:
                _plog(f'Filnavn-lookup feil: {e}')
                fname = 'bilde_' + str(uuid.uuid4())[:8] + '.jpg'
            dst = os.path.join(IMG_DIR, fname)
            return dst if _copy_content_uri(uri, dst) else None

        def on_activity_result(request_code, result_code, data):
            if request_code != _PICK_IMAGE_REQUEST:
                return
            activity_unbind(on_activity_result=on_activity_result)
            cb = _pick_image_callback[0]
            _pick_image_callback[0] = None
            # RESULT_OK = -1 i Java, men p4a kan sende usignert 0xFFFFFFFF
            _RESULT_OK = (-1, 0xFFFFFFFF, 4294967295)
            _wlog_write(f'[RESULT] req={request_code} res={result_code} data={data is not None}')
            _plog(f'on_activity_result: req={request_code} res={result_code} data={data is not None}')
            if result_code not in _RESULT_OK or data is None:
                _plog(f'Bildevelger avbrutt: result_code={result_code}')
                if cb:
                    Clock.schedule_once(lambda *_: cb(None), 0)
                return

            paths = []
            # Flervalg: ClipData
            clip = data.getClipData()
            _wlog_write(f'[CLIP] clip={clip is not None} count={clip.getItemCount() if clip else 0}')
            if clip and clip.getItemCount() > 0:
                for i in range(clip.getItemCount()):
                    uri = clip.getItemAt(i).getUri()
                    p   = _uri_to_path(uri)
                    _wlog_write(f'[CLIP item {i}] uri={uri is not None} path={p}')
                    if p:
                        paths.append(p)
            else:
                # Enkeltvalg: getData()
                uri = data.getData()
                _wlog_write(f'[GETDATA] uri={uri}')
                if uri:
                    p = _uri_to_path(uri)
                    _wlog_write(f'[URI2PATH] p={p}')
                    if p:
                        paths.append(p)

            _wlog_write(f'[PATHS] total={len(paths)}')
            if cb:
                if len(paths) == 1:
                    Clock.schedule_once(lambda *_: cb(paths[0]), 0)
                elif len(paths) > 1:
                    Clock.schedule_once(lambda *_: cb(paths), 0)
                else:
                    Clock.schedule_once(lambda *_: cb(None), 0)

        activity_bind(on_activity_result=on_activity_result)

        # NB: ACTION_OPEN_DOCUMENT bruker Storage Access Framework, som gir
        # midlertidig URI-tillatelse uten at appen trenger READ_MEDIA_IMAGES.
        # Vi spør derfor ikke om denne tillatelsen i det hele tatt — det sparer
        # brukeren én dialog og fjerner et race mellom permission-prompt og
        # startActivityForResult.

        _wlog_write('[PICKER] activity_bind OK, starter filvelger')
        mActivity.startActivityForResult(intent, _PICK_IMAGE_REQUEST)
        _plog('ACTION_OPEN_DOCUMENT startet (flervalg aktivert)')
    except Exception as e:
        _wlog_write(f'[PICKER FEIL] {type(e).__name__}: {e}')
        _plog(f'_open_android_picker feil: {e}')
        logging.exception('_open_android_picker: feil')
        callback(None)


# ══════════════════════════════════════════════════════════════════
#  WIDGET: TRYKKBART BILDE
# ══════════════════════════════════════════════════════════════════

class DrawCanvas(Image):
    """
    PIL/Pillow-basert tegneflate med stempel-basert pensel og
    Catmull-Rom stabilisering.

    VIKTIG: bruker 'draw_color' (ikke 'color') for å unngå kollisjon
    med Kivy Image sin innebygde 'color'-tint-egenskap.

    Penselkvalitet:
      Stempel-metoden maler fylte sirkler langs hele banen i stedet
      for d.line(). Dette gir myke, runde strøk uten hakkete kanter.
      Tettheten styres av 'spacing' (brøkdel av radius).

    Stabilisering (lazy brush):
      Rå touch-punkter samles i _raw_pts under tegning.
      Glidende gjennomsnitt av siste N punkter gir stabil
      sanntidspreview der N = self.stabilize * 2.
      Ved finger-opp tegnes hele strøket på nytt via Catmull-Rom
      spline-interpolasjon – krokete linjer rettes opp retroaktivt.
      stabilize=0 → ingen effekt. stabilize=10 → maksimal glatthet.
    """

    def __init__(self, **kw):
        super().__init__(allow_stretch=True, keep_ratio=False, **kw)
        self._pil        = PILImage.new('RGB', (CANVAS_W, CANVAS_H), (255, 255, 255))
        self._base       = None    # Snapshot for rubber-band
        self._start      = None    # Startpunkt for shapes
        self._raw_pts    = []      # Alle rå touch-punkter for strøket
        self._stab_pts   = []      # Stabiliserte punkter (glidende snitt)
        self._stroke_base = None   # Canvas-kopi fra start av strøk (for re-tegning)
        self.tool        = 'pen'
        self.draw_color  = '#000000'
        self.size_px     = 6
        self.stabilize   = 4       # 0–10, der 0=av og 10=maks
        self.brush_type  = 'rund'  # rund | myk | kalligrafisk | spray | piksel
        self._history    = []
        self._redo       = []
        self._MAX_HIST   = 20
        self._refresh()

    # ── Koordinater ──────────────────────────────────────────────

    def _kv2pil(self, kx, ky):
        if self.width == 0 or self.height == 0:
            return (0, 0)
        px = int((kx - self.x) / self.width  * CANVAS_W)
        py = int((1.0 - (ky - self.y) / self.height) * CANVAS_H)
        return (max(0, min(CANVAS_W-1, px)), max(0, min(CANVAS_H-1, py)))

    # ── Tekstur ───────────────────────────────────────────────────

    def _refresh(self):
        if not PIL_OK:
            return
        try:
            raw = self._pil.convert('RGBA').tobytes()
            tex = Texture.create(size=(CANVAS_W, CANVAS_H), colorfmt='rgba')
            tex.blit_buffer(raw, colorfmt='rgba', bufferfmt='ubyte')
            tex.flip_vertical()
            self.texture = tex
        except Exception:
            logging.exception('_refresh feil')

    # ── Stabilisering ─────────────────────────────────────────────

    def _moving_avg(self, pts, window):
        """
        Bakover-trekkende glidende gjennomsnitt.
        Hvert utgangspunkt er snittet av de siste 'window' inngangspunktene.
        Brukes BARE under sanntids-tegning der vi ikke har "fremtidige" punkter
        ennå. Asymmetrien gir et synlig hakk i starten ved høy stabilisering,
        derfor bruker vi den sentrerte varianten ved sluttføring av strøk.
        """
        if window <= 1 or len(pts) < 2:
            return list(pts)
        result = []
        for i in range(len(pts)):
            s = max(0, i - window + 1)
            w = pts[s:i+1]
            result.append((
                int(sum(p[0] for p in w) / len(w)),
                int(sum(p[1] for p in w) / len(w)),
            ))
        return result

    def _moving_avg_centered(self, pts, window):
        """
        Sentrert glidende gjennomsnitt med endepunkts-bevaring.

        Vinduet krymper symmetrisk mot endepunktene slik at:
          - smoothed[0]  = raw[0]   (eksakt – ingen midling)
          - smoothed[-1] = raw[-1]  (eksakt – ingen midling)
          - smoothed[i] i midten av strøket = full vindumidling

        Dette er kritisk for lukkede former som sirkler: hvis endepunktene
        ble midlet sammen med naboene, ville begge bli trukket innover mot
        midten av strøket og brukeren fikk et synlig gap mellom start og
        slutt. Slik holdes start- og sluttpunktet eksakt der fingeren var,
        mens midten får full glatting.
        """
        if window <= 1 or len(pts) < 2:
            return list(pts)
        half = window // 2
        N = len(pts)
        result = []
        for i in range(N):
            # Radien er minst av: ønsket halv-vindu, avstand til start,
            # avstand til slutt. Ved i=0 og i=N-1 blir radien 0 og vi
            # bevarer det rå punktet.
            radius = min(half, i, N - 1 - i)
            s = i - radius
            e = i + radius + 1
            w = pts[s:e]
            result.append((
                int(sum(p[0] for p in w) / len(w)),
                int(sum(p[1] for p in w) / len(w)),
            ))
        return result

    def _catmull_rom(self, pts, subdivisions=6):
        """
        Catmull-Rom spline-interpolasjon.
        Genererer 'subdivisions' mellompunkter mellom hvert par av
        kontrollpunkter, noe som gjør krokete touch-sekvenser glatte.
        Fantom-endepunkter legges til slik at kurven berører
        alle originalpunkter.
        """
        if len(pts) < 2:
            return list(pts)
        p = [pts[0]] + list(pts) + [pts[-1]]
        out = []
        for i in range(1, len(p) - 2):
            p0, p1, p2, p3 = p[i-1], p[i], p[i+1], p[i+2]
            for j in range(subdivisions):
                t  = j / subdivisions
                t2 = t * t
                t3 = t2 * t
                x  = int(0.5 * (
                    2*p1[0]
                    + (-p0[0] + p2[0]) * t
                    + (2*p0[0] - 5*p1[0] + 4*p2[0] - p3[0]) * t2
                    + (-p0[0] + 3*p1[0] - 3*p2[0] + p3[0]) * t3
                ))
                y  = int(0.5 * (
                    2*p1[1]
                    + (-p0[1] + p2[1]) * t
                    + (2*p0[1] - 5*p1[1] + 4*p2[1] - p3[1]) * t2
                    + (-p0[1] + 3*p1[1] - 3*p2[1] + p3[1]) * t3
                ))
                out.append((
                    max(0, min(CANVAS_W-1, x)),
                    max(0, min(CANVAS_H-1, y)),
                ))
        out.append(pts[-1])
        return out

    # ── Stempel-pensel ────────────────────────────────────────────

    def _stamp_path(self, pts, col, r, erase=False):
        """
        Maler penselstrøk langs punktliste – penseltype bestemmer utseende.

        rund:         Fylte sirkler. Klassisk, ren strek.
        myk:          Samme som rund men med ufylt Alpha-overlegg –
                      simulert myk kant via ImageFilter.GaussianBlur på
                      en midlertidig RGBA-flate.
        kalligrafisk: Ellipse vridd 45°, bredde/høyde 2:1 –
                      imiterer kalligrafipenn.
        spray:        Tilfeldig fordelte prikker innenfor radius,
                      tetthet synker utover – spraybokse-effekt.
        piksel:       Firkantede stempler, ingen utjevning.
                      Piksel-kunst-estetikk.
        """
        if not pts:
            return
        import random as _rnd
        fill = (255, 255, 255) if erase else col
        d    = ImageDraw.Draw(self._pil)
        r    = max(1, r)
        bt   = 'rund' if erase else self.brush_type

        step = max(1, int(r * (0.5 if bt == 'spray' else 0.35)))
        acc  = 0.0

        def stamp(x, y):
            if bt == 'rund':
                d.ellipse([x-r, y-r, x+r, y+r], fill=fill)

            elif bt == 'myk':
                # Tegn en litt lysere sirkel rundt for myk kant
                outer = max(1, int(r * 1.6))
                # Kjerne
                d.ellipse([x-r, y-r, x+r, y+r], fill=fill)
                # To halvtransparente ringar utover
                a1 = tuple(max(0, int(c * 0.55)) for c in fill) if fill != (255,255,255) else (220,220,220)
                a2 = tuple(max(0, int(c * 0.25)) for c in fill) if fill != (255,255,255) else (240,240,240)
                r2 = max(r+1, int(r*1.3))
                r3 = max(r+2, int(r*1.65))
                d.ellipse([x-r2, y-r2, x+r2, y+r2], fill=a1)
                d.ellipse([x-r3, y-r3, x+r3, y+r3], fill=a2)
                # Tegn kjernen på topp igjen
                d.ellipse([x-r, y-r, x+r, y+r], fill=fill)

            elif bt == 'kalligrafisk':
                # Flat ellipse vridd ~45 grader
                rw = max(1, int(r * 1.8))
                rh = max(1, int(r * 0.55))
                # Rotasjon via polygon
                import math
                ang  = math.radians(45)
                cos_ = math.cos(ang)
                sin_ = math.sin(ang)
                pts4 = [
                    (x + cos_*rw - sin_*(-rh), y + sin_*rw + cos_*(-rh)),
                    (x + cos_*rw - sin_*rh,    y + sin_*rw + cos_*rh),
                    (x - cos_*rw - sin_*rh,    y - sin_*rw + cos_*rh),
                    (x - cos_*rw - sin_*(-rh), y - sin_*rw + cos_*(-rh)),
                ]
                d.polygon([(int(px), int(py)) for px, py in pts4], fill=fill)

            elif bt == 'spray':
                # Tette prikker sentralt, spredt utover
                n_dots = max(6, r * 2)
                for _ in range(n_dots):
                    dist2 = _rnd.gauss(0, r * 0.5)
                    ang2  = _rnd.uniform(0, 6.2832)
                    import math
                    sx = int(x + math.cos(ang2) * dist2)
                    sy = int(y + math.sin(ang2) * dist2)
                    sx = max(0, min(CANVAS_W-1, sx))
                    sy = max(0, min(CANVAS_H-1, sy))
                    dot_r = max(1, r // 4)
                    d.ellipse([sx-dot_r, sy-dot_r, sx+dot_r, sy+dot_r], fill=fill)

            elif bt == 'piksel':
                # Hard firkant – ingen avrunding
                d.rectangle([x-r, y-r, x+r, y+r], fill=fill)

        stamp(*pts[0])
        px, py = pts[0]
        for x, y in pts[1:]:
            dx   = x - px
            dy   = y - py
            dist = (dx*dx + dy*dy) ** 0.5
            acc += dist
            while acc >= step:
                acc -= step
                frac = 1.0 - acc / max(dist, 1)
                sx   = int(px + dx * frac)
                sy   = int(py + dy * frac)
                stamp(sx, sy)
            px, py = x, y

    # ── Touch ─────────────────────────────────────────────────────

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        try:
            pt = self._kv2pil(*touch.pos)
            self._start    = pt
            self._raw_pts  = [pt]
            self._stab_pts = [pt]

            if self.tool == 'fill':
                self._push_history()
                self._do_fill(pt)
                self._refresh()

            elif self.tool in ('pen', 'eraser'):
                self._push_history()
                self._stroke_base = self._pil.copy()
                r = max(1, self.size_px // 2)
                self._stamp_path([pt], self._col(), r,
                                 erase=(self.tool == 'eraser'))
                self._refresh()

            elif self.tool in ('line', 'rect', 'ellipse'):
                self._push_history()
                self._base = self._pil.copy()

        except Exception:
            logging.exception('on_touch_down feil')
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        try:
            pt = self._kv2pil(*touch.pos)

            if self.tool in ('pen', 'eraser'):
                self._raw_pts.append(pt)

                # Sanntids-stabilisering: glidende snitt
                win = max(1, self.stabilize * 2)
                smoothed = self._moving_avg(self._raw_pts, win)
                new_stab = smoothed[len(self._stab_pts):]
                if not new_stab:
                    new_stab = [smoothed[-1]]
                self._stab_pts.extend(new_stab)

                # Tegn bare de nye stemmelpunktene (ikke hele strøket)
                if len(self._stab_pts) >= 2:
                    seg = self._stab_pts[-2:]
                else:
                    seg = self._stab_pts
                r = max(1, self.size_px // 2)
                self._stamp_path(seg, self._col(), r,
                                 erase=(self.tool == 'eraser'))
                self._refresh()

            elif self.tool in ('line', 'rect', 'ellipse') and self._base:
                self._pil = self._base.copy()
                self._draw_shape(self._start, pt)
                self._refresh()

        except Exception:
            logging.exception('on_touch_move feil')
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        try:
            pt = self._kv2pil(*touch.pos)

            if self.tool in ('pen', 'eraser') and self._stroke_base is not None:
                self._raw_pts.append(pt)

                if self.stabilize > 0 and len(self._raw_pts) >= 3:
                    # Post-strøk: gjenopprett canvas-snapshot og
                    # tegn hele strøket på nytt via Catmull-Rom.
                    # Vi bruker sentrert glidende snitt her – symmetrisk,
                    # ingen randeffekt – så strøket ikke får et hakk i starten
                    # ved høy stabilisering.
                    win      = max(1, self.stabilize * 2)
                    smoothed = self._moving_avg_centered(self._raw_pts, win)
                    subs     = max(2, self.stabilize)
                    final    = self._catmull_rom(smoothed, subdivisions=subs)
                    self._pil = self._stroke_base.copy()
                    r = max(1, self.size_px // 2)
                    self._stamp_path(final, self._col(), r,
                                     erase=(self.tool == 'eraser'))
                    self._refresh()

                self._stroke_base = None
                self._raw_pts     = []
                self._stab_pts    = []

            elif self.tool in ('line', 'rect', 'ellipse') and self._base:
                self._pil = self._base.copy()
                self._draw_shape(self._start, pt)
                self._refresh()
                self._base = None

        except Exception:
            logging.exception('on_touch_up feil')
        self._start = None
        return True

    # ── Shapes ───────────────────────────────────────────────────

    def _col(self):
        return (255, 255, 255) if self.tool == 'eraser' else hex_p(self.draw_color)

    def _draw_shape(self, p1, p2):
        if not p1 or not p2:
            return
        d  = ImageDraw.Draw(self._pil)
        x0 = min(p1[0], p2[0]); y0 = min(p1[1], p2[1])
        x1 = max(p1[0], p2[0]); y1 = max(p1[1], p2[1])
        c  = hex_p(self.draw_color)
        w  = max(1, self.size_px)
        if self.tool == 'line':
            # Lines bruker Catmull-Rom mellom to punkter for mykere avslutt
            pts   = [p1, p2]
            final = self._catmull_rom(pts, subdivisions=8)
            self._stamp_path(final, c, w // 2)
        elif self.tool == 'rect':
            d.rectangle([x0, y0, x1, y1], outline=c, width=w)
        elif self.tool == 'ellipse':
            d.ellipse([x0, y0, x1, y1], outline=c, width=w)

    def _do_fill(self, pt):
        try:
            ImageDraw.floodfill(self._pil, pt, hex_p(self.draw_color), thresh=30)
        except Exception:
            logging.exception('_do_fill feil')

    # ── Offentlige metoder ────────────────────────────────────────

    def clear_canvas(self, *_):
        self._push_history()
        self._pil = PILImage.new('RGB', (CANVAS_W, CANVAS_H), (255, 255, 255))
        self._refresh()

    def save_to(self, path):
        self._pil.save(path)

    def load_from(self, path):
        try:
            self._pil = PILImage.open(path).convert('RGB').resize(
                (CANVAS_W, CANVAS_H), PILImage.LANCZOS)
            self._refresh()
        except Exception:
            logging.exception('load_from feil')

    # ── Angre / Gjenta ────────────────────────────────────────────

    def _push_history(self):
        self._history.append(self._pil.copy())
        if len(self._history) > self._MAX_HIST:
            self._history.pop(0)
        self._redo.clear()

    def angre(self, *_):
        if not self._history:
            return
        self._redo.append(self._pil.copy())
        self._pil = self._history.pop()
        self._refresh()

    def gjenta(self, *_):
        if not self._redo:
            return
        self._history.append(self._pil.copy())
        self._pil = self._redo.pop()
        self._refresh()



class GradientColorPicker(Image):
    """
    HSV gradient-fargevelger med PIL.
    Layout (PIL top-to-bottom, flippes til Kivy):
      [Hue-strip 30px] [Gap 3px] [SV-kvadrat 148px] [Gap 3px] [Preview 22px]
    Berøring i hue-stripen setter tone, SV-kvadratet setter metning/lysstyrke.
    on_color(hex_str) kalles ved hver endring.
    """
    PICK_W  = 220
    HUE_H   = 30
    SV_H    = 148
    PREV_H  = 22
    GAP     = 3
    TOTAL_H = 206   # 30+3+148+3+22

    def __init__(self, on_color=None, initial_hex='#FF0000', **kw):
        super().__init__(allow_stretch=True, keep_ratio=False, **kw)
        self._on_color = on_color
        self._grabbed  = None
        import colorsys
        try:
            r = int(initial_hex[1:3], 16) / 255
            g = int(initial_hex[3:5], 16) / 255
            b = int(initial_hex[5:7], 16) / 255
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            self._hue = h; self._sat = s
            self._val = v if v > 0.05 else 1.0
        except Exception:
            self._hue = 0.0; self._sat = 1.0; self._val = 1.0
        self._render()

    @property
    def current_hex(self):
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(self._hue, self._sat, self._val)
        return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

    def _render(self):
        if not PIL_OK:
            return
        import colorsys
        W=self.PICK_W; TH=self.TOTAL_H; HH=self.HUE_H
        SH=self.SV_H;  G=self.GAP
        buf = bytearray(W * TH * 4)
        def sp(x, y, r, g, b):
            i=(y*W+x)*4; buf[i]=r; buf[i+1]=g; buf[i+2]=b; buf[i+3]=255
        # Hue-strip
        for x in range(W):
            r,g,b=colorsys.hsv_to_rgb(x/W,1.0,1.0)
            ri,gi,bi=int(r*255),int(g*255),int(b*255)
            for y in range(HH): sp(x,y,ri,gi,bi)
        hx=int(self._hue*(W-1))
        for y in range(HH):
            for dx in (-2,-1,0,1,2): sp(max(0,min(W-1,hx+dx)),y,255,255,255)
        # Gap etter hue
        for y in range(HH,HH+G):
            for x in range(W): sp(x,y,210,212,220)
        # SV-kvadrat
        sv0=HH+G
        br,bg2,bb=[c*255 for c in colorsys.hsv_to_rgb(self._hue,1.0,1.0)]
        for y in range(SH):
            v=1.0-y/SH
            for x in range(W):
                s=x/W
                sp(x,sv0+y,int((255+(br-255)*s)*v),
                   int((255+(bg2-255)*s)*v),int((255+(bb-255)*s)*v))
        sx=int(self._sat*(W-1)); sy=sv0+int((1-self._val)*(SH-1))
        for dy in range(-7,8):
            for dx in range(-7,8):
                d=(dx*dx+dy*dy)**0.5
                xx=max(0,min(W-1,sx+dx)); yy=max(0,min(TH-1,sy+dy))
                if 5.2<d<7.2:   sp(xx,yy,0,0,0)
                elif 3.8<d<=5.2: sp(xx,yy,255,255,255)
        # Gap etter SV
        p0=HH+G+SH
        for y in range(p0,p0+G):
            for x in range(W): sp(x,y,210,212,220)
        # Forhåndsvisning
        r2,g2,b2=colorsys.hsv_to_rgb(self._hue,self._sat,self._val)
        ri,gi,bi=int(r2*255),int(g2*255),int(b2*255)
        for y in range(p0+G,TH):
            for x in range(W): sp(x,y,ri,gi,bi)
        tex=Texture.create(size=(W,TH),colorfmt='rgba')
        tex.blit_buffer(bytes(buf),colorfmt='rgba',bufferfmt='ubyte')
        tex.flip_vertical(); self.texture=tex

    def _update(self, tx, ty):
        if self.width==0 or self.height==0: return
        W=self.PICK_W; TH=self.TOTAL_H
        px=max(0.0,min(1.0,(tx-self.x)/self.width))
        row=int((1.0-max(0.0,min(1.0,(ty-self.y)/self.height)))*TH)
        if self._grabbed=='hue' or (self._grabbed is None and row<self.HUE_H):
            self._grabbed='hue'; self._hue=px
        elif self._grabbed=='sv' or (self._grabbed is None and
                self.HUE_H+self.GAP<=row<self.HUE_H+self.GAP+self.SV_H):
            self._grabbed='sv'; sv_row=max(0,row-self.HUE_H-self.GAP)
            self._sat=px; self._val=1.0-sv_row/max(1,self.SV_H-1)
        self._render()
        if self._on_color: self._on_color(self.current_hex)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos): return False
        touch.grab(self); self._grabbed=None; self._update(*touch.pos); return True
    def on_touch_move(self, touch):
        if touch.grab_current is not self: return False
        self._update(*touch.pos); return True
    def on_touch_up(self, touch):
        if touch.grab_current is not self: return False
        touch.ungrab(self); self._grabbed=None; return True


def smart_input(text='', hint='', on_save=None, **kw):
    """
    Forbedret TextInput for navn-felt:
    - Markerer all tekst ved fokus → skriv rett over uten å slette manuelt
    - Stor forbokstav (capitalize) ved oppstart
    - on_text_validate (Enter/OK på tastatur) kaller on_save
    - Hintfarge for tom tilstand
    """
    kw.setdefault('multiline',    False)
    kw.setdefault('size_hint_y',  None)
    kw.setdefault('height',       dp(52))
    kw.setdefault('font_size',    sp(16))
    kw.setdefault('padding',      (dp(10), dp(12)))
    kw.setdefault('hint_text',    hint)
    kw.setdefault('hint_text_color', [0.55, 0.55, 0.60, 1])

    # Stor forbokstav på Android
    inp = TextInput(text=text, **kw)
    inp.keyboard_suggestions = True

    def on_focus(widget, focused):
        if focused:
            # Marker alt ved fokus – uansett om det er eksisterende tekst
            Clock.schedule_once(lambda *_: widget.select_all(), 0.05)

    def _capitalize_first(widget, val):
        # Første bokstav stor mens brukeren skriver
        if val and val[0].islower():
            widget.text = val[0].upper() + val[1:]
            # Flytt cursor til slutten
            Clock.schedule_once(
                lambda *_: setattr(widget, 'cursor', (len(widget.text), 0)), 0)

    inp.bind(focus=on_focus)
    inp.bind(text=_capitalize_first)

    if on_save:
        inp.bind(on_text_validate=lambda *_: on_save())

    return inp


# ══════════════════════════════════════════════════════════════════
#  KONFETTI
# ══════════════════════════════════════════════════════════════════

def launch_confetti(duration=3.0):
    """
    Konfetti faller fra TOPPEN av skjermen ned.
    Partikler starter over skjermen (y > H) og faller nedover
    (vy er positiv tyngdekraft, y synker).
    Stor størrelse (20-40px) og full alpha for god synlighet.
    """
    import random as _r
    from kivy.uix.widget import Widget as KWidget
    from kivy.graphics import Color as KC, Rectangle
    W, H = Window.size
    n = 80
    cols = ['#FFD93D','#FF6B6B','#6BCB77','#4D96FF','#C77DFF','#FF9F43','#FF6BB5']
    particles = []
    for _ in range(n):
        particles.append({
            # Start spredt over toppen av skjermen
            'x':   _r.uniform(-20, W + 20),
            'y':   H + _r.uniform(0, H * 0.5),  # Kivy: y=0 er bunn, H er topp
            'vx':  _r.uniform(-3, 3),
            'vy':  _r.uniform(6, 16),            # positiv = oppover i Kivy
            'col': hex_k(_r.choice(cols))[:3],
            'w':   _r.randint(14, 28),
            'h':   _r.randint(8,  18),
            'born': Clock.get_time(),
        })
    overlay = KWidget(size=Window.size, pos=(0, 0))
    Window.add_widget(overlay)
    started = Clock.get_time()
    _ev = [None]

    def update(dt):
        overlay.canvas.clear()
        now   = Clock.get_time()
        alive = False
        with overlay.canvas:
            for p in particles:
                p['y']  -= p['vy']     # faller ned (y synker mot 0)
                p['x']  += p['vx']
                p['vy'] += 0.18        # tyngdekraft – akselererer nedover
                age   = now - p['born']
                # Full synlighet de første 1.2s, deretter fade
                alpha = 1.0 if age < 1.2 else max(0.0, 1.0 - (age-1.2)/(duration-1.2))
                # Stopp ikke før partikkelen er under bunn av skjermen (y < -h)
                if p['y'] > -p['h'] * 3 and alpha > 0:
                    alive = True
                KC(*p['col'], alpha)
                Rectangle(pos=(p['x'], p['y']), size=(p['w'], p['h']))
        if not alive or now - started > duration + 0.3:
            _ev[0].cancel()
            Window.remove_widget(overlay)

    _ev[0] = Clock.schedule_interval(update, 1/50)


# ══════════════════════════════════════════════════════════════════
#  KALENDER-DAGVISNING (redigeringsmodus)
# ══════════════════════════════════════════════════════════════════

class ActivityBlock(BoxLayout):
    """
    En enkelt aktivitets-blokk i CalendarDayView. Stilt med rundet
    bakgrunn og kategorifarge-stripe på venstre kant. Håndterer
    egne touch-events for å skille mellom tap (åpne redigerings-popup)
    og drag (flytte i tid).
    """
    def __init__(self, activity, calendar_view, **kw):
        super().__init__(**kw)
        self.orientation     = 'horizontal'
        self.activity        = activity
        self.calendar        = calendar_view
        self.padding         = (dp(6), dp(4))
        self.spacing         = dp(4)
        # Touch-state for drag-and-drop og long-press
        self._touch_start_x = None
        self._touch_start_y = None
        self._is_dragging   = False
        self._long_press_ev = None
        self._original_y    = 0
        # Bakgrunn (kategori-tonet) + stripe
        cat = get_category(calendar_view.app.data, activity.get('category'))
        if cat:
            cr, cg, cb, _ = hex_k(cat['color'])
            bg = (0.85 + cr*0.15, 0.88 + cg*0.12, 0.96 + cb*0.04, 0.95)
            stripe_col = hex_k(cat['color'])
        else:
            bg = (0.78, 0.86, 0.96, 0.95)
            stripe_col = hex_k('#4D96FF')
        from kivy.graphics import Color as KColor, RoundedRectangle, Rectangle
        with self.canvas.before:
            KColor(*bg)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size,
                                              radius=[dp(8)])
            KColor(*stripe_col)
            self._stripe = Rectangle(pos=self.pos, size=(dp(4), self.height))
        self.bind(pos=self._redraw, size=self._redraw)
        # Tekst-etikett – navn på en linje, tid på neste hvis høyt nok
        self._lbl = Label(
            text=self._make_label_text(),
            font_size=fsp(12), color=(0.04, 0.10, 0.36, 1),
            halign='left', valign='top',
            markup=False,
        )
        self._lbl.bind(size=self._update_text_size)
        self.add_widget(Widget(size_hint_x=None, width=dp(4)))  # stripe-spacer
        self.add_widget(self._lbl)

    def _make_label_text(self):
        start = self.activity.get('start', '')
        end   = self.activity.get('end',   '')
        name  = self.activity.get('name',  '')
        return f'{name}\n{start} – {end}'

    def _update_text_size(self, lbl, sz):
        lbl.text_size = (sz[0] - dp(6), sz[1])

    def _redraw(self, *_):
        self._bg_rect.pos  = self.pos
        self._bg_rect.size = self.size
        self._stripe.pos   = self.pos
        self._stripe.size  = (dp(4), self.height)

    # ── Touch ───────────────────────────────────────────────────────
    # Long-press for å gå inn i drag-modus. Korte tap åpner
    # redigerings-popup. Sveip = scroll i parent ScrollView. Slik
    # konkurrerer ikke drag-gesten med scrolling.
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        # Lagre startposisjon og start 300 ms timer for å aktivere drag.
        self._touch_start_x = touch.x
        self._touch_start_y = touch.y
        self._is_dragging   = False
        self._long_press_ev = Clock.schedule_once(
            lambda *_: self._activate_drag(touch), 0.3)
        # Ikke grip touch ennå – lar ScrollView håndtere scroll inntil
        # vi eventuelt aktiverer drag-modus.
        return False

    def _activate_drag(self, touch):
        """Etter long-press: gå inn i drag-modus og grip touch."""
        # Hvis brukeren allerede har sluppet fingeren, hopp over
        if self._long_press_ev is None:
            return
        self._is_dragging   = True
        self._original_y    = self.y
        touch.grab(self)
        # Visuell tilbakemelding: lett opacity-endring og litt løft
        Animation(opacity=0.85, duration=0.10).start(self)
        # Tilbake-skyv litt opp så det er åpenbart blokken er "tatt"
        self._long_press_ev = None

    def on_touch_move(self, touch):
        if self._long_press_ev is not None:
            # Drag-aktivering pågår – sjekk om brukeren beveger fingeren
            # før timeren fyrer. Hvis ja, kanseller drag og la scroll skje.
            dx = abs(touch.x - self._touch_start_x)
            dy = abs(touch.y - self._touch_start_y)
            if dx > dp(10) or dy > dp(10):
                self._long_press_ev.cancel()
                self._long_press_ev = None
            return False
        if touch.grab_current is not self:
            return False
        if self._is_dragging:
            new_y = max(0, min(self.calendar.height - self.height,
                               self._original_y + (touch.y - self._touch_start_y)))
            self.y = new_y
            return True
        return False

    def on_touch_up(self, touch):
        if self._long_press_ev is not None:
            self._long_press_ev.cancel()
            self._long_press_ev = None
            # Rask tap (uten langt trykk) – åpne redigerings-popup
            if (self.collide_point(*touch.pos)
                and abs(touch.x - self._touch_start_x) < dp(10)
                and abs(touch.y - self._touch_start_y) < dp(10)):
                self.calendar.app._dr_entry_popup(self.activity)
                return True
            return False
        if touch.grab_current is self:
            touch.ungrab(self)
            if self._is_dragging:
                Animation(opacity=1.0, duration=0.10).start(self)
                self.calendar._commit_block_move(self)
                self._is_dragging = False
                return True
        return False


class CalendarDayView(FloatLayout):
    """
    Vertikal tidsakse med aktiviteter som flyttbare fargede blokker.
    Brukes i redigeringsmodus istedenfor liste-visningen. Tap åpner
    redigering, drag flytter aktiviteten i tid (snap til 5 min).

    Tidsakse: H_START til H_END (06–23 dekker en typisk barnehage-dag
    inkludert ettermiddag, men kan utvides hvis behov).
    """
    HOUR_PX  = None  # settes i __init__ for å bruke dp()
    H_START  = 6
    H_END    = 23

    def __init__(self, app, day_code, activities, **kw):
        super().__init__(**kw)
        self.HOUR_PX     = dp(64)
        self.app         = app
        self.day_code    = day_code
        self.activities  = list(activities)
        self.size_hint_y = None
        self.height      = (self.H_END - self.H_START) * self.HOUR_PX + dp(12)
        self._gutter     = dp(36)   # bredde på time-etiketts-kolonnen
        self._build()

    def _build(self):
        from kivy.graphics import Color as KColor, Line as KLine, Rectangle
        # Bakgrunns-rutenett – horisontale linjer for hver time
        with self.canvas.before:
            KColor(0.97, 0.97, 0.99, 1)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
            KColor(0.85, 0.86, 0.92, 1)
            self._hour_lines = []
            for h in range(self.H_START, self.H_END + 1):
                self._hour_lines.append(KLine(width=0.7))
            # Halv-time-linjer (lysere)
            KColor(0.92, 0.93, 0.97, 1)
            self._half_lines = []
            for h in range(self.H_START, self.H_END):
                self._half_lines.append(KLine(width=0.5))
            # "Nå"-linje (rød) – kun for i dag
            self._now_line = None
            if self.day_code == today_code():
                KColor(0.93, 0.25, 0.20, 1)
                self._now_line = KLine(width=1.5)
        self.bind(pos=self._redraw_grid, size=self._redraw_grid)

        # Time-etiketter
        self._hour_labels = []
        for h in range(self.H_START, self.H_END + 1):
            lbl = Label(
                text=f'{h:02d}', font_size=fsp(11),
                color=(0.4, 0.42, 0.55, 1),
                size_hint=(None, None), size=(dp(30), dp(20)),
                halign='right', valign='top',
            )
            lbl.bind(size=lbl.setter('text_size'))
            self.add_widget(lbl)
            self._hour_labels.append((h, lbl))

        # Aktivitets-blokker
        self._blocks = []
        for act in self.activities:
            self._add_block(act)

        # Plasser alt ved første layout
        self.bind(size=lambda *_: self._layout(),
                  pos=lambda  *_: self._layout())
        Clock.schedule_once(lambda *_: self._layout(), 0)

    def _redraw_grid(self, *_):
        x0 = self.x + self._gutter
        x1 = self.right - dp(4)
        self._bg_rect.pos  = self.pos
        self._bg_rect.size = self.size
        for i, h in enumerate(range(self.H_START, self.H_END + 1)):
            y = self._time_to_y(h, 0)
            self._hour_lines[i].points = [x0, y, x1, y]
        for i, h in enumerate(range(self.H_START, self.H_END)):
            y = self._time_to_y(h, 30)
            self._half_lines[i].points = [x0 + dp(10), y, x1, y]
        # Nå-linje
        if self._now_line is not None:
            now = datetime.now()
            ny = self._time_to_y(now.hour, now.minute)
            self._now_line.points = [self.x + dp(2), ny, x1, ny]

    def _time_to_y(self, hour, minute):
        """Konverterer (hour, minute) til absolutt Y i widget-koordinater."""
        offset_min = (hour - self.H_START) * 60 + minute
        return self.top - dp(8) - (offset_min / 60) * self.HOUR_PX

    def _y_to_time(self, y, snap=5):
        """Konverterer Y til (hour, minute), snappet til 5-min-grid."""
        offset_px = (self.top - dp(8)) - y
        total_min = (offset_px / self.HOUR_PX) * 60
        if snap:
            total_min = round(total_min / snap) * snap
        total_min = max(0, min((self.H_END - self.H_START) * 60, total_min))
        h = self.H_START + int(total_min // 60)
        m = int(total_min % 60)
        return (h, m)

    def _add_block(self, act):
        block        = ActivityBlock(activity=act, calendar_view=self,
                                      size_hint=(None, None))
        block.act_id = act.get('id')
        self.add_widget(block)
        self._blocks.append(block)

    def _layout(self):
        """Plasserer time-etiketter og aktivitets-blokker."""
        for h, lbl in self._hour_labels:
            y = self._time_to_y(h, 0)
            lbl.pos = (self.x, y - dp(10))
        x0 = self.x + self._gutter
        block_width = max(dp(80), self.width - self._gutter - dp(8))
        for block in self._blocks:
            act = block.activity
            try:
                sh, sm = (int(p) for p in act['start'].split(':'))
                eh, em = (int(p) for p in act['end'].split(':'))
            except Exception:
                continue
            y_top = self._time_to_y(sh, sm)
            y_bot = self._time_to_y(eh, em)
            block.size = (block_width, max(dp(28), y_top - y_bot))
            block.pos  = (x0, y_bot)
            # Original-Y brukes som referanse for drag
            block._original_y = block.y
        self._redraw_grid()

    def _commit_block_move(self, block):
        """Beregner ny start/slutt fra blokkens nåværende Y, snapper og lagrer."""
        try:
            sh, sm = (int(p) for p in block.activity['start'].split(':'))
            eh, em = (int(p) for p in block.activity['end'].split(':'))
        except Exception:
            return
        duration_min = (eh*60 + em) - (sh*60 + sm)
        # Blokkens nedre kant = sluttid, øvre kant = starttid
        new_start_h, new_start_m = self._y_to_time(block.top, snap=5)
        new_total_start = new_start_h * 60 + new_start_m
        new_total_end   = new_total_start + duration_min
        # Sørg for at slutt ikke faller utenfor tidsaksen
        if new_total_end > self.H_END * 60:
            new_total_end   = self.H_END * 60
            new_total_start = new_total_end - duration_min
        new_eh = new_total_end // 60
        new_em = new_total_end %  60
        block.activity['start'] = f'{new_start_h:02d}:{new_start_m:02d}'
        block.activity['end']   = f'{new_eh:02d}:{new_em:02d}'
        # Oppdater datastruktur og lagre
        save_struct(self.app.data)
        Clock.schedule_once(lambda *_: _update_widget(self.app.data), 0.2)
        # Re-layout for å snappe blokken til riktig posisjon
        self._layout()


# ══════════════════════════════════════════════════════════════════
#  HOVED-APP
# ══════════════════════════════════════════════════════════════════

class KommunikasjonstavleApp(App):

    # ── Oppstart ──────────────────────────────────────────────────

    @property
    def is_hc_mode(self):
        """KV-tilgjengelig egenskap for høykontrast-modus."""
        return bool(self.data.get('settings', {}).get('high_contrast', False))             if hasattr(self, 'data') else False

    # ══════════════════════════════════════════════════
    #  SPLASH OVERLAY
    # ══════════════════════════════════════════════════

    def _show_splash_overlay(self):
        """android.presplash i buildozer.spec håndterer splash."""
        pass

    def _toggle_confetti_btn(self, enable):
        """
        Viser/skjuler vedvarende konfetti-knapp.
        Bruker mk_btn direkte – den pålitelige løsningen i denne appen.
        Knappen legges til Window og posisjoneres manuelt.
        """
        self._confetti_btn_visible = enable
        if enable:
            if self._confetti_btn_widget:
                return
            S  = dp(58)
            M  = dp(12)
            WW, WH = Window.size
            btn = mk_btn(
                'Konfetti',
                hex_k('#FF6B6B'),
                h=S, fs=12,
                size_hint=(None, None),
                width=S,
            )
            # Plasser under tittellinjen (46dp fra topp) med litt marg
            btn.pos = (WW - S - M, WH - dp(46) - S - M)
            btn.bind(on_release=lambda *_: launch_confetti(3.0))
            Window.add_widget(btn)
            self._confetti_btn_widget = btn
        else:
            if self._confetti_btn_widget:
                Window.remove_widget(self._confetti_btn_widget)
                self._confetti_btn_widget = None

    def _init_bundled_assets(self):
        """
        Kopierer bilder bundlet i APK-en (assets/bilder/<Mappenavn>/*.png/jpg)
        til appens IMG_DIR og oppretter tilsvarende bildetavle-mapper i
        structure.json.

        Øk BUNDLE_VERSION når du legger til/endrer bilder i assets/-mappen
        for å tvinge re-import ved neste APK-oppdatering.

        Kjøres alltid ETTER load_struct() slik at self.data er tilgjengelig
        og bundled_version-sjekken fungerer korrekt.
        """
        BUNDLE_VERSION = 4   # ← økt til 4: reparerer mojibake i mappenavn (æøå)

        # ── Reparer mojibake i ALLEREDE importerte mappenavn ─────────────
        # Kjøres FØR versjonssjekken slik at "Måltid" (lagret som mangled
        # navn av en tidligere BUNDLE_VERSION) repareres selv om
        # bundled_version allerede er satt til en høyere/lik verdi senere.
        # Idempotent: navn uten mojibake returneres uendret av _fix_mojibake.
        _renamed = False
        for _f in self.data.get('folders', []):
            _orig = _f.get('name', '')
            _fixed = _fix_mojibake(_orig)
            if _fixed != _orig:
                diag(f'MOJIBAKE_FIX: "{_orig}" → "{_fixed}"')
                logging.info('bundled assets: reparerte mappenavn "%s" → "%s"',
                             _orig, _fixed)
                _f['name'] = _fixed
                _renamed = True
        if _renamed:
            save_struct(self.data, immediate=True)

        # ── Sjekk om dette allerede er gjort ────────────────────────
        done_ver = self.data.get('settings', {}).get('bundled_version', 0)
        if done_ver >= BUNDLE_VERSION:
            logging.debug('bundled assets: versjon %d allerede importert', done_ver)
            return

        # ── Finn assets/bilder/-mappen – prøv alle kjente Android-stier ──
        # På Android (p4a/Buildozer) hentes stier fra flere kilder fordi
        # __file__ og self.directory ikke alltid er identiske.
        app_dirs = []
        try:
            app_dirs.append(os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            pass
        try:
            app_dirs.append(self.directory)
        except Exception:
            pass
        try:
            from kivy import kivy_data_dir as _kdd
            app_dirs.append(os.path.dirname(_kdd))
        except Exception:
            pass
        # Android-spesifikk: p4a legger alltid app-filer her
        pkg = 'no.askapp.kommunikasjonstavle'
        for base in [f'/data/user/0/{pkg}/files/app',
                     f'/data/data/{pkg}/files/app']:
            app_dirs.append(base)

        assets_root = None
        for d in app_dirs:
            cand = os.path.join(d, 'assets', 'bilder')
            logging.debug('bundled assets: prøver sti %s → finnes=%s', cand, os.path.isdir(cand))
            if os.path.isdir(cand):
                assets_root = cand
                break

        if not assets_root:
            diag(f'ASSETS_ROOT IKKE FUNNET – prøvde: {[os.path.join(d, "assets", "bilder") for d in app_dirs[:3]]}')
            logging.warning('bundled assets: ingen assets/bilder/-mappe funnet. '
                            'Prøvde: %s', [os.path.join(d, 'assets', 'bilder') for d in app_dirs])
            return

        diag(f'ASSETS_ROOT={assets_root}')
        logging.info('bundled assets: bruker rot %s', assets_root)

        # Logg innholdet av IMG_DIR ved start av import-løkken – avgjørende
        # for å skille om filene var der fra før eller ble kopiert nå.
        try:
            imgdir_at_start = sorted(os.listdir(IMG_DIR))
        except Exception:
            imgdir_at_start = ['(listdir feilet)']
        diag(f'IMG_DIR ved init-start ({len(imgdir_at_start)} filer): {imgdir_at_start[:10]}')

        # ── Importer mapper og bilder ────────────────────────────────
        imported_folders = 0
        imported_images  = 0
        failed_images    = 0

        for folder_name_raw in sorted(os.listdir(assets_root)):
            src_folder = os.path.join(assets_root, folder_name_raw)
            if not os.path.isdir(src_folder):
                continue

            # folder_name_raw kan inneholde mojibake (se _fix_mojibake) –
            # brukes KUN til filsystem-operasjoner (os.path.join/isdir),
            # siden det er den faktiske strengen filsystemet returnerte.
            # folder_name er den reparerte, korrekte visningsstrengen som
            # lagres i structure.json og brukes til matching mot
            # eksisterende mapper.
            folder_name = _fix_mojibake(folder_name_raw)
            if folder_name != folder_name_raw:
                diag(f'MOJIBAKE_FIX (assets): "{folder_name_raw}" → "{folder_name}"')

            # Finn eller opprett mappe i structure.json
            existing = next(
                (f for f in self.data.get('folders', [])
                 if f.get('name', '').lower() == folder_name.lower()),
                None)
            if not existing:
                color_idx = imported_folders % len(FOLDER_COLORS)
                existing = {
                    'id':         str(uuid.uuid4()),
                    'name':       folder_name,
                    'color':      FOLDER_COLORS[color_idx],
                    'image':      None,
                    'items':      [],
                    'subfolders': [],
                    'opens':      0,
                }
                self.data.setdefault('folders', []).append(existing)
                imported_folders += 1
                diag(f'NY_MAPPE opprettet: "{folder_name}"')
                logging.info('bundled assets: opprettet mappe "%s"', folder_name)

            # Bygg sett av allerede importerte filnavn
            # Inkluder kun items der bildet faktisk finnes på disk.
            existing_imgs = {
                os.path.basename(it.get('image', ''))
                for it in existing.get('items', [])
                if it.get('image') and os.path.exists(it['image'])
            }
            # Fjern items med manglende bildefiler fra mappen (reparasjon)
            before = len(existing.get('items', []))
            existing['items'] = [
                it for it in existing.get('items', [])
                if not it.get('image') or os.path.exists(it['image'])
            ]
            removed = before - len(existing['items'])
            diag(f'MAPPE "{folder_name}": items_før={before} fjernet={removed} '
                 f'existing_imgs={sorted(existing_imgs)}')
            if removed:
                logging.info('bundled assets: fjernet %d items med manglende bilder fra "%s"',
                             removed, folder_name)

            for img_file in sorted(os.listdir(src_folder)):
                if not img_file.lower().endswith(
                        ('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    continue

                if img_file in existing_imgs:
                    diag(f'SKIP_EXISTING_IMG {img_file} (allerede i mappen med gyldig sti)')
                    logging.debug('bundled assets: %s allerede importert, hopper over', img_file)
                    continue

                src_path = os.path.join(src_folder, img_file)
                dst_path = os.path.join(IMG_DIR, img_file)

                # Kopier bare hvis kildefilen faktisk finnes
                if not os.path.exists(src_path):
                    diag(f'SRC_MISSING {img_file} → src={src_path}')
                    logging.warning('bundled assets: kildefil finnes ikke: %s', src_path)
                    failed_images += 1
                    continue

                try:
                    newly_copied = False
                    if not os.path.exists(dst_path):
                        newly_copied = True
                        t_copy = time.time()
                        # Bruker shutil.copyfile (KUN rådata, ingen metadata) i stedet
                        # for shutil.copy2 (som kopierer tidsstempler via os.utime og
                        # rettigheter via os.chmod). På Android feiler os.utime() for
                        # filer ekstrahert fra APK-bunten, selv om dataene kopieres
                        # korrekt. shutil.copy2 tolker dette som en full feil, kaster
                        # exception ETTER at filen er skrevet til disk, og den ytre
                        # except-blokken hindrer item-tillegg – selv om bildet er
                        # tilgjengelig. shutil.copyfile unngår dette helt.
                        shutil.copyfile(src_path, dst_path)
                        size_after = os.path.getsize(dst_path) if os.path.exists(dst_path) else -1
                        try:
                            with open(dst_path, 'rb') as _f:
                                os.fsync(_f.fileno())
                            fsync_ok = True
                        except Exception as _fe:
                            fsync_ok = False
                            diag(f'COPY fsync FEIL {img_file}: {_fe}')
                        diag(f'COPY {"OK" if size_after > 0 else "TOMT"} {img_file} '
                             f'size={size_after}B fsync={fsync_ok} '
                             f't={time.time()-t_copy:.3f}s')
                        logging.debug('bundled assets: kopiert %s → %s', src_path, dst_path)
                    else:
                        try:
                            fsize = os.path.getsize(dst_path)
                        except Exception:
                            fsize = -1
                        diag(f'ALREADY_EXISTS {img_file} size={fsize}B')
                        logging.debug('bundled assets: %s finnes allerede i IMG_DIR (size=%d)',
                                      img_file, fsize)

                    if newly_copied and not os.path.exists(dst_path):
                        diag(f'VERIFY_FAIL {img_file} – ny kopi finnes ikke etter skriving!')
                        logging.error('bundled assets: kopiering feilet – dst finnes ikke: %s',
                                      dst_path)
                        failed_images += 1
                        continue

                    name = os.path.splitext(img_file)[0].replace('_', ' ')
                    existing.setdefault('items', []).append({
                        'id':    str(uuid.uuid4()),
                        'name':  name,
                        'image': dst_path,
                    })
                    imported_images += 1
                    diag(f'ITEM_ADDED {img_file} → mappe="{existing["name"]}"')
                except Exception as copy_err:
                    diag(f'COPY_EXCEPTION {img_file}: {type(copy_err).__name__}: {copy_err}')
                    logging.error('bundled assets: kopiering feilet for %s: %s',
                                  img_file, copy_err)
                    failed_images += 1

        logging.info('bundled assets: %d mapper, %d bilder importert, %d feilet',
                     imported_folders, imported_images, failed_images)

        # ── Synkroniser mappeliste ────────────────────────────────────────
        # Behold mapper som enten finnes i assets/bilder/ (bundlede)
        # eller har innhold (brukeren har lagt til items).
        # Tomme mapper med ukjent opprinnelse fjernes – disse er artefakter
        # fra DEFAULT_STRUCT, eldre app-versjoner eller debug-kjøringer.
        bundled_names = {
            _fix_mojibake(n).lower() for n in os.listdir(assets_root)
            if os.path.isdir(os.path.join(assets_root, n))
        }
        before_sync = len(self.data.get('folders', []))
        self.data['folders'] = [
            f for f in self.data.get('folders', [])
            if f.get('name', '').lower() in bundled_names
            or f.get('items')
        ]
        removed_sync = before_sync - len(self.data['folders'])
        if removed_sync:
            diag(f'SYNC: fjernet {removed_sync} tomme mapper utenfor bunten')
            logging.info('bundled assets: ryddet opp %d foreldreløse mapper', removed_sync)

        # Merk som ferdig KUN hvis minst ett bilde ble importert ELLER
        # det ikke fantes noen bilder å importere (assets-mappen er tom).
        total_in_assets = sum(
            1 for fn in os.listdir(assets_root) if os.path.isdir(os.path.join(assets_root, fn))
            for f in os.listdir(os.path.join(assets_root, fn))
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))
        )
        if failed_images == 0 or imported_images > 0:
            self.data.setdefault('settings', {})['bundled_version'] = BUNDLE_VERSION
        elif total_in_assets == 0:
            # Ingen bilder å importere – sett versjon så vi ikke prøver igjen
            self.data.setdefault('settings', {})['bundled_version'] = BUNDLE_VERSION

        save_struct(self.data, immediate=True)

    def build(self):
        setup_logging()
        Window.clearcolor = time_of_day_tint()
        Window.softinput_mode = 'below_target'  # Skyv innhold over tastatur

        # Periodisk oppdatering av tid-av-døgn-fargetone. Hver halvtime sjekker
        # vi om bakgrunnen bør skiftes til neste tidsbånd. Subtilt nok til at
        # brukeren ikke merker selve overgangen.
        def _refresh_tint(*_):
            if self._cur_scr == 'image':
                return  # adaptiv bakgrunn på bildeskjermen overstyrer
            if is_hc():
                return  # høykontrast overstyrer
            Window.clearcolor = time_of_day_tint()
        Clock.schedule_interval(_refresh_tint, 1800)

        # Sett ALLE datastier fra user_data_dir – alltid skrivbar
        # uten tillatelser på alle Android-versjoner.
        global DATA_DIR, IMG_DIR, DRAW_DIR, STRUCT_FILE, LOG_FILE, DIAG_FILE, _DIAG_SESSION
        DATA_DIR    = self.user_data_dir
        IMG_DIR     = os.path.join(DATA_DIR, 'images')
        DRAW_DIR    = os.path.join(DATA_DIR, 'drawings')
        STRUCT_FILE = os.path.join(DATA_DIR, 'structure.json')
        LOG_FILE    = os.path.join(DATA_DIR, 'crash.log')
        DIAG_FILE   = os.path.join(DATA_DIR, 'diag.log')

        for d in [DATA_DIR, IMG_DIR, DRAW_DIR, DOWNLOAD_DIR]:
            os.makedirs(d, exist_ok=True)

        self.data        = load_struct()

        # ── Sesjonsnummer – brukes i diagnoseloggen ───────────────
        _DIAG_SESSION = self.data.get('settings', {}).get('run_count', 0) + 1
        self.data.setdefault('settings', {})['run_count'] = _DIAG_SESSION

        diag_section(f'SESJON #{_DIAG_SESSION} – APP START')
        diag(f'PIL_OK={PIL_OK}  DATA_DIR={DATA_DIR}')
        diag(f'Window={Window.width}×{Window.height}px  '
             f'IMG_DIR_items={len(os.listdir(IMG_DIR)) if os.path.isdir(IMG_DIR) else "?"}')
        diag(f'structure.json: {len(self.data.get("folders",[]))} mapper, '
             f'bundled_version={self.data.get("settings",{}).get("bundled_version","(ingen)")}')

        # Aktiver HC-modus hvis det var aktivert ved forrige kjøring
        if self.data.get('settings', {}).get('high_contrast', False):
            apply_high_contrast(True)

        # Kopier bundlede bilder (fra repo assets/) til IMG_DIR.
        # Kjøres etter load_struct() så self.data er satt og
        # bundled_version-sjekken fungerer korrekt.
        diag('build() → kaller _init_bundled_assets()')
        t_assets = time.time()
        self._init_bundled_assets()
        diag(f'build() → _init_bundled_assets() ferdig t={time.time()-t_assets:.3f}s '
             f'IMG_DIR_items={len(os.listdir(IMG_DIR))}')

        self.nav_stack   = []
        self.cur_folder  = None
        self.edit_mode   = False
        self.draw_canvas = None
        self._cur_scr    = 'home'
        self._next_slide_dir = 'forward'  # slide-retning for neste _set_content
        # Fase 1 – landskapsstøtte: husk gjeldende retning slik at
        # _on_window_resize kun trigger ombygging VED FAKTISK
        # retningsskifte (ikke for hver minste resize/tastatur-endring).
        self._is_landscape = is_landscape()

        root = BoxLayout(orientation='vertical')
        # Tittellinje øverst (slim, ikke-interaktiv, mørk)
        self._bottombar = self._build_bottombar()
        root.add_widget(self._bottombar)
        # Hurtigrad rett under tittellinje
        self._quickbar = self._build_quickbar()
        root.add_widget(self._quickbar)
        # Innholdsflate i midten (tar all gjenværende plass)
        # ── Lagdeling for FAB (flytende søkeknapp) ──────────────────
        # self._content = ytre, PERSISTENT FloatLayout – tømmes ALDRI.
        #   Inneholder to lag:
        #     1. self._content_inner – det _set_content() faktisk
        #        tømmer/fyller for hver skjerm.
        #     2. self._fab – flytende søkeknapp, ligger alltid OVENPÅ
        #        skjerminnholdet (lagt til etter _content_inner →
        #        tegnes sist → øverst).
        # pos_hint={'x':0,'y':0} er nødvendig: FloatLayout endrer ikke
        # child.pos uten pos_hint, så uten dette ville _content_inner
        # arvet (0,0) i vindu-koordinater i stedet for _content sin
        # faktiske posisjon (over navigasjonsbaren).
        self._content = FloatLayout()
        root.add_widget(self._content)

        self._content_inner = FloatLayout(size_hint=(1, 1),
                                           pos_hint={'x': 0, 'y': 0})
        self._content.add_widget(self._content_inner)

        self._fab = self._build_fab()
        self._content.add_widget(self._fab)
        # Navigasjonsbar NEDERST for énhånds-bruk på store telefoner
        self._navbar = self._build_navbar()
        root.add_widget(self._navbar)

        diag('build() → kaller _show_home()')
        self._show_home()
        # Widget-oppdatering – pakket inn i try/except
        def _safe_widget_start(*_):
            try:
                if hasattr(self, 'data') and isinstance(self.data, dict):
                    _update_widget(self.data)
            except Exception as e:
                logging.warning('widget start feilet: %s', e)
        def _safe_alarm(*_):
            try:
                _schedule_widget_alarm()
            except Exception as e:
                logging.warning('alarm feilet: %s', e)
        # Forsink til etter splash (5 sek) så data er garantert lastet
        Clock.schedule_once(_safe_widget_start, 5.0)
        self._widget_tick = Clock.schedule_interval(
            lambda *_: Clock.schedule_once(_safe_widget_start, 0), 60)
        # AlarmManager setter seg selv opp via KtWidget.onEnabled –
        # kaller _schedule_widget_alarm kun som backup
        Clock.schedule_once(_safe_alarm, 6.0)
        # Bind tilbake-knapp (ESC / Android Back)
        Window.bind(on_keyboard=self.on_keyboard)
        # Fase 1 – landskapsstøtte: rebygg gjeldende skjerm når retningen
        # faktisk skifter (portrett ↔ liggende), slik at rutenett (4→6
        # kolonner) og rdp()-skalering oppdateres. p4a sin PythonActivity
        # deklarerer configChanges som inkluderer "orientation|screenSize",
        # så Activity blir IKKE ødelagt/gjenskapt ved rotasjon – Window
        # får bare en on_resize-hendelse, og widget-treet må selv reagere.
        Window.bind(on_resize=self._on_window_resize)
        # Vis splash-overlay i 2 sekunder etter oppstart
        Clock.schedule_once(lambda *_: self._show_splash_overlay(), 0.1)
        self._confetti_btn_visible = False
        self._confetti_btn_widget  = None
        # Tillatelsesforespørsel fra build() – samme mønster som Eldritch Portal.
        Clock.schedule_once(lambda dt: request_android_permissions(), 0.5)
        return root

    # ══════════════════════════════════════════════════
    #  ANDROID-TILLATELSER
    #
    #  Android 6+ (API 23+) krever at "farlige" tillatelser
    #  (lagring, bilder) bes om eksplisitt under kjøring,
    #  selv om de er deklarert i AndroidManifest.xml.
    #  Uten dette vil FileChooser vise mapper men ingen bilder.
    #
    #  Vi bruker READ_MEDIA_IMAGES (Android 13+) som ber om
    #  tilgang til bilder spesifikt – en langt mer passende
    #  dialog enn den inngripende MANAGE_EXTERNAL_STORAGE.
    # ══════════════════════════════════════════════════

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        """
        Fanger Androids tilbake-knapp (keycode 27 = ESC = Android Back).
        Navigerer tilbake i appen i stedet for å lukke den.
        Dersom vi er på hjemskjermen og nav_stack er tom, lukkes appen normalt.
        """
        if key == 27:   # ESC / Android Back
            if self.nav_stack:
                self.go_back()
                return True   # konsumér – hindrer app-lukking
            elif self._cur_scr != 'home':
                self.go_home()
                return True
            else:
                return False  # hjemskjerm + tom stack → lukk appen
        return False

    def on_pause(self):
        # IKKE lukk popup-er – bildevelgeren sender appen til bakgrunn
        # og da ville aktivitets-popup-en forsvinne
        save_struct(self.data, immediate=True)
        self._write_app_state(False)   # appen er i bakgrunnen
        return True

    def on_resume(self):
        self._write_app_state(True)    # appen er i forgrunnen igjen
        def _safe(*_):
            try:
                if hasattr(self, 'data') and isinstance(self.data, dict):
                    _update_widget(self.data)
            except Exception as e:
                logging.warning('resume widget: %s', e)
        Clock.schedule_once(_safe, 0.5)

    def on_start(self):
        """
        Sjekker om appen ble åpnet via Share intent (delt bilde fra Galleri).
        Binder også on_new_intent for å fange deling mens appen kjører.
        Viser onboarding-omvisningen for nye brukere første gang.
        """
        self._write_app_state(True)   # appen er i forgrunnen

        # Onboarding: kort delay så hjemskjermen rekker å rendres først,
        # ellers ser det rart ut at popup-en dukker opp før appen.
        Clock.schedule_once(self._maybe_show_onboarding, 0.6)

        # Første oppstart: _init_bundled_assets() kopierer bilder til IMG_DIR
        # i build(), men filsystemet på Android kan bufre skrivene. En stille
        # re-render 0,4 s etter oppstart sikrer at «Akkurat nå»-kortet og
        # andre bilder lastes inn korrekt uten at brukeren ser noen animasjon.
        def _silent_home_refresh(dt):
            if self._cur_scr == 'home':
                self._show_home(animate=False)
        Clock.schedule_once(_silent_home_refresh, 0.4)

        # Planlegg dagsplan-varsler basert på dagens plan, og be om
        # POST_NOTIFICATIONS-tillatelse (kreves på Android 13+).
        Clock.schedule_once(lambda *_: self._reschedule_dagsplan_notifs(), 1.0)
        Clock.schedule_once(lambda *_: self._request_notification_permission(), 2.0)

        if platform == 'android':
            try:
                from android import mActivity
                from android.activity import bind as activity_bind
                # Sjekk startintenten (appen var ikke i forgrunnen)
                intent = mActivity.getIntent()
                _handle_share_intent(intent)
                # Bind for fremtidige intents (appen er allerede åpen)
                activity_bind(on_new_intent=lambda intent: (
                    _handle_share_intent(intent),
                    Clock.schedule_once(lambda *_: self._process_shared_image(), 0.3),
                ))
                # Behandle eventuelt ventende Share-bilde fra oppstart
                if _SHARE_PENDING[0]:
                    Clock.schedule_once(lambda *_: self._process_shared_image(), 0.8)
            except Exception as e:
                _plog(f'on_start share-sjekk feil: {e}')

    # _request_android_permissions() er erstattet av modul-nivå-funksjonen
    # request_android_permissions() øverst i filen – se der.

    def _process_shared_image(self):
        """
        Behandler et bilde mottatt via Share intent.
        Kopierer bildet til IMG_DIR og ber brukeren velge hvilken mappe
        det skal legges i – viser en enkel mappevelger-popup.
        """
        uri = _SHARE_PENDING[0]
        if not uri:
            return
        _SHARE_PENDING[0] = None

        _plog('_process_shared_image: behandler delt bilde')
        try:
            # Finn filnavn fra URI
            fname = 'delt_bilde_' + str(uuid.uuid4())[:8] + '.jpg'
            try:
                from jnius import autoclass
                from android import mActivity
                OpenableColumns = autoclass('android.provider.OpenableColumns')
                cursor = mActivity.getContentResolver().query(
                    uri, None, None, None, None)
                if cursor and cursor.moveToFirst():
                    idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if idx >= 0:
                        fname = cursor.getString(idx)
                    cursor.close()
            except Exception:
                pass

            if not IMG_DIR:
                self._toast('Appen er ikke klar ennå. Prøv igjen.')
                return

            dst = os.path.join(IMG_DIR, fname)
            ok  = _copy_content_uri(uri, dst)
            if not ok:
                self._toast('Kunne ikke lese det delte bildet.')
                return

            # Be brukeren velge mappe
            self._share_pick_folder_popup(dst, fname)

        except Exception:
            logging.exception('_process_shared_image: feil')
            self._toast('Feil ved mottak av delt bilde.')

    def _share_pick_folder_popup(self, img_path, fname):
        """
        Popup som lar brukeren velge hvilken mappe et Share-mottatt bilde
        skal legges i. Filnavnet (uten extension) brukes som navneforslag.
        """
        folders = self.data.get('folders', [])
        if not folders:
            self._toast('Ingen mapper funnet. Opprett en mappe først.')
            return

        pop_ref  = [None]
        layout   = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        layout.add_widget(Label(
            text=f'Mottatt bilde: {fname}\nVelg hvilken mappe det skal legges i:',
            size_hint_y=None, height=dp(56),
            font_size=fsp(15), color=(0.08, 0.10, 0.35, 1),
            halign='center', valign='middle',
        ))

        name_suggestion = os.path.splitext(fname)[0].replace('_', ' ')
        layout.add_widget(Label(
            text='Navn på symbolet:',
            size_hint_y=None, height=dp(26),
            font_size=fsp(13), color=(0.3, 0.3, 0.4, 1), halign='left',
        ))
        name_inp = smart_input(text=name_suggestion, hint='Navn på symbol')
        layout.add_widget(name_inp)

        sv   = ScrollView(size_hint_y=None, height=dp(220))
        vbox = BoxLayout(orientation='vertical', spacing=dp(6), size_hint_y=None)
        vbox.bind(minimum_height=vbox.setter('height'))

        for fo in folders:
            def make_add(dest=fo):
                def do_add(*_):
                    nm = name_inp.text.strip() or name_suggestion
                    dest['items'].append({
                        'id':    str(uuid.uuid4()),
                        'name':  nm,
                        'image': img_path,
                    })
                    save_struct(self.data)
                    pop_ref[0].dismiss()
                    self._toast(f'Lagt til i: {dest["name"]}')
                    logging.info('Share-bilde lagt til: %s → %s', fname, dest["name"])
                return do_add

            vbox.add_widget(mk_btn(
                dest['name'],
                hex_k(fo['color']),
                color=(0.05, 0.05, 0.2, 1),
                h=dp(58), fs=16,
                cb=make_add(fo),
            ))

        sv.add_widget(vbox)
        layout.add_widget(sv)
        layout.add_widget(mk_btn(
            'Avbryt (slett bildet)',
            hex_k('#9CA3AF'), h=dp(48), fs=14,
            cb=lambda *_: (
                os.remove(img_path) if os.path.exists(img_path) else None,
                pop_ref[0].dismiss(),
            ),
        ))

        pop = Popup(
            title='Legg til delt bilde',
            content=layout, size_hint=POPUP_LARGE,
        )
        pop_ref[0] = pop
        pop.open()



    def _on_permissions_result(self, permissions, grants):
        """Kalles av Android etter at brukeren har svart på tillatelsesdialogen."""
        granted = [p for p, g in zip(permissions, grants) if g]
        denied  = [p for p, g in zip(permissions, grants) if not g]
        logging.info('Tillatelser innvilget: %s', granted)
        if denied:
            logging.warning('Tillatelser avvist: %s', denied)
            self._toast(
                'Noen tillatelser ble avvist.\n'
                'Filblaing fungerer kanskje ikke.',
                duration=4.0,
            )

    # ══════════════════════════════════════════════════
    #  NAVIGASJONSBAR
    # ══════════════════════════════════════════════════

    def _build_quickbar(self):
        """
        Permanent hurtigrad over navigasjonsbar – alltid synlig.
        Rekker, Dagsplan, Tidsur, Spill – fire snarveier.
        """
        bar = BoxLayout(
            size_hint_y=None, height=rdp(52),
            spacing=dp(4), padding=(dp(4), dp(3), dp(4), dp(2)),
        )
        # Bakgrunnsfarge via canvas – import utenfor with-blokken
        from kivy.graphics import Color as _KC, Rectangle as _KR
        with bar.canvas.before:
            _KC(0.84, 0.86, 0.92, 1.0)
            self._qbar_bg = _KR(pos=bar.pos, size=bar.size)
        bar.bind(pos=lambda w, v: setattr(self._qbar_bg, 'pos', v),
                 size=lambda w, v: setattr(self._qbar_bg, 'size', v))
        _qcols = [
            ('Rekker',   '#4ECDC4', self._nav_sequences),
            ('Dagsplan', '#FF9F43', self._nav_dagsrytme),
            ('Tidsur',   '#4D96FF', self._nav_tidsur),
            ('Spill',    '#C77DFF', self._nav_bildepar),
            ('Tegn',     '#FFD93D', self.go_draw),
        ]
        for lbl, col, fn in _qcols:
            bar.add_widget(mk_btn(lbl, hex_k(col), h=rdp(46), fs=12,
                cb=lambda *_, f=fn: f()))
        return bar

    def _build_navbar(self):
        """
        Navigasjonsbar plassert NEDERST for énhånds-bruk på store telefoner.
        Lys grå bakgrunn (NavBar KV-regel) med fargede pill-knapper.
        Hver knapp har sin egen kategori-farge for rask gjenkjennelse.
        """
        bar = NavBar(
            orientation='horizontal',
            size_hint_y=None, height=rdp(72),
            padding=(dp(8), dp(8)),
            spacing=dp(6),
        )

        # Pill-knapper med kategori-farger mot lys grå navbar-bakgrunn.
        # Tekstfargen velges automatisk via text_on() per knappefarge.
        btn_kw = dict(size_hint_y=None, height=rdp(56), radius=dp(14))

        self._btn_back = mk_btn(
            'Tilbake', hex_k('#4D96FF'), fs=13,
            cb=self.go_back, **btn_kw,
        )
        self._btn_home = mk_btn(
            'Hjem', hex_k('#6BCB77'), fs=13,
            cb=self.go_home, **btn_kw,
        )
        # Plassen der Søk-knappen lå tidligere holdes åpen for fremtidig
        # bruk. Søk-funksjonen er flyttet til tittellinjen oppe til høyre
        # for bedre tilgjengelighet (synlig på alle skjermer).
        search_kw = {k: v for k, v in btn_kw.items() if k != 'radius'}
        self._btn_search = Widget(**search_kw)
        self._btn_edit = mk_btn(
            'Red.', hex_k('#C77DFF'), fs=13,
            cb=self.toggle_edit, **btn_kw,
        )
        self._btn_settings_nav = mk_btn(
            'Innst.', hex_k('#78909C'), fs=13,
            cb=lambda *_: self._nav_settings(), **btn_kw,
        )

        for w in [self._btn_back, self._btn_home, self._btn_search,
                  self._btn_edit, self._btn_settings_nav]:
            bar.add_widget(w)
        return bar

    def _build_bottombar(self):
        """
        Slim mørk tittellinje øverst med tittel sentrert.

        Søkeknappen som tidligere lå her er flyttet til FAB-ens
        hurtigmeny (_fab_quick_menu) – mer tilgjengelig for énhånds-
        bruk enn et lite ikon i øvre høyre hjørne.

        Høyde: 46dp – kompakt men lesbar.
        """
        bar = BottomBar(
            size_hint_y=None, height=rdp(46),
            padding=(dp(14), dp(6)),
            spacing=dp(0),
        )
        self._lbl_title = Label(
            text=APP_TITLE, bold=True, font_size=sp(17),
            color=(1.0, 1.0, 1.0, 0.95),
            halign='center', valign='middle',
        )
        self._lbl_title.bind(size=self._lbl_title.setter('text_size'))
        bar.add_widget(self._lbl_title)
        return bar

    def _set_title(self, t):
        self._lbl_title.text = t

    def _set_edit_highlight(self, on):
        self._btn_edit.btn_color = list(hex_k('#7B2FBE' if on else '#C77DFF'))

    # ── Navigasjon ─────────────────────────────────────────────────

    def go_back(self, *_):
        if self.nav_stack:
            scr, kw = self.nav_stack.pop()
            self._next_slide_dir = 'back'
            getattr(self, f'_show_{scr}')(**kw)
        else:
            self._next_slide_dir = 'back'
            self._show_home()

    def go_home(self, *_):
        self.nav_stack.clear()
        self.edit_mode = False
        self._set_edit_highlight(False)
        self._show_home()

    def go_draw(self, *_):
        if self._cur_scr == 'folder':
            self.nav_stack.append(('folder', {'fid': self.cur_folder}))
        elif self._cur_scr == 'sequences':
            self.nav_stack.append(('sequences', {}))
        elif self._cur_scr not in ('draw',):
            self.nav_stack.append(('home', {}))
        self._show_draw()

    def toggle_edit(self, *_):
        if self._cur_scr in ('draw', 'image', 'tidsur', 'bildepar', 'settings'):
            return
        st = self.data.get('settings', {})
        # Barn-modus: krev PIN for å aktivere redigeringsmodus
        if st.get('barn_modus', False) and not self.edit_mode:
            self._barn_pin_popup(self._do_toggle_edit)
        else:
            self._do_toggle_edit()

    def _do_toggle_edit(self):
        self.edit_mode = not self.edit_mode
        self._set_edit_highlight(self.edit_mode)
        if self._cur_scr == 'folder':
            self._show_folder(fid=self.cur_folder)
        elif self._cur_scr == 'sequences':
            self._show_sequences()
        elif self._cur_scr == 'dagsrytme':
            self._build_dagsrytme_ui()
        else:
            self._show_home()

    def _on_window_resize(self, *_):
        """
        Fase 1 – landskapsstøtte. Kalles ved enhver Window-resize
        (rotasjon, multi-vindu, osv.). Sjekker om PORTRETT/LIGGENDE
        faktisk har skiftet (ikke bare en mindre størrelsesendring,
        f.eks. tastatur som dukker opp), og rebygger i så fall
        gjeldende skjerm slik at rutenett (4↔6 kolonner) og
        rdp()-skalering oppdateres med nye Window-dimensjoner.
        """
        new_landscape = is_landscape()
        if new_landscape == self._is_landscape:
            return
        self._is_landscape = new_landscape
        self._refresh_for_orientation()

    def _refresh_for_orientation(self):
        """
        Rebygger gjeldende skjerm etter et retningsskifte – samme
        skjerm-dispatch som _do_toggle_edit, men uten å endre
        edit_mode. Skjermer som ikke har retningsavhengig layout
        (tegning, bilde, innstillinger osv.) lar vi stå urørt; de
        bruker uansett size_hint/pos_hint og reflyter selv via Kivy.
        """
        if self._cur_scr == 'home':
            self._show_home(animate=False)
        elif self._cur_scr == 'folder':
            self._show_folder(fid=self.cur_folder, animate=False)
        elif self._cur_scr == 'sequences':
            self._show_sequences()
        elif self._cur_scr == 'dagsrytme':
            self._build_dagsrytme_ui()
        elif self._cur_scr == 'settings':
            self._show_settings()

    def _set_orientation(self, landscape):
        """
        Bytter skjermretning programmatisk via Android sin
        Activity.setRequestedOrientation(). Dette virker UAVHENGIG av
        android:screenOrientation i manifestet (som kun setter
        STARTVERDIEN) – API-kallet overstyrer ved kjøretid, så ingen
        endring i buildozer.spec er nødvendig for fase 1.

        SENSOR-variantene (SENSOR_LANDSCAPE/SENSOR_PORTRAIT) brukes i
        stedet for de faste (LANDSCAPE/PORTRAIT) slik at enheten kan
        velge "opp-ned"-variant basert på hvilken vei den faktisk
        holdes, mens den fortsatt er LÅST til hovedretningen brukeren
        valgte.
        """
        if platform != 'android':
            self._toast('Retningsbytte er kun tilgjengelig på Android.')
            return
        try:
            from jnius import autoclass
            ActivityInfo = autoclass('android.content.pm.ActivityInfo')
            Activity = autoclass('org.kivy.android.PythonActivity')
            activity = Activity.mActivity
            if landscape:
                activity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE)
            else:
                activity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT)
        except Exception as e:
            diag(f'_set_orientation feilet: {e}')
            self._toast('Kunne ikke bytte skjermretning.')

    def _toggle_orientation(self, *_):
        """Knapp-callback: bytt mellom liggende og portrett."""
        self._set_orientation(not self._is_landscape)

    def _push(self, scr, **kw):
        self.nav_stack.append((scr, kw))

    # ══════════════════════════════════════════════════════════════════
    #  FLYTENDE SØKEKNAPP (FAB)
    #  Premium-UX-tiltak #2: alltid tilgjengelig ett-tommel-trykk for
    #  raskt søk i symboler/mapper/aktiviteter – uavhengig av hvilken
    #  skjerm den ansatte står på. Reduserer "opphold" i kommunikasjon
    #  fordi man slipper å navigere tilbake til hjem/mappestruktur for
    #  å finne et bilde man ikke vet hvor ligger.
    # ══════════════════════════════════════════════════════════════════

    def _build_fab(self):
        """
        Bygger den flytende runde "+"-knappen.

        Plassert nederst til høyre (pos_hint) – naturlig tommel-sone
        ved énhånds-bruk på store telefoner. mk_btn() gir automatisk
        haptic feedback (kort vibrasjon) og trykk-animasjon.

        radius == width/2 (begge dp(64)/2 = dp(32)) gir en perfekt
        sirkel i stedet for avrundet rektangel.

        "+" er et vanlig ASCII-tegn og rendres trygt med NotoSans –
        i motsetning til emoji (➕✏️📸🔍), som mangler glyfer i
        NotoSans-Regular og ville vist seg som tomme firkanter
        (samme problem som ble fikset for æ/ø/å, men for emoji).
        Derfor brukes ren tekst uten emoji i hele quick-menyen.
        """
        fab = mk_btn(
            '+', hex_k('#9B59B6'), h=dp(64), fs=34,
            size_hint=(None, None), width=dp(64),
            pos_hint={'right': 0.97, 'y': 0.035},
            radius=dp(32),
            cb=lambda *_: self._fab_quick_menu(),
        )
        return fab

    def _fab_quick_menu(self):
        """
        Hurtigmeny som "popper ut" fra FAB-en – énhånds-vennlig design:

          • Gjennomsiktig bakgrunn (ingen Popup-scrim) – knappene flyter
            direkte over skjerminnholdet.
          • Kompakt: maks ~260dp total høyde, plassert på VENSTRE side
            av skjermen, vertikalt sentrert – innenfor naturlig
            tommelbue når telefonen holdes i høyre hånd og FAB-en
            (nederst til høyre) trykkes.
          • Hver knapp animeres fra FAB-ens posisjon og ut til sin
            endelige plass, med liten forsinkelse per knapp (kaskade)
            og 'out_back'-easing – gir et "popp"-preg med en bitte
            liten studs/deakselerasjon på slutten.
          • Usynlig "fangstlag" bak knappene lukker menyen ved trykk
            utenfor – slik at man ikke trenger en egen Avbryt-knapp
            for det vanligste tilfellet (angre = trykk hvor som helst
            ellers), men «Avbryt» finnes likevel som siste knapp for
            tydelighet.
        """
        if getattr(self, '_fab_menu_open', False):
            return
        self._fab_menu_open = True
        haptic_feedback()

        actions = [
            ('Ny aktivitet',      '#6BCB77', self._dr_new_activity_flow),
            ('Rediger aktivitet', '#4D96FF', self._fab_edit_current_activity),
            ('Legg til bilde',    '#FF9F43', self._fab_add_image),
            ('Søk',               '#9B59B6', self._global_search_popup),
            ('Avbryt',            '#9CA3AF', None),
        ]

        btn_w, btn_h, gap = dp(190), dp(44), dp(8)
        fab_cx, fab_cy = self._fab.center

        # ── Plassering: stables OPPOVER fra FAB-en, høyrejustert ────
        # med FAB-ens høyrekant – «rett ved siden av»-følelse i stedet
        # for et frittstående panel et annet sted på skjermen.
        # Knapp 0 ("Ny aktivitet") havner nærmest FAB-en (kortest
        # tommelreise for den mest brukte handlingen), etterfølgende
        # knapper stables videre oppover.
        target_x = self._fab.right - btn_w
        first_y  = self._fab.top + gap

        self._fab_menu_widgets = []

        # ── Usynlig fangstlag – fyller hele innholdsflaten ──────────
        catcher = Widget(size_hint=(None, None),
                         pos=self._content.pos, size=self._content.size)
        def _catcher_touch(w, touch):
            if w.collide_point(*touch.pos):
                self._fab_menu_close()
                return True
            return False
        catcher.bind(on_touch_down=_catcher_touch)
        self._content.add_widget(catcher)
        self._fab_menu_widgets.append(catcher)

        # ── Knapper – starter som et lite punkt ved FAB-en ──────────
        for i, (label, color, fn) in enumerate(actions):
            target_pos = (target_x, first_y + i * (btn_h + gap))
            btn = mk_btn(label, hex_k(color), h=btn_h, fs=13,
                         size_hint=(None, None), width=btn_w)
            btn.size    = (dp(2), dp(2))
            btn.pos     = (fab_cx - dp(1), fab_cy - dp(1))
            btn.opacity = 0

            cb = (self._fab_make_action(fn) if fn
                  else (lambda *_: self._fab_menu_close()))
            btn.bind(on_release=cb)

            self._content.add_widget(btn)
            self._fab_menu_widgets.append(btn)

            anim = Animation(pos=target_pos, size=(btn_w, btn_h),
                             opacity=1, duration=0.28, t='out_back')
            Clock.schedule_once(
                lambda dt, a=anim, b=btn: a.start(b), i * 0.035)

    def _fab_make_action(self, fn):
        """Lukker hurtigmenyen, deretter kjører fn() etter en kort pause
        (lar lukke-animasjonen starte før evt. ny popup åpnes)."""
        def _cb(*_):
            self._fab_menu_close()
            Clock.schedule_once(lambda *_: fn(), 0.08)
        return _cb

    def _fab_menu_close(self, instant=False):
        """
        Lukker hurtigmenyen.

        instant=True  → fjerner umiddelbart uten animasjon. Brukes som
                         sikkerhetsnett i _set_content() hvis brukeren
                         skulle navigere bort mens menyen er åpen, slik
                         at vi aldri etterlater "spøkelsesknapper" flytende
                         over neste skjerm.
        instant=False → rask fade-ut (0.12s) før fjerning – normal lukking.
        """
        if not getattr(self, '_fab_menu_open', False):
            return
        self._fab_menu_open = False
        widgets = getattr(self, '_fab_menu_widgets', [])
        for w in widgets:
            if instant:
                if w in self._content.children:
                    self._content.remove_widget(w)
            else:
                anim = Animation(opacity=0, duration=0.12, t='in_cubic')
                anim.bind(on_complete=lambda *a, ww=w: (
                    self._content.remove_widget(ww)
                    if ww in self._content.children else None))
                anim.start(w)
        self._fab_menu_widgets = []

    def _fab_edit_current_activity(self):
        """
        Finner aktiviteten som er aktiv "NÅ" i dagens dagsplan og åpner
        rediger-popup for den direkte. Samme søke-logikk som
        «Akkurat nå»-kortet på hjemskjermen (se _home_now_card).

        Hvis ingen aktivitet pågår akkurat nå, vises en toast i stedet
        for å åpne en tom/feil popup.
        """
        entries = sorted(
            get_day_plan(self.data, today_code()),
            key=lambda e: e.get('start', '00:00'))
        now_m = datetime.now().hour * 60 + datetime.now().minute
        current = None
        for e in entries:
            s = self._dr_parse(e.get('start', '00:00'))
            t = self._dr_parse(e.get('end',   '23:59'))
            if s <= now_m < t:
                current = e
                break
        if current is None:
            self._toast('Ingen aktivitet pågår akkurat nå.')
            return
        self._dr_entry_popup(current)

    def _fab_add_image(self):
        """
        «Legg til bilde»-handlingen i quick-menyen.

        Hvis brukeren allerede står inne i en mappe (_cur_scr=='folder'),
        åpnes _item_popup direkte for DEN mappen – dette er den vanligste
        situasjonen («jeg mangler et symbol her og nå»).

        Ellers vises en kompakt mappevelger først, slik at brukeren kan
        legge til et bilde i en mappe uten å navigere dit manuelt.
        """
        if self._cur_scr == 'folder' and self.cur_folder:
            fo = get_folder(self.data, self.cur_folder)
            if fo:
                self._item_popup(fo, None)
                return

        folders = self.data.get('folders', [])
        if not folders:
            self._toast('Ingen mapper finnes ennå.')
            return

        pop_ref = [None]
        layout = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(14))
        layout.add_widget(Label(
            text='Velg mappe for nytt bilde:', size_hint_y=None, height=dp(32),
            font_size=fsp(15), bold=True, color=(0.08, 0.10, 0.35, 1)))
        sv  = ScrollView()
        col = BoxLayout(orientation='vertical', spacing=dp(6),
                        size_hint_y=None)
        col.bind(minimum_height=col.setter('height'))

        def _pick(fo):
            pop_ref[0].dismiss()
            Clock.schedule_once(lambda *_: self._item_popup(fo, None), 0.05)

        for fo in folders:
            col.add_widget(mk_btn(
                fo['name'], hex_k(fo.get('color', '#4D96FF')),
                h=dp(50), fs=15,
                cb=lambda *_, f=fo: _pick(f)))
        sv.add_widget(col)
        layout.add_widget(sv)
        layout.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(46), fs=14,
            cb=lambda *_: pop_ref[0].dismiss()))

        pop = Popup(title='Velg mappe', content=layout,
                    size_hint=POPUP_MEDIUM, title_size=fsp(16))
        pop_ref[0] = pop
        pop.open()

    def _update_fab_visibility(self):
        """
        Skjuler søke-FAB-en i kontekster der den ikke gir mening eller
        ville forstyrre:
          • barn-modus – enheten er da overlevert til et barn, og
            søk/navigasjon utenfor den kuraterte tavla skal ikke være
            tilgjengelig for dem.
          • fullskjermbilde (_cur_scr == 'image') – dette er visningen
            som vises TIL barnet; en flytende knapp ville forstyrre.

        Fjerner/legger til widgeten helt (ikke bare opacity) slik at
        den verken er synlig eller mottar berøringer når skjult.
        """
        barn = self.data.get('settings', {}).get('barn_modus', False)
        hide = barn or self._cur_scr == 'image'
        in_tree = self._fab in self._content.children
        if hide and in_tree:
            self._content.remove_widget(self._fab)
        elif not hide and not in_tree:
            self._content.add_widget(self._fab)

    def _set_content(self, widget, animate=True, direction=None):
        """
        Bytter innholdsflaten med slide-animasjon.
        direction='forward' → slide inn fra høyre (x: Window.width → 0)
        direction='back'    → slide inn fra venstre (tilbake-navigasjon)
        animate=False       → ingen animasjon (bakgrunns-refresh)
        Retning kan settes via self._next_slide_dir (konsumeres her).
        """
        if direction is None:
            direction = getattr(self, '_next_slide_dir', 'forward')
        self._next_slide_dir = 'forward'  # reset til default

        # Sikkerhetsnett: hvis FAB-hurtigmenyen av en eller annen grunn
        # fortsatt er åpen når skjermen byttes, fjern den øyeblikkelig
        # (uten fade) – ellers ville knappene bli liggende flytende
        # over den NYE skjermen.
        if getattr(self, '_fab_menu_open', False):
            self._fab_menu_close(instant=True)

        if self._cur_scr != 'dagsrytme':
            ev = getattr(self, '_dr_event', None)
            if ev:
                ev.cancel()
                self._dr_event = None
        if self._cur_scr != 'tidsur' and getattr(self, '_timer_running', False):
            self._tidsur_stop()
        # Nullstill adaptiv bakgrunn når vi forlater bilde-skjermen
        if self._cur_scr == 'image':
            hc_bg = (1.0, 1.0, 1.0, 1.0) if is_hc() else time_of_day_tint()
            Window.clearcolor = hc_bg

        self._content_inner.clear_widgets()
        # FloatLayout krever size_hint=(1,1) for å fylle hele flaten
        widget.size_hint = (1, 1)
        self._content_inner.add_widget(widget)

        # KRITISK: FloatLayout endrer IKKE child.y når pos_hint er tom –
        # widget.y forblir på sin default-verdi (0 = vindusbunnen).
        # Men _content_inner selv ligger IKKE ved vindusbunnen (det er
        # navigasjonsbaren _navbar som gjør det) – _content_inner.y =
        # navbar-høyden. Uten denne linjen blir widget plassert
        # navbar_h piksler for lavt: et tomt gap øverst (under
        # hurtigmenyen) og widgetens nederste del havner bak/under
        # _navbar i stedet for over den.
        widget.y = self._content_inner.y

        if animate:
            if direction == 'back':
                # Slide inn fra venstre (tilbake-navigasjon)
                widget.x = -Window.width
                widget.opacity = 1
                Animation(x=0, duration=0.2, t='out_cubic').start(widget)
            else:
                # Slide inn fra høyre (navigering fremover)
                widget.x = Window.width
                widget.opacity = 1
                Animation(x=0, duration=0.2, t='out_cubic').start(widget)
        else:
            widget.opacity = 1
            widget.x = 0

        # Bind sveipe-navigasjon hvis aktivert i innstillinger
        if self.data.get('settings', {}).get('swipe_nav', False):
            self._bind_swipe(widget)

        # Skjul/vis flytende søkeknapp avhengig av kontekst
        # (barn-modus / fullskjermbilde → skjult)
        self._update_fab_visibility()

    def _bind_swipe(self, widget):
        """Binder sveipe-gjenkjenning til widget for høyre/venstre navigasjon."""
        touch_start = [None]
        def on_touch_down_sw(w, touch):
            touch_start[0] = touch.x
            return False   # ikke konsumér – la scrolling fungere
        def on_touch_up_sw(w, touch):
            if touch_start[0] is None:
                return False
            dx = touch.x - touch_start[0]
            dy = abs(touch.y - touch.oy)
            touch_start[0] = None
            # Kun horisontale sveip (dx > 80dp, vertikal drift < 40dp)
            if abs(dx) > dp(80) and dy < dp(40):
                if dx > 0:
                    self.go_back()   # sveip høyre = tilbake
                else:
                    pass             # sveip venstre = frem (ingen stack ennå)
            return False
        widget.bind(on_touch_down=on_touch_down_sw,
                    on_touch_up=on_touch_up_sw)

    # ══════════════════════════════════════════════════
    #  HJEMSKJERM
    # ══════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    #  FESTEDE SNARVEIER
    # ══════════════════════════════════════════════════════════════

    def _build_pinned_section(self, festede):
        """Bygger rad med opp til 8 festede bildesnarveier øverst på hjem."""
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(4))
        box.bind(minimum_height=box.setter('height'))
        lbl = Label(text='Snarveier', font_size=fsp(12), bold=True,
                    color=(0.45, 0.47, 0.60, 1),
                    size_hint_y=None, height=dp(20), halign='left')
        lbl.bind(size=lbl.setter('text_size'))
        box.add_widget(lbl)
        # 4 kolonner i portrett, 6 i liggende (fase 1 – landskapsstøtte)
        grid = GridLayout(cols=(6 if is_landscape() else 4),
                          spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for pin in festede[:8]:
            grid.add_widget(self._make_pinned_tile(pin))
        box.add_widget(grid)
        return box

    def _make_pinned_tile(self, pin):
        IMG_H = dp(72)
        LBL_H = dp(28)
        edit  = self.edit_mode
        # I redigeringsmodus får snarveien en ekstra "Fjern"-rad nederst,
        # slik at festede bilder kan løsnes direkte fra hjemskjermen –
        # samme mønster som "Slett" på mappe-/bildekort.
        ACT_H  = dp(28) if edit else 0
        TILE_H = IMG_H + LBL_H + ACT_H + dp(4)
        fo     = get_folder(self.data, pin.get('folder_id'))
        color  = fo.get('color', '#4D96FF') if fo else '#4D96FF'
        r, g, b, _ = hex_k(color)
        card_col = (r*0.12 + 0.88, g*0.12 + 0.88, b*0.12 + 0.88, 1.0)
        cell = RBox(orientation='vertical', size_hint_y=None, height=TILE_H,
                    spacing=0, padding=(0, 0, 0, dp(2)),
                    box_color=list(card_col), radius=dp(12))
        bind_card_pop(cell)
        img_path = pin.get('image', '')
        if img_path and os.path.exists(img_path):
            thumb = get_thumbnail(img_path, int(IMG_H), int(IMG_H))
            ti = TappableImage(
                (lambda: None) if edit else
                (lambda p=img_path, n=pin['name']: self._show_image_full(p, n)),
                source=img_path if thumb is None else '',
                allow_stretch=True, keep_ratio=True,
                size_hint=(1, None), height=IMG_H)
            if thumb:
                ti.texture = thumb
            cell.add_widget(ti)
        btn = RBtn(text=pin['name'], size_hint=(1, None), height=LBL_H,
                   btn_color=list(hex_k(color)), color=text_on(color),
                   bold=True, font_size=fsp(11), radius=dp(8),
                   shorten=True, shorten_from='right',
                   halign='center', valign='middle')
        btn.bind(size=btn.setter('text_size'))
        if edit:
            # I redigeringsmodus åpner trykk på selve bildet/etiketten
            # IKKE fullskjermvisning (det gir ingen mening å redigere
            # derfra) – i stedet er "Fjern"-knappen den eneste handlingen.
            btn.disabled = True
        else:
            btn.bind(on_release=lambda b, p=img_path, n=pin['name']:
                     self._show_image_full(p, n))
        cell.add_widget(btn)

        if edit:
            def _do_unpin(*_, pid=pin.get('id')):
                self.data['festede'] = [
                    p for p in self.data.get('festede', [])
                    if p.get('id') != pid]
                save_struct(self.data)
                self._toast('Snarvei fjernet.')
                self._show_home()
            cell.add_widget(mk_btn(
                'Fjern', hex_k('#FF6B6B'), h=ACT_H - dp(2), fs=11,
                cb=_do_unpin))

        return cell

    def _pin_popup(self, fo, it):
        """Popup: fest til hjem / løsne fra hjem."""
        festede = self.data.setdefault('festede', [])
        already = next((p for p in festede if p.get('id') == it['id']), None)
        box = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        box.add_widget(Label(text=it['name'], font_size=fsp(16), bold=True,
                             color=(0.06, 0.08, 0.30, 1),
                             size_hint_y=None, height=dp(36), halign='center'))
        pop = Popup(title='', content=box, size_hint=POPUP_SMALL,
                    separator_height=0)
        if already:
            def _unpin(*_):
                self.data['festede'] = [p for p in festede
                                        if p.get('id') != it['id']]
                save_struct(self.data)
                pop.dismiss()
                self._toast('Snarvei fjernet.')
                self._show_home()
            box.add_widget(mk_btn('Løsne fra hjem', hex_k('#FF9F43'),
                                  h=dp(50), fs=14, cb=_unpin))
        else:
            def _pin(*_):
                festede.append({'id': it['id'], 'name': it['name'],
                                'image': it.get('image', ''),
                                'folder_id': fo['id']})
                save_struct(self.data)
                pop.dismiss()
                self._toast('Festet til hjem!')
            box.add_widget(mk_btn('Fest til hjem', hex_k('#6BCB77'),
                                  h=dp(50), fs=14, cb=_pin))
        box.add_widget(mk_btn('Avbryt', hex_k('#78909C'),
                              h=dp(46), fs=13,
                              cb=lambda *_: pop.dismiss()))
        pop.open()

    # ══════════════════════════════════════════════════════════════
    #  BARN-MODUS
    # ══════════════════════════════════════════════════════════════

    def _barn_pin_popup(self, on_success):
        """Viser en 4-sifret PIN-dialog for barn-modus. on_success() kalles ved riktig PIN."""
        pin_stored = self.data.get('settings', {}).get('barn_modus_pin', '')
        if not pin_stored:
            on_success()
            return
        entered = ['']
        box = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
        box.add_widget(Label(text='Skriv inn PIN for å redigere',
                             font_size=fsp(15), bold=True,
                             color=(0.06, 0.08, 0.30, 1),
                             size_hint_y=None, height=dp(34), halign='center'))
        dots_lbl = Label(text='_ _ _ _', font_size=fsp(22), bold=True,
                         color=(0.20, 0.30, 0.60, 1),
                         size_hint_y=None, height=dp(40), halign='center')
        box.add_widget(dots_lbl)
        err_lbl = Label(text='', font_size=fsp(13),
                        color=(0.80, 0.15, 0.15, 1),
                        size_hint_y=None, height=dp(24), halign='center')
        box.add_widget(err_lbl)
        pop = Popup(title='', content=box, size_hint=POPUP_SMALL,
                    separator_height=0)

        def _update_dots():
            n = len(entered[0])
            dots_lbl.text = '  '.join(['●' if i < n else '_' for i in range(4)])

        def _digit(d):
            if len(entered[0]) < 4:
                entered[0] += str(d)
                _update_dots()
                if len(entered[0]) == 4:
                    if entered[0] == pin_stored:
                        pop.dismiss()
                        on_success()
                    else:
                        err_lbl.text = 'Feil PIN – prøv igjen'
                        entered[0] = ''
                        _update_dots()

        numpad = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(210))
        for d in [1,2,3,4,5,6,7,8,9,None,0,None]:
            if d is None:
                numpad.add_widget(Widget())
            else:
                numpad.add_widget(mk_btn(str(d), hex_k('#4D96FF'),
                                         h=dp(64), fs=20,
                                         cb=lambda *_, digit=d: _digit(digit)))
        box.add_widget(numpad)
        box.add_widget(mk_btn('Avbryt', hex_k('#78909C'), h=dp(44), fs=13,
                              cb=lambda *_: pop.dismiss()))
        pop.open()

    # ══════════════════════════════════════════════════════════════
    #  DAGSPLAN-FREMGANG ANIMASJON
    # ══════════════════════════════════════════════════════════════

    def _anim_activity_done(self, center_x=None, center_y=None):
        """
        Viser en grønn ekspanderende ring som fades ut – bekrefter
        fullført aktivitet. Sentrert på skjermen om pos ikke er gitt.
        """
        if center_x is None:
            center_x = Window.width  / 2
        if center_y is None:
            center_y = Window.height / 2
        SIZE = dp(90)
        from kivy.uix.widget import Widget as _W
        from kivy.graphics import Color as _C, Line as _L
        ring = _W(size_hint=(None, None), size=(SIZE, SIZE),
                  pos=(center_x - SIZE/2, center_y - SIZE/2))
        with ring.canvas:
            _C(0.18, 0.72, 0.38, 0.85)
            _line = _L(circle=(center_x, center_y, SIZE/2), width=dp(4))
        Window.add_widget(ring)
        def _cleanup(*_):
            try: Window.remove_widget(ring)
            except Exception: pass
        anim_ring = Animation(size=(SIZE*2.2, SIZE*2.2), opacity=0,
                              duration=0.45, t='out_cubic')
        anim_ring.bind(on_complete=_cleanup)
        anim_ring.start(ring)

    # ══════════════════════════════════════════════════════════════
    #  FLIP-OVERGANG TIL FULLSKJERM-BILDE
    # ══════════════════════════════════════════════════════════════

    def _flip_to_image(self, path, name):
        """Åpner fullskjermbilde. Slide-animasjon håndteres av _set_content."""
        self._show_image_full(path, name)

    def _show_home(self, animate=True, **_):
        self._cur_scr   = 'home'
        self.cur_folder = None
        self._set_title(APP_TITLE)

        outer = BoxLayout(orientation='vertical', spacing=rdp(6),
                          padding=(dp(8), rdp(6), dp(8), 0))

        # ── «Akkurat nå»-kort ────────────────────────────────────
        snap = self._home_now_card()
        if snap is not None:
            outer.add_widget(snap)

        # ── Festede snarveier ─────────────────────────────────────
        festede = self.data.get('festede', [])
        if festede:
            outer.add_widget(self._build_pinned_section(festede))

        # ── «Ny mappe»-knapp kun i redigeringsmodus ───────────────
        if self.edit_mode:
            outer.add_widget(mk_btn(
                '+  Ny mappe', hex_k('#6BCB77'), h=dp(46), fs=14,
                cb=lambda *_: self._folder_popup(None),
            ))

        # ── 3-kolonne mappegrid ───────────────────────────────────
        if not self.data['folders']:
            # Vennlig empty state hvis ingen mapper er opprettet ennå
            outer.add_widget(self._empty_state(
                glyph='[ Mapper ]',
                msg='Ingen mapper ennå.\nTrykk "Red." og deretter "+ Ny mappe".'))
        else:
            # 3 kolonner i portrett, 6 i liggende (fase 1 – landskapsstøtte)
            grid = GridLayout(cols=(6 if is_landscape() else 3),
                              spacing=dp(6), padding=(dp(6), dp(6)),
                              size_hint_y=None)
            grid.bind(minimum_height=grid.setter('height'))
            for fo in self.data['folders']:
                grid.add_widget(self._make_folder_tile(fo))
            sv = ScrollView()
            sv.add_widget(grid)
            outer.add_widget(sv)
        self._set_content(outer, animate=animate)

    def _home_now_card(self):
        """
        Bygger «Akkurat nå»-kortet øverst på hjemskjermen.

        Returnerer None i alle tilfeller der det ikke er noe meningsfylt å vise:
          – ingen dagsplan for i dag
          – alle aktiviteter er ferdige for dagen
          – det er mer enn 4 timer til neste aktivitet (ingen umiddelbar verdi)

        Dette sikrer at hjemskjermen IKKE har et tomt/usynlig mellomrom
        når dagsplanen ikke er aktiv.
        """
        if is_paused(self.data):
            box = RBox(orientation='horizontal',
                       size_hint_y=None, height=rdp(72),
                       padding=(dp(14), dp(8)),
                       box_color=(1.0, 0.86, 0.30, 1.0), radius=dp(16))
            box.add_widget(Label(
                text='[b]⏸  Dagsrytme på pause[/b]\nTrykk for å gå til dagsplan',
                markup=True, font_size=fsp(14),
                color=(0.15, 0.10, 0.05, 1), halign='left', valign='middle'))
            box.children[-1].bind(size=box.children[-1].setter('text_size'))
            def _tap_pause(w, touch):
                if w.collide_point(*touch.pos):
                    self._nav_dagsrytme()
                    return True
                return False
            box.bind(on_touch_down=_tap_pause)
            # Myk fade-inn – gir "Akkurat nå"-kortet et levende preg når
            # hjemskjermen (re)bygges, i stedet for at det bare hopper
            # rett inn med fullt innhold.
            box.opacity = 0
            Animation(opacity=1, duration=0.35, t='out_cubic').start(box)
            return box

        # Finn nåværende/neste aktivitet for dagens plan
        entries = sorted(get_day_plan(self.data, today_code()),
                         key=lambda e: e.get('start', '00:00'))
        if not entries:
            return None  # ingen aktiviteter i dag

        now   = datetime.now()
        now_m = now.hour * 60 + now.minute
        current = upcoming = None
        for e in entries:
            s = self._dr_parse(e.get('start', '00:00'))
            t = self._dr_parse(e.get('end',   '23:59'))
            if s <= now_m < t:
                current = (e, s, t); break
            elif s > now_m and upcoming is None:
                upcoming = (e, s)

        # Kollapser kortet:
        #  – alle aktiviteter er ferdig for dagen
        #  – neste aktivitet starter mer enn 4 timer frem i tid (ingen snart-verdi)
        if not current and not upcoming:
            return None
        if not current and upcoming:
            wait_min = upcoming[1] - now_m
            if wait_min > 240:          # > 4 timer → ikke relevant enda
                return None

        # Bygg kortet – horisontalt layout med (lite) bilde + tekst
        e, info = (current[0], 'NÅ') if current else (upcoming[0], 'NESTE')
        bg = (1.0, 1.0, 1.0, 1.0)   # alltid hvit kortbakgrunn
        card = RBox(orientation='horizontal',
                    size_hint_y=None, height=rdp(96),
                    padding=(dp(10), dp(8)), spacing=dp(10),
                    box_color=bg, radius=dp(16))
        # Bilde
        if e.get('image') and os.path.exists(e['image']):
            img_h = rdp(80)
            img_wrap = BoxLayout(size_hint_x=None, width=img_h)
            img_wrap.add_widget(self._make_framed_image(
                e['image'], img_h, faded=(info == 'NESTE')))
            card.add_widget(img_wrap)
        # Tekstkolonne
        col = BoxLayout(orientation='vertical', spacing=dp(2))
        badge_color = '#6BCB77' if info == 'NÅ' else '#4D96FF'
        col.add_widget(Label(
            text=f'[b][color={badge_color[1:]}]{info}[/color][/b]   '
                 f'[b]{e["name"]}[/b]',
            markup=True, font_size=fsp(17),
            color=(0.04, 0.10, 0.36, 1),
            size_hint_y=None, height=rdp(28), halign='left'))
        col.children[-1].bind(size=col.children[-1].setter('text_size'))
        sub = f'{e.get("start","")} – {e.get("end","")}'
        if info == 'NÅ':
            rem = current[2] - now_m
            sub += f'   ({self._dr_fmt(rem)} igjen)'
        else:
            wait = upcoming[1] - now_m
            sub += f'   (starter om {self._dr_fmt(wait)})'
        col.add_widget(Label(
            text=sub, font_size=fsp(13),
            color=(0.35, 0.40, 0.55, 1),
            size_hint_y=None, height=rdp(22), halign='left'))
        col.children[-1].bind(size=col.children[-1].setter('text_size'))
        card.add_widget(col)
        # Trykk → naviger til dagsplan
        def _tap(w, touch):
            if w.collide_point(*touch.pos):
                self._nav_dagsrytme()
                return True
            return False
        card.bind(on_touch_down=_tap)
        # Myk fade-inn – samme begrunnelse som i pause-varianten over.
        # Gir tydelig "noe oppdaterte seg nettopp"-følelse når aktiviteten
        # skifter (NÅ → NESTE, eller ny aktivitet starter).
        card.opacity = 0
        Animation(opacity=1, duration=0.35, t='out_cubic').start(card)
        return card

    def _make_folder_tile(self, fo):
        """Enkel farget flis med sentrert navn – ingen bilde."""
        edit   = self.edit_mode
        TILE_H = rdp(176) if edit else rdp(142)
        btn_h  = rdp(138) if edit else rdp(142)

        if edit:
            tap = lambda f=fo: self._folder_popup(f)
        else:
            tap = lambda f=fo: self._open_folder(f)

        cell = BoxLayout(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=dp(3),
        )

        opens    = fo.get('opens', 0)
        border_w = min(5, 1 + opens // 4)
        btn = RBtn(
            text=fo['name'],
            size_hint=(1, None), height=btn_h,
            btn_color=list(hex_k(fo['color'])),
            color=text_on(fo['color']),
            bold=True, font_size=fsp(17),
            radius=dp(16),
        )
        btn.bind(on_release=lambda b, t=tap: t())
        bind_card_pop(btn)
        r2, g2, b2, _ = hex_k(fo['color'])
        def _add_border(b=btn, r=r2, g=g2, bv=b2, bw=border_w):
            from kivy.graphics import Color as KColor, Line
            with b.canvas.after:
                KColor(max(0,r-0.18), max(0,g-0.18), max(0,bv-0.18), 0.65)
                bl = Line(rounded_rectangle=(b.x+1,b.y+1,b.width-2,b.height-2,dp(14)), width=bw)
            def _upd(w,*_):
                bl.rounded_rectangle=(w.x+1,w.y+1,w.width-2,w.height-2,dp(14))
            b.bind(pos=_upd, size=_upd)
        btn.bind(on_kv_post=lambda b,*_: _add_border())
        Clock.schedule_once(lambda *_: _add_border(), 0.05)
        cell.add_widget(btn)

        if edit:
            cell.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=dp(34), fs=12,
                cb=lambda *_, f=fo: self._del_folder(f),
            ))

        return cell

    def _open_folder(self, fo):
        self._push('home')
        fo['opens'] = fo.get('opens', 0) + 1
        save_struct(self.data)
        self.cur_folder = fo['id']
        self._show_folder(fid=fo['id'])
        # Mappe-åpning: skaler innhold fra 0.88→1.0 med spring for «løft ut»-følelse
        def _spring_in(*_):
            if self._content_inner.children:
                w = self._content_inner.children[0]
                w.opacity = 0
                Animation(opacity=1, duration=0.22, t='out_cubic').start(w)
        Clock.schedule_once(_spring_in, 0.02)

    # ══════════════════════════════════════════════════
    #  MAPPESKJERM – ASK-bilder
    # ══════════════════════════════════════════════════

    def _show_folder(self, fid=None, **_):
        fo = get_folder(self.data, fid or self.cur_folder)
        if not fo:
            self._show_home()
            return
        self._cur_scr   = 'folder'
        self.cur_folder = fo['id']
        self._set_title(fo['name'])

        items     = fo.get('items', [])
        has_img   = [it for it in items if it.get('image')]
        on_disk   = [it for it in has_img if os.path.exists(it['image'])]
        diag_section(f'MAPPE ÅPNET: {fo["name"]}')
        diag(f'items={len(items)}  med_bilde={len(has_img)}  finnes_på_disk={len(on_disk)}')
        for it in has_img[:8]:        # logg inntil 8 bilder
            p  = it['image']
            sz = os.path.getsize(p) if os.path.exists(p) else -1
            diag(f'  bilde: {os.path.basename(p)}  size={sz}B  exists={os.path.exists(p)}')

        outer = BoxLayout(
            orientation='vertical',
            spacing=dp(8), padding=(0, dp(6), 0, 0),
        )

        if self.edit_mode:
            btn_bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            btn_bar.add_widget(mk_btn(
                '+  Nytt bilde', hex_k('#6BCB77'), h=dp(46), fs=13,
                cb=lambda *_: self._item_popup(fo, None),
            ))
            btn_bar.add_widget(mk_btn(
                'Last opp', hex_k('#4D96FF'), h=dp(46), fs=13,
                cb=lambda *_: self._upload_to_folder(fo),
            ))
            btn_bar.add_widget(mk_btn(
                'Søk', hex_k('#9B59B6'), h=dp(46), fs=13,
                cb=lambda *_: self._arasaac_search_popup(fo),
            ))
            btn_bar.add_widget(mk_btn(
                '+  Ny mappe', hex_k('#FF9F43'), h=dp(46), fs=13,
                cb=lambda *_: self._folder_popup(None),
            ))
            outer.add_widget(btn_bar)

        # ── Undermapper ──────────────────────────────────────────
        subfolders = fo.get('subfolders', [])
        if subfolders or self.edit_mode:
            sub_section = BoxLayout(orientation='vertical',
                                    size_hint_y=None, spacing=dp(4))
            sub_section.bind(minimum_height=sub_section.setter('height'))
            if subfolders:
                sub_grid = GridLayout(cols=3, spacing=dp(6),
                                      size_hint_y=None)
                sub_grid.bind(minimum_height=sub_grid.setter('height'))
                for sub in subfolders:
                    sub_grid.add_widget(self._make_subfolder_tile(fo, sub))
                sub_section.add_widget(sub_grid)
            if self.edit_mode:
                sub_section.add_widget(mk_btn(
                    '+  Ny undermappe', hex_k('#4ECDC4'), h=dp(42), fs=13,
                    cb=lambda *_, f=fo: self._subfolder_popup(f, None)))
            outer.add_widget(sub_section)

        # ── ASK-bilder ────────────────────────────────────────────
        # spacing=dp(10): mellomrom mellom kort
        # padding=(dp(10), dp(4)): sidepadding = samme som spacing → jevn kant
        # Barn-modus: 2 kolonner for større treffflater
        barn = self.data.get('settings', {}).get('barn_modus', False)
        n_cols = 2 if barn else 3
        grid = GridLayout(
            cols=n_cols, spacing=dp(10),
            padding=(dp(10), dp(4), dp(10), dp(10)),
            size_hint_y=None,
        )
        grid.bind(minimum_height=grid.setter('height'))
        # Lat innlasting – tilføyer fliser med 40ms forsinkelse mellom hver.
        # Forhindrer UI-frysing ved mapper med mange bilder.
        items = list(fo['items'])
        def _add_tile(i, fo=fo, items=items):
            if i >= len(items):
                return
            grid.add_widget(self._make_item_tile(fo, items[i]))
            Clock.schedule_once(lambda *_: _add_tile(i + 1), 0.04)
        _add_tile(0)

        sv = ScrollView()
        sv.add_widget(grid)
        outer.add_widget(sv)
        self._set_content(outer)

    def _make_item_tile(self, fo, it):
        """
        ASK-bilde-kort: kvadratisk bilde øverst + etikett-knapp under.

        IMG_H beregnes dynamisk fra skjermbredde og kolonneantall slik at
        bildeflaten alltid blir kvadratisk uavhengig av skjermstørrelse.
        """
        img_path = it.get('image') or ''
        has_img  = bool(img_path and os.path.exists(img_path))
        edit     = self.edit_mode

        # Beregn kolonne-bredde fra skjermbredde:
        # grid padding lr=dp(10), spacing=dp(10) → usable = W - dp(40)
        barn = self.data.get('settings', {}).get('barn_modus', False)
        n_cols = 2 if barn else 3
        IMG_H  = (Window.width - dp(40)) / n_cols   # kvadratisk bildehøyde
        LBL_H  = dp(36)
        ACT_H  = dp(36)
        TILE_H = (IMG_H + LBL_H + ACT_H + dp(6)) if edit else (IMG_H + LBL_H + dp(2))

        if edit:
            tap = lambda f=fo, i=it: self._item_popup(f, i)
        else:
            # Direkte til fullskjerm – slide-animasjon håndteres av _set_content
            tap = lambda p=img_path, n=it['name']: self._show_image_full(p, n)

        r, g, b, _ = hex_k(fo.get('color', '#4D96FF'))
        card_col   = (r*0.12 + 0.88, g*0.12 + 0.88, b*0.12 + 0.88, 1.0)
        cell = RBox(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=0,
            padding=(0, 0, 0, dp(4)),
            box_color=list(card_col),
            radius=dp(14),
        )
        bind_card_pop(cell)

        if has_img:
            # Ingen padding – bildet går helt til toppen av kortet
            img_wrap = BoxLayout(
                size_hint=(1, None), height=IMG_H,
                padding=0,
            )
            # Hvit bakgrunn bak bildet
            with img_wrap.canvas.before:
                from kivy.graphics import Color as KC, RoundedRectangle as KRR
                KC(1.0, 1.0, 1.0, 1.0)
                _rr = KRR(
                    pos=img_wrap.pos,
                    size=img_wrap.size,
                    radius=[dp(10), dp(10), dp(2), dp(2)],
                )
            def _upd_rr(w, *_, rr=_rr):
                rr.pos  = w.pos
                rr.size = w.size
            img_wrap.bind(pos=_upd_rr, size=_upd_rr)

            tile_sz   = int(IMG_H)
            thumb_tex = get_thumbnail(img_path, tile_sz, tile_sz)
            ti = TappableImage(
                tap, source=img_path if thumb_tex is None else '',
                allow_stretch=True, keep_ratio=True,  # behold proporsjoner
            )
            if thumb_tex:
                ti.texture = thumb_tex
                diag(f'TILE PIL_OK {os.path.basename(img_path)}')
            elif img_path:
                diag(f'TILE PIL_FAIL {os.path.basename(img_path)} – starter retry')
                # ── Retry med eksponentiell backoff ──────────────────────
                def _retry_load(attempt=1, ti=ti, p=img_path, tsz=tile_sz):
                    fsize = os.path.getsize(p) if os.path.exists(p) else -1
                    diag(f'RETRY #{attempt} {os.path.basename(p)} '
                         f'size={fsize}B texture={ti.texture is not None}')
                    if ti.texture is not None:
                        diag(f'RETRY #{attempt} ALLEREDE_LASTET – avbryter')
                        return
                    # Prøv PIL-thumbnail igjen (ikke cachet ved feil)
                    new_tex = get_thumbnail(p, tsz, tsz)
                    if new_tex is not None:
                        ti.texture = new_tex
                        diag(f'RETRY #{attempt} PIL_OK – texture satt')
                        return
                    # PIL feilet – prøv Kivy async-loader som sekundær strategi
                    if ti.source and os.path.exists(p):
                        try:
                            ti.reload()
                            diag(f'RETRY #{attempt} KIVY_RELOAD kalt')
                        except Exception as _re:
                            diag(f'RETRY #{attempt} KIVY_RELOAD FEIL: {_re}')
                    if attempt < 5:
                        delay = 0.5 * attempt
                        diag(f'RETRY #{attempt} neste om {delay}s')
                        Clock.schedule_once(
                            lambda dt, a=attempt: _retry_load(a + 1),
                            delay)
                    else:
                        diag(f'RETRY GITT_OPP etter 5 forsøk: {os.path.basename(p)}')
                Clock.schedule_once(lambda dt: _retry_load(1), 0.5)
            img_wrap.add_widget(ti)
            cell.add_widget(img_wrap)

        # Etikett-knapp – fyller resten av kortet
        lbl_h = LBL_H if has_img else (IMG_H + LBL_H)
        btn = RBtn(
            text=it['name'],
            size_hint=(1, None), height=lbl_h,
            btn_color=list(hex_k(fo.get('color', '#4D96FF'))),
            color=text_on(fo.get('color', '#4D96FF')),
            bold=True, font_size=fsp(13),
            radius=dp(10) if has_img else dp(14),
            shorten=True, shorten_from='right',
            halign='center', valign='middle',
        )
        btn.bind(size=btn.setter('text_size'))

        if edit:
            btn.bind(on_release=lambda b: tap())
        else:
            # Lang trykk (0.5s) → pin-popup; kort trykk → normal tap
            _lp   = [None]
            _done = [False]

            def _lp_press(*_):
                _done[0] = False
                _lp[0] = Clock.schedule_once(lambda *_: _fire_lp(), 0.5)

            def _fire_lp():
                _done[0] = True
                haptic_feedback()
                self._pin_popup(fo, it)

            def _lp_release(*_):
                if _lp[0]:
                    _lp[0].cancel(); _lp[0] = None
                if not _done[0]:
                    tap()

            btn.bind(on_press=_lp_press, on_release=_lp_release)

        cell.add_widget(btn)

        if edit:
            row = BoxLayout(size_hint_y=None, height=ACT_H, spacing=dp(3))
            row.add_widget(mk_btn(
                'Flytt', hex_k('#FF9F43'), h=ACT_H-dp(2), fs=10,
                cb=lambda *_, f=fo, i=it: self._move_item_popup(f, i),
            ))
            row.add_widget(mk_btn(
                'Ned', hex_k('#6BCB77'), h=ACT_H-dp(2), fs=10,
                cb=lambda *_, p=img_path: self._download_image(p),
            ))
            row.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=ACT_H-dp(2), fs=10,
                cb=lambda *_, f=fo, i=it: self._del_item(f, i),
            ))
            cell.add_widget(row)

        return cell

    # ══════════════════════════════════════════════════
    #  FULLSKJERM-BILDE
    # ══════════════════════════════════════════════════

    def _show_image_full(self, path, name):
        if not path or not os.path.exists(path):
            self._toast('Bildefil ikke funnet.')
            return
        self._push('folder', fid=self.cur_folder)
        self._cur_scr = 'image'
        self._set_title('')   # tittel vises i kortet, ikke bunnbaren

        # Adaptiv bakgrunn – toner mot dominerende farge i bildet
        dom = dominant_color(path)
        Window.clearcolor = (*dom, 1.0)

        # Wrapper: RBox inneholder bilde + tittel tett pakket.
        # size_hint=(1, None) + bind på minimum_height gjør at RBox
        # kryper rundt innholdet i stedet for å fylle hele skjermen.
        outer = BoxLayout(
            orientation='vertical',
            padding=dp(12), spacing=dp(8),
        )

        card = RBox(
            orientation='vertical',
            size_hint=(1, None),
            box_color=(0.97, 0.97, 0.99, 1.0),
            radius=dp(20),
            padding=dp(8),
            spacing=dp(6),
        )
        card.bind(minimum_height=card.setter('height'))

        card.add_widget(Image(
            source=path,
            size_hint=(1, None), height=dp(340),
            allow_stretch=True, keep_ratio=True,
        ))

        name_lbl = Label(
            text=name,
            size_hint_y=None, height=dp(48),
            font_size=fsp(24), bold=True,
            color=(0.06, 0.08, 0.30, 1),
            halign='center', valign='middle',
        )
        name_lbl.bind(size=name_lbl.setter('text_size'))
        card.add_widget(name_lbl)

        btn_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        btn_row.add_widget(mk_btn(
            'Les opp', hex_k('#FF9F43'), h=dp(48), fs=14,
            cb=lambda *_: self._speak(name),
        ))
        btn_row.add_widget(mk_btn(
            'QR-kode', hex_k('#4D96FF'), h=dp(48), fs=14,
            cb=lambda *_: self._show_qr_popup(name, f'QR: {name}'),
        ))
        btn_row.add_widget(mk_btn(
            'Last ned', hex_k('#6BCB77'), h=dp(48), fs=14,
            cb=lambda *_: self._download_image(path),
        ))
        card.add_widget(btn_row)

        # ── Dagsplan-integrasjon: vis om bildet er i dagens plan ──
        today_entries = get_day_plan(self.data, today_code())
        linked = [e for e in today_entries if e.get('image') == path]
        if linked:
            e = linked[0]
            tid = f"{e.get('start','')}–{e.get('end','')}".strip('–')
            badge = RBox(
                orientation='horizontal', size_hint_y=None, height=dp(36),
                padding=(dp(10), dp(6)), spacing=dp(8),
                box_color=(0.88, 0.96, 0.90, 1.0), radius=dp(10),
            )
            badge.add_widget(Label(
                text=f'Dagsplan i dag: {e["name"]}' + (f'  {tid}' if tid else ''),
                font_size=fsp(13), color=(0.10, 0.40, 0.18, 1),
                halign='left', valign='middle',
            ))
            card.add_widget(badge)

        outer.add_widget(card)
        outer.add_widget(BoxLayout())  # spacer

        self._speak(name)
        self._set_content(outer)

    # ══════════════════════════════════════════════════
    #  TEGNESKJERM
    # ══════════════════════════════════════════════════

    def _show_draw(self, **_):
        self._cur_scr = 'draw'
        self._set_title('Tegn')
        logging.info('Åpner tegneskjerm. PIL_OK=%s', PIL_OK)

        if not PIL_OK:
            self._set_content(Label(
                text='Feil: Pillow/PIL er ikke installert.\nSjekk requirements i buildozer.spec.',
                font_size=sp(16), color=(1, 0.2, 0.2, 1),
                halign='center',
            ))
            return

        root = BoxLayout(
            orientation='vertical',
            spacing=dp(5),
            padding=(dp(6), dp(5)),
        )

        # ── Rad 1: Verktøyknapper ──────────────────────────────────
        # Penn-knappen viser/skjuler penseltype-raden ved trykk.
        # Alle andre verktøy skjuler penselraden (ikke relevant).
        tool_grid = GridLayout(
            cols=6, size_hint_y=None, height=dp(52), spacing=dp(4),
        )
        tools = [
            ('pen',     'Penn'),
            ('eraser',  'Visk.'),
            ('line',    'Linje'),
            ('rect',    'Rekt.'),
            ('ellipse', 'Oval'),
            ('fill',    'Fyll'),
        ]
        self._tool_btns  = {}
        self._brush_open = [False]   # om penselraden er synlig

        # Penselrad – bygges nå men legges til ETTER tool_grid
        brush_panel = BoxLayout(
            size_hint_y=None, height=dp(0),  # starter skjult
            opacity=0,
        )
        brush_grid = GridLayout(cols=5, spacing=dp(4))
        brushes = [
            ('rund',         'Rund'),
            ('myk',          'Myk'),
            ('kalligrafisk', 'Kalli.'),
            ('spray',        'Spray'),
            ('piksel',       'Piksel'),
        ]
        self._brush_btns = {}
        for key, lbl in brushes:
            b = RBtn(
                text=lbl,
                size_hint=(1, 1),
                font_size=sp(12),
                btn_color=list(hex_k(BRUSH_COLORS[key])),
                color=(1, 1, 1, 1),
                bold=True,
                radius=dp(8),
            )
            b.bind(on_release=lambda btn, k=key: self._set_brush_type(k))
            brush_grid.add_widget(b)
            self._brush_btns[key] = b
        brush_panel.add_widget(brush_grid)

        def toggle_brush_panel(*_):
            """Viser/skjuler penselraden ved trykk på Penn-knappen."""
            open_ = not self._brush_open[0]
            self._brush_open[0] = open_
            if open_:
                brush_panel.opacity = 1
                Animation(height=dp(46), duration=0.15, t='out_quad').start(brush_panel)
            else:
                def hide(*_): brush_panel.opacity = 0
                a = Animation(height=dp(0), duration=0.12, t='in_quad')
                a.bind(on_complete=lambda *_: setattr(brush_panel, 'opacity', 0))
                a.start(brush_panel)
            # Oppdater Penn-knappens tekst
            pen_btn = self._tool_btns.get('pen')
            if pen_btn:
                pen_btn.text = 'Penn v' if open_ else 'Penn'

        for key, lbl in tools:
            b = RBtn(
                text=lbl,
                size_hint=(1, 1),
                font_size=sp(13),
                btn_color=list(hex_k(TOOL_COLORS[key])),
                color=(1, 1, 1, 1),
                bold=True,
                radius=dp(14),
            )
            if key == 'pen':
                def pen_tap(btn, *_):
                    self._set_draw_tool('pen')
                    toggle_brush_panel()
                b.bind(on_release=pen_tap)
            else:
                def other_tap(btn, k=key, *_):
                    self._set_draw_tool(k)
                    # Lukk penselraden når man velger et annet verktøy
                    if self._brush_open[0]:
                        self._brush_open[0] = True
                        toggle_brush_panel()
                b.bind(on_release=other_tap)
            tool_grid.add_widget(b)
            self._tool_btns[key] = b

        root.add_widget(tool_grid)
        root.add_widget(brush_panel)

        # ── Rad 2: Angre / Gjenta / Lagre / Tom ──────────────────
        act = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(5))
        act.add_widget(mk_btn('Angre',  hex_k('#546E7A'), h=dp(44), fs=13,
            cb=lambda *_: self.draw_canvas and self.draw_canvas.angre()))
        act.add_widget(mk_btn('Gjenta', hex_k('#546E7A'), h=dp(44), fs=13,
            cb=lambda *_: self.draw_canvas and self.draw_canvas.gjenta()))
        act.add_widget(mk_btn('Lagre',  hex_k('#6BCB77'), h=dp(44), fs=13,
            cb=self._save_drawing))
        act.add_widget(mk_btn('Tom',    hex_k('#FF6B6B'), h=dp(44), fs=13,
            cb=lambda *_: self.draw_canvas.clear_canvas()))
        root.add_widget(act)

        # ── Rad 3: Penselstørrelse – egen rad, slider får full bredde ──
        size_row = BoxLayout(size_hint_y=None, height=dp(46),
                             spacing=dp(6), padding=(dp(4), dp(2)))
        size_row.add_widget(Label(
            text='Str:', size_hint_x=None, width=dp(36),
            font_size=sp(13), bold=True, color=(0.1, 0.1, 0.1, 1)))
        self._size_slider = Slider(min=2, max=60, value=6, step=1)
        self._size_lbl    = Label(
            text='  6', size_hint_x=None, width=dp(38),
            font_size=sp(13), color=(0.1, 0.1, 0.1, 1))
        self._size_slider.bind(value=self._on_size_change)
        size_row.add_widget(self._size_slider)
        size_row.add_widget(self._size_lbl)
        root.add_widget(size_row)

        # ── Rad 4: Stabilisering + Farge ────────────────────────────
        stab_row = BoxLayout(size_hint_y=None, height=dp(46),
                             spacing=dp(6), padding=(dp(4), dp(2)))
        stab_row.add_widget(Label(
            text='Stab:', size_hint_x=None, width=dp(44),
            font_size=sp(13), bold=True, color=(0.1, 0.1, 0.1, 1)))
        self._stab_slider = Slider(min=0, max=10, value=4, step=1)
        self._stab_lbl    = Label(
            text='4', size_hint_x=None, width=dp(22),
            font_size=sp(13), color=(0.1, 0.1, 0.1, 1))
        def on_stab(sl, val):
            v = int(val)
            self._stab_lbl.text = str(v)
            if self.draw_canvas:
                self.draw_canvas.stabilize = v
        self._stab_slider.bind(value=on_stab)
        stab_row.add_widget(self._stab_slider)
        stab_row.add_widget(self._stab_lbl)

        self._cur_color_btn = RBtn(
            size_hint=(None, None), size=(dp(40), dp(40)),
            btn_color=list(hex_k('#000000')), radius=dp(20),
        )
        self._cur_color_btn.bind(on_release=lambda *_: self._open_color_popup())
        stab_row.add_widget(self._cur_color_btn)
        open_pal_btn = mk_btn('Farge', hex_k('#4D96FF'), h=dp(42), fs=13,
            size_hint_x=None, width=dp(72))
        open_pal_btn.bind(on_release=lambda *_: self._open_color_popup())
        stab_row.add_widget(open_pal_btn)
        root.add_widget(stab_row)

        # Initialiserer _col_btns som tom dict (brukes i _set_draw_color)
        self._col_btns = {}

        # ── Tegneflate ─────────────────────────────────────────────
        self.draw_canvas = DrawCanvas()
        self.draw_canvas.stabilize = int(self._stab_slider.value)
        root.add_widget(self.draw_canvas)
        logging.info('DrawCanvas opprettet.')

        self._set_content(root)
        self._set_draw_tool('pen')
        self._set_draw_color('#000000')
        self._set_brush_type('rund')

    def _set_draw_tool(self, key):
        if self.draw_canvas:
            self.draw_canvas.tool = key
        for k, btn in self._tool_btns.items():
            btn.btn_color = list(hex_k(
                TOOL_ACTIVE[k] if k == key else TOOL_COLORS[k]
            ))
        logging.debug('Tegne-verktoy: %s', key)

    def _set_brush_type(self, key):
        """Setter penseltype på DrawCanvas og uthever valgt knapp."""
        if self.draw_canvas:
            self.draw_canvas.brush_type = key
        for k, btn in self._brush_btns.items():
            btn.btn_color = list(hex_k(
                BRUSH_ACTIVE[k] if k == key else BRUSH_COLORS[k]
            ))
        logging.debug('Penseltype: %s', key)

    def _set_draw_color(self, col):
        """
        Oppdaterer draw_color paa DrawCanvas.
        VIKTIG: setter draw_canvas.draw_color, IKKE draw_canvas.color.
        draw_canvas.color er Kivy Image sin tint-RGBA og maa ikke roeres.
        """
        if self.draw_canvas:
            self.draw_canvas.draw_color = col
        # Oppdater den lille fargesirkelen ved siden av "Velg farge"-knappen
        if hasattr(self, '_cur_color_btn'):
            self._cur_color_btn.btn_color = list(hex_k(col))
        # Oppdater eventuelle popup-fargeknapper (hvis popupen er åpen)
        for h, btn in self._col_btns.items():
            if h == col:
                r, g, b, _ = hex_k(h)
                btn.btn_color = [min(r + 0.28, 1), min(g + 0.28, 1), min(b + 0.28, 1), 1]
            else:
                btn.btn_color = list(hex_k(h))

    def _on_size_change(self, slider, val):
        if self.draw_canvas:
            self.draw_canvas.size_px = int(val)
        self._size_lbl.text = f' {int(val)}' 

    def _save_drawing(self, *_):
        if not self.draw_canvas:
            return
        fname = datetime.now().strftime('tegning_%Y%m%d_%H%M%S.png')
        path  = os.path.join(DRAW_DIR, fname)
        try:
            self.draw_canvas.save_to(path)
            self._toast(f'Lagret:\n{fname}')
            logging.info('Tegning lagret: %s', path)
        except Exception:
            logging.exception('_save_drawing: feil')
            self._toast('Feil ved lagring!')

    def _open_color_popup(self):
        """
        Fargevalgpopup med to faner: Palett (rutenett) og Gradient (HSV-velger).
        Faneknappene bytter innholdsflaten uten å lukke popupen.
        """
        pop_ref     = [None]
        cur_col     = [getattr(self.draw_canvas, 'draw_color', '#000000')
                       if self.draw_canvas else '#000000']

        outer = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(10))

        # ── Faneknapper ────────────────────────────────────────────
        tab_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        btn_pal = mk_btn('Palett',   hex_k('#0D47A1'), h=dp(42), fs=14)
        btn_grd = mk_btn('Gradient', hex_k('#4D96FF'), h=dp(42), fs=14)
        tab_row.add_widget(btn_pal); tab_row.add_widget(btn_grd)
        outer.add_widget(tab_row)

        # ── Innholdsflate (byttes ved faneskift) ───────────────────
        content_box = BoxLayout(orientation='vertical')
        outer.add_widget(content_box)

        outer.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(48), fs=14,
            cb=lambda *_: pop_ref[0].dismiss(),
        ))

        # ── Bygger palett-panel ────────────────────────────────────
        def make_palette_panel():
            panel = BoxLayout(orientation='vertical', spacing=dp(6))
            panel.add_widget(Label(
                text='Velg farge:', size_hint_y=None, height=dp(26),
                font_size=fsp(14), bold=True,
                color=(0.08, 0.10, 0.35, 1), halign='center'))
            sv = ScrollView(do_scroll_x=False)
            grid = GridLayout(cols=6, spacing=dp(6), size_hint_y=None)
            grid.bind(minimum_height=grid.setter('height'))
            self._col_btns = {}
            for col_hex in PALETTE:
                cb = RBtn(size_hint=(None, None), size=(dp(46), dp(46)),
                          btn_color=list(hex_k(col_hex)), radius=dp(23))
                def pick_pal(b, c=col_hex):
                    self._set_draw_color(c)
                    cur_col[0] = c
                    pop_ref[0].dismiss()
                cb.bind(on_release=pick_pal)
                grid.add_widget(cb); self._col_btns[col_hex] = cb
            sv.add_widget(grid); panel.add_widget(sv)
            return panel

        # ── Bygger gradient-panel ──────────────────────────────────
        def make_gradient_panel():
            panel = BoxLayout(orientation='vertical', spacing=dp(6))
            panel.add_widget(Label(
                text='Dra i fargehjulet:', size_hint_y=None, height=dp(26),
                font_size=fsp(14), bold=True,
                color=(0.08, 0.10, 0.35, 1), halign='center'))
            def on_grd_color(hex_c):
                cur_col[0] = hex_c
                self._set_draw_color(hex_c)
            gp = GradientColorPicker(
                on_color=on_grd_color,
                initial_hex=cur_col[0],
                size_hint_y=None,
                height=dp(GradientColorPicker.TOTAL_H * 2),
            )
            panel.add_widget(gp)
            panel.add_widget(mk_btn(
                'Velg denne fargen', hex_k('#6BCB77'), h=dp(48), fs=15,
                cb=lambda *_: pop_ref[0].dismiss(),
            ))
            return panel

        panels = {'pal': None, 'grd': None}

        def show_tab(tab):
            content_box.clear_widgets()
            btn_pal.btn_color = list(hex_k('#0D47A1' if tab=='pal' else '#4D96FF'))
            btn_grd.btn_color = list(hex_k('#0D47A1' if tab=='grd' else '#4D96FF'))
            if tab == 'pal':
                if panels['pal'] is None:
                    panels['pal'] = make_palette_panel()
                content_box.add_widget(panels['pal'])
                self._set_draw_color(cur_col[0])
            else:
                if panels['grd'] is None:
                    panels['grd'] = make_gradient_panel()
                content_box.add_widget(panels['grd'])

        btn_pal.bind(on_release=lambda *_: show_tab('pal'))
        btn_grd.bind(on_release=lambda *_: show_tab('grd'))

        pop = Popup(title='Farge', content=outer, size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        show_tab('pal')
        pop.open()

    # ══════════════════════════════════════════════════
    #  POPUP – REDIGER MAPPE
    # ══════════════════════════════════════════════════

    # ══════════════════════════════════════════════════
    #  HANDLINGSREKKER – navigasjon og listeskjerm
    # ══════════════════════════════════════════════════

    def _nav_sequences(self):
        """Naviger fra hjemskjerm til handlingsrekke-listen."""
        self._push('home')
        self._show_sequences()

    def _show_sequences(self, **_):
        """Viser listen over alle lagrede handlingsrekker."""
        self._cur_scr = 'sequences'
        self._set_title('Handlingsrekker')

        outer = BoxLayout(
            orientation='vertical',
            spacing=dp(10), padding=dp(12),
        )

        if self.edit_mode:
            outer.add_widget(mk_btn(
                '+  Ny handlingsrekke', hex_k('#6BCB77'), h=dp(52),
                cb=lambda *_: self._seq_editor_popup(None),
            ))

        seqs = self.data.get('sequences', [])
        if not seqs:
            outer.add_widget(Label(
                text='Ingen handlingsrekker ennå.\nTrykk "Red." og "+" for å lage en.',
                font_size=sp(16), color=(0.4, 0.4, 0.5, 1),
                halign='center', valign='middle',
            ))
        else:
            sv = ScrollView()
            vbox = BoxLayout(
                orientation='vertical',
                spacing=dp(10), size_hint_y=None,
            )
            vbox.bind(minimum_height=vbox.setter('height'))
            for seq in seqs:
                vbox.add_widget(self._make_seq_tile(seq))
            sv.add_widget(vbox)
            outer.add_widget(sv)

        self._set_content(outer)

    def _make_seq_tile(self, seq):
        """Lager en flis for én handlingsrekke i listen."""
        n    = len(seq.get('items', []))
        edit = self.edit_mode
        h    = dp(106) if edit else dp(72)

        tile = RBox(
            orientation='vertical',
            size_hint_y=None, height=h,
            spacing=dp(4), padding=(dp(6), dp(6)),
            box_color=(1.0, 1.0, 1.0, 1.0), radius=dp(16),
        )

        lbl = f'{seq["name"]}  ({n} {"bilde" if n == 1 else "bilder"})'
        if edit:
            tap = lambda s=seq: self._seq_editor_popup(s)
        else:
            tap = lambda s=seq: self._play_sequence(s)

        main_btn = RBtn(
            text=lbl,
            btn_color=list(hex_k('#4ECDC4')),
            color=(0.02, 0.12, 0.18, 1),
            bold=True, font_size=sp(17),
            radius=dp(14),
        )
        main_btn.bind(on_release=lambda b, t=tap: t())
        tile.add_widget(main_btn)

        if edit:
            h = dp(106) + dp(42)
            tile.height = h
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            row.add_widget(mk_btn(
                'Eksporter', hex_k('#FF9F43'), h=dp(38), fs=12,
                cb=lambda *_, s=seq: self._export_sequence(s),
            ))
            row.add_widget(mk_btn(
                'QR', hex_k('#4D96FF'), h=dp(38), fs=12,
                cb=lambda *_, s=seq: self._show_qr_popup(
                    'Handlingsrekke: ' + s['name'] + '\n' +
                    '\n'.join(f'{i+1}. {it["name"]}' for i, it in enumerate(s.get('items',[]))),
                    f'QR: {s["name"]}'),
            ))
            row.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=dp(38), fs=12,
                cb=lambda *_, s=seq: self._del_sequence(s),
            ))
            tile.add_widget(row)

        return tile

    # ── Spiller ───────────────────────────────────────────────────

    def _play_sequence(self, seq):
        """
        Åpner et fullskjerm-popup som viser handlingsrekkens bilder ett
        for ett. Trykk på bildet for å gå til neste; ved siste bilde
        lukkes popupen automatisk.
        """
        items = [
            it for it in seq.get('items', [])
            if it.get('image') and os.path.exists(it['image'])
        ]
        if not items:
            self._toast('Ingen bilder i handlingsrekken.\nLegg til bilder i redigeringsmodus.')
            return

        state = {'idx': 0}

        # ── Faste UI-elementer ────────────────────────────────────
        layout = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(8))

        prog_lbl = Label(
            text='', size_hint_y=None, height=dp(36),
            font_size=sp(15), bold=True,
            color=(0.08, 0.10, 0.35, 1), halign='center',
        )
        prog_lbl.bind(size=prog_lbl.setter('text_size'))

        img_box  = BoxLayout()   # Inneholder TappableImage, byttes ut per steg

        name_lbl = Label(
            text='', size_hint_y=None, height=dp(50),
            font_size=sp(22), bold=True,
            color=(0.08, 0.10, 0.35, 1), halign='center',
        )
        name_lbl.bind(size=name_lbl.setter('text_size'))

        instr_lbl = Label(
            text='', size_hint_y=None, height=dp(28),
            font_size=sp(13), color=(0.45, 0.48, 0.55, 1),
            halign='center',
        )
        instr_lbl.bind(size=instr_lbl.setter('text_size'))

        for w in [prog_lbl, img_box, name_lbl, instr_lbl]:
            layout.add_widget(w)

        pop = Popup(
            title=seq['name'], content=layout,
            size_hint=(1, 1),
        )

        def show_step(idx):
            """Oppdaterer popupen til å vise steg idx."""
            img_box.clear_widgets()
            it      = items[idx]
            is_last = (idx == len(items) - 1)

            prog_lbl.text  = f'Steg {idx + 1} av {len(items)}'
            name_lbl.text  = it.get('name', '')
            instr_lbl.text = (
                'Trykk på bildet for å avslutte'
                if is_last else
                'Trykk på bildet for neste steg'
            )
            if is_last:
                Clock.schedule_once(lambda *_: launch_confetti(2.2), 0.3)

            def advance(*_):
                if is_last:
                    pop.dismiss()
                else:
                    nxt = idx + 1
                    state['idx'] = nxt
                    show_step(nxt)

            img_box.add_widget(TappableImage(
                advance, source=it['image'],
                allow_stretch=True, keep_ratio=True,
            ))

        show_step(0)
        pop.open()
        logging.info('Starter handlingsrekke: %s (%d steg)', seq['name'], len(items))

    # ── Eksport ───────────────────────────────────────────────────

    def _export_sequence(self, seq):
        """
        Eksporterer handlingsrekken til /sdcard/Download/[navn]_handlingsrekke/.
        Viser popup med spinner mens eksport pågår i bakgrunnstråd.
        """
        import threading
        items = seq.get('items', [])
        if not items:
            self._toast('Ingen bilder å eksportere.')
            return
        safe       = seq['name'].replace(' ', '_').replace('/', '_')
        export_dir = os.path.join(DOWNLOAD_DIR, f'{safe}_handlingsrekke')

        # ── Spinner-popup ─────────────────────────────────────────
        spin_box = BoxLayout(orientation='vertical',
                             spacing=dp(16), padding=dp(20))
        spin_box.add_widget(Label(
            text='Eksporterer...', font_size=fsp(16), bold=True,
            color=(0.08, 0.10, 0.35, 1),
            size_hint_y=None, height=dp(32), halign='center'))
        pb = ProgressBar(max=100, value=0,
                         size_hint_y=None, height=dp(16))
        spin_box.add_widget(pb)
        spin_box.add_widget(Label(
            text=f'{safe}_handlingsrekke/', font_size=fsp(12),
            color=(0.4, 0.44, 0.55, 1),
            size_hint_y=None, height=dp(24), halign='center'))
        spin_pop = Popup(
            title='', content=spin_box,
            size_hint=POPUP_SMALL,
            auto_dismiss=False,
            separator_height=0)
        spin_pop.open()

        _pb_dir = [1]
        def _pulse_pb(dt):
            pb.value = (pb.value + 3 * _pb_dir[0]) % 101
            if pb.value >= 100: _pb_dir[0] = -1
            if pb.value <= 0:   _pb_dir[0] =  1
        _pb_event = Clock.schedule_interval(_pulse_pb, 0.03)

        def _do():
            try:
                os.makedirs(export_dir, exist_ok=True)
                manifest = [f'Handlingsrekke: {seq["name"]}\n']
                for i, it in enumerate(items, 1):
                    img_path = it.get('image', '')
                    if img_path and os.path.exists(img_path):
                        ext      = os.path.splitext(img_path)[1].lower() or '.png'
                        dst_name = f'{i:02d}_{it["name"].replace(" ", "_")}{ext}'
                        shutil.copy2(img_path, os.path.join(export_dir, dst_name))
                        manifest.append(f'{i}. {it["name"]}  ->  {dst_name}')
                    else:
                        manifest.append(f'{i}. {it["name"]}  (ingen bildefil)')
                txt_path = os.path.join(export_dir, 'rekkefølge.txt')
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(manifest))
                logging.info('Eksportert sekvens: %s', export_dir)
                def _done(*_):
                    _pb_event.cancel()
                    spin_pop.dismiss()
                    self._toast(f'Eksportert til Nedlastinger:\n{safe}_handlingsrekke/')
                Clock.schedule_once(_done, 0)
            except Exception as ex:
                _msg = str(ex)
                def _err(*_):
                    _pb_event.cancel()
                    spin_pop.dismiss()
                    self._toast(f'Eksport feilet: {_msg}')
                    logging.exception('_export_sequence: feil')
                Clock.schedule_once(_err, 0)

        threading.Thread(target=_do, daemon=True).start()

    def _del_sequence(self, seq):
        item_count = len(seq.get('items', []))
        detail = (f' med {item_count} bilde' + ('r' if item_count != 1 else '')
                  if item_count else '')
        self._confirm(
            title='Slette handlingsrekke?',
            message=f'Handlingsrekken "{seq.get("name", "")}"{detail} '
                    f'vil forsvinne fra appen.',
            on_confirm=lambda: self._do_del_sequence(seq),
        )

    def _do_del_sequence(self, seq):
        self.data['sequences'] = [
            s for s in self.data.get('sequences', []) if s['id'] != seq['id']
        ]
        save_struct(self.data)
        self._show_sequences()

    # ── Rediger sekvens ───────────────────────────────────────────

    def _seq_editor_popup(self, seq):
        """
        Popup for å opprette (seq=None) eller redigere en handlingsrekke.
        Viser: navnfelt, scrollbar bildeliste med slette-knapper,
        knapper for å legge til fra eksisterende ASK-mapper eller fra enhet.
        """
        import copy as _copy
        new_seq   = seq is None
        seq_items = _copy.deepcopy(seq.get('items', [])) if seq else []
        pop_ref   = [None]

        # ── Navn ─────────────────────────────────────────────────
        layout = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(14))

        layout.add_widget(Label(
            text='Navn på handlingsrekken:',
            size_hint_y=None, height=dp(28),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        name_inp = smart_input(
            text='' if new_seq else seq['name'],
            hint='Navn på handlingsrekken',
            on_save=lambda: on_save(),
        )
        layout.add_widget(name_inp)

        # ── Bildeliste ────────────────────────────────────────────
        count_lbl = Label(
            text='', size_hint_y=None, height=dp(26),
            font_size=sp(14), color=(0.25, 0.25, 0.25, 1), halign='left',
        )
        layout.add_widget(count_lbl)

        list_sv = ScrollView(size_hint_y=None, height=dp(200))
        list_box = BoxLayout(
            orientation='vertical', spacing=dp(4), size_hint_y=None,
        )
        list_box.bind(minimum_height=list_box.setter('height'))
        layout.add_widget(list_sv)
        list_sv.add_widget(list_box)

        def refresh_list():
            list_box.clear_widgets()
            count_lbl.text = f'Bilder i rekken: {len(seq_items)}'
            for i, it in enumerate(seq_items):
                row = RBox(
                    size_hint_y=None, height=dp(52),
                    spacing=dp(6), padding=(dp(6), dp(4)),
                    box_color=(0.96, 0.97, 1.0, 1.0), radius=dp(14),
                    orientation='horizontal',
                )
                # Miniatyr
                if it.get('image') and os.path.exists(it['image']):
                    row.add_widget(Image(
                        source=it['image'],
                        size_hint=(None, 1), width=dp(44),
                        allow_stretch=True, keep_ratio=True,
                    ))
                row.add_widget(Label(
                    text=f'{i + 1}.  {it["name"]}',
                    font_size=sp(14), color=(0.08, 0.08, 0.08, 1),
                    halign='left',
                ))
                row.add_widget(mk_btn(
                    'Fjern', hex_k('#FF6B6B'), h=dp(44), fs=12,
                    size_hint_x=None, width=dp(72),
                    cb=lambda *_, idx=i: (seq_items.pop(idx), refresh_list()),
                ))
                list_box.add_widget(row)

        refresh_list()

        # ── Legg til-knapper ──────────────────────────────────────
        add_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        add_row.add_widget(mk_btn(
            'Fra mapper', hex_k('#4D96FF'), h=dp(48), fs=14,
            cb=lambda *_: self._seq_pick_from_folders(seq_items, refresh_list),
        ))
        add_row.add_widget(mk_btn(
            'Fra enhet', hex_k('#FF9F43'), h=dp(48), fs=14,
            cb=lambda *_: self._seq_pick_from_device(seq_items, refresh_list),
        ))
        layout.add_widget(add_row)

        # ── Lagre / Avbryt ────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))

        def on_save(*_):
            nm = name_inp.text.strip()
            if not nm:
                self._toast('Skriv inn et navn.')
                return
            if new_seq:
                if 'sequences' not in self.data:
                    self.data['sequences'] = []
                self.data['sequences'].append({
                    'id':    str(uuid.uuid4()),
                    'name':  nm,
                    'items': seq_items,
                })
            else:
                seq.update({'name': nm, 'items': seq_items})
            save_struct(self.data)
            pop_ref[0].dismiss()
            self._show_sequences()

        btn_row.add_widget(mk_btn('Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_save))
        btn_row.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss(),
        ))
        layout.add_widget(btn_row)

        pop = Popup(
            title='Ny handlingsrekke' if new_seq else f'Rediger: {seq["name"]}',
            content=layout,
            size_hint=POPUP_FULL,
        )
        pop_ref[0] = pop
        pop.open()

    def _seq_pick_from_folders(self, seq_items, refresh_fn):
        """
        Viser alle ASK-bilder fra alle mapper i et blaingsrutenett.
        Brukeren trykker på et bilde for å legge det til i rekken.
        """
        import copy as _copy
        all_items = [
            _copy.deepcopy(it)
            for fo in self.data.get('folders', [])
            for it in fo.get('items', [])
            if it.get('image') and os.path.exists(it['image'])
        ]

        if not all_items:
            self._toast('Ingen ASK-bilder funnet.\nLegg til bilder i mappene først.')
            return

        pick_ref = [None]
        layout   = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
        layout.add_widget(Label(
            text='Trykk på et bilde for å legge det til i rekken:',
            size_hint_y=None, height=dp(30),
            font_size=sp(14), color=(0.1, 0.1, 0.1, 1), halign='center',
        ))

        grid = GridLayout(cols=3, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        for it in all_items:
            cell = BoxLayout(
                orientation='vertical',
                size_hint_y=None, height=dp(116), spacing=dp(2),
            )

            def make_pick(item=it):
                def on_pick(*_):
                    seq_items.append(item)
                    refresh_fn()
                    pick_ref[0].dismiss()
                return on_pick

            cell.add_widget(TappableImage(
                make_pick(),
                source=it['image'],
                size_hint=(1, None), height=dp(80),
                allow_stretch=True, keep_ratio=True,
            ))
            lbl = Label(
                text=it['name'], font_size=sp(11),
                color=(0.1, 0.1, 0.1, 1), halign='center',
                size_hint_y=None, height=dp(28),
            )
            lbl.bind(size=lbl.setter('text_size'))
            cell.add_widget(lbl)
            grid.add_widget(cell)

        sv = ScrollView()
        sv.add_widget(grid)
        layout.add_widget(sv)
        layout.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pick_ref[0].dismiss(),
        ))

        pick_pop = Popup(
            title='Velg ASK-bilde',
            content=layout, size_hint=POPUP_LARGE,
        )
        pick_ref[0] = pick_pop
        pick_pop.open()

    def _seq_pick_from_device(self, seq_items, refresh_fn):
        """Åpner Android-bildevelger for å legge bilde(r) til i handlingsrekken."""
        def on_picked(result):
            if not result:
                return
            # Normaliser: støtter enkeltbilde (str) og flervalg (list)
            paths = result if isinstance(result, list) else [result]
            added = 0
            for dst in paths:
                if not dst:
                    continue
                fname    = os.path.basename(dst)
                name_sug = os.path.splitext(fname)[0].replace('_', ' ')
                seq_items.append({'id': str(uuid.uuid4()), 'name': name_sug, 'image': dst})
                logging.info('Sekvens: bilde lagt til fra enhet: %s', dst)
                added += 1
            if added:
                refresh_fn()
                msg = (f'Lagt til: {added} bilder' if added > 1
                       else f'Lagt til: {os.path.basename(paths[0])}')
                self._toast(msg)
        _open_android_picker(on_picked)

    def _init_tts(self):
        """
        Plyer sin TTS-wrapper håndterer Android TextToSpeech
        internt uten at vi trenger PythonJavaClass-callbacks.
        Ingen initialisering nødvendig – plyer.tts.speak() er
        tilstandsløs og kaller Android TTS direkte.
        """
        pass   # plyer krever ingen manuell initialisering

    def _speak_now(self, text):
        """Kaller plyer.tts.speak() direkte."""
        try:
            from plyer import tts as plyer_tts
            plyer_tts.speak(text)
            logging.info('TTS (plyer) talte: %s', text[:30])
        except Exception:
            logging.exception('_speak_now (plyer): feil')

    def _speak(self, text):
        """
        Les opp tekst via plyer.tts (Android TextToSpeech).
        plyer er den anbefalte abstraksjonslaget for TTS i Kivy-apper
        og unngår alle PythonJavaClass-callback-problemer.
        """
        if not self.data.get('settings', {}).get('tts_enabled', False):
            return
        if not text or not text.strip():
            return
        # Liten forsinkelse sikrer at UI er ferdig oppdatert
        # før lydkortet aktiveres (unngår kortingsartefakter)
        Clock.schedule_once(lambda *_: self._speak_now(text), 0.2)

    # ══════════════════════════════════════════════════
    #  INNSTILLINGER
    # ══════════════════════════════════════════════════

    def _nav_settings(self):
        self._push('home')
        self._show_settings()

    def _show_settings(self, **_):
        self._cur_scr = 'settings'
        self._set_title('Innstillinger')
        st = self.data.setdefault('settings', {'tts_enabled': False, 'font_scale': 1.0})
        outer = BoxLayout(orientation='vertical', spacing=dp(16), padding=dp(16))

        # ── Høykontrast ──────────────────────────────────────────
        outer.add_widget(Label(text='Høykontrast:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        hc_row  = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        is_hc_on = st.get('high_contrast', False)
        hc_on  = mk_btn('På',  hex_k('#000000' if is_hc_on else '#546E7A'),
                         fg=(1,1,1,1), h=dp(52), fs=16)
        hc_off = mk_btn('Av',  hex_k('#4D96FF' if not is_hc_on else '#90CAF9'),
                         fg=(1,1,1,1), h=dp(52), fs=16)
        def set_hc(val):
            st['high_contrast'] = val
            save_struct(self.data)
            apply_high_contrast(val)
            hc_on.btn_color  = list(hex_k('#000000' if val else '#546E7A'))
            hc_off.btn_color = list(hex_k('#4D96FF' if not val else '#90CAF9'))
            # Gjenbygg innstillingsskjermen så farger oppdateres
            Clock.schedule_once(lambda *_: self._show_settings(), 0.15)
        hc_on.bind( on_release=lambda *_: set_hc(True))
        hc_off.bind(on_release=lambda *_: set_hc(False))
        hc_row.add_widget(hc_on); hc_row.add_widget(hc_off)
        outer.add_widget(hc_row)
        _lbl_hc = Label(
            text='Svart bakgrunn og hvit tekst på alle knapper (WCAG AAA, 7:1). Gjelder fra neste skjerminnlasting.',
            size_hint_y=None, height=dp(44),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1),
            halign='left', valign='top')
        _lbl_hc.bind(width=lambda w,v: setattr(w,'text_size',(v,None)))
        outer.add_widget(_lbl_hc)

        # ── Skjermretning (fase 1 – landskapsstøtte) ─────────────
        # Eksplisitt vippe-knapp i stedet for automatisk
        # sensor-rotasjon hele tiden – forutsigbart for ASK-bruk
        # (spesielt viktig om barnet ser på skjermen). Brukeren
        # velger selv NÅR appen skal følge enhetens vipping, f.eks.
        # når et nettbrett settes opp liggende.
        outer.add_widget(Label(text='Skjermretning:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        or_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        or_portrait = mk_btn(
            'Stående', hex_k('#000000' if not self._is_landscape else '#546E7A'),
            fg=(1, 1, 1, 1), h=dp(52), fs=16,
            cb=lambda *_: self._toggle_orientation()
                if self._is_landscape else None)
        or_landscape = mk_btn(
            'Liggende', hex_k('#4D96FF' if self._is_landscape else '#90CAF9'),
            fg=(1, 1, 1, 1), h=dp(52), fs=16,
            cb=lambda *_: self._toggle_orientation()
                if not self._is_landscape else None)
        or_row.add_widget(or_portrait); or_row.add_widget(or_landscape)
        outer.add_widget(or_row)
        _lbl_or = Label(
            text='Bytter skjermretning umiddelbart. Mappe- og bilderutenett '
                 'tilpasser seg (4 → 6 kolonner i liggende).',
            size_hint_y=None, height=dp(44),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1),
            halign='left', valign='top')
        _lbl_or.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        outer.add_widget(_lbl_or)

        # ── Sveipenavigasjon ─────────────────────────────────────
        outer.add_widget(Label(text='Sveipenavigasjon:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        sw_row   = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        is_sw_on = st.get('swipe_nav', False)
        sw_on  = mk_btn('På', hex_k('#2E7D32' if is_sw_on  else '#6BCB77'), h=dp(52), fs=16)
        sw_off = mk_btn('Av', hex_k('#B71C1C' if not is_sw_on else '#FF6B6B'), h=dp(52), fs=16)
        def set_sw(val):
            st['swipe_nav'] = val
            save_struct(self.data)
            sw_on.btn_color  = list(hex_k('#2E7D32' if val else '#6BCB77'))
            sw_off.btn_color = list(hex_k('#B71C1C' if not val else '#FF6B6B'))
        sw_on.bind( on_release=lambda *_: set_sw(True))
        sw_off.bind(on_release=lambda *_: set_sw(False))
        sw_row.add_widget(sw_on); sw_row.add_widget(sw_off)
        outer.add_widget(sw_row)
        _lbl_sw = Label(
            text='Sveip høyre for tilbake, venstre for neste. Kan forstyrre scrolling.',
            size_hint_y=None, height=dp(32),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1),
            halign='left', valign='middle')
        _lbl_sw.bind(width=lambda w,v: setattr(w,'text_size',(v,None)))
        outer.add_widget(_lbl_sw)

        outer.add_widget(Label(text='Les opp etiketter (tale):', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        tts_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        is_on   = st.get('tts_enabled', False)
        tts_on  = mk_btn('Pa',  hex_k('#2E7D32' if is_on else '#6BCB77'), h=dp(52), fs=16)
        tts_off = mk_btn('Av',  hex_k('#B71C1C' if not is_on else '#FF6B6B'), h=dp(52), fs=16)
        def set_tts(val):
            st['tts_enabled'] = val
            save_struct(self.data)
            if val:
                self._init_tts()
            tts_on.btn_color  = list(hex_k('#2E7D32' if val else '#6BCB77'))
            tts_off.btn_color = list(hex_k('#B71C1C' if not val else '#FF6B6B'))
        tts_on.bind( on_release=lambda *_: set_tts(True))
        tts_off.bind(on_release=lambda *_: set_tts(False))
        tts_row.add_widget(tts_on); tts_row.add_widget(tts_off)
        outer.add_widget(tts_row)
        outer.add_widget(Label(
            text='Trykk på et ASK-bilde for å høre etiketten.',
            size_hint_y=None, height=dp(26),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1), halign='left'))

        outer.add_widget(Label(text='Tekststorrelse:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        scale_opts = [('Liten', 0.82), ('Normal', 1.0), ('Stor', 1.20), ('Storst', 1.42)]
        cur_sc     = st.get('font_scale', 1.0)
        sg = GridLayout(cols=4, spacing=dp(8), size_hint_y=None, height=dp(58))
        sb_list = []
        for lbl, val in scale_opts:
            active = abs(val - cur_sc) < 0.05
            b = mk_btn(lbl, hex_k('#0D47A1' if active else '#4D96FF'), h=dp(54), fs=14)
            def pick(_, v=val, sbl=sb_list, so=scale_opts):
                st['font_scale'] = v
                save_struct(self.data)
                for sb2, (_, sv2) in zip(sbl, so):
                    sb2.btn_color = list(hex_k('#0D47A1' if abs(sv2-v)<0.05 else '#4D96FF'))
            b.bind(on_release=pick)
            sg.add_widget(b); sb_list.append(b)
        outer.add_widget(sg)
        outer.add_widget(Label(
            text='Ny storrelse gjelder fra neste skjerminnlasting.',
            size_hint_y=None, height=dp(26),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1), halign='left'))

        # ── Bildemappe-info ──────────────────────────────────────────
        outer.add_widget(Label(
            text='Importer bilder:',
            size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True,
            color=(0.08, 0.10, 0.35, 1), halign='left'))
        _lbl_img = Label(
            text=(
                'Trykk "Last opp" i en mappe for å velge bilde.\n'
                'Bildevelgeren åpnes – ingen tillatelser trengs.\n\n'
                'Bilder lagres i appens private mappe.\n'
                'Eksporter via "Last ned" for å kopiere til Nedlastinger.'
            ),
            size_hint_y=None, height=dp(100),
            font_size=fsp(12), color=(0.3, 0.3, 0.4, 1),
            halign='left', valign='top')
        _lbl_img.bind(width=lambda w,v: setattr(w,'text_size',(v,None)))
        outer.add_widget(_lbl_img)


        # ── Konfetti-knapp ───────────────────────────────────────
        outer.add_widget(Label(text='Konfetti-knapp:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        kb_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        is_kb_on = getattr(self, '_confetti_btn_visible', False)
        kb_on  = mk_btn('På', hex_k('#2E7D32' if is_kb_on else '#6BCB77'), h=dp(52), fs=16)
        kb_off = mk_btn('Av', hex_k('#B71C1C' if not is_kb_on else '#FF6B6B'), h=dp(52), fs=16)
        def set_kb(val):
            self._toggle_confetti_btn(val)
            kb_on.btn_color  = list(hex_k('#2E7D32' if val else '#6BCB77'))
            kb_off.btn_color = list(hex_k('#B71C1C' if not val else '#FF6B6B'))
        kb_on.bind( on_release=lambda *_: set_kb(True))
        kb_off.bind(on_release=lambda *_: set_kb(False))
        kb_row.add_widget(kb_on); kb_row.add_widget(kb_off)
        outer.add_widget(kb_row)

        # ── Varsler ──────────────────────────────────────────────────
        outer.add_widget(Label(text='Push-varsler:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        outer.add_widget(Label(
            text='Varsler sendes kun når appen er i bakgrunnen / skjermen er av.',
            font_size=fsp(13), color=(0.4, 0.4, 0.5, 1),
            size_hint_y=None, height=dp(28), halign='left'))

        def _mk_notif_row(label, key):
            on_now = self.data.get('settings', {}).get(key, False)
            row = BoxLayout(size_hint_y=None, height=rdp(56), spacing=dp(8))
            btn_on  = mk_btn('På',  hex_k('#6BCB77' if on_now     else '#B0B8C4'),
                             h=rdp(50), fs=14)
            btn_off = mk_btn('Av',  hex_k('#EF5350' if not on_now else '#B0B8C4'),
                             h=rdp(50), fs=14)
            def _set(val, b_on=btn_on, b_off=btn_off, k=key):
                self.data.setdefault('settings', {})[k] = val
                b_on.btn_color  = list(hex_k('#6BCB77' if val  else '#B0B8C4'))
                b_off.btn_color = list(hex_k('#EF5350' if not val else '#B0B8C4'))
                save_struct(self.data)
                if k == 'notifications_dagsplan':
                    self._reschedule_dagsplan_notifs()
                if val:
                    self._request_notification_permission()
            btn_on.bind( on_release=lambda *_: _set(True))
            btn_off.bind(on_release=lambda *_: _set(False))
            row.add_widget(Label(text=label, font_size=fsp(15),
                                 color=(0.1, 0.1, 0.3, 1), halign='left'))
            row.add_widget(btn_on)
            row.add_widget(btn_off)
            return row

        outer.add_widget(_mk_notif_row('Tidsur:',    'notifications_timer'))
        outer.add_widget(_mk_notif_row('Dagsplan:',  'notifications_dagsplan'))

        # ── Hjelp ────────────────────────────────────────────────────
        outer.add_widget(Label(text='Hjelp:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08,0.10,0.35,1), halign='left'))
        outer.add_widget(mk_btn('Les brukerveiledning', hex_k('#4D96FF'), h=dp(54), fs=15,
            cb=lambda *_: self._show_help_popup()))
        outer.add_widget(mk_btn('Vis widget-logg', hex_k('#78909C'), h=dp(48), fs=14,
            cb=lambda *_: self._show_widget_log()))
        outer.add_widget(mk_btn('Vis diagnoselogg', hex_k('#546E7A'), h=dp(48), fs=14,
            cb=lambda *_: self._show_diag_log()))

        # ── Personvern ───────────────────────────────────────────────
        outer.add_widget(Label(
            text='Personvern:',
            size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True,
            color=(0.08, 0.10, 0.35, 1), halign='left'))
        outer.add_widget(mk_btn(
            'Les personvernerklæringen',
            hex_k('#4D96FF'), h=dp(54), fs=15,
            cb=lambda *_: self._show_privacy_popup()))

        # ── Omvisning ────────────────────────────────────────────
        # Lar brukeren se den guidede omvisningen igjen senere.
        outer.add_widget(Label(text='Hjelp:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1),
            halign='left'))
        outer.add_widget(mk_btn(
            '🎯  Vis omvisning på nytt',
            hex_k('#6BCB77'), h=dp(54), fs=15,
            cb=lambda *_: self._show_onboarding()))

        # ── Barn-modus ───────────────────────────────────────────
        outer.add_widget(Label(text='Barn-modus:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08, 0.10, 0.35, 1), halign='left'))
        is_barn = st.get('barn_modus', False)
        barn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        barn_on  = mk_btn('På',  hex_k('#FF9F43' if is_barn  else '#546E7A'), h=dp(52), fs=16)
        barn_off = mk_btn('Av',  hex_k('#4D96FF' if not is_barn else '#90CAF9'), h=dp(52), fs=16)
        def set_barn(val):
            st['barn_modus'] = val
            save_struct(self.data)
            barn_on.btn_color  = list(hex_k('#FF9F43' if val else '#546E7A'))
            barn_off.btn_color = list(hex_k('#4D96FF' if not val else '#90CAF9'))
        barn_on.bind( on_release=lambda *_: set_barn(True))
        barn_off.bind(on_release=lambda *_: set_barn(False))
        barn_row.add_widget(barn_on); barn_row.add_widget(barn_off)
        outer.add_widget(barn_row)
        outer.add_widget(Label(
            text='2-kolonne rutenett og PIN-beskyttet redigering for å hindre utilsiktede endringer.',
            size_hint_y=None, height=dp(44), font_size=fsp(12),
            color=(0.5, 0.5, 0.5, 1), halign='left', valign='top'))

        # PIN-oppsett for barn-modus
        cur_pin = st.get('barn_modus_pin', '')
        pin_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        pin_lbl = Label(
            text=f'PIN: {"*" * len(cur_pin) if cur_pin else "(ingen – kun knapp-lås)"}',
            font_size=fsp(13), color=(0.3, 0.34, 0.50, 1),
            halign='left', valign='middle', size_hint_x=1)
        pin_lbl.bind(size=pin_lbl.setter('text_size'))
        pin_row.add_widget(pin_lbl)

        def _set_pin_popup(*_):
            from kivy.uix.textinput import TextInput as _TI
            pbox = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(16))
            pbox.add_widget(Label(text='Ny PIN (4 siffer, la stå tomt for ingen PIN):',
                                  font_size=fsp(14), color=(0.06,0.08,0.30,1),
                                  size_hint_y=None, height=dp(38), halign='center'))
            pin_inp = _TI(hint_text='1234', multiline=False, input_filter='int',
                          max_chars=4, size_hint_y=None, height=dp(50),
                          font_size=fsp(18), halign='center')
            pbox.add_widget(pin_inp)
            pp = Popup(title='', content=pbox, size_hint=POPUP_SMALL, separator_height=0)
            def _save(*_):
                v = pin_inp.text.strip()
                st['barn_modus_pin'] = v
                save_struct(self.data)
                pin_lbl.text = f'PIN: {"*"*len(v) if v else "(ingen)"}'
                pp.dismiss()
            pbox.add_widget(mk_btn('Lagre PIN', hex_k('#4D96FF'), h=dp(48), fs=14, cb=_save))
            pbox.add_widget(mk_btn('Avbryt', hex_k('#78909C'), h=dp(44), fs=13,
                                   cb=lambda *_: pp.dismiss()))
            pp.open()

        pin_row.add_widget(mk_btn('Endre PIN', hex_k('#78909C'),
                                  h=dp(46), fs=12, size_hint_x=None, width=dp(110),
                                  cb=_set_pin_popup))
        outer.add_widget(pin_row)

        # Wrap outer i ScrollView slik at innstillinger kan rulles
        sv = ScrollView(do_scroll_x=False)
        inner = BoxLayout(
            orientation='vertical', spacing=dp(16),
            padding=dp(16), size_hint_y=None)
        inner.bind(minimum_height=inner.setter('height'))
        for w in list(outer.children[::-1]):
            outer.remove_widget(w)
            inner.add_widget(w)
        sv.add_widget(inner)
        self._set_content(sv)

    # ══════════════════════════════════════════════════
    #  PERSONVERNERKLÆRING
    # ══════════════════════════════════════════════════

    def _show_help_popup(self):
        """Brukerveiledning som beskriver alle funksjoner."""
        HELP = """KOMMUNIKASJONSTAVLE – BRUKERVEILEDNING

HURTIGRAD (under tittellinjen)
• Rekker – Handlingsrekker: visuelle sekvenser av bilder i rekkefølge
• Dagsplan – Dagsrytme: tidsbasert plan for dagen med klokkeslett
• Tidsur – Visuell nedtelling med rød pai som tømmes
• Spill – Bildepar-minnespill med symbolene dine
• Tegn – Fri tegning med ulike penseltyper og farger

NAVIGASJONSBAR (bunnen)
• Tilbake – Gå ett steg tilbake
• Hjem – Gå til startskjermen
• Søk – Søk lokalt i alle symboler ELLER hent fra ARASAAC (13 000+ norske symboler)
• Red. – Slå redigering av/på. I redigeringsmodus kan du legge til, flytte og slette
• Innst. – Innstillinger og denne veiledningen

MAPPER OG SYMBOLER
• Opprett mapper fra startskjermen i redigeringsmodus
• Trykk på en mappe for å åpne den
• I en mappe: legg til bilder via kamera, filvelger, tegning eller ARASAAC-søk
• Last ned symboler til Nedlastinger via «Ned»-knappen
• Flytt symboler mellom mapper via «Flytt»-knappen

ARASAAC-SØKET
• Skriv et norsk eller engelsk ord i søkefeltet
• Velg mellom «Lokalt» (egne bilder) og «ARASAAC» (nettbasert bibliotek)
• Trykk på et symbol for å laste det ned til en mappe

DAGSPLAN
• Legg til aktiviteter med start- og sluttid og valgfritt bilde
• Dagsplanen vises automatisk på hjemskjerm-widgeten
• Eksporter dagsplanen som bilde til Nedlastinger

HANDLINGSREKKER
• Opprett rekker med bilder i rekkefølge (f.eks. påkledningsrutine)
• Trykk på bildet for å spille av rekken bilde for bilde
• Konfetti vises automatisk når rekken er fullført
• Eksporter rekken som bilde

TIDSUR
• Velg tid fra forhåndsinnstillinger (1–10 min) eller slider
• Rød pai tømmes gradvis – lett å forstå for barn
• Konfetti og lydmelding når tiden er ute

INNSTILLINGER
• Høykontrast – svart/hvitt for bedre synlighet
• Tekststørrelse – fire nivåer
• Les opp – trykk på et symbol for å høre navnet
• Konfetti-knapp – alltid synlig på skjermen
"""
        from kivy.uix.scrollview import ScrollView
        layout = BoxLayout(orientation='vertical', padding=dp(10))
        sv = ScrollView()
        lbl = Label(
            text=HELP,
            font_name='NotoSans', font_size=fsp(13),
            color=(0.1,0.1,0.3,1),
            halign='left', valign='top',
            size_hint_y=None,
        )
        lbl.bind(width=lambda w,v: setattr(w,'text_size',(v,None)))
        lbl.bind(texture_size=lambda w,v: setattr(w,'height',v[1]))
        sv.add_widget(lbl)
        layout.add_widget(sv)
        Popup(title='Brukerveiledning', content=layout,
              size_hint=POPUP_LARGE).open()

    def _show_widget_log(self):
        """Viser widget_log.txt – logg over widget-prosesser og oppdateringer."""
        log_path = os.path.join(DATA_DIR, 'widget_log.txt') if DATA_DIR else None
        if not log_path or not os.path.exists(log_path):
            self._toast('Ingen widget-logg ennå.')
            return
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # Vis de 100 siste linjene, nyeste øverst
            text = ''.join(reversed(lines[-100:]))
        except Exception as e:
            text = f'Feil ved lesing: {e}'

        layout = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        # Topprad med tittel og slett-knapp
        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        top.add_widget(Label(text='Widget-logg (nyeste øverst)',
                             font_size=fsp(14), bold=True,
                             color=(0.1,0.1,0.3,1)))
        pop_ref = [None]
        def _clear(*_):
            try:
                open(log_path, 'w').close()
                self._toast('Logg tømt.')
                pop_ref[0].dismiss()
            except Exception:
                pass
        top.add_widget(mk_btn('Tøm', hex_k('#EF5350'), h=dp(40), fs=12,
            cb=_clear))
        layout.add_widget(top)

        sv = ScrollView()
        lbl = Label(
            text=text or '(tom)',
            font_name='NotoSans', font_size=fsp(11),
            color=(0.1,0.15,0.1,1),
            halign='left', valign='top',
            size_hint_y=None,
        )
        lbl.bind(width=lambda w,v: setattr(w,'text_size',(v,None)))
        lbl.bind(texture_size=lambda w,v: setattr(w,'height',v[1]))
        sv.add_widget(lbl)
        layout.add_widget(sv)

        pop = Popup(title='Widget-logg', content=layout,
                    size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        pop.open()

    def _show_diag_log(self):
        """
        Viser diag.log – detaljert diagnoselogg over oppstart og bildelasting.

        Loggen inneholder sesjonsnummer (S#N) slik at sesjon 1 (fersk
        installasjon, bilder usynlige) kan sammenlignes direkte med
        sesjon 2 (bilder synlige) for å finne rotårsaken.

        THUMB START/OK/FAIL – get_thumbnail()-kall med filstørrelse og timing
        COPY OK/TOMT        – shutil.copy2 + fsync-resultat per bilde
        TILE PIL_OK/FAIL    – om thumbnail ble satt direkte i _make_item_tile
        RETRY #N            – hvert retry-forsøk med filstatus og resultat
        """
        diag_path = DIAG_FILE
        if not diag_path or not os.path.exists(diag_path):
            self._toast('Ingen diagnoselogg ennå – åpne en mappe først.')
            return
        try:
            with open(diag_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # Vis de 80 siste linjene, nyeste øverst
            text = ''.join(reversed(lines[-80:]))
            n_lines = len(lines)
        except Exception as e:
            text    = f'Feil ved lesing: {e}'
            n_lines = 0

        layout  = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
        pop_ref = [None]

        # ── Topprad ──────────────────────────────────────────────
        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        top.add_widget(Label(
            text=f'Diagnoselogg  [{n_lines} linjer, siste 80 vises]',
            font_size=fsp(13), bold=True, color=(0.1, 0.1, 0.3, 1)))
        def _clear(*_):
            try:
                open(diag_path, 'w').close()
                self._toast('Diagnoselogg tømt.')
                pop_ref[0].dismiss()
            except Exception:
                pass
        top.add_widget(mk_btn('Tøm', hex_k('#EF5350'), h=dp(40), fs=12, cb=_clear))
        layout.add_widget(top)

        # ── Logginnhold ───────────────────────────────────────────
        sv  = ScrollView()
        lbl = Label(
            text=text or '(tom)',
            font_name='NotoSans', font_size=fsp(10),
            color=(0.05, 0.12, 0.08, 1),
            halign='left', valign='top',
            size_hint_y=None,
        )
        lbl.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        lbl.bind(texture_size=lambda w, v: setattr(w, 'height', v[1]))
        sv.add_widget(lbl)
        layout.add_widget(sv)

        pop = Popup(title='Diagnoselogg', content=layout,
                    size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        pop.open()

    def _show_privacy_popup(self):
        """
        Viser den fullstendige personvernerklæringen i et scrollbart popup.
        Teksten er bakt direkte inn i koden fra PERSONVERN.md.
        """
        policy_text = "PERSONVERNERKL\u00c6RING \u2013 KOMMUNIKASJONSTAVLE\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\nVersjon: 1.2  \nSist oppdatert: Mai 2025  \nUtvikler: Privat utvikler (ikke-kommersiell applikasjon)\n\n\n\n\nHVA ER KOMMUNIKASJONSTAVLE?\n\nKommunikasjonstavle er en Android-applikasjon utviklet for bruk i pedagogisk sammenheng i barnehage og skole. Appen er laget for \u00e5 st\u00f8tte kommunikasjon med barn ved hjelp av bilder og symboler (ASK \u2013 Alternativ og Supplerende Kommunikasjon).\n\n\n\n\nHVILKE OPPLYSNINGER SAMLES INN?\n\nIngen personopplysninger sendes fra denne appen.\n\nAll informasjon appen lagrer, befinner seg utelukkende p\u00e5 den enheten appen er installert p\u00e5. Det sendes ingenting til internett, ingen skytjeneste, ingen server og ingen tredjepart.\n\nAppen lagrer lokalt p\u00e5 enheten:\n- Mappestruktur og kategorier du oppretter\n- Bildefiler du laster opp\n- Tegninger du lager i appen\n- Innstillinger (tekstst\u00f8rrelse, tale p\u00e5/av)\n- En teknisk feillogg (`crash.log`) ved programfeil\n\nIngen av disse dataene forlater enheten.\n\n\n\n\nVIKTIG ADVARSEL OM BILDER AV BARN\n\nVi frar\u00e5der p\u00e5 det sterkeste \u00e5 laste opp fotografier av identifiserbare barn i appen.\n\nGrunnen er enkel: det er ikke n\u00f8dvendig i pedagogisk sammenheng. Pedagogiske ASK-symboler viser generelle konsepter \u2013 mat, aktiviteter, f\u00f8lelser \u2013 og trenger ikke \u00e5 knyttes til et bestemt barn. Symbolbiblioteker som PCS (Picture Communication Symbols) er nettopp utviklet for dette form\u00e5let.\n\nDersom bilder av identifiserbare barn likevel lastes opp, er dette en personopplysning underlagt GDPR (personvernforordningen). Behandlingsansvaret ligger da hos den institusjonen (barnehagen eller skolen) som bruker appen, ikke hos apputvikleren. Foresattes samtykke vil i slike tilfeller normalt v\u00e6re p\u00e5krevd.\n\n\n\n\nHVEM HAR BEHANDLINGSANSVARET?\n\nApputvikleren samler ikke inn, mottar eller har tilgang til noen data fra appen.\n\nBehandlingsansvar for eventuelle personopplysninger som legges inn i appen, ligger hos:\n- Den kommunen, det private selskapet eller den enkeltpersonen som installerer og bruker appen\n- I tr\u00e5d med norsk tolkning av GDPR (personopplysningsloven, LOV-2018-06-15-38)\n\n\n\n\nTREDJEPARTSBIBLIOTEKER OG AVHENGIGHETER\n\nAppen benytter f\u00f8lgende programvarekomponenter som er bakt inn i applikasjonen:\n\nKomponent  Form\u00e5l  Sender data?\nPython / Kivy  App-rammeverk  Nei\nPillow (PIL)  Bildebehandling  Nei\nqrcode  QR-kode-generering  Nei\nAndroid SDK  Android-plattform  Se Googles egne vilk\u00e5r\n\nAndroid-plattformen (Google) kan samle inn diagnostikk- og bruksdata uavhengig av denne appen, i henhold til Googles egne personvernvilk\u00e5r.\n\n\n\n\nSLETTING AV DATA\n\nAll data appen har lagret slettes automatisk n\u00e5r appen avinstalleres fra enheten. Det finnes ingen ekstern kopi \u00e5 be om sletting av.\n\n\u00d8nsker du \u00e5 slette enkeltdata mens appen er installert:\n- Bilder og mapper: Slett via redigeringsmodus i appen\n- Tegninger: Slett filene manuelt fra enhetens filsystem\n- All appdata: Avinstaller appen, eller g\u00e5 til Innstillinger \u2192 Apper \u2192 Kommunikasjonstavle \u2192 Lagring \u2192 Slett data\n\n\n\n\nPCS-SYMBOLER (PICTURE COMMUNICATION SYMBOLS)\n\nDersom denne versjonen av appen inkluderer PCS-symboler fra Tobii DynaVox, er disse brukt i henhold til lisensavtale med Tobii DynaVox. PCS\u00ae er et registrert varemerke tilh\u00f8rende Tobii DynaVox.\n\n\n\n\nUNIVERSELL UTFORMING\n\nAppen er utviklet med tanke p\u00e5 tilgjengelighet for brukere med ulike kommunikasjonsbehov. Justerbar tekstst\u00f8rrelse og h\u00f8ykontrastalternativer er tilgjengelig i innstillinger.\n\n\n\n\nKONTAKT\n\nSp\u00f8rsm\u00e5l om personvern eller appen kan rettes til apputvikleren via GitHub-prosjektets \u00abIssues\u00bb-seksjon.\n\n\n\n\nENDRINGER I PERSONVERNERKL\u00c6RINGEN\n\nVesentlige endringer i denne erkl\u00e6ringen vil gjenspeiles i versjonsnummeret \u00f8verst. Det anbefales \u00e5 lese erkl\u00e6ringen p\u00e5 nytt ved oppgradering av appen."

        outer = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(12))

        # Advarsel øverst – tydelig og umiddelbart synlig
        warn_box = RBox(
            size_hint_y=None, height=dp(56),
            box_color=(1.0, 0.94, 0.92, 1.0),
            radius=dp(14), padding=(dp(10), dp(8)),
        )
        warn_box.add_widget(Label(
            text='Advarsel: Last ikke opp bilder av barn',
            font_size=fsp(14), bold=True,
            color=(0.70, 0.08, 0.06, 1),
            halign='center', valign='middle',
        ))
        outer.add_widget(warn_box)

        # Scrollbar tekst
        sv  = ScrollView(do_scroll_x=False)
        lbl = Label(
            text=policy_text,
            font_size=fsp(13),
            color=(0.10, 0.12, 0.28, 1),
            halign='left', valign='top',
            size_hint_y=None,
            padding=(dp(4), dp(4)),
        )
        lbl.bind(
            width=lambda *_: lbl.setter('text_size')(lbl, (lbl.width, None)),
            texture_size=lambda *_: lbl.setter('height')(lbl, lbl.texture_size[1]),
        )
        sv.add_widget(lbl)
        outer.add_widget(sv)

        outer.add_widget(mk_btn(
            'Lukk', hex_k('#4D96FF'), h=dp(54),
            cb=lambda *_: pop.dismiss(),
        ))

        pop = Popup(
            title='Personvernerklæring – Kommunikasjonstavle',
            content=outer, size_hint=POPUP_LARGE,
        )
        pop.open()

    # ══════════════════════════════════════════════════
    #  QR-KODE
    # ══════════════════════════════════════════════════

    def _show_qr_popup(self, text, title='QR-kode'):
        """Genererer og viser QR-kode for gitt tekst."""
        try:
            import qrcode as _qr
            qr = _qr.QRCode(version=None,
                error_correction=_qr.constants.ERROR_CORRECT_M,
                box_size=9, border=3)
            qr.add_data(text)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color='black', back_color='white').convert('RGBA')
            pil_img = pil_img.resize((380, 380), PILImage.LANCZOS)

            raw = pil_img.tobytes()
            tex = Texture.create(size=(380, 380), colorfmt='rgba')
            tex.blit_buffer(raw, colorfmt='rgba', bufferfmt='ubyte')
            tex.flip_vertical()

            pop_ref = [None]
            layout  = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(12))
            qr_img  = Image(); qr_img.texture = tex
            layout.add_widget(qr_img)
            br = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
            br.add_widget(mk_btn('Lagre QR', hex_k('#6BCB77'), h=dp(50), fs=14,
                cb=lambda *_: self._save_qr(pil_img, title)))
            br.add_widget(mk_btn('Lukk', hex_k('#9CA3AF'), h=dp(50), fs=14,
                cb=lambda *_: pop_ref[0].dismiss()))
            layout.add_widget(br)
            pop = Popup(title=title, content=layout, size_hint=POPUP_MEDIUM)
            pop_ref[0] = pop; pop.open()
        except ImportError:
            self._toast('qrcode-pakken mangler. Legg til "qrcode" i buildozer.spec.')
        except Exception:
            logging.exception('_show_qr_popup: feil')
            self._toast('Feil ved QR-generering.')

    def _save_qr(self, pil_img, name):
        try:
            safe = name.replace(' ', '_').replace('/', '_')[:40]
            path = os.path.join(DOWNLOAD_DIR, f'qr_{safe}.png')
            pil_img.save(path)
            self._toast(f'QR lagret: qr_{safe}.png')
        except Exception:
            logging.exception('_save_qr: feil')
            self._toast('Feil ved lagring.')

    # ══════════════════════════════════════════════════
    #  DAGSRYTME
    # ══════════════════════════════════════════════════

    def _nav_dagsrytme(self):
        # Start alltid på dagens plan ved navigering inn til skjermen.
        # Brukeren kan deretter trykke andre dag-faner for å se/redigere dem.
        self._dr_selected_day = today_code()
        self._push('home')
        self._show_dagsrytme()

    def _show_dagsrytme(self, **_):
        self._cur_scr = 'dagsrytme'
        self._set_title('Dagsplaner')
        self._build_dagsrytme_ui(animate=True)
        if hasattr(self, '_dr_event') and self._dr_event:
            self._dr_event.cancel()
        self._dr_event = Clock.schedule_interval(
            lambda *_: self._build_dagsrytme_ui(animate=False), 30)

    def _dr_switch_day(self, code):
        """Bytter til en annen ukedag-fane."""
        self._dr_selected_day = code
        self._build_dagsrytme_ui(animate=True)

    def _dr_parse(self, s):
        """'HH:MM' → minutter siden midnatt."""
        try:
            h, m = s.split(':'); return int(h) * 60 + int(m)
        except Exception:
            return 0

    def _dr_fmt(self, minutes):
        """Formater minutter til lesbar tekst."""
        if minutes <= 0:
            return '0 min'
        h, m = minutes // 60, minutes % 60
        if h > 0 and m > 0:
            return f'{h} t {m} min'
        if h > 0:
            return f'{h} time{"r" if h > 1 else ""}'
        return f'{m} min'

    def _dr_copy_popup(self):
        """
        Popup som lar brukeren kopiere den valgte dagens plan til andre
        ukedager. Overskriver eventuelle eksisterende aktiviteter på målene.
        """
        sel = getattr(self, '_dr_selected_day', today_code())
        source_acts = list(get_day_plan(self.data, sel))
        if not source_acts:
            self._toast('Ingen aktiviteter å kopiere fra denne dagen.')
            return

        targets = {c: False for c in DAY_CODES if c != sel}

        outer = BoxLayout(orientation='vertical',
                          spacing=dp(10), padding=dp(14))
        outer.add_widget(Label(
            text=f'Kopier {DAY_FULL_NO[sel]}s plan til:\n'
                 f'(eksisterende aktiviteter på valgte dager overskrives)',
            size_hint_y=None, height=dp(58),
            font_size=fsp(14), color=(0.1, 0.1, 0.3, 1),
            halign='center', valign='middle'))
        outer.children[-1].bind(size=outer.children[-1].setter('text_size'))

        # Bygg av/på-knapper for hver målday
        toggle_btns = {}
        def update_toggle(code, btn):
            on = targets[code]
            btn.btn_color = list(hex_k('#6BCB77' if on else '#9CA3AF'))
            btn.text = ('✓ ' if on else '') + DAY_FULL_NO[code]
        def on_toggle(code):
            targets[code] = not targets[code]
            update_toggle(code, toggle_btns[code])

        for code in DAY_CODES:
            if code == sel:
                continue
            btn = mk_btn(DAY_FULL_NO[code], hex_k('#9CA3AF'),
                         h=dp(42), fs=14,
                         cb=lambda *_, c=code: on_toggle(c))
            toggle_btns[code] = btn
            outer.add_widget(btn)

        pop_ref = [None]
        def confirm(*_):
            chosen = [c for c, on in targets.items() if on]
            if not chosen:
                self._toast('Ingen dager valgt.')
                return
            for c in chosen:
                self.data['dagsplaner'][c] = [dict(a) for a in source_acts]
            save_struct(self.data)
            pop_ref[0].dismiss()
            self._toast(f'Kopiert til {len(chosen)} dag(er).')
            self._build_dagsrytme_ui()

        btn_row = BoxLayout(orientation='horizontal',
                            size_hint_y=None, height=dp(54), spacing=dp(10))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(54), fs=15,
                                   cb=lambda *_: pop_ref[0].dismiss()))
        btn_row.add_widget(mk_btn('Kopier', hex_k('#6BCB77'), h=dp(54), fs=16,
                                   cb=confirm))
        outer.add_widget(btn_row)

        pop = Popup(title='Kopier dagsplan',
                    content=outer, size_hint=POPUP_MEDIUM,
                    title_size=fsp(16))
        pop_ref[0] = pop
        pop.open()

    def _toggle_pause(self):
        """Slå dagsrytme-pause av/på. Lagres og synkes til widget."""
        if is_paused(self.data):
            self.data['pause'] = None
            self._toast('Dagsrytme gjenopptatt.')
        else:
            self.data['pause'] = {'since': datetime.now().isoformat()}
            self._toast('Dagsrytme satt på pause.')
        save_struct(self.data)
        Clock.schedule_once(lambda *_: _update_widget(self.data), 0.2)
        self._build_dagsrytme_ui()

    def _dagsoppsett_popup(self):
        """
        Forvaltning av dagsoppsett – maler for hele dagsplaner som kan
        aktiveres med ett tap. Brukbart f.eks. "Skogstur", "Sykebarn-modus",
        "Bursdag".

        Listen viser alle lagrede oppsett med "Bruk"- og "Slett"-knapper.
        Nederst er det en knapp for å lagre nåværende dag som nytt oppsett.
        """
        sel       = getattr(self, '_dr_selected_day', today_code())
        oppsett   = self.data.get('dagsoppsett', [])

        outer = BoxLayout(orientation='vertical',
                          spacing=dp(8), padding=dp(12))
        outer.add_widget(Label(
            text=f'Bruk et oppsett for {DAY_FULL_NO[sel].lower()}.\n'
                 f'Eksisterende aktiviteter på dagen overskrives.',
            size_hint_y=None, height=dp(50),
            font_size=fsp(13), color=(0.25, 0.27, 0.40, 1),
            halign='center', valign='middle'))
        outer.children[-1].bind(size=outer.children[-1].setter('text_size'))

        pop_ref = [None]

        # Liste over eksisterende oppsett
        if not oppsett:
            outer.add_widget(self._empty_state(
                glyph='[ Oppsett ]',
                msg='Ingen lagrede oppsett ennå.\n'
                    'Lag ditt første nederst.'))
        else:
            sv = ScrollView(size_hint_y=None, height=dp(280))
            list_box = BoxLayout(orientation='vertical',
                                 spacing=dp(6), size_hint_y=None)
            list_box.bind(minimum_height=list_box.setter('height'))
            for op in oppsett:
                op_ref = op
                row = RBox(orientation='horizontal',
                           size_hint_y=None, height=dp(58),
                           spacing=dp(6), padding=(dp(8), dp(4)),
                           box_color=(0.97, 0.97, 1.0, 1.0), radius=dp(14))
                # Ikon + navn
                lbl = Label(text=f'{op.get("icon", "🎭")}  {op["name"]}',
                            font_size=fsp(15), bold=True,
                            color=(0.04, 0.10, 0.36, 1),
                            halign='left')
                lbl.bind(size=lbl.setter('text_size'))
                row.add_widget(lbl)
                # Antall aktiviteter
                row.add_widget(Label(
                    text=f'{len(op.get("activities", []))} akt.',
                    size_hint_x=None, width=dp(60),
                    font_size=fsp(11), color=(0.4, 0.4, 0.5, 1)))
                # Bruk-knapp
                row.add_widget(mk_btn(
                    'Bruk', hex_k('#6BCB77'), h=dp(44), fs=12,
                    size_hint_x=None, width=dp(56),
                    cb=lambda *_, o=op_ref: self._apply_dagsoppsett(o, pop_ref)))
                # Slett-knapp
                row.add_widget(mk_btn(
                    'Slett', hex_k('#FF6B6B'), h=dp(44), fs=12,
                    size_hint_x=None, width=dp(58),
                    cb=lambda *_, o=op_ref: self._delete_dagsoppsett(o, pop_ref)))
                list_box.add_widget(row)
            sv.add_widget(list_box)
            outer.add_widget(sv)

        # Lagre-knapp – fra nåværende dag
        current_acts = get_day_plan(self.data, sel)
        save_enabled = bool(current_acts)
        save_btn = mk_btn(
            '💾  Lagre dagens plan som nytt oppsett'
            if save_enabled
            else '💾  (ingen aktiviteter å lagre)',
            hex_k('#4D96FF' if save_enabled else '#9CA3AF'),
            h=dp(50), fs=14)
        if save_enabled:
            save_btn.bind(on_release=lambda *_:
                self._save_as_dagsoppsett(sel, pop_ref))
        outer.add_widget(save_btn)
        outer.add_widget(mk_btn('Lukk', hex_k('#9CA3AF'), h=dp(50), fs=14,
            cb=lambda *_: pop_ref[0].dismiss()))

        pop = Popup(title='Dagsoppsett',
                    content=outer, size_hint=POPUP_LARGE,
                    title_size=fsp(16))
        pop_ref[0] = pop
        pop.open()

    def _apply_dagsoppsett(self, oppsett, parent_pop_ref):
        """
        Bruker et oppsett på den valgte dagen. Eksisterende aktiviteter
        overskrives. Aktivitets-ID-er regenereres så hver bruk gir
        uavhengige forekomster (slett på dag A skal ikke ramme dag B).
        """
        sel = getattr(self, '_dr_selected_day', today_code())
        self._confirm(
            title='Bruk dagsoppsett?',
            message=f'Erstatte alle aktiviteter for {DAY_FULL_NO[sel].lower()} '
                f'med oppsettet "{oppsett["name"]}"?\n\n'
                f'Eksisterende aktiviteter på dagen vil bli fjernet.',
            on_confirm=lambda: self._do_apply_dagsoppsett(oppsett, parent_pop_ref))

    def _do_apply_dagsoppsett(self, oppsett, parent_pop_ref):
        sel = getattr(self, '_dr_selected_day', today_code())
        # Lag dyp kopi av aktivitetene med nye id-er
        new_acts = []
        for a in oppsett.get('activities', []):
            copy_a = dict(a)
            copy_a['id'] = str(uuid.uuid4())
            new_acts.append(copy_a)
        self.data.setdefault('dagsplaner', {})[sel] = new_acts
        save_struct(self.data)
        Clock.schedule_once(lambda *_: _update_widget(self.data), 0.2)
        self._toast(f'Oppsett "{oppsett["name"]}" brukt på '
                    f'{DAY_FULL_NO[sel].lower()}.')
        if parent_pop_ref[0]:
            parent_pop_ref[0].dismiss()
        self._build_dagsrytme_ui()

    def _delete_dagsoppsett(self, oppsett, parent_pop_ref):
        self._confirm(
            title='Slett oppsett?',
            message=f'Vil du slette oppsettet "{oppsett["name"]}"?\n\n'
                f'Dagsplaner som bruker dette oppsettet vil ikke bli '
                f'påvirket – de beholder sine aktiviteter.',
            on_confirm=lambda: self._do_delete_dagsoppsett(oppsett, parent_pop_ref))

    def _do_delete_dagsoppsett(self, oppsett, parent_pop_ref):
        self.data['dagsoppsett'] = [
            o for o in self.data.get('dagsoppsett', [])
            if o.get('id') != oppsett.get('id')
        ]
        save_struct(self.data)
        self._toast('Oppsett slettet.')
        if parent_pop_ref[0]:
            parent_pop_ref[0].dismiss()
        # Gjenåpne med oppdatert liste
        Clock.schedule_once(lambda *_: self._dagsoppsett_popup(), 0.1)

    def _save_as_dagsoppsett(self, source_day, parent_pop_ref):
        """
        Popup for å lagre nåværende dags aktiviteter som et nytt oppsett.
        Brukeren velger navn og emoji-ikon.
        """
        outer = BoxLayout(orientation='vertical',
                          spacing=dp(10), padding=dp(14))
        outer.add_widget(Label(
            text=f'Lagre {DAY_FULL_NO[source_day].lower()}s plan '
                 f'({len(get_day_plan(self.data, source_day))} aktiviteter) '
                 f'som nytt oppsett.',
            size_hint_y=None, height=dp(42),
            font_size=fsp(13), color=(0.20, 0.22, 0.32, 1),
            halign='center', valign='middle'))
        outer.children[-1].bind(size=outer.children[-1].setter('text_size'))

        name_inp = TextInput(hint_text='Navn på oppsettet…',
                             multiline=False, size_hint_y=None, height=dp(48),
                             font_size=fsp(15))
        outer.add_widget(Label(text='Navn:', size_hint_y=None, height=dp(22),
            font_size=fsp(13), bold=True, color=(0.3,0.3,0.4,1),
            halign='left'))
        outer.add_widget(name_inp)

        # Ikon-velger – noen passende emoji for typiske dagsoppsett
        icon_state = ['🎭']
        outer.add_widget(Label(text='Ikon:', size_hint_y=None, height=dp(22),
            font_size=fsp(13), bold=True, color=(0.3,0.3,0.4,1),
            halign='left'))
        icon_row = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(48), spacing=dp(4))
        icons = ['☀️','🌳','🏠','🌧️','❄️','🎂','🤒','🎉','🚌','📚']
        icon_btns = []
        def select_icon(em):
            icon_state[0] = em
            for b in icon_btns:
                b.btn_color = list(hex_k('#4D96FF' if b.text == em else '#E0E0E0'))
        for em in icons:
            b = mk_btn(em, hex_k('#E0E0E0'), h=dp(48), fs=18,
                       cb=lambda *_, e=em: select_icon(e))
            icon_btns.append(b)
            icon_row.add_widget(b)
        outer.add_widget(icon_row)
        # Sett default-ikon til markert
        Clock.schedule_once(lambda *_: select_icon('🎭'), 0)

        sub_pop_ref = [None]
        def confirm(*_):
            name = name_inp.text.strip()
            if not name:
                self._toast('Gi oppsettet et navn.')
                return
            new_op = {
                'id':   str(uuid.uuid4()),
                'name': name,
                'icon': icon_state[0],
                'activities': [
                    {k: v for k, v in a.items()}
                    for a in get_day_plan(self.data, source_day)
                ],
            }
            self.data.setdefault('dagsoppsett', []).append(new_op)
            save_struct(self.data)
            self._toast(f'Oppsett "{name}" lagret.')
            sub_pop_ref[0].dismiss()
            if parent_pop_ref[0]:
                parent_pop_ref[0].dismiss()
            Clock.schedule_once(lambda *_: self._dagsoppsett_popup(), 0.1)

        btn_row = BoxLayout(orientation='horizontal',
                            size_hint_y=None, height=dp(54), spacing=dp(10))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(54), fs=15,
            cb=lambda *_: sub_pop_ref[0].dismiss()))
        btn_row.add_widget(mk_btn('Lagre', hex_k('#6BCB77'), h=dp(54), fs=15,
            cb=confirm))
        outer.add_widget(btn_row)

        pop = Popup(title='Nytt dagsoppsett',
                    content=outer, size_hint=POPUP_LARGE,
                    title_size=fsp(16))
        sub_pop_ref[0] = pop
        pop.open()

    def _build_dagsrytme_ui(self, animate=False):
        """
        Bygger dagsplan-skjermen for valgt ukedag.

        I visningsmodus:
          - Pause-banner hvis aktivert
          - Ukedag-faner
          - Tittel med fullføringsstatus inline
          - "Forrige | Nåværende | Neste"-trio (bilder)
          - Aktivitetsinfo + ÉN fargevarierende fremdriftslinje
          - Start tidsur-knapp
          - Plan-liste under

        I redigeringsmodus:
          - Primær handling (Legg til) + 2x2 sekundære handlinger
          - Kalender-stil dagvisning med dra-og-slipp
          - Notat-felt nederst

        animate=True ved navigering inn / dag-bytte; animate=False fra
        bakgrunns-refresh så skjermen ikke blinker hvert 30. sek.
        """
        if self._cur_scr != 'dagsrytme':
            return
        if not getattr(self, '_dr_selected_day', None):
            self._dr_selected_day = today_code()

        sel       = self._dr_selected_day
        today_c   = today_code()
        is_today  = (sel == today_c)
        paused    = is_paused(self.data) and is_today
        entries   = sorted(get_day_plan(self.data, sel),
                           key=lambda e: e.get('start', '00:00'))
        now       = datetime.now()
        now_m     = now.hour * 60 + now.minute
        edit      = self.edit_mode

        # Finn forrige / nåværende / kommende aktivitet (kun for i dag, ikke pauset)
        previous_act = current = upcoming = None
        if is_today and not paused:
            for e in entries:
                s = self._dr_parse(e.get('start','00:00'))
                t = self._dr_parse(e.get('end',  '23:59'))
                if t <= now_m:
                    previous_act = (e, s, t)
                elif s <= now_m < t:
                    current = (e, s, t)
                elif s > now_m and upcoming is None:
                    upcoming = (e, s)

        # Dagsfullføringen brukes inline i tittellinjen, ikke som egen progressbar
        completed_count = 0
        if is_today and entries:
            completed_count = sum(
                1 for e in entries
                if self._dr_parse(e.get('end','23:59')) <= now_m
            )

        outer = BoxLayout(orientation='vertical',
                          spacing=dp(12), padding=(dp(10), dp(8)),
                          size_hint_y=None)
        outer.bind(minimum_height=outer.setter('height'))

        # ── 1. Pause-banner ──────────────────────────────────────
        if paused:
            banner = RBox(orientation='horizontal',
                          size_hint_y=None, height=dp(52),
                          padding=(dp(12), dp(6)),
                          box_color=(1.0, 0.86, 0.30, 1.0), radius=dp(14))
            banner.add_widget(Label(
                text='[b]⏸  Dagsrytme på pause[/b] – trykk for å gjenoppta',
                markup=True, font_size=fsp(15),
                color=(0.15, 0.10, 0.05, 1), halign='left', valign='middle'))
            def _banner_tap(w, touch):
                if w.collide_point(*touch.pos):
                    self._toggle_pause()
                    return True
                return False
            banner.bind(on_touch_down=_banner_tap)
            outer.add_widget(banner)

        # ── 2. Ukedag-faner ──────────────────────────────────────
        tabs = BoxLayout(orientation='horizontal',
                         size_hint_y=None, height=dp(48), spacing=dp(4))
        for code in DAY_CODES:
            is_sel       = (code == sel)
            is_today_tab = (code == today_c)
            if is_sel:
                col = '#4D96FF'
            elif is_today_tab:
                col = '#6BCB77'
            else:
                col = '#9CA3AF'
            label = DAY_LABEL_NO[code] + ('•' if is_today_tab else '')
            tabs.add_widget(mk_btn(label, hex_k(col), h=dp(48), fs=14,
                cb=lambda *_, c=code: self._dr_switch_day(c)))
        outer.add_widget(tabs)

        # ── 3. Dagstittel med fullføringsstatus inline ───────────
        if is_today and entries and not paused:
            title_text = (f'{DAY_FULL_NO[sel]} (i dag)   ·   '
                          f'{completed_count} av {len(entries)} fullført')
        else:
            title_text = DAY_FULL_NO[sel] + (' (i dag)' if is_today else '')
        outer.add_widget(Label(text=title_text, size_hint_y=None, height=dp(28),
            font_size=fsp(16), bold=True, color=(0.04, 0.10, 0.36, 1),
            halign='center'))

        # ── 4. Edit-mode-knapper (kompakt: 1 + 2x2) ──────────────
        if edit:
            outer.add_widget(mk_btn('+  Legg til aktivitet',
                hex_k('#6BCB77'), h=dp(52), fs=15,
                cb=lambda *_: self._dr_new_activity_flow()))
            row1 = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(44),
                             spacing=dp(6))
            if is_today:
                p_label = '▶  Gjenoppta' if paused else '⏸  Sett på pause'
                p_color = '#6BCB77' if paused else '#FF9F43'
                row1.add_widget(mk_btn(p_label, hex_k(p_color),
                    h=dp(44), fs=13,
                    cb=lambda *_: self._toggle_pause()))
            row1.add_widget(mk_btn('⎘  Kopier dag', hex_k('#FF9F43'),
                h=dp(44), fs=13,
                cb=lambda *_: self._dr_copy_popup()))
            outer.add_widget(row1)
            row2 = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(44),
                             spacing=dp(6))
            row2.add_widget(mk_btn('Dagsoppsett', hex_k('#C77DFF'),
                h=dp(44), fs=13,
                cb=lambda *_: self._dagsoppsett_popup()))
            row2.add_widget(mk_btn('↗  Eksporter', hex_k('#546E7A'),
                h=dp(44), fs=13,
                cb=lambda *_: self._export_popup('dagsrytme')))
            outer.add_widget(row2)

        # ── 5. Hovedinnhold ──────────────────────────────────────
        if edit:
            # Enkel liste i redigeringsmodus – ↑/↓ for rekkefølge, Slett for fjerning.
            # Ingen drag-og-slipp; mye lettere å bruke på mobil.
            if not entries:
                outer.add_widget(Label(
                    text='Ingen aktiviteter ennå. Trykk «+ Legg til» ovenfor.',
                    size_hint_y=None, height=dp(50),
                    font_size=fsp(14), color=(0.45, 0.48, 0.55, 1),
                    halign='center', valign='middle'))
            else:
                edit_sv = ScrollView(size_hint=(1, None), height=dp(360))
                edit_box = BoxLayout(
                    orientation='vertical', spacing=dp(6),
                    size_hint_y=None, padding=(0, dp(4)))
                edit_box.bind(minimum_height=edit_box.setter('height'))

                def _rebuild_edit_list():
                    edit_box.clear_widgets()
                    current_entries = sorted(
                        get_day_plan(self.data, sel),
                        key=lambda e: e.get('start', '00:00'))
                    for idx, e in enumerate(current_entries):
                        row = RBox(
                            orientation='horizontal',
                            size_hint_y=None, height=dp(56),
                            spacing=dp(4), padding=(dp(6), dp(4)),
                            box_color=(0.96, 0.97, 1.0, 1.0), radius=dp(12))

                        # Kategori-farge stripe
                        cat = get_category(self.data, e.get('category'))
                        stripe_col = hex_k(cat['color']) if cat else hex_k('#4D96FF')
                        stripe = BoxLayout(size_hint_x=None, width=dp(4))
                        from kivy.graphics import Color as KColor, Rectangle as KRect
                        with stripe.canvas.before:
                            KColor(*stripe_col)
                            sr = KRect(pos=stripe.pos, size=stripe.size)
                        def _us(sw, *_, _sr=sr): _sr.pos = sw.pos; _sr.size = sw.size
                        stripe.bind(pos=_us, size=_us)
                        row.add_widget(stripe)

                        # Aktivitetsnavn + tidspunkt
                        info_lbl = Label(
                            text=f'{e.get("start","?")}–{e.get("end","?")}  {e["name"]}',
                            font_size=fsp(13), color=(0.08, 0.10, 0.35, 1),
                            halign='left', valign='middle',
                            size_hint_x=1)
                        info_lbl.bind(size=info_lbl.setter('text_size'))
                        row.add_widget(info_lbl)

                        # ↑ Flytt opp
                        def _move_up(e_id=e['id'], *_):
                            pl = self.data['dagsplaner'][sel]
                            ids = [x['id'] for x in sorted(pl, key=lambda x: x.get('start','00:00'))]
                            i2 = ids.index(e_id)
                            if i2 > 0:
                                # Bytt start-tidspunkter
                                pl_map = {x['id']: x for x in pl}
                                a, b = pl_map[ids[i2-1]], pl_map[ids[i2]]
                                a['start'], b['start'] = b['start'], a['start']
                                a['end'],   b['end']   = b['end'],   a['end']
                                save_struct(self.data)
                                _rebuild_edit_list()
                        up_btn = mk_btn('▲', hex_k('#78909C'),
                            h=dp(48), fs=14,
                            size_hint_x=None, width=dp(42))
                        up_btn.bind(on_release=lambda *_, f=_move_up: f())
                        if idx == 0:
                            up_btn.opacity = 0.35
                            up_btn.disabled = True
                        row.add_widget(up_btn)

                        # ↓ Flytt ned
                        def _move_down(e_id=e['id'], *_):
                            pl = self.data['dagsplaner'][sel]
                            ids = [x['id'] for x in sorted(pl, key=lambda x: x.get('start','00:00'))]
                            i2 = ids.index(e_id)
                            if i2 < len(ids) - 1:
                                pl_map = {x['id']: x for x in pl}
                                a, b = pl_map[ids[i2]], pl_map[ids[i2+1]]
                                a['start'], b['start'] = b['start'], a['start']
                                a['end'],   b['end']   = b['end'],   a['end']
                                save_struct(self.data)
                                _rebuild_edit_list()
                        dn_btn = mk_btn('▼', hex_k('#78909C'),
                            h=dp(48), fs=14,
                            size_hint_x=None, width=dp(42))
                        dn_btn.bind(on_release=lambda *_, f=_move_down: f())
                        if idx == len(current_entries) - 1:
                            dn_btn.opacity = 0.35
                            dn_btn.disabled = True
                        row.add_widget(dn_btn)

                        # Rediger
                        def _edit_entry(entry=e, *_):
                            self._dr_entry_popup(entry)
                        ed_btn = mk_btn('Red.', hex_k('#4D96FF'),
                            h=dp(48), fs=12,
                            size_hint_x=None, width=dp(52))
                        ed_btn.bind(on_release=lambda *_, f=_edit_entry: f())
                        row.add_widget(ed_btn)

                        # Slett
                        def _delete_entry(entry=e, *_):
                            self._dr_delete(entry)
                        del_btn = mk_btn('Slett', hex_k('#FF6B6B'),
                            h=dp(48), fs=12,
                            size_hint_x=None, width=dp(58))
                        del_btn.bind(on_release=lambda *_, f=_delete_entry: f())
                        row.add_widget(del_btn)

                        edit_box.add_widget(row)

                _rebuild_edit_list()
                edit_sv.add_widget(edit_box)
                outer.add_widget(edit_sv)
        elif paused:
            outer.add_widget(Label(
                text='Dagsrytmen er pauset. Nåværende og neste vises ikke.',
                size_hint_y=None, height=dp(40),
                font_size=fsp(14), color=(0.4, 0.4, 0.5, 1),
                halign='center', valign='middle'))
            outer.children[-1].bind(size=outer.children[-1].setter('text_size'))
        elif current:
            # PREV | NÅ | NEXT image trio
            outer.add_widget(self._build_activity_trio(
                prev_act=previous_act[0] if previous_act else None,
                center_act=current[0],
                next_act=upcoming[0] if upcoming else None,
                center_label='Pågår nå',
                center_color='#1FAB3A'))
            # Aktivitetsnavn (stort)
            outer.add_widget(Label(text=current[0]['name'],
                size_hint_y=None, height=dp(46),
                font_size=fsp(24), bold=True,
                color=(0.04, 0.10, 0.36, 1), halign='center'))
            # Tidspunkter
            outer.add_widget(Label(
                text=f'{current[0].get("start","")}  –  {current[0].get("end","")}',
                size_hint_y=None, height=dp(24),
                font_size=fsp(13), color=(0.4, 0.44, 0.55, 1),
                halign='center'))
            # "Slutter om X"
            remaining = current[2] - now_m
            outer.add_widget(Label(text=f'Slutter om {self._dr_fmt(remaining)}',
                size_hint_y=None, height=dp(28),
                font_size=fsp(15), color=(0.25, 0.35, 0.55, 1),
                halign='center'))
            # ENESTE fremdriftslinje – fargevariert (grønn → gul → rød)
            outer.add_widget(self._make_time_bar(
                current[1], current[2], now_m))
            # Start tidsur-knapp
            outer.add_widget(mk_btn(
                f'Start tidsur ({self._dr_fmt(remaining)})',
                hex_k('#4D96FF'), h=dp(48), fs=14,
                cb=lambda *_, en=current[0], em=current[2]:
                    self._start_timer_for_activity(en, em)))
        elif upcoming and is_today:
            # Venter på neste aktivitet – samme trio men sentrum er
            # neste-aktiviteten med dempet visning. Tidligere vises også
            # for kontekst.
            outer.add_widget(self._build_activity_trio(
                prev_act=previous_act[0] if previous_act else None,
                center_act=upcoming[0],
                next_act=None,
                center_label='Neste',
                center_color='#4D96FF',
                center_faded=True))
            outer.add_widget(Label(text=upcoming[0]['name'],
                size_hint_y=None, height=dp(40),
                font_size=fsp(22), bold=True,
                color=(0.04, 0.10, 0.36, 1), halign='center'))
            wait = upcoming[1] - now_m
            outer.add_widget(Label(
                text=f'Starter om {self._dr_fmt(wait)}  (kl. {upcoming[0].get("start","")})',
                size_hint_y=None, height=dp(30),
                font_size=fsp(15), color=(0.3, 0.4, 0.5, 1),
                halign='center'))
        elif is_today and entries:
            outer.add_widget(Label(
                text='✓  Alle aktiviteter for i dag er ferdige.',
                size_hint_y=None, height=dp(60),
                font_size=fsp(17), color=(0.30, 0.55, 0.30, 1),
                halign='center', valign='middle'))
        elif not entries:
            outer.add_widget(BoxLayout(size_hint_y=None, height=dp(20)))
            outer.add_widget(self._empty_state(
                glyph='[ Plan ]',
                msg=f'Ingen aktiviteter for {DAY_FULL_NO[sel].lower()}.\n'
                    f'Trykk "Red." og "+" for å starte.'))

        # ── 6. Plan-liste (kun i visningsmodus) ──────────────────
        # I redigeringsmodus tar kalender-visningen rollen som liste.
        if not edit and entries:
            outer.add_widget(Label(
                text='Plan for ' + DAY_FULL_NO[sel].lower() + ':',
                size_hint_y=None, height=dp(22),
                font_size=fsp(13), bold=True, color=(0.3, 0.3, 0.4, 1),
                halign='left'))
            list_sv  = ScrollView(size_hint_y=None, height=dp(190))
            list_box = BoxLayout(orientation='vertical', spacing=dp(4),
                                 size_hint_y=None)
            list_box.bind(minimum_height=list_box.setter('height'))
            for e in entries:
                is_cur = bool(current and current[0]['id'] == e['id'])
                end_m  = self._dr_parse(e.get('end', '23:59'))
                completed = is_today and not paused and end_m <= now_m
                cat = get_category(self.data, e.get('category'))
                stripe_col = hex_k(cat['color']) if cat else None

                if is_cur:
                    bg = (0.84, 0.96, 0.84, 1.0)
                elif completed:
                    bg = (0.93, 0.93, 0.95, 1.0)
                else:
                    bg = (0.97, 0.97, 1.0, 1.0)

                row = RBox(orientation='horizontal',
                           size_hint_y=None, height=dp(56),
                           spacing=dp(6), padding=(dp(4), dp(4)),
                           box_color=bg, radius=dp(12))

                if stripe_col:
                    stripe = BoxLayout(size_hint_x=None, width=dp(4))
                    with stripe.canvas.before:
                        from kivy.graphics import Color as KColor, Rectangle
                        KColor(*stripe_col)
                        s_rect = Rectangle(pos=stripe.pos, size=stripe.size)
                    def _us(sw, *_, sr=s_rect):
                        sr.pos = sw.pos; sr.size = sw.size
                    stripe.bind(size=_us, pos=_us)
                    row.add_widget(stripe)
                else:
                    row.add_widget(Widget(size_hint_x=None, width=dp(4)))

                # ── Symbol-thumbnail ──────────────────────────────────
                # Aktiviteter opprettet via _dr_new_activity_flow har et
                # bilde knyttet direkte (entry['image'] = symbolets bilde).
                # Viser dette i listen – gir umiddelbar visuell gjenkjenning
                # av aktiviteten, samme symbol som i resten av appen.
                # Aktiviteter uten bilde (manuelt navngitt, f.eks. "Fri lek")
                # får en tom plassholder i samme bredde – holder
                # klokkeslett/navn-teksten på linje på tvers av rader.
                THUMB = int(dp(40))
                act_img = e.get('image')
                has_act_img = bool(act_img and os.path.exists(act_img))
                thumb_w = Image(size_hint=(None, None),
                                size=(dp(40), dp(40)),
                                allow_stretch=True, keep_ratio=True)
                if has_act_img:
                    _tex = get_thumbnail(act_img, THUMB, THUMB)
                    if _tex:
                        thumb_w.texture = _tex
                    else:
                        thumb_w.source = act_img
                else:
                    thumb_w.opacity = 0
                row.add_widget(thumb_w)

                txt = f'{e.get("start","?")} – {e.get("end","?")}   {e["name"]}'
                if completed and not is_cur:
                    label_text = f'[s]{txt}[/s]'
                    text_col = (0.45, 0.48, 0.55, 1)
                else:
                    label_text = txt
                    text_col = ((0.04, 0.30, 0.04, 1) if is_cur
                                else (0.08, 0.10, 0.35, 1))
                row.add_widget(Label(
                    text=label_text, markup=True,
                    font_size=fsp(14), bold=is_cur,
                    color=text_col, halign='left'))

                # «Fullfør»-knapp bare på aktiv aktivitet (ikke allerede fullfort)
                if is_cur and not completed:
                    def _do_complete(row=row, *_):
                        # Finn senter av raden i vindu-koordinater
                        try:
                            wx, wy = row.to_window(row.center_x, row.center_y)
                        except Exception:
                            wx, wy = Window.width/2, Window.height/2
                        self._anim_activity_done(wx, wy)
                        self._toast('Aktivitet fullfort!')
                    row.add_widget(mk_btn(
                        'Fullfört', hex_k('#6BCB77'),
                        h=dp(36), fs=11,
                        size_hint_x=None, width=dp(72),
                        cb=_do_complete))

                list_box.add_widget(row)
            list_sv.add_widget(list_box)
            outer.add_widget(list_sv)

        # ── 7. Notater per ukedag ────────────────────────────────
        notes_section = BoxLayout(orientation='vertical',
                                  size_hint_y=None, spacing=dp(4))
        notes_section.bind(minimum_height=notes_section.setter('height'))
        notes_section.add_widget(Label(
            text=f'Notater for {DAY_FULL_NO[sel].lower()}:',
            size_hint_y=None, height=dp(22),
            font_size=fsp(13), bold=True, color=(0.3, 0.3, 0.4, 1),
            halign='left'))
        if edit:
            note_text = self.data.get('notater', {}).get(sel, '')
            note_inp = TextInput(
                text=note_text, multiline=True,
                size_hint_y=None, height=dp(90),
                font_size=fsp(14),
                hint_text='Observasjoner, hendelser, kommunikasjon mellom skift…',
            )
            def _save_note(inst, val):
                self.data.setdefault('notater', {})[sel] = val
                save_struct(self.data)
            note_inp.bind(text=_save_note)
            notes_section.add_widget(note_inp)
        else:
            note_text = self.data.get('notater', {}).get(sel, '')
            disp = RBox(orientation='vertical',
                        size_hint_y=None, padding=(dp(10), dp(8)),
                        box_color=(0.98, 0.98, 1.0, 1.0), radius=dp(10))
            disp.bind(minimum_height=disp.setter('height'))
            shown = note_text if note_text.strip() else '(Ingen notater for denne dagen.)'
            txt_col = (0.1, 0.1, 0.3, 1) if note_text.strip() else (0.5, 0.5, 0.6, 1)
            lbl = Label(text=shown, font_size=fsp(13),
                        color=txt_col, size_hint_y=None,
                        halign='left', valign='top')
            lbl.bind(width=lambda l, w: setattr(l, 'text_size', (w - dp(10), None)),
                     texture_size=lambda l, ts: setattr(l, 'height', max(dp(36), ts[1] + dp(10))))
            disp.add_widget(lbl)
            notes_section.add_widget(disp)
        outer.add_widget(notes_section)

        sv = ScrollView()
        sv.add_widget(outer)
        self._set_content(sv, animate=animate)

    def _build_activity_trio(self, prev_act, center_act, next_act,
                             center_label='Pågår nå', center_color='#1FAB3A',
                             center_faded=False):
        """
        Tre-kolonne layout for forrige | nåværende/neste | neste-aktivitet.
        Sentrum får størst plass og full opasitet (med mindre faded=True),
        sidene halvparten av høyden med dempet opasitet.

        Hvis prev/next mangler, vises tomme plassholdere så layouten ikke
        hopper rundt når aktivitets-strømmen endres.
        """
        TRIO_H = dp(200)
        SIDE_H = dp(120)

        trio = BoxLayout(orientation='horizontal',
                         size_hint_y=None, height=TRIO_H,
                         spacing=dp(8))

        # Hjelpefunksjon for å lage en sidemarkør med bilde og dempet
        # label over (Forrige / Neste)
        def make_side_col(act, label_text):
            col = BoxLayout(orientation='vertical',
                            size_hint_x=0.25)
            col.add_widget(Widget())  # toppspacer
            if act and act.get('image') and os.path.exists(act['image']):
                col.add_widget(Label(
                    text=label_text,
                    size_hint_y=None, height=dp(18),
                    font_size=fsp(10),
                    color=(0.45, 0.48, 0.58, 1),
                    halign='center', bold=True))
                img_wrap = BoxLayout(size_hint_y=None, height=SIDE_H)
                img_wrap.add_widget(self._make_framed_image(
                    act['image'], SIDE_H, faded=True))
                col.add_widget(img_wrap)
                col.add_widget(Label(
                    text=act.get('name',''),
                    size_hint_y=None, height=dp(20),
                    font_size=fsp(11),
                    color=(0.35, 0.40, 0.55, 1),
                    halign='center', shorten=True, shorten_from='right'))
                col.children[0].bind(
                    size=col.children[0].setter('text_size'))
            else:
                # Tom plassholder så layout-bredden holdes
                col.add_widget(Widget(size_hint_y=None, height=dp(20)))
                col.add_widget(Widget(size_hint_y=None, height=SIDE_H))
            col.add_widget(Widget())  # bunnspacer
            return col

        # Sentrum-kolonne med stor label-pille
        def make_center_col():
            col = BoxLayout(orientation='vertical', size_hint_x=0.5)
            # Pille
            badge_row = BoxLayout(orientation='horizontal',
                                   size_hint_y=None, height=dp(28),
                                   spacing=dp(6))
            badge_row.add_widget(Widget())
            badge = RBox(orientation='horizontal',
                         size_hint=(None, None),
                         width=dp(96), height=dp(26),
                         padding=(dp(10), dp(2)),
                         box_color=hex_k(center_color), radius=dp(13))
            badge.add_widget(Label(text=center_label,
                font_size=fsp(11), bold=True, color=(1,1,1,1)))
            badge_row.add_widget(badge)
            badge_row.add_widget(Widget())
            col.add_widget(badge_row)
            # Bilde
            if center_act and center_act.get('image') and os.path.exists(center_act['image']):
                img_wrap = BoxLayout(size_hint_y=None, height=TRIO_H - dp(28))
                img_wrap.add_widget(self._make_framed_image(
                    center_act['image'], TRIO_H - dp(28),
                    faded=center_faded))
                col.add_widget(img_wrap)
            else:
                col.add_widget(Widget(size_hint_y=None, height=TRIO_H - dp(28)))
            return col

        trio.add_widget(make_side_col(prev_act, 'Forrige'))
        trio.add_widget(make_center_col())
        trio.add_widget(make_side_col(next_act,  'Neste'))
        return trio

    def _make_time_bar(self, start_m, end_m, now_m):
        """
        Lager en flott fargevariert tidsbar:
          grønn (god tid igjen) → gul (snart slutt) → rød (nesten ferdig)
        Erstatter både den gamle Kivy ProgressBar og custom-bar-en.
        """
        duration = max(end_m - start_m, 1)
        elapsed  = max(0, now_m - start_m)
        pct      = elapsed / duration if duration > 0 else 0
        if pct < 0.6:
            col = (0.15, 0.65, 0.20, 1)
        elif pct < 0.85:
            col = (0.85, 0.62, 0.05, 1)
        else:
            col = (0.80, 0.15, 0.12, 1)
        bar = BoxLayout(size_hint_y=None, height=dp(10))
        from kivy.graphics import Color as KColor, Rectangle
        with bar.canvas.before:
            # Spor (lys grå)
            KColor(0.88, 0.88, 0.93, 1)
            track = Rectangle(pos=bar.pos, size=bar.size)
            # Fyll (fargevariert)
            KColor(*col)
            fill = Rectangle(pos=bar.pos,
                             size=(bar.width * pct, bar.height))
        def _u(b, *_):
            track.pos  = b.pos
            track.size = b.size
            fill.pos   = b.pos
            fill.size  = (b.width * pct, b.height)
        bar.bind(size=_u, pos=_u)
        return bar

    def _dr_delete(self, entry):
        start = entry.get('start', '')
        end   = entry.get('end',   '')
        when  = f' ({start}–{end})' if start and end else ''
        self._confirm(
            title='Slette aktivitet?',
            message=f'Aktiviteten "{entry.get("name", "")}"{when} '
                    f'fjernes fra dagsrytmen.',
            on_confirm=lambda: self._do_dr_delete(entry),
        )

    def _do_dr_delete(self, entry):
        sel = getattr(self, '_dr_selected_day', today_code())
        plans = self.data.setdefault('dagsplaner', {})
        if sel in plans:
            plans[sel] = [e for e in plans[sel] if e.get('id') != entry.get('id')]
        save_struct(self.data)
        self._build_dagsrytme_ui()

    def _make_framed_image(self, source, height, faded=False):
        """
        Bilde med indre skygge og 200 ms fade-in når teksturen er klar.
        Indre skyggen ligger på topp av bildet i kantene og gir en svak
        følelse av at bildet er satt INN i en ramme – ikke ligger oppå.

        source – filsti til bildet
        height – ønsket høyde
        faded  – True for å rendre med 0.65 opacity (brukes for "neste"-
                 visningen der bildet skal være dempet)
        """
        wrap = BoxLayout(size_hint_y=None, height=height)
        img = Image(source=source, allow_stretch=True, keep_ratio=True,
                    opacity=0)
        # Tegn indre skygge som mørke kanter inne i bildet via canvas.after
        with wrap.canvas.after:
            from kivy.graphics import Color as KColor, Line as KLine
            # Mørke kanter med dempet opasitet – simulerer indre skygge.
            # Kantene blir tegnet på topp av bildet, ikke utenfor.
            KColor(0, 0, 0, 0.12)
            inner_top    = KLine(width=2)
            inner_left   = KLine(width=2)
            KColor(0, 0, 0, 0.06)
            inner_right  = KLine(width=2)
            inner_bottom = KLine(width=2)
        def _u(w, *_):
            x, y, ww, hh = w.x, w.y, w.width, w.height
            # Topp og venstre – sterkere skygge (lyskilde fra øvre venstre)
            inner_top.points    = [x+2, y+hh-2, x+ww-2, y+hh-2]
            inner_left.points   = [x+2, y+hh-2, x+2, y+2]
            inner_right.points  = [x+ww-2, y+hh-2, x+ww-2, y+2]
            inner_bottom.points = [x+2, y+2, x+ww-2, y+2]
        wrap.bind(size=_u, pos=_u)
        wrap.add_widget(img)
        # Fade-in: vent til teksturen er klar.
        # På kald Android-oppstart kan texture-eventet noen ganger aldri
        # fyre (race condition i Kivy-loaderen). Fallback-timeren sikrer
        # at bildet alltid blir synlig etter maks 1,5 sekunder.
        target = 0.65 if faded else 1.0
        def _fade_when_ready(*_):
            if img.opacity >= target * 0.9:
                return  # allerede synlig
            Animation(opacity=target, duration=0.2, t='out_quad').start(img)
        if img.texture:
            _fade_when_ready()
        else:
            img.bind(texture=lambda *_: _fade_when_ready())
            Clock.schedule_once(lambda dt: _fade_when_ready(), 1.5)
        return wrap

    def _empty_state(self, glyph, msg):
        """
        Vennlig 'tom skjerm'-visning – glyf-merke + tekst i et avrundet
        kort med svak gradient (samme RBox-tekstur som resten av appen),
        i stedet for ren tekst direkte på bakgrunnen. Fader mykt inn for
        et "levende" førsteinntrykk i stedet for å bare poppe opp.
        """
        card = RBox(orientation='vertical',
                     size_hint_y=None, height=dp(184),
                     spacing=dp(10), padding=(dp(20), dp(20)),
                     box_color=(0.965, 0.965, 0.99, 1.0), radius=dp(18))

        # Glyf-merke: liten avrundet "badge" bak teksten – gir glyfen
        # litt visuell vekt/farge i stedet for å flyte fritt på hvitt.
        badge = RBox(orientation='vertical',
                     size_hint=(None, None), size=(dp(96), dp(64)),
                     pos_hint={'center_x': 0.5},
                     box_color=(0.88, 0.90, 0.98, 1.0), radius=dp(14))
        badge.add_widget(Label(text=glyph, font_size=sp(15), bold=True,
                                color=(0.35, 0.40, 0.62, 1),
                                halign='center', valign='middle'))
        badge.children[-1].bind(size=badge.children[-1].setter('text_size'))
        badge_wrap = BoxLayout(size_hint_y=None, height=dp(64))
        badge_wrap.add_widget(Widget())
        badge_wrap.add_widget(badge)
        badge_wrap.add_widget(Widget())
        card.add_widget(badge_wrap)

        lbl = Label(text=msg, font_size=fsp(15),
                    color=(0.45, 0.45, 0.55, 1),
                    halign='center', valign='top')
        lbl.bind(width=lambda l, w: setattr(l, 'text_size', (w - dp(20), None)))
        card.add_widget(lbl)

        card.opacity = 0
        Animation(opacity=1, duration=0.35, t='out_cubic').start(card)
        return card

    def _dr_new_activity_flow(self):
        """
        Inngangspunkt for "Ny aktivitet" – erstatter direkte kall til
        _dr_entry_popup(None).

        Resonnement: en aktivitet i dagsplanen vises med et ASK-symbol,
        og navnet på aktiviteten ER i praksis navnet på det symbolet.
        Å skrive inn et navn manuelt er derfor unødvendig dobbeltarbeid
        i de fleste tilfeller. I stedet vises symbolvelgeren FØRST:

          • Velger brukeren et symbol → _dr_entry_popup åpnes med navn
            OG bilde forhåndsutfylt fra symbolet (fortsatt redigerbart),
            sammen med smarte tid-/kategori-standardverdier fra batch 2.
            Da gjenstår normalt kun ett trykk: "Lagre".
          • Trykker brukeren "Skriv navn manuelt i stedet" → vanlig
            tom popup med auto-fokusert navnefelt, for aktiviteter uten
            et bestemt symbol (f.eks. "Fri lek", "Samling").
        """
        self._pick_symbol_popup(
            on_picked=lambda path, name: self._dr_entry_popup(
                None, preset_image=path, preset_name=name),
            on_cancel=lambda: self._dr_entry_popup(None))

    def _pick_symbol_popup(self, on_picked, on_cancel=None):
        """
        Symbolvelger for "Ny aktivitet": viser alle ASK-symboler gruppert
        per mappe (samme oversiktlige liste som _pick_from_folders), slik
        at den ansatte raskt kan trykke seg ned til riktig symbol.

        on_picked(image_path, name) kalles ved valg av symbol.
        on_cancel() kalles hvis brukeren velger å skrive navn manuelt
        i stedet (f.eks. for aktiviteter uten et bestemt symbol).
        """
        from kivy.uix.image import Image as KImg

        pop_ref = [None]
        layout = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
        layout.add_widget(Label(
            text='Velg symbol for ny aktivitet:',
            size_hint_y=None, height=dp(32),
            font_size=fsp(15), bold=True, color=(0.1, 0.1, 0.3, 1)))

        sv = ScrollView()
        gl = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        gl.bind(minimum_height=gl.setter('height'))

        has_any = False
        for fo in self.data.get('folders', []):
            items = fo.get('items', [])
            if not items:
                continue
            has_any = True
            gl.add_widget(Label(
                text=fo['name'], size_hint_y=None, height=dp(28),
                font_size=fsp(13), bold=True,
                color=hex_k(fo.get('color', '#4D96FF'))[:3] + (1,),
                halign='left'))
            # 4 kolonner i portrett, 6 i liggende (fase 1 – landskapsstøtte)
            img_grid = GridLayout(cols=(6 if is_landscape() else 4),
                                   spacing=dp(4), size_hint_y=None)
            img_grid.bind(minimum_height=img_grid.setter('height'))
            for it in items:
                ip = it.get('image', '')
                if not ip or not os.path.exists(ip):
                    continue
                cell = BoxLayout(orientation='vertical',
                                 size_hint_y=None, height=dp(90))
                img_w = KImg(source=ip, allow_stretch=True, keep_ratio=True,
                              size_hint_y=None, height=dp(72))
                lbl = Label(text=it['name'], font_size=sp(10),
                            size_hint_y=None, height=dp(16),
                            color=(0.2, 0.2, 0.3, 1),
                            shorten=True, shorten_from='right')
                lbl.bind(size=lbl.setter('text_size'))
                cell.add_widget(img_w)
                cell.add_widget(lbl)

                def _tap(w, t, _ip=ip, _name=it['name']):
                    if w.collide_point(*t.pos):
                        pop_ref[0].dismiss()
                        Clock.schedule_once(
                            lambda *_: on_picked(_ip, _name), 0.05)
                        return True
                cell.bind(on_touch_down=_tap)
                img_grid.add_widget(cell)
            gl.add_widget(img_grid)

        if not has_any:
            gl.add_widget(Label(
                text='Ingen symboler ennå.\nLegg til bilder i mapper først.',
                size_hint_y=None, height=dp(80),
                font_size=fsp(14), color=(0.5, 0.5, 0.5, 1), halign='center'))

        sv.add_widget(gl)
        layout.add_widget(sv)

        def _cancel(*_):
            pop_ref[0].dismiss()
            if on_cancel:
                Clock.schedule_once(lambda *_: on_cancel(), 0.05)

        layout.add_widget(mk_btn(
            'Skriv navn manuelt i stedet', hex_k('#9CA3AF'), h=dp(46), fs=13,
            cb=_cancel))

        pop = Popup(title='Velg symbol', content=layout, size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        pop.open()

    def _dr_entry_popup(self, entry, preset_image=None, preset_name=None):
        """
        Popup for å opprette eller redigere en dagsrytme-aktivitet.

        preset_image/preset_name: brukes når brukeren har valgt symbol
        FØR denne popup-en åpnes (se _dr_new_activity_flow). Navn og
        bilde forhåndsutfylles fra symbolet, men forblir redigerbare –
        siden aktivitetens navn i praksis ER symbolets navn, trenger
        brukeren da bare å bekrefte tid/kategori og trykke Lagre.
        """
        new = entry is None
        pop_ref = [None]
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        layout.add_widget(Label(text='Navn:', size_hint_y=None, height=dp(28),
            font_size=fsp(15), color=(0, 0, 0, 1), halign='left'))
        # on_save defineres nedenfor – bruk lambda for å unngå NameError
        name_inp = smart_input(
            text=(preset_name or '') if new else entry['name'],
            hint='Navn på aktivitet',
            on_save=lambda *_: on_save(),
        )
        layout.add_widget(name_inp)

        time_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        time_row.add_widget(Label(text='Fra:', size_hint_x=None, width=dp(40),
            font_size=fsp(15), color=(0, 0, 0, 1)))

        # ── Smarte standardverdier for NY aktivitet ──────────────────
        # Reduserer tastetrykk for det vanligste tilfellet: aktivitet
        # som starter "nå" og varer en time.
        #   • Starttid = nærmeste halvtime FREMOVER (avrundes opp til
        #     :00 eller :30 – f.eks. 14:05 → 14:30, 14:35 → 15:00).
        #     Hvis klokka allerede er på en halvtime, brukes den direkte.
        #   • Sluttid  = starttid + 1 time.
        #   • Kategori = sist brukte kategori (lagres i innstillinger
        #     ved lagring, se on_save nedenfor).
        # Brukeren kan justere alt med ett trykk hvis det ikke passer.
        if new:
            _now = datetime.now()
            _total = _now.hour * 60 + _now.minute
            if _total % 30 == 0:
                _start_total = _total
            else:
                _start_total = ((_total // 30) + 1) * 30
            _start_total %= (24 * 60)
            _end_total = (_start_total + 60) % (24 * 60)
            initial_start = f'{_start_total // 60:02d}:{_start_total % 60:02d}'
            initial_end   = f'{_end_total   // 60:02d}:{_end_total   % 60:02d}'
        else:
            initial_start = entry.get('start', '08:00')
            initial_end   = entry.get('end',   '08:30')
        time_state = {'start': initial_start, 'end': initial_end}

        start_btn = mk_btn(initial_start, hex_k('#4D96FF'), h=dp(50), fs=17,
                           size_hint_x=None, width=dp(96))
        end_btn   = mk_btn(initial_end,   hex_k('#4D96FF'), h=dp(50), fs=17,
                           size_hint_x=None, width=dp(96))

        def on_start_picked(hhmm):
            time_state['start'] = hhmm
            start_btn.text = hhmm
        def on_end_picked(hhmm):
            time_state['end'] = hhmm
            end_btn.text = hhmm

        start_btn.bind(on_release=lambda *_:
            self._pick_time_dialog(time_state['start'], on_start_picked))
        end_btn.bind(on_release=lambda *_:
            self._pick_time_dialog(time_state['end'], on_end_picked))

        time_row.add_widget(start_btn)
        time_row.add_widget(Label(text='Til:', size_hint_x=None, width=dp(36),
            font_size=fsp(15), color=(0, 0, 0, 1)))
        time_row.add_widget(end_btn)
        layout.add_widget(time_row)

        # ── Kategorivelger ───────────────────────────────────────
        # Knapp som viser nåværende kategori og åpner et utvalg.
        # Brukes til fargekoding i dagsplanen.
        # For NY aktivitet brukes sist brukte kategori som standard
        # (lagres i settings ved lagring) – ofte riktig siden ansatte
        # gjerne legger inn flere aktiviteter i samme kategori etter
        # hverandre (f.eks. flere måltider/aktiviteter på rad).
        last_cat  = self.data.get('settings', {}).get('last_activity_category')
        cat_state = [entry.get('category') if entry else last_cat]
        cat_btn   = mk_btn('Kategori', hex_k('#9CA3AF'),
                            h=dp(46), fs=14)
        def refresh_cat_label():
            cat = get_category(self.data, cat_state[0])
            if cat:
                cat_btn.text = f'Kategori: {cat["name"]}'
                cat_btn.btn_color = list(hex_k(cat['color']))
            else:
                cat_btn.text = 'Kategori: (ingen)'
                cat_btn.btn_color = list(hex_k('#9CA3AF'))
        def open_cat_picker(*_):
            inner = BoxLayout(orientation='vertical',
                              spacing=dp(6), padding=dp(12))
            pop_inner_ref = [None]
            def pick(cat_id):
                cat_state[0] = cat_id
                refresh_cat_label()
                pop_inner_ref[0].dismiss()
            # "Ingen" øverst
            inner.add_widget(mk_btn('(Ingen kategori)', hex_k('#9CA3AF'),
                h=dp(42), fs=14, cb=lambda *_: pick(None)))
            for c in self.data.get('kategorier', []):
                inner.add_widget(mk_btn(c['name'], hex_k(c['color']),
                    h=dp(42), fs=14, cb=lambda *_, cid=c['id']: pick(cid)))
            pop_inner = Popup(title='Velg kategori', content=inner,
                              size_hint=POPUP_MEDIUM, title_size=fsp(16))
            pop_inner_ref[0] = pop_inner
            pop_inner.open()
        cat_btn.bind(on_release=open_cat_picker)
        refresh_cat_label()
        layout.add_widget(cat_btn)

        chosen_img = [preset_image if new else entry.get('image')]
        if new and preset_image and preset_name:
            # Symbolet er allerede valgt (se _dr_new_activity_flow) –
            # vis symbolnavnet i stedet for det rå filnavnet.
            _img_label_text = 'Bilde: ' + preset_name
        else:
            _img_label_text = 'Bilde: ' + (
                os.path.basename(chosen_img[0]) if chosen_img[0] else 'ingen')

        # ── Bildeforhåndsvisning ──────────────────────────────────
        # Visuell bekreftelse på hvilket bilde aktiviteten vil bruke –
        # særlig viktig når navn/bilde kommer fra _dr_new_activity_flow
        # (symbolvalg), slik at det er tydelig at AKTIVITETEN faktisk
        # arver bildet til symbolet man trykket på, ikke bare navnet.
        # Skjult (høyde 0) når intet bilde er valgt.
        _has_img = bool(chosen_img[0] and os.path.exists(chosen_img[0]))
        img_preview = Image(
            source=chosen_img[0] or '',
            size_hint_y=None,
            height=dp(110) if _has_img else 0,
            opacity=1 if _has_img else 0,
            allow_stretch=True, keep_ratio=True,
        )
        layout.add_widget(img_preview)

        img_lbl = Label(
            text=_img_label_text,
            size_hint_y=None, height=dp(26), font_size=fsp(13), color=(0.3, 0.3, 0.3, 1))
        layout.add_widget(img_lbl)
        layout.add_widget(mk_btn('Velg bilde', hex_k('#4D96FF'), h=dp(48),
            cb=lambda *_: self._pick_from_folders(chosen_img, img_lbl, img_preview)))

        btn_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        def on_save(*_):
            nm = name_inp.text.strip()
            st = time_state['start']
            en = time_state['end']
            if not nm or not st or not en:
                self._toast('Fyll inn navn og tidspunkt.')
                return
            sel = getattr(self, '_dr_selected_day', today_code())
            # Sikre at dagsplaner-dict og dag-listen finnes
            self.data.setdefault('dagsplaner', {
                c: [] for c in DAY_CODES})
            self.data['dagsplaner'].setdefault(sel, [])
            if new:
                self.data['dagsplaner'][sel].append({
                    'id': str(uuid.uuid4()), 'name': nm,
                    'start': st, 'end': en, 'image': chosen_img[0],
                    'category': cat_state[0]})
            else:
                entry.update({'name': nm, 'start': st, 'end': en,
                              'image': chosen_img[0],
                              'category': cat_state[0]})
            # Husk kategorien til neste gang man oppretter en ny aktivitet
            self.data.setdefault('settings', {})['last_activity_category'] = cat_state[0]
            save_struct(self.data)
            Clock.schedule_once(lambda *_: _update_widget(self.data), 0.2)
            Clock.schedule_once(lambda *_: self._reschedule_dagsplan_notifs(), 0.3)
            pop_ref[0].dismiss()
            self._build_dagsrytme_ui()

        save_btn = mk_btn('Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_save)

        # Lagre-knappen er aktiv (grønn) kun når navnefeltet har tekst –
        # forhindrer aktiviteter uten navn og gir tydelig "klar til å
        # lagre"-tilbakemelding. Tid/kategori har alltid gyldige
        # standardverdier, så navn er det eneste som mangler for nye
        # aktiviteter.
        def _update_save_state(*_):
            has_text = bool(name_inp.text.strip())
            save_btn.disabled  = not has_text
            save_btn.btn_color = list(hex_k('#6BCB77' if has_text else '#B0B8C4'))
        name_inp.bind(text=_update_save_state)
        _update_save_state()

        btn_row.add_widget(save_btn)
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss()))
        layout.add_widget(btn_row)

        pop = Popup(title='Ny aktivitet' if new else 'Rediger aktivitet',
                    content=layout, size_hint=POPUP_LARGE)
        pop_ref[0] = pop; pop.open()

        # Auto-fokus på navnefeltet for nye aktiviteter UTEN forhåndsvalgt
        # symbol – tastaturet dukker opp med én gang, og siden tid/kategori
        # allerede har fornuftige standardverdier kan brukeren ofte bare
        # skrive navnet og trykke Lagre. Liten forsinkelse slik at popup-en
        # er ferdig rendret/animert inn før fokus settes (ellers kan
        # tastaturet på enkelte Android-versjoner ikke dukke opp).
        #
        # Hvis navn allerede er forhåndsutfylt fra et valgt symbol
        # (preset_name), trengs ikke tastaturet – brukeren kan bare
        # bekrefte tid/kategori og trykke Lagre direkte.
        if new and not preset_name:
            Clock.schedule_once(lambda *_: setattr(name_inp, 'focus', True), 0.35)

    # ══════════════════════════════════════════════════
    #  TIDSUR
    # ══════════════════════════════════════════════════

    def _export_popup(self, mode, seq=None):
        """
        Eksporter dagsplan eller handlingsrekke som PNG til Nedlastinger.
        Viser popup med ubestemt ProgressBar og «Eksporterer...» mens det pågår.
        Kjøres i bakgrunnstråd for å ikke fryse UI.
        """
        if not PIL_OK:
            self._toast('PIL ikke tilgjengelig.')
            return
        import datetime as _dt, threading

        # Dagsplan: bruk valgt dag sin plan
        if mode == 'dagsrytme':
            sel = getattr(self, '_dr_selected_day', today_code())
            entries = sorted(
                get_day_plan(self.data, sel),
                key=lambda e: e.get('start', '00:00'))
            title = f'Dagsplan_{DAY_FULL_NO.get(sel, sel)}'
        else:
            entries = seq.get('items', []) if seq else []
            title   = seq.get('name', 'Rekke') if seq else 'Rekke'

        fname = f'{title}_{_dt.date.today()}.png'

        if not entries:
            self._toast('Ingen innhold å eksportere.')
            return

        # ── Spinner-popup ─────────────────────────────────────────
        spin_box = BoxLayout(orientation='vertical',
                             spacing=dp(16), padding=dp(20))
        spin_box.add_widget(Label(
            text='Eksporterer...', font_size=fsp(16), bold=True,
            color=(0.08, 0.10, 0.35, 1),
            size_hint_y=None, height=dp(32), halign='center'))
        pb = ProgressBar(max=100, value=0,
                         size_hint_y=None, height=dp(16))
        spin_box.add_widget(pb)
        spin_box.add_widget(Label(
            text=fname, font_size=fsp(12),
            color=(0.4, 0.44, 0.55, 1),
            size_hint_y=None, height=dp(24), halign='center'))

        spin_pop = Popup(
            title='', content=spin_box,
            size_hint=POPUP_SMALL,
            auto_dismiss=False,
            separator_height=0)
        spin_pop.open()

        # Pulserende progressbar – simulerer aktivitet (ubestemt)
        _pb_dir = [1]
        def _pulse_pb(dt):
            pb.value = (pb.value + 3 * _pb_dir[0]) % 101
            if pb.value >= 100: _pb_dir[0] = -1
            if pb.value <= 0:   _pb_dir[0] =  1
        _pb_event = Clock.schedule_interval(_pulse_pb, 0.03)

        def _do():
            try:
                # ── Sideoppsett ───────────────────────────────────────────
                MAX_PER_PAGE = 6          # maks aktiviteter per side
                W            = 800
                HEADER_H     = 62         # overskrift-blokk
                PAGE_H       = 1050       # fast sidehøyde
                PAD          = 18
                AVAIL_H      = PAGE_H - HEADER_H - PAD * 2

                try:
                    fh = ImageFont.truetype(_FONT_PATH, 34)
                    fr = ImageFont.truetype(_FONT_PATH, 24)
                    fs = ImageFont.truetype(_FONT_PATH, 18)
                    fp = ImageFont.truetype(_FONT_PATH, 15)
                except Exception:
                    fh = fr = fs = fp = ImageFont.load_default()

                pages = [entries[i:i+MAX_PER_PAGE]
                         for i in range(0, max(len(entries), 1), MAX_PER_PAGE)]
                saved_files = []

                for page_idx, page_entries in enumerate(pages):
                    n_rows = max(len(page_entries), 1)
                    ROW    = min(AVAIL_H // n_rows, 160)
                    H      = HEADER_H + PAD * 2 + ROW * n_rows

                    img = PILImage.new('RGB', (W, H), (250, 251, 255))
                    d   = ImageDraw.Draw(img)

                    hdr_text = title if len(pages) == 1 else f'{title}  ({page_idx+1}/{len(pages)})'
                    d.rectangle([0, 0, W, HEADER_H], fill=(21, 28, 68))
                    d.text((W//2, HEADER_H//2), hdr_text, font=fh,
                           fill=(255, 255, 255), anchor='mm')

                    for i, e in enumerate(page_entries):
                        y  = PAD + HEADER_H + i * ROW
                        bg = (240, 242, 252) if i % 2 == 0 else (248, 249, 255)
                        d.rectangle([0, y, W, y + ROW - 2], fill=bg)
                        d.rectangle([0, y, 4, y + ROW - 2], fill=(77, 150, 255))

                        nx = PAD + 8
                        if mode == 'dagsrytme':
                            tid = f"{e.get('start', '')}\u2013{e.get('end', '')}"
                            d.text((nx, y + ROW // 2), tid, font=fs,
                                   fill=(80, 90, 120), anchor='lm')
                            nx = 190

                        img_size = ROW - 10
                        ip = e.get('image', '')
                        if ip and os.path.exists(ip):
                            try:
                                sym = PILImage.open(ip).convert('RGBA')
                                sym.thumbnail((img_size, img_size), PILImage.LANCZOS)
                                r2, g2, b2, a2 = sym.split()
                                sym_rgb = PILImage.merge('RGB', (r2, g2, b2))
                                iy = y + (ROW - sym.height) // 2
                                img.paste(sym_rgb, (nx, iy), mask=a2)
                                nx += img_size + 8
                            except Exception:
                                pass

                        d.text((nx + 4, y + ROW // 2), e.get('name', ''),
                               font=fr, fill=(20, 24, 60), anchor='lm')

                    if len(pages) > 1:
                        d.text((W // 2, H - 10),
                               f'Side {page_idx+1} av {len(pages)}',
                               font=fp, fill=(140, 150, 170), anchor='mb')

                    if len(pages) == 1:
                        dst = os.path.join(DOWNLOAD_DIR, fname)
                    else:
                        base, ext = os.path.splitext(fname)
                        dst = os.path.join(DOWNLOAD_DIR,
                                           f'{base}_side{page_idx+1}{ext}')
                    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                    img.save(dst)
                    saved_files.append(os.path.basename(dst))

                def _done(*_):
                    _pb_event.cancel()
                    spin_pop.dismiss()
                    if len(saved_files) == 1:
                        self._toast(f'Lagret: {saved_files[0]}')
                    else:
                        self._toast(f'Lagret {len(saved_files)} sider til Nedlastinger')
                Clock.schedule_once(_done, 0)
                Clock.schedule_once(_done, 0)
            except Exception as ex:
                _msg = str(ex)
                def _err(*_):
                    _pb_event.cancel()
                    spin_pop.dismiss()
                    self._toast(f'Eksport feilet: {_msg}')
                Clock.schedule_once(_err, 0)

        threading.Thread(target=_do, daemon=True).start()

    def _nav_tidsur(self):
        self._push('home')
        self._show_tidsur()

    def _show_tidsur(self, **_):
        self._cur_scr = 'tidsur'
        self._set_title('Tidsur')
        if not hasattr(self, '_timer_sek'):
            self._timer_sek       = 300
            self._timer_total_sek = 300
            self._timer_running   = False
            self._timer_event     = None

        root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        # Hvis tidsuret er knyttet til en aktivitet, vises navnet over
        # disken så brukeren vet hva tidsuret gjelder.
        if getattr(self, '_timer_label', ''):
            root.add_widget(Label(
                text=f'Tidsur: {self._timer_label}',
                size_hint_y=None, height=dp(36),
                font_size=fsp(18), bold=True,
                color=(0.04, 0.10, 0.40, 1), halign='center'))

        # Rund disk-widget – fyller all gjenværende plass (size_hint_y=1)
        # slik at Start-knappen og presettene alltid er synlige uansett
        # skjermstørrelse.
        self._timer_disk = Image(
            size_hint=(1, 1),
            allow_stretch=True, keep_ratio=True,
        )
        root.add_widget(self._timer_disk)
        self._timer_display = Label(text='05:00', size_hint_y=None, height=dp(60),
            font_size=fsp(52), bold=True, color=(0.04, 0.10, 0.40, 1), halign='center')
        root.add_widget(self._timer_display)
        self._timer_pb = ProgressBar(max=100, value=100, size_hint_y=None, height=dp(10))
        root.add_widget(self._timer_pb)

        # Start/Nullstill – plassert HER (over presettene) slik at den
        # alltid er synlig selv på mindre skjermer.
        ctrl = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(10))
        self._timer_start_btn = mk_btn(
            'Pause' if self._timer_running else 'Start',
            hex_k('#FF9F43' if self._timer_running else '#6BCB77'),
            h=dp(60), fs=20, cb=self._tidsur_toggle)
        ctrl.add_widget(self._timer_start_btn)
        ctrl.add_widget(mk_btn('Nullstill', hex_k('#FF6B6B'), h=dp(60), fs=17,
            cb=self._tidsur_reset))
        root.add_widget(ctrl)

        root.add_widget(Label(text='Velg tid:', size_hint_y=None, height=dp(24),
            font_size=fsp(14), color=(0.2, 0.2, 0.3, 1), halign='center'))

        presets = [('1 min', 60), ('2 min', 120), ('3 min', 180),
                   ('5 min', 300), ('10 min', 600), ('15 min', 900)]
        pg = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(114))
        for lbl, sek in presets:
            pg.add_widget(mk_btn(lbl, hex_k('#4D96FF'), h=dp(54), fs=14,
                cb=lambda *_, s=sek: self._tidsur_set(s)))
        root.add_widget(pg)

        cust = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        cust.add_widget(Label(text='Min:', size_hint_x=None, width=dp(44),
            font_size=fsp(15), color=(0.2, 0.2, 0.3, 1)))
        self._timer_cust_sl  = Slider(min=1, max=60, value=5, step=1)
        self._timer_cust_lbl = Label(text='5', size_hint_x=None, width=dp(34),
            font_size=fsp(15), color=(0.2, 0.2, 0.3, 1))
        self._timer_cust_sl.bind(value=lambda sl, v:
            setattr(self._timer_cust_lbl, 'text', str(int(v))))
        cust.add_widget(self._timer_cust_sl); cust.add_widget(self._timer_cust_lbl)
        cust.add_widget(mk_btn('Sett', hex_k('#FF9F43'), h=dp(48), fs=14,
            size_hint_x=None, width=dp(76),
            cb=lambda *_: self._tidsur_set(int(self._timer_cust_sl.value) * 60)))
        root.add_widget(cust)

        self._tidsur_refresh_display()
        self._set_content(root)

    def _tidsur_set(self, seconds, label=None):
        """
        Setter tidsur til 'seconds' sekunder. Hvis label er gitt, vises
        den over telleren – brukes når tidsuret startes fra en aktivitet
        i dagsplan, så brukeren ser hva tidsuret gjelder.
        """
        self._tidsur_stop()
        self._timer_sek = self._timer_total_sek = seconds
        self._timer_label = label or ''
        self._tidsur_refresh_display()

    def _start_timer_for_activity(self, entry, end_minute):
        """
        Starter tidsuret med gjenstående tid for en aktivitet, og
        navigerer til tidsur-skjermen. Hvis aktiviteten er over, fyrer
        ikke noe.
        """
        now   = datetime.now()
        now_m = now.hour * 60 + now.minute
        remaining_min = end_minute - now_m
        if remaining_min <= 0:
            self._toast('Aktiviteten er allerede ferdig.')
            return
        seconds = remaining_min * 60
        # Bytt skjerm og pre-fyll tidsuret. Starter ikke automatisk –
        # brukeren får mulighet til å se det og starte selv.
        self._push('home')
        self._show_tidsur()
        self._tidsur_set(seconds, label=entry.get('name', ''))

    def _tidsur_toggle(self, *_):
        if self._timer_running:
            self._tidsur_stop()
        else:
            self._tidsur_start()

    def _tidsur_start(self):
        if getattr(self, '_timer_sek', 0) <= 0:
            return
        self._timer_running = True
        if hasattr(self, '_timer_start_btn'):
            self._timer_start_btn.text      = 'Pause'
            self._timer_start_btn.btn_color = list(hex_k('#FF9F43'))
        self._timer_event = Clock.schedule_interval(self._tidsur_tick, 1)
        self._schedule_timer_notif()   # planlegg varsel for når tidsuret er ferdig

    def _tidsur_stop(self):
        self._timer_running = False
        self._pulse_phase   = 0.0   # nullstill puls ved stopp
        ev = getattr(self, '_timer_event', None)
        if ev:
            ev.cancel()
            self._timer_event = None
        if hasattr(self, '_timer_start_btn') and self._timer_start_btn:
            self._timer_start_btn.text      = 'Start'
            self._timer_start_btn.btn_color = list(hex_k('#6BCB77'))
        self._cancel_alarm(NOTIF_TIMER)   # avbryt varsel ved pause/stopp

    def _tidsur_reset(self, *_):
        self._tidsur_stop()
        self._timer_sek = getattr(self, '_timer_total_sek', 300)
        self._tidsur_refresh_display()
        self._cancel_alarm(NOTIF_TIMER)

    # ══════════════════════════════════════════════════════════════════
    #  NOTIFIKASJONER (Android)
    #  Push-varsler via AlarmManager + KtAlarmReceiver.java.
    #  Vises kun når appen er i bakgrunnen (kontrollert via app_state.txt).
    # ══════════════════════════════════════════════════════════════════

    def _notif_on(self, kind: str) -> bool:
        """True hvis varsler av typen 'timer' eller 'dagsplan' er skrudd på."""
        return bool(self.data.get('settings', {}).get(f'notifications_{kind}', False))

    def _write_app_state(self, foreground: bool) -> None:
        """Skriver forgrunns-tilstand til fil lest av KtAlarmReceiver."""
        if not DATA_DIR:
            return
        try:
            with open(os.path.join(DATA_DIR, 'app_state.txt'), 'w') as _f:
                _f.write('1' if foreground else '0')
        except Exception:
            pass

    def _schedule_alarm(self, notif_id: int, title: str,
                        body: str, epoch_ms: int,
                        image_path: str = None) -> None:
        """
        Planlegger ett Android-varsel via AlarmManager.

        epoch_ms: tidspunkt i millisekunder siden Unix-epoch (UTC).
        Bruker setExactAndAllowWhileIdle for å fyre i Doze-modus;
        faller tilbake til setAndAllowWhileIdle hvis eksakt alarm
        ikke er tillatt (Android 12+).

        image_path: valgfri sti til aktivitetsbilde – vises som
        stort ikon/big-picture i varselet (KtAlarmReceiver.java).

        VIKTIG: extras settes via en Bundle med putString()/putInt(),
        IKKE intent.putExtra() direkte. pyjnius kan ikke alltid løse
        riktig overload for Intent.putExtra() (String vs CharSequence
        vs Serializable), noe som resulterer i at Java-siden får
        getStringExtra()==null. Bundle.putString()/putInt() har
        utvetydige signaturer og er trygge fra pyjnius.
        """
        if platform != 'android':
            return
        try:
            from jnius import autoclass
            PythonActivity  = autoclass('org.kivy.android.PythonActivity')
            Intent          = autoclass('android.content.Intent')
            Bundle          = autoclass('android.os.Bundle')
            PendingIntent   = autoclass('android.app.PendingIntent')
            AlarmManager    = autoclass('android.app.AlarmManager')
            KtAlarmReceiver = autoclass(
                'no.askapp.kommunikasjonstavle.KtAlarmReceiver')

            ctx    = PythonActivity.mActivity
            intent = Intent(ctx, KtAlarmReceiver)

            extras = Bundle()
            extras.putInt('notif_id', int(notif_id))
            extras.putString('title', title)
            extras.putString('body',  body)
            if image_path:
                extras.putString('image_path', image_path)
            intent.putExtras(extras)

            flags = PendingIntent.FLAG_UPDATE_CURRENT
            try:
                flags |= PendingIntent.FLAG_IMMUTABLE   # API 23+
            except Exception:
                pass

            pi = PendingIntent.getBroadcast(ctx, notif_id, intent, flags)
            am = ctx.getSystemService('alarm')

            # Forsøk eksakt alarm; faller tilbake ved PermissionError (API 31+)
            try:
                am.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP, epoch_ms, pi)
            except Exception:
                am.setAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP, epoch_ms, pi)
        except Exception as _e:
            logging.warning('_schedule_alarm feilet: %s', _e)

    def _cancel_alarm(self, notif_id: int) -> None:
        """Avbryter et planlagt AlarmManager-varsel."""
        if platform != 'android':
            return
        try:
            from jnius import autoclass
            PythonActivity  = autoclass('org.kivy.android.PythonActivity')
            Intent          = autoclass('android.content.Intent')
            PendingIntent   = autoclass('android.app.PendingIntent')
            AlarmManager    = autoclass('android.app.AlarmManager')
            KtAlarmReceiver = autoclass(
                'no.askapp.kommunikasjonstavle.KtAlarmReceiver')

            ctx    = PythonActivity.mActivity
            intent = Intent(ctx, KtAlarmReceiver)
            flags  = PendingIntent.FLAG_NO_CREATE
            try:
                flags |= PendingIntent.FLAG_IMMUTABLE
            except Exception:
                pass

            pi = PendingIntent.getBroadcast(ctx, notif_id, intent, flags)
            if pi is not None:
                am = ctx.getSystemService('alarm')
                am.cancel(pi)
        except Exception as _e:
            logging.warning('_cancel_alarm feilet: %s', _e)

    def _schedule_timer_notif(self) -> None:
        """Planlegger 'Tidsur ferdig'-varsel basert på gjenværende sekunder."""
        self._cancel_alarm(NOTIF_TIMER)
        if not self._notif_on('timer'):
            return
        sek = getattr(self, '_timer_sek', 0)
        if sek <= 0:
            return
        epoch_ms = int((time.time() + sek) * 1000)
        title = (f'Tidsuret for "{self._timer_label}" er ferdig'
                 if getattr(self, '_timer_label', '') else 'Tidsuret er ferdig')
        self._schedule_alarm(
            NOTIF_TIMER,
            title,
            'Tiden er ute.',
            epoch_ms)

    def _reschedule_dagsplan_notifs(self) -> None:
        """
        Avbryter og gjenplanlegger alle dagsplan-varsler for i dag.

        Logikk iht. spesifikasjon:
          • Start-varsel for hver aktivitet.
          • Slutt-varsel KUN hvis neste aktivitet starter på et annet
            tidspunkt enn denne slutter, ELLER det er siste aktivitet.
        """
        # Avbryt alt som måtte ligge inne
        for _i in range(32):
            self._cancel_alarm(NOTIF_DAG_START_BASE + _i)
            self._cancel_alarm(NOTIF_DAG_END_BASE   + _i)

        if not self._notif_on('dagsplan'):
            return

        entries = sorted(
            get_day_plan(self.data, today_code()),
            key=lambda e: e.get('start', '00:00'))
        if not entries:
            return

        now_m = datetime.now().hour * 60 + datetime.now().minute

        def _epoch(h_m: int) -> int:
            """Minutter siden midnatt → epoch-ms i dag."""
            t = datetime.now().replace(
                hour=h_m // 60, minute=h_m % 60,
                second=0, microsecond=0)
            return int(t.timestamp() * 1000)

        for idx, entry in enumerate(entries[:32]):
            s_m   = self._dr_parse(entry.get('start', '00:00'))
            e_m   = self._dr_parse(entry.get('end',   '23:59'))
            name  = entry.get('name', 'Aktivitet')
            s_str = entry.get('start', '')
            e_str = entry.get('end',   '')
            img   = entry.get('image') or None
            if img and not os.path.exists(img):
                img = None

            # Start-varsel (kun i fremtiden)
            if s_m > now_m:
                self._schedule_alarm(
                    NOTIF_DAG_START_BASE + idx,
                    f'Aktiviteten {name} starter nå',
                    f'{s_str}–{e_str}',
                    _epoch(s_m),
                    image_path=img)

            # Slutt-varsel: kun hvis neste aktivitet IKKE starter akkurat nå
            if e_m > now_m:
                nxt = entries[idx + 1] if idx + 1 < len(entries) else None
                nxt_s_m = self._dr_parse(nxt['start']) if nxt else -1

                if nxt_s_m != e_m:          # gap eller ingen neste
                    if nxt:
                        body = f'Neste: {nxt["name"]} kl. {nxt.get("start","")}'
                    else:
                        body = 'Ingen flere aktiviteter i dag'
                    self._schedule_alarm(
                        NOTIF_DAG_END_BASE + idx,
                        f'Aktiviteten {name} er nå ferdig',
                        body,
                        _epoch(e_m),
                        image_path=img)

    def _request_notification_permission(self) -> None:
        """Ber om POST_NOTIFICATIONS-tillatelse på Android 13+ (API 33)."""
        if platform != 'android':
            return
        try:
            from jnius import autoclass
            Build   = autoclass('android.os.Build')
            if Build.VERSION.SDK_INT < 33:
                return
            Activity    = autoclass('android.app.Activity')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            ctx = PythonActivity.mActivity
            perm = 'android.permission.POST_NOTIFICATIONS'
            pm = ctx.getPackageManager()
            if pm.checkPermission(perm, ctx.getPackageName()) != 0:
                ctx.requestPermissions([perm], 1002)
        except Exception as _e:
            logging.warning('_request_notification_permission: %s', _e)

    def _tidsur_tick(self, dt):
        self._timer_sek = max(0, getattr(self, '_timer_sek', 0) - 1)
        if self._timer_sek <= 0:
            self._tidsur_stop()
            self._toast('Tiden er ute!', duration=4.0)
            Clock.schedule_once(lambda *_: launch_confetti(3.0), 0.1)
            return
        total = max(getattr(self, '_timer_total_sek', 1), 1)
        frac  = self._timer_sek / total
        # Puls-fase: øk bare når under 20% igjen
        if frac < 0.20:
            self._pulse_phase = getattr(self, '_pulse_phase', 0.0) + 0.22
        else:
            self._pulse_phase = 0.0
        self._tidsur_refresh_display()

    def _tidsur_refresh_display(self):
        if not hasattr(self, '_timer_display') or not self._timer_display:
            return
        sek   = getattr(self, '_timer_sek', 0)
        total = max(getattr(self, '_timer_total_sek', 1), 1)
        frac  = sek / total          # 1.0=full, 0.0=tom
        mins  = sek // 60; secs = sek % 60
        self._timer_display.text = f'{mins:02d}:{secs:02d}'
        if hasattr(self, '_timer_pb') and self._timer_pb:
            self._timer_pb.value = int(frac * 100)
        # Tegn rund disk med PIL
        if hasattr(self, '_timer_disk') and self._timer_disk and PIL_OK:
            self._draw_timer_disk(frac)

    def _draw_timer_disk(self, frac):
        """
        Pai-animasjon. Under 20% pulserer fargen via sin-kurve
        mellom dyp rød og lys oransje for å varsle brukeren.
        """
        import math as _math
        SIZE = 300
        cx = cy = SIZE // 2
        r  = SIZE // 2 - 8

        pil_img = PILImage.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
        d       = ImageDraw.Draw(pil_img)

        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(245, 245, 248, 255))

        if frac > 0.001:
            if frac > 0.20:
                col = (229, 57, 53, 255)
            else:
                phase = getattr(self, '_pulse_phase', 0.0)
                pulse = (_math.sin(phase) + 1) / 2
                col = (
                    int(220 + 35 * pulse),
                    int(30  + 80 * pulse),
                    int(20  * (1 - pulse)),
                    255
                )
            end_angle = -90 + frac * 360
            d.pieslice([cx-r, cy-r, cx+r, cy+r],
                       start=-90, end=end_angle, fill=col)

        d.ellipse([cx-r, cy-r, cx+r, cy+r],
                  outline=(180, 60, 50, 180), width=3)

        # Konvertér til Kivy-tekstur
        raw = pil_img.convert('RGBA').tobytes()
        tex = Texture.create(size=(SIZE, SIZE), colorfmt='rgba')
        tex.blit_buffer(raw, colorfmt='rgba', bufferfmt='ubyte')
        tex.flip_vertical()
        self._timer_disk.texture = tex

    # ══════════════════════════════════════════════════
    #  BILDEPAR-SPILL
    # ══════════════════════════════════════════════════

    def _nav_bildepar(self):
        all_images = [
            {'path': it['image'], 'name': it['name']}
            for fo in self.data.get('folders', [])
            for it in fo.get('items', [])
            if it.get('image') and os.path.exists(it['image'])
        ]
        if len(all_images) < 2:
            self._toast('Trenger minst 2 bilder i mappene for å spille.')
            return
        self._push('home')
        self._bildepar_setup_popup(all_images)

    def _bildepar_setup_popup(self, all_images):
        max_pairs = min(6, len(all_images))
        chosen    = [min(4, max_pairs)]
        pop_ref   = [None]

        layout = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(16))
        layout.add_widget(Label(text='Velg antall par:', size_hint_y=None, height=dp(36),
            font_size=fsp(18), bold=True, color=(0.08, 0.10, 0.35, 1), halign='center'))

        pg = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(130))
        pb_list = []
        for n in range(2, max_pairs + 1):
            b = mk_btn(f'{n} par', hex_k('#4D96FF' if n != chosen[0] else '#0D47A1'),
                       h=dp(56), fs=15)
            def sel(_, v=n, blist=pb_list, rng=range(2, max_pairs+1)):
                chosen[0] = v
                for bi, ni in zip(blist, rng):
                    bi.btn_color = list(hex_k('#0D47A1' if ni == v else '#4D96FF'))
            b.bind(on_release=sel); pg.add_widget(b); pb_list.append(b)
        layout.add_widget(pg)

        def on_start(*_):
            n = chosen[0]
            sel_imgs = random.sample(all_images, n)
            cards = []
            for pid, img in enumerate(sel_imgs):
                cards.append({'pair_id': pid, 'path': img['path'], 'name': img['name']})
                cards.append({'pair_id': pid, 'path': img['path'], 'name': img['name']})
            random.shuffle(cards)
            pop_ref[0].dismiss()
            self._start_bildepar_game(cards)

        layout.add_widget(mk_btn('Start spill', hex_k('#6BCB77'), h=dp(58), fs=18, cb=on_start))
        layout.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(50), fs=14,
            cb=lambda *_: (pop_ref[0].dismiss(), self.nav_stack.pop() if self.nav_stack else None)))
        pop = Popup(title='Bildepar-spill', content=layout, size_hint=POPUP_MEDIUM)
        pop_ref[0] = pop; pop.open()

    def _start_bildepar_game(self, cards):
        self._cur_scr = 'bildepar'
        self._set_title('Bildepar-spill')
        self._bp_cards    = cards
        self._bp_state    = ['hidden'] * len(cards)
        self._bp_revealed = []
        self._bp_moves    = 0
        self._bp_matches  = 0

        root = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(8))
        self._bp_status_lbl = Label(
            text=f'Trekk: 0  |  Par funnet: 0 / {len(cards)//2}',
            size_hint_y=None, height=dp(34),
            font_size=fsp(15), color=(0.2, 0.2, 0.35, 1), halign='center')
        root.add_widget(self._bp_status_lbl)

        ncols = 3 if len(cards) <= 12 else 4
        self._bp_grid = GridLayout(cols=ncols, spacing=dp(6), size_hint_y=None)
        self._bp_grid.bind(minimum_height=self._bp_grid.setter('height'))
        sv = ScrollView(); sv.add_widget(self._bp_grid); root.add_widget(sv)

        self._bildepar_rebuild_grid()
        self._set_content(root)

    def _bildepar_rebuild_grid(self):
        if not hasattr(self, '_bp_grid') or not self._bp_grid:
            return
        self._bp_grid.clear_widgets()
        for idx, card in enumerate(self._bp_cards):
            state = self._bp_state[idx]
            h     = dp(118)
            if state == 'matched':
                cell = RBox(orientation='vertical', size_hint_y=None, height=h,
                    spacing=dp(2), padding=dp(3),
                    box_color=(0.84, 0.96, 0.84, 1.0), radius=dp(14))
                cell.add_widget(Image(source=card['path'], size_hint=(1, None), height=dp(82),
                    allow_stretch=True, keep_ratio=True))
                cell.add_widget(Label(text=card['name'], font_size=fsp(11),
                    size_hint_y=None, height=dp(26),
                    color=(0.1, 0.45, 0.1, 1), halign='center'))
            elif state == 'revealed':
                cell = RBox(orientation='vertical', size_hint_y=None, height=h,
                    spacing=dp(2), padding=dp(3),
                    box_color=(1.0, 0.95, 0.80, 1.0), radius=dp(14))
                cell.add_widget(Image(source=card['path'], size_hint=(1, None), height=dp(82),
                    allow_stretch=True, keep_ratio=True))
                cell.add_widget(Label(text=card['name'], font_size=fsp(11),
                    size_hint_y=None, height=dp(26),
                    color=(0.50, 0.35, 0.00, 1), halign='center'))
            else:
                cell = RBox(size_hint_y=None, height=h,
                    box_color=list(hex_k('#4D96FF')), radius=dp(14))
                btn  = RBtn(text='?', btn_color=list(hex_k('#4D96FF')),
                    color=(1, 1, 1, 1), bold=True, font_size=fsp(32), radius=dp(14))
                btn.bind(on_release=lambda b, i=idx: self._bildepar_tap(i))
                cell.add_widget(btn)
            self._bp_grid.add_widget(cell)

    def _bildepar_flip_cell(self, idx, on_done):
        """
        Flip-animasjon: scale_x 1→0 (forsvinner), bytt innhold, scale_x 0→1.
        """
        cells = list(self._bp_grid.children)
        n = len(self._bp_cards)
        ci = n - 1 - idx
        if ci < 0 or ci >= len(cells):
            self._bp_state[idx] = 'revealed'
            self._bildepar_rebuild_grid()
            on_done(); return
        cell = cells[ci]
        def _phase2(*_):
            self._bp_state[idx] = 'revealed'
            self._bildepar_rebuild_grid()
            new_cells = list(self._bp_grid.children)
            if ci < len(new_cells):
                nc = new_cells[ci]
                nc.size_hint_x = 0.01
                a2 = Animation(size_hint_x=1, duration=0.11, t='out_quad')
                a2.bind(on_complete=lambda *_: on_done())
                a2.start(nc)
            else:
                on_done()
        a1 = Animation(size_hint_x=0.01, duration=0.09, t='in_quad')
        a1.bind(on_complete=_phase2)
        a1.start(cell)

    def _bildepar_tap(self, idx):
        if self._bp_state[idx] != 'hidden' or len(self._bp_revealed) >= 2:
            return
        self._bp_revealed.append(idx)
        def after_flip():
            if len(self._bp_revealed) < 2:
                return
            self._bp_moves += 1
            i1, i2 = self._bp_revealed
            if self._bp_cards[i1]['pair_id'] == self._bp_cards[i2]['pair_id']:
                self._bp_state[i1] = self._bp_state[i2] = 'matched'
                self._bp_revealed  = []
                self._bp_matches  += 1
                self._bildepar_rebuild_grid()
                self._bildepar_update_status()
                if self._bp_matches == len(self._bp_cards) // 2:
                    Clock.schedule_once(lambda *_: self._bildepar_win(), 0.5)
            else:
                self._bildepar_update_status()
                Clock.schedule_once(lambda *_: self._bildepar_flip_back(), 1.1)
        self._bildepar_flip_cell(idx, after_flip)

    def _bildepar_flip_back(self):
        for i in self._bp_revealed:
            if self._bp_state[i] == 'revealed':
                self._bp_state[i] = 'hidden'
        self._bp_revealed = []
        self._bildepar_rebuild_grid()

    def _bildepar_update_status(self):
        if hasattr(self, '_bp_status_lbl') and self._bp_status_lbl:
            self._bp_status_lbl.text = (
                f'Trekk: {self._bp_moves}  |  '
                f'Par funnet: {self._bp_matches} / {len(self._bp_cards) // 2}')

    def _bildepar_win(self):
        lbl = Label(
            text=f'Gratulerer!\nAlle {self._bp_matches} par funnet\ni løpet av {self._bp_moves} trekk!',
            font_size=fsp(19), color=(0.1, 0.5, 0.1, 1),
            halign='center', valign='middle')
        lbl.bind(size=lbl.setter('text_size'))
        pop_ref = [None]
        br = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        layout = BoxLayout(orientation='vertical', spacing=dp(16), padding=dp(20))
        layout.add_widget(lbl); layout.add_widget(br)
        all_imgs = [
            {'path': it['image'], 'name': it['name']}
            for fo in self.data.get('folders', [])
            for it in fo.get('items', [])
            if it.get('image') and os.path.exists(it['image'])
        ]
        br.add_widget(mk_btn('Spill igjen', hex_k('#6BCB77'), h=dp(52), fs=16,
            cb=lambda *_: (pop_ref[0].dismiss(), self._bildepar_setup_popup(all_imgs))))
        br.add_widget(mk_btn('Hjem', hex_k('#4D96FF'), h=dp(52), fs=16,
            cb=lambda *_: (pop_ref[0].dismiss(), self.go_home())))
        pop = Popup(title='Spill fullfort!', content=layout, size_hint=POPUP_SMALL)
        pop_ref[0] = pop; pop.open()

    # ══════════════════════════════════════════════════
    #  POPUP – REDIGER MAPPE
    # ══════════════════════════════════════════════════

    # ══════════════════════════════════════════════════
    #  POPUP – REDIGER MAPPE
    # ══════════════════════════════════════════════════

    def _folder_popup(self, fo):
        new    = fo is None
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        layout.add_widget(Label(
            text='Mappenavn:', size_hint_y=None, height=dp(28),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        name_inp = smart_input(
            text='' if new else fo['name'],
            hint='Mappenavn',
            on_save=lambda: on_ok(),
        )
        layout.add_widget(name_inp)

        layout.add_widget(Label(
            text='Velg farge:', size_hint_y=None, height=dp(26),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        chosen_color = [fo['color'] if fo else FOLDER_COLORS[0]]

        # ── Fane-toggle for fargevalg ─────────────────────────────
        f_tab_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        f_btn_pal = mk_btn('Palett',   hex_k('#0D47A1'), h=dp(38), fs=13)
        f_btn_grd = mk_btn('Gradient', hex_k('#4D96FF'), h=dp(38), fs=13)
        f_tab_row.add_widget(f_btn_pal); f_tab_row.add_widget(f_btn_grd)
        layout.add_widget(f_tab_row)

        f_color_box = BoxLayout(orientation='vertical',
                                size_hint_y=None, height=dp(130))
        layout.add_widget(f_color_box)

        def build_folder_palette():
            f_color_box.clear_widgets()
            f_btn_pal.btn_color = list(hex_k('#0D47A1'))
            f_btn_grd.btn_color = list(hex_k('#4D96FF'))
            col_grid = GridLayout(cols=4, spacing=dp(6),
                                  size_hint_y=None, height=dp(118))
            col_btns = []
            for c in FOLDER_COLORS:
                cb = RBtn(btn_color=list(hex_k(c)),
                          size_hint=(1, None), height=dp(52),
                          opacity=1.0 if chosen_color[0] == c else 0.5,
                          radius=dp(14))
                def pick(b, col=c, btns=col_btns, sel=chosen_color):
                    sel[0] = col
                    for x in btns: x.opacity = 0.5
                    b.opacity = 1.0
                cb.bind(on_release=pick)
                col_grid.add_widget(cb); col_btns.append(cb)
            f_color_box.add_widget(col_grid)
            f_color_box.height = dp(126)

        def build_folder_gradient():
            f_color_box.clear_widgets()
            f_btn_pal.btn_color = list(hex_k('#4D96FF'))
            f_btn_grd.btn_color = list(hex_k('#0D47A1'))
            def on_fc(hex_c): chosen_color[0] = hex_c
            gp = GradientColorPicker(
                on_color=on_fc, initial_hex=chosen_color[0],
                size_hint_y=None,
                height=dp(GradientColorPicker.TOTAL_H * 1.35),
            )
            f_color_box.add_widget(gp)
            f_color_box.height = dp(int(GradientColorPicker.TOTAL_H * 1.35) + 4)

        f_btn_pal.bind(on_release=lambda *_: build_folder_palette())
        f_btn_grd.bind(on_release=lambda *_: build_folder_gradient())
        build_folder_palette()

        chosen_img = [fo.get('image') if fo else None]
        img_lbl = Label(
            text='Bilde: ' + (os.path.basename(chosen_img[0]) if chosen_img[0] else 'ingen'),
            size_hint_y=None, height=dp(26),
            font_size=sp(13), color=(0.3, 0.3, 0.3, 1),
        )
        layout.add_widget(img_lbl)

        pop_ref = [None]
        pick_btn = mk_btn('Velg bilde fra enhet', hex_k('#4D96FF'), h=dp(48))
        pick_btn.bind(on_release=lambda *_: self._pick_image(
            chosen_img, img_lbl))
        layout.add_widget(pick_btn)

        btn_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))

        def on_ok(*_):
            nm = name_inp.text.strip()
            if not nm:
                return
            if new:
                self.data['folders'].append({
                    'id':          str(uuid.uuid4()),
                    'name':        nm,
                    'color':       chosen_color[0],
                    'image':       chosen_img[0],
                    'items':       [],
                    'user_created': True,
                })
            else:
                fo.update({'name': nm, 'color': chosen_color[0], 'image': chosen_img[0]})
            save_struct(self.data)
            pop_ref[0].dismiss()
            self._show_home()

        btn_row.add_widget(mk_btn('Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_ok))
        btn_row.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss(),
        ))
        layout.add_widget(btn_row)

        pop = Popup(
            title='Ny mappe' if new else 'Rediger mappe',
            content=layout, size_hint=POPUP_LARGE,
        )
        pop_ref[0] = pop
        pop.open()

    def _del_folder(self, fo):
        item_count = len(fo.get('items', []))
        sub_count  = len(fo.get('subfolders', []))
        details = []
        if item_count:
            details.append(f'{item_count} bilde' + ('r' if item_count != 1 else ''))
        if sub_count:
            details.append(f'{sub_count} undermappe' + ('r' if sub_count != 1 else ''))
        detail_str = ' med ' + ' og '.join(details) if details else ''
        self._confirm(
            title='Slette mappe?',
            message=f'Mappen "{fo.get("name", "")}"{detail_str} '
                    f'vil forsvinne fra appen.',
            on_confirm=lambda: self._do_del_folder(fo),
        )

    def _do_del_folder(self, fo):
        self.data['folders'] = [f for f in self.data['folders'] if f['id'] != fo['id']]
        save_struct(self.data)
        self._show_home()

    # ══════════════════════════════════════════════════
    #  POPUP – REDIGER ELEMENT
    # ══════════════════════════════════════════════════

    def _item_popup(self, fo, it):
        new = it is None

        # ScrollView sørger for at innholdet kan scrolles opp når tastaturet
        # dukker opp – forutsetter at Window.softinput_mode = 'below_target'.
        sv     = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14),
                           size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        # ── Bildeforhåndsvisning ──────────────────────────────────
        # Høyden tilpasses bildets sideforhold (innen 120–280dp).
        # En liggende thumbnail får da lav høyde uten tom plass over og under;
        # et stående bilde får mer høyde uten å bli klemt sammen.
        init_src = ''
        if it and it.get('image') and os.path.exists(it.get('image', '')):
            init_src = it['image']
        img_preview = Image(
            source=init_src,
            size_hint_y=None, height=dp(180),
            allow_stretch=True, keep_ratio=True,
        )

        def _resize_preview(img, *_):
            """Justerer høyden basert på bildets sideforhold når teksturen lastes."""
            tw, th = img.texture_size
            if tw <= 0 or th <= 0:
                return
            # Estimer tilgjengelig bredde i popup-en (POPUP_LARGE = 0.95)
            # minus padding på hver side
            popup_w = max(Window.width * 0.95 - dp(56), dp(200))
            ratio   = th / tw
            ideal   = popup_w * ratio
            img.height = max(dp(120), min(dp(280), ideal))

        img_preview.bind(texture_size=_resize_preview)
        layout.add_widget(img_preview)

        # ── Navn-felt ─────────────────────────────────────────────
        layout.add_widget(Label(
            text='Navn (etikett under bildet):',
            size_hint_y=None, height=dp(28),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        name_inp = smart_input(
            text='' if new else it['name'],
            hint='Symbolnavn',
            on_save=lambda: on_ok(),
        )
        layout.add_widget(name_inp)

        # ── Filnavn-etikett og bildevelger ────────────────────────
        chosen_img = [it.get('image') if it else None]
        img_lbl = Label(
            text='Bilde: ' + (os.path.basename(chosen_img[0]) if chosen_img[0] else 'ingen'),
            size_hint_y=None, height=dp(28),
            font_size=sp(13), color=(0.3, 0.3, 0.3, 1),
        )
        layout.add_widget(img_lbl)

        pop_ref = [None]

        def do_pick(*_):
            """Åpner bildevelger og oppdaterer forhåndsvisning + etikett."""
            if platform == 'android':
                def on_picked(result):
                    if not result:
                        self._toast('Ingen bilde valgt.')
                        return
                    # Normaliser: ta første bilde ved flervalg
                    dst = result[0] if isinstance(result, list) else result
                    if dst:
                        chosen_img[0]      = dst
                        img_lbl.text       = 'Bilde: ' + os.path.basename(dst)
                        img_preview.source = dst
                        img_preview.reload()
                        logging.info('Bilde valgt: %s', dst)
                    else:
                        self._toast('Ingen bilde valgt.')
                _open_android_picker(on_picked)
            else:
                # Fallback: bruk eksisterende _pick_image for desktop-testing
                self._pick_image(chosen_img, img_lbl)

        pick_btn = mk_btn('Velg ASK-bilde fra enhet', hex_k('#4D96FF'), h=dp(48))
        pick_btn.bind(on_release=do_pick)
        layout.add_widget(pick_btn)

        # ── Auto-foreslag fra bildet ──────────────────────────────
        # Liten knapp som analyserer bildet og foreslår navn + kategori
        # basert på filnavn og dominant farge. Brukeren godkjenner før
        # noe lagres.
        def suggest_now(*_):
            if not chosen_img[0]:
                self._toast('Velg et bilde først.')
                return
            sug_name, sug_cat = _suggest_from_image(chosen_img[0])
            if not sug_name and not sug_cat:
                self._toast('Ingen forslag kunne genereres.')
                return
            # Bygg en bekreftelses-popup som viser forslagene
            inner = BoxLayout(orientation='vertical',
                              spacing=dp(10), padding=dp(14))
            inner.add_widget(Label(
                text='Foreslått basert på bildet:',
                size_hint_y=None, height=dp(28),
                font_size=fsp(14), bold=True,
                color=(0.04, 0.10, 0.36, 1), halign='center'))
            if sug_name:
                inner.add_widget(Label(
                    text=f'Navn: [b]{sug_name}[/b]',
                    markup=True, size_hint_y=None, height=dp(26),
                    font_size=fsp(14),
                    color=(0.1, 0.1, 0.3, 1), halign='center'))
            if sug_cat:
                cat = get_category(self.data, sug_cat)
                if cat:
                    inner.add_widget(Label(
                        text=f'Kategori (om aktiviteter): [b]{cat["name"]}[/b]',
                        markup=True, size_hint_y=None, height=dp(26),
                        font_size=fsp(14),
                        color=(0.1, 0.1, 0.3, 1), halign='center'))
            sub_ref = [None]
            def apply_sug(*_):
                if sug_name:
                    name_inp.text = sug_name
                if sug_cat:
                    # I item-popup setter vi ikke kategori (bilder har ikke
                    # kategori), men vi viser den slik at brukeren kan
                    # huske kategorien hvis de senere bruker bildet i en
                    # aktivitet. Lagrer ikke noe nå.
                    pass
                sub_ref[0].dismiss()
                self._toast('Forslag brukt.')
            br = BoxLayout(orientation='horizontal',
                           size_hint_y=None, height=dp(54), spacing=dp(10))
            br.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'),
                h=dp(54), fs=14,
                cb=lambda *_: sub_ref[0].dismiss()))
            br.add_widget(mk_btn('Bruk forslag', hex_k('#6BCB77'),
                h=dp(54), fs=14, cb=apply_sug))
            inner.add_widget(br)
            sub_pop = Popup(title='Forslag', content=inner,
                            size_hint=POPUP_SMALL, title_size=fsp(16))
            sub_ref[0] = sub_pop
            sub_pop.open()

        layout.add_widget(mk_btn(
            '✨  Foreslå navn fra bildet',
            hex_k('#9C7DCE'), h=dp(46), fs=13,
            cb=suggest_now))

        # ── Lagre / Avbryt ────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))

        def on_ok(*_):
            nm = name_inp.text.strip()
            if not nm:
                return
            if new:
                fo['items'].append({
                    'id':    str(uuid.uuid4()),
                    'name':  nm,
                    'image': chosen_img[0],
                })
            else:
                it.update({'name': nm, 'image': chosen_img[0]})
            save_struct(self.data)
            pop_ref[0].dismiss()
            self._show_folder(fid=fo['id'])

        btn_row.add_widget(mk_btn('Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_ok))
        btn_row.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss(),
        ))
        layout.add_widget(btn_row)

        sv.add_widget(layout)

        pop = Popup(
            title='Nytt ASK-bilde' if new else 'Rediger ASK-bilde',
            content=sv, size_hint=POPUP_LARGE,
        )
        pop_ref[0] = pop
        pop.open()

    def _del_item(self, fo, it):
        self._confirm(
            title='Slette bilde?',
            message=f'"{it.get("name", "")}" blir slettet fra enheten '
                    f'og kan ikke gjenopprettes.',
            on_confirm=lambda: self._do_del_item(fo, it),
        )

    def _do_del_item(self, fo, it):
        img = it.get('image', '')
        fo['items'] = [i for i in fo['items'] if i['id'] != it['id']]
        # Slett bildefilen og invalider thumbnail-cache
        if img and os.path.exists(img):
            try:
                os.remove(img)
                # lru_cache støtter ikke selektiv fjerning – tøm hele cachen
                get_thumbnail.cache_clear()
            except Exception:
                pass
        save_struct(self.data)
        self._show_folder(fid=fo['id'])

    # ══════════════════════════════════════════════════
    #  UNDERMAPPER
    # ══════════════════════════════════════════════════

    def _make_subfolder_tile(self, parent_fo, sub):
        """
        Lager en undermappe-flis med identisk stil som mappene på startsiden:
        én stor farget RBtn med sentrert navn, samme høyde og grid-kolonne-antall.
        """
        edit   = self.edit_mode
        TILE_H = dp(176) if edit else dp(142)
        btn_h  = dp(138) if edit else dp(142)

        if edit:
            tap = lambda s=sub, p=parent_fo: self._subfolder_popup(p, s)
        else:
            tap = lambda s=sub: self._open_subfolder(s)

        cell = BoxLayout(orientation='vertical',
                         size_hint_y=None, height=TILE_H, spacing=dp(3))

        btn = RBtn(
            text=sub['name'],
            size_hint=(1, None), height=btn_h,
            btn_color=list(hex_k(sub.get('color', '#4ECDC4'))),
            color=text_on(sub.get('color', '#4ECDC4')),
            bold=True, font_size=fsp(16), radius=dp(16),
        )
        btn.bind(on_release=lambda b, t=tap: t())
        cell.add_widget(btn)

        if edit:
            cell.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=dp(34), fs=12,
                cb=lambda *_, s=sub, p=parent_fo: self._del_subfolder(p, s)))
        return cell

    def _open_subfolder(self, sub):
        self._push('folder', fid=self.cur_folder)
        prev_fid = self.cur_folder
        self.cur_folder = sub['id']
        self._show_subfolder(sub, prev_fid)

    def _show_subfolder(self, sub, parent_fid, **_):
        """Viser innholdet i en undermappe."""
        self._cur_scr = 'folder'
        self._set_title(sub['name'])

        outer = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        if self.edit_mode:
            btn_bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            btn_bar.add_widget(mk_btn(
                '+  Nytt bilde', hex_k('#6BCB77'), h=dp(46), fs=13,
                cb=lambda *_: self._item_popup(sub, None)))
            btn_bar.add_widget(mk_btn(
                'Last opp', hex_k('#4D96FF'), h=dp(46), fs=13,
                cb=lambda *_: self._upload_to_folder(sub)))
            outer.add_widget(btn_bar)

        # 4 kolonner i portrett, 6 i liggende (fase 1 – landskapsstøtte)
        grid = GridLayout(cols=(6 if is_landscape() else 4),
                          spacing=dp(6), padding=(dp(4),dp(4)),
                          size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for it in sub.get('items', []):
            grid.add_widget(self._make_item_tile(sub, it))
        sv = ScrollView(); sv.add_widget(grid); outer.add_widget(sv)
        self._set_content(outer)

    def _subfolder_popup(self, parent_fo, sub):
        """Oppretter eller redigerer en undermappe."""
        new    = sub is None
        pop_ref = [None]
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        layout.add_widget(Label(text='Navn:', size_hint_y=None, height=dp(28),
            font_size=sp(15), color=(0,0,0,1), halign='left'))
        name_inp = smart_input(
            text='' if new else sub['name'],
            hint='Undermappenavn',
            on_save=on_ok,
        )
        layout.add_widget(name_inp)

        layout.add_widget(Label(text='Farge:', size_hint_y=None, height=dp(26),
            font_size=sp(14), color=(0,0,0,1), halign='left'))
        chosen = [sub.get('color','#4ECDC4') if sub else '#4ECDC4']
        col_grid = GridLayout(cols=4, spacing=dp(6), size_hint_y=None, height=dp(120))
        col_btns = []
        for c in FOLDER_COLORS:
            cb = RBtn(btn_color=list(hex_k(c)), size_hint=(1,None), height=dp(52),
                      opacity=1.0 if chosen[0]==c else 0.5, radius=dp(14))
            def pick(b, col=c, btns=col_btns, sel=chosen):
                sel[0]=col
                for x in btns: x.opacity=0.5
                b.opacity=1.0
            cb.bind(on_release=pick); col_grid.add_widget(cb); col_btns.append(cb)
        layout.add_widget(col_grid)

        btn_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        def on_ok(*_):
            nm = name_inp.text.strip()
            if not nm: return
            if new:
                parent_fo.setdefault('subfolders', []).append({
                    'id': str(uuid.uuid4()), 'name': nm,
                    'color': chosen[0], 'items': []})
            else:
                sub.update({'name': nm, 'color': chosen[0]})
            save_struct(self.data)
            pop_ref[0].dismiss()
            self._show_folder(fid=parent_fo['id'])
        btn_row.add_widget(mk_btn('Lagre',  hex_k('#6BCB77'), h=dp(50), cb=on_ok))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss()))
        layout.add_widget(btn_row)

        pop = Popup(
            title='Ny undermappe' if new else 'Rediger undermappe',
            content=layout, size_hint=POPUP_MEDIUM)
        pop_ref[0] = pop; pop.open()

    def _del_subfolder(self, parent_fo, sub):
        item_count = len(sub.get('items', []))
        detail = (f' med {item_count} bilde' + ('r' if item_count != 1 else '')
                  if item_count else '')
        self._confirm(
            title='Slette undermappe?',
            message=f'Undermappen "{sub.get("name", "")}"{detail} '
                    f'vil forsvinne fra appen.',
            on_confirm=lambda: self._do_del_subfolder(parent_fo, sub),
        )

    def _do_del_subfolder(self, parent_fo, sub):
        parent_fo['subfolders'] = [
            s for s in parent_fo.get('subfolders', []) if s['id'] != sub['id']]
        save_struct(self.data)
        self._show_folder(fid=parent_fo['id'])

    def _move_item_popup(self, src_folder, item):
        """
        Viser en liste med alle andre mapper å flytte item til.
        Bildet flyttes ved å fjerne det fra src_folder og legge det
        til i den valgte mappen – ingen filkopiering nødvendig.
        """
        other_folders = [
            f for f in self.data.get('folders', [])
            if f['id'] != src_folder['id']
        ]
        if not other_folders:
            self._toast('Ingen andre mapper å flytte til.')
            return

        pop_ref = [None]
        layout  = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))
        layout.add_widget(Label(
            text=f'Flytt "{item["name"]}" til:',
            size_hint_y=None, height=dp(36),
            font_size=fsp(17), bold=True,
            color=(0.08, 0.10, 0.35, 1), halign='center',
        ))

        sv   = ScrollView()
        vbox = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None)
        vbox.bind(minimum_height=vbox.setter('height'))

        for dest in other_folders:
            def make_move(dst=dest):
                def do_move(*_):
                    # Fjern fra kilde
                    src_folder['items'] = [
                        i for i in src_folder['items'] if i['id'] != item['id']
                    ]
                    # Legg til i mål
                    dst['items'].append(item)
                    save_struct(self.data)
                    pop_ref[0].dismiss()
                    self._toast(f'Flyttet til: {dst["name"]}')
                    self._show_folder(fid=src_folder['id'])
                return do_move

            vbox.add_widget(mk_btn(
                dest['name'],
                hex_k(dest['color']),
                fg=text_on(dest['color']),  # bruk fg=, ikke color= (krasjer i mk_btn)
                h=dp(62), fs=17,
                cb=make_move(),
            ))

        sv.add_widget(vbox)
        layout.add_widget(sv)
        layout.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss(),
        ))

        pop = Popup(
            title='Flytt bilde',
            content=layout, size_hint=POPUP_MEDIUM,
        )
        pop_ref[0] = pop
        pop.open()

    # ══════════════════════════════════════════════════
    #  BILDE – LAST OPP / LAST NED
    # ══════════════════════════════════════════════════

    def _pick_from_folders(self, chosen_img_ref, label_widget, preview_widget=None):
        """
        Lar brukeren velge et allerede opplastet bilde fra mappene.
        Viser alle mapper og bildene i dem – ingen filvelger nødvendig.

        preview_widget: valgfritt Image-widget som oppdateres med det
        valgte bildet (brukes av _dr_entry_popup for visuell bekreftelse
        på hvilket bilde aktiviteten vil bruke).
        """
        pop_ref = [None]
        layout  = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        layout.add_widget(Label(
            text='Velg bilde fra en mappe:',
            size_hint_y=None, height=dp(32),
            font_size=fsp(15), bold=True, color=(0.1,0.1,0.3,1)))

        sv = ScrollView()
        gl = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        gl.bind(minimum_height=gl.setter('height'))

        folders = self.data.get('folders', [])
        if not folders:
            gl.add_widget(Label(
                text='Ingen mapper ennå.\nOpprett mapper og last opp bilder først.',
                size_hint_y=None, height=dp(80),
                font_size=fsp(14), color=(0.5,0.5,0.5,1),
                halign='center'))
        else:
            for fo in folders:
                items = fo.get('items', [])
                if not items:
                    continue
                # Mappetittel
                gl.add_widget(Label(
                    text=fo['name'],
                    size_hint_y=None, height=dp(28),
                    font_size=fsp(13), bold=True,
                    color=hex_k(fo.get('color','#4D96FF'))[:3] + (1,),
                    halign='left'))
                # Bilder i grid – 4 kolonner i portrett, 6 i liggende
                # (fase 1 – landskapsstøtte)
                img_grid = GridLayout(
                    cols=(6 if is_landscape() else 4),
                    spacing=dp(4), size_hint_y=None)
                img_grid.bind(minimum_height=img_grid.setter('height'))
                for it in items:
                    ip = it.get('image','')
                    if not ip or not os.path.exists(ip):
                        continue
                    from kivy.uix.image import Image as KImg
                    cell = BoxLayout(orientation='vertical',
                                     size_hint_y=None, height=dp(90))
                    img_w = KImg(source=ip, allow_stretch=True,
                                 keep_ratio=True,
                                 size_hint_y=None, height=dp(72))
                    lbl = Label(text=it['name'], font_size=sp(10),
                                size_hint_y=None, height=dp(16),
                                color=(0.2,0.2,0.3,1),
                                shorten=True, shorten_from='right')
                    lbl.bind(size=lbl.setter('text_size'))
                    cell.add_widget(img_w)
                    cell.add_widget(lbl)
                    def _tap(w, t, _ip=ip, _name=it['name']):
                        if w.collide_point(*t.pos):
                            chosen_img_ref[0] = _ip
                            label_widget.text = 'Bilde: ' + _name
                            if preview_widget is not None:
                                preview_widget.source  = _ip
                                preview_widget.height  = dp(110)
                                preview_widget.opacity = 1
                                preview_widget.reload()
                            pop_ref[0].dismiss()
                            return True
                    cell.bind(on_touch_down=_tap)
                    img_grid.add_widget(cell)
                gl.add_widget(img_grid)

        sv.add_widget(gl)
        layout.add_widget(sv)
        layout.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(46),
            cb=lambda *_: pop_ref[0].dismiss()))

        pop = Popup(title='Velg bilde', content=layout,
                    size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        pop.open()

    def _pick_image(self, chosen_img_ref, label_widget, parent_popup=None):
        """
        Åpner Androids innebygde bildevelger (ACTION_OPEN_DOCUMENT).
        Ingen tillatelser nødvendig – Android håndterer alt.
        På ikke-Android brukes FileChooserListView som fallback.
        """
        if platform == 'android':
            def on_picked(result):
                if not result:
                    self._toast('Ingen bilde valgt.')
                    return
                # Normaliser: ta første bilde ved flervalg
                dst = result[0] if isinstance(result, list) else result
                if dst:
                    chosen_img_ref[0] = dst
                    label_widget.text = 'Bilde: ' + os.path.basename(dst)
                    logging.info('Bilde valgt: %s', dst)
                else:
                    self._toast('Ingen bilde valgt.')
            _open_android_picker(on_picked)
        else:
            # Fallback for desktop-testing
            fc_layout = BoxLayout(orientation='vertical', spacing=dp(8))
            fc = FileChooserListView(path=os.path.expanduser('~'), filters=[img_filter])
            fc_layout.add_widget(fc)
            btn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
            fc_pop_ref = [None]
            def on_select(*_):
                if fc.selection:
                    src = fc.selection[0]
                    dst = os.path.join(IMG_DIR, os.path.basename(src))
                    try:
                        shutil.copy2(src, dst)
                        chosen_img_ref[0] = dst
                        label_widget.text = 'Bilde: ' + os.path.basename(dst)
                    except Exception:
                        logging.exception('_pick_image fallback: feil')
                fc_pop_ref[0].dismiss()
            btn_row.add_widget(mk_btn('Velg', hex_k('#6BCB77'), h=dp(52), cb=on_select))
            btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(52),
                cb=lambda *_: fc_pop_ref[0].dismiss()))
            fc_layout.add_widget(btn_row)
            pop = Popup(title='Velg bilde', content=fc_layout, size_hint=POPUP_FULL)
            fc_pop_ref[0] = pop
            pop.open()

    def _global_search_popup(self):
        """
        Global søkepopup fra navbar: søk i symbolnavn på tvers av mapper
        OG i ARASAAC. To faner: Lokalt og ARASAAC.
        """
        import threading, urllib.request as _ur, json as _js

        pop_ref = [None]
        layout  = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        # Søkefelt
        inp = TextInput(
            hint_text='Søk i symboler og ARASAAC…',
            multiline=False, size_hint_y=None, height=dp(48),
            font_name='NotoSans', font_size=sp(15))
        layout.add_widget(inp)

        # Faner
        tab_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        btn_lok = mk_btn('Lokalt', hex_k('#4D96FF'), h=dp(38), fs=13)
        btn_ara = mk_btn('ARASAAC', hex_k('#9B59B6'), h=dp(38), fs=13)
        tab_row.add_widget(btn_lok)
        tab_row.add_widget(btn_ara)
        layout.add_widget(tab_row)

        status = Label(text='Skriv og velg søketype.',
                       size_hint_y=None, height=dp(26),
                       font_size=fsp(12), color=(0.4,0.4,0.5,1))
        layout.add_widget(status)

        grid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        sv = ScrollView(); sv.add_widget(grid); layout.add_widget(sv)

        def search_local(*_):
            """
            Søker på tvers av alle datalag: mapper, bilder i mapper,
            aktiviteter (per ukedag), sekvenser og notater. Resultater
            grupperes visuelt med en type-emoji som viser hva treffer er.
            """
            term = inp.text.strip().lower()
            grid.clear_widgets()
            if not term:
                return

            # Bygg en flat resultatliste med (type, tittel, undertittel,
            # callback). Vi viser maks 30 treff totalt.
            hits = []

            # 1. Bildemapper – navn
            for fo in self.data.get('folders', []):
                if term in fo.get('name', '').lower():
                    fo_ref = fo
                    hits.append(('📁', fo['name'], 'Mappe',
                                 lambda _fo=fo_ref: self._open_folder(_fo)))

            # 2. Bilder i mapper – item-navn
            for fo in self.data.get('folders', []):
                for it in fo.get('items', []):
                    if term in it.get('name', '').lower():
                        fo_ref = fo
                        hits.append(('[Bilde]', it['name'],
                                     f'I mappe: {fo["name"]}',
                                     lambda _fo=fo_ref: self._open_folder(_fo)))

            # 3. Aktiviteter – på tvers av ukedager
            for code in DAY_CODES:
                for act in get_day_plan(self.data, code):
                    if term in act.get('name', '').lower():
                        hits.append((
                            '[Plan]', act['name'],
                            f'{DAY_FULL_NO[code]} {act.get("start","")}–{act.get("end","")}',
                            lambda c=code: (
                                setattr(self, '_dr_selected_day', c),
                                self._nav_dagsrytme()
                            )))

            # 4. Sekvenser (rekker) – navn
            for seq in self.data.get('sequences', []):
                if term in seq.get('name', '').lower():
                    hits.append(('🔗', seq['name'], 'Rekke',
                                 lambda: self._show_sequences()))

            # 5. Notater – søk i tekstinnholdet
            for code, txt in (self.data.get('notater') or {}).items():
                if txt and term in txt.lower():
                    # Vis et utdrag rundt treffet
                    idx = txt.lower().find(term)
                    a = max(0, idx - 20)
                    b = min(len(txt), idx + len(term) + 30)
                    snippet = ('…' if a > 0 else '') + txt[a:b] + ('…' if b < len(txt) else '')
                    hits.append((
                        '📝', f'Notat: {DAY_FULL_NO[code]}', snippet,
                        lambda c=code: (
                            setattr(self, '_dr_selected_day', c),
                            self._nav_dagsrytme()
                        )))

            status.text = f'{len(hits)} treff' if hits else 'Ingen treff.'

            # Bygg resultatene som vertikal liste (ikke grid) for å gi
            # plass til undertittel og type-ikon.
            # Vi bytter ut grid-en med en vertikal box for denne typen
            # resultater.
            grid.cols = 1
            for emoji, title, subtitle, on_tap in hits[:30]:
                row = RBox(orientation='horizontal',
                           size_hint_y=None, height=dp(58),
                           padding=(dp(8), dp(4)), spacing=dp(8),
                           box_color=(0.97, 0.97, 1.0, 1.0), radius=dp(12))
                # Emoji-kolonne
                row.add_widget(Label(text=emoji, size_hint_x=None, width=dp(36),
                    font_size=sp(20), color=(0.1, 0.1, 0.3, 1),
                    halign='center'))
                # Tekst-kolonne
                col = BoxLayout(orientation='vertical', spacing=dp(2))
                t = Label(text=title, font_size=fsp(14), bold=True,
                          color=(0.04, 0.10, 0.36, 1),
                          size_hint_y=None, height=dp(24),
                          halign='left',
                          shorten=True, shorten_from='right')
                t.bind(size=lambda l, sz: setattr(l, 'text_size', sz))
                s = Label(text=subtitle, font_size=fsp(11),
                          color=(0.45, 0.48, 0.55, 1),
                          size_hint_y=None, height=dp(22),
                          halign='left',
                          shorten=True, shorten_from='right')
                s.bind(size=lambda l, sz: setattr(l, 'text_size', sz))
                col.add_widget(t); col.add_widget(s)
                row.add_widget(col)

                def _bind_tap(w, callback):
                    def on_tap(widget, touch):
                        if widget.collide_point(*touch.pos):
                            pop_ref[0].dismiss()
                            callback()
                            return True
                    w.bind(on_touch_down=on_tap)
                _bind_tap(row, on_tap)
                grid.add_widget(row)

        def search_arasaac(*_):
            term = inp.text.strip()
            if not term: return
            status.text = 'Søker ARASAAC…'
            grid.clear_widgets()
            def fetch():
                try:
                    url = ('https://api.arasaac.org/api/pictograms/no/search/'
                           + _ur.quote(term))
                    data = _js.loads(_ur.urlopen(url, timeout=10).read())
                    Clock.schedule_once(lambda *_: show_arasaac(data[:18]), 0)
                except Exception as e:
                    _msg = str(e)
                    Clock.schedule_once(
                        lambda *_, m=_msg: setattr(status, 'text', f'Feil: {m}'), 0)
            threading.Thread(target=fetch, daemon=True).start()

        def show_arasaac(data):
            if not data:
                status.text = 'Ingen ARASAAC-treff.'
                return
            status.text = f'{len(data)} ARASAAC-treff – velg mappe etter nedlasting'
            for item in data:
                pid  = item.get('_id') or item.get('id')
                kw   = item.get('keywords', [{}])
                name = kw[0].get('keyword', str(pid)) if kw else str(pid)
                url  = (f'https://static.arasaac.org/pictograms/'
                        f'{pid}/{pid}_300.png')
                from kivy.uix.image import AsyncImage
                cell = BoxLayout(orientation='vertical',
                                 size_hint_y=None, height=dp(112))
                ai = AsyncImage(source=url, allow_stretch=True,
                                keep_ratio=True,
                                size_hint_y=None, height=dp(82))
                lbl = Label(text=name, font_size=sp(11),
                            size_hint_y=None, height=dp(22),
                            color=(0.1,0.1,0.2,1),
                            shorten=True, shorten_from='right')
                lbl.bind(size=lbl.setter('text_size'))
                cell.add_widget(ai); cell.add_widget(lbl)
                def _tap(w, t, _p=pid, _n=name, _u=url):
                    if w.collide_point(*t.pos):
                        self._arasaac_choose_folder(_p, _n, _u, pop_ref)
                        return True
                cell.bind(on_touch_down=_tap)
                grid.add_widget(cell)

        btn_lok.bind(on_release=search_local)
        btn_ara.bind(on_release=search_arasaac)
        inp.bind(on_text_validate=search_local)

        pop = Popup(title='Søk', content=layout, size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        pop.open()

    def _arasaac_choose_folder(self, pid, name, img_url, pop_ref):
        """Velg hvilken mappe ARASAAC-symbol skal legges i."""
        folders = self.data.get('folders', [])
        if not folders:
            self._toast('Opprett en mappe først.')
            return
        layout = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
        layout.add_widget(Label(text='Velg mappe:',
                                size_hint_y=None, height=dp(32),
                                font_size=fsp(15), bold=True,
                                color=(0.1,0.1,0.3,1)))
        sv = ScrollView()
        gl = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        gl.bind(minimum_height=gl.setter('height'))
        fp = [None]
        for fo in folders:
            fo_ = fo
            gl.add_widget(mk_btn(fo['name'], hex_k(fo['color']), h=dp(54),
                cb=lambda *_, f=fo_: (
                    fp.__setitem__(0, f),
                    self._arasaac_download(pid, name, img_url, f, pop_ref),
                    fp[0] and setattr(fp[0], '_chosen', True),
                )))
        sv.add_widget(gl)
        layout.add_widget(sv)
        layout.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(46),
            cb=lambda *_: fp_pop.dismiss()))
        fp_pop = Popup(title='Velg mappe', content=layout,
                       size_hint=POPUP_MEDIUM)
        fp_pop.open()

    def _arasaac_search_popup(self, fo):
        """
        Søk i ARASAAC (13 000+ symboler, norsk, gratis).
        Viser opptil 18 resultater som kan lastes ned direkte.
        """
        import threading, urllib.request as _ur, json as _js
        pop_ref = [None]

        layout = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        search_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        inp = TextInput(
            hint_text='Søk på norsk eller engelsk…',
            multiline=False, size_hint_x=0.76,
            font_name='NotoSans', font_size=sp(15))
        search_row.add_widget(inp)
        search_row.add_widget(mk_btn('Søk', hex_k('#9B59B6'), h=dp(46), fs=14,
            cb=lambda *_: do_search()))
        layout.add_widget(search_row)

        status = Label(text='Skriv et ord og trykk Søk.',
                       size_hint_y=None, height=dp(28),
                       font_size=fsp(13), color=(0.4, 0.4, 0.5, 1))
        layout.add_widget(status)

        grid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        sv = ScrollView()
        sv.add_widget(grid)
        layout.add_widget(sv)

        def do_search(*_):
            term = inp.text.strip()
            if not term:
                return
            status.text = 'Søker…'
            grid.clear_widgets()
            def fetch():
                try:
                    url = ('https://api.arasaac.org/api/pictograms/no/search/'
                           + _ur.quote(term))
                    data = _js.loads(_ur.urlopen(url, timeout=10).read())
                    Clock.schedule_once(lambda *_: show_results(data[:18]), 0)
                except Exception as e:
                    _msg = str(e)
                    Clock.schedule_once(
                        lambda *_, m=_msg: setattr(status, 'text', f'Feil: {m}'), 0)
            threading.Thread(target=fetch, daemon=True).start()

        def show_results(data):
            if not data:
                status.text = 'Ingen resultater.'
                return
            status.text = f'{len(data)} treff – trykk for å legge til'
            for item in data:
                pid  = item.get('_id') or item.get('id')
                kw   = item.get('keywords', [{}])
                name = kw[0].get('keyword', str(pid)) if kw else str(pid)
                url  = (f'https://static.arasaac.org/pictograms/'
                        f'{pid}/{pid}_300.png')
                from kivy.uix.image import AsyncImage
                cell = BoxLayout(orientation='vertical',
                                 size_hint_y=None, height=dp(112))
                ai = AsyncImage(source=url, allow_stretch=True,
                                keep_ratio=True,
                                size_hint_y=None, height=dp(82))
                lbl = Label(text=name, font_size=sp(11),
                            size_hint_y=None, height=dp(22),
                            color=(0.1,0.1,0.2,1),
                            shorten=True, shorten_from='right')
                lbl.bind(size=lbl.setter('text_size'))
                cell.add_widget(ai)
                cell.add_widget(lbl)
                _pid, _name, _url = pid, name, url
                def _touch(w, t, _p=_pid, _n=_name, _u=_url):
                    if w.collide_point(*t.pos):
                        self._arasaac_download(_p, _n, _u, fo, pop_ref)
                        return True
                cell.bind(on_touch_down=_touch)
                grid.add_widget(cell)

        inp.bind(on_text_validate=lambda *_: do_search())
        pop = Popup(title='ARASAAC symbolsøk',
                    content=layout, size_hint=POPUP_LARGE)
        pop_ref[0] = pop
        pop.open()

    def _arasaac_download(self, pid, name, img_url, fo, pop_ref):
        """Laster ned symbol i bakgrunn og legger til i mappen."""
        import threading, urllib.request as _ur
        self._toast('Laster ned…')
        def fetch():
            try:
                dst = os.path.join(IMG_DIR, f'arasaac_{pid}.png')
                _ur.urlretrieve(img_url, dst)
                fo['items'].append({
                    'id': str(uuid.uuid4()), 'name': name, 'image': dst})
                save_struct(self.data)
                def _done(*_):
                    self._toast(f'Lagt til: {name}')
                    if pop_ref[0]:
                        pop_ref[0].dismiss()
                    self._show_folder(fid=fo['id'])
                Clock.schedule_once(_done, 0)
            except Exception as e:
                Clock.schedule_once(
                    lambda *_: self._toast(f'Nedlasting feilet: {e}'), 0)
        threading.Thread(target=fetch, daemon=True).start()

    def _upload_to_folder(self, fo):
        """
        Åpner Android-bildevelger og legger valgt bilde til i mappen.
        Viser først en advarsel om å ikke laste opp bilder av barn.
        """
        # Vis advarsel først – brukeren må bekrefte
        warn_ref = [None]
        warn_layout = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(16))
        warn_layout.add_widget(Label(
            text='⚠  Advarsel om personvern',
            size_hint_y=None, height=dp(36),
            font_size=fsp(18), bold=True,
            color=(0.78, 0.20, 0.10, 1), halign='center',
        ))
        warn_layout.add_widget(Label(
            text=(
                'Last ikke opp bilder av identifiserbare barn.\n\n'
                'Pedagogiske ASK-symboler viser generelle konsepter '
                'og trenger ikke å vise et spesifikt barn. '
                'Bruk generiske symboler (tegninger, clip-art, PCS-symboler).'
            ),
            font_size=fsp(14), color=(0.15, 0.15, 0.25, 1),
            halign='center', valign='middle',
        ))
        btn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))

        def do_upload(*_):
            warn_ref[0].dismiss()
            _do_upload()

        btn_row.add_widget(mk_btn('Jeg forstår – fortsett', hex_k('#FF9F43'), h=dp(52), fs=14, cb=do_upload))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(52), fs=14,
            cb=lambda *_: warn_ref[0].dismiss()))
        warn_layout.add_widget(btn_row)
        warn_pop = Popup(title='Personvern', content=warn_layout, size_hint=POPUP_MEDIUM)
        warn_ref[0] = warn_pop
        warn_pop.open()

        def _do_upload():
            """Selve opplastingen – kjøres etter advarsel er godkjent."""
            def on_picked(result):
                if not result:
                    self._toast('Ingen bilde valgt.')
                    return
                # Støtter både enkeltbilde (str) og flervalg (list)
                paths = result if isinstance(result, list) else [result]
                added = 0
                for dst in paths:
                    if not dst or not os.path.exists(dst):
                        continue
                    fname = os.path.basename(dst)
                    name  = os.path.splitext(fname)[0].replace('_', ' ')
                    fo['items'].append({
                        'id':    str(uuid.uuid4()),
                        'name':  name,
                        'image': dst,
                    })
                    added += 1
                if added:
                    save_struct(self.data)
                    msg = (f'Lagt til: {added} bilder'
                           if added > 1 else f'Lagt til: {os.path.basename(paths[0])}')
                    self._toast(msg)
                    self._show_folder(fid=fo['id'])
                    logging.info('Lastet opp %d bilde(r) til mappe', added)
            _open_android_picker(on_picked)
    def _download_image(self, src_path):
        if not src_path or not os.path.exists(src_path):
            self._toast('Ingen bildefil å laste ned.')
            return
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            dst = os.path.join(DOWNLOAD_DIR, os.path.basename(src_path))
            shutil.copy2(src_path, dst)
            self._toast(f'Lagret til Nedlastinger:\n{os.path.basename(dst)}')
            logging.info('Bilde lastet ned: %s', dst)
        except Exception:
            logging.exception('_download_image: feil')
            self._toast('Nedlasting feilet.')

    # ══════════════════════════════════════════════════
    #  TOAST
    # ══════════════════════════════════════════════════

    def _maybe_show_onboarding(self, *_):
        """Vises automatisk én gang ved første start for nye brukere."""
        try:
            done = self.data.get('settings', {}).get('onboarding_done', False)
            if not done:
                self._show_onboarding()
        except Exception:
            logging.exception('_maybe_show_onboarding feilet')

    def _show_onboarding(self):
        """
        Guidet omvisning i 6 slides + interaktiv mappe-oppretting.
        Etter slide 6 bes brukeren trykke «Red.»-knappen (uthevet med
        pulserende glød) og opprette sin første mappe (forhåndsutfylt
        navn). Når mappen er lagret vises «Du er klar!»-slide.
        """
        slides = [
            ('1/6', 'Velkommen til Kommunikasjonstavle',
             'Et verktøy for barnehage og spesialpedagogikk – '
             'støtter visuell kommunikasjon, struktur i dagen og '
             'tilrettelegging for barn med ulike kommunikasjonsbehov.'),
            ('2/6', 'Bildemapper på hjemskjermen',
             'Mappene samler bilder etter tema (mat, klær, følelser '
             'osv.). Trykk en mappe for å åpne den, og et bilde for å '
             'vise det stort. Bildet kan brukes i kommunikasjon med '
             'barnet ved peking eller blikk-kontakt.'),
            ('3/6', 'Dagsplan med ukedager',
             'I «Dagsplan» lager du en aktivitetsplan per ukedag. '
             'Hver dag kan ha sin egen plan. Widget på hjemskjermen '
             'viser nåværende aktivitet og hva som kommer neste.'),
            ('4/6', 'Tidsur og rekker',
             'Tidsuret viser tid igjen av en aktivitet. '
             '«Rekker» er bildesekvenser for rutiner som '
             'påkledning, håndvask eller utflukt i bestemt rekkefølge.'),
            ('5/6', 'Redigeringsmodus',
             'Trykk «Red.» nederst for å redigere. Da kan du legge til '
             'mapper, bilder, aktiviteter og sekvenser. '
             'Trykk «Red.» igjen for å gå tilbake til visningsmodus.'),
            ('6/6', 'Prøv det nå!',
             'La oss opprette din første mappe. '
             'Trykk «Neste» for å komme i gang – '
             'vi guider deg gjennom det.'),
        ]
        idx      = [0]
        pop_ref  = [None]
        # Pulserings-event-referanse
        pulse_ev = [None]

        def _stop_pulse():
            if pulse_ev[0]:
                pulse_ev[0].cancel()
                pulse_ev[0] = None
                # Reset Red.-knapp til normal
                try:
                    self._btn_edit.btn_color = list(
                        hex_k('#7B2FBE' if self.edit_mode else '#C77DFF'))
                    from kivy.graphics import Color as KColor
                    with self._btn_edit.canvas.before:
                        pass  # canvas refresh
                except Exception:
                    pass

        def _start_pulse():
            """Pulserende glød rundt Red.-knappen via fargeanimasjon."""
            _stop_pulse()
            state = [0.0, 1]  # [fase, retning]
            def _tick(dt):
                state[0] += 0.07 * state[1]
                if state[0] >= 1.0: state[1] = -1
                if state[0] <= 0.0: state[1] =  1
                t = state[0]
                # Veksle mellom lilla og lys lilla
                r = 0.48 + 0.20 * t
                g = 0.18 + 0.20 * t
                b = 0.74 + 0.20 * t
                try:
                    self._btn_edit.btn_color = [r, g, b, 1.0]
                except Exception:
                    pass
            pulse_ev[0] = Clock.schedule_interval(_tick, 0.04)

        # ── UI-elementer ──────────────────────────────────────────
        step_lbl  = Label(text='', font_size=fsp(12),
                          size_hint_y=None, height=dp(22),
                          color=(0.55, 0.58, 0.68, 1), halign='center')
        title_lbl = Label(text='', font_size=fsp(19), bold=True,
                          size_hint_y=None, height=dp(44),
                          color=(0.04, 0.10, 0.36, 1), halign='center')
        body_lbl  = Label(text='', font_size=fsp(15),
                          size_hint_y=None, height=dp(150),
                          color=(0.20, 0.22, 0.32, 1),
                          halign='center', valign='top')
        body_lbl.bind(width=lambda l, w:
                      setattr(l, 'text_size', (w - dp(20), None)))

        # Dotnav – canvas-tegnet sirkler (ingen font-avhengighet)
        # Aktiv: litt større og lysere; inaktiv: liten og mørkere enn bg.
        class DotWidget(Widget):
            """Enkel widget som tegner én rund dot via canvas."""
            def __init__(self, **kw):
                super().__init__(**kw)
                self._active  = False
                self._r       = (0.72, 0.74, 0.82, 1.0)  # inaktiv farge
                self._size_px = dp(8)
                self.bind(pos=self._redraw, size=self._redraw)

            def set_active(self, active):
                self._active   = active
                self._r        = (0.38, 0.60, 1.0, 1.0) if active else (0.68, 0.70, 0.78, 1.0)
                self._size_px  = dp(11) if active else dp(8)
                self._redraw()

            def _redraw(self, *_):
                from kivy.graphics import Color as _C, Ellipse as _E
                self.canvas.clear()
                cx = self.center_x
                cy = self.center_y
                r  = self._size_px / 2
                with self.canvas:
                    _C(*self._r)
                    _E(pos=(cx - r, cy - r), size=(self._size_px, self._size_px))

        dots_row = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(24), spacing=dp(10))
        dots_row.add_widget(Widget())  # flex spacer
        dots = []
        for _ in slides:
            d = DotWidget(size_hint_x=None, width=dp(14),
                          size_hint_y=None, height=dp(24))
            dots.append(d)
            dots_row.add_widget(d)
        dots_row.add_widget(Widget())  # flex spacer

        btn_row  = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(54), spacing=dp(8))
        skip_btn = mk_btn('Hopp over', hex_k('#9CA3AF'), h=dp(54), fs=13)
        prev_btn = mk_btn('Forrige',   hex_k('#78909C'), h=dp(54), fs=14)
        next_btn = mk_btn('Neste',     hex_k('#4D96FF'), h=dp(54), fs=15)
        btn_row.add_widget(skip_btn)
        btn_row.add_widget(prev_btn)
        btn_row.add_widget(next_btn)

        # Mappe-opprettingspanel (vises etter slide 6)
        folder_panel = BoxLayout(orientation='vertical',
                                 spacing=dp(8), size_hint_y=None, height=0,
                                 opacity=0)
        folder_panel.add_widget(Label(
            text='Skriv inn et navn på mappen din:',
            font_size=fsp(14), color=(0.2, 0.22, 0.32, 1),
            size_hint_y=None, height=dp(28), halign='left'))
        from kivy.uix.textinput import TextInput as _TI
        folder_name_inp = _TI(
            text='Min første mappe',
            hint_text='Mappenavn',
            multiline=False,
            size_hint_y=None, height=dp(48),
            font_size=fsp(15),
        )
        folder_panel.add_widget(folder_name_inp)
        create_folder_btn = mk_btn(
            'Opprett mappen', hex_k('#6BCB77'),
            h=dp(50), fs=15)
        folder_panel.add_widget(create_folder_btn)

        outer = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(16))
        outer.add_widget(step_lbl)
        outer.add_widget(title_lbl)
        outer.add_widget(body_lbl)
        outer.add_widget(folder_panel)
        outer.add_widget(BoxLayout())  # spacer
        outer.add_widget(dots_row)
        outer.add_widget(btn_row)

        def finish(*_):
            _stop_pulse()
            self.data.setdefault('settings', {})['onboarding_done'] = True
            save_struct(self.data)
            if pop_ref[0]:
                pop_ref[0].dismiss()

        def _show_done_slide():
            """Erstatter innhold med «Du er klar!»-avslutning."""
            _stop_pulse()
            step_lbl.text  = ''
            title_lbl.text = 'Du er klar!'
            body_lbl.text  = (
                'Flott! Mappen din er opprettet. '
                'Utforsk gjerne resten av appen – '
                'du kan alltid gå tilbake til omvisningen '
                'via Innstillinger.')
            folder_panel.height  = 0
            folder_panel.opacity = 0
            for d in dots:
                d.set_active(True)
            skip_btn.opacity  = 0; skip_btn.disabled  = True
            prev_btn.opacity  = 0; prev_btn.disabled  = True
            next_btn.text     = 'Start appen'
            next_btn.btn_color = list(hex_k('#6BCB77'))

        def _on_create_folder(*_):
            nm = folder_name_inp.text.strip() or 'Min første mappe'
            import uuid as _uuid
            new_fo = {
                    'id':          str(_uuid.uuid4()),
                    'name':        nm,
                    'color':       FOLDER_COLORS[2] if len(FOLDER_COLORS) > 2 else '#6BCB77',
                    'image':       None,
                    'items':       [],
                    'subfolders':  [],
                    'opens':       0,
                    'user_created': True,
                }
            self.data.setdefault('folders', []).append(new_fo)
            save_struct(self.data)
            _show_done_slide()

        create_folder_btn.bind(on_release=_on_create_folder)

        def render(*_):
            i = idx[0]
            step, title, body = slides[i]
            step_lbl.text  = step
            title_lbl.text = title
            body_lbl.text  = body
            for k, d in enumerate(dots):
                d.set_active(k == i)
            prev_btn.opacity  = 0 if i == 0 else 1
            prev_btn.disabled = (i == 0)
            is_last = (i == len(slides) - 1)

            # Vis/skjul mappe-opprettingspanel på siste slide
            if is_last:
                folder_panel.height  = dp(148)
                folder_panel.opacity = 1.0
            else:
                folder_panel.height  = 0
                folder_panel.opacity = 0

            if is_last:
                next_btn.text       = 'Ferdig uten mappe'
                next_btn.btn_color  = list(hex_k('#9CA3AF'))
                skip_btn.opacity    = 0
                skip_btn.disabled   = True
                # Start pulsering på Red.-knappen
                _start_pulse()
            else:
                next_btn.text      = 'Neste'
                next_btn.btn_color = list(hex_k('#4D96FF'))
                skip_btn.opacity   = 1
                skip_btn.disabled  = False
                _stop_pulse()

        def go_next(*_):
            if next_btn.text == 'Start appen':
                finish()
                return
            if idx[0] >= len(slides) - 1:
                # «Ferdig uten mappe» på siste slide
                finish()
                return
            idx[0] += 1
            render()

        def go_prev(*_):
            if idx[0] > 0:
                idx[0] -= 1
                render()

        skip_btn.bind(on_release=finish)
        prev_btn.bind(on_release=go_prev)
        next_btn.bind(on_release=go_next)

        pop = Popup(title='', content=outer,
                    size_hint=POPUP_LARGE,
                    separator_height=0)
        pop_ref[0] = pop
        # Stopp puls ved manuell popup-lukking
        pop.bind(on_dismiss=lambda *_: _stop_pulse())
        render()
        pop.open()

    def _toast(self, msg, duration=3.0):
        lbl = Label(
            text=msg, font_size=sp(15), color=(0.08, 0.10, 0.30, 1),
            halign='center', valign='middle',
        )
        lbl.bind(size=lbl.setter('text_size'))
        pop = Popup(
            title='', content=lbl,
            size_hint=POPUP_TOAST,
        )
        pop.open()
        Clock.schedule_once(lambda *_: pop.dismiss(), duration)

    def _pick_time_dialog(self, initial_hhmm, on_picked):
        """
        Egen tids-velger med stor numpad og hurtigjusterings-knapper.

        Brukerflyt:
        - To bokser (HH og MM). Den aktive er fremhevet.
        - Trykk en boks for å gi den fokus.
        - Trykk siffer for å skrive – auto-bytt fra HH til MM etter 2 siffer
          (eller hvis et siffer gjør verdien ugyldig).
        - ⌫ sletter siste siffer.
        - ±5 / ±15 justerer hele tidspunktet (krysser time-grenser korrekt).
        - OK bekrefter, Avbryt forkaster.

        initial_hhmm – starttid som 'HH:MM'.
        on_picked    – callback med 'HH:MM' når brukeren bekrefter.
        """
        try:
            parts = initial_hhmm.split(':')
            h = max(0, min(23, int(parts[0])))
            m = max(0, min(59, int(parts[1])))
        except Exception:
            h, m = 8, 0

        ACTIVE_COLOR   = '#4D96FF'   # blå for aktiv boks
        INACTIVE_COLOR = '#9CA3AF'   # grå for inaktiv boks
        DIGIT_COLOR    = '#E8EAF2'   # lys for talltastatur
        BACK_COLOR     = '#FFB74D'   # oransje for slett-knapp
        ADJ_COLOR      = '#78909C'   # mørk grå for ±knapper

        state = {
            'h': h, 'm': m,
            'focus': 'h',          # 'h' eller 'm'
            'fresh': True,         # True = neste siffer erstatter, False = appender
        }
        pop_ref = [None]

        # ── Display: to tappbare bokser ───────────────────────────────
        disp_row = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(96),
                             spacing=dp(4))
        disp_row.add_widget(Widget())  # spacer venstre

        hh_btn = mk_btn('{:02d}'.format(state['h']),
                        hex_k(ACTIVE_COLOR), h=dp(96), fs=42,
                        size_hint_x=None, width=dp(110))
        sep = Label(text=':', font_size=sp(40),
                    color=(0.1, 0.1, 0.2, 1),
                    size_hint_x=None, width=dp(28),
                    halign='center', valign='middle')
        mm_btn = mk_btn('{:02d}'.format(state['m']),
                        hex_k(INACTIVE_COLOR), h=dp(96), fs=42,
                        size_hint_x=None, width=dp(110))

        disp_row.add_widget(hh_btn)
        disp_row.add_widget(sep)
        disp_row.add_widget(mm_btn)
        disp_row.add_widget(Widget())  # spacer høyre

        def refresh_display():
            hh_btn.text = '{:02d}'.format(state['h'])
            mm_btn.text = '{:02d}'.format(state['m'])
            if state['focus'] == 'h':
                hh_btn.btn_color = list(hex_k(ACTIVE_COLOR))
                mm_btn.btn_color = list(hex_k(INACTIVE_COLOR))
            else:
                hh_btn.btn_color = list(hex_k(INACTIVE_COLOR))
                mm_btn.btn_color = list(hex_k(ACTIVE_COLOR))

        def focus_field(field):
            state['focus'] = field
            state['fresh'] = True
            refresh_display()

        hh_btn.bind(on_release=lambda *_: focus_field('h'))
        mm_btn.bind(on_release=lambda *_: focus_field('m'))

        # ── Numpad ────────────────────────────────────────────────────
        def press_digit(d):
            d = int(d)
            f = state['focus']
            cur = state[f]
            limit = 23 if f == 'h' else 59
            if state['fresh']:
                # Første siffer i feltet – erstatt
                state[f] = d
                state['fresh'] = False
                # Hvis første siffer alene overskrider grensen, kan vi
                # gå rett videre. F.eks. HH: trykk 3 → HH=3, men neste
                # siffer kan ikke gjøre 3X gyldig (alle 30+ er ugyldige),
                # så det er greit å auto-bytte allerede her.
                # Men 0, 1, 2 kan fortsatt få 2. siffer (00-23).
                if f == 'h' and d >= 3:
                    # Auto-bytt til MM med tomt felt
                    state['focus'] = 'm'
                    state['fresh'] = True
                elif f == 'm' and d >= 6:
                    # MM kan ikke ha første siffer > 5
                    # Bare aksepter dette som hele verdien, ingen videre input nødvendig
                    state['fresh'] = True  # neste trykk starter på nytt
            else:
                # Andre siffer – multipliser med 10 og legg til
                new_val = cur * 10 + d
                if new_val > limit:
                    # Ugyldig – bruk dette som ny verdi (start over)
                    state[f] = d
                    state['fresh'] = False
                    if f == 'h' and d >= 3:
                        state['focus'] = 'm'
                        state['fresh'] = True
                else:
                    state[f] = new_val
                    # Feltet er fullt – auto-bytt fra HH til MM
                    if f == 'h':
                        state['focus'] = 'm'
                        state['fresh'] = True
                    else:
                        state['fresh'] = True  # MM full, neste trykk erstatter
            refresh_display()

        def press_back(*_):
            f = state['focus']
            cur = state[f]
            if cur >= 10:
                state[f] = cur // 10
                state['fresh'] = False
            elif cur > 0:
                state[f] = 0
                state['fresh'] = True
            else:
                # Allerede 0 – flytt fokus til forrige felt om vi er på MM
                if f == 'm':
                    state['focus'] = 'h'
                    state['fresh'] = False
            refresh_display()

        numpad = GridLayout(cols=3, spacing=dp(6),
                            size_hint_y=None, height=dp(248))
        for d in '123456789':
            btn = mk_btn(d, hex_k(DIGIT_COLOR), h=dp(58), fs=22,
                         cb=lambda *_, dd=d: press_digit(dd))
            numpad.add_widget(btn)
        # Bunnrad: ⌫, 0, spacer
        numpad.add_widget(mk_btn('⌫', hex_k(BACK_COLOR), h=dp(58), fs=20,
                                  cb=press_back))
        numpad.add_widget(mk_btn('0', hex_k(DIGIT_COLOR), h=dp(58), fs=22,
                                  cb=lambda *_: press_digit('0')))
        numpad.add_widget(Widget())  # tom celle for symmetri

        # ── Hurtigjustering ±5 / ±15 ─────────────────────────────────
        def adjust(delta_min):
            total = state['h'] * 60 + state['m'] + delta_min
            total = total % (24 * 60)  # wraps over døgnet
            state['h'] = total // 60
            state['m'] = total % 60
            state['fresh'] = True
            refresh_display()

        adj_row = BoxLayout(orientation='horizontal',
                            size_hint_y=None, height=dp(46),
                            spacing=dp(6))
        for label, dm in [('−15', -15), ('−5', -5), ('+5', +5), ('+15', +15)]:
            adj_row.add_widget(mk_btn(label, hex_k(ADJ_COLOR), h=dp(46), fs=14,
                                      cb=lambda *_, d=dm: adjust(d)))

        # ── Avbryt / OK ───────────────────────────────────────────────
        def confirm(*_):
            hhmm = '{:02d}:{:02d}'.format(state['h'], state['m'])
            on_picked(hhmm)
            pop_ref[0].dismiss()

        btn_row = BoxLayout(orientation='horizontal',
                            size_hint_y=None, height=dp(54),
                            spacing=dp(10))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(54), fs=15,
                                   cb=lambda *_: pop_ref[0].dismiss()))
        btn_row.add_widget(mk_btn('OK', hex_k('#6BCB77'), h=dp(54), fs=16,
                                   cb=confirm))

        outer = BoxLayout(orientation='vertical',
                          spacing=dp(10), padding=dp(14))
        outer.add_widget(disp_row)
        outer.add_widget(numpad)
        outer.add_widget(adj_row)
        outer.add_widget(btn_row)

        pop = Popup(title='Velg tidspunkt', content=outer,
                    size_hint=POPUP_LARGE, title_size=fsp(16))
        pop_ref[0] = pop
        refresh_display()
        pop.open()

    def _confirm(self, title, message, on_confirm,
                 confirm_label='Slett', cancel_label='Avbryt',
                 confirm_color='#FF6B6B'):
        """
        Modal bekreftelsesdialog for destruktive handlinger.
        on_confirm kalles bare hvis brukeren trykker bekreft-knappen.
        Default-fargene er valgt for sletting; for andre destruktive
        handlinger kan confirm_label/confirm_color overrides.
        """
        layout = BoxLayout(orientation='vertical',
                           spacing=dp(14), padding=dp(16))
        msg_lbl = Label(
            text=message, font_size=fsp(16),
            color=(0.08, 0.10, 0.30, 1),
            halign='center', valign='middle',
        )
        msg_lbl.bind(size=msg_lbl.setter('text_size'))
        layout.add_widget(msg_lbl)

        btn_row = BoxLayout(orientation='horizontal',
                            size_hint_y=None, height=dp(54),
                            spacing=dp(10))
        pop_ref = [None]

        # Avbryt-knappen først (til venstre) – mindre risiko for feiltrykk
        # når brukeren leser fra venstre og refleksivt trykker den nærmeste.
        btn_cancel = mk_btn(
            cancel_label, hex_k('#78909C'), h=dp(54), fs=15,
            cb=lambda *_: pop_ref[0].dismiss(),
        )
        btn_confirm = mk_btn(
            confirm_label, hex_k(confirm_color), h=dp(54), fs=15,
            cb=lambda *_: (pop_ref[0].dismiss(), on_confirm()),
        )
        btn_row.add_widget(btn_cancel)
        btn_row.add_widget(btn_confirm)
        layout.add_widget(btn_row)

        pop = Popup(
            title=title, content=layout,
            size_hint=POPUP_CONFIRM,
            title_size=fsp(17),
        )
        pop_ref[0] = pop
        pop.open()


# ══════════════════════════════════════════════════════════════════
#  INNGANG
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Tidlig crash-log til hardkodet sti – fanger krasj før build() kjøres
    import traceback as _tb2
    _early_log = '/sdcard/Download/kt_crash.log'
    try:
        os.makedirs(os.path.dirname(_early_log), exist_ok=True)
        with open(_early_log, 'a', encoding='utf-8') as _ef:
            _ef.write('\n=== APP START ===\n')
    except Exception:
        pass

    try:
        KommunikasjonstavleApp().run()
    except Exception:
        try:
            with open(_early_log, 'a', encoding='utf-8') as _ef:
                _ef.write('\n=== FATAL KRASJ ===\n')
                _tb2.print_exc(file=_ef)
            if LOG_FILE:
                os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write('\n=== FATAL KRASJ ===\n')
                    _tb2.print_exc(file=f)
        except Exception:
            pass
        raise
