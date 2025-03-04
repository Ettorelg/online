package eliminacode;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import androidx.annotation.Nullable;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
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
import java.net.Socket;
import java.nio.charset.Charset;


public class FlaskService extends Service {
    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        new Thread(() -> startFlaskServer()).start();
        return START_STICKY;
    }

    private void startFlaskServer() {
        try {
            Process process = Runtime.getRuntime().exec("python3 /data/user/0/com.example.eliminacode/files/server.py");
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
