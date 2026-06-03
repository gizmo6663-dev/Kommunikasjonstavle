"""
p4a_hooks.py – p4a-hook for Kommunikasjonstavle.

p4a v2024.01.21 kaller before_apk_build og before_apk_assemble.
Hooken kjøres for TIDLIG til å påvirke Gradle-kompileringen –
Java, res og manifest håndteres derfor av build.yml i stedet.

Hooken beholdes som sikkerhetsnett for evt. fremtidige p4a-versjoner
der hook-tidspunktet endres.
"""
import os


def before_apk_build(ctx, *args, **kwargs):
    pass  # build.yml håndterer Java/res/manifest


def before_apk_assemble(ctx, *args, **kwargs):
    pass  # build.yml håndterer Java/res/manifest
