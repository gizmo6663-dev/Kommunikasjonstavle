"""
patch_manifest.py – legger til KtWidget-receiver og KtAlarmReceiver i AndroidManifest.xml.
Kalles fra build.yml: python3 patch_manifest.py <manifest-sti>
"""
import sys

manifest_path = sys.argv[1]

with open(manifest_path, 'r', encoding='utf-8') as f:
    content = f.read()

# ── KtWidget ──────────────────────────────────────────────────────────────
if 'KtWidget' not in content:
    widget_receiver = '''
        <receiver
            android:name="no.askapp.kommunikasjonstavle.KtWidget"
            android:exported="true"
            android:label="Dagsrytme">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
                <action android:name="no.askapp.kommunikasjonstavle.WIDGET_REFRESH" />
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.QUICKBOOT_POWERON" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/kt_widget_info" />
        </receiver>'''
    content = content.replace('</application>',
                              widget_receiver + '\n    </application>')
    print('Manifest: KtWidget lagt til')
else:
    print('Manifest: KtWidget allerede til stede')

# ── KtAlarmReceiver (push-varsler for tidsur og dagsplan) ─────────────────
if 'KtAlarmReceiver' not in content:
    alarm_receiver = '''
        <receiver
            android:name="no.askapp.kommunikasjonstavle.KtAlarmReceiver"
            android:exported="false" />'''
    content = content.replace('</application>',
                              alarm_receiver + '\n    </application>')
    print('Manifest: KtAlarmReceiver lagt til')
else:
    print('Manifest: KtAlarmReceiver allerede til stede')

# ── Tillatelser ────────────────────────────────────────────────────────────
permissions = {
    'POST_NOTIFICATIONS':  'android.permission.POST_NOTIFICATIONS',
    'SCHEDULE_EXACT_ALARM': 'android.permission.SCHEDULE_EXACT_ALARM',
}
for short, full in permissions.items():
    tag = f'<uses-permission android:name="{full}"'
    if tag not in content:
        # Sett inn rett etter <manifest ...>-åpningstaggen
        content = content.replace(
            '<uses-permission',
            f'{tag}/>\n    <uses-permission',
            1)   # bare første forekomst (for å sette den øverst)
        print(f'Manifest: {short} lagt til')
    else:
        print(f'Manifest: {short} allerede til stede')

if '</application>' not in content:
    print('FEIL: fant ikke </application> i manifest')
    sys.exit(1)

with open(manifest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('patch_manifest.py: ferdig')
