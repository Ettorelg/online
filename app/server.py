from flask import Flask, request
import socket

app = Flask(__name__)

@app.route('/stampa', methods=['POST'])
def stampa():
    try:
        data = request.json.get('data')  # Testo del ticket
        ip = request.json.get('ip')      # IP della stampante locale

        print(f"📨 Stampa richiesta per {ip}: {data}")  # Log della richiesta

        # Connessione alla stampante termica via socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, 9100))

        # Inizializza la stampante ESC/POS
        s.sendall(b'\x1B\x40')

        # Stampa il contenuto del ticket
        s.sendall(data.encode('utf-8'))

        # Comando per il taglio della carta
        s.sendall(b'\x1D\x56\x41\x10')

        s.close()
        print("✅ Stampa completata!")
        return 'Stampa completata', 200

    except Exception as e:
        print(f"❌ Errore di stampa: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
