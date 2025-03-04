package eliminacode;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import android.os.Bundle;
import java.io.OutputStream;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.net.Socket;
import java.nio.charset.Charset;

import android.util.Log;
import android.util.Log;
import android.webkit.WebChromeClient;
class PrintManager {

    public static void printTicket(String ip, String repartoNome, String data) {

        new Thread(() -> {
            try {
                Log.d("DEBUG_PRINT", "Tentativo di connessione alla stampante IP: " + ip);
                Socket socket = new Socket(ip, 9100);
                Log.d("DEBUG_PRINT", "Connessione riuscita, invio dati alla stampante...");

                OutputStream outputStream = socket.getOutputStream();

                byte[] initPrinter = new byte[]{0x1B, 0x40}; // Reset della stampante
                byte[] alignCenter = new byte[]{0x1B, 0x61, 0x01}; // Centra il testo
                byte[] boldOn = new byte[]{0x1B, 0x45, 0x01}; // Testo in grassetto
                byte[] boldOff = new byte[]{0x1B, 0x45, 0x00}; // Disattiva grassetto
                byte[] newLine = new byte[]{0x0A}; // Nuova riga
                byte[] cutPaper = new byte[]{0x1D, 0x56, 0x41, 0x10}; // Taglio della carta

                outputStream.write(initPrinter);
                outputStream.write(alignCenter);
                outputStream.write(boldOn);
                outputStream.write("TICKET\n".getBytes());
                outputStream.write(boldOff);
                outputStream.write(("Reparto: " + repartoNome + "\n").getBytes());
                outputStream.write(("Numero: " + data + "\n").getBytes());
                outputStream.write(newLine);
                outputStream.write(newLine);
                outputStream.write(cutPaper);

                outputStream.flush();
                socket.close();
                Log.d("DEBUG_PRINT", "Ticket inviato con successo!");

            } catch (Exception e) {
                Log.e("DEBUG_PRINT", "Errore durante la stampa", e);
                e.printStackTrace();
            }
        }).start();
    }


}
