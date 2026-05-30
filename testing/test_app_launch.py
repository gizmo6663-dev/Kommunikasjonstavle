#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_app_launch.py - ADB-basert testskript for app-oppstart og stabilitet

Dette skriptet:
- Starter appen via adb shell am start
- Sjekker for krasj via logcat
- Verifiserer at prosessen kjører
- Dumper UI-hierarki og sjekker for forventede UI-elementer
- Genererer JSON-rapport med resultat
- Returnerer exit-kode 0 ved suksess, 1 ved feil
"""

import subprocess
import time
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# Konstanter
APP_PACKAGE = "no.askapp.kommunikasjonstavle"
APP_ACTIVITY = f"{APP_PACKAGE}/.org.kivy.android.PythonActivity"
STARTUP_TIMEOUT = 12
LOGCAT_WAIT = 5  # Sekunder å vente før å sjekke logcat
EXPECTED_UI_ELEMENTS = [
    "Kommunikasjonstavle",
    "Rekker",
    "Hjem",
    "Dagsplan"
]


def run_adb_command(command):
    """
    Kjører en ADB-kommando og returnerer output.
    
    Args:
        command: ADB-kommando som string eller liste
    
    Returns:
        (stdout: str, stderr: str, returncode: int)
    """
    try:
        if isinstance(command, str):
            command = ["adb"] + command.split()
        else:
            command = ["adb"] + command
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout, result.stderr, result.returncode
    
    except subprocess.TimeoutExpired:
        return "", "ADB-kommando tidsavbrutt", -1
    except Exception as e:
        return "", str(e), -1


def start_app():
    """
    Starter appen via adb shell am start.
    
    Returns:
        (success: bool, message: str)
    """
    print(f"🚀 Starter app: {APP_PACKAGE}")
    
    # Sjekker at enheten er koblet til
    stdout, stderr, rc = run_adb_command("devices")
    if rc != 0:
        return False, "ADB devices kommando feilet"
    
    if "no permissions" in stderr.lower():
        return False, "ADB permissions denied"
    
    # Starter app-aktiviteten
    stdout, stderr, rc = run_adb_command(f"shell am start -n {APP_ACTIVITY}")
    
    if rc != 0:
        return False, f"Feil ved start av app: {stderr}"
    
    if "Error" in stdout or "error" in stdout.lower():
        return False, f"AM start returnerte feil: {stdout}"
    
    print(f"✓ App-startkommando sendt")
    return True, "App startet"


def wait_for_startup(timeout=STARTUP_TIMEOUT):
    """
    Venter på at appen skal starte opp.
    
    Args:
        timeout: Maksimalt antall sekunder å vente
    
    Returns:
        (success: bool, startup_time: float)
    """
    print(f"⏳ Venter på app-oppstart (maks {timeout} sekunder)...")
    
    start_time = time.time()
    
    for i in range(timeout):
        elapsed = time.time() - start_time
        
        # Sjekker om prosessen finnes
        stdout, _, rc = run_adb_command("shell ps")
        
        if rc == 0 and APP_PACKAGE in stdout:
            print(f"✓ App prosess opprettet etter {elapsed:.1f} sekunder")
            return True, elapsed
        
        # Prøver ikke oftere enn hver halvt sekund
        time.sleep(0.5)
    
    return False, timeout


def check_for_crash(delay=LOGCAT_WAIT):
    """
    Sjekker logcat for feil-indikasjon.
    
    Args:
        delay: Sekunder å vente før sjekk
    
    Returns:
        (crashed: bool, error_message: str)
    """
    print(f"⏸️  Venter {delay} sekunder før logcat-sjekk...")
    time.sleep(delay)
    
    print("🔍 Sjekker logcat for krasj...")
    
    # Dumper siste 100 linjer av logcat
    stdout, stderr, rc = run_adb_command("logcat -d -t 100")
    
    if rc != 0:
        return False, "Kunne ikke lese logcat"
    
    # Sjekker for kritiske feil
    crash_indicators = [
        "FATAL EXCEPTION",
        f"Process: {APP_PACKAGE}",
        "AndroidRuntime: FATAL",
        "java.lang.RuntimeException",
        "java.lang.NullPointerException"
    ]
    
    for indicator in crash_indicators:
        if indicator in stdout:
            # Forsøker å finne mer kontekst omkring feilen
            lines = stdout.split('\n')
            for i, line in enumerate(lines):
                if indicator in line:
                    context_start = max(0, i - 2)
                    context_end = min(len(lines), i + 5)
                    context = '\n'.join(lines[context_start:context_end])
                    return True, f"Feil oppdaget: {indicator}\n{context}"
    
    print("✓ Ingen krasj-indikatorer funnet")
    return False, ""


def verify_process_alive():
    """
    Sjekker at prosessen kjører via adb shell ps.
    
    Returns:
        (alive: bool, pid: str)
    """
    print("📋 Sjekker at prosess kjører...")
    
    stdout, stderr, rc = run_adb_command("shell ps")
    
    if rc != 0:
        return False, ""
    
    # Søker etter app-prosessen
    for line in stdout.split('\n'):
        if APP_PACKAGE in line:
            # Prøver å hente PID (vanligvis andre kolonne)
            parts = line.split()
            if len(parts) > 1:
                return True, parts[1]
    
    return False, ""


def dump_ui_hierarchy():
    """
    Dumper UI-hierarki via uiautomator og returnerer XML-innhold.
    
    Returns:
        (success: bool, xml_content: str)
    """
    print("📱 Dumper UI-hierarki...")
    
    # Rydder tidligere dump
    run_adb_command("shell rm -f /sdcard/window_dump.xml")
    time.sleep(0.5)
    
    # Dumper nytt hierarki
    stdout, stderr, rc = run_adb_command("shell uiautomator dump /sdcard/window_dump.xml")
    
    if rc != 0:
        return False, ""
    
    time.sleep(1)
    
    # Henter dumpen fra enheten
    stdout, stderr, rc = run_adb_command("pull /sdcard/window_dump.xml -")
    
    if rc != 0:
        return False, ""
    
    return True, stdout


def check_ui_elements(xml_content):
    """
    Sjekker om forventede UI-elementer finnes i XML-hierarkiet.
    
    Args:
        xml_content: XML-innhold fra uiautomator dump
    
    Returns:
        (found_elements: list, missing_elements: list)
    """
    print("🔎 Søker etter UI-elementer...")
    
    found = []
    missing = []
    
    for element_name in EXPECTED_UI_ELEMENTS:
        if element_name in xml_content:
            found.append(element_name)
            print(f"  ✓ Funnet: {element_name}")
        else:
            missing.append(element_name)
            print(f"  ✗ Mangler: {element_name}")
    
    return found, missing


def generate_json_report(passed, crash_detected, ui_elements_found, startup_time):
    """
    Genererer JSON-rapport over test-resultat.
    
    Args:
        passed: bool - om testen var vellykket
        crash_detected: bool - om krasj ble oppdaget
        ui_elements_found: int - antall UI-elementer funnet
        startup_time: float - oppstart-tid i sekunder
    
    Returns:
        dict med rapport-data
    """
    report = {
        "passed": 1 if passed else 0,
        "crash_detected": 1 if crash_detected else 0,
        "ui_element_found": ui_elements_found,
        "startup_time_seconds": round(startup_time, 2),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return report


def main():
    """Hovedfunksjon - kjører alle tester."""
    
    print("=" * 60)
    print("Kommunikasjonstavle - App-starttestskript")
    print("=" * 60)
    print()
    
    test_result = {
        "passed": False,
        "crash_detected": False,
        "startup_time": 0,
        "errors": []
    }
    
    # Steg 1: Start app
    print("[1/5] Starter app...")
    success, msg = start_app()
    if not success:
        test_result["errors"].append(f"Start feilet: {msg}")
        print(f"❌ {msg}\n")
        startup_time = 0
    else:
        print(f"✅ {msg}\n")
        
        # Steg 2: Vent på oppstart
        print("[2/5] Venter på oppstart...")
        success, startup_time = wait_for_startup()
        if not success:
            test_result["errors"].append("App startet ikke innen timeout")
            print("❌ App startet ikke innen timeout\n")
            startup_time = STARTUP_TIMEOUT
        else:
            print(f"✅ App startet etter {startup_time:.1f}s\n")
    
    # Steg 3: Sjekk for krasj
    print("[3/5] Sjekker for krasj...")
    crashed, crash_msg = check_for_crash()
    test_result["crash_detected"] = crashed
    if crashed:
        test_result["errors"].append(crash_msg)
        print(f"❌ Krasj oppdaget:\n{crash_msg}\n")
    else:
        print("✅ Ingen krasj\n")
    
    # Steg 4: Verifiser prosess
    print("[4/5] Verifiserer prosess-status...")
    alive, pid = verify_process_alive()
    if not alive:
        test_result["errors"].append("Prosess ikke funnet")
        print("❌ Prosess ikke funnet\n")
    else:
        print(f"✅ Prosess kjører (PID: {pid})\n")
    
    # Steg 5: Dump UI og sjekk elementer
    print("[5/5] Sjekker UI-hierarki...")
    success, xml_content = dump_ui_hierarchy()
    if not success:
        test_result["errors"].append("UI-dump feilet")
        print("❌ Kunne ikke dumpe UI-hierarki\n")
        found_count = 0
    else:
        found, missing = check_ui_elements(xml_content)
        found_count = len(found)
        if len(found) == 0:
            print("⚠️  Ingen forventede elementer funnet\n")
        else:
            print(f"✅ {len(found)} av {len(EXPECTED_UI_ELEMENTS)} elementer funnet\n")
    
    # Bestemmer overordnet resultat
    test_result["passed"] = (
        not crashed and 
        alive and 
        startup_time < STARTUP_TIMEOUT and
        found_count > 0
    )
    
    test_result["startup_time"] = startup_time
    test_result["ui_elements_found"] = found_count
    
    # Genererer JSON-rapport
    json_report = generate_json_report(
        test_result["passed"],
        test_result["crash_detected"],
        test_result["ui_elements_found"],
        test_result["startup_time"]
    )
    
    # Lagrer rapport
    report_path = Path("test_result.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    
    print("=" * 60)
    print("RESULTAT")
    print("=" * 60)
    print(f"Samlet status: {'✅ BESTÅTT' if test_result['passed'] else '❌ FEILET'}")
    print(f"Oppstarttid: {test_result['startup_time']:.1f}s")
    print(f"Krasj oppdaget: {'Ja' if test_result['crash_detected'] else 'Nei'}")
    print(f"UI-elementer funnet: {test_result['ui_elements_found']}/{len(EXPECTED_UI_ELEMENTS)}")
    
    if test_result["errors"]:
        print("\nFeil oppstått:")
        for error in test_result["errors"]:
            print(f"  • {error}")
    
    print(f"\nJSON-rapport lagret: {report_path}")
    print("=" * 60)
    
    # Returnerer exit-kode basert på resultat
    exit_code = 0 if test_result["passed"] else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
