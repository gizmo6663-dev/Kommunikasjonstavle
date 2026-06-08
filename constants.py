#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
constants.py – Kommunikasjonstavle
===================================
Sentralisert modul for alle app-wide konstanter.
Importeres i main.py via:  from constants import *

Endringer her slår automatisk gjennom i hele appen uten å
røre main.py, og unngår at samme verdi defineres flere steder.
"""

# ── App-metadata ───────────────────────────────────────────────────
APP_TITLE    = 'Kommunikasjonstavle'
DOWNLOAD_DIR = '/sdcard/Download'

# ── Datastier – settes i build() via App.user_data_dir ────────────
DATA_DIR    = None
IMG_DIR     = None
DRAW_DIR    = None
STRUCT_FILE = None
LOG_FILE    = None

# ── Lerret-dimensjoner ────────────────────────────────────────────
CANVAS_W = 960
CANVAS_H = 1280   # Portrettformat passer mobilskjerm

# ── Ukedager ─────────────────────────────────────────────────────
# ISO-baserte ukekoder. datetime.weekday() gir 0=mandag,
# så DAY_CODES[weekday()] gir riktig kode direkte.
DAY_CODES    = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
DAY_LABEL_NO = {
    'MO': 'Ma', 'TU': 'Ti', 'WE': 'On', 'TH': 'To',
    'FR': 'Fr', 'SA': 'Lø', 'SU': 'Sø',
}
DAY_FULL_NO = {
    'MO': 'Mandag',  'TU': 'Tirsdag', 'WE': 'Onsdag',
    'TH': 'Torsdag', 'FR': 'Fredag',  'SA': 'Lørdag',
    'SU': 'Søndag',
}

# ── Popup-størrelser ──────────────────────────────────────────────
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

# ── Verktøyfarger (tegne-modus) ───────────────────────────────────
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

# ── Penselfarger ─────────────────────────────────────────────────
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

# ── Fargepalett – 30 farger i 6×5-rutenett ───────────────────────
# Bevisst valgt for maksimal variasjon.
# Rad 1: svart/hvit og grå-spekter
# Rad 2: rødt, brunt, burgunder, mørk lilla, mørk blå, marineblå
# Rad 3: oransje, gul, lime, grønn, blågrønn, turkis
# Rad 4: lyseblå, lys lilla, rosa, laks, beige, sand
# Rad 5: elektrisk blå, neon grønn, magenta, korall, mint, gull
PALETTE = [
    # Nøytrale
    '#000000', '#444444', '#888888', '#BBBBBB', '#E8E8E8', '#FFFFFF',
    # Mørke varme/kalde  (idx 6–11)
    '#B71C1C', '#6D4C41', '#880E4F', '#4A148C', '#1A237E', '#01579B',
    # Mellomtone primære (idx 12–17)
    '#E53935', '#FB8C00', '#FDD835', '#43A047', '#039BE5', '#8E24AA',
    # Lyse/pastel        (idx 18–23)
    '#EF9A9A', '#FFE082', '#C8E6C9', '#B3E5FC', '#E1BEE7', '#FFCCBC',
    # Spesielle/levende  (idx 24–29)
    '#00E5FF', '#76FF03', '#F50057', '#FF6D00', '#1DE9B6', '#FFD740',
]

# ── Mappefarger – hentet fra PALETTE via indekser ─────────────────
# Indeksene refererer til PALETTE ovenfor. Oppdater kun indeksene
# for å endre mappepaletten uten å duplisere hex-verdier.
FOLDER_COLOR_IDX = [6, 12, 14, 15, 17, 21, 23, 24]
FOLDER_COLORS    = [PALETTE[i] for i in FOLDER_COLOR_IDX]

# ── Standard aktivitetskategorier ────────────────────────────────
DEFAULT_CATEGORIES = [
    {'id': 'maltid',   'name': 'Måltid',   'color': '#FFB74D'},
    {'id': 'lek',      'name': 'Lek',      'color': '#FFD93D'},
    {'id': 'hvile',    'name': 'Hvile',    'color': '#9C7DCE'},
    {'id': 'utetid',   'name': 'Utetid',   'color': '#6BCB77'},
    {'id': 'samling',  'name': 'Samling',  'color': '#4D96FF'},
    {'id': 'overgang', 'name': 'Overgang', 'color': '#90A4AE'},
]
