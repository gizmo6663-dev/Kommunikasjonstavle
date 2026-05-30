#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frame_screenshots.py - Tegner realistiske mobilrammer og lager kompatibilitetsrapport

Dette skriptet:
- Leser inn 6 screenshots fra emulatorjobbene
- Tegner realistiske iOS/Android-lignende mobilrammer med PIL
- Setter dem i et 3×2-rutenett
- Lagrer resultat som testing/compatibility-report.png
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from datetime import datetime
import json


def tegn_mobilramme(screenshot_path, er_tablet=False):
    """
    Tegner en realistisk mobilramme rundt skjermbildet.
    
    Args:
        screenshot_path: Sti til skjermbildet
        er_tablet: True hvis det er en tablet (annen proporsjoner, webkamera i bezel)
    
    Returns:
        PIL.Image med ramme
    """
    # Åpner original-screenshottet
    screenshot = Image.open(screenshot_path)
    screen_w, screen_h = screenshot.size
    
    # Beregner rammeproporsjoner basert på enhetstype
    if er_tablet:
        ramme_bredde = 60  # Tykk bezel for tablet
        ramme_hoyde_topp = 80
        ramme_hoyde_bunn = 60
        corner_radius = 40
        har_kameraknast = False
    else:
        ramme_bredde = 50  # Sidekanter
        ramme_hoyde_topp = 120  # Plass til notch/kamera
        ramme_hoyde_bunn = 100
        corner_radius = int(screen_w * 0.08)  # 8 % av skjermbredden
        har_kameraknast = True
    
    # Lager ny ramme med sorte kanter
    ramme_w = screen_w + (ramme_bredde * 2)
    ramme_h = screen_h + ramme_hoyde_topp + ramme_hoyde_bunn
    ramme = Image.new('RGB', (ramme_w, ramme_h), color=(0, 0, 0))
    
    # Tegner avrundede hjørner
    _tegn_avrundede_hjorner(ramme, ramme_w, ramme_h, corner_radius)
    
    # Kleiner inn skjermbildet
    ramme.paste(screenshot, (ramme_bredde, ramme_hoyde_topp))
    
    # Tegner detaljer
    draw = ImageDraw.Draw(ramme)
    
    # Indre lysegrå kant (simulerer skjermkant)
    kant_farge = (80, 80, 80)
    kant_tykkelse = 3
    draw.rectangle(
        [
            (ramme_bredde - kant_tykkelse, ramme_hoyde_topp - kant_tykkelse),
            (ramme_bredde + screen_w + kant_tykkelse, ramme_hoyde_topp + screen_h + kant_tykkelse)
        ],
        outline=kant_farge,
        width=kant_tykkelse
    )
    
    # Tegner kameraknast hvis ikke tablet
    if har_kameraknast:
        kamera_x = ramme_w // 2
        kamera_y = ramme_hoyde_topp - 70
        kamera_radius = 18
        draw.ellipse(
            [
                (kamera_x - kamera_radius, kamera_y - kamera_radius),
                (kamera_x + kamera_radius, kamera_y + kamera_radius)
            ],
            fill=(10, 10, 10),
            outline=(30, 30, 30),
            width=2
        )
        # Lite refleks på kameralinsa
        draw.ellipse(
            [
                (kamera_x - 6, kamera_y - 6),
                (kamera_x - 2, kamera_y - 2)
            ],
            fill=(40, 40, 40)
        )
    else:
        # Webkamera sentrert i bezel for tablet
        kamera_x = ramme_w // 2
        kamera_y = ramme_hoyde_topp // 2
        kamera_radius = 16
        draw.ellipse(
            [
                (kamera_x - kamera_radius, kamera_y - kamera_radius),
                (kamera_x + kamera_radius, kamera_y + kamera_radius)
            ],
            fill=(10, 10, 10),
            outline=(40, 40, 40),
            width=2
        )
    
    # Tegner høyttalerrist (to tynne avrundede rektangler)
    hoyttaler_y = ramme_hoyde_topp - 40
    hoyttaler_tykkelse = 3
    for offset in [-8, 8]:
        draw.rectangle(
            [
                (ramme_w // 2 - 30 + offset, hoyttaler_y - hoyttaler_tykkelse),
                (ramme_w // 2 + 30 + offset, hoyttaler_y + hoyttaler_tykkelse)
            ],
            fill=(30, 30, 30)
        )
    
    # Tegner volum-knapper på venstre side
    knapp_x = ramme_bredde - 8
    for i, y_offset in enumerate([120, 180, 240]):
        knapp_y = ramme_hoyde_topp + y_offset
        draw.rectangle(
            [
                (knapp_x - 6, knapp_y - 20),
                (knapp_x + 2, knapp_y + 20)
            ],
            fill=(40, 40, 40),
            outline=(60, 60, 60),
            width=1
        )
    
    # Tegner strømknapp på høyre side
    strom_y = ramme_hoyde_topp + 150
    draw.rectangle(
        [
            (ramme_w - ramme_bredde + 4, strom_y - 25),
            (ramme_w - ramme_bredde + 12, strom_y + 25)
        ],
        fill=(40, 40, 40),
        outline=(60, 60, 60),
        width=1
    )
    
    return ramme


def _tegn_avrundede_hjorner(bilde, bredde, hoyde, radius):
    """
    Tegner avrundede hjørner på bilde ved å sette hjørner til gjennomsiktig.
    (Hjørner blir svart pga. bakgrunnsfarge)
    """
    draw = ImageDraw.Draw(bilde)
    
    # Tegner sorte avrundede kvadrater på hjørnene for å lage avrundingen
    for x, y in [(0, 0), (bredde - radius, 0), 
                  (0, hoyde - radius), (bredde - radius, hoyde - radius)]:
        draw.rectangle(
            [(x, y), (x + radius, y + radius)],
            fill=(0, 0, 0)
        )


def les_test_resultat(enhet_navn):
    """
    Leser test_result.json for en enhet og returnerer status.
    
    Returns:
        (passed: bool, startup_time: float)
    """
    try:
        with open(f"test_result_{enhet_navn}.json", "r") as f:
            data = json.load(f)
            return data.get("passed", 0) == 1, data.get("startup_time_seconds", 0)
    except FileNotFoundError:
        return False, 0
    except json.JSONDecodeError:
        return False, 0


def main():
    """Hovedfunksjon - tegner rammer og lager rapport."""
    
    # Definerer de 6 enhetene
    enheter = [
        {
            "navn": "moto-g-api26",
            "label": "Moto G",
            "android": "Android 8 (API 26)",
            "display": "360×640 dp",
            "tablet": False
        },
        {
            "navn": "xperia-10-api28",
            "label": "Xperia 10",
            "android": "Android 9 (API 28)",
            "display": "360×780 dp",
            "tablet": False
        },
        {
            "navn": "galaxy-a-api30",
            "label": "Galaxy A-serien",
            "android": "Android 11 (API 30)",
            "display": "412×892 dp",
            "tablet": False
        },
        {
            "navn": "pixel-7-api33",
            "label": "Pixel 7",
            "android": "Android 13 (API 33)",
            "display": "393×851 dp",
            "tablet": False
        },
        {
            "navn": "galaxy-s-api34",
            "label": "Galaxy S-flaggskip",
            "android": "Android 14 (API 34)",
            "display": "412×916 dp",
            "tablet": False
        },
        {
            "navn": "tablet-api34",
            "label": "Galaxy Tab A",
            "android": "Android 14 (API 34)",
            "display": "800×1280 dp",
            "tablet": True
        }
    ]
    
    # Tegner rammer rundt hvert screenshot
    rammet_bilder = []
    enhet_statuser = []
    
    for enhet in enheter:
        screenshot_sti = f"screenshot_{enhet['navn']}.png"
        
        # Sjekker om screenshot eksisterer
        if not Path(screenshot_sti).exists():
            print(f"⚠️  Advarsel: {screenshot_sti} ikke funnet")
            # Lager et grått placeholder-bilde
            placeholder = Image.new('RGB', (480, 854), color=(200, 200, 200))
            rammet_bilde = tegn_mobilramme(placeholder, er_tablet=enhet['tablet'])
            enhet_statuser.append((enhet, False))
        else:
            rammet_bilde = tegn_mobilramme(screenshot_sti, er_tablet=enhet['tablet'])
            # Prøver å lese test-resultat
            passed, _ = les_test_resultat(enhet['navn'])
            enhet_statuser.append((enhet, passed))
        
        rammet_bilder.append(rammet_bilde)
    
    # Lager et 3×2-rutenett
    # Beregner målstørrelser for hvert mockup
    mockup_bredde = 320
    mockup_hoyde = 640
    
    # Skalerer alle bildet til samme størrelse
    skalerte_bilder = []
    for rammet_bilde in rammet_bilder:
        skalert = rammet_bilde.resize((mockup_bredde, mockup_hoyde), Image.Resampling.LANCZOS)
        skalerte_bilder.append(skalert)
    
    # Padding mellom bilder
    padding_h = 40
    padding_v = 60
    
    # Tekst-høyde under hvert bilde
    tekst_hoyde = 120
    
    # Beregner totalt rutenett-størrelse (3 kolonner × 2 rader)
    rutenettsbredde = (mockup_bredde * 3) + (padding_h * 2)
    rutenetthoyde = (mockup_hoyde * 2) + (tekst_hoyde * 2) + (padding_v * 3)
    
    # Lager bakgrund med hvit farge
    rapport_bilde = Image.new('RGB', (rutenettsbredde + 40, rutenetthoyde + 180), color=(255, 255, 255))
    rapport_draw = ImageDraw.Draw(rapport_bilde)
    
    # Tegner tittel
    tittel = "Kommunikasjonstavle – Kompatibilitetstesting"
    dato_tekst = f"Dato: {datetime.now().strftime('%d. %B %Y')}"
    
    # Prøver å laste en fin font, faller tilbake til default
    try:
        tittel_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        dato_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        status_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except (IOError, OSError):
        tittel_font = ImageFont.load_default()
        dato_font = ImageFont.load_default()
        info_font = ImageFont.load_default()
        status_font = ImageFont.load_default()
    
    # Tegner tittel
    rapport_draw.text((20, 20), tittel, fill=(0, 0, 0), font=tittel_font)
    rapport_draw.text((20, 70), dato_tekst, fill=(100, 100, 100), font=dato_font)
    
    # Plasserer bildet i 3×2-rutenett med tekst under
    y_offset = 130
    for rad in range(2):
        x_offset = 20
        for kolonne in range(3):
            indeks = (rad * 3) + kolonne
            
            if indeks < len(skalerte_bilder):
                enhet, passed = enhet_statuser[indeks]
                bilde = skalerte_bilder[indeks]
                
                # Plasserer rammet bilde
                rapport_bilde.paste(bilde, (x_offset, y_offset))
                
                # Tegner enhetsinformasjon under
                tekst_y = y_offset + mockup_hoyde + 10
                
                # Enhetsnavn
                rapport_draw.text(
                    (x_offset + 5, tekst_y),
                    enhet['label'],
                    fill=(0, 0, 0),
                    font=ImageFont.load_default()
                )
                
                # Android-versjon
                rapport_draw.text(
                    (x_offset + 5, tekst_y + 18),
                    enhet['android'],
                    fill=(60, 60, 60),
                    font=ImageFont.load_default()
                )
                
                # Skjermstørrelse
                rapport_draw.text(
                    (x_offset + 5, tekst_y + 36),
                    enhet['display'],
                    fill=(60, 60, 60),
                    font=ImageFont.load_default()
                )
                
                # Status
                status_tekst = "✓ Bestått" if passed else "✗ Feilet"
                status_farge = (34, 139, 34) if passed else (220, 20, 60)  # Grønn eller rød
                
                # Tegner bakgrunn for status
                bbox = rapport_draw.textbbox((x_offset + 5, tekst_y + 54), status_tekst, font=status_font)
                rapport_draw.rectangle(
                    [
                        (bbox[0] - 5, bbox[1] - 2),
                        (bbox[2] + 5, bbox[3] + 2)
                    ],
                    fill=status_farge
                )
                
                # Tegner status-tekst
                rapport_draw.text(
                    (x_offset + 5, tekst_y + 54),
                    status_tekst,
                    fill=(255, 255, 255),
                    font=status_font
                )
            
            x_offset += mockup_bredde + padding_h
        
        y_offset += mockup_hoyde + tekst_hoyde + padding_v
    
    # Lager testing-mappen hvis den ikke finnes
    Path("testing").mkdir(exist_ok=True)
    
    # Lagrer rapporten
    rapport_bilde.save("testing/compatibility-report.png", quality=95)
    print("✅ Kompatibilitetsrapport lagret: testing/compatibility-report.png")


if __name__ == "__main__":
    main()
