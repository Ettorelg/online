package eliminacode;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
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
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import java.net.Socket;
import java.nio.charset.Charset;
import android.webkit.WebChromeClient;

import com.example.eliminacode.R;

public class MainActivity extends AppCompatActivity {
    private WebView webView;
    private static final String LOGIN_URL = "https://zestful-flow-pregettoonline.up.railway.app/login";
    private static final String TEST_PRINTER_IP = "192.168.1.100"; // IP della stampante per test




    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);

        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setAllowFileAccess(true);
        webSettings.setAllowContentAccess(true);
        webSettings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient()); // Abilita debugging JavaScript

        // ⚠️ IMPORTANTE: Aggiungi prima l'interfaccia JavaScript, poi carica la pagina
        webView.addJavascriptInterface(new WebAppInterface(), "Android");
        webView.loadUrl(LOGIN_URL);
    }


    private class WebAppInterface {
        @JavascriptInterface
        public void printTicket(String ip, String repartoNome, String ticketNumber) {
            Log.d("DEBUG_PRINT", "✅ Dati ricevuti per stampa: IP=" + ip + ", Reparto=" + repartoNome + ", Ticket=" + ticketNumber);
            Toast.makeText(MainActivity.this, "Stampando ticket...", Toast.LENGTH_SHORT).show();
            PrintManager.printTicket(ip, repartoNome, ticketNumber);
        }
    }

}

