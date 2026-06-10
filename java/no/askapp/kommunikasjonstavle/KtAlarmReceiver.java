package no.askapp.kommunikasjonstavle;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.os.Bundle;

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
 *
 * Extras leses fra en Bundle (intent.getExtras()), IKKE via
 * intent.getStringExtra() direkte – pyjnius kan ikke alltid
 * matche riktig Intent.putExtra()-overload, noe som ga
 * getStringExtra()==null på Java-siden (varselet viste da kun
 * appnavnet som tittel og tom tekst). Bundle.putString()/putInt()
 * fra Python-siden har utvetydige signaturer og leses trygt her
 * via Bundle.getString()/getInt().
 */
public class KtAlarmReceiver extends BroadcastReceiver {

    static final String CHANNEL_ID   = "kt_varsler";
    static final String CHANNEL_NAME = "Kommunikasjonstavle";

    /** Maks bredde/høyde (px) for innlastet bilde – unngår OutOfMemory på store bilder. */
    static final int MAX_IMG_DIM = 512;

    @Override
    public void onReceive(Context context, Intent intent) {
        // Ikke vis varsel hvis appen er i forgrunnen
        if (isAppForeground(context)) return;

        Bundle extras = intent.getExtras();
        int    notifId   = extras != null ? extras.getInt("notif_id", 0) : 0;
        String title     = extras != null ? extras.getString("title") : null;
        String body      = extras != null ? extras.getString("body")  : null;
        String imagePath = extras != null ? extras.getString("image_path") : null;

        if (title == null) title = "Kommunikasjonstavle";
        if (body  == null) body  = "";

        ensureChannel(context);
        showNotification(context, notifId, title, body, imagePath);
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

    /**
     * Laster ned-skalert bitmap fra fil – eller null hvis stien er tom,
     * filen ikke finnes, eller dekoding feiler.
     *
     * Bruker inSampleSize for å unngå å laste hele originalbildet i minnet
     * når det kun skal vises som lite ikon/big-picture i et varsel.
     */
    private Bitmap loadScaledBitmap(String path) {
        if (path == null || path.isEmpty()) return null;
        File f = new File(path);
        if (!f.exists()) return null;
        try {
            BitmapFactory.Options opts = new BitmapFactory.Options();
            opts.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(path, opts);

            int sample = 1;
            while (opts.outWidth  / sample > MAX_IMG_DIM
                || opts.outHeight / sample > MAX_IMG_DIM) {
                sample *= 2;
            }
            opts.inSampleSize = sample;
            opts.inJustDecodeBounds = false;
            return BitmapFactory.decodeFile(path, opts);
        } catch (Exception e) {
            return null;
        }
    }

    private void showNotification(Context context, int notifId, String title,
                                   String body, String imagePath) {
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

        // Aktivitetsbilde – vises som lite ikon ved siden av teksten,
        // og som stort utvidet bilde (BigPictureStyle) når varselet
        // dras ned/utvides.
        Bitmap bmp = loadScaledBitmap(imagePath);
        if (bmp != null) {
            b.setLargeIcon(bmp);
            Notification.BigPictureStyle style = new Notification.BigPictureStyle()
                    .bigPicture(bmp)
                    .setBigContentTitle(title)
                    .setSummaryText(body);
            // bigLargeIcon(null) skjuler det lille ikonet i utvidet visning
            // slik at kun det store bildet vises – unngår dobbelt opp.
            style.bigLargeIcon((Bitmap) null);
            b.setStyle(style);
        }

        nm.notify(notifId, b.build());
    }
}
