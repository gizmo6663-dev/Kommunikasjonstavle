package no.askapp.kommunikasjonstavle;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class KtWidget extends AppWidgetProvider {

    private static final String TAG            = "KtWidget";
    static final String         ACTION_REFRESH =
        "no.askapp.kommunikasjonstavle.WIDGET_REFRESH";

    @Override
    public void onEnabled(Context ctx) {
        scheduleAlarm(ctx);
    }

    @Override
    public void onDisabled(Context ctx) {
        cancelAlarm(ctx);
    }

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        WidgetLog.w(ctx, "[onUpdate] " + ids.length + " widget(er)");
        for (int id : ids) {
            try { updateWidget(ctx, mgr, id); }
            catch (Exception e) {
                Log.e(TAG, "onUpdate feil: " + e);
                WidgetLog.w(ctx, "[FEIL] onUpdate: " + e.getMessage());
            }
        }
    }

    @Override
    public void onReceive(Context ctx, Intent intent) {
        super.onReceive(ctx, intent);
        String action = intent.getAction();

        if (ACTION_REFRESH.equals(action)) {
            WidgetLog.w(ctx, "[ACTION_REFRESH] mottatt");
            AppWidgetManager mgr = AppWidgetManager.getInstance(ctx);
            int[] ids = mgr.getAppWidgetIds(
                new ComponentName(ctx, KtWidget.class));
            onUpdate(ctx, mgr, ids);

        } else if (Intent.ACTION_BOOT_COMPLETED.equals(action)
                || "android.intent.action.QUICKBOOT_POWERON".equals(action)) {
            WidgetLog.w(ctx, "[BOOT] gjenoppretter alarm-kjede");
            AppWidgetManager mgr = AppWidgetManager.getInstance(ctx);
            int[] ids = mgr.getAppWidgetIds(
                new ComponentName(ctx, KtWidget.class));
            if (ids.length > 0) {
                Log.i(TAG, "Boot: gjenoppretter widget-alarm");
                onUpdate(ctx, mgr, ids);
            }
        }
    }

    // ── AlarmManager ──────────────────────────────────────────────

    static void scheduleAlarm(Context ctx) {
        scheduleNext(ctx, 60_000);
    }

    static void scheduleNext(Context ctx, long delayMs) {
        try {
            AlarmManager am = (AlarmManager)
                ctx.getSystemService(Context.ALARM_SERVICE);
            long target = System.currentTimeMillis() + delayMs;
            PendingIntent pi = getAlarmIntent(ctx);

            // Eksakte alarmer for dagsrytme-overganger:
            // - API < 31: canScheduleExactAlarms() finnes ikke, men eksakte alarmer er alltid tillatt.
            // - API 31+: vi må sjekke canScheduleExactAlarms() runtime. På apper som deklarerer
            //   USE_EXACT_ALARM (kategori: kalender/alarm/dagsrytme) er den auto-innvilget.
            // - setExactAndAllowWhileIdle bypasser Doze, så et veggmontert nettbrett som har stått
            //   stille en stund får oppdatert widget med riktig aktivitet uansett.
            boolean canExact = (Build.VERSION.SDK_INT < 31) || am.canScheduleExactAlarms();
            String mode;
            try {
                if (canExact) {
                    am.setExactAndAllowWhileIdle(AlarmManager.RTC, target, pi);
                    mode = "exact+idle";
                } else {
                    // Inexact fallback: setAndAllowWhileIdle (ikke plain set) –
                    // bypasser Doze og er mindre sannsynlig til å bli parkert
                    // i bakgrunnen av Samsung sin batterioptimisering. Fortsatt
                    // ikke sekundpresist, men typisk innen 10 sek av målet.
                    am.setAndAllowWhileIdle(AlarmManager.RTC, target, pi);
                    mode = "inexact+idle (mangler permission)";
                }
            } catch (SecurityException se) {
                // Defensiv: skal ikke skje når canScheduleExactAlarms() er true, men håndter likevel
                am.setAndAllowWhileIdle(AlarmManager.RTC, target, pi);
                mode = "inexact+idle (SecurityException)";
            }
            WidgetLog.w(ctx, "[ALARM] " + mode + " satt om " + (delayMs/1000) + " sek");
        } catch (Exception e) {
            Log.e(TAG, "scheduleNext feil: " + e);
            WidgetLog.w(ctx, "[FEIL] scheduleNext: " + e.getMessage());
        }
    }

    static void scheduleNextFromData(Context ctx, JSONArray dr) {
        long delayMs = 15 * 60 * 1000L;
        boolean scheduled = false;  // Sann hvis en aktiv/fremtidig aktivitet matchet
        try {
            Calendar cal    = Calendar.getInstance();
            int      nowMin = cal.get(Calendar.HOUR_OF_DAY) * 60
                            + cal.get(Calendar.MINUTE);
            int      nowSec = cal.get(Calendar.SECOND);

            // Sorter etter starttidspunkt
            List<JSONObject> entries = new ArrayList<>();
            if (dr != null)
                for (int i = 0; i < dr.length(); i++)
                    entries.add(dr.getJSONObject(i));
            Collections.sort(entries, (a, b) ->
                toMin(a.optString("start","")) -
                toMin(b.optString("start","")));

            for (JSONObject e : entries) {
                int s = toMin(e.optString("start", ""));
                int t = toMin(e.optString("end",   ""));
                if (s < 0 || t < 0) continue;

                if (s <= nowMin && nowMin < t) {
                    // Aktiv – oppdater ved slutt.
                    // +1 sek padding: fyrer like etter minuttgrensa så Calendar
                    // garantert har rullet over til neste minutt når widgeten
                    // leser klokka igjen. Med setExactAndAllowWhileIdle holder 1 sek.
                    int remSec = (t - nowMin) * 60 - nowSec + 1;
                    delayMs = remSec * 1000L;
                    WidgetLog.w(ctx, "[PLAN] slutt kl." + e.optString("end")
                          + " om " + remSec + "s");
                    scheduled = true;
                    break;
                }
                if (s > nowMin) {
                    // Neste – oppdater ved start (samme padding-logikk)
                    int waitSec = (s - nowMin) * 60 - nowSec + 1;
                    delayMs = waitSec * 1000L;
                    WidgetLog.w(ctx, "[PLAN] start kl." + e.optString("start")
                          + " om " + waitSec + "s");
                    scheduled = true;
                    break;
                }
            }
            if (!scheduled) {
                WidgetLog.w(ctx, "[PLAN] ingen kommende aktivitet – default 15 min");
            }
        } catch (Exception e) {
            Log.w(TAG, "scheduleNextFromData feil: " + e);
            WidgetLog.w(ctx, "[FEIL] scheduleNextFromData: " + e.getMessage());
        }
        // Nedre clamp på 2 sek beskytter mot uendelige løkker hvis remSec
        // skulle bli null/negativ pga. en bug. Den gamle verdien (30 sek)
        // forsinket transisjoner med opptil 30 sek for korte aktiviteter
        // og generelt de siste 30 sek av enhver aktivitet.
        // Øvre clamp på 15 min sikrer at vi våkner jevnlig selv om noe
        // går galt med beregningen.
        delayMs = Math.max(2_000, Math.min(delayMs, 15 * 60 * 1000L));
        scheduleNext(ctx, delayMs);
    }

    static void cancelAlarm(Context ctx) {
        try {
            AlarmManager am = (AlarmManager)
                ctx.getSystemService(Context.ALARM_SERVICE);
            am.cancel(getAlarmIntent(ctx));
        } catch (Exception e) {
            Log.e(TAG, "cancelAlarm feil: " + e);
        }
    }

    static PendingIntent getAlarmIntent(Context ctx) {
        Intent i = new Intent(ctx, KtWidget.class);
        i.setAction(ACTION_REFRESH);
        return PendingIntent.getBroadcast(ctx, 0, i,
            PendingIntent.FLAG_UPDATE_CURRENT |
            PendingIntent.FLAG_IMMUTABLE);
    }

    // ── Widget-oppdatering ─────────────────────────────────────────

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        try {
            WidgetData data = readFromJson(ctx);
            if (data == null) data = readFromPrefs(ctx);
            if (data == null) data = new WidgetData(
                "Kommunikasjonstavle", "", null, null);

            RemoteViews views = new RemoteViews(
                ctx.getPackageName(), R.layout.kt_widget_layout);

            views.setTextViewText(R.id.kt_line1, data.line1);
            views.setTextViewText(R.id.kt_line2, data.line2);

            // Bilde – les direkte fra fil hvis mulig, ellers SharedPreferences
            boolean hasImage = false;
            Bitmap bmp = null;

            if (data.imagePath != null && !data.imagePath.isEmpty()) {
                bmp = loadBitmapFromFile(data.imagePath);
            }
            if (bmp == null && data.imgB64 != null && !data.imgB64.isEmpty()) {
                byte[] bytes = Base64.decode(data.imgB64, Base64.DEFAULT);
                bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            }

            if (bmp != null) {
                views.setImageViewBitmap(R.id.kt_img, bmp);
                views.setViewVisibility(R.id.kt_img, View.VISIBLE);
                // Dempet bilde i pending-tilstand (~40% alpha) for å antyde
                // at aktiviteten kommer, men er ikke i gang ennå.
                // Full alpha (255) når aktiviteten er aktiv.
                views.setInt(R.id.kt_img, "setImageAlpha",
                             data.pending ? 100 : 255);
                hasImage = true;
            }
            if (!hasImage) {
                views.setViewVisibility(R.id.kt_img, View.GONE);
            }

            // Klikk åpner appen
            Intent open = new Intent(ctx,
                org.kivy.android.PythonActivity.class);
            open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                          Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent piOpen = PendingIntent.getActivity(ctx, 1, open,
                PendingIntent.FLAG_UPDATE_CURRENT |
                PendingIntent.FLAG_IMMUTABLE);
            views.setOnClickPendingIntent(R.id.kt_line1, piOpen);
            views.setOnClickPendingIntent(R.id.kt_img,   piOpen);

            // ↻ knapp
            Intent ref = new Intent(ctx, KtWidget.class);
            ref.setAction(ACTION_REFRESH);
            PendingIntent piRef = PendingIntent.getBroadcast(ctx, 2, ref,
                PendingIntent.FLAG_UPDATE_CURRENT |
                PendingIntent.FLAG_IMMUTABLE);
            views.setOnClickPendingIntent(R.id.kt_refresh, piRef);

            mgr.updateAppWidget(id, views);
            WidgetLog.w(ctx, "[VISER] \"" + data.line1 + "\"  |  "
                + data.line2
                + (hasImage ? "  [bilde]" : "  [ingen bilde]"));

            // Planlegg neste oppdatering
            scheduleNextFromData(ctx, data.dagsrytme);

        } catch (Exception e) {
            Log.e(TAG, "updateWidget feil: " + e);
        }
    }

    // ── Les bilde fra fil ─────────────────────────────────────────

    static Bitmap loadBitmapFromFile(String path) {
        try {
            File f = new File(path);
            if (!f.exists()) return null;
            BitmapFactory.Options opts = new BitmapFactory.Options();
            opts.inSampleSize = 2; // Halvér oppløsning for minnesparing
            return BitmapFactory.decodeFile(path, opts);
        } catch (Exception e) {
            Log.w(TAG, "loadBitmapFromFile feil: " + e);
            return null;
        }
    }

    // ── Les fra structure.json ─────────────────────────────────────

    static WidgetData readFromJson(Context ctx) {
        try {
            File f = new File(ctx.getFilesDir(), "structure.json");
            if (!f.exists()) return null;

            StringBuilder sb = new StringBuilder();
            try (BufferedReader br = new BufferedReader(new FileReader(f))) {
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
            }

            JSONObject root = new JSONObject(sb.toString());

            // Pause-sjekk: hvis dagsrytmen er på pause, vis det isteden
            // for å være misvisende om "neste aktivitet".
            JSONObject pause = root.optJSONObject("pause");
            if (pause != null) {
                return new WidgetData("⏸  Dagsrytme på pause",
                                       "Trykk for å gjenoppta", null, null);
            }

            // Hent dagens ukekode for å finne riktig plan.
            // Calendar.DAY_OF_WEEK: 1=SU, 2=MO, ... 7=SA.
            Calendar cal      = Calendar.getInstance();
            int      dowField = cal.get(Calendar.DAY_OF_WEEK);
            String[] codes    = {"SU","MO","TU","WE","TH","FR","SA"};
            String   todayCd  = codes[Math.max(0, Math.min(6, dowField - 1))];

            // Hent dagens plan fra dagsplaner-objektet. Faller tilbake til
            // det gamle dagsrytme-arrayet for strukturer fra før migrering.
            JSONArray  dr     = null;
            JSONObject plans  = root.optJSONObject("dagsplaner");
            if (plans != null) {
                dr = plans.optJSONArray(todayCd);
            }
            if (dr == null) {
                dr = root.optJSONArray("dagsrytme");
            }
            if (dr == null || dr.length() == 0)
                return new WidgetData("Ingen aktivitet nå", "", null, dr);

            int      nowMin = cal.get(Calendar.HOUR_OF_DAY) * 60
                            + cal.get(Calendar.MINUTE);

            // Sorter etter starttidspunkt
            List<JSONObject> entries = new ArrayList<>();
            for (int i = 0; i < dr.length(); i++)
                entries.add(dr.getJSONObject(i));
            Collections.sort(entries, (a, b) ->
                toMin(a.optString("start","")) -
                toMin(b.optString("start","")));

            JSONObject current = null;
            for (JSONObject e : entries) {
                int s = toMin(e.optString("start", ""));
                int t = toMin(e.optString("end",   ""));
                if (s >= 0 && t >= 0 && s <= nowMin && nowMin < t) {
                    current = e;
                    break;
                }
            }

            if (current == null) {
                // Finn neste aktivitet – og vis bildet dempet for å antyde
                // at den kommer.
                String nextName = "";
                String nextStart = "";
                String nextEnd   = "";
                String nextImg   = "";
                for (JSONObject e : entries) {
                    int s = toMin(e.optString("start",""));
                    if (s > nowMin) {
                        nextName  = e.optString("name", "");
                        nextStart = e.optString("start", "");
                        nextEnd   = e.optString("end",   "");
                        nextImg   = e.optString("image", "");
                        break;
                    }
                }
                String l1, l2;
                if (nextName.isEmpty()) {
                    l1 = "Ingen aktivitet nå";
                    l2 = "";
                } else {
                    l1 = "Neste: " + nextName;
                    l2 = "kl. " + nextStart
                         + (nextEnd.isEmpty() ? "" : " – " + nextEnd);
                }
                WidgetLog.w(ctx, "[JSON] pending. Neste: \"" + nextName
                    + "\" " + nextStart
                    + (nextImg.isEmpty() ? " (uten bilde)" : " (med dempet bilde)"));
                String img = nextImg.isEmpty() ? null : nextImg;
                WidgetData wd = new WidgetData(l1, l2, img, dr);
                wd.pending = (img != null);
                return wd;
            }

            String name  = current.optString("name",  "");
            String start = current.optString("start", "");
            String end   = current.optString("end",   "");
            int    endM  = toMin(end);
            int    rem   = Math.max(0, endM - nowMin);
            String line2 = start + " – " + end
                         + "  (" + rem + " min igjen)";
            String imgPath = current.optString("image", "");

            WidgetLog.w(ctx, "[JSON] aktiv: \"" + name
                + "\" " + start + "-" + end
                + (imgPath.isEmpty() ? " ingen bilde" : " har bilde"));
            return new WidgetData(name, line2, imgPath, dr);

        } catch (Exception e) {
            Log.w(TAG, "readFromJson feil: " + e);
            return null;
        }
    }

    static WidgetData readFromPrefs(Context ctx) {
        try {
            SharedPreferences p =
                ctx.getSharedPreferences("kt_widget", 0);
            String line1 = p.getString("line1", null);
            if (line1 == null) return null;
            return new WidgetData(line1,
                p.getString("line2",   ""),
                null,
                null);
        } catch (Exception e) { return null; }
    }

    static int toMin(String t) {
        try {
            String[] parts = t.split(":");
            return Integer.parseInt(parts[0]) * 60 +
                   Integer.parseInt(parts[1]);
        } catch (Exception e) { return -1; }
    }

    // ── Data-klasse ────────────────────────────────────────────────

    static class WidgetData {
        String    line1, line2, imagePath, imgB64;
        JSONArray dagsrytme;
        // pending=true betyr at vi venter på en aktivitet (før første eller i mellomrom).
        // Brukes til å vise bildet dempet (alpha) for å antyde at det kommer.
        boolean   pending;
        WidgetData(String l1, String l2, String img, JSONArray dr) {
            line1 = l1; line2 = l2; imagePath = img; dagsrytme = dr;
            imgB64 = null;  // Eksplisitt: vi bruker imagePath nå, ikke base64
            pending = false;
        }
    }
}
