package no.askapp.kommunikasjonstavle;

import android.content.Context;
import android.net.Uri;
import java.io.FileOutputStream;
import java.io.InputStream;

/**
 * FileHelper – Java-side filkopiering for Kommunikasjonstavle.
 *
 * Brukes fra Python via jnius for å kopiere content-URI til lokal fil.
 * Hele I/O-løkken skjer i Java, slik at Python aldri trenger å håndtere
 * Java byte[]-arrayer (som jnius ikke støtter).
 */
public class FileHelper {

    /**
     * Kopierer en content-URI til en lokal filsti.
     * @return antall bytes skrevet, eller -1 ved feil.
     */
    public static long copyUriToFile(Context ctx, Uri uri, String destPath) {
        try {
            InputStream    is  = ctx.getContentResolver().openInputStream(uri);
            FileOutputStream fos = new FileOutputStream(destPath);
            byte[]  buf   = new byte[65536];
            long    total = 0;
            int     n;
            while ((n = is.read(buf)) != -1) {
                fos.write(buf, 0, n);
                total += n;
            }
            is.close();
            fos.close();
            return total;
        } catch (Exception e) {
            android.util.Log.e("FileHelper", "copyUriToFile feil: " + e.getMessage());
            return -1;
        }
    }
}
