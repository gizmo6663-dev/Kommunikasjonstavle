package no.askapp.kommunikasjonstavle;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

/**
 * KtWidget – hjemskjerm-widget for Kommunikasjonstavle.
 *
 * Viser:
 *   - Neste aktivitet i dagsrytmen (navn + tid)
 *   - Knapp for å åpne appen direkte til dagsrytmen
 *
 * Data leses fra SharedPreferences (nøkkel "kt_widget").
 * Kivy-appen skriver data via jnius etter hver dagsrytme-endring.
 */
public class KtWidget extends AppWidgetProvider {

    static final String PREFS_NAME    = "kt_widget";
    static final String KEY_ACTIVITY  = "next_activity";
    static final String KEY_TIME      = "next_time";
    static final String KEY_STATUS    = "status";  // "active", "upcoming", "done", "empty"
    static final String KEY_CURRENT   = "current_activity";

    @Override
    public void onUpdate(Context ctx,
                         AppWidgetManager mgr,
                         int[] ids) {
        for (int id : ids) {
            updateWidget(ctx, mgr, id);
        }
    }

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        SharedPreferences prefs = ctx.getSharedPreferences(PREFS_NAME, 0);
        String status   = prefs.getString(KEY_STATUS,   "empty");
        String activity = prefs.getString(KEY_ACTIVITY, "Ingen aktiviteter");
        String time     = prefs.getString(KEY_TIME,     "");
        String current  = prefs.getString(KEY_CURRENT,  "");

        RemoteViews views = new RemoteViews(
            ctx.getPackageName(),
            R.layout.kt_widget
        );

        // Sett appnavn
        views.setTextViewText(R.id.widget_app_title, "Kommunikasjonstavle");

        // Sett aktivitetsnavn og tid
        switch (status) {
            case "active":
                views.setTextViewText(R.id.widget_activity_label, "Nå:");
                views.setTextViewText(R.id.widget_activity_name,  current);
                views.setTextViewText(R.id.widget_activity_time,  time);
                views.setInt(R.id.widget_status_dot,
                    "setBackgroundColor", 0xFF6BCB77);  // grønn
                break;
            case "upcoming":
                views.setTextViewText(R.id.widget_activity_label, "Neste:");
                views.setTextViewText(R.id.widget_activity_name,  activity);
                views.setTextViewText(R.id.widget_activity_time,  time);
                views.setInt(R.id.widget_status_dot,
                    "setBackgroundColor", 0xFFFF9F43);  // oransje
                break;
            case "done":
                views.setTextViewText(R.id.widget_activity_label, "Ferdig for i dag");
                views.setTextViewText(R.id.widget_activity_name,  "");
                views.setTextViewText(R.id.widget_activity_time,  "");
                views.setInt(R.id.widget_status_dot,
                    "setBackgroundColor", 0xFF9CA3AF);  // grå
                break;
            default:
                views.setTextViewText(R.id.widget_activity_label, "Ingen plan lagt");
                views.setTextViewText(R.id.widget_activity_name,  "");
                views.setTextViewText(R.id.widget_activity_time,  "");
                views.setInt(R.id.widget_status_dot,
                    "setBackgroundColor", 0xFFCCCCCC);
        }

        // Trykk på widget åpner appen
        Intent launchIntent = new Intent(ctx,
            org.kivy.android.PythonActivity.class);
        launchIntent.setFlags(
            Intent.FLAG_ACTIVITY_NEW_TASK |
            Intent.FLAG_ACTIVITY_CLEAR_TOP);
        launchIntent.putExtra("widget_open", "dagsrytme");

        PendingIntent pi = PendingIntent.getActivity(
            ctx, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT |
            PendingIntent.FLAG_IMMUTABLE);

        views.setOnClickPendingIntent(R.id.widget_root, pi);

        mgr.updateAppWidget(id, views);
    }
}
