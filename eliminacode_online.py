import psycopg2
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, jsonify
from escpos.printer import Network


app = Flask(__name__)
app.secret_key = "supersecretkey"
socketio = SocketIO(app)

# Configurazione Database Online

DATABASE_URL = "postgres://postgres:LrPuARcRABMibMgWZcjQnNlPZXypfwky@hopper.proxy.rlwy.net:31053/railway"
class Database:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.cursor = self.conn.cursor()

    def execute_query(self, query, params=(), commit=False):
        self.cursor.execute(query, params)
        if commit:
            self.conn.commit()
        try:
            result = self.cursor.fetchall()
        except psycopg2.ProgrammingError:
            result = []
        return result

    def get_licenze_utente(self, user_id):
        query = "SELECT tipo, data_scadenza FROM licenze WHERE id_utente = %s"
        result = self.execute_query(query, (user_id,))
        return {row[0]: row[1] for row in result}

    def crea_tabelle(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                admin BOOLEAN,
                ragione_sociale TEXT,
                indirizzo TEXT,
                citta TEXT,
                cap TEXT,
                partita_iva TEXT,
                telefono TEXT,
                email TEXT
            )
        ''')

        # Modificato per includere ON DELETE CASCADE
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS licenze (
                id SERIAL PRIMARY KEY,
                id_utente INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                data_scadenza TEXT NOT NULL
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS reparti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                IP_ADDRESS TEXT,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_reparto (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                id_reparto INTEGER REFERENCES reparti(id) ON DELETE CASCADE
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticket_reparto (
                id_reparto INTEGER PRIMARY KEY,
                numero_attuale INTEGER DEFAULT 0,
                numero_massimo INTEGER DEFAULT 0,
                FOREIGN KEY (id_reparto) REFERENCES reparti(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorie (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                prezzo DECIMAL(10,2) NOT NULL,
                tempo_produzione INTEGER NOT NULL, -- Tempo in minuti
                id_categoria INTEGER REFERENCES categorie(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS dipendenti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                cognome TEXT NOT NULL,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS calendario (
                id SERIAL PRIMARY KEY,
                id_utente INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
                id_prodotto INTEGER REFERENCES prodotti(id) ON DELETE CASCADE,
                id_dipendente INTEGER REFERENCES dipendenti(id) ON DELETE CASCADE,
                data_ora TIMESTAMP NOT NULL
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS immagini_utenti (
                id SERIAL PRIMARY KEY,
                id_utente INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
                immagine_url TEXT NOT NULL
            )
        ''')
        


        self.conn.commit()

    def close(self):
        self.cursor.close()
        self.conn.close()

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = Database()
        result = db.execute_query(
            "SELECT id, username, admin FROM utenti WHERE username = %s AND password = %s",
            (username, password)
        )

        if result:
            user_id, username, is_admin = result[0]
            session["user_id"] = user_id
            session["username"] = username
            session["is_admin"] = is_admin
            db.close()
            return redirect("/dashboard_admin") if is_admin else redirect("/dashboard_user")
        else:
            db.close()
            return "Login fallito! Username o password errati."

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard_admin")
def dashboard_admin():
    if not session.get("is_admin"):
        return redirect("/login")

    db = Database()
    utenti = db.execute_query("SELECT * FROM utenti")
    licenze_raw = db.execute_query("SELECT id_utente, tipo, data_scadenza FROM licenze")
    
    licenze = {}
    for id_utente, tipo, scadenza in licenze_raw:
        if id_utente not in licenze:
            licenze[id_utente] = []
        licenze[id_utente].append((tipo, scadenza))
    
    db.close()
    return render_template("dashboard_admin.html", utenti=utenti, licenze=licenze)

@app.route("/dashboard_user")
def dashboard_user():
    if "user_id" not in session:
        return redirect("/login")
    
    user_id = session["user_id"]
    db = Database()
    licenze = db.execute_query("SELECT tipo, data_scadenza FROM licenze WHERE id_utente = %s", (user_id,))
    eliminacode_attiva = any(licenza[0] == "eliminacode" for licenza in licenze)
    db.close()
    
    return render_template("dashboard_user.html", username=session["username"], licenze=licenze, eliminacode_attiva=eliminacode_attiva)

@app.route("/aggiungi_utente", methods=["GET", "POST"])
def aggiungi_utente():
    if not session.get("is_admin"):
        return redirect("/login")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        admin = True if "admin" in request.form else False
        ragione_sociale = request.form["ragione_sociale"]
        indirizzo = request.form["indirizzo"]
        citta = request.form["citta"]
        cap = request.form["cap"]
        partita_iva = request.form["partita_iva"]
        telefono = request.form["telefono"]
        email = request.form["email"]

        db = Database()

        try:
            db.execute_query('''
                INSERT INTO utenti (username, password, admin, ragione_sociale, indirizzo, citta, cap, partita_iva, telefono, email)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (username, password, admin, ragione_sociale, indirizzo, citta, cap, partita_iva, telefono, email), commit=True)
            db.close()
            return redirect("/dashboard_admin")
        except psycopg2.IntegrityError:
            db.conn.rollback()
            db.close()
            return "Errore: Username già esistente. Riprova con un altro nome."

    return render_template("aggiungi_utente.html")

@app.route("/modifica_utente/<int:user_id>", methods=["GET", "POST"])
def modifica_utente(user_id):
    if not session.get("is_admin"):
        return redirect("/login")
    db = Database()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        admin = True if "admin" in request.form else False
        ragione_sociale = request.form["ragione_sociale"]
        indirizzo = request.form["indirizzo"]
        citta = request.form["citta"]
        cap = request.form["cap"]
        partita_iva = request.form["partita_iva"]
        telefono = request.form["telefono"]
        email = request.form["email"]

        query = '''
            UPDATE utenti
            SET username = %s, password = %s, admin = %s, ragione_sociale = %s,
                indirizzo = %s, citta = %s, cap = %s, partita_iva = %s, telefono = %s, email = %s
            WHERE id = %s
        '''
        db.execute_query(query, (username, password, admin, ragione_sociale, indirizzo, citta, cap, partita_iva, telefono, email, user_id), commit=True)
        db.close()
        return redirect("/dashboard_admin")
    else:
        query = "SELECT username, password, admin, ragione_sociale, indirizzo, citta, cap, partita_iva, telefono, email FROM utenti WHERE id = %s"
        result = db.execute_query(query, (user_id,))
        db.close()
        if result:
            user = result[0]
            # Passiamo i dati dell'utente alla pagina per la modifica
            return render_template("modifica_utente.html", user_id=user_id, user=user)
        else:
            return "Utente non trovato"

@app.route("/cancella_utente/<int:user_id>")
def cancella_utente(user_id):
    if not session.get("is_admin"):
        return redirect("/login")
    db = Database()
    db.execute_query("DELETE FROM utenti WHERE id = %s", (user_id,), commit=True)
    db.close()
    # Se l'utente cancellato è quello attualmente loggato, esegui il logout
    if session.get("user_id") == user_id:
        session.clear()
        return redirect("/login")
    return redirect("/dashboard_admin")

@app.route("/gestisci_licenze/<int:user_id>", methods=["GET", "POST"])
def gestisci_licenze(user_id):
    if not session.get("is_admin"):
        return redirect("/login")

    db = Database()
    licenze_disponibili = ["eliminacode", "prenotazioni", "ordini"]
    licenze_attuali = db.get_licenze_utente(user_id)

    if request.method == "POST":
        # Gestione delle licenze
        if "update_licenze" in request.form:
            licenze_selezionate = request.form.getlist("licenze")

            # Rimuove le licenze non più selezionate
            for licenza in list(licenze_attuali.keys()):
                if licenza not in licenze_selezionate:
                    db.execute_query(
                        "DELETE FROM licenze WHERE id_utente = %s AND tipo = %s", 
                        (user_id, licenza), commit=True
                    )
                    del licenze_attuali[licenza]

            # Aggiunge le nuove licenze non presenti
            for licenza in licenze_selezionate:
                if licenza not in licenze_attuali:
                    scadenza = (datetime.today() + timedelta(days=365)).strftime("%Y-%m-%d")
                    db.execute_query(
                        "INSERT INTO licenze (id_utente, tipo, data_scadenza) VALUES (%s, %s, %s)",
                        (user_id, licenza, scadenza), commit=True
                    )
                    licenze_attuali[licenza] = scadenza

            # Aggiorna le scadenze se modificate
            for licenza in licenze_attuali:
                if f"scadenza_{licenza}" in request.form:
                    nuova_scadenza = request.form[f"scadenza_{licenza}"]
                    db.execute_query(
                        "UPDATE licenze SET data_scadenza = %s WHERE id_utente = %s AND tipo = %s",
                        (nuova_scadenza, user_id, licenza), commit=True
                    )
                    licenze_attuali[licenza] = nuova_scadenza

        # Aggiunta di un nuovo reparto con indirizzo IP
        elif "nuovo_reparto" in request.form:
            if "eliminacode" in licenze_attuali:
                licenza_id_result = db.execute_query(
                    "SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'eliminacode'",
                    (user_id,)
                )
                if licenza_id_result:
                    nuovo_reparto = request.form["nuovo_reparto"].strip()
                    ip_address = request.form.get("ip_reparto", "").strip()

                    db.execute_query(
                        "INSERT INTO reparti (nome, ip_address, id_licenza) VALUES (%s, %s, %s)",
                        (nuovo_reparto, ip_address, licenza_id_result[0][0]), commit=True
                    )

        # Eliminazione di un reparto
        elif "elimina_reparto" in request.form:
            reparto_id = request.form["elimina_reparto"]
            db.execute_query("DELETE FROM reparti WHERE id = %s", (reparto_id,), commit=True)

        # Modifica dell'IP di un reparto esistente
        elif "modifica_ip_reparto" in request.form:
            reparto_id = request.form.get("reparto_id")
            nuovo_ip = request.form.get("nuovo_ip", "").strip()
            if reparto_id and nuovo_ip:
                db.execute_query(
                    "UPDATE reparti SET ip_address = %s WHERE id = %s",
                    (nuovo_ip, reparto_id), commit=True
                )

        # Aggiunta di una fila al reparto
        elif "nuova_fila" in request.form:
            reparto_id = request.form.get("reparto_id")
            nuova_fila = request.form.get("nuova_fila").strip()
            if nuova_fila and reparto_id:
                db.execute_query(
                    "INSERT INTO file_reparto (nome, id_reparto) VALUES (%s, %s)",
                    (nuova_fila, reparto_id), commit=True
                )

        # Eliminazione di una fila
        elif "elimina_file" in request.form:
            file_id = request.form["elimina_file"]
            db.execute_query("DELETE FROM file_reparto WHERE id = %s", (file_id,), commit=True)

        db.conn.commit()
        db.close()
        return redirect(f"/gestisci_licenze/{user_id}")

    # Recupero dati reparti e file associati
    reparti = []
    file_reparto = {}
    if "eliminacode" in licenze_attuali:
        reparti = db.execute_query(
            "SELECT id, nome, ip_address FROM reparti WHERE id_licenza = (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'eliminacode')",
            (user_id,)
        )
        for reparto_id, reparto_nome, ip_address in reparti:
            file_reparto[reparto_id] = db.execute_query(
                "SELECT id, nome FROM file_reparto WHERE id_reparto = %s",
                (reparto_id,)
            )

    db.close()
    return render_template("gestisci_licenze.html", user_id=user_id, licenze_disponibili=licenze_disponibili,
                           licenze_attuali=licenze_attuali, reparti=reparti, file_reparto=file_reparto)
                           

# 🔹 Route per ritirare il ticket
@app.route("/ritira_ticket", methods=["GET", "POST"])
def ritira_ticket():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    db = Database()

    reparti = db.execute_query("""
        SELECT DISTINCT r.id, r.nome, r.ip_address 
        FROM reparti r
        INNER JOIN licenze l ON r.id_licenza = l.id
        WHERE l.id_utente = %s  
          AND l.tipo = 'eliminacode'
          AND TO_DATE(l.data_scadenza, 'YYYY-MM-DD') >= CURRENT_DATE
    """, (user_id,))

    if request.method == "GET":
        db.close()
        return render_template("ritira_ticket.html", reparti=reparti)

    # 🔹 Se la richiesta è POST, elabora il ticket
    try:
        reparto_id = request.form.get("reparto")
        reparto_nome = request.form.get("reparto_nome")

        if reparto_id and reparto_nome:
            result = db.execute_query("SELECT numero_massimo FROM ticket_reparto WHERE id_reparto = %s", (reparto_id,))
            ticket_number = (result[0][0] + 1) if result else 1

            db.execute_query(
                "UPDATE ticket_reparto SET numero_massimo = %s WHERE id_reparto = %s",
                (ticket_number, reparto_id), commit=True
            )

            ip_result = db.execute_query("SELECT ip_address FROM reparti WHERE id = %s", (reparto_id,))
            ip_stampante = ip_result[0][0] if ip_result else None

            db.close()

            response_data = {
                "success": True,
                "ticket_number": ticket_number,
                "reparto_nome": reparto_nome,
                "ip_stampante": ip_stampante
            }

            if ip_stampante:
                success = stampa_ticket_termico(reparto_nome, ticket_number, ip_stampante)
                if not success:
                    response_data["success"] = False
                    response_data["message"] = "Errore nella stampa del ticket"

            return jsonify(response_data)

    except Exception as e:
        print(f"❌ ERRORE SERVER: {e}")
        return jsonify({"success": False, "message": f"Errore interno: {str(e)}"}), 500

@app.route("/visualizza_ticket/<int:reparto_id>/<int:ticket_number>")
def visualizza_ticket(reparto_id, ticket_number):
    db = Database()

    # Recupera il nome del reparto
    reparto_result = db.execute_query("SELECT nome FROM reparti WHERE id = %s", (reparto_id,))
    reparto_nome = reparto_result[0][0] if reparto_result else "Sconosciuto"

    db.close()
    return render_template("visualizza_ticket.html", reparto_id=reparto_id, reparto_nome=reparto_nome, ticket_number=ticket_number)

@app.route("/ticket_chiamato")
def ticket_chiamato():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]  # Ottieni l'ID dell'utente dalla sessione
    db = Database()

    numeri_chiamati = db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    numeri_chiamati_dict = {row[0]: row[1] for row in numeri_chiamati} if numeri_chiamati else {}

    reparti = db.execute_query("""
        SELECT DISTINCT r.id, r.nome
        FROM reparti r
        INNER JOIN licenze l ON r.id_licenza = l.id
        WHERE l.id_utente = %s
    """, (user_id,))

    immagini = db.execute_query("SELECT immagine_url FROM immagini_utenti WHERE id_utente = %s", (user_id,))
    immagini_list = [row[0] for row in immagini] if immagini else []

    db.close()
    return render_template("ticket_chiamato.html", user_id=user_id, reparti=reparti, numeri_chiamati=numeri_chiamati_dict, immagini=immagini_list)

@app.route("/aggiorna_ticket", methods=["POST"])
def aggiorna_ticket():
    db = Database()
    numeri_chiamati = db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto")

    numeri_formattati = {}
    for reparto_id, numero in numeri_chiamati:
        reparto_nome_result = db.execute_query("SELECT nome FROM reparti WHERE id = %s", (reparto_id,))
        if reparto_nome_result:
            reparto_nome = reparto_nome_result[0][0]
            numeri_formattati[reparto_nome] = numero  # Usa il nome del reparto come chiave

            # **Invia il segnale specifico per il reparto**
            socketio.emit(f"update_ticket_{reparto_nome}", numero)

    db.close()
    print("📢 INVIO AGGIORNAMENTO CORRETTO:", numeri_formattati)  # Debug importante
    socketio.emit("update_tickets", numeri_formattati)
    return "OK", 200


@app.route("/gestione_ticket", methods=["GET", "POST"])
def gestione_ticket():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    db = Database()

    # Recupera i reparti associati all'utente
    reparti = db.execute_query("""
        SELECT DISTINCT r.id, r.nome 
        FROM reparti r
        INNER JOIN licenze l ON r.id_licenza = l.id
        WHERE l.id_utente = %s 
          AND l.tipo = 'eliminacode'
          AND TO_DATE(l.data_scadenza, 'YYYY-MM-DD') >= CURRENT_DATE
    """, (user_id,))

    # Mappatura reparti -> numeri ticket
    numeri_ticket = {}
    reparti_ids = [row[0] for row in reparti]
    
    if reparti_ids:
        placeholders = ', '.join(['%s'] * len(reparti_ids))  # Evita SQL Injection
        numeri_ticket_query = f"""
            SELECT id_reparto, numero_attuale 
            FROM ticket_reparto 
            WHERE id_reparto IN ({placeholders})
        """
        numeri_ticket = dict(db.execute_query(numeri_ticket_query, reparti_ids))

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        azione = request.form.get("azione")

        if reparto_id and azione and int(reparto_id) in reparti_ids:
            result = db.execute_query(
                "SELECT numero_attuale, numero_massimo FROM ticket_reparto WHERE id_reparto = %s", 
                (reparto_id,)
            )
            if result:
                numero_attuale, numero_massimo = result[0]
                if azione == "avanti" and numero_attuale < numero_massimo:
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = numero_attuale + 1 WHERE id_reparto = %s", 
                        (reparto_id,), commit=True
                    )
                elif azione == "indietro" and numero_attuale > 0:
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = numero_attuale - 1 WHERE id_reparto = %s", 
                        (reparto_id,), commit=True
                    )
                elif azione == "reset":
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = 0 WHERE id_reparto = %s", 
                        (reparto_id,), commit=True
                    )

                # Ricarica i dati aggiornati dei ticket
                numeri_ticket = dict(db.execute_query(numeri_ticket_query, reparti_ids))

                # Invio aggiornamento ai client via socket
                socketio.emit("update_tickets", numeri_ticket)

    db.close()
    return render_template("gestione_ticket.html", reparti=reparti, numeri_ticket=numeri_ticket)

@app.route("/visualizza_ticket_qr")
def visualizza_ticket_qr():
    return render_template("visualizza_ticket_qr.html")

@app.route("/ritira_ticket_qr", methods=["GET", "POST"])
def ritira_ticket_qr():
    db = Database()

    # Ottieni l'ID dell'utente dal parametro dell'URL
    user_id = request.args.get("user")

    if not user_id:
        return "Errore: nessun utente specificato nel QR code.", 400

    # Recupera solo i reparti associati all'utente specificato nel QR code
    reparti = db.execute_query("""
        SELECT id, nome FROM reparti
        WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s)
    """, (user_id,))

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        if reparto_id:
            result = db.execute_query("SELECT numero_massimo FROM ticket_reparto WHERE id_reparto = %s", (reparto_id,))
            ticket_number = (result[0][0] + 1) if result else 1

            db.execute_query(
                "UPDATE ticket_reparto SET numero_massimo = %s WHERE id_reparto = %s",
                (ticket_number, reparto_id), commit=True
            )

            db.close()
            return redirect(f"/visualizza_ticket/{reparto_id}/{ticket_number}")

    db.close()
    return render_template("ritira_ticket_qr.html", reparti=reparti)

from escpos.printer import Network
import time

def stampa_ticket_termico(reparto_nome, ticket_number, ip_stampante, tentativi=3):
    for tentativo in range(tentativi):
        try:
            print(f"🖨 Tentativo {tentativo + 1} di connessione alla stampante {ip_stampante}...")

            # 🔹 Connessione alla stampante termica con timeout maggiore
            p = Network(ip_stampante, timeout=10)  

            # 🔹 Reset della stampante
            p._raw(b'\x1B\x40')  

            # 🔹 Layout del ticket
            p.set(align='center')
            p._raw(b"************************\n")
            p._raw(b"        TICKET        \n")
            p._raw(b"************************\n\n")

            p._raw(b"Reparto: " + reparto_nome.encode('utf-8') + b"\n\n")

            # 🔹 Numero del ticket con cornice
            numero_str = f"  {ticket_number}  "  # Spazi extra per centrare il numero
            bordo_superiore = "═" * (len(numero_str) + 2)
            bordo_laterale = f"║{numero_str}║"

            p._raw(b'\x1D\x21\x22')  # 🔹 TESTO 4X PIÙ GRANDE
            p._raw(b" " + bordo_superiore.encode('utf-8') + b" \n")
            p._raw(b" " + bordo_laterale.encode('utf-8') + b" \n")
            p._raw(b" " + bordo_superiore.encode('utf-8') + b" \n\n")
            p._raw(b'\x1D\x21\x00')  # 🔹 Reset dimensione testo

            p._raw(b"----------------------\n")

            # 🔹 Taglio della carta
            p.cut()

            # 🔹 Chiude la connessione
            p.close()

            print(f"✅ Ticket stampato con successo per {reparto_nome} (N. {ticket_number})")
            return True  # Stampa riuscita

        except Exception as e:
            print(f"⚠️ Tentativo {tentativo + 1} fallito: {e}")
            time.sleep(3)  # 🔹 Aspetta 3 secondi prima di ritentare
            
    print(f"❌ Errore definitivo: impossibile connettersi alla stampante {ip_stampante} dopo {tentativi} tentativi.")
    return False  # Se dopo tutti i tentativi non riesce, restituisce errore



def get_ticket_data(reparto_id):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Recuperiamo il reparto specifico e l'IP della stampante
    cursor.execute("""
        SELECT r.nome, t.numero_massimo + 1, r.ip_address
        FROM reparti r
        INNER JOIN ticket_reparto t ON r.id = t.id_reparto
        WHERE t.id_reparto = %s
    """, (reparto_id,))
    result = cursor.fetchone()
    
    if result:
        reparto_nome, numero_ticket, ip_stampante = result

        # Aggiorniamo il numero massimo del ticket SOLO per il reparto selezionato
        cursor.execute("UPDATE ticket_reparto SET numero_massimo = %s WHERE id_reparto = %s", (numero_ticket, reparto_id))
        conn.commit()
        
        cursor.close()
        conn.close()

        return {
            "success": True,
            "reparto": reparto_nome,
            "numero_ticket": numero_ticket,
            "ip_stampante": ip_stampante
        }
    else:
        cursor.close()
        conn.close()
        return {"success": False}

@app.route("/api/get_ticket", methods=["GET"])
def get_ticket():
    reparto_id = request.args.get("reparto_id")  # Riceviamo l'ID del reparto dalla richiesta
    if not reparto_id:
        return jsonify({"success": False, "error": "Nessun ID reparto specificato"})

    print(f"📢 DEBUG: Richiesta ricevuta per reparto ID {reparto_id}")  # <-- Aggiunto per debug
    return jsonify(get_ticket_data(reparto_id))


if __name__ == "__main__":
    db = Database()
    db.crea_tabelle()
    db.close()
    app.run(host="0.0.0.0", port=5000)
