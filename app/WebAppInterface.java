package eliminacode;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.util.Log;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import android.os.Bundle;
import java.io.OutputStream;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.net.Socket;
import java.nio.charset.Charset;


class WebAppInterface {
    private MainActivity activity;

    WebAppInterface(MainActivity activity) {
        this.activity = activity;
    }

    @JavascriptInterface
    public void printTicket(String repartoNome, String ticketNumber, String printerIp) {
        Log.d("WEB_APP_INTERFACE", "Ricevuti dati dal WebView:");
        Log.d("WEB_APP_INTERFACE", "Reparto: " + repartoNome);
        Log.d("WEB_APP_INTERFACE", "Numero Ticket: " + (ticketNumber != null ? ticketNumber : "NULL"));
        Log.d("WEB_APP_INTERFACE", "Stampante IP: " + (printerIp != null ? printerIp : "NULL"));

        if (ticketNumber == null || ticketNumber.isEmpty()) {
            Log.e("WEB_APP_INTERFACE", "Errore: Numero Ticket non valido!");
        }
        if (printerIp == null || printerIp.isEmpty()) {
            Log.e("WEB_APP_INTERFACE", "Errore: IP Stampante non valido!");
        }

        PrintManager.printTicket(repartoNome, ticketNumber, printerIp);
    }
}
