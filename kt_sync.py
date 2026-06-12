# -*- coding: utf-8 -*-
"""
kt_sync.py – Enhet-til-enhet-deling over lokalt WiFi for Kommunikasjonstavle.

Enkel HTTP-basert protokoll, KUN for bruk på samme lokale nettverk (ingen
internett, ingen skytjeneste):

    GET /manifest?code=XXXX        -> JSON-beskrivelse av delte mapper/
                                       undermapper/elementer (uten
                                       absolutte filstier)
    GET /image/<item_id>?code=XXXX -> bildefil (rå bytes) for ett element

`code` er en 4-sifret PIN generert av den delende enheten og vist i
appen – fungerer som en enkel beskyttelse mot at andre enheter på
samme nettverk (f.eks. åpent gjeste-WiFi i barnehagen) henter data ved
en feiltakelse.

Modulen har INGEN Kivy-avhengigheter og kan derfor importeres og
testes uavhengig av appen.
"""

import os
import json
import socket
import random
import threading
import mimetypes
import urllib.request
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class SyncError(Exception):
    """Feil under deling/mottak. Meldingen er trygg å vise til brukeren."""


# ──────────────────────────────────────────────────────────────────────
#  Hjelpefunksjoner
# ──────────────────────────────────────────────────────────────────────

def get_local_ip():
    """
    Beste gjetning på enhetens lokale WiFi-IP.

    Den klassiske "UDP connect-trikset": en UDP-socket trenger ikke
    faktisk sende noe for å få operativsystemet til å velge et
    utgående nettverksgrensesnitt – `getsockname()` gir da den lokale
    IP-en på det grensesnittet. 8.8.8.8 er bare et eksternt mål; ingen
    pakker sendes dit.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def make_code():
    """Tilfeldig 4-sifret PIN-kode (som streng, med ledende nuller)."""
    return f'{random.randint(0, 9999):04d}'


def count_items(folder):
    """Antall elementer i `folder` og alle dens undermapper, rekursivt."""
    n = len(folder.get('items', []))
    for sub in folder.get('subfolders', []):
        n += count_items(sub)
    return n


# ──────────────────────────────────────────────────────────────────────
#  Manifest – bygges av den DELENDE enheten
# ──────────────────────────────────────────────────────────────────────

def build_manifest(folders):
    """
    Bygger en JSON-serialiserbar beskrivelse av `folders` (en liste med
    mappe-dicts, slik de ligger i structure.json) for deling.

    Returnerer (manifest, image_map):
      - manifest  : dict – sendes som-is til klienten via /manifest.
                    Inneholder IKKE absolutte filstier.
      - image_map : dict item_id -> absolutt filsti, brukt av
                    HTTP-serveren til å finne riktig bildefil for
                    /image/<item_id>-forespørsler. Sendes ALDRI til
                    klienten.

    Elementer uten gyldig bildefil (slettet/flyttet fra disk) hoppes
    over – mottaker kan ikke gjøre noe med dem uansett.
    """
    image_map = {}

    def walk(fo):
        items_out = []
        for it in fo.get('items', []):
            img = it.get('image')
            if not img or not os.path.exists(img):
                continue
            image_map[it['id']] = img
            items_out.append({
                'id':   it['id'],
                'name': it.get('name', ''),
                'ext':  os.path.splitext(img)[1].lower() or '.jpg',
                'size': os.path.getsize(img),
            })
        return {
            'id':         fo.get('id', ''),
            'name':       fo.get('name', ''),
            'color':      fo.get('color'),
            'items':      items_out,
            'subfolders': [walk(s) for s in fo.get('subfolders', [])],
        }

    manifest = {
        'app':     'kommunikasjonstavle',
        'version': 1,
        'folders': [walk(fo) for fo in folders],
    }
    return manifest, image_map


def manifest_totals(manifest):
    """Returnerer (antall_mapper, antall_bilder, total_bytes) for manifestet."""
    n_folders, n_images, total = 0, 0, 0

    def walk(fo):
        nonlocal n_folders, n_images, total
        n_folders += 1
        for it in fo.get('items', []):
            n_images += 1
            total += it.get('size', 0)
        for s in fo.get('subfolders', []):
            walk(s)

    for fo in manifest.get('folders', []):
        walk(fo)
    return n_folders, n_images, total


# ──────────────────────────────────────────────────────────────────────
#  Server – kjøres på den DELENDE enheten
# ──────────────────────────────────────────────────────────────────────

class SyncServer:
    """
    Liten lokal HTTP-server som deler ut et manifest og tilhørende
    bildefiler. Kjører i en egen daemon-tråd via ThreadingHTTPServer,
    slik at den ikke blokkerer Kivy sin hovedløkke.

    Port velges automatisk av OS (port=0) for å unngå konflikter –
    faktisk port er tilgjengelig via `.port` etter `start()`.
    """

    def __init__(self, manifest, image_map, code=None):
        self.manifest  = manifest
        self.image_map = dict(image_map)
        self.code      = code or make_code()
        self.port      = None
        self._httpd    = None
        self._thread   = None

    @property
    def running(self):
        return self._httpd is not None

    def start(self):
        if self._httpd:
            return
        manifest_bytes = json.dumps(self.manifest).encode('utf-8')
        image_map = self.image_map
        code      = self.code

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, fmt, *args):
                pass  # stille – ikke spam Android-logcat

            def _send_json(self, payload, status=200):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                try:
                    parsed = urllib.parse.urlparse(self.path)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if qs.get('code', [''])[0] != code:
                        self._send_json(b'{"error":"feil kode"}', 403)
                        return

                    if parsed.path == '/manifest':
                        self._send_json(manifest_bytes)
                        return

                    if parsed.path.startswith('/image/'):
                        item_id = urllib.parse.unquote(parsed.path[len('/image/'):])
                        src = image_map.get(item_id)
                        if not src or not os.path.exists(src):
                            self._send_json(b'{"error":"bilde ikke funnet"}', 404)
                            return
                        ctype = mimetypes.guess_type(src)[0] or 'application/octet-stream'
                        try:
                            with open(src, 'rb') as f:
                                data = f.read()
                        except OSError:
                            self._send_json(b'{"error":"lesefeil"}', 500)
                            return
                        self.send_response(200)
                        self.send_header('Content-Type', ctype)
                        self.send_header('Content-Length', str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return

                    self._send_json(b'{"error":"ukjent forespoersel"}', 404)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # klienten avbrøt – ufarlig

        self._httpd = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd  = None
            self._thread = None


# ──────────────────────────────────────────────────────────────────────
#  Klient – kjøres på den MOTTAKENDE enheten
# ──────────────────────────────────────────────────────────────────────

def fetch_manifest(ip, port, code, timeout=6):
    """Henter og parser /manifest fra den delende enheten. Kaster SyncError."""
    url = f'http://{ip}:{port}/manifest?code={urllib.parse.quote(str(code))}'
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise SyncError('Feil kode.')
        raise SyncError(f'Enheten svarte med feil {e.code}.')
    except urllib.error.URLError:
        raise SyncError(
            f'Fant ikke {ip}:{port}. Sjekk at begge enheter er på samme '
            f'WiFi, og at IP-adresse og port er riktig skrevet inn.')
    except (ValueError, OSError, json.JSONDecodeError) as e:
        raise SyncError(f'Feil ved tilkobling: {e}')


def download_image(ip, port, code, item_id, dest_path, timeout=25):
    """Laster ned ett bilde og skriver det til `dest_path`. Kaster SyncError."""
    url = (f'http://{ip}:{port}/image/{urllib.parse.quote(item_id)}'
           f'?code={urllib.parse.quote(str(code))}')
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise SyncError(f'Nedlasting feilet ({e.code}).')
    except urllib.error.URLError as e:
        raise SyncError(f'Nedlasting feilet: {e.reason}.')
    with open(dest_path, 'wb') as f:
        f.write(data)
