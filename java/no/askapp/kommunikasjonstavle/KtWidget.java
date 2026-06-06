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
                    am.set(AlarmManager.RTC, target, pi);
                    mode = "inexact (mangler permission)";
                }
            } catch (SecurityException se) {
                // Defensiv: skal ikke skje når canScheduleExactAlarms() er true, men håndter likevel
                am.set(AlarmManager.RTC, target, pi);
                mode = "inexact (SecurityException)";
            }
            WidgetLog.w(ctx, "[ALARM] " + mode + " satt om " + (delayMs/1000) + " sek");
        } catch (Exception e) {
            Log.e(TAG, "scheduleNext feil: " + e);
            WidgetLog.w(ctx, "[FEIL] scheduleNext: " + e.getMessage());
        }
    }

    static void scheduleNextFromData(Context ctx, JSONArray dr) {
        long delayMs = 15 * 60 * 1000L;
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
                    // Aktiv – oppdater ved slutt
                    int remSec = (t - nowMin) * 60 - nowSec + 5;
                    delayMs = remSec * 1000L;
                    Log.i(TAG, "Slutter kl." + e.optString("end")
                          + " om " + remSec + " sek");
                    break;
                }
                if (s > nowMin) {
                    // Neste – oppdater ved start
                    int waitSec = (s - nowMin) * 60 - nowSec + 5;
                    delayMs = waitSec * 1000L;
                    Log.i(TAG, "Starter kl." + e.optString("start")
                          + " om " + waitSec + " sek");
                    break;
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "scheduleNextFromData feil: " + e);
        }
        delayMs = Math.max(30_000, Math.min(delayMs, 15 * 60 * 1000L));
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
            JSONArray  dr   = root.optJSONArray("dagsrytme");
            if (dr == null || dr.length() == 0)
                return new WidgetData("Ingen aktivitet nå", "", null, dr);

            Calendar cal    = Calendar.getInstance();
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
                // Finn neste aktivitet
                String nextName = "";
                String nextTime = "";
                for (JSONObject e : entries) {
                    int s = toMin(e.optString("start",""));
                    if (s > nowMin) {
                        nextName = e.optString("name","");
                        nextTime = e.optString("start","");
                        break;
                    }
                }
                String l1 = nextName.isEmpty()
                    ? "Ingen aktivitet nå"
                    : "Neste: " + nextName;
                String l2 = nextTime.isEmpty() ? "" : "kl. " + nextTime;
                WidgetLog.w(ctx, "[JSON] ingen aktiv. Neste: \"" + nextName
                    + "\" kl." + nextTime);
                return new WidgetData(l1, l2, null, dr);
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
        WidgetData(String l1, String l2, String img, JSONArray dr) {
            line1 = l1; line2 = l2; imagePath = img; dagsrytme = dr;
            imgB64 = null;  // Eksplisitt: vi bruker imagePath nå, ikke base64
        }
    }
}
