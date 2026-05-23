#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kommunikasjonstavle
ASK-kommunikasjonsapp for barnehage og skole
Python 3 / Kivy 2.3.0  –  Buildozer / Android

Arkitektur:
  - Ingen ScreenManager; innholdsflaten bygges om ved navigasjon (på forespørsel)
  - Ingen egne canvas-operasjoner i UI-widget (jf. Eldritch Portal-arkitektur)
  - Tegning via PIL/Pillow, vist som Kivy Image-tekstur
  - Data lagret i /sdcard/Documents/Kommunikasjonstavle/structure.json
  - Bilder i /sdcard/Documents/Kommunikasjonstavle/images/
  - Tegninger i /sdcard/Documents/Kommunikasjonstavle/drawings/
"""

import os
import json
import uuid
import shutil
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
DOWNLOAD_DIR = '/sdcard/Download'

# Tegne-canvas oppløsning
CANVAS_W = 1280
CANVAS_H = 960

# Fargepalett for mapper
FOLDER_COLORS = [
    '#FFD93D', '#FF6B6B', '#6BCB77', '#4D96FF',
    '#C77DFF', '#FF9F43', '#4ECDC4', '#FF6BB5',
]

# Tegne-verktøy: farge → Kivy hex
TOOL_COLORS = {
    'pen':     '#4D96FF',
    'eraser':  '#9CA3AF',
    'line':    '#228B22',
    'rect':    '#FF9F43',
    'ellipse': '#FF69B4',
    'fill':    '#7B2FBE',
}
TOOL_ACTIVE = {
    'pen':     '#1a5ccc',
    'eraser':  '#444444',
    'line':    '#145214',
    'rect':    '#b36800',
    'ellipse': '#b00066',
    'fill':    '#4a0077',
}

# Fargepalett for tegning
PALETTE = [
    '#000000', '#FFFFFF', '#FF0000', '#FF8C00',
    '#FFD700', '#228B22', '#1E90FF', '#8B008B',
    '#FF69B4', '#8B4513', '#808080', '#00CED1',
]

# Standard mappestruktur ved første oppstart
DEFAULT_STRUCT = {
    "folders": [
        {"id": "f1", "name": "Mat og drikke", "color": "#FFD93D", "image": None, "items": []},
        {"id": "f2", "name": "Aktiviteter",   "color": "#6BCB77", "image": None, "items": []},
        {"id": "f3", "name": "Følelser",      "color": "#4D96FF", "image": None, "items": []},
        {"id": "f4", "name": "Kropp",         "color": "#FF6B6B", "image": None, "items": []},
        {"id": "f5", "name": "Klær",          "color": "#C77DFF", "image": None, "items": []},
        {"id": "f6", "name": "Transport",     "color": "#FF9F43", "image": None, "items": []},
    ]
}

# ══════════════════════════════════════════════════════════════════
#  HJELPERE
# ══════════════════════════════════════════════════════════════════

def hex_k(h):
    """Hex-farge (#RRGGBB) → Kivy RGBA-tuple (0–1-skala)."""
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4)) + (1,)

def hex_p(h):
    """Hex-farge (#RRGGBB) → PIL RGB-tuple (0–255)."""
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def mk_btn(text, bg, fg=(1, 1, 1, 1), fs=16, h=dp(56), cb=None, **kw):
    """Lager en flat farget knapp med tekst."""
    b = Button(
        text=text, size_hint_y=None, height=h,
        font_size=sp(fs), background_normal='',
        background_color=bg, color=fg, bold=True, **kw,
    )
    if cb:
        b.bind(on_release=cb)
    return b

def load_struct():
    """Leser structure.json, faller tilbake til standard hvis mangler/ugyldig."""
    if os.path.exists(STRUCT_FILE):
        try:
            with open(STRUCT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    import copy
    return copy.deepcopy(DEFAULT_STRUCT)

def save_struct(d):
    """Skriver structure.json til disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STRUCT_FILE, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def get_folder(d, fid):
    """Returnerer mappeobjekt med gitt id, eller None."""
    return next((x for x in d['folders'] if x['id'] == fid), None)

# ══════════════════════════════════════════════════════════════════
#  WIDGET: TRYKKBART BILDE
# ══════════════════════════════════════════════════════════════════

class TappableImage(Image):
    """
    Image-widget som utfører en handling ved touch.
    Brukes for ASK-bilder og mappebilder som skal kunne trykkes på.
    """
    def __init__(self, action, **kw):
        super().__init__(**kw)
        self._action = action

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._action()
            return True
        return super().on_touch_down(touch)

# ══════════════════════════════════════════════════════════════════
#  WIDGET: TEGNE-CANVAS (PIL-basert)
# ══════════════════════════════════════════════════════════════════

class DrawCanvas(Image):
    """
    Tegne-canvas implementert med PIL/Pillow.
    Vises som Kivy Image-widget via Texture.

    Koordinatsystem:
      Kivy: (0,0) = nederst-venstre
      PIL:  (0,0) = øverst-venstre
    Konvertering håndteres i _kv2pil().

    Verktøy: pen, eraser, line, rect, ellipse, fill
    """
    def __init__(self, **kw):
        super().__init__(allow_stretch=True, keep_ratio=False, **kw)
        self._pil    = PILImage.new('RGB', (CANVAS_W, CANVAS_H), (255, 255, 255))
        self._base   = None   # Kopi av canvas før shape-tegning starter (rubber-band)
        self._prev   = None   # Forrige touch-punkt (freehand-linje)
        self._start  = None   # Startpunkt for shape-verktøy
        self.tool    = 'pen'
        self.color   = '#000000'
        self.size_px = 6
        self._refresh()

    # ── Koordinat-konvertering ────────────────────────────────────

    def _kv2pil(self, kx, ky):
        """Kivy touch-koordinater → PIL piksel-koordinater."""
        px = int((kx - self.x) / self.width  * CANVAS_W)
        py = int((1.0 - (ky - self.y) / self.height) * CANVAS_H)
        return (max(0, min(CANVAS_W - 1, px)),
                max(0, min(CANVAS_H - 1, py)))

    # ── Oppdater Kivy-tekstur ─────────────────────────────────────

    def _refresh(self):
        """Konverterer PIL-bilde til Kivy-tekstur og oppdaterer widget."""
        if not PIL_OK:
            return
        raw = self._pil.convert('RGBA').tobytes()
        tex = Texture.create(size=(CANVAS_W, CANVAS_H), colorfmt='rgba')
        tex.blit_buffer(raw, colorfmt='rgba', bufferfmt='ubyte')
        tex.flip_vertical()
        self.texture = tex

    # ── Touch-hendelser ───────────────────────────────────────────

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
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
            self._base = self._pil.copy()   # Snapshot for rubber-band
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        pt = self._kv2pil(*touch.pos)

        if self.tool in ('pen', 'eraser'):
            if self._prev:
                self._draw_seg(self._prev, pt)
            self._prev = pt
            self._refresh()
        elif self.tool in ('line', 'rect', 'ellipse') and self._base:
            # Gjenopprett snapshot og tegn oppdatert shape (rubber-band)
            self._pil = self._base.copy()
            self._draw_shape(self._start, pt)
            self._refresh()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        pt = self._kv2pil(*touch.pos)

        if self.tool in ('line', 'rect', 'ellipse') and self._base:
            self._pil = self._base.copy()
            self._draw_shape(self._start, pt)
            self._refresh()
            self._base = None

        self._start = None
        self._prev  = None
        return True

    # ── PIL-tegne-primitiver ──────────────────────────────────────

    def _col(self):
        return (255, 255, 255) if self.tool == 'eraser' else hex_p(self.color)

    def _draw_dot(self, pt):
        d = ImageDraw.Draw(self._pil)
        r = self.size_px // 2
        x, y = pt
        d.ellipse([x - r, y - r, x + r, y + r], fill=self._col())

    def _draw_seg(self, p1, p2):
        d = ImageDraw.Draw(self._pil)
        d.line([p1, p2], fill=self._col(), width=self.size_px)

    def _draw_shape(self, p1, p2):
        d = ImageDraw.Draw(self._pil)
        x0, y0 = min(p1[0], p2[0]), min(p1[1], p2[1])
        x1, y1 = max(p1[0], p2[0]), max(p1[1], p2[1])
        c = hex_p(self.color)
        w = self.size_px
        if self.tool == 'line':
            d.line([p1, p2], fill=c, width=w)
        elif self.tool == 'rect':
            d.rectangle([x0, y0, x1, y1], outline=c, width=w)
        elif self.tool == 'ellipse':
            d.ellipse([x0, y0, x1, y1], outline=c, width=w)

    def _do_fill(self, pt):
        """Floodfill fra touch-punkt."""
        ImageDraw.floodfill(self._pil, pt, hex_p(self.color), thresh=40)

    # ── Offentlige metoder ────────────────────────────────────────

    def clear_canvas(self, *_):
        self._pil = PILImage.new('RGB', (CANVAS_W, CANVAS_H), (255, 255, 255))
        self._refresh()

    def save_to(self, path):
        self._pil.save(path)

    def load_from(self, path):
        self._pil = PILImage.open(path).convert('RGB').resize(
            (CANVAS_W, CANVAS_H), PILImage.LANCZOS)
        self._refresh()

# ══════════════════════════════════════════════════════════════════
#  HOVED-APP
# ══════════════════════════════════════════════════════════════════

class KommunikasjonstavleApp(App):

    # ── Oppstart ──────────────────────────────────────────────────

    def build(self):
        Window.clearcolor = (0.95, 0.96, 0.98, 1)

        # Sikre at alle datamapper finnes
        for d in [DATA_DIR, IMG_DIR, DRAW_DIR, DOWNLOAD_DIR]:
            os.makedirs(d, exist_ok=True)

        # App-tilstand
        self.data        = load_struct()
        self.nav_stack   = []       # [(screen_name, kwargs)]
        self.cur_folder  = None     # ID på åpen mappe
        self.edit_mode   = False
        self.draw_canvas = None     # Referanse til aktiv DrawCanvas
        self._cur_scr    = 'home'

        # Rot-layout: NavBar øverst, innholdsflate under
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
        bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None, height=dp(68),
            padding=dp(6), spacing=dp(6),
        )

        self._btn_back = mk_btn(
            '←', hex_k('#4D96FF'), h=dp(56), fs=24,
            cb=self.go_back, size_hint_x=None, width=dp(64),
        )
        self._btn_home = mk_btn(
            '🏠', hex_k('#6BCB77'), h=dp(56), fs=22,
            cb=self.go_home, size_hint_x=None, width=dp(64),
        )
        self._lbl_title = Label(
            text=APP_TITLE, bold=True, font_size=sp(18),
            color=(0.08, 0.10, 0.35, 1),
        )
        self._btn_draw = mk_btn(
            '🎨', hex_k('#FF9F43'), h=dp(56), fs=22,
            cb=self.go_draw, size_hint_x=None, width=dp(64),
        )
        self._btn_edit = mk_btn(
            '✏️', hex_k('#C77DFF'), h=dp(56), fs=22,
            cb=self.toggle_edit, size_hint_x=None, width=dp(64),
        )

        for w in [self._btn_back, self._btn_home, self._lbl_title,
                  self._btn_draw, self._btn_edit]:
            bar.add_widget(w)
        return bar

    def _set_title(self, t):
        self._lbl_title.text = t

    def _set_edit_highlight(self, on):
        self._btn_edit.background_color = hex_k('#7B2FBE' if on else '#C77DFF')

    # ── Navigasjons-metoder ───────────────────────────────────────

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
        # Lagre nåværende skjerm i stakken for Tilbake-knappen
        if self._cur_scr == 'folder':
            self.nav_stack.append(('folder', {'fid': self.cur_folder}))
        elif self._cur_scr not in ('draw',):
            self.nav_stack.append(('home', {}))
        self._show_draw()

    def toggle_edit(self, *_):
        # Toggler redigeringsmodus og bygger om gjeldende skjerm
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
    #  HJEMSKJERM – Mappeoversikt
    # ══════════════════════════════════════════════════

    def _show_home(self, **_):
        self._cur_scr   = 'home'
        self.cur_folder = None
        self._set_title(APP_TITLE)

        outer = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        if self.edit_mode:
            outer.add_widget(mk_btn(
                '＋  Legg til ny mappe', hex_k('#6BCB77'), h=dp(54),
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
        """Lager én mappe-flis for hjemskjermen."""
        has_img  = bool(fo.get('image') and os.path.exists(fo['image']))
        h_total  = dp(194) if self.edit_mode else dp(158)
        img_h    = dp(98)  if self.edit_mode else dp(108)
        label_h  = dp(50)
        del_h    = dp(38)

        if self.edit_mode:
            tap = lambda f=fo: self._folder_popup(f)
        else:
            tap = lambda f=fo: self._open_folder(f)

        cell = BoxLayout(
            orientation='vertical',
            size_hint_y=None, height=h_total,
            spacing=dp(4),
        )

        if has_img:
            cell.add_widget(TappableImage(
                tap, source=fo['image'],
                size_hint=(1, None), height=img_h,
                allow_stretch=True, keep_ratio=True,
            ))

        btn = Button(
            text=fo['name'],
            size_hint=(1, None),
            height=label_h if has_img else (dp(150) if not self.edit_mode else dp(110)),
            background_normal='',
            background_color=hex_k(fo['color']),
            color=(0.05, 0.05, 0.2, 1),
            bold=True, font_size=sp(18),
        )
        btn.bind(on_release=lambda b, t=tap: t())
        cell.add_widget(btn)

        if self.edit_mode:
            cell.add_widget(mk_btn(
                '🗑  Slett mappe', hex_k('#FF6B6B'), h=del_h, fs=13,
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

        outer = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        if self.edit_mode:
            bar = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
            bar.add_widget(mk_btn(
                '＋  Nytt ASK-bilde', hex_k('#6BCB77'), h=dp(50),
                cb=lambda *_: self._item_popup(fo, None),
            ))
            bar.add_widget(mk_btn(
                '⬆  Last opp fra enhet', hex_k('#4D96FF'), h=dp(50),
                cb=lambda *_: self._upload_to_folder(fo),
            ))
            outer.add_widget(bar)

        grid = GridLayout(cols=3, spacing=dp(10), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for it in fo['items']:
            grid.add_widget(self._make_item_tile(fo, it))

        sv = ScrollView()
        sv.add_widget(grid)
        outer.add_widget(sv)
        self._set_content(outer)

    def _make_item_tile(self, fo, it):
        """Lager én ASK-bilde-flis for mappeskjermen."""
        img_path = it.get('image') or ''
        has_img  = bool(img_path and os.path.exists(img_path))
        h_total  = dp(206) if self.edit_mode else dp(164)
        img_h    = dp(114) if self.edit_mode else dp(120)
        label_h  = dp(42)
        act_h    = dp(38)

        if self.edit_mode:
            tap = lambda f=fo, i=it: self._item_popup(f, i)
        else:
            tap = lambda p=img_path, n=it['name']: self._show_image_full(p, n)

        cell = BoxLayout(
            orientation='vertical',
            size_hint_y=None, height=h_total,
            spacing=dp(4),
        )

        if has_img:
            cell.add_widget(TappableImage(
                tap, source=img_path,
                size_hint=(1, None), height=img_h,
                allow_stretch=True, keep_ratio=True,
            ))

        btn = Button(
            text=it['name'],
            size_hint=(1, None),
            height=label_h if has_img else (dp(160) if not self.edit_mode else dp(120)),
            background_normal='',
            background_color=hex_k('#4D96FF'),
            color=(1, 1, 1, 1), bold=True, font_size=sp(13),
        )
        btn.bind(on_release=lambda b: tap())
        cell.add_widget(btn)

        if self.edit_mode:
            row = BoxLayout(size_hint_y=None, height=act_h, spacing=dp(4))
            row.add_widget(mk_btn(
                '⬇ Last ned', hex_k('#6BCB77'), h=act_h - dp(2), fs=13,
                cb=lambda *_, p=img_path: self._download_image(p),
            ))
            row.add_widget(mk_btn(
                '🗑 Slett', hex_k('#FF6B6B'), h=act_h - dp(2), fs=13,
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
            f'⬇  Last ned «{name}» til enheten',
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

        if not PIL_OK:
            self._set_content(Label(
                text='Feil: Pillow/PIL ikke installert (PIL_OK=False)',
                font_size=sp(18), color=(1, 0.2, 0.2, 1),
            ))
            return

        root = BoxLayout(orientation='vertical', spacing=dp(4), padding=dp(6))

        # ── Verktøylinje ─────────────────────────────────────────
        toolbar = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(5))

        tools = [
            ('pen',     '🖊 Penn'),
            ('eraser',  '🧹 Viskelær'),
            ('line',    '╱ Linje'),
            ('rect',    '▭ Rektangel'),
            ('ellipse', '○ Ellipse'),
            ('fill',    '🪣 Fyll'),
        ]
        self._tool_btns = {}
        for key, label in tools:
            b = mk_btn(label, hex_k(TOOL_COLORS[key]), h=dp(52), fs=12)
            b.bind(on_release=lambda btn, k=key: self._set_draw_tool(k))
            toolbar.add_widget(b)
            self._tool_btns[key] = b

        toolbar.add_widget(mk_btn(
            '💾 Lagre', hex_k('#6BCB77'), h=dp(52), fs=13,
            cb=self._save_drawing,
        ))
        toolbar.add_widget(mk_btn(
            '🗑 Tøm', hex_k('#FF6B6B'), h=dp(52), fs=13,
            cb=lambda *_: self.draw_canvas.clear_canvas(),
        ))
        root.add_widget(toolbar)

        # ── Størrelsesstrek ───────────────────────────────────────
        size_row = BoxLayout(
            size_hint_y=None, height=dp(48), spacing=dp(8),
            padding=(dp(6), dp(4)),
        )
        size_row.add_widget(Label(
            text='Penselstørrelse:', size_hint_x=None, width=dp(145),
            font_size=sp(14), color=(0.1, 0.1, 0.1, 1),
        ))
        self._size_slider = Slider(min=2, max=50, value=6, step=1)
        self._size_lbl    = Label(
            text='6 px', size_hint_x=None, width=dp(55),
            font_size=sp(14), color=(0.1, 0.1, 0.1, 1),
        )
        self._size_slider.bind(value=self._on_size_change)
        size_row.add_widget(self._size_slider)
        size_row.add_widget(self._size_lbl)
        root.add_widget(size_row)

        # ── Fargepalett ───────────────────────────────────────────
        palette_row = BoxLayout(
            size_hint_y=None, height=dp(58), spacing=dp(6),
            padding=(dp(4), dp(4)),
        )
        self._col_btns = {}
        for h in PALETTE:
            cb = Button(
                size_hint=(None, None), size=(dp(50), dp(50)),
                background_normal='', background_color=hex_k(h),
            )
            cb.bind(on_release=lambda b, col=h: self._set_draw_color(col))
            palette_row.add_widget(cb)
            self._col_btns[h] = cb
        root.add_widget(palette_row)

        # ── Tegne-canvas (fyller resten av skjermen) ──────────────
        self.draw_canvas = DrawCanvas()
        root.add_widget(self.draw_canvas)

        self._set_content(root)
        # Sett standardvalg
        self._set_draw_tool('pen')
        self._set_draw_color('#000000')

    def _set_draw_tool(self, key):
        if self.draw_canvas:
            self.draw_canvas.tool = key
        for k, btn in self._tool_btns.items():
            btn.background_color = hex_k(
                TOOL_ACTIVE[k] if k == key else TOOL_COLORS[k]
            )

    def _set_draw_color(self, col):
        if self.draw_canvas:
            self.draw_canvas.color = col
        for h, btn in self._col_btns.items():
            # Uthev valgt farge med lysere bakgrunn
            if h == col:
                r, g, b, _ = hex_k(h)
                btn.background_color = (
                    min(r + 0.25, 1),
                    min(g + 0.25, 1),
                    min(b + 0.25, 1), 1,
                )
            else:
                btn.background_color = hex_k(h)

    def _on_size_change(self, slider, val):
        if self.draw_canvas:
            self.draw_canvas.size_px = int(val)
        self._size_lbl.text = f'{int(val)} px'

    def _save_drawing(self, *_):
        if not self.draw_canvas:
            return
        fname = datetime.now().strftime('tegning_%Y%m%d_%H%M%S.png')
        path  = os.path.join(DRAW_DIR, fname)
        self.draw_canvas.save_to(path)
        self._toast(f'Tegning lagret:\n{fname}')

    # ══════════════════════════════════════════════════
    #  POPUP – REDIGER MAPPE
    # ══════════════════════════════════════════════════

    def _folder_popup(self, fo):
        """Åpner popup for å opprette (fo=None) eller redigere en mappe."""
        new = fo is None
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        # Navn-felt
        layout.add_widget(Label(
            text='Navn på mappen:', size_hint_y=None, height=dp(30),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        name_inp = TextInput(
            text='' if new else fo['name'],
            multiline=False, size_hint_y=None, height=dp(52), font_size=sp(16),
        )
        layout.add_widget(name_inp)

        # Fargevelger
        layout.add_widget(Label(
            text='Velg farge:', size_hint_y=None, height=dp(28),
            font_size=sp(15), color=(0, 0, 0, 1), halign='left',
        ))
        chosen_color = [fo['color'] if fo else FOLDER_COLORS[0]]
        col_row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        col_btns_list = []
        for c in FOLDER_COLORS:
            cb = Button(
                background_normal='', background_color=hex_k(c),
                size_hint=(None, None), size=(dp(54), dp(54)),
            )
            cb.opacity = 1.0 if chosen_color[0] == c else 0.55
            def pick_col(b, col=c):
                chosen_color[0] = col
                for x in col_btns_list:
                    x.opacity = 0.55
                b.opacity = 1.0
            cb.bind(on_release=pick_col)
            col_row.add_widget(cb)
            col_btns_list.append(cb)
        layout.add_widget(col_row)

        # Bilde-velger
        chosen_img = [fo.get('image') if fo else None]
        img_lbl = Label(
            text='Bilde: ' + (os.path.basename(chosen_img[0]) if chosen_img[0] else 'ingen'),
            size_hint_y=None, height=dp(28),
            font_size=sp(13), color=(0.25, 0.25, 0.25, 1),
        )
        layout.add_widget(img_lbl)

        pop_ref = [None]   # Referanse til popup (brukes i _pick_image)
        pick_btn = mk_btn(
            '📁  Velg mappe-bilde fra enhet', hex_k('#4D96FF'), h=dp(48),
        )
        pick_btn.bind(on_release=lambda *_: self._pick_image(
            chosen_img, img_lbl, pop_ref[0]))
        layout.add_widget(pick_btn)

        # OK / Avbryt
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

        btn_row.add_widget(mk_btn('✓  Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_ok))
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
    #  POPUP – REDIGER ELEMENT (ASK-bilde)
    # ══════════════════════════════════════════════════

    def _item_popup(self, fo, it):
        """Åpner popup for å opprette (it=None) eller redigere et ASK-element."""
        new = it is None
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))

        layout.add_widget(Label(
            text='Navn (etiketten under bildet):', size_hint_y=None, height=dp(30),
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
            font_size=sp(13), color=(0.25, 0.25, 0.25, 1),
        )
        layout.add_widget(img_lbl)

        pop_ref = [None]
        pick_btn = mk_btn('📁  Velg ASK-bilde fra enhet', hex_k('#4D96FF'), h=dp(48))
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

        btn_row.add_widget(mk_btn('✓  Lagre', hex_k('#6BCB77'), h=dp(50), cb=on_ok))
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
        """
        Åpner filebrowser for å velge et bilde.
        Kopier valgt fil til IMG_DIR og oppdaterer chosen_img_ref.
        Foreldre-popup forblir åpen under (Kivy støtter stablede popups).
        """
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
                except Exception as e:
                    self._toast(f'Feil ved kopiering:\n{e}')
            fc_pop.dismiss()

        btn_row.add_widget(mk_btn(
            '✓  Velg dette bildet', hex_k('#6BCB77'), h=dp(52), cb=on_select,
        ))
        btn_row.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(52),
            cb=lambda *_: fc_pop.dismiss(),
        ))
        fc_layout.add_widget(btn_row)

        fc_pop = Popup(
            title='Velg bildefil', content=fc_layout,
            size_hint=(0.97, 0.93),
        )
        fc_pop.open()

    def _upload_to_folder(self, fo):
        """
        Åpner filebrowser og legger valgt bilde direkte til mappen
        som et nytt ASK-element (filnavn uten extension brukes som etikettforslag).
        """
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
                    self._toast(f'Lagt til: {fname}')
                    self._show_folder(fid=fo['id'])
                except Exception as e:
                    self._toast(f'Feil:\n{e}')
            else:
                pop.dismiss()

        btn_row.add_widget(mk_btn(
            '⬆  Last opp til mappe', hex_k('#4D96FF'), h=dp(52), cb=on_upload,
        ))
        btn_row.add_widget(mk_btn(
            'Avbryt', hex_k('#9CA3AF'), h=dp(52),
            cb=lambda *_: pop.dismiss(),
        ))
        fc_layout.add_widget(btn_row)

        pop = Popup(
            title=f'Last opp til «{fo["name"]}»', content=fc_layout,
            size_hint=(0.97, 0.93),
        )
        pop.open()

    def _download_image(self, src_path):
        """Kopierer bildefil til /sdcard/Download."""
        if not src_path or not os.path.exists(src_path):
            self._toast('Ingen bildefil å laste ned.')
            return
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            dst = os.path.join(DOWNLOAD_DIR, os.path.basename(src_path))
            shutil.copy2(src_path, dst)
            self._toast(f'Lagret til Nedlastinger:\n{os.path.basename(dst)}')
        except Exception as e:
            self._toast(f'Nedlasting feilet:\n{e}')

    # ══════════════════════════════════════════════════
    #  TOAST-MELDING (selvlukkende infovindu)
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
    KommunikasjonstavleApp().run()
