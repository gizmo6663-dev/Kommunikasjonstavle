package no.askapp.kommunikasjonstavle;

import android.content.Context;
import android.util.Log;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * WidgetLog – skriver timestampede logglinjer til widget_log.txt.
 * Deles mellom KtWidget.java (Java) og main.py (Python via fillesing).
 * Maks 200 linjer – eldre linjer roteres ut automatisk.
 */
public class WidgetLog {

    private static final String  FILE    = "widget_log.txt";
    private static final int     MAX     = 200;
    private static final String  TAG     = "WidgetLog";
    private static final SimpleDateFormat FMT =
        new SimpleDateFormat("HH:mm:ss", Locale.getDefault());

    public static void w(Context ctx, String msg) {
        String line = FMT.format(new Date()) + "  " + msg;
        Log.d(TAG, line);
        try {
            File f = new File(ctx.getFilesDir(), FILE);
            // Les eksisterende linjer
            java.util.List<String> lines = new java.util.ArrayList<>();
            if (f.exists()) {
                try (java.io.BufferedReader br =
                         new java.io.BufferedReader(
                             new java.io.FileReader(f))) {
                    String l;
                    while ((l = br.readLine()) != null) lines.add(l);
                }
            }
            lines.add(line);
            // Behold kun siste MAX linjer
            if (lines.size() > MAX)
                lines = lines.subList(lines.size() - MAX, lines.size());
            // Skriv tilbake
            try (PrintWriter pw = new PrintWriter(new FileWriter(f, false))) {
                for (String l : lines) pw.println(l);
            }
        } catch (Exception e) {
            Log.e(TAG, "Skriv feil: " + e);
        }
    }
}
