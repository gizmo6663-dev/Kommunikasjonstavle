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
import sys
import json
import uuid
import shutil
import logging
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
    from PIL import Image as PILImage, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ══════════════════════════════════════════════════════════════════
#  KV-REGLER – RBtn, RBox, NavBar, BottomBar
#
#  Alle stilede widgets bruker utelukkende canvas.before (aldri
#  canvas / canvas.after) for å unngå RenderContext-stack-krasj.
#  4 lag per widget: skygge → fargefyll → mørk ytre kant → lys indre kant.
#  Ingen glød- eller pulseffekter – de er utelatt med vilje.
# ══════════════════════════════════════════════════════════════════

_KV = """
<RBtn>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    bold: True
    canvas.before:
        # Rotasjon rundt midten av knappen
        PushMatrix:
        Rotate:
            angle: self.rotation
            origin: self.center
        # 1. Skygge – skrå ned mot høyre (offset +3dp X, -3dp Y)
        Color:
            rgba: 0.04, 0.06, 0.18, 0.12
        RoundedRectangle:
            pos: self.x + dp(3), self.y - dp(3)
            size: self.width, self.height
            radius: [self.radius + dp(2)]
        # 2. PIL-gradient som tekstur (genereres av _update_grad_texture)
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
            texture: self._grad_tex if hasattr(self, '_grad_tex') and self._grad_tex else None
        # Fallback flat farge hvis tekstur ikke er klar
        Color:
            rgba: self.btn_color if not (hasattr(self, '_grad_tex') and self._grad_tex) else (0,0,0,0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
        # 3. Subtil ytre kantlinje
        Color:
            rgba: 0, 0, 0, 0.14
        Line:
            rounded_rectangle: (self.x + dp(0.8), self.y + dp(0.8), self.width - dp(1.6), self.height - dp(1.6), self.radius)
            width: 1.0
        # 4. Lys indre glans-linje
        Color:
            rgba: 1, 1, 1, 0.30
        Line:
            rounded_rectangle: (self.x + dp(2), self.y + dp(2), self.width - dp(4), self.height - dp(4), max(1, self.radius - dp(1)))
            width: 1.1
    canvas.after:
        # PopMatrix ETTER at tekst er tegnet – slik roteres alt inkl. label
        PopMatrix:

<RBox>:
    canvas.before:
        # 1. Skygge – skrå ned mot høyre
        Color:
            rgba: 0.04, 0.06, 0.18, 0.10
        RoundedRectangle:
            pos: self.x + dp(3), self.y - dp(3)
            size: self.width, self.height
            radius: [self.radius + dp(1.5)]
        # 2. Bakgrunnsfarge
        Color:
            rgba: self.box_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
        # 3. Subtil ytre kant
        Color:
            rgba: 0, 0, 0, 0.08
        Line:
            rounded_rectangle: (self.x + dp(0.8), self.y + dp(0.8), self.width - dp(1.6), self.height - dp(1.6), self.radius)
            width: 0.9

<NavBar>:
    canvas.before:
        # Svakt mørkere enn app-bakgrunnen (0.94,0.95,0.98)
        # – gir tydelig adskillelse uten å dominere visuelt
        Color:
            rgba: 0.86, 0.88, 0.93, 1.0
        Rectangle:
            pos: self.pos
            size: self.size
        # Tynn separator øverst
        Color:
            rgba: 0.70, 0.74, 0.84, 1.0
        Line:
            points: self.x, self.top, self.right, self.top
            width: 1.2

<BottomBar>:
    canvas.before:
        # Lys tittellinje øverst
        Color:
            rgba: 0.12, 0.16, 0.28, 1.0
        Rectangle:
            pos: self.pos
            size: self.size
        # Lys bunn-separator
        Color:
            rgba: 1.0, 1.0, 1.0, 0.10
        Line:
            points: self.x, self.y, self.right, self.y
            width: 1.0

<Popup>:
    # Lys, nesten hvit bakgrunn – standard Kivy er mørk grå
    background_color: 0.97, 0.97, 1.0, 1.0
    background: ''
    title_color: 0.08, 0.10, 0.35, 1
    title_size: sp(17)
    separator_color: 0.72, 0.78, 0.92, 1
    canvas.before:
        # Subtil skygge bak hele popupen
        Color:
            rgba: 0.04, 0.06, 0.18, 0.18
        RoundedRectangle:
            pos: self.x + dp(4), self.y - dp(6)
            size: self.width - dp(6), self.height * 0.96
            radius: [dp(16)]
        # Hvit bakgrunn
        Color:
            rgba: 0.97, 0.97, 1.0, 1.0
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
        # Tynn blå kant
        Color:
            rgba: 0.72, 0.78, 0.92, 1.0
        Line:
            rounded_rectangle: (self.x + dp(1), self.y + dp(1), self.width - dp(2), self.height - dp(2), dp(13))
            width: 1.2
"""

Builder.load_string(_KV)

# ── Fontregistrering ──────────────────────────────────────────────
# NotoSans støtter fullt ut æ, ø, å og alle norske tegn.
# Kivy's innebygde Roboto mangler disse på noen Android-versjoner.
# Fonten ligger i assets/ og er inkludert i APK via buildozer.spec.
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

class RBtn(Button):
    """
    Avrundet knapp med skygge, kantlinje og PIL-basert lineær gradient.
    rotation er NumericProperty slik at Animation kan animere den
    via PushMatrix/Rotate/PopMatrix i KV-regelen.
    """
    btn_color  = ListProperty([0.30, 0.50, 1.0, 1.0])
    radius     = NumericProperty(dp(14))
    rotation   = NumericProperty(0.0)
    _grad_cache = {}  # delt tekstur-cache for alle RBtn-instanser

    def on_btn_color(self, *_):
        self._update_grad_texture()

    def _update_grad_texture(self):
        """
        Genererer en 1×64-px gradient-tekstur fra btn_color.
        Cacher teksturer per hex-farge – unngår unødvendig PIL-arbeid
        ved skjermbytte når samme farge brukes flere ganger.
        """
        if not PIL_OK:
            return
        # Bruk cache hvis samme farge allerede er generert
        r, g, b, a = self.btn_color
        cache_key = f'{r:.3f}{g:.3f}{b:.3f}{a:.3f}'
        cached = RBtn._grad_cache.get(cache_key)
        if cached:
            self._grad_tex = cached
            return
        try:
            r, g, b, a = self.btn_color
            H = 64
            buf = bytearray(1 * H * 4)
            for y in range(H):
                # y=0 er bunn i PIL (flippes), y=H-1 er topp
                # Gradient: øverst +22% lysere, midten ren farge, bunn -12% mørkere
                t = y / (H - 1)           # 0=bunn, 1=topp etter flip
                if t > 0.55:
                    blend = (t - 0.55) / 0.45   # 0→1 fra midten til topp
                    fr = min(1.0, r + 0.22 * blend)
                    fg = min(1.0, g + 0.22 * blend)
                    fb = min(1.0, b + 0.22 * blend)
                elif t < 0.20:
                    blend = (0.20 - t) / 0.20   # 0→1 fra midten til bunn
                    fr = max(0.0, r - 0.14 * blend)
                    fg = max(0.0, g - 0.14 * blend)
                    fb = max(0.0, b - 0.14 * blend)
                else:
                    fr, fg, fb = r, g, b
                i = y * 4
                buf[i]   = int(fr * 255)
                buf[i+1] = int(fg * 255)
                buf[i+2] = int(fb * 255)
                buf[i+3] = int(a  * 255)
            tex = Texture.create(size=(1, H), colorfmt='rgba')
            tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
            tex.wrap = 'repeat'   # tiles horisontalt til knappens fulle bredde
            self._grad_tex = tex
            RBtn._grad_cache[cache_key] = tex  # cache for gjenbruk
        except Exception:
            pass


class RBox(BoxLayout):
    """
    Avrundet kort/panel-container med skygge og dobbel kantlinje.
    Brukes for mappe-fliser og ASK-bilde-kort.
    """
    box_color = ListProperty([1.0, 1.0, 1.0, 1.0])
    radius    = NumericProperty(dp(16))


class NavBar(BoxLayout):
    """Navigasjonsbar med hvit bakgrunn og separator-linje i bunn."""
    pass


class BottomBar(BoxLayout):
    """Bunnbar med hvit bakgrunn og separator-linje i topp."""
    pass


# ══════════════════════════════════════════════════════════════════
#  KONSTANTER
# ══════════════════════════════════════════════════════════════════

APP_TITLE    = 'Kommunikasjonstavle'
DOWNLOAD_DIR = '/sdcard/Download'

# Disse settes i build() via App.user_data_dir
DATA_DIR    = None
IMG_DIR     = None
DRAW_DIR    = None
STRUCT_FILE = None
LOG_FILE    = None

CANVAS_W = 960
CANVAS_H = 1280   # Portrettformat passer mobilskjerm

FOLDER_COLORS = [
    '#FFD93D', '#FF6B6B', '#6BCB77', '#4D96FF',
    '#C77DFF', '#FF9F43', '#4ECDC4', '#FF6BB5',
]

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

DEFAULT_STRUCT = {
    "folders": [
        {"id": "f1", "name": "Mat og drikke", "color": "#FFD93D", "image": None, "items": [], "subfolders": [], "opens": 0},
        {"id": "f2", "name": "Aktiviteter",   "color": "#6BCB77", "image": None, "items": [], "subfolders": [], "opens": 0},
        {"id": "f3", "name": "Følelser",     "color": "#4D96FF", "image": None, "items": [], "subfolders": [], "opens": 0},
        {"id": "f4", "name": "Kropp",         "color": "#FF6B6B", "image": None, "items": [], "subfolders": [], "opens": 0},
        {"id": "f5", "name": "Klær",         "color": "#C77DFF", "image": None, "items": [], "subfolders": [], "opens": 0},
        {"id": "f6", "name": "Transport",     "color": "#FF9F43", "image": None, "items": [], "subfolders": [], "opens": 0},
    ],
    "sequences": [],
    "dagsrytme": [],
    "settings": {
        "tts_enabled": False,
        "font_scale": 1.0,
        "high_contrast": False,
        "swipe_nav": False
    }
}

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

def hex_k(h):
    """Hex-farge (#RRGGBB) → Kivy RGBA-tuple (0–1)."""
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4)) + (1,)

def hex_p(h):
    """Hex-farge (#RRGGBB) → PIL RGB-tuple (0–255)."""
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def dominant_color(img_path, default=(0.94, 0.95, 0.98)):
    """
    Finner dominerende farge i et bilde med PIL ved å:
    1. Skalere ned til 48×48 for ytelse
    2. Konvertere til palette-modus (255 farger)
    3. Velge hyppigste farge som ikke er nesten hvit/svart
    Returnerer (r,g,b) Kivy float-tuple (0–1), blandet 15% mot hvit
    for å gi et subtilt, ikke-overveldende bakgrunnstopp.
    """
    if not PIL_OK or not img_path or not os.path.exists(img_path):
        return default
    try:
        img = PILImage.open(img_path).convert('RGB').resize((48, 48))
        paletted = img.quantize(colors=8, method=PILImage.Quantize.MEDIANCUT)
        palette  = paletted.getpalette()
        counts   = {}
        for px in paletted.getdata():
            counts[px] = counts.get(px, 0) + 1
        for idx in sorted(counts, key=counts.get, reverse=True):
            r = palette[idx*3];  g = palette[idx*3+1];  b = palette[idx*3+2]
            # Hopp over nesten-hvit og nesten-svart
            lum = 0.299*r + 0.587*g + 0.114*b
            if 35 < lum < 220:
                # Bland 15% mot hvit for subtilt uttrykk
                fr = (r/255 * 0.15 + 0.85)
                fg = (g/255 * 0.15 + 0.85)
                fb = (b/255 * 0.15 + 0.85)
                return (fr, fg, fb)
    except Exception:
        pass
    return default


def text_on(bg_hex):
    """
    Returnerer enten mørk eller lys Kivy RGBA-farge for tekst
    basert på bakgrunnens relative luminans (WCAG-formel).
    Brukes for å sikre lesbar tekst på alle mappefarger.
    """
    h = bg_hex.lstrip('#')
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    # sRGB linearisering
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b)
    # Mørk tekst på lys bakgrunn, lys tekst på mørk bakgrunn
    if lum > 0.35:
        return (0.06, 0.07, 0.18, 1.0)   # nesten svart
    return (1.0, 1.0, 1.0, 1.0)           # hvit

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


def _update_widget(data):
    """
    Skriver dagsrytme-status til SharedPreferences for widget.
    Kun tekst – ingen bildeoverføring for stabilitet.
    """
    if platform != 'android':
        return
    try:
        import datetime as _dt
        from jnius import autoclass
        from android import mActivity

        prefs  = mActivity.getSharedPreferences('kt_widget', 0)
        editor = prefs.edit()

        entries   = data.get('dagsrytme', [])
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
        for e in entries:
            s = to_min(e.get('start', ''))
            t = to_min(e.get('end',   ''))
            if s < 0 or t < 0:
                continue
            if s <= now_total < t:
                current = e
                break
            if s > now_total and upcoming is None:
                upcoming = e

        if current:
            editor.putString('line1', current['name'])
            editor.putString('line2',
                current.get('start','') + ' – ' + current.get('end',''))
        else:
            editor.putString('line1', 'Ingen aktivitet nå')
            editor.putString('line2', '')

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


_thumb_cache = {}   # { (path, w, h): Kivy Texture }
_THUMB_MAX   = 200  # maks antall entries


def get_thumbnail(path, w, h):
    """
    Returnerer en PIL-basert Kivy Texture skalert til (w×h).
    Bruker _thumb_cache for å unngå gjentatt PIL-arbeid og minnebruk.
    Eldre entries kastes automatisk når cachen vokser over _THUMB_MAX.
    """
    if not PIL_OK or not path or not os.path.exists(path):
        return None
    key = (path, int(w), int(h))
    if key in _thumb_cache:
        return _thumb_cache[key]
    try:
        img  = PILImage.open(path).convert('RGB')
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
        # Begrens cache-størrelse
        if len(_thumb_cache) >= _THUMB_MAX:
            # Fjern eldste entry
            oldest = next(iter(_thumb_cache))
            del _thumb_cache[oldest]
        _thumb_cache[key] = tex
        return tex
    except Exception:
        return None


def haptic_feedback():
    """
    Haptisk feedback ved knappetrykk.
    Metode 1: performHapticFeedback() via Android View – krever INGEN tillatelse.
    Metode 2: plyer.vibrator(40) som fallback.
    """
    if platform != 'android':
        return
    # ── Metode 1: View.performHapticFeedback (anbefalt av Google) ──
    try:
        from jnius import autoclass
        View            = autoclass('android.view.View')
        PythonActivity  = autoclass('org.kivy.android.PythonActivity')
        root_view       = (PythonActivity.mActivity
                           .getWindow().getDecorView().getRootView())
        if root_view:
            # HAPTIC_FEEDBACK_VIRTUAL_KEY = 1 – standard klikk-effekt
            root_view.performHapticFeedback(1)
            return
    except Exception as e:
        logging.debug('performHapticFeedback feilet: %s', e)
    # ── Metode 2: plyer (int, ikke float) ──────────────────────────
    try:
        from plyer import vibrator
        vibrator.vibrate(40)     # må være int (millisekunder)
    except Exception as e:
        logging.debug('plyer.vibrator feilet: %s', e)


def fsp(base_size):
    """
    Skalerbar sp()-wrapper. Leser font_scale fra appens innstillinger
    slik at tekststørrelse kan justeres globalt fra Innstillinger-skjermen.
    Returnerer sp(base_size) som fallback hvis appen ikke er startet ennå.
    """
    try:
        app = App.get_running_app()
        if app and hasattr(app, 'data'):
            scale = app.data.get('settings', {}).get('font_scale', 1.0)
            return sp(base_size * scale)
    except Exception:
        pass
    return sp(base_size)


def is_hc():
    """Returnerer True hvis høykontrast-modus er aktivert."""
    try:
        app = App.get_running_app()
        if app and hasattr(app, 'data'):
            return bool(app.data.get('settings', {}).get('high_contrast', False))
    except Exception:
        pass
    return False


def hc(normal_hex, hc_hex=None):
    """
    Returnerer hex_k(hc_hex) i høykontrast-modus, ellers hex_k(normal_hex).
    Dersom hc_hex ikke er oppgitt brukes '#000000' (svart) som standard HC-farge.
    Brukes der knapper og bakgrunner må skifte farge i HC-modus.
    """
    if is_hc():
        return hex_k(hc_hex or '#000000')
    return hex_k(normal_hex)


def apply_high_contrast(enabled):
    """
    Bytter appens overordnede utseende mellom normal og høykontrast.

    Kivy-KV støtter ikke dynamiske betingelser i canvas-blokker på
    en enkel måte (de evalueres ikke ved runtime). I stedet:
      - Window.clearcolor settes umiddelbart
      - mk_btn() og _make_folder_tile() leser is_hc() ved neste
        gjenbygging av skjermen (skjer automatisk ved skjermbytte)

    Høykontrast:
      - Bakgrunn: hvit
      - Knapper: svart (#000000) med hvit tekst
      - Tekst-labels: svart (#000000)
      - Kontrast-ratio: 21:1 (WCAG AAA maksimum)
    """
    from kivy.core.window import Window
    if enabled:
        Window.clearcolor = (1.0, 1.0, 1.0, 1.0)
    else:
        Window.clearcolor = (0.94, 0.95, 0.98, 1.0)

def mk_btn(text, bg, fg=(1, 1, 1, 1), fs=15, h=dp(54), cb=None, **kw):
    """
    Lager en RBtn med:
    - PIL-gradient (via _update_grad_texture i RBtn)
    - Kortvippings-animasjon ved trykk (rotation ±2°)
    - Haptic feedback via plyer.vibrator (kort 30ms puls)
    - WCAG AAA i høykontrast-modus
    """
    from kivy.animation import Animation
    kw.setdefault('size_hint_y', None)
    kw.setdefault('height', h)
    if is_hc():
        btn_color = [0.0, 0.0, 0.0, 1.0]
        txt_color = (1.0, 1.0, 1.0, 1.0)
    else:
        btn_color = list(bg)
        txt_color = fg
    b = RBtn(
        text=text,
        btn_color=btn_color,
        font_size=sp(fs),
        color=txt_color, bold=True, **kw,
    )
    # Generer gradient-tekstur med det samme
    b._update_grad_texture()

    # Lagre original farge for tilbakestilling
    orig_color = list(btn_color)

    def _on_press(btn, *_):
        # Mørklegg + vipp lett til venstre
        r, g, bv, a = btn.btn_color
        btn.btn_color = [max(0, r*0.75), max(0, g*0.75), max(0, bv*0.75), a]
        Animation(rotation=-2.5, duration=0.07, t='out_quad').start(btn)
        haptic_feedback()

    def _on_release_anim(btn, *_):
        btn.btn_color = list(orig_color)
        # Tilbake med liten oversving: -2.5 → +1.2 → 0
        (Animation(rotation=1.2, duration=0.07, t='out_quad') +
         Animation(rotation=0.0, duration=0.09, t='out_bounce')).start(btn)

    b.bind(on_press=_on_press, on_release=_on_release_anim)
    if cb:
        b.bind(on_release=cb)
    return b

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
            if 'settings' not in d:
                d['settings'] = {'tts_enabled': False, 'font_scale': 1.0, 'high_contrast': False, 'swipe_nav': False}
            return d
        except Exception as e:
            logging.error('Feil ved lasting av structure.json: %s', e)
    import copy
    return copy.deepcopy(DEFAULT_STRUCT)

_save_event = [None]

def save_struct(d, immediate=False):
    """
    Lagrer structure.json med 500ms debounce.
    immediate=True brukes ved app-pause og kritiske endringer.
    Reduserer I/O ved f.eks. opens-teller og sekvensielle endringer.
    """
    if not STRUCT_FILE:
        logging.error('save_struct: STRUCT_FILE ikke satt ennå')
        return

    def _do_save(*_):
        os.makedirs(os.path.dirname(STRUCT_FILE), exist_ok=True)
        try:
            with open(STRUCT_FILE, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            logging.debug('structure.json lagret (%s)', STRUCT_FILE)
        except Exception as e:
            logging.error('Feil ved lagring: %s', e)
        _save_event[0] = None

    if immediate:
        if _save_event[0]:
            _save_event[0].cancel()
            _save_event[0] = None
        _do_save()
        return

    if _save_event[0]:
        _save_event[0].cancel()
    _save_event[0] = Clock.schedule_once(_do_save, 0.5)

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
    PERMS = [
        'android.permission.READ_EXTERNAL_STORAGE',
        'android.permission.WRITE_EXTERNAL_STORAGE',
        'android.permission.READ_MEDIA_IMAGES',
    ]

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
    FileHelper.copyUriToFile() gjør all I/O i Java med ekte byte[]-array.
    """
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        from jnius import autoclass
        from android import mActivity
        _plog(f'_copy_content_uri: laster FileHelper...')
        FileHelper = autoclass('no.askapp.kommunikasjonstavle.FileHelper')
        _plog(f'_copy_content_uri: FileHelper lastet OK, kaller copyUriToFile')
        n = FileHelper.copyUriToFile(mActivity, uri, dst_path)
        _plog(f'_copy_content_uri: copyUriToFile returnerte {n}')
        if n < 0:
            _plog('_copy_content_uri: FileHelper returnerte -1 – sjekk logcat')
            return False
        _plog(f'_copy_content_uri OK: {n} bytes -> {dst_path}')
        _scale_image(dst_path)
        return True
    except Exception as e:
        _plog(f'_copy_content_uri UNNTAK: {type(e).__name__}: {e}')
        logging.exception('_copy_content_uri: feil')
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
            if result_code != -1 or data is None:
                _plog('Bildevelger: bruker avbrøt eller ingen data')
                if cb:
                    Clock.schedule_once(lambda *_: cb(None), 0)
                return

            paths = []
            # Flervalg: ClipData
            clip = data.getClipData()
            if clip and clip.getItemCount() > 0:
                for i in range(clip.getItemCount()):
                    uri = clip.getItemAt(i).getUri()
                    p   = _uri_to_path(uri)
                    if p:
                        paths.append(p)
                _plog(f'Flervalg: {len(paths)} bilder')
            else:
                # Enkeltvalg: getData()
                uri = data.getData()
                if uri:
                    p = _uri_to_path(uri)
                    if p:
                        paths.append(p)

            if cb:
                if len(paths) == 1:
                    Clock.schedule_once(lambda *_: cb(paths[0]), 0)
                elif len(paths) > 1:
                    # Send liste – callback som støtter flervalg
                    Clock.schedule_once(lambda *_: cb(paths), 0)
                else:
                    Clock.schedule_once(lambda *_: cb(None), 0)

        activity_bind(on_activity_result=on_activity_result)
        mActivity.startActivityForResult(intent, _PICK_IMAGE_REQUEST)
        _plog('ACTION_OPEN_DOCUMENT startet (flervalg aktivert)')
    except Exception as e:
        _plog(f'_open_android_picker feil: {e}')
        logging.exception('_open_android_picker: feil')
        callback(None)


# ══════════════════════════════════════════════════════════════════
#  WIDGET: TRYKKBART BILDE
# ══════════════════════════════════════════════════════════════════

class TappableImage(Image):
    """
    Image-widget med enkelt-trykk-callback og dobbelt-trykk-zoom.
    Enkelt trykk → action-callback.
    Dobbelt trykk (< 0.35s) → popup-zoom av bildet.
    """
    def __init__(self, action, **kw):
        super().__init__(**kw)
        self._action     = action
        self._last_touch = 0

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        now = Clock.get_time()
        dt  = now - self._last_touch
        self._last_touch = now
        # Visuell feedback: kort dimming
        from kivy.animation import Animation
        Animation(opacity=0.65, duration=0.06).start(self)
        if dt < 0.35 and dt > 0.01:
            self._show_zoom_popup()
        else:
            self._action()
        return True

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            from kivy.animation import Animation
            Animation(opacity=1.0, duration=0.12).start(self)
        return super().on_touch_up(touch)

    def _show_zoom_popup(self):
        from kivy.uix.floatlayout import FloatLayout
        from kivy.animation import Animation
        overlay = FloatLayout(size=Window.size)
        with overlay.canvas.before:
            from kivy.graphics import Color as KColor, Rectangle
            KColor(0, 0, 0, 0.85)
            Rectangle(pos=(0,0), size=Window.size)
        zoom_img = Image(
            source=self.source,
            size_hint=(0.96, 0.96),
            pos_hint={'center_x': .5, 'center_y': .5},
            allow_stretch=True, keep_ratio=True,
        )
        zoom_img.opacity = 0
        overlay.add_widget(zoom_img)
        Window.add_widget(overlay)
        Animation(opacity=1, duration=0.20, t='out_quad').start(zoom_img)
        def dismiss(*_):
            anim = Animation(opacity=0, duration=0.15)
            anim.bind(on_complete=lambda *_: Window.remove_widget(overlay))
            anim.start(overlay)
        overlay.bind(on_touch_down=lambda w, t: dismiss())


# ══════════════════════════════════════════════════════════════════
#  WIDGET: TEGNE-CANVAS
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
        Glidende gjennomsnitt over punktbuffer.
        Hvert utgangspunkt er snittet av de siste 'window' inngangspunktene.
        Gir sanntids-stabilisering mens fingeren beveger seg.
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
                    # Dette er det som glatter ut rystende linjer.
                    win      = max(1, self.stabilize * 2)
                    smoothed = self._moving_avg(self._raw_pts, win)
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

    def build(self):
        setup_logging()
        Window.clearcolor = (0.94, 0.95, 0.98, 1)
        Window.softinput_mode = 'below_target'  # Skyv innhold over tastatur

        # Sett ALLE datastier fra user_data_dir – alltid skrivbar
        # uten tillatelser på alle Android-versjoner.
        global DATA_DIR, IMG_DIR, DRAW_DIR, STRUCT_FILE, LOG_FILE
        DATA_DIR    = self.user_data_dir
        IMG_DIR     = os.path.join(DATA_DIR, 'images')
        DRAW_DIR    = os.path.join(DATA_DIR, 'drawings')
        STRUCT_FILE = os.path.join(DATA_DIR, 'structure.json')
        LOG_FILE    = os.path.join(DATA_DIR, 'crash.log')

        for d in [DATA_DIR, IMG_DIR, DRAW_DIR, DOWNLOAD_DIR]:
            os.makedirs(d, exist_ok=True)

        self.data        = load_struct()
        # Aktiver HC-modus hvis det var aktivert ved forrige kjøring
        if self.data.get('settings', {}).get('high_contrast', False):
            apply_high_contrast(True)
        self.nav_stack   = []
        self.cur_folder  = None
        self.edit_mode   = False
        self.draw_canvas = None
        self._cur_scr    = 'home'

        root = BoxLayout(orientation='vertical')
        # Tittellinje øverst (slim, ikke-interaktiv, mørk)
        self._bottombar = self._build_bottombar()
        root.add_widget(self._bottombar)
        # Hurtigrad rett under tittellinje
        self._quickbar = self._build_quickbar()
        root.add_widget(self._quickbar)
        # Innholdsflate i midten (tar all gjenværende plass)
        self._content = BoxLayout(orientation='vertical')
        root.add_widget(self._content)
        # Navigasjonsbar NEDERST for énhånds-bruk på store telefoner
        self._navbar = self._build_navbar()
        root.add_widget(self._navbar)

        self._show_home()
        # Widget-oppdatering – pakket inn i try/except
        def _safe_widget_start(*_):
            try:
                _update_widget(self.data)
            except Exception as e:
                logging.warning('widget start feilet: %s', e)
        def _safe_alarm(*_):
            try:
                _schedule_widget_alarm()
            except Exception as e:
                logging.warning('alarm feilet: %s', e)
        Clock.schedule_once(_safe_widget_start, 2.0)
        self._widget_tick = Clock.schedule_interval(
            lambda *_: Clock.schedule_once(_safe_widget_start, 0), 60)
        Clock.schedule_once(_safe_alarm, 3.0)
        # Bind tilbake-knapp (ESC / Android Back)
        Window.bind(on_keyboard=self.on_keyboard)
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
        return True

    def on_resume(self):
        def _safe(*_):
            try: _update_widget(self.data)
            except Exception as e: logging.warning('resume widget: %s', e)
        Clock.schedule_once(_safe, 0.5)

    def on_start(self):
        """
        Sjekker om appen ble åpnet via Share intent (delt bilde fra Galleri).
        Binder også on_new_intent for å fange deling mens appen kjører.
        """
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
            content=layout, size_hint=(0.92, 0.88),
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
            size_hint_y=None, height=dp(52),
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
            ('Tegn',     '#FF9F43', self.go_draw),
        ]
        for lbl, col, fn in _qcols:
            bar.add_widget(mk_btn(lbl, hex_k(col), h=dp(46), fs=12,
                cb=lambda *_, f=fn: f()))
        return bar

    def _build_navbar(self):
        """
        Navigasjonsbar plassert NEDERST for énhånds-bruk på store telefoner.
        Mørk bakgrunn (via KV) med halvt-transparente pill-knapper.
        Knappene er hvite/lyse for god kontrast mot mørk bunn.
        """
        bar = NavBar(
            orientation='horizontal',
            size_hint_y=None, height=dp(72),
            padding=(dp(8), dp(8)),
            spacing=dp(6),
        )

        # Halv-transparente pill-knapper mot mørk bakgrunn
        # Farger er lysere/mer saturerte enn normalt siden de
        # skal leses mot mørk (#1a2340) bakgrunn.
        btn_kw = dict(size_hint_y=None, height=dp(56), radius=dp(14))

        self._btn_back = mk_btn(
            'Tilbake', hex_k('#4D96FF'), fs=13,
            cb=self.go_back, **btn_kw,
        )
        self._btn_home = mk_btn(
            'Hjem', hex_k('#6BCB77'), fs=13,
            cb=self.go_home, **btn_kw,
        )
        self._btn_search = mk_btn(
            'Søk', hex_k('#9B59B6'), fs=13,
            cb=lambda *_: self._global_search_popup(), **btn_kw,
        )
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
        Slim mørk tittellinje øverst – viser kun skjermnavnet.
        Innstillinger er flyttet til navbar-knappen.
        Høyde: 46dp – kompakt men lesbar.
        """
        bar = BottomBar(
            size_hint_y=None, height=dp(46),
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
            getattr(self, f'_show_{scr}')(**kw)
        else:
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
        if self._cur_scr in ('draw', 'image'):
            return
        self.edit_mode = not self.edit_mode
        self._set_edit_highlight(self.edit_mode)
        if self._cur_scr == 'folder':
            self._show_folder(fid=self.cur_folder)
        elif self._cur_scr == 'sequences':
            self._show_sequences()
        else:
            self._show_home()

    def _push(self, scr, **kw):
        self.nav_stack.append((scr, kw))

    def _set_content(self, widget, animate=True):
        """
        Bytter innholdsflaten med fade + skalering fra 92%→100%.
        Sveipe-touch-håndtering aktiveres hvis swipe_nav er på.
        """
        if self._cur_scr != 'dagsrytme':
            ev = getattr(self, '_dr_event', None)
            if ev:
                ev.cancel()
                self._dr_event = None
        if self._cur_scr != 'tidsur' and getattr(self, '_timer_running', False):
            self._tidsur_stop()
        # Nullstill adaptiv bakgrunn når vi forlater bilde-skjermen
        if self._cur_scr == 'image':
            hc_bg = (1.0, 1.0, 1.0, 1.0) if is_hc() else (0.94, 0.95, 0.98, 1.0)
            Window.clearcolor = hc_bg

        self._content.clear_widgets()
        widget.opacity = 0
        self._content.add_widget(widget)

        if animate:
            from kivy.animation import Animation
            anim = Animation(opacity=1, duration=0.18, t='out_quad')
            anim.start(widget)
        else:
            widget.opacity = 1

        # Bind sveipe-navigasjon hvis aktivert i innstillinger
        if self.data.get('settings', {}).get('swipe_nav', False):
            self._bind_swipe(widget)

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

    def _show_home(self, **_):
        self._cur_scr   = 'home'
        self.cur_folder = None
        self._set_title(APP_TITLE)

        outer = BoxLayout(orientation='vertical', spacing=dp(6), padding=(dp(8), dp(6)))


        # ── «Ny mappe»-knapp kun i redigeringsmodus ───────────────
        if self.edit_mode:
            outer.add_widget(mk_btn(
                '+  Ny mappe', hex_k('#6BCB77'), h=dp(46), fs=14,
                cb=lambda *_: self._folder_popup(None),
            ))

        # ── 3-kolonne mappegrid ───────────────────────────────────
        grid = GridLayout(cols=3, spacing=dp(6), padding=(dp(6), dp(6)), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for fo in self.data['folders']:
            grid.add_widget(self._make_folder_tile(fo))

        sv = ScrollView()
        sv.add_widget(grid)
        outer.add_widget(sv)
        self._set_content(outer)

    def _make_folder_tile(self, fo):
        """Enkel farget flis med sentrert navn – ingen bilde."""
        edit   = self.edit_mode
        TILE_H = dp(176) if edit else dp(142)
        btn_h  = dp(138) if edit else dp(142)

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

        outer = BoxLayout(
            orientation='vertical',
            spacing=dp(8), padding=dp(10),
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
                '🔍 Søk', hex_k('#9B59B6'), h=dp(46), fs=13,
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
        grid = GridLayout(
            cols=3, spacing=dp(8), padding=(dp(6), dp(6)),
            size_hint_y=None,
            col_force_default=True, col_default_width=dp(108),
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

        Designprinsipper:
        - Kun ÉN ytre ramme (RBox på cell-nivå) – ingen nestet RBox for bildet
        - Bildet er alltid kvadratisk (keep_ratio=False, allow_stretch=True)
          fordi alle opplastede symbolbilder er kvadratiske
        - Hvit bakgrunn bak bildet tegnes direkte i BoxLayout via canvas.before
        - Ingen dobbel bakgrunn eller overflow
        """
        img_path = it.get('image') or ''
        has_img  = bool(img_path and os.path.exists(img_path))
        edit     = self.edit_mode

        # Bilde nesten like bredt som etikett:
        # cell har padding dp(4) på hver side → bilde-bredde = kolonne - dp(8)
        # Vi gjør bildet kvadratisk ved å sette IMG_H lik forventet bredde.
        # 4-kol grid, spacing dp(6), padding dp(4) → ca 82dp per kol på 360dp skjerm.
        # Setter IMG_H litt over dette for store skjermer, justeres med size_hint.
        IMG_H  = dp(110)  # 3-kol: fast høyde = kolonne-bredde ≈ 110dp
        LBL_H  = dp(36)
        ACT_H  = dp(36)
        TILE_H = (IMG_H + LBL_H + ACT_H + dp(6)) if edit else (IMG_H + LBL_H + dp(4))

        if edit:
            tap = lambda f=fo, i=it: self._item_popup(f, i)
        else:
            tap = lambda p=img_path, n=it['name']: self._show_image_full(p, n)

        # Én enkelt ytre ramme – tonet mappefarge
        # padding=0 på sidene så bildet fyller full bredde
        r, g, b, _ = hex_k(fo.get('color', '#4D96FF'))
        card_col   = (r*0.12 + 0.88, g*0.12 + 0.88, b*0.12 + 0.88, 1.0)
        cell = RBox(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=0,
            padding=(0, 0, 0, dp(3)),  # ingen sidepadding – bilde fyller full bredde
            box_color=list(card_col),
            radius=dp(14),
        )

        if has_img:
            img_wrap = BoxLayout(
                size_hint=(1, None), height=IMG_H,
            )
            # Hvit bakgrunn bak bildet direkte i canvas
            with img_wrap.canvas.before:
                from kivy.graphics import Color as KC, RoundedRectangle as KRR
                KC(1.0, 1.0, 1.0, 1.0)
                self._last_img_rr = KRR(
                    pos=img_wrap.pos,
                    size=img_wrap.size,
                    radius=[dp(10), dp(10), dp(2), dp(2)],
                )
            def _upd_rr(w, *_, rr=self._last_img_rr):
                rr.pos  = w.pos
                rr.size = w.size
            img_wrap.bind(pos=_upd_rr, size=_upd_rr)

            # Bruk thumbnail-cache for rask visning og lavt minnebruk
            tile_sz = int(dp(110))
            thumb_tex = get_thumbnail(img_path, tile_sz, tile_sz)
            ti = TappableImage(
                tap, source=img_path if thumb_tex is None else '',
                allow_stretch=True, keep_ratio=False,
            )
            if thumb_tex:
                ti.texture = thumb_tex
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
        btn.bind(on_release=lambda b: tap())
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
            from kivy.animation import Animation
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

        pop = Popup(title='Farge', content=outer, size_hint=(0.95, 0.92))
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
        Bildene nummereres (01_, 02_, …) og en tekstfil beskriver rekkefølgen.
        """
        items = seq.get('items', [])
        if not items:
            self._toast('Ingen bilder å eksportere.')
            return
        safe = seq['name'].replace(' ', '_').replace('/', '_')
        export_dir = os.path.join(DOWNLOAD_DIR, f'{safe}_handlingsrekke')
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
            self._toast(f'Eksportert til Nedlastinger:\n{safe}_handlingsrekke/')
            logging.info('Eksportert sekvens: %s', export_dir)
        except Exception:
            logging.exception('_export_sequence: feil')
            self._toast('Feil ved eksport.')

    def _del_sequence(self, seq):
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
            size_hint=(0.95, 0.94),
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
            content=layout, size_hint=(0.95, 0.92),
        )
        pick_ref[0] = pick_pop
        pick_pop.open()

    def _seq_pick_from_device(self, seq_items, refresh_fn):
        """Åpner Android-bildevelger for å legge bilde til i handlingsrekken."""
        def on_picked(dst):
            if not dst:
                return
            fname    = os.path.basename(dst)
            name_sug = os.path.splitext(fname)[0].replace('_', ' ')
            seq_items.append({'id': str(uuid.uuid4()), 'name': name_sug, 'image': dst})
            refresh_fn()
            self._toast(f'Lagt til: {fname}')
            logging.info('Sekvens: bilde lagt til fra enhet: %s', dst)
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

        # ── Hjelp ────────────────────────────────────────────────────
        outer.add_widget(Label(text='Hjelp:', size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True, color=(0.08,0.10,0.35,1), halign='left'))
        outer.add_widget(mk_btn('Les brukerveiledning', hex_k('#4D96FF'), h=dp(54), fs=15,
            cb=lambda *_: self._show_help_popup()))

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
              size_hint=(0.95, 0.92)).open()

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
            content=outer, size_hint=(0.95, 0.92),
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
            pop = Popup(title=title, content=layout, size_hint=(0.88, 0.82))
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
        self._push('home')
        self._show_dagsrytme()

    def _show_dagsrytme(self, **_):
        self._cur_scr = 'dagsrytme'
        self._set_title('Dagsrytme')
        self._build_dagsrytme_ui()
        if hasattr(self, '_dr_event') and self._dr_event:
            self._dr_event.cancel()
        self._dr_event = Clock.schedule_interval(
            lambda *_: self._build_dagsrytme_ui(), 30)

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

    def _build_dagsrytme_ui(self):
        """Bygger dagsrytme-skjermen. Kalles også av bakgrunnsklokken."""
        if self._cur_scr != 'dagsrytme':
            return
        entries = sorted(self.data.get('dagsrytme', []),
                         key=lambda e: e.get('start', '00:00'))
        now   = datetime.now()
        now_m = now.hour * 60 + now.minute

        current = upcoming = None
        for e in entries:
            s = self._dr_parse(e.get('start', '00:00'))
            t = self._dr_parse(e.get('end',   '23:59'))
            if s <= now_m < t:
                current = (e, s, t)
            elif s > now_m and upcoming is None:
                upcoming = (e, s)

        outer = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10),
                          size_hint_y=None)
        outer.bind(minimum_height=outer.setter('height'))

        if self.edit_mode:
            outer.add_widget(mk_btn('+  Legg til aktivitet', hex_k('#6BCB77'), h=dp(50),
                cb=lambda *_: self._dr_entry_popup(None)))
            outer.add_widget(mk_btn('↗  Eksporter dagsplan', hex_k('#546E7A'), h=dp(48),
                cb=lambda *_: self._export_popup('dagsrytme')))

        if current:
            e, s_m, t_m = current
            remaining = t_m - now_m
            elapsed   = now_m - s_m
            duration  = max(t_m - s_m, 1)
            if e.get('image') and os.path.exists(e['image']):
                outer.add_widget(Image(source=e['image'], size_hint_y=None, height=dp(260),
                    allow_stretch=True, keep_ratio=True))
            outer.add_widget(Label(text=e['name'], size_hint_y=None, height=dp(52),
                font_size=fsp(26), bold=True, color=(0.04, 0.10, 0.36, 1), halign='center'))
            outer.add_widget(Label(
                text=f'{e.get("start","")}  -  {e.get("end","")}',
                size_hint_y=None, height=dp(28), font_size=fsp(14),
                color=(0.4, 0.44, 0.55, 1), halign='center'))
            outer.add_widget(Label(
                text=f'Slutter om {self._dr_fmt(remaining)}',
                size_hint_y=None, height=dp(34), font_size=fsp(16),
                color=(0.25, 0.35, 0.55, 1), halign='center'))
            pb = ProgressBar(max=duration, value=elapsed,
                             size_hint_y=None, height=dp(18))
            outer.add_widget(pb)

            # Fargede fremgangsetiketter – grønn → gul → rød
            pct = elapsed / duration if duration > 0 else 0
            if pct < 0.6:
                prog_col = (0.15, 0.65, 0.20, 1)   # grønn: god tid igjen
            elif pct < 0.85:
                prog_col = (0.85, 0.62, 0.05, 1)   # gul: snart slutt
            else:
                prog_col = (0.80, 0.15, 0.12, 1)   # rød: nesten ferdig

            time_bar = BoxLayout(size_hint_y=None, height=dp(8))
            with time_bar.canvas.before:
                from kivy.graphics import Color as KColor, Rectangle
                KColor(*prog_col)
                # Fyller proporsjonal bredde
                prog_rect = Rectangle(
                    pos=time_bar.pos,
                    size=(time_bar.width * (elapsed / duration), time_bar.height)
                )
            def _upd_bar(tb, val, pr=prog_rect, dur=duration):
                pr.pos  = tb.pos
                pr.size = (tb.width * (val / dur), tb.height)
            time_bar.bind(size=lambda tb, *_: _upd_bar(tb, elapsed),
                          pos=lambda  tb, *_: _upd_bar(tb, elapsed))
            outer.add_widget(time_bar)

        elif upcoming:
            e, s_m = upcoming
            wait = s_m - now_m
            outer.add_widget(Label(text='Ingen aktiv aktivitet na',
                size_hint_y=None, height=dp(36), font_size=fsp(17),
                color=(0.5, 0.5, 0.5, 1), halign='center'))
            if e.get('image') and os.path.exists(e['image']):
                outer.add_widget(Image(source=e['image'], size_hint_y=None, height=dp(160),
                    allow_stretch=True, keep_ratio=True, opacity=0.65))
            outer.add_widget(Label(text=f'Neste: {e["name"]}',
                size_hint_y=None, height=dp(44), font_size=fsp(22), bold=True,
                color=(0.04, 0.10, 0.36, 1), halign='center'))
            outer.add_widget(Label(
                text=f'Starter om {self._dr_fmt(wait)}  (kl. {e.get("start","")})',
                size_hint_y=None, height=dp(32), font_size=fsp(16),
                color=(0.3, 0.4, 0.5, 1), halign='center'))
        elif entries:
            outer.add_widget(Label(text='Alle aktiviteter for i dag er ferdige.',
                font_size=fsp(17), color=(0.4, 0.4, 0.5, 1),
                halign='center', valign='middle'))
        else:
            # Sentrert i tilgjengelig plass med spacere over og under
            outer.add_widget(BoxLayout())  # øvre spacer
            outer.add_widget(Label(
                text='Ingen aktiviteter lagt til.\nTrykk "Red." og "+" for å starte.',
                font_size=fsp(16), color=(0.45, 0.45, 0.5, 1),
                size_hint_y=None, height=dp(80),
                halign='center', valign='middle'))
            outer.add_widget(BoxLayout())  # nedre spacer

        if entries:
            outer.add_widget(Label(text='Plan for dagen:', size_hint_y=None, height=dp(26),
                font_size=fsp(14), bold=True, color=(0.3, 0.3, 0.4, 1), halign='left'))
            list_sv  = ScrollView(size_hint_y=None, height=dp(176))
            list_box = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_y=None)
            list_box.bind(minimum_height=list_box.setter('height'))
            for e in entries:
                is_cur = bool(current and current[0]['id'] == e['id'])
                row = RBox(orientation='horizontal', size_hint_y=None, height=dp(52),
                    spacing=dp(6), padding=(dp(8), dp(4)),
                    box_color=(0.84, 0.96, 0.84, 1.0) if is_cur else (0.97, 0.97, 1.0, 1.0),
                    radius=dp(14))
                row.add_widget(Label(
                    text=f'  {e.get("start","?")} - {e.get("end","?")}  {e["name"]}',
                    font_size=fsp(14), bold=is_cur,
                    color=(0.04, 0.30, 0.04, 1) if is_cur else (0.08, 0.10, 0.35, 1),
                    halign='left'))
                if self.edit_mode:
                    row.add_widget(mk_btn('Red.', hex_k('#C77DFF'), h=dp(44), fs=12,
                        size_hint_x=None, width=dp(52),
                        cb=lambda *_, en=e: self._dr_entry_popup(en)))
                    row.add_widget(mk_btn('Slett', hex_k('#FF6B6B'), h=dp(44), fs=12,
                        size_hint_x=None, width=dp(58),
                        cb=lambda *_, en=e: self._dr_delete(en)))
                list_box.add_widget(row)
            list_sv.add_widget(list_box)
            outer.add_widget(list_sv)

        sv = ScrollView()
        sv.add_widget(outer)
        self._content.clear_widgets()
        sv.opacity = 1  # ingen fade for bakgrunnsoppdatering
        self._content.add_widget(sv)

    def _dr_delete(self, entry):
        self.data['dagsrytme'] = [
            e for e in self.data.get('dagsrytme', []) if e['id'] != entry['id']]
        save_struct(self.data)
        self._build_dagsrytme_ui()

    def _dr_entry_popup(self, entry):
        """Popup for å opprette eller redigere en dagsrytme-aktivitet."""
        new = entry is None
        pop_ref = [None]
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        layout.add_widget(Label(text='Navn:', size_hint_y=None, height=dp(28),
            font_size=fsp(15), color=(0, 0, 0, 1), halign='left'))
        # on_save defineres nedenfor – bruk lambda for å unngå NameError
        name_inp = smart_input(
            text='' if new else entry['name'],
            hint='Navn på aktivitet',
            on_save=lambda *_: on_save(),
        )
        layout.add_widget(name_inp)

        time_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        time_row.add_widget(Label(text='Fra:', size_hint_x=None, width=dp(40),
            font_size=fsp(15), color=(0, 0, 0, 1)))
        start_inp = TextInput(text='08:00' if new else entry.get('start', '08:00'),
            multiline=False, size_hint_x=None, width=dp(80), font_size=sp(18),
            size_hint_y=None, height=dp(50))
        time_row.add_widget(start_inp)
        time_row.add_widget(Label(text='Til:', size_hint_x=None, width=dp(36),
            font_size=fsp(15), color=(0, 0, 0, 1)))
        end_inp = TextInput(text='08:30' if new else entry.get('end', '08:30'),
            multiline=False, size_hint_x=None, width=dp(80), font_size=sp(18),
            size_hint_y=None, height=dp(50))
        time_row.add_widget(end_inp)
        time_row.add_widget(Label(text='(HH:MM)', size_hint_x=None, width=dp(76),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1)))
        layout.add_widget(time_row)

        chosen_img = [entry.get('image') if entry else None]
        img_lbl = Label(
            text='Bilde: ' + (os.path.basename(chosen_img[0]) if chosen_img[0] else 'ingen'),
            size_hint_y=None, height=dp(26), font_size=fsp(13), color=(0.3, 0.3, 0.3, 1))
        layout.add_widget(img_lbl)
        layout.add_widget(mk_btn('Velg bilde', hex_k('#4D96FF'), h=dp(48),
            cb=lambda *_: self._pick_from_folders(chosen_img, img_lbl)))

        btn_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        def on_save(*_):
            nm = name_inp.text.strip()
            st = start_inp.text.strip()
            en = end_inp.text.strip()
            if not nm or not st or not en:
                self._toast('Fyll inn navn og tidspunkt.')
                return
            if new:
                self.data.setdefault('dagsrytme', []).append({
                    'id': str(uuid.uuid4()), 'name': nm,
                    'start': st, 'end': en, 'image': chosen_img[0]})
            else:
                entry.update({'name': nm, 'start': st, 'end': en, 'image': chosen_img[0]})
            save_struct(self.data)
            Clock.schedule_once(lambda *_: _update_widget(self.data), 0.2)
            pop_ref[0].dismiss()
            self._build_dagsrytme_ui()
        btn_row.add_widget(mk_btn('Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_save))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(50),
            cb=lambda *_: pop_ref[0].dismiss()))
        layout.add_widget(btn_row)

        pop = Popup(title='Ny aktivitet' if new else 'Rediger aktivitet',
                    content=layout, size_hint=(0.95, 0.90))
        pop_ref[0] = pop; pop.open()

    # ══════════════════════════════════════════════════
    #  TIDSUR
    # ══════════════════════════════════════════════════

    def _export_popup(self, mode, seq=None):
        """
        Eksporter dagsplan eller handlingsrekke som PNG til Nedlastinger.
        Kjøres i bakgrunnstråd for å ikke fryse UI.
        """
        if not PIL_OK:
            self._toast('PIL ikke tilgjengelig.')
            return
        import datetime as _dt, threading

        entries = (self.data.get('dagsrytme', []) if mode == 'dagsrytme'
                   else (seq.get('items', []) if seq else []))
        title   = ('Dagsplan' if mode == 'dagsrytme'
                   else (seq.get('name', 'Rekke') if seq else 'Rekke'))
        fname   = f'{title}_{_dt.date.today()}.png'

        if not entries:
            self._toast('Ingen innhold å eksportere.')
            return

        self._toast('Eksporterer…')

        def _do():
            try:
                W, ROW, PAD = 800, 88, 20
                H = PAD*2 + 60 + ROW * len(entries)
                img = PILImage.new('RGB', (W, H), (250, 251, 255))
                d   = ImageDraw.Draw(img)
                try:
                    fh = ImageFont.truetype(_FONT_PATH, 32)
                    fr = ImageFont.truetype(_FONT_PATH, 22)
                    fs = ImageFont.truetype(_FONT_PATH, 18)
                except Exception:
                    fh = fr = fs = ImageFont.load_default()

                d.rectangle([0,0,W,58], fill=(21,28,68))
                d.text((W//2, 29), title, font=fh,
                       fill=(255,255,255), anchor='mm')

                for i, e in enumerate(entries):
                    y  = PAD + 60 + i * ROW
                    bg = (240,242,252) if i%2==0 else (248,249,255)
                    d.rectangle([0,y,W,y+ROW-2], fill=bg)
                    nx = PAD
                    if mode == 'dagsrytme':
                        tid = f"{e.get('start','')}–{e.get('end','')}"
                        d.text((PAD, y+ROW//2), tid, font=fs,
                               fill=(80,90,120), anchor='lm')
                        nx = 190
                    ip = e.get('image','')
                    if ip and os.path.exists(ip):
                        try:
                            sym = PILImage.open(ip).convert('RGBA')
                            sym.thumbnail((ROW-8, ROW-8))
                            # Bruk alfa-kanal som maske, eller konverter til RGB
                            r, g, b, a = sym.split()
                            sym_rgb = PILImage.merge('RGB', (r, g, b))
                            img.paste(sym_rgb, (nx, y+4), mask=a)
                            nx += ROW
                        except Exception:
                            pass
                    d.text((nx+6, y+ROW//2), e.get('name',''),
                           font=fr, fill=(20,24,60), anchor='lm')

                dst = os.path.join(DOWNLOAD_DIR, fname)
                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                img.save(dst)  # PNG – ingen quality-parameter
                Clock.schedule_once(
                    lambda *_: self._toast(f'Lagret: {fname}'), 0)
            except Exception as ex:
                Clock.schedule_once(
                    lambda *_: self._toast(f'Eksport feilet: {ex}'), 0)

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

        root = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(12))

        # Rund disk-widget – PIL-tegnet sirkel som gradvis blir hvit
        self._timer_disk = Image(
            size_hint=(1, None), height=dp(220),
            allow_stretch=True, keep_ratio=True,
        )
        root.add_widget(self._timer_disk)
        self._timer_display = Label(text='05:00', size_hint_y=None, height=dp(60),
            font_size=fsp(52), bold=True, color=(0.04, 0.10, 0.40, 1), halign='center')
        root.add_widget(self._timer_display)
        self._timer_pb = ProgressBar(max=100, value=100, size_hint_y=None, height=dp(10))
        root.add_widget(self._timer_pb)

        root.add_widget(Label(text='Velg tid:', size_hint_y=None, height=dp(26),
            font_size=fsp(15), color=(0.2, 0.2, 0.3, 1), halign='center'))

        presets = [('1 min', 60), ('2 min', 120), ('3 min', 180),
                   ('5 min', 300), ('10 min', 600), ('15 min', 900)]
        pg = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(120))
        for lbl, sek in presets:
            pg.add_widget(mk_btn(lbl, hex_k('#4D96FF'), h=dp(56), fs=14,
                cb=lambda *_, s=sek: self._tidsur_set(s)))
        root.add_widget(pg)

        cust = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        cust.add_widget(Label(text='Min:', size_hint_x=None, width=dp(44),
            font_size=fsp(15), color=(0.2, 0.2, 0.3, 1)))
        self._timer_cust_sl  = Slider(min=1, max=60, value=5, step=1)
        self._timer_cust_lbl = Label(text='5', size_hint_x=None, width=dp(34),
            font_size=fsp(15), color=(0.2, 0.2, 0.3, 1))
        self._timer_cust_sl.bind(value=lambda sl, v:
            setattr(self._timer_cust_lbl, 'text', str(int(v))))
        cust.add_widget(self._timer_cust_sl); cust.add_widget(self._timer_cust_lbl)
        cust.add_widget(mk_btn('Sett', hex_k('#FF9F43'), h=dp(52), fs=14,
            size_hint_x=None, width=dp(76),
            cb=lambda *_: self._tidsur_set(int(self._timer_cust_sl.value) * 60)))
        root.add_widget(cust)

        ctrl = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(10))
        self._timer_start_btn = mk_btn(
            'Pause' if self._timer_running else 'Start',
            hex_k('#FF9F43' if self._timer_running else '#6BCB77'),
            h=dp(60), fs=20, cb=self._tidsur_toggle)
        ctrl.add_widget(self._timer_start_btn)
        ctrl.add_widget(mk_btn('Nullstill', hex_k('#FF6B6B'), h=dp(60), fs=17,
            cb=self._tidsur_reset))
        root.add_widget(ctrl)

        self._tidsur_refresh_display()
        self._set_content(root)

    def _tidsur_set(self, seconds):
        self._tidsur_stop()
        self._timer_sek = self._timer_total_sek = seconds
        self._tidsur_refresh_display()

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

    def _tidsur_stop(self):
        self._timer_running = False
        ev = getattr(self, '_timer_event', None)
        if ev:
            ev.cancel()
            self._timer_event = None
        if hasattr(self, '_timer_start_btn') and self._timer_start_btn:
            self._timer_start_btn.text      = 'Start'
            self._timer_start_btn.btn_color = list(hex_k('#6BCB77'))

    def _tidsur_reset(self, *_):
        self._tidsur_stop()
        self._timer_sek = getattr(self, '_timer_total_sek', 300)
        self._tidsur_refresh_display()

    def _tidsur_tick(self, dt):
        self._timer_sek = max(0, getattr(self, '_timer_sek', 0) - 1)
        if self._timer_sek <= 0:
            self._tidsur_stop()
            self._toast('Tiden er ute!', duration=4.0)
            Clock.schedule_once(lambda *_: launch_confetti(3.0), 0.1)
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
        Pai-animasjon: starter som hel rød sirkel, blir gradvis hvit.
        frac=1.0 → full rød pai (full tid igjen)
        frac=0.0 → helt hvit (tom – tid ute)

        Visuelt: rød "pai" tegnes fra toppen og dekker frac*360 grader.
        Resten er hvit. Ingen donut – full fyllt sirkel.
        Fargen interpolerer: rød (#E53935) → oransje (#FF9800) → hvit
        slik at siste 20% advarer med oransje.
        """
        SIZE = 300
        cx = cy = SIZE // 2
        r  = SIZE // 2 - 8

        pil_img = PILImage.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
        d       = ImageDraw.Draw(pil_img)

        # Hvit bakgrunns-sirkel (vises når frac < 1.0)
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(245, 245, 248, 255))

        if frac > 0.001:
            # Farge: rød → oransje de siste 20%
            if frac > 0.20:
                col = (229, 57, 53, 255)    # rød #E53935
            else:
                t = frac / 0.20             # 0→1 i siste 20%
                col = (
                    int(255 + (229 - 255) * t),   # R: 255→229
                    int(152 + (57  - 152) * t),   # G: 152→57
                    int(0   + (53  - 0)   * t),   # B: 0→53
                    255
                )
            # Tegn rød pai fra toppen, dekker frac av sirkelen
            end_angle = -90 + frac * 360
            d.pieslice(
                [cx-r, cy-r, cx+r, cy+r],
                start=-90, end=end_angle,
                fill=col,
            )

        # Tynn mørk kant
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
        pop = Popup(title='Bildepar-spill', content=layout, size_hint=(0.88, 0.64))
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
        pop = Popup(title='Spill fullfort!', content=layout, size_hint=(0.82, 0.52))
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
                    'id':    str(uuid.uuid4()),
                    'name':  nm,
                    'color': chosen_color[0],
                    'image': chosen_img[0],
                    'items': [],
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
            content=layout, size_hint=(0.93, 0.90),
        )
        pop_ref[0] = pop
        pop.open()

    def _del_folder(self, fo):
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
        init_src = ''
        if it and it.get('image') and os.path.exists(it.get('image', '')):
            init_src = it['image']
        img_preview = Image(
            source=init_src,
            size_hint_y=None, height=dp(180),
            allow_stretch=True, keep_ratio=True,
        )
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
                def on_picked(dst):
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
            content=sv, size_hint=(0.93, 0.82),
        )
        pop_ref[0] = pop
        pop.open()

    def _del_item(self, fo, it):
        fo['items'] = [i for i in fo['items'] if i['id'] != it['id']]
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

        grid = GridLayout(cols=4, spacing=dp(6), padding=(dp(4),dp(4)),
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
            content=layout, size_hint=(0.90, 0.82))
        pop_ref[0] = pop; pop.open()

    def _del_subfolder(self, parent_fo, sub):
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
            content=layout, size_hint=(0.88, 0.82),
        )
        pop_ref[0] = pop
        pop.open()

    # ══════════════════════════════════════════════════
    #  BILDE – LAST OPP / LAST NED
    # ══════════════════════════════════════════════════

    def _pick_from_folders(self, chosen_img_ref, label_widget):
        """
        Lar brukeren velge et allerede opplastet bilde fra mappene.
        Viser alle mapper og bildene i dem – ingen filvelger nødvendig.
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
                # Bilder i 4-kolonne grid
                img_grid = GridLayout(
                    cols=4, spacing=dp(4), size_hint_y=None)
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
                    size_hint=(0.96, 0.90))
        pop_ref[0] = pop
        pop.open()

    def _pick_image(self, chosen_img_ref, label_widget, parent_popup=None):
        """
        Åpner Androids innebygde bildevelger (ACTION_OPEN_DOCUMENT).
        Ingen tillatelser nødvendig – Android håndterer alt.
        På ikke-Android brukes FileChooserListView som fallback.
        """
        if platform == 'android':
            def on_picked(dst):
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
            pop = Popup(title='Velg bilde', content=fc_layout, size_hint=(0.97, 0.93))
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
            term = inp.text.strip().lower()
            grid.clear_widgets()
            if not term:
                return
            hits = [(fo, it)
                    for fo in self.data.get('folders', [])
                    for it in fo.get('items', [])
                    if term in it.get('name','').lower()]
            status.text = f'{len(hits)} lokale treff'
            for fo, it in hits[:24]:
                cell = BoxLayout(orientation='vertical',
                                 size_hint_y=None, height=dp(112))
                if it.get('image') and os.path.exists(it['image']):
                    from kivy.uix.image import Image as KImg
                    cell.add_widget(KImg(
                        source=it['image'], allow_stretch=True,
                        keep_ratio=True, size_hint_y=None, height=dp(82)))
                lbl = Label(text=it['name'], font_size=sp(11),
                            size_hint_y=None, height=dp(22),
                            color=(0.1,0.1,0.2,1),
                            shorten=True, shorten_from='right')
                lbl.bind(size=lbl.setter('text_size'))
                cell.add_widget(lbl)
                def _tap(w, t, _fo=fo):
                    if w.collide_point(*t.pos):
                        pop_ref[0].dismiss()
                        self._open_folder(_fo)
                        return True
                cell.bind(on_touch_down=_tap)
                grid.add_widget(cell)

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
                    Clock.schedule_once(
                        lambda *_: setattr(status, 'text', f'Feil: {e}'), 0)
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

        pop = Popup(title='Søk', content=layout, size_hint=(0.96, 0.92))
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
                       size_hint=(0.82, 0.72))
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
                    Clock.schedule_once(
                        lambda *_: setattr(status, 'text', f'Feil: {e}'), 0)
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
                    content=layout, size_hint=(0.96, 0.92))
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
        warn_pop = Popup(title='Personvern', content=warn_layout, size_hint=(0.90, 0.68))
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

    def _toast(self, msg, duration=3.0):
        lbl = Label(
            text=msg, font_size=sp(15), color=(0.08, 0.10, 0.30, 1),
            halign='center', valign='middle',
        )
        lbl.bind(size=lbl.setter('text_size'))
        pop = Popup(
            title='', content=lbl,
            size_hint=(0.78, 0.22),
        )
        pop.open()
        Clock.schedule_once(lambda *_: pop.dismiss(), duration)


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
