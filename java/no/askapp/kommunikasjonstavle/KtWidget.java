package no.askapp.kommunikasjonstavle;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.widget.RemoteViews;

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

        RemoteViews views = new RemoteViews(
            ctx.getPackageName(), R.layout.kt_widget_layout);

        String line1, line2;
        int color2;

        switch (status) {
            case "active":
                line1  = "Kommunikasjonstavle \u25CF";
                line2  = "Na: " + current + (time.isEmpty() ? "" : "  " + time);
                color2 = Color.rgb(107, 203, 119);
                break;
            case "upcoming":
                line1  = "Kommunikasjonstavle \u25CF";
                line2  = "Neste: " + label + (time.isEmpty() ? "" : "  " + time);
                color2 = Color.rgb(255, 159, 67);
                break;
            case "done":
                line1  = "Kommunikasjonstavle";
                line2  = "Ferdig for i dag";
                color2 = Color.rgb(156, 163, 175);
                break;
            default:
                line1  = "Kommunikasjonstavle";
                line2  = "Ingen plan lagt til";
                color2 = Color.rgb(156, 163, 175);
        }

        views.setTextViewText(R.id.kt_line1, line1);
        views.setTextViewText(R.id.kt_line2, line2);
        views.setTextColor(R.id.kt_line2, color2);

        Intent intent = new Intent(ctx, org.kivy.android.PythonActivity.class);
        intent.setFlags(
            Intent.FLAG_ACTIVITY_NEW_TASK |
            Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(
            ctx, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT |
            PendingIntent.FLAG_IMMUTABLE);
        views.setOnClickPendingIntent(R.id.kt_line1, pi);

        mgr.updateAppWidget(id, views);
    }
}
