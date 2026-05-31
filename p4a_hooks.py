"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.

p4a v2024.01.21 kaller disse hook-funksjonene:
  before_apk_build, after_apk_build,
  before_apk_assemble, after_apk_assemble

Vi bruker before_apk_assemble – da er dists/src/main/ på plass
og klar for å motta res/ og java/.
"""
import os
import glob
import shutil
import logging


def before_apk_assemble(ctx, *args, **kwargs):
    """Kalles rett før Gradle assembleDebug – riktig tidspunkt for res/java-kopiering."""
    print("=== p4a_hooks: before_apk_assemble KALT ===")
    _run_hook(ctx)


def before_apk_build(ctx, *args, **kwargs):
    """Fallback for andre p4a-versjoner."""
    print("=== p4a_hooks: before_apk_build KALT ===")
    _run_hook(ctx)


def _get_root(ctx):
    """Henter rotmappen til prosjektet fra ctx."""
    try:
        return ctx.buildozer.root_dir
    except AttributeError:
        pass
    try:
        return ctx.root_dir
    except AttributeError:
        pass
    # Fallback: finn via dist_dir
    try:
        dist = str(ctx.dist_dir)
        # dist_dir er typisk .buildozer/android/platform/build-*/dists/<name>
        # root er 5 nivåer opp
        root = dist
        for _ in range(5):
            root = os.path.dirname(root)
        if os.path.exists(os.path.join(root, 'main.py')):
            return root
    except Exception:
        pass
    return None


def _run_hook(ctx):
    root = _get_root(ctx)
    if not root:
        print("p4a_hooks: klarte ikke finne root_dir, avbryter")
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

        # ── 1. Kopier res/ ────────────────────────────────────────
        if os.path.exists(res_src):
            res_dst = os.path.join(main_dir, 'res')
            os.makedirs(res_dst, exist_ok=True)
            for folder in os.listdir(res_src):
                src_f = os.path.join(res_src, folder)
                dst_f = os.path.join(res_dst, folder)
                if os.path.isdir(src_f):
                    if os.path.exists(dst_f):
                        shutil.rmtree(dst_f)
                    shutil.copytree(src_f, dst_f)
                    print(f"p4a_hooks: kopierte res/{folder} -> {dst_f}")

        # ── 2. Kopier java/ til src/main/java/ ───────────────────
        if os.path.exists(java_src):
            java_dst = os.path.join(main_dir, 'java')
            if os.path.exists(java_dst):
                # Legg til i eksisterende, ikke slett
                for root_j, dirs, files in os.walk(java_src):
                    rel = os.path.relpath(root_j, java_src)
                    dst_dir = os.path.join(java_dst, rel)
                    os.makedirs(dst_dir, exist_ok=True)
                    for f in files:
                        shutil.copy2(
                            os.path.join(root_j, f),
                            os.path.join(dst_dir, f))
            else:
                shutil.copytree(java_src, java_dst)
            print(f"p4a_hooks: kopierte java/ -> {java_dst}")

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
            print("p4a_hooks: </application> ikke funnet i manifest!")

    print("p4a_hooks: ferdig")
