# Kommunikasjonstavle – Android Kompatibilitetstest

## Oversikt

Dette testmiljøet kjører **Kommunikasjonstavle** på 6 ulike Android-emulatorkonfigurasjoner via GitHub Actions for å verifisere stabilitet og UI-kompatibilitet på tvers av enheter.

## Hvorfor iOS ikke er med

iOS-testing er **bevisst utelatt** fra dette oppsettet. Grunner:

- **kivy-ios** krever **macOS** og **Xcode**
- GitHub Actions `ubuntu-latest`-runner har ikke macOS tilgjengelig (krever betalt macOS-runner)
- **Arkitektur-forskjell**: iOS bygges som en universal binary (ARM64/ARM7s), mens Android bruker APK
- iOS-testing kreves derfor som et **separat fremtidig prosjekt** med dedikert CI/CD-oppsett

Se [Apple's App Store Connect](https://appstoreconnect.apple.com/) for fremtidig iOS-distribusjon.

---

## Enhetsprofiler – Hvorfor disse 6?

Hver konfigurasjon er valgt basert på **norske markedsandeler** og tekniske varianter som berører UI-layout:

| # | Enhet | Android | API | Skjerm (dp) | DPI | Arkitektur | Valgt for |
|---|-------|---------|-----|-------------|-----|-----------|-----------|
| 1 | **Moto G** | 8.0 | 26 | 360×640 | hdpi | x86 | Lavbudsjett-segment, gamle Android, håndholdt |
| 2 | **Sony Xperia 10** | 9.0 | 28 | 360×780 | xhdpi | x86 | Smal 21:9-format (edge-case for layout) |
| 3 | **Galaxy A-serien** | 11 | 30 | 412×892 | xxhdpi | x86_64 | Populær i Norge, mid-range |
| 4 | **Google Pixel 7** | 13 | 33 | 393×851 | 420dpi | x86_64 | Stock Android, standarder-lederskap |
| 5 | **Galaxy S-flaggskip** | 14 | 34 | 412×916 | 560dpi | x86_64 | Premium, høy DPI, OneUI 6 |
| 6 | **Galaxy Tab A** | 14 | 34 | 800×1280 | xhdpi | x86_64 | Nettbrett, større skjerm |

**Kombinasjon av faktorer:**
- API-nivåer dekker Android 8 → 14
- Skjermstørrelse: 360dp (smal) → 800dp (tablet)
- DPI: hdpi → xxhdpi (testerer skalering)
- Arkitektur: x86 (eldre emulator-standard) → x86_64 (moderne)

---

## Workflowen – Hvordan den utløses

### Automatisk utløsing
Workflowen `compatibility-test.yml` kjøres **automatisk** når `build-apk.yml` fullføres:

```yaml
on:
  workflow_run:
    workflows: ['Build APK']
    types: [completed]
```

### Manuell utløsing
Kan også startes manuelt fra GitHub Actions UI:

1. Gå til **Actions** tab i repoet
2. Velg **"Android Kompatibilitetstest"**
3. Klikk **"Run workflow"**

---

## Workflow-struktur

```
┌─────────────────────────────────────┐
│  Build APK (build-apk.yml)          │
│  ✓ Lagrer artefakt: app-release.apk │
└──────────────────┬──────────────────┘
                   │
                   ▼ (workflow_run trigger)
┌─────────────────────────────────────────────────┐
│  6 parallelle emulatorkonfigurasjoner            │
├─────────────────────────────────────────────────┤
│ [API 26] [API 28] [API 30] [API 33] [API 34a] [API 34b] │
│   Moto G  Xperia  Galaxy A Pixel 7  Galaxy S  Tablet    │
└────────┬──────────┬────────┬────────┬─────────┬────────┘
         │ Download APK
         │ Install APK
         │ Run test_app_launch.py
         │ adb screencap > screenshot_X.png
         │ Upload screenshot
         └───────────────┬──────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────────┐
         │  Sammenstillingsjobb             │
         │  (compatibility-report)          │
         ├──────────────────────────────────┤
         │ • Download alle 6 screenshots    │
         │ • Kjør frame_screenshots.py      │
         │ • Tegn mobilrammer + layout      │
         │ • Lagr: compatibility-report.png │
         └──────────────────────────────────┘
```

**Estimert kjøretid:** 12–15 minutter totalt (6 emulatorer kjøres **parallelt**)

---

## Lesing av resultat

### Via GitHub Actions
1. Gå til **Actions** > **Android Kompatibilitetstest** > **seneste run**
2. **Artifacts** seksjon inneholder:
   - `compatibility-report.png` – visuelle resultat for alle 6 enheter
   - `compatibility-screenshots` – individuelle screenshots
   - `test-results` – JSON-rapporter fra hver enhet

### Tolking av rapporten
- **✓ Bestått (grønn bakgrunn)** – Appen startet, ingen krasj, UI-elementer funnet
- **✗ Feilet (rød bakgrunn)** – Krasj, UI-element mangler, eller oppstart-timeout

---

## Begrenninger

### 1. Emulator vs. ekte hardware
Emulatorer simulerer Android, men **ikke** all oppførsel:

| Aspekt | Emulator | Ekte enhet |
|--------|----------|-----------|
| Nettverk | Simulert (langsomere) | Reelt |
| Sensorer | Simulert (GPS, accel) | Reelt |
| Minne | 2048 MB fast | Variabel |
| Intern lagring | 1024 MB partition | Variabel |
| Grafikkmotor | swiftshader_indirect | GPU-akselerert |
| Android-versjon | Eksakt | Kan variere med OS-oppdatering |

### 2. Produsent-spesifikk oppførsel
- **OneUI (Samsung)** – Custom launcher, dekstorator, permisjonsadministrasjon
- **MIUI (Xiaomi)** – Aggressive background-doding
- **ColorOS (OPPO/OnePlus)** – RAM-management

Disse fanges **ikke** av emulator. For Samsung-spesifikk testing, se [Samsung Remote Test Lab](#samsung-remote-test-lab).

### 3. Kivy-spesifikke begrensninger
- **JNI/pyjnius** – Avhengig av p4a/buildozer (testet implisitt)
- **Canvas-rendering** – GPU-simulert, ikke identisk med ekte enhet
- **Android-tillatelser** – Simulert i emulator

### 4. Tid og ressurser
- Hver emulator-jobb tar **~2 minutter** (nedlasting, oppstart, test, screenshot)
- 6 parallelle jobber + 1 sammenstilling = **~12 min** total

---

## Feilsøking

### Emulator startet ikke
**Symptom:** "Timeout waiting for device"

**Løsning:**
```bash
# Kontroller emulator-logg i workflow
adb logcat

# Redusr antall emulator-jobber (edit matrix i yml)
```

### Screenshot mangler
**Symptom:** `screenshot_X.png` ikke lastet opp

**Løsning:**
```bash
adb exec-out screencap -p > screenshot.png
# Hvis svart: device ikke låst opp (adb shell input keyevent 82)
```

### Test bestod lokalt, mislyktes i CI
**Mulige årsaker:**
- Annen APK-versjon
- Forskjellig Android-API-niveau
- Nettverk-avhengighet (Kivy nedlaster ressurser?)

**Debug:**
1. Last ned samme APK fra Artifacts
2. Kjør på lokal emulator med samme API-nivå
3. Sammenlikn logcat: `adb logcat > local.log`

---

## Samsung Remote Test Lab

For **Samsung-spesifikk testing** (OneUI, Galaxy S/A/Tab):

1. Gå til https://developer.samsung.com/remote-test-lab/
2. Login med Samsung-konto
3. Velg enhet fra Samsung-katalog
4. Last opp APK → tester live på ekte enhet
5. Mottaker rapport + screenshots

**Fordeler:**
- Ekte enhet (ikke emulator)
- OneUI-spesifikk oppførsel
- Offline-sertifisering

---

## Oppsett lokalt (valgfritt)

Hvis du vil kjøre tester lokalt uten GitHub Actions:

```bash
# Forutsetning: Android SDK installert, emulator konfigurert

# 1. Bygg APK
cd prosjektrot/
buildozer android release

# 2. Start emulator
emulator @Pixel_API_34 -no-window -no-audio -gpu swiftshader_indirect &

# 3. Installer APK
adb install -g bin/kommunikasjonstavle-release-*.apk

# 4. Kjør test
cd testing/
python test_app_launch.py

# 5. Ta screenshot
adb exec-out screencap -p > screenshot.png

# 6. Tegn ramme (hvis du har bilder fra flere enheter)
python frame_screenshots.py
```

---

## Filene i denne mappen

```
testing/
├── compatibility-test.yml     # GitHub Actions workflow
├── test_app_launch.py         # ADB-testskript (Python)
├── frame_screenshots.py       # Rammtegning + rapport (Python)
├── README.md                  # Denne filen
└── compatibility-report.png   # Generert ved kjøring
```

---

## Kontakt & Bidrag

Hvis du oppdager problemer med emulatorkonfigurasjoner eller manglende enhetsprofiler, oppretts en issue med:

- **Enhetsnavn / Android-versjon**
- **Markedsandel i Norge** (kilder: IDC, Statista)
- **Tekniske aspekter** (skjermstørrelse, DPI, API-nivå som gjør den unik)

---

## Lisensiering

Denne testinfrastrukturen er del av **Kommunikasjonstavle** og følger samme lisensiering.

**Sist oppdatert:** 2026-05-30
