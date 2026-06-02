package no.askapp.kommunikasjonstavle;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.graphics.Paint;
import android.util.Base64;
import android.widget.RemoteViews;

public class KtWidget extends AppWidgetProvider {

    static final String PREFS = "kt_widget";

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) updateWidget(ctx, mgr, id);
    }

    static void updateWidget(Context ctx, AppWidgetManager mgr, int id) {
        SharedPreferences p = ctx.getSharedPreferences(PREFS, 0);
        String status  = p.getString("status",           "empty");
        String label   = p.getString("next_activity",    "Ingen aktiviteter");
        String time    = p.getString("next_time",        "");
        String curImg  = p.getString("current_image",    "");
        String nextImg = p.getString("next_image",       "");

        RemoteViews views = new RemoteViews(
            ctx.getPackageName(), R.layout.kt_widget_layout);

        String line1, line2;

        switch (status) {
            case "active":
                line1 = "Nå: " + label;
                line2 = time;
                // Vis aktivt bilde i farger
                setBitmap(views, R.id.kt_img_current, curImg, false);
                // Vis neste bilde gråtonet
                setBitmap(views, R.id.kt_img_next, nextImg, true);
                break;
            case "upcoming":
                line1 = "Neste: " + label;
                line2 = time;
                setBitmap(views, R.id.kt_img_current, nextImg, false);
                views.setImageViewResource(R.id.kt_img_next, android.R.color.transparent);
                break;
            case "done":
                line1 = "Ferdig for i dag";
                line2 = "";
                views.setImageViewResource(R.id.kt_img_current, android.R.color.transparent);
                views.setImageViewResource(R.id.kt_img_next, android.R.color.transparent);
                break;
            default:
                line1 = "Kommunikasjonstavle";
                line2 = "Ingen plan lagt til";
                views.setImageViewResource(R.id.kt_img_current, android.R.color.transparent);
                views.setImageViewResource(R.id.kt_img_next, android.R.color.transparent);
        }

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

    static void setBitmap(RemoteViews views, int viewId,
                          String b64, boolean grayout) {
        if (b64 == null || b64.isEmpty()) {
            views.setImageViewResource(viewId, android.R.color.transparent);
            return;
        }
        try {
            byte[] bytes  = Base64.decode(b64, Base64.DEFAULT);
            Bitmap orig   = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (orig == null) {
                views.setImageViewResource(viewId, android.R.color.transparent);
                return;
            }
            Bitmap bmp = orig;
            if (grayout) {
                bmp = Bitmap.createBitmap(
                    orig.getWidth(), orig.getHeight(), orig.getConfig());
                Canvas canvas = new Canvas(bmp);
                Paint  paint  = new Paint();
                ColorMatrix cm = new ColorMatrix();
                cm.setSaturation(0);
                paint.setColorFilter(new ColorMatrixColorFilter(cm));
                paint.setAlpha(120);
                canvas.drawBitmap(orig, 0, 0, paint);
            }
            views.setImageViewBitmap(viewId, bmp);
        } catch (Exception e) {
            views.setImageViewResource(viewId, android.R.color.transparent);
        }
    }
}
