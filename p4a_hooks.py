"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.

Gjør to ting rett før Gradle-bygget:
1. Kopierer res/ inn i Gradle-prosjektets src/main/res/
2. Patcher AndroidManifest.xml med KtWidget-receiver + meta-data

Bruker glob for å finne stiene pålitelig uavhengig av dist-navn.
"""
import os
import glob
import shutil
import logging


def prebuild_apk(build, *args, **kwargs):
    root    = build.buildozer.root_dir
    res_src = os.path.join(root, 'res')

    # ── Finn Gradle-prosjektets src/main/ via glob ────────────────
    pattern = os.path.join(
        root, '.buildozer', 'android', 'platform',
        'build-*', 'dists', '*', 'src', 'main')
    matches = glob.glob(pattern)

    if not matches:
        logging.warning('p4a_hooks: fant ikke src/main/, hopper over')
        return

    for main_dir in matches:
        # ── 1. Kopier res/ ────────────────────────────────────────
        res_dst = os.path.join(main_dir, 'res')
        if os.path.exists(res_src):
            os.makedirs(res_dst, exist_ok=True)
            for folder in os.listdir(res_src):
                src_f = os.path.join(res_src, folder)
                dst_f = os.path.join(res_dst, folder)
                if os.path.isdir(src_f):
                    if os.path.exists(dst_f):
                        shutil.rmtree(dst_f)
                    shutil.copytree(src_f, dst_f)
                    logging.info('p4a_hooks: kopierte res/%s', folder)

        # ── 2. Patch AndroidManifest.xml ──────────────────────────
        manifest = os.path.join(main_dir, 'AndroidManifest.xml')
        if not os.path.exists(manifest):
            logging.warning('p4a_hooks: fant ikke %s', manifest)
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
        else:
            logging.warning('p4a_hooks: fant ikke </application> i manifest')
