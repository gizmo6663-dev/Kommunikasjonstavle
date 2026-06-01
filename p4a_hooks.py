"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.

p4a v2024.01.21 kaller before_apk_build og before_apk_assemble.
ctx er et p4a-toolchain-objekt, ikke et Buildozer-objekt –
root_dir finnes via ctx.build_dir eller hardkodet hostcwd-sti.
"""
import os
import glob
import shutil


def before_apk_build(ctx, *args, **kwargs):
    print("=== p4a_hooks: before_apk_build KALT ===")
    _run_hook(ctx)


def before_apk_assemble(ctx, *args, **kwargs):
    print("=== p4a_hooks: before_apk_assemble KALT ===")
    _run_hook(ctx)


def _get_root(ctx):
    # Prøv ulike attributter på ctx
    for attr in ('build_dir', 'dist_dir', 'storage_dir'):
        val = getattr(ctx, attr, None)
        if val:
            val = str(val)
            # Gå opp i mappetreet til vi finner main.py
            candidate = val
            for _ in range(8):
                if os.path.exists(os.path.join(candidate, 'main.py')):
                    return candidate
                candidate = os.path.dirname(candidate)

    # Hardkodet fallback – GitHub Actions Docker-volum
    for candidate in ['/home/user/hostcwd', '/hostcwd', os.getcwd()]:
        if os.path.exists(os.path.join(candidate, 'main.py')):
            return candidate

    return None


def _run_hook(ctx):
    root = _get_root(ctx)
    if not root:
        print("p4a_hooks: klarte ikke finne root_dir, avbryter")
        # Debug: print ctx-attributter
        print(f"p4a_hooks: ctx type = {type(ctx)}")
        print(f"p4a_hooks: ctx attrs = {[a for a in dir(ctx) if not a.startswith('__')][:20]}")
        return

    print(f"p4a_hooks: root = {root}")
    res_src  = os.path.join(root, 'res')
    java_src = os.path.join(root, 'java')
    print(f"p4a_hooks: res eksisterer: {os.path.exists(res_src)}")
    print(f"p4a_hooks: java eksisterer: {os.path.exists(java_src)}")

    # Finn src/main/ via glob
    pattern = os.path.join(
        root, '.buildozer', 'android', 'platform',
        'build-*', 'dists', '*', 'src', 'main')
    matches = glob.glob(pattern)
    print(f"p4a_hooks: src/main/ treff: {matches}")

    if not matches:
        print("p4a_hooks: fant ikke src/main/, avbryter")
        return

    for main_dir in matches:
        print(f"p4a_hooks: behandler {main_dir}")

        # ── 1. res/xml/kt_widget_info.xml – skriv direkte ───────
        # Kopierer IKKE hele res/-mappen – det krasjer AAPT2.
        # Skriver kt_widget_info.xml direkte til riktig sti.
        xml_dst = os.path.join(main_dir, 'res', 'xml')
        os.makedirs(xml_dst, exist_ok=True)
        widget_info = os.path.join(xml_dst, 'kt_widget_info.xml')
        with open(widget_info, 'w', encoding='utf-8') as wf:
            wf.write('''<?xml version="1.0" encoding="utf-8"?>
<appwidget-provider
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:minWidth="180dp"
    android:minHeight="110dp"
    android:minResizeWidth="120dp"
    android:minResizeHeight="80dp"
    android:targetCellWidth="3"
    android:targetCellHeight="2"
    android:updatePeriodMillis="1800000"
    android:resizeMode="horizontal|vertical"
    android:widgetCategory="home_screen" />
''')
        print(f"p4a_hooks: skrev kt_widget_info.xml -> {widget_info}")

        # ── 2. Java – håndteres av android.add_src i buildozer.spec ─
        print("p4a_hooks: java kopieres via android.add_src (ikke hooken)")

        # ── 3. Patch AndroidManifest.xml ──────────────────────────
        manifest = os.path.join(main_dir, 'AndroidManifest.xml')
        if not os.path.exists(manifest):
            print(f"p4a_hooks: manifest ikke funnet: {manifest}")
            continue

        with open(manifest, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'KtWidget' in content:
            print("p4a_hooks: KtWidget allerede i manifest")
            continue

        receiver_block = '''
        <receiver
            android:name="no.askapp.kommunikasjonstavle.KtWidget"
            android:exported="true"
            android:label="Dagsrytme">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/kt_widget_info" />
        </receiver>'''

        if '</application>' in content:
            content = content.replace(
                '</application>',
                receiver_block + '\n    </application>')
            with open(manifest, 'w', encoding='utf-8') as f:
                f.write(content)
            print("p4a_hooks: KtWidget lagt til i manifest")
        else:
            print("p4a_hooks: </application> ikke funnet!")

    print("p4a_hooks: _run_hook ferdig")
