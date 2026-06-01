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

        # ── 2. Java-kopiering DEAKTIVERT – feilsøking ────────────
        # Tester om manifest-patch alene er nok (uten KtWidget.class)
        print("p4a_hooks: java-kopiering hoppet over (feilsøking)")

        # ── 3. Manifest-patching DEAKTIVERT ──────────────────────
        # KtWidget må kompileres inn i APK-en FØR manifestet patches.
        # Begge deler aktiveres igjen når Java-kopiering er bekreftet OK.
        print("p4a_hooks: manifest-patch hoppet over (widget deaktivert)")

    print("p4a_hooks: _run_hook ferdig")
