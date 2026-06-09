# assets/bilder/ – Bundlede bilder

Bilder du legger her pakkes automatisk med i APK-en og importeres
til appen ved første oppstart (eller ved ny `BUNDLE_VERSION`).

## Mappestruktur

```
assets/
  bilder/
    Spising/          ← blir en bildetavle-mappe i appen
      spise.png
      drikke.jpg
    Påkledning/
      bukse.png
      genser.png
    Følelser/
      glad.png
      lei_seg.png
```

## Regler

- **Mappenavn** → tittel på bildetavle-mappen i appen
- **Filnavn** → bildenavn i appen (`spise.png` → «spise», `lei_seg.png` → «lei seg»)
- Støttede format: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`
- Eksisterende brukerdata overskrives **ikke**
- For å tvinge re-import (f.eks. etter store endringer): øk `BUNDLE_VERSION`
  i `_init_bundled_assets()` i `main.py`

## Oppdatere bundlede bilder

1. Legg til/endre bilder i riktig undermappe
2. Øk `BUNDLE_VERSION = X` i `_init_bundled_assets()` i `main.py`
3. Push → GitHub Actions bygger ny APK
4. Ved neste app-start importeres de nye bildene automatisk

## Merk

`buildozer.spec` inkluderer `assets/` via:
```
source.include_patterns = assets/**/*, ...
```
