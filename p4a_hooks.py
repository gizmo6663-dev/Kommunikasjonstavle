"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.
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
    print(f"p4a_hooks: ctx type = {type(ctx)}")
    print(f"p4a_hooks: ctx attrs = {[a for a in dir(ctx) if not a.startswith('__')][:20]}")

    # Prøv ctx-attributter
    for attr in ('build_dir', 'dist_dir', 'storage_dir', 'root_dir'):
        val = getattr(ctx, attr, None)
        if val:
            val = str(val)
            candidate = val
            for _ in range(8):
                if os.path.exists(os.path.join(candidate, 'main.py')):
                    return candidate
                candidate = os.path.dirname(candidate)

    # Hardkodet – GitHub Actions Docker-volum
    print(f"p4a_hooks: getcwd = {os.getcwd()}")
    for candidate in [
        '/home/user/hostcwd',
        '/hostcwd',
        os.getcwd(),
        os.path.dirname(os.getcwd()),
    ]:
        print(f"p4a_hooks: prøver {candidate}, main.py: {os.path.exists(os.path.join(candidate, 'main.py'))}")
        if os.path.exists(os.path.join(candidate, 'main.py')):
            return candidate

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

        if os.path.exists(java_src):
            java_dst = os.path.join(main_dir, 'java')
            os.makedirs(java_dst, exist_ok=True)
            for root_j, dirs, files in os.walk(java_src):
                rel     = os.path.relpath(root_j, java_src)
                dst_dir = os.path.join(java_dst, rel)
                os.makedirs(dst_dir, exist_ok=True)
                for f in files:
                    shutil.copy2(
                        os.path.join(root_j, f),
                        os.path.join(dst_dir, f))
            print(f"p4a_hooks: kopierte java/ -> {java_dst}")

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
