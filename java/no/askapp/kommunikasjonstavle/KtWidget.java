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
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileReader;
import java.io.BufferedReader;
import java.util.Calendar;

/**
 * KtWidget – hjemskjerm-widget for Kommunikasjonstavle.
 *
 * Leser structure.json direkte fra appens private lagring,
 * og beregner aktiv aktivitet uten at Python trenger å kjøre.
 * AlarmManager oppdaterer widgeten automatisk hvert 15. minutt.
 */
public class KtWidget extends AppWidgetProvider {

    private static final String TAG            = "KtWidget";
    static final String         ACTION_REFRESH =
        "no.askapp.kommunikasjonstavle.WIDGET_REFRESH";

    @Override
    public void onEnabled(Context ctx) {
        // Kalles når første widget legges til hjemskjermen
        scheduleAlarm(ctx);
    }

    @Override
    public void onDisabled(Context ctx) {
        // Kalles når siste widget fjernes fra hjemskjermen
        cancelAlarm(ctx);
    }

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) {
            try { updateWidget(ctx, mgr, id); }
            catch (Exception e) { Log.e(TAG, "onUpdate feil: " + e); }
        }
    }

    @Override
    public void onReceive(Context ctx, Intent intent) {
        super.onReceive(ctx, intent);
        if (ACTION_REFRESH.equals(intent.getAction())) {
            AppWidgetManager mgr = AppWidgetManager.getInstance(ctx);
            int[] ids = mgr.getAppWidgetIds(
                new ComponentName(ctx, KtWidget.class));
            onUpdate(ctx, mgr, ids);
        }
    }

    // ── AlarmManager ──────────────────────────────────────────────

    static void scheduleAlarm(Context ctx) {
        try {
            AlarmManager am = (AlarmManager)
                ctx.getSystemService(Context.ALARM_SERVICE);
            PendingIntent pi = getAlarmIntent(ctx);
            // Hvert 15. minutt, inexact for batterisparing
            am.setInexactRepeating(
                AlarmManager.RTC,
                System.currentTimeMillis() + 60_000,
                15 * 60 * 1000L,
                pi);
            Log.i(TAG, "AlarmManager satt (15 min)");
        } catch (Exception e) {
            Log.e(TAG, "scheduleAlarm feil: " + e);
        }
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
        return PendingIntent.getBroadcast(
            ctx, 0, i,
            PendingIntent.FLAG_UPDATE_CURRENT |
            PendingIntent.FLAG_IMMUTABLE);
    }

    // ── Widget-oppdatering ─────────────────────────────────────────

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        try {
            // Les data: prøv structure.json, fall tilbake til SharedPreferences
            WidgetData data = readFromJson(ctx);
            if (data == null) data = readFromPrefs(ctx);
            if (data == null) data = new WidgetData(
                "Kommunikasjonstavle", "", null);

            RemoteViews views = new RemoteViews(
                ctx.getPackageName(), R.layout.kt_widget_layout);

            views.setTextViewText(R.id.kt_line1, data.line1);
            views.setTextViewText(R.id.kt_line2, data.line2);

            // Bilde
            boolean hasImage = false;
            if (data.imgB64 != null && !data.imgB64.isEmpty()) {
                try {
                    byte[] bytes = Base64.decode(
                        data.imgB64, Base64.DEFAULT);
                    Bitmap bmp = BitmapFactory.decodeByteArray(
                        bytes, 0, bytes.length);
                    if (bmp != null) {
                        views.setImageViewBitmap(R.id.kt_img, bmp);
                        views.setViewVisibility(R.id.kt_img, View.VISIBLE);
                        hasImage = true;
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Bilde feil: " + e);
                }
            }
            if (!hasImage) {
                views.setViewVisibility(R.id.kt_img, View.GONE);
            }

            // Klikk åpner appen
            Intent open = new Intent(ctx,
                org.kivy.android.PythonActivity.class);
            open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                          Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent piOpen = PendingIntent.getActivity(
                ctx, 1, open,
                PendingIntent.FLAG_UPDATE_CURRENT |
                PendingIntent.FLAG_IMMUTABLE);
            views.setOnClickPendingIntent(R.id.kt_line1, piOpen);
            views.setOnClickPendingIntent(R.id.kt_img,   piOpen);

            // ↻ refresh
            Intent ref = new Intent(ctx, KtWidget.class);
            ref.setAction(ACTION_REFRESH);
            PendingIntent piRef = PendingIntent.getBroadcast(
                ctx, 2, ref,
                PendingIntent.FLAG_UPDATE_CURRENT |
                PendingIntent.FLAG_IMMUTABLE);
            views.setOnClickPendingIntent(R.id.kt_refresh, piRef);

            mgr.updateAppWidget(id, views);

        } catch (Exception e) {
            Log.e(TAG, "updateWidget feil: " + e);
        }
    }

    // ── Les fra structure.json ─────────────────────────────────────

    static WidgetData readFromJson(Context ctx) {
        try {
            // structure.json ligger i appens private files-mappe
            File f = new File(ctx.getFilesDir(), "structure.json");
            if (!f.exists()) return null;

            StringBuilder sb = new StringBuilder();
            try (BufferedReader br = new BufferedReader(new FileReader(f))) {
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
            }

            JSONObject root = new JSONObject(sb.toString());
            JSONArray  dr   = root.optJSONArray("dagsrytme");
            if (dr == null || dr.length() == 0) return null;

            Calendar cal     = Calendar.getInstance();
            int      nowMin  = cal.get(Calendar.HOUR_OF_DAY) * 60 +
                               cal.get(Calendar.MINUTE);

            JSONObject current = null;
            for (int i = 0; i < dr.length(); i++) {
                JSONObject e = dr.getJSONObject(i);
                int s = toMin(e.optString("start", ""));
                int t = toMin(e.optString("end",   ""));
                if (s >= 0 && t >= 0 && s <= nowMin && nowMin < t) {
                    current = e;
                    break;
                }
            }

            if (current == null) {
                return new WidgetData("Ingen aktivitet nå", "", null);
            }

            String name  = current.optString("name", "");
            String start = current.optString("start", "");
            String end   = current.optString("end",   "");
            int    endM  = toMin(end);
            int    rem   = Math.max(0, endM - nowMin);
            String line2 = start + " – " + end +
                           "  (" + rem + " min igjen)";

            // Forsøk å lese bilde
            String imgB64 = null;
            SharedPreferences p =
                ctx.getSharedPreferences("kt_widget", 0);
            String cachedB64 = p.getString("img_b64", "");
            String cachedName = p.getString("line1", "");
            // Bruk cachet bilde hvis aktivitet er lik
            if (name.equals(cachedName) && !cachedB64.isEmpty()) {
                imgB64 = cachedB64;
            }

            return new WidgetData(name, line2, imgB64);

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
            return new WidgetData(
                line1,
                p.getString("line2",   ""),
                p.getString("img_b64", ""));
        } catch (Exception e) {
            return null;
        }
    }

    static int toMin(String t) {
        try {
            String[] parts = t.split(":");
            return Integer.parseInt(parts[0]) * 60 +
                   Integer.parseInt(parts[1]);
        } catch (Exception e) {
            return -1;
        }
    }

    // ── Data-klasse ────────────────────────────────────────────────

    static class WidgetData {
        String line1, line2, imgB64;
        WidgetData(String l1, String l2, String img) {
            line1 = l1; line2 = l2; imgB64 = img;
        }
    }
}
