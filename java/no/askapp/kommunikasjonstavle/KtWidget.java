package no.askapp.kommunikasjonstavle;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.widget.RemoteViews;

public class KtWidget extends AppWidgetProvider {

    private static final String TAG = "KtWidget";

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) {
            try { updateWidget(ctx, mgr, id); }
            catch (Exception e) { Log.e(TAG, "onUpdate feil: " + e.getMessage()); }
        }
    }

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        try {
            SharedPreferences p = ctx.getSharedPreferences("kt_widget", 0);
            String line1  = p.getString("line1",   "Kommunikasjonstavle");
            String line2  = p.getString("line2",   "");
            String imgB64 = p.getString("img_b64", "");

            RemoteViews views = new RemoteViews(
                ctx.getPackageName(), R.layout.kt_widget_layout);

            views.setTextViewText(R.id.kt_line1, line1);
            views.setTextViewText(R.id.kt_line2, line2);

            boolean hasImage = false;
            if (imgB64 != null && !imgB64.isEmpty()) {
                try {
                    byte[] bytes = Base64.decode(imgB64, Base64.DEFAULT);
                    Bitmap bmp   = BitmapFactory.decodeByteArray(
                                       bytes, 0, bytes.length);
                    if (bmp != null) {
                        views.setImageViewBitmap(R.id.kt_img, bmp);
                        views.setViewVisibility(R.id.kt_img, View.VISIBLE);
                        hasImage = true;
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Bilde feilet: " + e.getMessage());
                }
            }

            if (!hasImage) {
                views.setViewVisibility(R.id.kt_img, View.GONE);
            }

            // Trykk åpner appen
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

        } catch (Exception e) {
            Log.e(TAG, "updateWidget feil: " + e.getMessage());
        }
    }
}
