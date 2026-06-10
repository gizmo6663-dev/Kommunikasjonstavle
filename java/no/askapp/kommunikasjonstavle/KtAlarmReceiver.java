package no.askapp.kommunikasjonstavle;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;

/**
 * KtAlarmReceiver – mottar AlarmManager-varsler for tidsur og dagsplan.
 *
 * Registreres i AndroidManifest av patch_manifest.py.
 * Kalles fra Python via AlarmManager.setExactAndAllowWhileIdle().
 *
 * Viser kun notifikasjon dersom appen er i bakgrunnen
 * (leses fra app_state.txt skrevet av Python-siden).
 */
public class KtAlarmReceiver extends BroadcastReceiver {

    static final String CHANNEL_ID   = "kt_varsler";
    static final String CHANNEL_NAME = "Kommunikasjonstavle";

    @Override
    public void onReceive(Context context, Intent intent) {
        // Ikke vis varsel hvis appen er i forgrunnen
        if (isAppForeground(context)) return;

        int    notifId = intent.getIntExtra("notif_id", 0);
        String title   = intent.getStringExtra("title");
        String body    = intent.getStringExtra("body");
        if (title == null) title = "Kommunikasjonstavle";
        if (body  == null) body  = "";

        ensureChannel(context);
        showNotification(context, notifId, title, body);
    }

    /**
     * Leser app_state.txt skrevet av Python-siden.
     * "1" = appen er i forgrunnen → ikke vis varsel.
     * Manglende fil eller "0" = bakgrunn → vis varsel.
     */
    private boolean isAppForeground(Context context) {
        try {
            File f = new File(context.getFilesDir(), "app_state.txt");
            if (!f.exists()) return false;
            BufferedReader br = new BufferedReader(new FileReader(f));
            String line = br.readLine();
            br.close();
            return "1".equals(line != null ? line.trim() : "");
        } catch (Exception e) {
            return false;
        }
    }

    /** Oppretter notifikasjonskanal (kreves for Android 8+, trygt å kalle gjentatte ganger). */
    private void ensureChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = (NotificationManager)
                context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null && nm.getNotificationChannel(CHANNEL_ID) == null) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("Varsler for tidsur og dagsplan-aktiviteter");
            ch.enableVibration(true);
            nm.createNotificationChannel(ch);
        }
    }

    private void showNotification(Context context, int notifId, String title, String body) {
        NotificationManager nm = (NotificationManager)
                context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;

        // Åpner appen når varselet trykkes
        Intent openIntent = context.getPackageManager()
                .getLaunchIntentForPackage(context.getPackageName());
        PendingIntent pi = null;
        if (openIntent != null) {
            openIntent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP
                              | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            int piFlags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
                piFlags |= PendingIntent.FLAG_IMMUTABLE;
            pi = PendingIntent.getActivity(context, notifId, openIntent, piFlags);
        }

        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            b = new Notification.Builder(context, CHANNEL_ID);
        } else {
            b = new Notification.Builder(context);
            b.setPriority(Notification.PRIORITY_HIGH);
        }

        b.setContentTitle(title)
         .setContentText(body)
         .setSmallIcon(android.R.drawable.ic_dialog_info)
         .setAutoCancel(true);

        if (pi != null) b.setContentIntent(pi);

        nm.notify(notifId, b.build());
    }
}
