#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kommunikasjonstavle v1.1
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

try:
    from PIL import Image as PILImage, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

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

CANVAS_W = 1280
CANVAS_H = 960

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
PALETTE = [
    '#000000', '#FFFFFF', '#EF5350', '#FF7043',
    '#FFD600', '#43A047', '#1E88E5', '#8E24AA',
    '#EC407A', '#6D4C41', '#78909C', '#00ACC1',
]

DEFAULT_STRUCT = {
    "folders": [
        {"id": "f1", "name": "Mat og drikke", "color": "#FFD93D", "image": None, "items": []},
        {"id": "f2", "name": "Aktiviteter",   "color": "#6BCB77", "image": None, "items": []},
        {"id": "f3", "name": "Foelelser",     "color": "#4D96FF", "image": None, "items": []},
        {"id": "f4", "name": "Kropp",         "color": "#FF6B6B", "image": None, "items": []},
        {"id": "f5", "name": "Klaer",         "color": "#C77DFF", "image": None, "items": []},
        {"id": "f6", "name": "Transport",     "color": "#FF9F43", "image": None, "items": []},
    ]
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
    logging.info('Kommunikasjonstavle v1.1 starter. PIL_OK=%s', PIL_OK)


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
    """Lager en farget Kivy-knapp uten bakgrunnsbilde."""
    b = Button(
        text=text, size_hint_y=None, height=h,
        font_size=sp(fs), background_normal='',
        background_color=bg, color=fg, bold=True, **kw,
    )
    if cb:
        b.bind(on_release=cb)
    return b

def load_struct():
    if os.path.exists(STRUCT_FILE):
        try:
            with open(STRUCT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
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
                self._do_fill(pt)
                self._refresh()
            elif self.tool in ('pen', 'eraser'):
                self._draw_dot(pt)
                self._refresh()
            elif self.tool in ('line', 'rect', 'ellipse'):
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

        self._show_home()
        return root

    # ══════════════════════════════════════════════════
    #  NAVIGASJONSBAR
    # ══════════════════════════════════════════════════

    def _build_navbar(self):
        """
        Navigasjonsbar med tekstknapper (ingen emojier – Android
        mangler emoji-fonter i Kivy-kontekst).
        """
        bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None, height=dp(62),
            padding=(dp(4), dp(4)),
            spacing=dp(4),
        )

        # btn_kw innehar size_hint_y og height – send IKKE h= til mk_btn i tillegg.
        btn_kw = dict(
            size_hint_x=None, width=dp(72),
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
        self._lbl_title = Label(
            text=APP_TITLE, bold=True, font_size=sp(17),
            color=(0.08, 0.10, 0.35, 1),
        )
        self._btn_draw = mk_btn(
            'Tegn', hex_k('#FF9F43'), fs=13,
            cb=self.go_draw, **btn_kw,
        )
        self._btn_edit = mk_btn(
            'Red.', hex_k('#C77DFF'), fs=13,
            cb=self.toggle_edit, **btn_kw,
        )

        for w in [self._btn_back, self._btn_home, self._lbl_title,
                  self._btn_draw, self._btn_edit]:
            bar.add_widget(w)
        return bar

    def _set_title(self, t):
        self._lbl_title.text = t

    def _set_edit_highlight(self, on):
        self._btn_edit.background_color = hex_k('#7B2FBE' if on else '#C77DFF')

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

        if self.edit_mode:
            outer.add_widget(mk_btn(
                '+  Legg til mappe', hex_k('#6BCB77'), h=dp(52),
                cb=lambda *_: self._folder_popup(None),
            ))

        grid = GridLayout(cols=2, spacing=dp(12), size_hint_y=None)
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

        cell = BoxLayout(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=dp(4),
        )

        if has_img:
            cell.add_widget(TappableImage(
                tap, source=fo['image'],
                size_hint=(1, None), height=IMG_H,
                allow_stretch=True, keep_ratio=True,
            ))

        lbl_h = LBL_H if has_img else (dp(155) if not edit else dp(115))
        btn = Button(
            text=fo['name'],
            size_hint=(1, None), height=lbl_h,
            background_normal='',
            background_color=hex_k(fo['color']),
            color=(0.05, 0.05, 0.2, 1),
            bold=True, font_size=sp(18),
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

        grid = GridLayout(cols=3, spacing=dp(10), size_hint_y=None)
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

        cell = BoxLayout(
            orientation='vertical',
            size_hint_y=None, height=TILE_H,
            spacing=dp(4),
        )

        if has_img:
            cell.add_widget(TappableImage(
                tap, source=img_path,
                size_hint=(1, None), height=IMG_H,
                allow_stretch=True, keep_ratio=True,
            ))

        lbl_h = LBL_H if has_img else (dp(158) if not edit else dp(118))
        btn = Button(
            text=it['name'],
            size_hint=(1, None), height=lbl_h,
            background_normal='',
            background_color=hex_k('#4D96FF'),
            color=(1, 1, 1, 1), bold=True, font_size=sp(14),
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

        layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        layout.add_widget(Image(
            source=path,
            allow_stretch=True, keep_ratio=True,
        ))
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
            b = Button(
                text=lbl,
                size_hint=(1, 1),
                font_size=sp(14),
                background_normal='',
                background_color=hex_k(TOOL_COLORS[key]),
                color=(1, 1, 1, 1),
                bold=True,
            )
            b.bind(on_release=lambda btn, k=key: self._set_draw_tool(k))
            tool_grid.add_widget(b)
            self._tool_btns[key] = b
        root.add_widget(tool_grid)

        # ── Rad 2: Penselstørrelse + Lagre/Tøm ────────────────────
        ctrl = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        ctrl.add_widget(Label(
            text='Str.:', size_hint_x=None, width=dp(38),
            font_size=sp(13), color=(0.08, 0.08, 0.08, 1),
        ))
        self._size_slider = Slider(min=2, max=60, value=6, step=1)
        self._size_lbl    = Label(
            text='6', size_hint_x=None, width=dp(34),
            font_size=sp(13), color=(0.08, 0.08, 0.08, 1),
        )
        self._size_slider.bind(value=self._on_size_change)
        ctrl.add_widget(self._size_slider)
        ctrl.add_widget(self._size_lbl)
        ctrl.add_widget(mk_btn(
            'Lagre', hex_k('#6BCB77'), h=dp(46), fs=13,
            size_hint_x=None, width=dp(84),
            cb=self._save_drawing,
        ))
        ctrl.add_widget(mk_btn(
            'Tom', hex_k('#FF6B6B'), h=dp(46), fs=13,
            size_hint_x=None, width=dp(72),
            cb=lambda *_: self.draw_canvas.clear_canvas(),
        ))
        root.add_widget(ctrl)

        # ── Rad 3: Fargepalett (horisontal rullefelt) ─────────────
        pal_sv = ScrollView(
            size_hint_y=None, height=dp(58),
            do_scroll_x=True, do_scroll_y=False,
        )
        pal_inner = BoxLayout(
            orientation='horizontal',
            size_hint_x=None, height=dp(54),
            spacing=dp(6), padding=(dp(4), dp(4)),
        )
        pal_inner.bind(minimum_width=pal_inner.setter('width'))

        self._col_btns = {}
        for col_hex in PALETTE:
            cb = Button(
                size_hint=(None, None),
                size=(dp(46), dp(46)),
                background_normal='',
                background_color=hex_k(col_hex),
            )
            cb.bind(on_release=lambda b, c=col_hex: self._set_draw_color(c))
            pal_inner.add_widget(cb)
            self._col_btns[col_hex] = cb

        pal_sv.add_widget(pal_inner)
        root.add_widget(pal_sv)

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
            btn.background_color = hex_k(
                TOOL_ACTIVE[k] if k == key else TOOL_COLORS[k]
            )
        logging.debug('Tegne-verktoy: %s', key)

    def _set_draw_color(self, col):
        """
        Oppdaterer draw_color paa DrawCanvas.
        VIKTIG: setter draw_canvas.draw_color, IKKE draw_canvas.color.
        draw_canvas.color er Kivy Image sin tint-RGBA og maa ikke roeres.
        """
        if self.draw_canvas:
            self.draw_canvas.draw_color = col
        for h, btn in self._col_btns.items():
            if h == col:
                # Lyser opp valgt farge litt
                r, g, b, _ = hex_k(h)
                btn.background_color = (
                    min(r + 0.28, 1),
                    min(g + 0.28, 1),
                    min(b + 0.28, 1), 1,
                )
            else:
                btn.background_color = hex_k(h)

    def _on_size_change(self, slider, val):
        if self.draw_canvas:
            self.draw_canvas.size_px = int(val)
        self._size_lbl.text = str(int(val))

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
            cb = Button(
                background_normal='', background_color=hex_k(c),
                size_hint=(None, None), size=(dp(54), dp(54)),
                opacity=1.0 if chosen_color[0] == c else 0.5,
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
            filters=['*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp'],
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
            filters=['*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp'],
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
