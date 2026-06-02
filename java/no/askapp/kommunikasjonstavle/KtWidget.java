package no.askapp.kommunikasjonstavle;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

public class KtWidget extends AppWidgetProvider {

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) updateWidget(ctx, mgr, id);
    }

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        SharedPreferences p = ctx.getSharedPreferences("kt_widget", 0);
        String line1 = p.getString("line1", "Kommunikasjonstavle");
        String line2 = p.getString("line2", "");

        RemoteViews views = new RemoteViews(
            ctx.getPackageName(), R.layout.kt_widget_layout);
        views.setTextViewText(R.id.kt_line1, line1);
        views.setTextViewText(R.id.kt_line2, line2);

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
