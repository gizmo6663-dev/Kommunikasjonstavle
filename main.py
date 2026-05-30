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
        # 1. Lett skygge (halvert offset og opacity vs originalt)
        Color:
            rgba: 0.04, 0.06, 0.18, 0.13
        RoundedRectangle:
            pos: self.x + dp(1.5), self.y - dp(2.5)
            size: self.width - dp(2), self.height * 0.88
            radius: [self.radius + dp(1.5)]
        # 2. Hoved-farge
        Color:
            rgba: self.btn_color
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
        # 4. Lys toppglans – gradert fra hvit øverst
        Color:
            rgba: 1, 1, 1, 0.22
        Line:
            rounded_rectangle: (self.x + dp(2), self.y + dp(2), self.width - dp(4), self.height - dp(4), max(1, self.radius - dp(1)))
            width: 1.2

<RBox>:
    canvas.before:
        # 1. Minimal skygge (halvvert)
        Color:
            rgba: 0.04, 0.06, 0.18, 0.10
        RoundedRectangle:
            pos: self.x + dp(2), self.y - dp(3)
            size: self.width - dp(3), self.height * 0.90
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
        # Lys hvit bakgrunn for tydelig adskillelse fra innhold
        Color:
            rgba: 0.99, 0.99, 1.0, 1.0
        Rectangle:
            pos: self.pos
            size: self.size
        # Tynn separator-linje i bunn av navbaren
        Color:
            rgba: 0.72, 0.78, 0.92, 1.0
        Line:
            points: self.x, self.y, self.right, self.y
            width: 1.4

<BottomBar>:
    canvas.before:
        Color:
            rgba: 0.99, 0.99, 1.0, 1.0
        Rectangle:
            pos: self.pos
            size: self.size
        # Tynn separator-linje i topp av bunnbaren
        Color:
            rgba: 0.72, 0.78, 0.92, 1.0
        Line:
            points: self.x, self.top, self.right, self.top
            width: 1.4

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
    Avrundet knapp med skygge og dobbel kantlinje.
    Bruker btn_color (ListProperty) i stedet for background_color
    slik at KV-regelen kan lese fargen uten å kollidere med Kivys
    innebygde background_color (som settes til gjennomsiktig).
    """
    btn_color = ListProperty([0.30, 0.50, 1.0, 1.0])
    radius    = NumericProperty(dp(12))


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
        {"id": "f1", "name": "Mat og drikke", "color": "#FFD93D", "image": None, "items": []},
        {"id": "f2", "name": "Aktiviteter",   "color": "#6BCB77", "image": None, "items": []},
        {"id": "f3", "name": "Følelser",     "color": "#4D96FF", "image": None, "items": []},
        {"id": "f4", "name": "Kropp",         "color": "#FF6B6B", "image": None, "items": []},
        {"id": "f5", "name": "Klær",         "color": "#C77DFF", "image": None, "items": []},
        {"id": "f6", "name": "Transport",     "color": "#FF9F43", "image": None, "items": []},
    ],
    "sequences": [],
    "dagsrytme": [],
    "settings": {
        "tts_enabled": False,
        "font_scale": 1.0,
        "high_contrast": False
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
    Lager en RBtn med opacity-dimming ved trykk.
    I høykontrast-modus overstyres bg med svart og fg med hvit
    for å oppnå WCAG AAA-kontrast (21:1).
    """
    kw.setdefault('size_hint_y', None)
    kw.setdefault('height', h)
    if is_hc():
        btn_color = [0.0, 0.0, 0.0, 1.0]   # svart
        txt_color = (1.0, 1.0, 1.0, 1.0)   # hvit tekst
    else:
        btn_color = list(bg)
        txt_color = fg
    b = RBtn(
        text=text,
        btn_color=btn_color,
        font_size=sp(fs),
        color=txt_color, bold=True, **kw,
    )
    from kivy.animation import Animation
    def _on_press(btn, *_):
        Animation(opacity=0.72, duration=0.06, t='out_quad').start(btn)
    def _on_release_anim(btn, *_):
        Animation(opacity=1.0, duration=0.10, t='out_quad').start(btn)
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
            if 'dagsrytme' not in d:
                d['dagsrytme'] = []
            if 'settings' not in d:
                d['settings'] = {'tts_enabled': False, 'font_scale': 1.0, 'high_contrast': False}
            return d
        except Exception as e:
            logging.error('Feil ved lasting av structure.json: %s', e)
    import copy
    return copy.deepcopy(DEFAULT_STRUCT)

def save_struct(d):
    if not STRUCT_FILE:
        logging.error('save_struct: STRUCT_FILE ikke satt ennå')
        return
    os.makedirs(os.path.dirname(STRUCT_FILE), exist_ok=True)
    try:
        with open(STRUCT_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        logging.debug('structure.json lagret til %s', STRUCT_FILE)
    except Exception as e:
        logging.error('Feil ved lagring av structure.json: %s', e)

def get_folder(d, fid):
    return next((x for x in d['folders'] if x['id'] == fid), None)

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
    Kopierer en Android content-URI til en lokal filsti.

    Bruker openFileDescriptor() i stedet for openInputStream() +
    Java byte-array fordi jnius ikke kan instansiere primitive
    Java-arrays ([B) via autoclass() – dette var rotaarsaken til
    "No constructor available"-feilen.

    openFileDescriptor() returnerer en ekte POSIX file descriptor
    som Python kan lese direkte med os.fdopen() uten Java-arrays.
    """
    try:
        from jnius import autoclass
        from android import mActivity
        cr  = mActivity.getContentResolver()
        pfd = cr.openFileDescriptor(uri, 'r')
        fd  = pfd.detachFd()           # Python-lesbar int fd
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with os.fdopen(fd, 'rb') as src_f:
            data = src_f.read()
        pfd.close()
        with open(dst_path, 'wb') as dst_f:
            dst_f.write(data)
        _plog(f'_copy_content_uri OK: {dst_path} ({len(data)} bytes)')
        return True
    except Exception as e:
        _plog(f'_copy_content_uri feil: {e}')
        logging.exception('_copy_content_uri: feil')
        return False


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

        def on_activity_result(request_code, result_code, data):
            if request_code != _PICK_IMAGE_REQUEST:
                return
            activity_unbind(on_activity_result=on_activity_result)  # fjern binding
            cb = _pick_image_callback[0]
            _pick_image_callback[0] = None
            if result_code != -1 or data is None:   # RESULT_OK = -1
                _plog('Bildevelger: bruker avbrøt eller ingen data')
                if cb:
                    Clock.schedule_once(lambda *_: cb(None), 0)
                return
            uri = data.getData()
            _plog(f'Bildevelger: URI mottatt: {uri}')
            # Finn filnavn fra URI
            try:
                Cursor = autoclass('android.database.Cursor')
                OpenableColumns = autoclass('android.provider.OpenableColumns')
                from android import mActivity as act
                cursor = act.getContentResolver().query(uri, None, None, None, None)
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
            ok  = _copy_content_uri(uri, dst)
            if cb:
                Clock.schedule_once(lambda *_: cb(dst if ok else None), 0)

        activity_bind(on_activity_result=on_activity_result)
        mActivity.startActivityForResult(intent, _PICK_IMAGE_REQUEST)
        _plog('ACTION_OPEN_DOCUMENT startet')
    except Exception as e:
        _plog(f'_open_android_picker feil: {e}')
        logging.exception('_open_android_picker: feil')
        callback(None)


# ══════════════════════════════════════════════════════════════════
#  WIDGET: TRYKKBART BILDE
# ══════════════════════════════════════════════════════════════════

class TappableImage(Image):
    """Image-widget med on_touch_down-binding til en callback."""
    def __init__(self, action, **kw):
        super().__init__(**kw)
        self._action = action

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._action()
            return True
        return super().on_touch_down(touch)


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


# ══════════════════════════════════════════════════════════════════
#  HOVED-APP
# ══════════════════════════════════════════════════════════════════

class KommunikasjonstavleApp(App):

    # ── Oppstart ──────────────────────────────────────────────────

    @property
    def is_hc_mode(self):
        """KV-tilgjengelig egenskap for høykontrast-modus."""
        return bool(self.data.get('settings', {}).get('high_contrast', False))             if hasattr(self, 'data') else False

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
        self._navbar = self._build_navbar()
        root.add_widget(self._navbar)
        self._content = BoxLayout(orientation='vertical')
        root.add_widget(self._content)
        self._bottombar = self._build_bottombar()
        root.add_widget(self._bottombar)

        self._show_home()
        # Tillatelsesforespørsel fra build() – samme mønster som Eldritch Portal.
        # Må ligge her (ikke on_start) for riktig timing på Android.
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
        name_inp = TextInput(
            text=name_suggestion,
            multiline=False, size_hint_y=None, height=dp(50), font_size=sp(15),
        )
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

    def _build_navbar(self):
        """
        Navigasjonsbar med tekstknapper (ingen emojier – Android
        mangler emoji-fonter i Kivy-kontekst).
        """
        bar = NavBar(
            orientation='horizontal',
            size_hint_y=None, height=dp(66),
            padding=(dp(6), dp(6)),
            spacing=dp(6),
        )

        # Ingen tittel-label her lenger – tittel er i bunnbaren.
        # Knappene fordeles jevnt (size_hint_x=1, ikke fast bredde).
        btn_kw = dict(
            size_hint_y=None, height=dp(54),
        )

        self._btn_back = mk_btn(
            '  Tilbake', hex_k('#4D96FF'), fs=13,
            cb=self.go_back, **btn_kw,
        )
        self._btn_home = mk_btn(
            'Hjem', hex_k('#6BCB77'), fs=13,
            cb=self.go_home, **btn_kw,
        )
        self._btn_draw = mk_btn(
            'Tegn', hex_k('#FF9F43'), fs=13,
            cb=self.go_draw, **btn_kw,
        )
        self._btn_edit = mk_btn(
            'Red.', hex_k('#C77DFF'), fs=13,
            cb=self.toggle_edit, **btn_kw,
        )

        for w in [self._btn_back, self._btn_home, self._btn_draw, self._btn_edit]:
            bar.add_widget(w)
        return bar

    def _build_bottombar(self):
        """
        Bunnbar: tittel til venstre, Innstillinger-knapp til høyre.
        """
        bar = BottomBar(
            size_hint_y=None, height=dp(54),
            padding=(dp(6), dp(4)),
            spacing=dp(6),
        )
        self._lbl_title = Label(
            text=APP_TITLE, bold=True, font_size=sp(15),
            color=(0.08, 0.10, 0.35, 1),
            halign='left', valign='middle',
        )
        self._lbl_title.bind(size=self._lbl_title.setter('text_size'))
        bar.add_widget(self._lbl_title)
        bar.add_widget(mk_btn(
            'Innst.', hex_k('#78909C'),
            h=dp(46), fs=13,
            size_hint_x=None, width=dp(72),
            cb=lambda *_: self._nav_settings(),
        ))
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
        Bytter innholdsflaten med en kort fade+slide-inn animasjon.
        animate=False brukes internt (f.eks. dagsrytme-oppdatering).
        """
        # Avbryt dagsrytme-klokke
        if self._cur_scr != 'dagsrytme':
            ev = getattr(self, '_dr_event', None)
            if ev:
                ev.cancel()
                self._dr_event = None
        # Pause tidsur
        if self._cur_scr != 'tidsur' and getattr(self, '_timer_running', False):
            self._tidsur_stop()

        self._content.clear_widgets()
        widget.opacity = 0
        self._content.add_widget(widget)
        if animate:
            from kivy.animation import Animation
            anim = Animation(opacity=1, duration=0.18, t='out_quad')
            anim.start(widget)
        else:
            widget.opacity = 1

    # ══════════════════════════════════════════════════
    #  HJEMSKJERM
    # ══════════════════════════════════════════════════

    def _show_home(self, **_):
        self._cur_scr   = 'home'
        self.cur_folder = None
        self._set_title(APP_TITLE)

        outer = BoxLayout(orientation='vertical', spacing=dp(6), padding=(dp(8), dp(6)))

        # ── Fire hurtigknapper i én rad (nav-knapp-størrelse) ─────
        qrow = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        _qcols = [
            ('Rekker',  '#4ECDC4', self._nav_sequences),
            ('Dagsplan','#FF9F43', self._nav_dagsrytme),
            ('Tidsur',  '#4D96FF', self._nav_tidsur),
            ('Spill',   '#C77DFF', self._nav_bildepar),
        ]
        for lbl, col, fn in _qcols:
            qrow.add_widget(mk_btn(lbl, hex_k(col), h=dp(50), fs=13,
                cb=lambda *_, f=fn: f()))
        outer.add_widget(qrow)

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

        btn = RBtn(
            text=fo['name'],
            size_hint=(1, None), height=btn_h,
            btn_color=list(hex_k(fo['color'])),
            color=(0.05, 0.05, 0.2, 1),
            bold=True, font_size=fsp(16),
            radius=dp(16),
        )
        btn.bind(on_release=lambda b, t=tap: t())
        cell.add_widget(btn)

        if edit:
            cell.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=dp(34), fs=12,
                cb=lambda *_, f=fo: self._del_folder(f),
            ))

        return cell

    def _open_folder(self, fo):
        self._push('home')
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
                '+  Ny mappe', hex_k('#FF9F43'), h=dp(46), fs=13,
                cb=lambda *_: self._folder_popup(None),
            ))
            outer.add_widget(btn_bar)

        grid = GridLayout(cols=4, spacing=dp(6), padding=(dp(4), dp(4)), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for it in fo['items']:
            grid.add_widget(self._make_item_tile(fo, it))

        sv = ScrollView()
        sv.add_widget(grid)
        outer.add_widget(sv)
        self._set_content(outer)

    def _make_item_tile(self, fo, it):
        """
        ASK-bilde-kort: bilde klippet innenfor RBox-rammen + etikett.
        4-kolonne grid betyr smalere fliser – tilpassede størrelser.
        """
        img_path = it.get('image') or ''
        has_img  = bool(img_path and os.path.exists(img_path))
        edit     = self.edit_mode

        IMG_H  = dp(78)
        LBL_H  = dp(34)
        ACT_H  = dp(36)
        TILE_H = (IMG_H + LBL_H + ACT_H + dp(14)) if edit else (IMG_H + LBL_H + dp(10))

        if edit:
            tap = lambda f=fo, i=it: self._item_popup(f, i)
        else:
            tap = lambda p=img_path, n=it['name']: self._show_image_full(p, n)

        # Kortcontainer med farget bakgrunn fra mappens farge (tonet)
        r, g, b, _ = hex_k(fo.get('color', '#4D96FF'))
        card_col   = (r * 0.15 + 0.85, g * 0.15 + 0.85, b * 0.15 + 0.85, 1.0)

        cell = RBox(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=dp(2),
            padding=(dp(3), dp(3)),
            box_color=list(card_col),
            radius=dp(14),
        )

        if has_img:
            # Bilde fyller RBox nøyaktig – ingen overflow
            img_box = RBox(
                size_hint=(1, None), height=IMG_H,
                box_color=(1.0, 1.0, 1.0, 0.0),
                radius=dp(10),
                padding=0,
            )
            img_box.add_widget(TappableImage(
                tap, source=img_path,
                allow_stretch=True, keep_ratio=True,
            ))
            cell.add_widget(img_box)

        lbl_h = LBL_H if has_img else (dp(100) if not edit else dp(78))
        btn = RBtn(
            text=it['name'],
            size_hint=(1, None), height=lbl_h,
            btn_color=list(hex_k(fo.get('color', '#4D96FF'))),
            color=(1, 1, 1, 1), bold=True, font_size=fsp(11),
            radius=dp(10),
        )
        btn.bind(on_release=lambda b: tap())
        cell.add_widget(btn)

        if edit:
            row = BoxLayout(size_hint_y=None, height=ACT_H, spacing=dp(2))
            row.add_widget(mk_btn(
                'Flytt', hex_k('#FF9F43'), h=ACT_H - dp(2), fs=10,
                cb=lambda *_, f=fo, i=it: self._move_item_popup(f, i),
            ))
            row.add_widget(mk_btn(
                'Ned', hex_k('#6BCB77'), h=ACT_H - dp(2), fs=10,
                cb=lambda *_, p=img_path: self._download_image(p),
            ))
            row.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=ACT_H - dp(2), fs=10,
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
                radius=dp(10),
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
        Åpner et popup-vindu med alle 24 farger i et 6×4-rutenett.
        Valg av farge setter tegnefargen og lukker popupen.
        _col_btns oppdateres her slik at _set_draw_color kan markere
        gjeldende valg med lys uthevning.
        """
        layout = BoxLayout(
            orientation='vertical',
            spacing=dp(10), padding=dp(14),
        )

        # Overskrift
        layout.add_widget(Label(
            text='Velg tegnefargen din:',
            size_hint_y=None, height=dp(32),
            font_size=sp(16), bold=True,
            color=(0.08, 0.10, 0.35, 1),
            halign='center', valign='middle',
        ))

        # 6×4-rutenett med fargeknapper
        grid = GridLayout(
            cols=6, spacing=dp(6),
            size_hint_y=None,
        )
        grid.bind(minimum_height=grid.setter('height'))

        pop_ref = [None]
        self._col_btns = {}

        for col_hex in PALETTE:
            cb = RBtn(
                size_hint=(None, None),
                size=(dp(46), dp(46)),
                btn_color=list(hex_k(col_hex)),
                radius=dp(23),
            )
            def pick(b, c=col_hex):
                self._set_draw_color(c)
                pop_ref[0].dismiss()
            cb.bind(on_release=pick)
            grid.add_widget(cb)
            self._col_btns[col_hex] = cb

        layout.add_widget(grid)

        layout.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(50), fs=15,
            cb=lambda *_: pop_ref[0].dismiss(),
        ))

        pop = Popup(
            title='Velg farge', content=layout,
            size_hint=(0.95, 0.90),
        )
        pop_ref[0] = pop

        # Marker gjeldende farge i popupen med det samme
        if self.draw_canvas:
            self._set_draw_color(self.draw_canvas.draw_color)

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
            radius=dp(12),
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
        name_inp = TextInput(
            text='' if new_seq else seq['name'],
            multiline=False, size_hint_y=None, height=dp(52), font_size=sp(16),
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
                    box_color=(0.96, 0.97, 1.0, 1.0), radius=dp(10),
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
        outer.add_widget(Label(
            text='Svart bakgrunn og hvit tekst på alle knapper (WCAG AAA, 7:1). Gjelder fra neste skjerminnlasting.',
            size_hint_y=None, height=dp(44),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1), halign='left'))

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
        outer.add_widget(Label(
            text=(
                'Trykk "Last opp" i en mappe for å velge bilde.\n'
                'Android-bildevelgeren apnes – ingen tillatelser trengs.\n\n'
                'Bilder lagres i appens private mappe (user_data_dir/images).\n'
                'Eksporter via "Last ned"-knappen for å kopiere til Nedlastinger.'
            ),
            size_hint_y=None, height=dp(110),
            font_size=fsp(12), color=(0.3, 0.3, 0.4, 1),
            halign='left', valign='top'))

        # ── Tilgang til alle filer (EP-stil backup) ──────────────────
        outer.add_widget(Label(
            text='Tilgang til alle filer (valgfritt):',
            size_hint_y=None, height=dp(32),
            font_size=fsp(17), bold=True,
            color=(0.08, 0.10, 0.35, 1), halign='left'))

        has_access = False
        if platform == 'android':
            try:
                from jnius import autoclass
                Environment = autoclass('android.os.Environment')
                has_access = bool(Environment.isExternalStorageManager())
            except Exception:
                pass
        outer.add_widget(Label(
            text='Status: PA' if has_access else 'Status: AV',
            size_hint_y=None, height=dp(28),
            font_size=fsp(14), bold=True,
            color=(0.10, 0.55, 0.10, 1) if has_access else (0.75, 0.20, 0.20, 1),
            halign='left'))
        outer.add_widget(Label(
            text='Ikke nødvendig for bildevelgeren, men gir tilgang til alle mapper.',
            size_hint_y=None, height=dp(34),
            font_size=fsp(12), color=(0.5, 0.5, 0.5, 1), halign='left'))

        def open_manage(*_):
            if platform != 'android':
                self._toast('Kun tilgjengelig på Android.')
                return
            try:
                from jnius import autoclass
                from android import mActivity
                Intent   = autoclass('android.content.Intent')
                Settings = autoclass('android.provider.Settings')
                Uri      = autoclass('android.net.Uri')
                intent   = Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                intent.setData(Uri.parse(
                    'package:' + mActivity.getPackageName()))
                mActivity.startActivity(intent)
            except Exception:
                logging.exception('open_manage: feil')
                self._toast('Kunne ikke apne innstillinger.')

        outer.add_widget(mk_btn(
            'Gi tilgang (åpner innstillinger)',
            hex_k('#546E7A'), h=dp(54), fs=15,
            cb=open_manage))

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
            radius=dp(10), padding=(dp(10), dp(8)),
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
                             size_hint_y=None, height=dp(20))
            outer.add_widget(pb)

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
            outer.add_widget(Label(
                text='Ingen aktiviteter lagt til.\nTrykk "Red." og "+" for å starte.',
                font_size=fsp(16), color=(0.45, 0.45, 0.5, 1),
                halign='center', valign='middle'))

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
                    radius=dp(10))
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
        name_inp = TextInput(text='' if new else entry['name'],
            multiline=False, size_hint_y=None, height=dp(52), font_size=sp(16))
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
            cb=lambda *_: self._pick_image(chosen_img, img_lbl, pop_ref[0])))

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

        self._timer_display = Label(text='05:00', size_hint_y=None, height=dp(130),
            font_size=fsp(66), bold=True, color=(0.04, 0.10, 0.40, 1), halign='center')
        root.add_widget(self._timer_display)

        self._timer_pb = ProgressBar(max=100, value=100, size_hint_y=None, height=dp(22))
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
        self._tidsur_refresh_display()

    def _tidsur_refresh_display(self):
        if not hasattr(self, '_timer_display') or not self._timer_display:
            return
        sek  = getattr(self, '_timer_sek', 0)
        mins = sek // 60; secs = sek % 60
        self._timer_display.text = f'{mins:02d}:{secs:02d}'
        if hasattr(self, '_timer_pb') and self._timer_pb:
            total = max(getattr(self, '_timer_total_sek', 1), 1)
            self._timer_pb.value = int((sek / total) * 100)

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
                    box_color=(0.84, 0.96, 0.84, 1.0), radius=dp(12))
                cell.add_widget(Image(source=card['path'], size_hint=(1, None), height=dp(82),
                    allow_stretch=True, keep_ratio=True))
                cell.add_widget(Label(text=card['name'], font_size=fsp(11),
                    size_hint_y=None, height=dp(26),
                    color=(0.1, 0.45, 0.1, 1), halign='center'))
            elif state == 'revealed':
                cell = RBox(orientation='vertical', size_hint_y=None, height=h,
                    spacing=dp(2), padding=dp(3),
                    box_color=(1.0, 0.95, 0.80, 1.0), radius=dp(12))
                cell.add_widget(Image(source=card['path'], size_hint=(1, None), height=dp(82),
                    allow_stretch=True, keep_ratio=True))
                cell.add_widget(Label(text=card['name'], font_size=fsp(11),
                    size_hint_y=None, height=dp(26),
                    color=(0.50, 0.35, 0.00, 1), halign='center'))
            else:
                cell = RBox(size_hint_y=None, height=h,
                    box_color=list(hex_k('#4D96FF')), radius=dp(12))
                btn  = RBtn(text='?', btn_color=list(hex_k('#4D96FF')),
                    color=(1, 1, 1, 1), bold=True, font_size=fsp(32), radius=dp(12))
                btn.bind(on_release=lambda b, i=idx: self._bildepar_tap(i))
                cell.add_widget(btn)
            self._bp_grid.add_widget(cell)

    def _bildepar_tap(self, idx):
        if self._bp_state[idx] != 'hidden' or len(self._bp_revealed) >= 2:
            return
        self._bp_state[idx] = 'revealed'
        self._bp_revealed.append(idx)
        self._bildepar_rebuild_grid()
        if len(self._bp_revealed) == 2:
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
        name_inp = TextInput(
            text='' if new else fo['name'],
            multiline=False, size_hint_y=None, height=dp(52), font_size=sp(16),
        )
        layout.add_widget(name_inp)

        layout.add_widget(Label(
            text='Velg farge:', size_hint_y=None, height=dp(26),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        chosen_color = [fo['color'] if fo else FOLDER_COLORS[0]]
        # 4×2 rutenett – alle 8 farger vises uten å flyte utenfor
        col_grid = GridLayout(cols=4, spacing=dp(8),
                              size_hint_y=None, height=dp(120))
        col_btns = []
        for c in FOLDER_COLORS:
            cb = RBtn(
                btn_color=list(hex_k(c)),
                size_hint=(1, None), height=dp(52),
                opacity=1.0 if chosen_color[0] == c else 0.5,
                radius=dp(12),
            )
            def pick(b, col=c, btns=col_btns, sel=chosen_color):
                sel[0] = col
                for x in btns:
                    x.opacity = 0.5
                b.opacity = 1.0
            cb.bind(on_release=pick)
            col_grid.add_widget(cb)
            col_btns.append(cb)
        layout.add_widget(col_grid)

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
        name_inp = TextInput(
            text='' if new else it['name'],
            multiline=False, size_hint_y=None, height=dp(52), font_size=sp(16),
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
                color=(0.05, 0.05, 0.2, 1),
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
            def on_picked(dst):
                if not dst:
                    self._toast('Ingen bilde valgt.')
                    return
                fname = os.path.basename(dst)
                name_suggestion = os.path.splitext(fname)[0].replace('_', ' ')
                fo['items'].append({
                    'id':    str(uuid.uuid4()),
                    'name':  name_suggestion,
                    'image': dst,
                })
                save_struct(self.data)
                self._toast(f'Lagt til: {fname}')
                self._show_folder(fid=fo['id'])
                logging.info('Bilde lastet opp til mappe: %s', fname)
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
    try:
        KommunikasjonstavleApp().run()
    except Exception:
        # Siste utvei: skriv krasj til loggfil selv om appen aldri startet
        try:
            if LOG_FILE:
                os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write('\n=== FATAL KRASJ ===\n')
                    _tb.print_exc(file=f)
        except Exception:
            pass
        raise
