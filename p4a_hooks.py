"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.
Kopierer res/ og java/ til Gradle-prosjektets src/main/,
og patcher AndroidManifest.xml med KtWidget-receiver.
"""
import os
import glob
import shutil
import logging

def before_gradle_build(ctx):
    """Kalles av python-for-android rett før gradle-bygg (nyere p4a)."""
    print("=== p4a_hooks: before_gradle_build KALT ===")
    root = ctx.buildozer.root_dir
    print(f"p4a_hooks: root = {root}")
    _run_hook(root)

def prebuild_apk(build, *args, **kwargs):
    """Kalles av eldre p4a-versjoner."""
    print("=== p4a_hooks: prebuild_apk KALT ===")
    root = build.buildozer.root_dir
    print(f"p4a_hooks: root = {root}")
    _run_hook(root)

def _run_hook(root):
    print("p4a_hooks: _run_hook starter")
    res_src = os.path.join(root, 'res')
    java_src = os.path.join(root, 'java')
    print(f"p4a_hooks: res_src = {res_src}, eksisterer: {os.path.exists(res_src)}")
    print(f"p4a_hooks: java_src = {java_src}, eksisterer: {os.path.exists(java_src)}")

    pattern = os.path.join(
        root, '.buildozer', 'android', 'platform',
        'build-*', 'dists', '*', 'src', 'main')
    print(f"p4a_hooks: pattern = {pattern}")
    matches = glob.glob(pattern)
    print(f"p4a_hooks: matches = {matches}")

    if not matches:
        print("p4a_hooks: fant ikke src/main/, avbryter")
        return

    for main_dir in matches:
        print(f"p4a_hooks: behandler {main_dir}")

        # 1. Kopier res/
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
                    print(f"p4a_hooks: kopierte res/{folder}")
        else:
            print("p4a_hooks: res/ finnes ikke, hopper over")

        # 2. Kopier java/ til src/main/java/
        if os.path.exists(java_src):
            java_dst = os.path.join(main_dir, 'java')
            if os.path.exists(java_dst):
                shutil.rmtree(java_dst)
            shutil.copytree(java_src, java_dst)
            print(f"p4a_hooks: kopierte java/ til {java_dst}")
        else:
            print("p4a_hooks: java/ finnes ikke, hopper over")

        # 3. Patch AndroidManifest.xml
        manifest = os.path.join(main_dir, 'AndroidManifest.xml')
        if not os.path.exists(manifest):
            print(f"p4a_hooks: manifest ikke funnet: {manifest}")
            continue

        with open(manifest, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'KtWidget' in content:
            print("p4a_hooks: KtWidget allerede i manifest, hopper over patching")
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
            print("p4a_hooks: </application> ikke funnet i manifest")
    print("p4a_hooks: _run_hook ferdig")
