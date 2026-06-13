#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kt_data.py – Kommunikasjonstavle
=================================
Rene datahjelpefunksjoner uten Kivy-avhengigheter eller global tilstand.
Importeres i main.py:  from kt_data import *
"""

from datetime import datetime

DAY_CODES = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']


def today_code():
    """Returnerer ISO-ukekode for i dag ('MO'–'SU')."""
    return DAY_CODES[datetime.now().weekday()]


def get_day_plan(data, code):
    """
    Returnerer listen over aktiviteter for gitt ukedagskode.
    Støtter både nytt format (dagsplaner-dict) og gammelt (dagsrytme-liste).
    """
    plans = data.get('dagsplaner', {})
    if isinstance(plans, dict):
        return list(plans.get(code, []))
    return list(data.get('dagsrytme', []))


def is_paused(data):
    """Returnerer True hvis dagsrytmen er satt på pause."""
    return bool(data.get('dagsrytme_paused', False))


def get_category(data, cat_id):
    """Returnerer kategoriobjekt med gitt id, eller None."""
    if not cat_id:
        return None
    return next(
        (c for c in data.get('categories', []) if c.get('id') == cat_id),
        None
    )


def get_folder(d, fid):
    """
    Returnerer mappeobjekt med gitt id.
    Søker i toppnivå-mapper og undermapper.
    """
    if not fid:
        return None
    for fo in d.get('folders', []):
        if fo.get('id') == fid:
            return fo
        for sf in fo.get('subfolders', []):
            if sf.get('id') == fid:
                return sf
    return None


def get_sequence(data, sid):
    """Returnerer handlingsrekke-objekt med gitt id, eller None."""
    if not sid:
        return None
    return next(
        (s for s in data.get('sequences', []) if s.get('id') == sid),
        None
    )


def tale_for_item(it):
    """
    Returnerer teksten som skal leses opp (TTS) for et symbol/element.

    Bruker det valgfrie 'uttale'-feltet hvis det er satt og ikke tomt –
    slik kan de ansatte skrive en alternativ skrivemåte som gir riktig
    uttale på talesyntesen, uten å endre selve symbolnavnet/etiketten
    som vises under bildet. Er feltet tomt/ikke satt, brukes 'name'
    som før.
    """
    uttale = (it.get('uttale') or '').strip()
    return uttale or it.get('name', '')
