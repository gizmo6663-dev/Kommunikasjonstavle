"""
patch_manifest.py – legger til KtWidget-receiver i AndroidManifest.xml.
Kalles fra build.yml: python3 patch_manifest.py <manifest-sti>
"""
import sys

manifest_path = sys.argv[1]

with open(manifest_path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'KtWidget' in content:
    print('Manifest: KtWidget allerede til stede')
    sys.exit(0)

receiver = '''
        <receiver
            android:name="no.askapp.kommunikasjonstavle.KtWidget"
            android:exported="true"
            android:label="Dagsrytme">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
                <action android:name="no.askapp.kommunikasjonstavle.WIDGET_REFRESH" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/kt_widget_info" />
        </receiver>'''

if '</application>' not in content:
    print('FEIL: fant ikke </application> i manifest')
    sys.exit(1)

content = content.replace('</application>',
                          receiver + '\n    </application>')

with open(manifest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Manifest: KtWidget + WIDGET_REFRESH lagt til')
