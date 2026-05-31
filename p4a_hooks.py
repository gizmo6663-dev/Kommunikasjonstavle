"""
p4a_hooks.py – Buildozer/p4a hook for Kommunikasjonstavle.

Kopierer res/-mappen inn i Gradle-prosjektets src/main/res/
etter at p4a har generert prosjektstrukturen men før Gradle bygger.
Dette er nødvendig for AppWidget-støtte (kt_widget_info.xml).

Aktiveres i buildozer.spec med: p4a.hook = p4a_hooks.py
"""
import os
import shutil
import logging


def prebuild_apk(build, *args, **kwargs):
    """Kalles av p4a rett før Gradle-bygget starter."""
    root   = build.buildozer.root_dir          # repoets rot
    res_src = os.path.join(root, 'res')

    # Finn Gradle-prosjektets res-mappe
    # p4a legger den under .buildozer/android/platform/build-*/dists/<name>/src/main/res
    dist_dir = getattr(build, 'dist_dir', None)
    if not dist_dir:
        # Prøv å finne dist_dir via build-stien
        platform_dir = os.path.join(
            root, '.buildozer', 'android', 'platform')
        for entry in os.listdir(platform_dir) if os.path.exists(platform_dir) else []:
            if entry.startswith('build-'):
                dists = os.path.join(platform_dir, entry, 'dists')
                if os.path.exists(dists):
                    for d in os.listdir(dists):
                        dist_dir = os.path.join(dists, d)
                        break
                break

    if not dist_dir:
        logging.warning('p4a_hooks: fant ikke dist_dir, hopper over res-kopiering')
        return

    res_dst = os.path.join(dist_dir, 'src', 'main', 'res')

    if not os.path.exists(res_src):
        logging.warning('p4a_hooks: res/ finnes ikke i roten, hopper over')
        return

    os.makedirs(res_dst, exist_ok=True)
    for folder in os.listdir(res_src):
        src_f = os.path.join(res_src, folder)
        dst_f = os.path.join(res_dst, folder)
        if os.path.isdir(src_f):
            if os.path.exists(dst_f):
                shutil.rmtree(dst_f)
            shutil.copytree(src_f, dst_f)
            logging.info('p4a_hooks: kopierte res/%s → %s', folder, dst_f)

    logging.info('p4a_hooks: res-kopiering fullfort')
