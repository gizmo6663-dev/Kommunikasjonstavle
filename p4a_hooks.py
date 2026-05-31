"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.

Kopierer res/ og java/ til Gradle-prosjektets src/main/,
og patcher AndroidManifest.xml med KtWidget-receiver.
"""
import os
import glob
import shutil
import logging


def prebuild_apk(build, *args, **kwargs):
    root     = build.buildozer.root_dir
    res_src  = os.path.join(root, 'res')
    java_src = os.path.join(root, 'java')

    pattern = os.path.join(
        root, '.buildozer', 'android', 'platform',
        'build-*', 'dists', '*', 'src', 'main')
    matches = glob.glob(pattern)

    if not matches:
        logging.warning('p4a_hooks: fant ikke src/main/, avbryter')
        return

    for main_dir in matches:
        logging.info('p4a_hooks: behandler %s', main_dir)

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
                    logging.info('p4a_hooks: kopierte res/%s', folder)

        # ── 2. Kopier java/ til src/main/java/ ───────────────────
        if os.path.exists(java_src):
            java_dst = os.path.join(main_dir, 'java')
            if os.path.exists(java_dst):
                shutil.rmtree(java_dst)
            shutil.copytree(java_src, java_dst)
            logging.info('p4a_hooks: kopierte java/ til %s', java_dst)

        # ── 3. Patch AndroidManifest.xml ──────────────────────────
        manifest = os.path.join(main_dir, 'AndroidManifest.xml')
        if not os.path.exists(manifest):
            logging.warning('p4a_hooks: fant ikke manifest')
            continue

        with open(manifest, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'KtWidget' in content:
            logging.info('p4a_hooks: KtWidget allerede i manifest')
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
            logging.info('p4a_hooks: KtWidget lagt til i manifest')
