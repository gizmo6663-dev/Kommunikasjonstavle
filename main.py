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
        # 1. Mjuk skygge forskjøvet ned-høyre
        Color:
            rgba: 0.04, 0.06, 0.18, 0.26
        RoundedRectangle:
            pos: self.x + dp(3), self.y - dp(5)
            size: self.width - dp(4), self.height * 0.80
            radius: [self.radius + dp(3)]
        # 2. Hoved-farge (beholdes fra btn_color – ingen fargeendring)
        Color:
            rgba: self.btn_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
        # 3. Mørk ytre kantlinje – gir dybde mot lys bakgrunn
        Color:
            rgba: 0, 0, 0, 0.20
        Line:
            rounded_rectangle: (self.x + dp(1), self.y + dp(1), self.width - dp(2), self.height - dp(2), self.radius)
            width: 1.2
        # 4. Lys indre kantlinje – imiterer lett skinnende overflate
        Color:
            rgba: 1, 1, 1, 0.35
        Line:
            rounded_rectangle: (self.x + dp(2.5), self.y + dp(2.5), self.width - dp(5), self.height - dp(5), max(1, self.radius - dp(1)))
            width: 1.5

<RBox>:
    canvas.before:
        # 1. Skygge
        Color:
            rgba: 0.04, 0.06, 0.18, 0.20
        RoundedRectangle:
            pos: self.x + dp(4), self.y - dp(6)
            size: self.width - dp(6), self.height * 0.82
            radius: [self.radius + dp(3)]
        # 2. Bakgrunnsfarge
        Color:
            rgba: self.box_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
        # 3. Mørk ytre kant
        Color:
            rgba: 0, 0, 0, 0.15
        Line:
            rounded_rectangle: (self.x + dp(1), self.y + dp(1), self.width - dp(2), self.height - dp(2), self.radius)
            width: 1.1
        # 4. Lys indre kant
        Color:
            rgba: 1, 1, 1, 0.28
        Line:
            rounded_rectangle: (self.x + dp(2.5), self.y + dp(2.5), self.width - dp(5), self.height - dp(5), max(1, self.radius - dp(1)))
            width: 1.4

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
"""

Builder.load_string(_KV)


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
DATA_DIR     = '/sdcard/Documents/Kommunikasjonstavle'
IMG_DIR      = os.path.join(DATA_DIR, 'images')
DRAW_DIR     = os.path.join(DATA_DIR, 'drawings')
STRUCT_FILE  = os.path.join(DATA_DIR, 'structure.json')
LOG_FILE     = os.path.join(DATA_DIR, 'crash.log')
DOWNLOAD_DIR = '/sdcard/Download'

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

# Fargepalett for tegning (12 farger)
# 24 farger i 6 kolonner × 4 rader – brukes i fargevalgpopup.
PALETTE = [
    # Nøytrale
    '#000000', '#333333', '#777777', '#AAAAAA', '#DDDDDD', '#FFFFFF',
    # Varme
    '#EF5350', '#FF7043', '#FF9800', '#FFD600', '#FFEB3B', '#FF5722',
    # Kalde
    '#43A047', '#4CAF50', '#1E88E5', '#3949AB', '#8E24AA', '#00ACC1',
    # Ekstra
    '#EC407A', '#6D4C41', '#78909C', '#00BCD4', '#9C27B0', '#795548',
]

DEFAULT_STRUCT = {
    "folders": [
        {"id": "f1", "name": "Mat og drikke", "color": "#FFD93D", "image": None, "items": []},
        {"id": "f2", "name": "Aktiviteter",   "color": "#6BCB77", "image": None, "items": []},
        {"id": "f3", "name": "Foelelser",     "color": "#4D96FF", "image": None, "items": []},
        {"id": "f4", "name": "Kropp",         "color": "#FF6B6B", "image": None, "items": []},
        {"id": "f5", "name": "Klaer",         "color": "#C77DFF", "image": None, "items": []},
        {"id": "f6", "name": "Transport",     "color": "#FF9F43", "image": None, "items": []},
    ],
    "sequences": [],
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

def mk_btn(text, bg, fg=(1, 1, 1, 1), fs=15, h=dp(54), cb=None, **kw):
    """
    Lager en RBtn (avrundet knapp med skygge og dobbel kant).
    bg sendes som btn_color – IKKE background_color – fordi KV-regelen
    bruker btn_color og setter background_color til gjennomsiktig.
    size_hint_y / height løses via setdefault for å unngå duplikat-kw.
    """
    kw.setdefault('size_hint_y', None)
    kw.setdefault('height', h)
    b = RBtn(
        text=text,
        btn_color=list(bg),
        font_size=sp(fs),
        color=fg, bold=True, **kw,
    )
    if cb:
        b.bind(on_release=cb)
    return b

def load_struct():
    if os.path.exists(STRUCT_FILE):
        try:
            with open(STRUCT_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            # Migrer eldre filer som mangler sequences-nøkkel
            if 'sequences' not in d:
                d['sequences'] = []
            return d
        except Exception as e:
            logging.error('Feil ved lasting av structure.json: %s', e)
    import copy
    return copy.deepcopy(DEFAULT_STRUCT)

def save_struct(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(STRUCT_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
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
    PIL/Pillow-basert tegneflate, vist via Kivy Texture.

    VIKTIG: bruker 'draw_color' (ikke 'color') fordi Kivy Image
    har en innebygd 'color'-egenskap som styrer bilde-tint (RGBA).
    Hvis vi hadde brukt 'self.color' ville hele lerretsbildet fått
    endret farge ved hvert fargevalg, og PIL-koden ville lest feil verdi.

    Koordinatsystem:
      Kivy: origo nederst-venstre
      PIL:  origo øverst-venstre
    Konvertering i _kv2pil().

    Verktøy: pen, eraser, line, rect, ellipse, fill
    """

    def __init__(self, **kw):
        super().__init__(allow_stretch=True, keep_ratio=False, **kw)
        self._pil       = PILImage.new('RGB', (CANVAS_W, CANVAS_H), (255, 255, 255))
        self._base      = None   # Snapshot for rubber-band-tegning
        self._prev      = None   # Forrige touch-punkt (freehand)
        self._start     = None   # Startpunkt for shape-verktøy
        self.tool       = 'pen'
        self.draw_color = '#000000'  # Tegnefargen (IKKE Image.color!)
        self.size_px    = 6
        self._history   = []   # Angre-bunke (PIL-kopier)
        self._redo      = []   # Gjenta-bunke
        self._MAX_HIST  = 20
        self._refresh()

    # ── Koordinater ───────────────────────────────────────────────

    def _kv2pil(self, kx, ky):
        """
        Konverterer Kivy-touch-koordinater til PIL-pikselkoordinater.
        Returnerer (0,0) og logger en advarsel hvis widgeten ennå
        ikke har fått sin endelige størrelse (divisjon-med-null-vern).
        """
        if self.width == 0 or self.height == 0:
            logging.warning('_kv2pil: width=%s height=%s – canvas ikke layoutet ennå', self.width, self.height)
            return (0, 0)
        px = int((kx - self.x) / self.width  * CANVAS_W)
        py = int((1.0 - (ky - self.y) / self.height) * CANVAS_H)
        return (
            max(0, min(CANVAS_W - 1, px)),
            max(0, min(CANVAS_H - 1, py)),
        )

    # ── Teksturoppdatering ─────────────────────────────────────────

    def _refresh(self):
        """Konverterer PIL-bildet til en Kivy-tekstur og oppdaterer widgeten."""
        if not PIL_OK:
            return
        try:
            raw = self._pil.convert('RGBA').tobytes()
            tex = Texture.create(size=(CANVAS_W, CANVAS_H), colorfmt='rgba')
            tex.blit_buffer(raw, colorfmt='rgba', bufferfmt='ubyte')
            tex.flip_vertical()
            self.texture = tex
        except Exception:
            logging.exception('_refresh: feil ved teksturoppdatering')

    # ── Touch-hendelser ────────────────────────────────────────────

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        try:
            pt = self._kv2pil(*touch.pos)
            self._start = pt
            self._prev  = pt
            if self.tool == 'fill':
                self._push_history()
                self._do_fill(pt)
                self._refresh()
            elif self.tool in ('pen', 'eraser'):
                self._push_history()
                self._draw_dot(pt)
                self._refresh()
            elif self.tool in ('line', 'rect', 'ellipse'):
                self._push_history()
                self._base = self._pil.copy()
        except Exception:
            logging.exception('on_touch_down: PIL-feil')
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        try:
            pt = self._kv2pil(*touch.pos)
            if self.tool in ('pen', 'eraser'):
                if self._prev:
                    self._draw_seg(self._prev, pt)
                self._prev = pt
                self._refresh()
            elif self.tool in ('line', 'rect', 'ellipse') and self._base:
                self._pil = self._base.copy()
                self._draw_shape(self._start, pt)
                self._refresh()
        except Exception:
            logging.exception('on_touch_move: PIL-feil')
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        try:
            pt = self._kv2pil(*touch.pos)
            if self.tool in ('line', 'rect', 'ellipse') and self._base:
                self._pil = self._base.copy()
                self._draw_shape(self._start, pt)
                self._refresh()
                self._base = None
        except Exception:
            logging.exception('on_touch_up: PIL-feil')
        self._start = None
        self._prev  = None
        return True

    # ── PIL-primitiver ─────────────────────────────────────────────

    def _col(self):
        """Returnerer gjeldende farge som PIL RGB-tuple."""
        return (255, 255, 255) if self.tool == 'eraser' else hex_p(self.draw_color)

    def _draw_dot(self, pt):
        d = ImageDraw.Draw(self._pil)
        r = max(1, self.size_px // 2)
        x, y = pt
        d.ellipse([x - r, y - r, x + r, y + r], fill=self._col())

    def _draw_seg(self, p1, p2):
        d = ImageDraw.Draw(self._pil)
        d.line([p1, p2], fill=self._col(), width=max(1, self.size_px))

    def _draw_shape(self, p1, p2):
        if not p1 or not p2:
            return
        d = ImageDraw.Draw(self._pil)
        x0, y0 = min(p1[0], p2[0]), min(p1[1], p2[1])
        x1, y1 = max(p1[0], p2[0]), max(p1[1], p2[1])
        c = hex_p(self.draw_color)
        w = max(1, self.size_px)
        if self.tool == 'line':
            d.line([p1, p2], fill=c, width=w)
        elif self.tool == 'rect':
            d.rectangle([x0, y0, x1, y1], outline=c, width=w)
        elif self.tool == 'ellipse':
            d.ellipse([x0, y0, x1, y1], outline=c, width=w)

    def _do_fill(self, pt):
        """
        Floodfill (malingsspann): fyller sammenhengende fargeomraade
        fra touch-punktet med gjeldende draw_color.
        thresh=30 gir toleranse for anti-aliasede kanter.
        """
        try:
            ImageDraw.floodfill(
                self._pil, pt,
                hex_p(self.draw_color),
                thresh=30,
            )
        except Exception:
            logging.exception('_do_fill: floodfill-feil')

    # ── Offentlige metoder ─────────────────────────────────────────

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
            logging.exception('load_from: feil ved bildeopplasting')

    # ── Angre / Gjenta ─────────────────────────────────────────────

    def _push_history(self):
        """
        Lagrer en kopi av gjeldende PIL-bilde til angre-bunken.
        Kalles FØR en destruktiv operasjon starter.
        Tømmer gjenta-bunken (ny handling gjør gjenta ugyldig).
        """
        self._history.append(self._pil.copy())
        if len(self._history) > self._MAX_HIST:
            self._history.pop(0)
        self._redo.clear()

    def angre(self, *_):
        """Angrer siste handling (Ctrl+Z-ekvivalent)."""
        if not self._history:
            logging.debug('angre: tom historikk')
            return
        self._redo.append(self._pil.copy())
        self._pil = self._history.pop()
        self._refresh()
        logging.debug('angre: %d steg igjen i historikk', len(self._history))

    def gjenta(self, *_):
        """Gjentar sist angret handling."""
        if not self._redo:
            logging.debug('gjenta: tom gjenta-bunke')
            return
        self._history.append(self._pil.copy())
        self._pil = self._redo.pop()
        self._refresh()
        logging.debug('gjenta: %d steg igjen i gjenta-bunke', len(self._redo))


# ══════════════════════════════════════════════════════════════════
#  HOVED-APP
# ══════════════════════════════════════════════════════════════════

class KommunikasjonstavleApp(App):

    # ── Oppstart ──────────────────────────────────────────────────

    def build(self):
        setup_logging()
        Window.clearcolor = (0.95, 0.96, 0.98, 1)

        for d in [DATA_DIR, IMG_DIR, DRAW_DIR, DOWNLOAD_DIR]:
            os.makedirs(d, exist_ok=True)

        self.data        = load_struct()
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
        return root

    # ══════════════════════════════════════════════════
    #  ANDROID-TILLATELSER
    #
    #  Android 6+ (API 23+) krever at "farlige" tillatelser
    #  (lagring, kamera, …) bes om eksplisitt under kjøring,
    #  selv om de er deklarert i AndroidManifest.xml.
    #  Uten dette vil FileChooser vise mapper men ingen filer.
    #
    #  For Android 11+ (API 30+) trengs i tillegg
    #  MANAGE_EXTERNAL_STORAGE for å lese/skrive til /sdcard
    #  utenfor appens private mappe. Dette åpner en Settings-side
    #  der brukeren aktiverer tilgang manuelt.
    # ══════════════════════════════════════════════════

    def on_start(self):
        """Ber om Android-lagringstillatelser straks appen er klar."""
        if platform == 'android':
            Clock.schedule_once(lambda *_: self._request_android_permissions(), 0.5)

    def _request_android_permissions(self):
        """
        Trinn 1: Be om READ_EXTERNAL_STORAGE / WRITE_EXTERNAL_STORAGE
                 og READ_MEDIA_IMAGES (Android 13+) via standard dialog.
        Trinn 2: Be om MANAGE_EXTERNAL_STORAGE via Settings-intent
                 (Android 11+) – nødvendig for full /sdcard-tilgang.
        """
        try:
            from android.permissions import (
                request_permissions, check_permission, Permission,
            )
            perms = [
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
            # READ_MEDIA_IMAGES ble innført i API 33 (Android 13)
            try:
                perms.append(Permission.READ_MEDIA_IMAGES)
            except AttributeError:
                logging.info('READ_MEDIA_IMAGES ikke tilgjengelig (eldre API).')

            # Sjekk om tillatelsene allerede er innvilget
            missing = [p for p in perms if not check_permission(p)]
            if missing:
                request_permissions(missing, self._on_permissions_result)
                logging.info('Forespor tillatelser: %s', missing)
            else:
                logging.info('Alle lagringstillatelser allerede innvilget.')

        except Exception:
            logging.exception('_request_android_permissions: feil')

        # Separat forespørsel om MANAGE_EXTERNAL_STORAGE (Android 11+)
        Clock.schedule_once(lambda *_: self._request_manage_storage(), 1.5)

    def _request_manage_storage(self):
        """
        MANAGE_EXTERNAL_STORAGE kan ikke bes om via vanlig dialog.
        I stedet åpnes Android Settings-siden for appen, der brukeren
        selv skrur på "Tillat tilgang til alle filer".
        Kalles bare på Android 11+ (API 30+) hvis tillatelsen mangler.
        """
        try:
            from jnius import autoclass
            from android import mActivity

            VersionClass = autoclass('android.os.Build$VERSION')
            if VersionClass.SDK_INT < 30:
                logging.info('MANAGE_EXTERNAL_STORAGE: ikke nødvendig (API < 30).')
                return

            Environment = autoclass('android.os.Environment')
            if Environment.isExternalStorageManager():
                logging.info('MANAGE_EXTERNAL_STORAGE: allerede innvilget.')
                return

            # Åpne Settings-siden for denne appen
            Intent   = autoclass('android.content.Intent')
            Uri      = autoclass('android.net.Uri')
            Settings = autoclass('android.provider.Settings')

            intent = Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION
            )
            pkg_uri = Uri.parse(
                'package:' + mActivity.getPackageName()
            )
            intent.setData(pkg_uri)
            mActivity.startActivity(intent)
            logging.info('MANAGE_EXTERNAL_STORAGE: Settings-intent startet.')

        except Exception:
            logging.exception('_request_manage_storage: feil')

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
            '<  Bak', hex_k('#4D96FF'), fs=13,
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
        Bunnbar med app-tittel / konteksttittel.
        Flyttes hit fra navbaren slik at tittelen ikke
        konkurrerer med navigasjonsknappene oppe.
        """
        bar = BottomBar(
            size_hint_y=None, height=dp(40),
            padding=(dp(8), dp(4)),
        )
        self._lbl_title = Label(
            text=APP_TITLE, bold=True, font_size=sp(16),
            color=(0.08, 0.10, 0.35, 1),
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

    def _set_content(self, widget):
        self._content.clear_widgets()
        self._content.add_widget(widget)

    # ══════════════════════════════════════════════════
    #  HJEMSKJERM
    # ══════════════════════════════════════════════════

    def _show_home(self, **_):
        self._cur_scr   = 'home'
        self.cur_folder = None
        self._set_title(APP_TITLE)

        outer = BoxLayout(
            orientation='vertical',
            spacing=dp(10), padding=dp(12),
        )

        # Handlingsrekker-knapp alltid synlig øverst
        outer.add_widget(mk_btn(
            'Handlingsrekker',
            hex_k('#4ECDC4'),
            h=dp(56), fs=16,
            cb=lambda *_: self._nav_sequences(),
        ))

        if self.edit_mode:
            outer.add_widget(mk_btn(
                '+  Legg til mappe', hex_k('#6BCB77'), h=dp(52),
                cb=lambda *_: self._folder_popup(None),
            ))

        grid = GridLayout(cols=2, spacing=dp(14), padding=(dp(6), dp(8)), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for fo in self.data['folders']:
            grid.add_widget(self._make_folder_tile(fo))

        sv = ScrollView()
        sv.add_widget(grid)
        outer.add_widget(sv)
        self._set_content(outer)

    def _make_folder_tile(self, fo):
        has_img = bool(fo.get('image') and os.path.exists(fo['image']))
        edit    = self.edit_mode

        TILE_H  = dp(200) if edit else dp(168)
        IMG_H   = dp(100)
        LBL_H   = dp(56)
        DEL_H   = dp(40)

        if edit:
            tap = lambda f=fo: self._folder_popup(f)
        else:
            tap = lambda f=fo: self._open_folder(f)

        cell = RBox(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=dp(4),
            padding=(dp(4), dp(4)),
            box_color=(1.0, 1.0, 1.0, 1.0),
            radius=dp(18),
        )

        if has_img:
            cell.add_widget(TappableImage(
                tap, source=fo['image'],
                size_hint=(1, None), height=IMG_H,
                allow_stretch=True, keep_ratio=True,
            ))

        lbl_h = LBL_H if has_img else (dp(155) if not edit else dp(115))
        btn = RBtn(
            text=fo['name'],
            size_hint=(1, None), height=lbl_h,
            btn_color=list(hex_k(fo['color'])),
            color=(0.05, 0.05, 0.2, 1),
            bold=True, font_size=sp(18),
            radius=dp(14),
        )
        btn.bind(on_release=lambda b, t=tap: t())
        cell.add_widget(btn)

        if edit:
            cell.add_widget(mk_btn(
                'Slett mappe', hex_k('#FF6B6B'), h=DEL_H, fs=13,
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
            btn_bar = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
            btn_bar.add_widget(mk_btn(
                '+  Nytt bilde', hex_k('#6BCB77'), h=dp(50),
                cb=lambda *_: self._item_popup(fo, None),
            ))
            btn_bar.add_widget(mk_btn(
                'Last opp', hex_k('#4D96FF'), h=dp(50),
                cb=lambda *_: self._upload_to_folder(fo),
            ))
            outer.add_widget(btn_bar)

        grid = GridLayout(cols=3, spacing=dp(12), padding=(dp(6), dp(8)), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for it in fo['items']:
            grid.add_widget(self._make_item_tile(fo, it))

        sv = ScrollView()
        sv.add_widget(grid)
        outer.add_widget(sv)
        self._set_content(outer)

    def _make_item_tile(self, fo, it):
        img_path = it.get('image') or ''
        has_img  = bool(img_path and os.path.exists(img_path))
        edit     = self.edit_mode

        TILE_H = dp(210) if edit else dp(166)
        IMG_H  = dp(116) if edit else dp(120)
        LBL_H  = dp(44)
        ACT_H  = dp(42)

        if edit:
            tap = lambda f=fo, i=it: self._item_popup(f, i)
        else:
            tap = lambda p=img_path, n=it['name']: self._show_image_full(p, n)

        cell = RBox(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=dp(4),
            padding=(dp(4), dp(4)),
            box_color=(1.0, 1.0, 1.0, 1.0),
            radius=dp(18),
        )

        if has_img:
            cell.add_widget(TappableImage(
                tap, source=img_path,
                size_hint=(1, None), height=IMG_H,
                allow_stretch=True, keep_ratio=True,
            ))

        lbl_h = LBL_H if has_img else (dp(158) if not edit else dp(118))
        btn = RBtn(
            text=it['name'],
            size_hint=(1, None), height=lbl_h,
            btn_color=list(hex_k('#4D96FF')),
            color=(1, 1, 1, 1), bold=True, font_size=sp(14),
            radius=dp(14),
        )
        btn.bind(on_release=lambda b: tap())
        cell.add_widget(btn)

        if edit:
            row = BoxLayout(size_hint_y=None, height=ACT_H, spacing=dp(4))
            row.add_widget(mk_btn(
                'Last ned', hex_k('#6BCB77'), h=ACT_H - dp(2), fs=13,
                cb=lambda *_, p=img_path: self._download_image(p),
            ))
            row.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=ACT_H - dp(2), fs=13,
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
        self._set_title(name)

        layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))

        # Bildet fyller tilgjengelig plass
        layout.add_widget(Image(
            source=path,
            allow_stretch=True, keep_ratio=True,
        ))

        # Etikett (bildets navn) rett under bildet
        name_lbl = Label(
            text=name,
            size_hint_y=None, height=dp(48),
            font_size=sp(20), bold=True,
            color=(0.08, 0.10, 0.35, 1),
            halign='center', valign='middle',
        )
        name_lbl.bind(size=name_lbl.setter('text_size'))
        layout.add_widget(name_lbl)

        layout.add_widget(mk_btn(
            'Last ned til enheten',
            hex_k('#6BCB77'), h=dp(54),
            cb=lambda *_: self._download_image(path),
        ))
        self._set_content(layout)

    # ══════════════════════════════════════════════════
    #  TEGNESKJERM
    # ══════════════════════════════════════════════════

    def _show_draw(self, **_):
        self._cur_scr = 'draw'
        self._set_title('Tegn')
        logging.info('Aapner tegneskjerm. PIL_OK=%s', PIL_OK)

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
        tool_grid = GridLayout(
            cols=6, size_hint_y=None, height=dp(56), spacing=dp(4),
        )
        tools = [
            ('pen',     'Penn'),
            ('eraser',  'Visk.'),
            ('line',    'Linje'),
            ('rect',    'Rekt.'),
            ('ellipse', 'Oval'),
            ('fill',    'Fyll'),
        ]
        self._tool_btns = {}
        for key, lbl in tools:
            b = RBtn(
                text=lbl,
                size_hint=(1, 1),
                font_size=sp(14),
                btn_color=list(hex_k(TOOL_COLORS[key])),
                color=(1, 1, 1, 1),
                bold=True,
                radius=dp(10),
            )
            b.bind(on_release=lambda btn, k=key: self._set_draw_tool(k))
            tool_grid.add_widget(b)
            self._tool_btns[key] = b
        root.add_widget(tool_grid)

        # ── Rad 2: Angre / Gjenta / Lagre / Tom ──────────────────
        act = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        act.add_widget(mk_btn(
            'Angre', hex_k('#546E7A'), h=dp(48), fs=14,
            cb=lambda *_: self.draw_canvas and self.draw_canvas.angre(),
        ))
        act.add_widget(mk_btn(
            'Gjenta', hex_k('#546E7A'), h=dp(48), fs=14,
            cb=lambda *_: self.draw_canvas and self.draw_canvas.gjenta(),
        ))
        act.add_widget(mk_btn(
            'Lagre', hex_k('#6BCB77'), h=dp(48), fs=14,
            cb=self._save_drawing,
        ))
        act.add_widget(mk_btn(
            'Tom', hex_k('#FF6B6B'), h=dp(48), fs=14,
            cb=lambda *_: self.draw_canvas.clear_canvas(),
        ))
        root.add_widget(act)

        # ── Rad 3: Penselstørrelse – egen rad, slider får full bredde ──
        # Slider trenger god plass og kan ikke dele rad med mange knapper.
        size_row = BoxLayout(
            size_hint_y=None, height=dp(54),
            spacing=dp(8), padding=(dp(6), dp(4)),
        )
        size_row.add_widget(Label(
            text='Penselstorrelse:', size_hint_x=None, width=dp(148),
            font_size=sp(14), bold=True,
            color=(0.10, 0.10, 0.10, 1), halign='left',
        ))
        self._size_slider = Slider(min=2, max=60, value=6, step=1)
        self._size_lbl    = Label(
            text=' 6 px', size_hint_x=None, width=dp(52),
            font_size=sp(14), color=(0.10, 0.10, 0.10, 1),
        )
        self._size_slider.bind(value=self._on_size_change)
        size_row.add_widget(self._size_slider)
        size_row.add_widget(self._size_lbl)
        root.add_widget(size_row)

        # ── Rad 4: Fargevalg – en knapp åpner fargevalgpopup ──────
        # Viser gjeldende farge som farget sirkel + knapp for å bytte.
        color_row = BoxLayout(
            size_hint_y=None, height=dp(56),
            spacing=dp(8), padding=(dp(4), dp(4)),
        )
        self._cur_color_btn = RBtn(
            size_hint=(None, None), size=(dp(48), dp(48)),
            btn_color=list(hex_k('#000000')),
            radius=dp(24),
        )
        self._cur_color_btn.bind(on_release=lambda *_: self._open_color_popup())
        color_row.add_widget(self._cur_color_btn)

        open_pal_btn = mk_btn(
            'Velg farge  (24 farger)', hex_k('#4D96FF'),
            h=dp(48), fs=14,
        )
        open_pal_btn.bind(on_release=lambda *_: self._open_color_popup())
        color_row.add_widget(open_pal_btn)
        root.add_widget(color_row)

        # Initialiserer _col_btns som tom dict (brukes i _set_draw_color)
        self._col_btns = {}

        # ── Tegneflate ─────────────────────────────────────────────
        self.draw_canvas = DrawCanvas()
        root.add_widget(self.draw_canvas)
        logging.info('DrawCanvas opprettet.')

        self._set_content(root)
        self._set_draw_tool('pen')
        self._set_draw_color('#000000')

    def _set_draw_tool(self, key):
        if self.draw_canvas:
            self.draw_canvas.tool = key
        for k, btn in self._tool_btns.items():
            btn.btn_color = list(hex_k(
                TOOL_ACTIVE[k] if k == key else TOOL_COLORS[k]
            ))
        logging.debug('Tegne-verktoy: %s', key)

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
        self._size_lbl.text = f'{int(val):2d} px' 

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
            cols=6, spacing=dp(8),
            size_hint_y=None,
        )
        grid.bind(minimum_height=grid.setter('height'))

        pop_ref = [None]
        self._col_btns = {}

        for col_hex in PALETTE:
            cb = RBtn(
                size_hint=(None, None),
                size=(dp(52), dp(52)),
                btn_color=list(hex_k(col_hex)),
                radius=dp(26),
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
            title='Farger', content=layout,
            size_hint=(0.92, 0.82),
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
                text='Ingen handlingsrekker ennaa.\nTrykk "Red." og "+" for aa lage en.',
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
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            row.add_widget(mk_btn(
                'Eksporter', hex_k('#FF9F43'), h=dp(38), fs=13,
                cb=lambda *_, s=seq: self._export_sequence(s),
            ))
            row.add_widget(mk_btn(
                'Slett', hex_k('#FF6B6B'), h=dp(38), fs=13,
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
                'Trykk pa bildet for aa avslutte'
                if is_last else
                'Trykk pa bildet for neste steg'
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
            self._toast('Ingen bilder aa eksportere.')
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
            text='Navn pa handlingsrekken:',
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
            self._toast('Ingen ASK-bilder funnet.\nLegg til bilder i mappene forst.')
            return

        pick_ref = [None]
        layout   = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
        layout.add_widget(Label(
            text='Trykk pa et bilde for aa legge det til i rekken:',
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
        """
        Åpner FileChooser for å laste opp et bilde direkte
        til handlingsrekken fra enheten.
        """
        fc_layout = BoxLayout(orientation='vertical', spacing=dp(8))
        fc = FileChooserListView(path='/sdcard', filters=[img_filter])
        fc_layout.add_widget(fc)

        btn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        pop_ref = [None]

        def on_upload(*_):
            if fc.selection:
                src_path = fc.selection[0]
                fname    = os.path.basename(src_path)
                dst      = os.path.join(IMG_DIR, fname)
                try:
                    shutil.copy2(src_path, dst)
                    name_sug = os.path.splitext(fname)[0].replace('_', ' ')
                    seq_items.append({
                        'id':    str(uuid.uuid4()),
                        'name':  name_sug,
                        'image': dst,
                    })
                    refresh_fn()
                    self._toast(f'Lagt til: {fname}')
                    logging.info('Sekvens: bilde lagt til fra enhet: %s', dst)
                except Exception:
                    logging.exception('_seq_pick_from_device: feil')
                    self._toast('Feil ved opplasting.')
            pop_ref[0].dismiss()

        btn_row.add_widget(mk_btn(
            'Legg til i rekken', hex_k('#6BCB77'), h=dp(52), cb=on_upload,
        ))
        btn_row.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(52),
            cb=lambda *_: pop_ref[0].dismiss(),
        ))
        fc_layout.add_widget(btn_row)

        pop = Popup(
            title='Last opp til handlingsrekke',
            content=fc_layout, size_hint=(0.97, 0.93),
        )
        pop_ref[0] = pop
        pop.open()

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
        col_row      = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        col_btns     = []
        for c in FOLDER_COLORS:
            cb = RBtn(
                btn_color=list(hex_k(c)),
                size_hint=(None, None), size=(dp(54), dp(54)),
                opacity=1.0 if chosen_color[0] == c else 0.5,
                radius=dp(27),
            )
            def pick(b, col=c, btns=col_btns, sel=chosen_color):
                sel[0] = col
                for x in btns:
                    x.opacity = 0.5
                b.opacity = 1.0
            cb.bind(on_release=pick)
            col_row.add_widget(cb)
            col_btns.append(cb)
        layout.add_widget(col_row)

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
            chosen_img, img_lbl, pop_ref[0]))
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
        new    = it is None
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

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

        chosen_img = [it.get('image') if it else None]
        img_lbl = Label(
            text='Bilde: ' + (os.path.basename(chosen_img[0]) if chosen_img[0] else 'ingen'),
            size_hint_y=None, height=dp(28),
            font_size=sp(13), color=(0.3, 0.3, 0.3, 1),
        )
        layout.add_widget(img_lbl)

        pop_ref = [None]
        pick_btn = mk_btn('Velg ASK-bilde fra enhet', hex_k('#4D96FF'), h=dp(48))
        pick_btn.bind(on_release=lambda *_: self._pick_image(
            chosen_img, img_lbl, pop_ref[0]))
        layout.add_widget(pick_btn)

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

        pop = Popup(
            title='Nytt ASK-bilde' if new else 'Rediger ASK-bilde',
            content=layout, size_hint=(0.93, 0.82),
        )
        pop_ref[0] = pop
        pop.open()

    def _del_item(self, fo, it):
        fo['items'] = [i for i in fo['items'] if i['id'] != it['id']]
        save_struct(self.data)
        self._show_folder(fid=fo['id'])

    # ══════════════════════════════════════════════════
    #  BILDE – LAST OPP / LAST NED
    # ══════════════════════════════════════════════════

    def _pick_image(self, chosen_img_ref, label_widget, parent_popup=None):
        fc_layout = BoxLayout(orientation='vertical', spacing=dp(8))
        fc = FileChooserListView(
            path='/sdcard',
            filters=[img_filter],
        )
        fc_layout.add_widget(fc)

        btn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))

        def on_select(*_):
            if fc.selection:
                src   = fc.selection[0]
                fname = os.path.basename(src)
                dst   = os.path.join(IMG_DIR, fname)
                try:
                    shutil.copy2(src, dst)
                    chosen_img_ref[0] = dst
                    label_widget.text = 'Bilde: ' + fname
                    logging.info('Bilde kopiert: %s', dst)
                except Exception:
                    logging.exception('_pick_image: kopieringsfeil')
                    self._toast('Feil ved kopiering av bilde.')
            fc_pop.dismiss()

        btn_row.add_widget(mk_btn('Velg dette bildet', hex_k('#6BCB77'), h=dp(52), cb=on_select))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(52),
                                   cb=lambda *_: fc_pop.dismiss()))
        fc_layout.add_widget(btn_row)

        fc_pop = Popup(
            title='Velg bildefil', content=fc_layout,
            size_hint=(0.97, 0.93),
        )
        fc_pop.open()

    def _upload_to_folder(self, fo):
        fc_layout = BoxLayout(orientation='vertical', spacing=dp(8))
        fc = FileChooserListView(
            path='/sdcard',
            filters=[img_filter],
        )
        fc_layout.add_widget(fc)

        btn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))

        def on_upload(*_):
            if fc.selection:
                src   = fc.selection[0]
                fname = os.path.basename(src)
                dst   = os.path.join(IMG_DIR, fname)
                try:
                    shutil.copy2(src, dst)
                    name_suggestion = os.path.splitext(fname)[0].replace('_', ' ')
                    fo['items'].append({
                        'id':    str(uuid.uuid4()),
                        'name':  name_suggestion,
                        'image': dst,
                    })
                    save_struct(self.data)
                    pop.dismiss()
                    self._toast(f'Lagt til:\n{fname}')
                    self._show_folder(fid=fo['id'])
                    logging.info('Bilde lastet opp til mappe: %s', fname)
                except Exception:
                    logging.exception('_upload_to_folder: feil')
                    self._toast('Feil ved opplasting.')
            else:
                pop.dismiss()

        btn_row.add_widget(mk_btn('Last opp til mappe', hex_k('#4D96FF'), h=dp(52), cb=on_upload))
        btn_row.add_widget(mk_btn('Avbryt', hex_k('#9CA3AF'), h=dp(52),
                                   cb=lambda *_: pop.dismiss()))
        fc_layout.add_widget(btn_row)

        pop = Popup(
            title=f'Last opp til «{fo["name"]}»',
            content=fc_layout, size_hint=(0.97, 0.93),
        )
        pop.open()

    def _download_image(self, src_path):
        if not src_path or not os.path.exists(src_path):
            self._toast('Ingen bildefil aa laste ned.')
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
            text=msg, font_size=sp(15), color=(1, 1, 1, 1),
            halign='center', valign='middle',
        )
        lbl.bind(size=lbl.setter('text_size'))
        pop = Popup(
            title='', content=lbl,
            size_hint=(0.78, 0.22),
            background_color=(0.08, 0.08, 0.08, 0.93),
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
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write('\n=== FATAL KRASJ ===\n')
                _tb.print_exc(file=f)
        except Exception:
            pass
        raise
