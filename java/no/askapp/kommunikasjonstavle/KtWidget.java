package no.askapp.kommunikasjonstavle;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.RemoteViews;
import android.widget.TextView;

/**
 * KtWidget – hjemskjerm-widget for Kommunikasjonstavle.
 *
 * Bruker android.R.layout.simple_list_item_2 som base RemoteViews
 * slik at vi ikke trenger egne res-filer (som p4a ikke støtter via add_res).
 * Data leses fra SharedPreferences "kt_widget".
 */
public class KtWidget extends AppWidgetProvider {

    static final String PREFS     = "kt_widget";
    static final String K_STATUS  = "status";
    static final String K_LABEL   = "next_activity";
    static final String K_TIME    = "next_time";
    static final String K_CURRENT = "current_activity";

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) updateWidget(ctx, mgr, id);
    }

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        SharedPreferences p = ctx.getSharedPreferences(PREFS, 0);
        String status  = p.getString(K_STATUS,  "empty");
        String label   = p.getString(K_LABEL,   "Ingen aktiviteter");
        String time    = p.getString(K_TIME,    "");
        String current = p.getString(K_CURRENT, "");

        // Bruk innebygd two-line list layout – ingen egne res-filer nødvendig
        RemoteViews views = new RemoteViews(
            ctx.getPackageName(),
            android.R.layout.simple_list_item_2);

        // Linje 1: appnavn + status
        String dot;
        switch (status) {
            case "active":   dot = "\u25CF"; break;  // grønn ●
            case "upcoming": dot = "\u25CF"; break;  // oransje ●
            case "done":     dot = "\u25CF"; break;  // grå ●
            default:         dot = "\u25CB"; break;  // tom ○
        }

        // Sett farger via setInt (RemoteViews API)
        int dotColor;
        switch (status) {
            case "active":   dotColor = Color.rgb(107, 203, 119); break;
            case "upcoming": dotColor = Color.rgb(255, 159,  67); break;
            case "done":     dotColor = Color.rgb(156, 163, 175); break;
            default:         dotColor = Color.rgb(200, 200, 200); break;
        }

        // android.R.id.text1 = øvre linje, text2 = nedre linje
        String line1 = "Kommunikasjonstavle  " + dot;
        String line2;
        switch (status) {
            case "active":
                line2 = "Na: " + current + (time.isEmpty() ? "" : "  " + time);
                break;
            case "upcoming":
                line2 = "Neste: " + label + (time.isEmpty() ? "" : "  " + time);
                break;
            case "done":
                line2 = "Ferdig for i dag";
                break;
            default:
                line2 = "Ingen plan lagt til";
        }

        views.setTextViewText(android.R.id.text1, line1);
        views.setTextViewText(android.R.id.text2, line2);
        views.setTextColor(android.R.id.text1, Color.rgb(18, 24, 58));
        views.setTextColor(android.R.id.text2, dotColor);

        // Trykk åpner appen
        Intent intent = new Intent(ctx, org.kivy.android.PythonActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(
            ctx, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        views.setOnClickPendingIntent(android.R.id.content, pi);

        mgr.updateAppWidget(id, views);
    }
}
