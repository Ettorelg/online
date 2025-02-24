import psycopg2
from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "supersecretkey"
socketio = SocketIO(app)

# Configurazione Database Online
DATABASE_URL = "postgresql://postgres:ukhOvjJOEWKeSFdAewMFfzoKzCvGqhTT@gondola.proxy.rlwy.net:42614/railway"

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

    def crea_tabelle():
        """Crea le tabelle necessarie nel database PostgreSQL."""
        conn = psycopg2.connect("postgres://postgres:ukhOvjJOEWKeSFdAewMFfzoKzCvGqhTT@gondola.proxy.rlwy.net:42614/railway")
        cursor = conn.cursor()

        cursor.execute('''
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS licenze (
                id SERIAL PRIMARY KEY,
                id_utente INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                data_scadenza TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reparti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_reparto (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                id_reparto INTEGER REFERENCES reparti(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticket_reparto (
                id_reparto INTEGER PRIMARY KEY,
                numero_attuale INTEGER DEFAULT 0,
                numero_massimo INTEGER DEFAULT 0,
                FOREIGN KEY (id_reparto) REFERENCES reparti(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorie (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                prezzo DECIMAL(10,2) NOT NULL,
                tempo_produzione INTEGER NOT NULL, -- Tempo in minuti
                id_categoria INTEGER REFERENCES categorie(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dipendenti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                cognome TEXT NOT NULL,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calendario (
                id SERIAL PRIMARY KEY,
                id_utente INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
                id_prodotto INTEGER REFERENCES prodotti(id) ON DELETE CASCADE,
                id_dipendente INTEGER REFERENCES dipendenti(id) ON DELETE CASCADE,
                data_ora TIMESTAMP NOT NULL
            )
        ''')

        conn.commit()
        cursor.close()
        conn.close()

    if __name__ == "__main__":
        crea_tabelle()

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
            return redirect("/dashboard_admin") if is_admin else redirect("/dashboard_utente")
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

    # Connessione al database locale SQLite
    conn = sqlite3.connect("local.db")
    cursor = conn.cursor()

    # Recupera tutte le licenze attive
    cursor.execute("SELECT tipo, data_scadenza FROM licenze WHERE id_utente = ?", (user_id,))
    licenze = cursor.fetchall()

    # Controlla se l'utente ha la licenza "eliminacode"
    eliminacode_attiva = any(licenza[0] == "eliminacode" for licenza in licenze)

    conn.close()

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
        # Branch per aggiornare le licenze, identificato dal campo nascosto update_licenze
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

        elif "nuovo_reparto" in request.form:
            if "eliminacode" in licenze_attuali:
                licenza_id_result = db.execute_query(
                    "SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'eliminacode'",
                    (user_id,)
                )
                if licenza_id_result:
                    nuovo_reparto = request.form["nuovo_reparto"].strip()
                    db.execute_query(
                        "INSERT INTO reparti (nome, id_licenza) VALUES (%s, %s)",
                        (nuovo_reparto, licenza_id_result[0][0]), commit=True
                    )
        elif "elimina_reparto" in request.form:
            reparto_id = request.form["elimina_reparto"]
            db.execute_query("DELETE FROM reparti WHERE id = %s", (reparto_id,), commit=True)
        elif "nuova_fila" in request.form:
            reparto_id = request.form.get("reparto_id")
            nuova_fila = request.form.get("nuova_fila").strip()
            if nuova_fila and reparto_id:
                db.execute_query(
                    "INSERT INTO file_reparto (nome, id_reparto) VALUES (%s, %s)",
                    (nuova_fila, reparto_id), commit=True
                )
        elif "elimina_file" in request.form:
            file_id = request.form["elimina_file"]
            db.execute_query("DELETE FROM file_reparto WHERE id = %s", (file_id,), commit=True)

        db.conn.commit()
        db.close()
        return redirect(f"/gestisci_licenze/{user_id}")

    reparti = []
    file_reparto = {}
    if "eliminacode" in licenze_attuali:
        reparti = db.execute_query(
            "SELECT id, nome FROM reparti WHERE id_licenza = (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'eliminacode')",
            (user_id,)
        )
        for reparto_id, reparto_nome in reparti:
            file_reparto[reparto_id] = db.execute_query(
                "SELECT id, nome FROM file_reparto WHERE id_reparto = %s",
                (reparto_id,)
            )
    db.close()
    return render_template("gestisci_licenze.html", user_id=user_id, licenze_disponibili=licenze_disponibili,
                           licenze_attuali=licenze_attuali, reparti=reparti, file_reparto=file_reparto)









@app.route("/ritira_ticket", methods=["GET", "POST"])
def ritira_ticket():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("local.db", timeout=10)  # Impostiamo il timeout
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.id, r.nome 
        FROM reparti r
        INNER JOIN licenze l ON r.id_licenza = l.id
        WHERE l.id_utente = ? 
          AND l.tipo = 'eliminacode'
          AND l.data_scadenza >= DATE('now')
    """, (session["user_id"],))
    reparti = cursor.fetchall()

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        reparto_nome = request.form.get("reparto_nome")

        if reparto_id and reparto_nome:
            try:
                cursor.execute("BEGIN IMMEDIATE")  # 🔄 Lock immediato per evitare deadlock
                
                # **Verifica se il reparto esiste in `ticket_reparto`**
                cursor.execute("SELECT numero_massimo FROM ticket_reparto WHERE id_reparto = ?", (reparto_id,))
                result = cursor.fetchone()

                if result is None:
                    # **Se il reparto non esiste, lo inseriamo**
                    cursor.execute("INSERT INTO ticket_reparto (id_reparto, numero_attuale, numero_massimo) VALUES (?, 0, 1)", (reparto_id,))
                    ticket_number = 1
                else:
                    # **Se il reparto esiste, aggiorniamo il ticket**
                    cursor.execute("UPDATE ticket_reparto SET numero_massimo = numero_massimo + 1 WHERE id_reparto = ?", (reparto_id,))
                    cursor.execute("SELECT numero_massimo FROM ticket_reparto WHERE id_reparto = ?", (reparto_id,))
                    ticket_number = cursor.fetchone()[0]

                conn.commit()  # ✅ Confermiamo la transazione
                
                return redirect(f"/visualizza_ticket/{reparto_nome}/{ticket_number}")

            except sqlite3.OperationalError as e:
                print(f"❌ Errore SQLite: {e}")
                conn.rollback()  # 🔄 Annulliamo la transazione in caso di errore

            finally:
                conn.close()  # ✅ Chiudiamo la connessione sempre

    conn.close()
    return render_template("ritira_ticket.html", reparti=reparti)

@app.route("/visualizza_ticket/<reparto_nome>/<int:ticket_number>")
def visualizza_ticket(reparto_nome, ticket_number):
    """Visualizza il ticket su una nuova pagina."""
    return render_template("visualizza_ticket.html", reparto_nome=reparto_nome, ticket_number=ticket_number)

@app.route("/ticket_chiamato")
def ticket_chiamato():
    if "user_id" not in session:
        return redirect("/login")

    db = Database()
    numeri_chiamati = db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    db.close()
    return render_template("ticket_chiamato.html", numeri_chiamati=dict(numeri_chiamati))

@app.route("/stampa_ticket/<reparto_nome>/<int:ticket_number>")
def stampa_ticket(reparto_nome, ticket_number):
    """Simula la stampa del ticket generando una pagina HTML."""
    return render_template("stampa_ticket.html", reparto_nome=reparto_nome, ticket_number=ticket_number)

@app.route("/ticket_chiamato")
def ticket_chiamato():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("local.db", timeout=10)
    cursor = conn.cursor()

    # Recupera solo i reparti dell'utente con licenza eliminacode attiva
    cursor.execute("""
        SELECT DISTINCT r.id, r.nome 
        FROM reparti r
        INNER JOIN licenze l ON r.id_licenza = l.id
        WHERE l.id_utente = ? 
          AND l.tipo = 'eliminacode'
          AND l.data_scadenza >= DATE('now')
    """, (session["user_id"],))
    reparti = cursor.fetchall()

    numeri_chiamati = {}

    cursor.execute("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    for row in cursor.fetchall():
        numeri_chiamati[row[0]] = row[1]

    conn.close()
    return render_template("ticket_chiamato.html", reparti=reparti, numeri_chiamati=numeri_chiamati)

@app.route("/aggiorna_ticket", methods=["POST"])
def aggiorna_ticket():
    """Quando un numero viene chiamato, aggiorna tutti i client in tempo reale."""
    conn = sqlite3.connect("local.db")
    cursor = conn.cursor()

    numeri_chiamati = {}
    cursor.execute("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    for row in cursor.fetchall():
        numeri_chiamati[row[0]] = row[1]

    conn.close()
    
    # Invia il numero aggiornato a tutti i client connessi
    socketio.emit("update_tickets", numeri_chiamati)
    return "OK", 200

@app.route("/gestione_ticket", methods=["GET", "POST"])
def gestione_ticket():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("local.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, nome FROM reparti")
    reparti = cursor.fetchall()

    numeri_ticket = {}
    cursor.execute("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    for row in cursor.fetchall():
        numeri_ticket[row[0]] = row[1]

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        azione = request.form.get("azione")

        if reparto_id and azione:
            cursor.execute("SELECT numero_attuale, numero_massimo FROM ticket_reparto WHERE id_reparto = ?", (reparto_id,))
            data = cursor.fetchone()

            if data:
                numero_attuale, numero_massimo = data

                if azione == "avanti" and numero_attuale < numero_massimo:
                    cursor.execute("UPDATE ticket_reparto SET numero_attuale = numero_attuale + 1 WHERE id_reparto = ?", (reparto_id,))
                elif azione == "indietro" and numero_attuale > 0:
                    cursor.execute("UPDATE ticket_reparto SET numero_attuale = numero_attuale - 1 WHERE id_reparto = ?", (reparto_id,))
                elif azione == "reset":
                    cursor.execute("UPDATE ticket_reparto SET numero_attuale = 0 WHERE id_reparto = ?", (reparto_id,))

                conn.commit()

                # **RICARICA il numero aggiornato dopo la modifica**
                cursor.execute("SELECT numero_attuale FROM ticket_reparto WHERE id_reparto = ?", (reparto_id,))
                numero_attuale = cursor.fetchone()[0]

                # **Invia l'aggiornamento a tutti i client in tempo reale**
                socketio.emit("update_tickets", {reparto_id: numero_attuale})
                print(f"🔄 WebSocket aggiornato per Reparto {reparto_id}: {numero_attuale}")

    # Recupera i numeri aggiornati
    numeri_ticket = {}
    cursor.execute("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    for row in cursor.fetchall():
        numeri_ticket[row[0]] = row[1]

    conn.close()
    return render_template("gestione_ticket.html", reparti=reparti, numeri_ticket=numeri_ticket)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
