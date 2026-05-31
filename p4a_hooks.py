"""
p4a_hooks.py – widget-støtte for Kommunikasjonstavle.
Kopierer res/ og java/ til Gradle-prosjektet og patcher AndroidManifest.xml.
"""

import os
import glob
import shutil
import logging

# Støtter både gammelt (prebuild_apk) og nytt (before_gradle_build) hook-navn
def prebuild_apk(build, *args, **kwargs):
    _run_hook(build)

def before_gradle_build(ctx):
    # For p4a nyere versjoner – bygg et dummy-objekt med buildozer.root_dir
    class Dummy:
        pass
    dummy = Dummy()
    dummy.buildozer = type('obj', (object,), {'root_dir': os.getcwd()})()
    _run_hook(dummy)

def _run_hook(build):
    root = build.buildozer.root_dir
    res_src = os.path.join(root, 'res')
    java_src = os.path.join(root, 'java')
    
    pattern = os.path.join(root, '.buildozer', 'android', 'platform',
                           'build-*', 'dists', '*', 'src', 'main')
    matches = glob.glob(pattern)
    if not matches:
        logging.warning('p4a_hooks: fant ikke src/main/')
        return

    for main_dir in matches:
        logging.info('p4a_hooks: patcher %s', main_dir)
        
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
                    logging.info('p4a_hooks: kopierte res/%s', folder)
        
        # 2. Kopier java/
        if os.path.exists(java_src):
            java_dst = os.path.join(main_dir, 'java')
            if os.path.exists(java_dst):
                shutil.rmtree(java_dst)
            shutil.copytree(java_src, java_dst)
            logging.info('p4a_hooks: kopierte java/')
        
        # 3. Patch AndroidManifest.xml
        manifest = os.path.join(main_dir, 'AndroidManifest.xml')
        if not os.path.exists(manifest):
            logging.warning('p4a_hooks: manifest ikke funnet')
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
            content = content.replace('</application>', receiver_block + '\n    </application>')
            with open(manifest, 'w', encoding='utf-8') as f:
                f.write(content)
            logging.info('p4a_hooks: KtWidget lagt til i manifest')
        else:
            logging.error('p4a_hooks: </application> ikke funnet')
