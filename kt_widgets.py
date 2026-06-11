#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kt_widgets.py – Kommunikasjonstavle
=====================================
Stilede Kivy-widgets, UI-hjelpefunksjoner og fargeberegninger.
Importeres i main.py:  from kt_widgets import *
"""

import os
import math
import logging

from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.utils import platform

# Popup-størrelse for fullskjerm-zoom (brukes i TappableImage._show_zoom_popup)
POPUP_FULL = (0.97, 0.94)

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
        # Skala-transform rundt midten av knappen.
        # Brukes til trykk-feedback (0.96 → 1.0) – roligere enn rotasjon.
        PushMatrix:
        Scale:
            x: self.scale
            y: self.scale
            origin: self.center
        # 1. Myk skygge i tre lag – gir gradvis fade fra senter til kant
        #    i stedet for en hard-kantet kopi av knappen.
        Color:
            rgba: 0.04, 0.06, 0.18, 0.04
        RoundedRectangle:
            pos: self.x + dp(4.5), self.y - dp(4.5)
            size: self.width + dp(3), self.height + dp(3)
            radius: [self.radius + dp(3)]
        Color:
            rgba: 0.04, 0.06, 0.18, 0.06
        RoundedRectangle:
            pos: self.x + dp(2.5), self.y - dp(2.5)
            size: self.width + dp(1), self.height + dp(1)
            radius: [self.radius + dp(2)]
        Color:
            rgba: 0.04, 0.06, 0.18, 0.08
        RoundedRectangle:
            pos: self.x + dp(1), self.y - dp(1)
            size: self.width, self.height
            radius: [self.radius + dp(1)]
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
        # 3. Én subtil ytre kant for definisjon.
        # Den indre "glans-linjen" er fjernet bevisst – den konkurrerte med
        # gradient-toppen og skapte en visuell "dobbel kant"-effekt.
        Color:
            rgba: 0, 0, 0, 0.16
        Line:
            rounded_rectangle: (self.x + dp(0.8), self.y + dp(0.8), self.width - dp(1.6), self.height - dp(1.6), self.radius)
            width: 1.0
    canvas.after:
        # PopMatrix ETTER at tekst er tegnet – slik skaleres alt inkl. label
        PopMatrix:

<RBox>:
    canvas.before:
        # Skala-transform rundt kortets senter – brukes til "pop"-
        # animasjon ved trykk (krymp svakt → fjær tilbake), samme
        # teknikk som RBtn sin trykk-feedback.
        PushMatrix:
        Scale:
            x: self.scale
            y: self.scale
            origin: self.center
        # Skyggehierarki: RBox = "surface" (lett). Lettere enn RBtn (som
        # er "elevated"), så knapper leses tydelig oppå container-flater.
        # To lag for myk overgang i stedet for hard offset-kopi.
        Color:
            rgba: 0.04, 0.06, 0.18, 0.03
        RoundedRectangle:
            pos: self.x + dp(2.5), self.y - dp(2.5)
            size: self.width + dp(1), self.height + dp(1)
            radius: [self.radius + dp(2)]
        Color:
            rgba: 0.04, 0.06, 0.18, 0.05
        RoundedRectangle:
            pos: self.x + dp(1), self.y - dp(1)
            size: self.width, self.height
            radius: [self.radius + dp(1)]
        # Bakgrunn: svak PIL-gradient-tekstur (genereres av
        # _update_grad_texture) – gir kortet litt dybde i stedet for
        # helt flat farge. ~5% spredning, mye svakere enn knappenes
        # ~11% slik at knapper fortsatt leses som "hevet" over kortet.
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
            texture: self._grad_tex if hasattr(self, '_grad_tex') and self._grad_tex else None
        # Fallback flat farge hvis tekstur ikke er klar (f.eks. PIL
        # mangler) – identisk med tidligere oppførsel.
        Color:
            rgba: self.box_color if not (hasattr(self, '_grad_tex') and self._grad_tex) else (0,0,0,0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]
        # Subtil ytre kant
        Color:
            rgba: 0, 0, 0, 0.08
        Line:
            rounded_rectangle: (self.x + dp(0.8), self.y + dp(0.8), self.width - dp(1.6), self.height - dp(1.6), self.radius)
            width: 0.9
    canvas.after:
        PopMatrix:

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

# Forleng ModalView/Popup entrance-animasjon globalt fra Kivy's standard 0.10s
# til 0.18s. Forkjellen merkes som at popup-en "lander" på skjermen i stedet
# for å brått overta. Samme verdi som vi bruker for skjermfade.
try:
    from kivy.uix.modalview import ModalView as _ModalView
    _ModalView._anim_duration = 0.18
except Exception:
    pass

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


def _make_gradient_texture(rgba, dark_end, light_end):
    """
    Genererer en 1×64-px vertikal lineær gradient-tekstur fra en RGBA-farge.

    dark_end / light_end er relative justeringer (-1.0..1.0) på topp/bunn
    av fargeverdiene – brukes til å gi flate farger en svak følelse av
    dybde/belysning uten harde brytningspunkter.

    Delt mellom RBtn (knapper, ~11% spredning – "elevated") og RBox
    (kort/overflater, ~5% spredning – "lett") slik at begge får samme
    visuelle teknikk, bare med ulik intensitet i tråd med skyggehierarkiet.

    Returnerer None hvis PIL ikke er tilgjengelig (ingen feil – bare
    ingen gradient, flat farge brukes som fallback).
    """
    if not PIL_OK:
        return None
    try:
        r, g, b, a = rgba
        H = 64
        buf = bytearray(1 * H * 4)
        for y in range(H):
            t = y / (H - 1)             # 0 = bunn, 1 = topp etter flip
            delta = dark_end + (light_end - dark_end) * t
            fr = min(1.0, max(0.0, r + delta))
            fg = min(1.0, max(0.0, g + delta))
            fb = min(1.0, max(0.0, b + delta))
            i = y * 4
            buf[i]   = int(fr * 255)
            buf[i+1] = int(fg * 255)
            buf[i+2] = int(fb * 255)
            buf[i+3] = int(a  * 255)
        tex = Texture.create(size=(1, H), colorfmt='rgba')
        tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
        tex.wrap = 'repeat'   # tiles horisontalt til full bredde
        return tex
    except Exception:
        return None


class RBtn(Button):
    """
    Avrundet knapp med myk skygge, kantlinje og PIL-basert lineær gradient.
    scale er NumericProperty slik at Animation kan animere den
    via PushMatrix/Scale/PopMatrix i KV-regelen — gir en rolig
    "trykk-inn-i-overflaten"-følelse i stedet for rotasjons-vipping.
    """
    btn_color  = ListProperty([0.30, 0.50, 1.0, 1.0])
    radius     = NumericProperty(dp(14))
    scale      = NumericProperty(1.0)
    _grad_cache = {}  # delt tekstur-cache for alle RBtn-instanser

    def on_btn_color(self, *_):
        self._update_grad_texture()

    def _update_grad_texture(self):
        """
        Genererer (eller henter fra cache) gradient-teksturen for
        gjeldende btn_color. ~11% spredning ("elevated"-nivå – knapper
        skal lese tydelig oppå kort/overflater).
        """
        r, g, b, a = self.btn_color
        cache_key = f'{r:.3f}{g:.3f}{b:.3f}{a:.3f}'
        cached = RBtn._grad_cache.get(cache_key)
        if cached:
            self._grad_tex = cached
            return
        tex = _make_gradient_texture(self.btn_color, dark_end=-0.03, light_end=0.08)
        if tex:
            self._grad_tex = tex
            RBtn._grad_cache[cache_key] = tex


class RBox(BoxLayout):
    """
    Avrundet kort/panel-container med skygge, dobbel kantlinje og svak
    gradient-tekstur. Brukes for mappe-fliser, ASK-bilde-kort,
    dagsplan-rader og "Akkurat nå"-kortet.

    scale er NumericProperty slik at trykkbare kort kan få en kort
    "pop"-animasjon (krymp → fjær tilbake) via PushMatrix/Scale/PopMatrix
    i KV-regelen, samme teknikk som RBtn.
    """
    box_color = ListProperty([1.0, 1.0, 1.0, 1.0])
    radius    = NumericProperty(dp(16))
    scale     = NumericProperty(1.0)
    _grad_cache = {}  # delt tekstur-cache for alle RBox-instanser

    def on_box_color(self, *_):
        self._update_grad_texture()

    def _update_grad_texture(self):
        """
        Genererer (eller henter fra cache) gradient-teksturen for
        gjeldende box_color. ~5% spredning ("lett"-nivå – halvparten av
        RBtn sin intensitet) for en subtil følelse av dybde uten å
        konkurrere visuelt med knapper oppå kortet.
        """
        r, g, b, a = self.box_color
        cache_key = f'{r:.3f}{g:.3f}{b:.3f}{a:.3f}'
        cached = RBox._grad_cache.get(cache_key)
        if cached:
            self._grad_tex = cached
            return
        tex = _make_gradient_texture(self.box_color, dark_end=-0.015, light_end=0.035)
        if tex:
            self._grad_tex = tex
            RBox._grad_cache[cache_key] = tex


class NavBar(BoxLayout):
    """Navigasjonsbar med hvit bakgrunn og separator-linje i bunn."""
    pass


class BottomBar(BoxLayout):
    """Bunnbar med hvit bakgrunn og separator-linje i topp."""
    pass


# ══════════════════════════════════════════════════════════════════
#  KONSTANTER
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
    1. Skalere ned til 48x48 for ytelse
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


def time_of_day_tint():
    """
    Returnerer (r, g, b, a) for vindusbakgrunnen basert på klokkeslett.
    Bittesmå skift – gir appen en «levende» følelse gjennom dagen.
    """
    from datetime import datetime as _dt
    h = _dt.now().hour
    if   6  <= h < 10: return (0.93, 0.95, 0.99, 1.0)   # morgen
    elif 10 <= h < 14: return (0.94, 0.95, 0.98, 1.0)   # midt
    elif 14 <= h < 18: return (0.97, 0.96, 0.94, 1.0)   # ettermiddag
    elif 18 <= h < 22: return (0.92, 0.93, 0.96, 1.0)   # kveld
    else:              return (0.90, 0.91, 0.94, 1.0)    # natt


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


def screen_scale():
    """
    Returnerer en dimensjonsløs skaleringsfaktor [0.80 – 1.20] basert på
    skjermens lengste side i tetthetsuavhengige piksler (dp).

    Referanse: 780 dp – tilsvarer en typisk FHD+ Android-telefon (f.eks.
    Pixel 7, Samsung A54, 6,1"–6,4" med ~420 dpi) i portrettmodus.

    Eksempler:
      650 dp  (liten/kompakt telefon)   → 0.83
      780 dp  (referanse)               → 1.00
      900 dp  (stor telefon, S25 Ultra) → 1.15
      1000 dp (nettbrett)               → capped 1.20

    Bruker max(bredde, høyde) i stedet for kun høyde, slik at en enhet
    som roteres til liggende (fase 1 – landskapsstøtte) beholder SAMME
    skaleringsfaktor som i portrett – den lange siden er fortsatt den
    lange siden, bare horisontal i stedet for vertikal. Uten dette ville
    rdp()-elementer krympet til minimum (0.80×) hver gang skjermen ble
    bredere enn den er høy.

    Brukes av rdp() til å skalere høyde-kritiske UI-elementer proporsjonalt
    med skjermstørrelsen slik at layouts ser konsistente ut på tvers av
    enheter og retninger.
    """
    long_dp = max(Window.width, Window.height) / dp(1)
    return max(0.80, min(1.20, long_dp / 780.0))


def is_landscape():
    """
    True hvis skjermen for øyeblikket er bredere enn den er høy.

    Brukes til å la rutenett (mappe-/bilde-grid, snarveier, symbolvelger)
    øke fra 4 til 6 kolonner i liggende format (fase 1 – landskapsstøtte),
    slik at den ekstra bredden utnyttes i stedet for å gi unaturlig brede,
    flate fliser.
    """
    return Window.width > Window.height


def rdp(base):
    """
    Responsiv dp: skalerer dp(base) etter skjermens lengste side via
    screen_scale().

    Bruk rdp(x) i stedet for dp(x) for alle høyde-kritiske elementer
    (rader, knapper, kort, navigasjonsbarer) der proporsjonalitet mellom
    skjermstørrelser er viktig. Horisontale bredder trenger normalt ikke
    rdp() – de er allerede relative til Window.width.

    Eksempel:
      dp(72) på 780 dp-skjerm → 72 dp
      dp(72) på 650 dp-skjerm → 58 dp  (0.80× ved nedre grense)
      dp(72) på 900 dp-skjerm → 83 dp
    """
    return dp(int(base * screen_scale()))



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
        Window.clearcolor = time_of_day_tint()


def bind_card_pop(card):
    """
    Gir et RBox-kort en kort "pop"-animasjon ved trykk: krymper svakt
    (scale 0.96) idet fingeren treffer kortet, og fjærer tilbake til
    full størrelse med out_back-easing (en bitteliten studs på slutten)
    kort tid etter – uavhengig av hvor lenge fingeren holdes nede.

    Bruker RBox.scale (NumericProperty + PushMatrix/Scale/PopMatrix i
    KV-regelen, samme teknikk som RBtn sin trykk-feedback).

    Bindingen returnerer alltid False fra on_touch_down – den FORBRUKER
    ikke touch-en, så eksisterende tap-/long-press-håndtering på
    barnewidgets (bilder, knapper inni kortet) fungerer helt uendret.
    Dette er ren visuell "krydder" lagt oppå eksisterende interaksjon.
    """
    def _on_down(card, touch):
        if card.collide_point(*touch.pos):
            haptic_feedback()
            Animation.cancel_all(card, 'scale')
            Animation(scale=0.96, duration=0.06, t='out_quad').start(card)

            def _spring_back(*_):
                Animation.cancel_all(card, 'scale')
                Animation(scale=1.0, duration=0.22, t='out_back').start(card)
            Clock.schedule_once(_spring_back, 0.10)
        return False
    card.bind(on_touch_down=_on_down)


def mk_btn(text, bg, fg=(1, 1, 1, 1), fs=15, h=dp(54), cb=None, **kw):
    """
    Lager en RBtn med:
    - PIL-gradient (via _update_grad_texture i RBtn)
    - Kortvippings-animasjon ved trykk (rotation ±2°)
    - Haptic feedback via plyer.vibrator (kort 30ms puls)
    - WCAG AAA i høykontrast-modus
    """
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
        # Mørklegg svakt + skala-trykk ned til 96%.
        # 88% brightness er mykere enn tidligere 75% – passer flat-stilet bedre.
        r, g, bv, a = btn.btn_color
        btn.btn_color = [max(0, r*0.88), max(0, g*0.88), max(0, bv*0.88), a]
        Animation(scale=0.92, duration=0.07, t='out_quad').start(btn)
        haptic_feedback()

    def _on_release_anim(btn, *_):
        btn.btn_color = list(orig_color)
        # Tilbake til normalstørrelse med svak elastisk overskyting (out_back).
        # Mer behersket enn forrige rotasjons-bounce.
        Animation(scale=1.0, duration=0.13, t='out_back').start(btn)

    b.bind(on_press=_on_press, on_release=_on_release_anim)
    if cb:
        b.bind(on_release=cb)
    return b

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
        Animation(opacity=0.65, duration=0.06).start(self)
        if dt < 0.35 and dt > 0.01:
            self._show_zoom_popup()
        else:
            self._action()
        return True

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            Animation(opacity=1.0, duration=0.12).start(self)
        return super().on_touch_up(touch)

    def _show_zoom_popup(self):
        from kivy.uix.floatlayout import FloatLayout
        overlay = FloatLayout(size=Window.size)
        with overlay.canvas.before:
            from kivy.graphics import Color as KColor, Rectangle
            KColor(0, 0, 0, 0.85)
            Rectangle(pos=(0,0), size=Window.size)
        zoom_img = Image(
            source=self.source,
            size_hint=POPUP_FULL,
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



class LongPressImage(TappableImage):
    """
    TappableImage med lang-trykk-callback (0.5 sek hold).
    Kort trykk → normal tap-callback.
    Lang trykk → long_cb() + haptisk feedback.
    """
    def __init__(self, tap_cb, long_cb, **kw):
        super().__init__(tap_cb, **kw)
        self._long_cb    = long_cb
        self._lp_event   = None
        self._lp_fired   = False

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._lp_fired = False
            self._lp_event = Clock.schedule_once(self._fire_long, 0.5)
        return super().on_touch_down(touch)

    def _fire_long(self, *_):
        self._lp_fired = True
        haptic_feedback()
        self._long_cb()

    def on_touch_up(self, touch):
        if self._lp_event:
            self._lp_event.cancel()
            self._lp_event = None
        return super().on_touch_up(touch)

