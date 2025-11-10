import os
import psycopg2
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
from escpos.printer import Network

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# Consigliato per SocketIO in produzione su Railway
socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*")

# DB: leggi da env (se non presente, fallback al tuo URL)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:xYYqHsLowEKfQarulXBolqWgHnMNTNgO@trolley.proxy.rlwy.net:34653/railway"
)


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
                ip_address TEXT,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE,
                visibile_ritira BOOLEAN NOT NULL DEFAULT FALSE,
                visibile_qr BOOLEAN NOT NULL DEFAULT FALSE
                visualizza_cronologia BOOLEAN NOT NULL DEFAULT FALSE
                visualizza_qr BOOLEAN NOT NULL DEFAULT FALSE
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS cronologia_ticket (
                id SERIAL PRIMARY KEY,
                reparto_id INTEGER NOT NULL REFERENCES reparti(id) ON DELETE CASCADE,
                numero INTEGER,
                azione TEXT NOT NULL CHECK (azione IN ('ritiro','chiamata','avanti','indietro','imposta','reset')),
                provenienza TEXT,                     -- es: 'qr', 'sportello', 'monitor', ecc.
                user_id INTEGER,                      -- opzionale: chi ha generato l’evento
                fila_id INTEGER,                      -- opzionale: se un domani vuoi tracciare la fila
                note TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
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
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorie (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS servizi (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                durata INTEGER NOT NULL,
                costo DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                id_categoria INTEGER REFERENCES categorie(id) ON DELETE CASCADE
            )
        ''')
        

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS personale (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                orario_inizio TIME NOT NULL DEFAULT '09:00',
                orario_fine TIME NOT NULL DEFAULT '18:00',
                id_licenza INTEGER REFERENCES licenze(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS personale_servizi (
                id_personale INTEGER REFERENCES personale(id) ON DELETE CASCADE,
                id_servizio INTEGER REFERENCES servizi(id) ON DELETE CASCADE,
                PRIMARY KEY (id_personale, id_servizio)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS prenotazioni (
                id SERIAL PRIMARY KEY,
                nome_cliente TEXT NOT NULL,
                id_servizio INTEGER REFERENCES servizi(id) ON DELETE CASCADE,
                id_personale INTEGER REFERENCES personale(id) ON DELETE CASCADE,
                orario TIMESTAMP NOT NULL
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

    # Recupera le licenze dell'utente
    licenze = db.execute_query(
        "SELECT tipo, data_scadenza FROM licenze WHERE id_utente = %s", (user_id,)
    )

    # Controlla se le licenze specifiche sono attive
    eliminacode_attiva = any(licenza[0] == "eliminacode" for licenza in licenze)
    prenotazioni_attiva = any(licenza[0] == "prenotazioni" for licenza in licenze)

    db.close()
    return render_template(
        "dashboard_user.html",
        username=session["username"],
        licenze=licenze,
        eliminacode_attiva=eliminacode_attiva,
        prenotazioni_attiva=prenotazioni_attiva
    )

@app.route("/gestione_eliminacode")
def gestione_eliminacode():
    if "user_id" not in session:
        return redirect("/login")
    
    return render_template("gestione_eliminacode.html")

from flask import jsonify

@app.route("/gestione_prenotazioni")
def gestione_prenotazioni_redirect():
    if "user_id" not in session:
        return redirect("/login")
    
    user_id = session["user_id"]
    return redirect(f"/gestione_prenotazioni/{user_id}")


@app.route("/gestione_prenotazioni/<int:user_id>")
def gestione_prenotazioni_user(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        return redirect("/login")

    db = Database()

    personale = db.execute_query(
        "SELECT id, nome FROM personale WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')",
        (user_id,)
    )

    db.close()
    return render_template("gestione_prenotazioni.html", user_id=user_id, personale=personale)


@app.route("/api/prenotazioni/<int:user_id>")
def api_prenotazioni(user_id):
    if "user_id" not in session:
        return jsonify([])

    db = Database()
    
    prenotazioni = db.execute_query("""
        SELECT p.id, p.nome_cliente, s.nome, pers.nome, p.orario 
        FROM prenotazioni p 
        JOIN servizi s ON p.id_servizio = s.id 
        JOIN personale pers ON p.id_personale = pers.id 
        WHERE s.id_categoria IN (
            SELECT id FROM categorie WHERE id_licenza IN (
                SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'
            )
        )
    """, (user_id,))

    db.close()

    events = []
    for prenotazione in prenotazioni:
        prenotazione_id, cliente_nome, servizio_nome, personale_nome, orario = prenotazione
        events.append({
            "id": prenotazione_id,
            "title": f"{cliente_nome} - {servizio_nome}",
            "start": orario.isoformat(),
            "extendedProps": {
                "personale": f"Assegnato a: {personale_nome}"
            }
        })

    return jsonify(events)

@app.route("/api/prenotazioni_personale/<int:personale_id>")
def api_prenotazioni_personale(personale_id):
    if "user_id" not in session:
        return jsonify([])

    db = Database()
    
    prenotazioni = db.execute_query("""
        SELECT p.id, p.nome_cliente, s.nome, s.durata, p.orario 
        FROM prenotazioni p 
        JOIN servizi s ON p.id_servizio = s.id 
        WHERE p.id_personale = %s
    """, (personale_id,))

    db.close()

    events = []
    for prenotazione in prenotazioni:
        prenotazione_id, cliente_nome, servizio_nome, durata, orario = prenotazione

        # Calcolo dell'ora di fine
        from datetime import datetime, timedelta
        inizio = datetime.fromisoformat(str(orario))
        fine = inizio + timedelta(minutes=durata)

        events.append({
            "id": prenotazione_id,
            "title": f"{servizio_nome}",
            "start": inizio.isoformat(),
            "end": fine.isoformat(),
            "extendedProps": {
                "cliente": f"Cliente: {cliente_nome}",
                "durata": f"{durata} min",
                "orario_fine": fine.strftime("%H:%M")
            }
        })

    return jsonify(events)


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
        azione = request.form.get("azione")

        # Gestione delle licenze
        if "update_licenze" in request.form:
            licenze_selezionate = request.form.getlist("licenze")
            for licenza in list(licenze_attuali.keys()):
                if licenza not in licenze_selezionate:
                    db.execute_query("DELETE FROM licenze WHERE id_utente = %s AND tipo = %s", (user_id, licenza), commit=True)
                    del licenze_attuali[licenza]

            for licenza in licenze_selezionate:
                if licenza not in licenze_attuali:
                    scadenza = (datetime.today() + timedelta(days=365)).strftime("%Y-%m-%d")
                    db.execute_query("INSERT INTO licenze (id_utente, tipo, data_scadenza) VALUES (%s, %s, %s)", (user_id, licenza, scadenza), commit=True)
                    licenze_attuali[licenza] = scadenza

            for licenza in licenze_attuali:
                if f"scadenza_{licenza}" in request.form:
                    nuova_scadenza = request.form[f"scadenza_{licenza}"]
                    db.execute_query("UPDATE licenze SET data_scadenza = %s WHERE id_utente = %s AND tipo = %s", (nuova_scadenza, user_id, licenza), commit=True)

        # Gestione categorie
        elif azione == "aggiungi_categoria":
            nome_categoria = request.form.get("nome_categoria").strip()
            if nome_categoria:
                db.execute_query("INSERT INTO categorie (nome, id_licenza) VALUES (%s, (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'))", 
                                 (nome_categoria, user_id), commit=True)

        elif azione == "elimina_categoria":
            categoria_id = request.form.get("categoria_id")
            db.execute_query("DELETE FROM categorie WHERE id = %s", (categoria_id,), commit=True)

        # Gestione servizi
        elif azione == "aggiungi_servizio":
            nome_servizio = request.form.get("nome_servizio").strip()
            tempo_servizio = request.form.get("tempo_servizio")
            categoria_id = request.form.get("categoria_id")
            if nome_servizio and tempo_servizio.isdigit() and categoria_id:
                db.execute_query("INSERT INTO servizi (nome, durata, id_categoria) VALUES (%s, %s, %s)", 
                                 (nome_servizio, int(tempo_servizio), categoria_id), commit=True)

        elif azione == "elimina_servizio":
            servizio_id = request.form.get("servizio_id")
            db.execute_query("DELETE FROM servizi WHERE id = %s", (servizio_id,), commit=True)

        # Gestione personale
        elif azione == "aggiungi_personale":
            nome_personale = request.form.get("nome_personale").strip()
            if nome_personale:
                db.execute_query("INSERT INTO personale (nome, id_licenza) VALUES (%s, (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'))", 
                                 (nome_personale, user_id), commit=True)

        elif azione == "elimina_personale":
            personale_id = request.form.get("personale_id")
            db.execute_query("DELETE FROM personale WHERE id = %s", (personale_id,), commit=True)

        # Gestione prenotazioni
        elif azione == "aggiungi_prenotazione":
            cliente_nome = request.form.get("cliente_nome").strip()
            servizio_id = request.form.get("servizio_id")
            personale_id = request.form.get("personale_id")
            orario = request.form.get("orario")

            if cliente_nome and servizio_id and personale_id and orario:
                db.execute_query("INSERT INTO prenotazioni (nome_cliente, id_servizio, id_personale, orario) VALUES (%s, %s, %s, %s)", 
                                 (cliente_nome, servizio_id, personale_id, orario), commit=True)

        elif azione == "elimina_prenotazione":
            prenotazione_id = request.form.get("prenotazione_id")
            db.execute_query("DELETE FROM prenotazioni WHERE id = %s", (prenotazione_id,), commit=True)

        db.close()
        return redirect(f"/gestisci_licenze/{user_id}")

    # Recupero dati per la visualizzazione
    categorie, servizi, personale, prenotazioni = [], [], [], []
    if "prenotazioni" in licenze_attuali:
        categorie = db.execute_query( "SELECT id, nome FROM categorie WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')", (user_id,))
        servizi = db.execute_query(
            "SELECT s.id, s.nome, s.durata, COALESCE(s.costo, 0.00), c.nome "
            "FROM servizi s "
            "JOIN categorie c ON s.id_categoria = c.id "
            "WHERE c.id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')",(user_id,))
        personale = db.execute_query("SELECT id, nome FROM personale WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')",(user_id,))
        prenotazioni = db.execute_query("SELECT p.id, p.nome_cliente, s.nome, pers.nome, p.orario FROM prenotazioni p JOIN servizi s ON p.id_servizio = s.id JOIN personale pers ON p.id_personale = pers.id WHERE s.id_categoria IN (SELECT id FROM categorie WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'))",(user_id,))

    db.close()
    return render_template("gestisci_licenze.html", user_id=user_id, licenze_disponibili=licenze_disponibili,
                           licenze_attuali=licenze_attuali, categorie=categorie, servizi=servizi, personale=personale, prenotazioni=prenotazioni)

@app.route("/gestisci_eliminacode/<int:user_id>", methods=["GET", "POST"])
def gestisci_eliminacode(user_id):
    if not session.get("is_admin"):
        return redirect("/login")

    db = Database()

    if request.method == "POST":
        azione = request.form.get("azione")

        if azione == "aggiungi_reparto":
            nome_reparto = request.form.get("nuovo_reparto").strip()
            ip_reparto = request.form.get("ip_reparto", "").strip()  # Permetti IP vuoto
            visibile_ritira = request.form.get("visibile_ritira", "off") == "on"  # Visibilità in ritira_ticket
            visibile_qr = request.form.get("visibile_qr", "off") == "on"  # Visibilità in visualizza_ticket_qr
            if nome_reparto:
                db.execute_query(
                    "INSERT INTO reparti (nome, ip_address, id_licenza, visibile_ritira, visibile_qr) VALUES (%s, NULLIF(%s, ''), (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'eliminacode'), %s, %s)", 
                    (nome_reparto, ip_reparto, user_id, visibile_ritira, visibile_qr), commit=True
                )
                # Assegna di default il numero massimo a 0 quando si crea un nuovo reparto
                reparto_id = db.execute_query("SELECT id FROM reparti WHERE nome = %s", (nome_reparto,))[0][0]
                db.execute_query(
                    "INSERT INTO ticket_reparto (id_reparto, numero_attuale, numero_massimo) VALUES (%s, 0, 0)",
                    (reparto_id,), commit=True
                )

        elif azione == "modifica_ip":
            reparto_id = request.form.get("reparto_id")
            nuovo_ip = request.form.get("nuovo_ip", "").strip()
            db.execute_query("UPDATE reparti SET ip_address = NULLIF(%s, '') WHERE id = %s", (nuovo_ip, reparto_id), commit=True)

        elif azione == "modifica_visibilita":
            reparto_id = request.form.get("reparto_id")
            visibile_ritira = request.form.get("visibile_ritira", "off") == "on"
            visibile_qr = request.form.get("visibile_qr", "off") == "on"
            db.execute_query("UPDATE reparti SET visibile_ritira = %s, visibile_qr = %s WHERE id = %s", (visibile_ritira, visibile_qr, reparto_id), commit=True)

        elif azione == "elimina_reparto":
            reparto_id = request.form.get("elimina_reparto")
            db.execute_query("DELETE FROM reparti WHERE id = %s", (reparto_id,), commit=True)

        elif azione == "aggiungi_fila":
            reparto_id = request.form.get("reparto_id")
            nuova_fila = request.form.get("nuova_fila").strip()
            db.execute_query("INSERT INTO file_reparto (nome, id_reparto) VALUES (%s, %s)", (nuova_fila, reparto_id), commit=True)

        elif azione == "elimina_fila":
            fila_id = request.form.get("elimina_file")
            db.execute_query("DELETE FROM file_reparto WHERE id = %s", (fila_id,), commit=True)
        elif azione == "modifica_visualizzazione":
            reparto_id = request.form.get("reparto_id")
            # checkbox -> "on" se spuntato, assente se non spuntato
            vis_cron = request.form.get("visualizza_cronologia") == "on"
            vis_qr   = request.form.get("visualizza_QRcode") == "on"

            db.execute_query(
                "UPDATE reparti SET visualizza_cronologia = %s, visualizza_qrcode = %s WHERE id = %s",
                (vis_cron, vis_qr, reparto_id),
                commit=True
            )

        return redirect(f"/gestisci_eliminacode/{user_id}")

    reparti = db.execute_query(
        "SELECT id, nome, ip_address, visibile_ritira, visibile_qr, visualizza_cronologia, visualizza_qrcode "
        "FROM reparti WHERE id_licenza = (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'eliminacode')",
        (user_id,)
    )

    file_reparto = {
        reparto[0]: db.execute_query("SELECT id, nome FROM file_reparto WHERE id_reparto = %s", (reparto[0],)) for reparto in reparti
    }

    db.close()
    return render_template("gestisci_eliminacode.html", user_id=user_id, reparti=reparti, file_reparto=file_reparto)


@app.route("/gestisci_prenotazioni/<int:user_id>", methods=["GET", "POST"])
def gestisci_prenotazioni(user_id):
    if not session.get("is_admin"):
        return redirect("/login")

    db = Database()

    if request.method == "POST":
        azione = request.form.get("azione")

        # Gestione Categorie
        if azione == "aggiungi_categoria":
            nome_categoria = request.form.get("nome_categoria").strip()
            if nome_categoria:
                db.execute_query(
                    "INSERT INTO categorie (nome, id_licenza) VALUES (%s, (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'))",
                    (nome_categoria, user_id), commit=True
                )

        elif azione == "modifica_categoria":
            categoria_id = request.form.get("categoria_id")
            nuovo_nome = request.form.get("nuovo_nome", "").strip()

            result = db.execute_query("SELECT nome FROM categorie WHERE id = %s", (categoria_id,))
            if result:
                nome_attuale = result[0][0]
                nuovo_nome = nuovo_nome if nuovo_nome else nome_attuale

                db.execute_query("UPDATE categorie SET nome = %s WHERE id = %s", (nuovo_nome, categoria_id), commit=True)

        elif azione == "modifica_personale":
            personale_id = request.form.get("personale_id")
            nuovo_nome = request.form.get("nuovo_nome", "").strip()

            result = db.execute_query("SELECT nome FROM personale WHERE id = %s", (personale_id,))
            if result:
                nome_attuale = result[0][0]
                nuovo_nome = nuovo_nome if nuovo_nome else nome_attuale

                db.execute_query("UPDATE personale SET nome = %s WHERE id = %s", (nuovo_nome, personale_id), commit=True)

        elif azione == "modifica_prenotazione":
            prenotazione_id = request.form.get("prenotazione_id")
            nuovo_cliente = request.form.get("nuovo_cliente", "").strip()
            nuovo_servizio = request.form.get("nuovo_servizio", "").strip()
            nuovo_personale = request.form.get("nuovo_personale", "").strip()
            nuovo_orario = request.form.get("nuovo_orario", "").strip()

            result = db.execute_query("SELECT nome_cliente, id_servizio, id_personale, orario FROM prenotazioni WHERE id = %s", (prenotazione_id,))
            if result:
                cliente_attuale, servizio_attuale, personale_attuale, orario_attuale = result[0]

                nuovo_cliente = nuovo_cliente if nuovo_cliente else cliente_attuale
                nuovo_servizio = int(nuovo_servizio) if nuovo_servizio.isdigit() else servizio_attuale
                nuovo_personale = int(nuovo_personale) if nuovo_personale.isdigit() else personale_attuale
                nuovo_orario = nuovo_orario if nuovo_orario else orario_attuale

                db.execute_query(
                    "UPDATE prenotazioni SET nome_cliente = %s, id_servizio = %s, id_personale = %s, orario = %s WHERE id = %s",
                    (nuovo_cliente, nuovo_servizio, nuovo_personale, nuovo_orario, prenotazione_id), commit=True
                )

        elif azione == "elimina_categoria":
            categoria_id = request.form.get("categoria_id")
            db.execute_query("DELETE FROM categorie WHERE id = %s", (categoria_id,), commit=True)

        # Gestione Servizi
        elif azione == "aggiungi_servizio":
            nome_servizio = request.form.get("nome_servizio").strip()
            tempo_servizio = request.form.get("tempo_servizio")
            costo_servizio = request.form.get("costo_servizio")
            categoria_id = request.form.get("categoria_id")

            if nome_servizio and tempo_servizio.isdigit() and categoria_id and costo_servizio.replace('.', '', 1).isdigit():
                db.execute_query(
                    "INSERT INTO servizi (nome, durata, costo, id_categoria) VALUES (%s, %s, %s, %s)",
                    (nome_servizio, int(tempo_servizio), float(costo_servizio), categoria_id), commit=True
                )

        elif azione == "modifica_servizio":
            servizio_id = request.form.get("servizio_id")
            nuovo_nome = request.form.get("nuovo_nome", "").strip()
            nuova_durata = request.form.get("nuova_durata", "").strip()
            nuovo_costo = request.form.get("nuovo_costo", "").strip()

            # Recupera i valori attuali dal database
            result = db.execute_query("SELECT nome, durata, costo FROM servizi WHERE id = %s", (servizio_id,))
            if result:
                nome_attuale, durata_attuale, costo_attuale = result[0]

                # Mantieni il valore attuale se il campo è vuoto
                nuovo_nome = nuovo_nome if nuovo_nome else nome_attuale
                nuova_durata = int(nuova_durata) if nuova_durata.isdigit() else durata_attuale
                nuovo_costo = float(nuovo_costo) if nuovo_costo.replace('.', '', 1).isdigit() else costo_attuale

                # Esegui l'aggiornamento solo se qualcosa è cambiato
                db.execute_query(
                    "UPDATE servizi SET nome = %s, durata = %s, costo = %s WHERE id = %s",
                    (nuovo_nome, nuova_durata, nuovo_costo, servizio_id), commit=True
                )

        elif azione == "elimina_servizio":
            servizio_id = request.form.get("servizio_id")
            db.execute_query("DELETE FROM servizi WHERE id = %s", (servizio_id,), commit=True)

        # Gestione Personale
        elif azione == "aggiungi_personale":
            nome_personale = request.form.get("nome_personale").strip()
            if nome_personale:
                db.execute_query(
                    "INSERT INTO personale (nome, id_licenza) VALUES (%s, (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'))",
                    (nome_personale, user_id), commit=True
                )


        elif azione == "elimina_personale":
            personale_id = request.form.get("personale_id")
            db.execute_query("DELETE FROM personale WHERE id = %s", (personale_id,), commit=True)

        # Gestione Prenotazioni
        elif azione == "aggiungi_prenotazione":
            cliente_nome = request.form.get("cliente_nome").strip()
            servizio_id = request.form.get("servizio_id")
            personale_id = request.form.get("personale_id")
            orario = request.form.get("orario")

            if cliente_nome and servizio_id and personale_id and orario:
                db.execute_query(
                    "INSERT INTO prenotazioni (nome_cliente, id_servizio, id_personale, orario) VALUES (%s, %s, %s, %s)",
                    (cliente_nome, servizio_id, personale_id, orario), commit=True
                )


        elif azione == "elimina_prenotazione":
            prenotazione_id = request.form.get("prenotazione_id")
            db.execute_query("DELETE FROM prenotazioni WHERE id = %s", (prenotazione_id,), commit=True)

        return redirect(f"/gestisci_prenotazioni/{user_id}")

    # Recupero dati per la visualizzazione
    categorie = db.execute_query(
        "SELECT id, nome FROM categorie WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')",
        (user_id,)
    )

    servizi = db.execute_query(
        "SELECT s.id, s.nome, s.durata, s.costo, c.nome FROM servizi s JOIN categorie c ON s.id_categoria = c.id WHERE c.id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')",
        (user_id,)
    )

    personale = db.execute_query(
        "SELECT id, nome FROM personale WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni')",
        (user_id,)
    )

    prenotazioni = db.execute_query(
        "SELECT p.id, p.nome_cliente, s.nome, pers.nome, p.orario FROM prenotazioni p "
        "JOIN servizi s ON p.id_servizio = s.id "
        "JOIN personale pers ON p.id_personale = pers.id "
        "WHERE s.id_categoria IN (SELECT id FROM categorie WHERE id_licenza IN (SELECT id FROM licenze WHERE id_utente = %s AND tipo = 'prenotazioni'))",
        (user_id,)
    )

    db.close()
    return render_template(
        "gestisci_prenotazioni.html",
        user_id=user_id,
        categorie=categorie,
        servizi=servizi,
        personale=personale,
        prenotazioni=prenotazioni
    )

# 🔹 Route per ritirare il ticket
@app.route("/ritira_ticket", methods=["GET", "POST"])
def ritira_ticket():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    db = Database()

    # Recupera solo i reparti con visibile_ritira = TRUE
    reparti = db.execute_query("""
        SELECT DISTINCT r.id, r.nome, r.ip_address 
        FROM reparti r
        INNER JOIN licenze l ON r.id_licenza = l.id
        WHERE l.id_utente = %s  
          AND l.tipo = 'eliminacode'
          AND TO_DATE(l.data_scadenza, 'YYYY-MM-DD') >= CURRENT_DATE
          AND r.visibile_ritira = TRUE
    """, (user_id,))
    
    if request.method == "GET":
        db.close()
        return render_template("ritira_ticket.html", reparti=reparti, user_id=user_id)

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
        placeholders = ', '.join(['%s'] * len(reparti_ids))
        numeri_ticket_query = f"""
            SELECT id_reparto, numero_attuale 
            FROM ticket_reparto 
            WHERE id_reparto IN ({placeholders})
        """
        numeri_ticket = dict(db.execute_query(numeri_ticket_query, reparti_ids))

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        azione = request.form.get("azione")
        nuovo_numero = request.form.get("nuovo_numero")

        if reparto_id and azione and int(reparto_id) in reparti_ids:
            result = db.execute_query(
                "SELECT numero_attuale FROM ticket_reparto WHERE id_reparto = %s", 
                (reparto_id,)
            )

            if result:
                numero_attuale = result[0][0]

                if azione == "avanti":
                    numero_attuale += 1
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = %s WHERE id_reparto = %s",
                        (numero_attuale, reparto_id), commit=True
                    )

                elif azione == "indietro" and numero_attuale > 0:
                    numero_attuale -= 1
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = %s WHERE id_reparto = %s",
                        (numero_attuale, reparto_id), commit=True
                    )

                elif azione == "reset":
                    numero_attuale = 0
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = 0 WHERE id_reparto = %s",
                        (reparto_id,), commit=True
                    )

                elif azione == "imposta" and nuovo_numero.isdigit():
                    numero_attuale = int(nuovo_numero)
                    db.execute_query(
                        "UPDATE ticket_reparto SET numero_attuale = %s WHERE id_reparto = %s",
                        (numero_attuale, reparto_id), commit=True
                    )

                # Aggiorna la mappa con il nuovo valore
                numeri_ticket[int(reparto_id)] = numero_attuale

                # Aggiorna i ticket in tempo reale via WebSocket
                socketio.emit("update_tickets", numeri_ticket)

                # Se la richiesta viene da fetch (JS), restituiamo JSON
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": True, "new_value": numero_attuale})
    
    db.close()
    return render_template("gestione_ticket.html", reparti=reparti, numeri_ticket=numeri_ticket)

@app.route("/visualizza_ticket_qr")
def visualizza_ticket_qr():
    return render_template("visualizza_ticket_qr.html")

@app.route("/ritira_ticket_qr", methods=["GET", "POST"])
def ritira_ticket_qr():
    db = Database()

        # Ottieni l'user_id dalla query string
    if request.method == "GET":
        user_id = request.args.get("user", type=int)
    else:
        user_id = request.form.get("user", type=int)

    if not user_id:
        return jsonify({"success": False, "message": "Dati mancanti: user_id non trovato"}), 400

    # Recupera solo i reparti con visibile_qr = TRUE per l'utente specificato
    reparti = db.execute_query("""
        SELECT id, nome 
        FROM reparti 
        WHERE id_licenza IN (
            SELECT id FROM licenze WHERE id_utente = %s
        )
        AND visibile_qr = TRUE
    """, (user_id,))

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        user_id = request.form.get("user")

        if not reparto_id or not user_id:
            db.close()
            return jsonify({"success": False, "message": "Dati mancanti"}), 400

        reparto_nome_result = db.execute_query("SELECT nome FROM reparti WHERE id = %s", (reparto_id,))
        reparto_nome = reparto_nome_result[0][0] if reparto_nome_result else None

        result = db.execute_query("SELECT numero_massimo FROM ticket_reparto WHERE id_reparto = %s", (reparto_id,))
        ticket_number = (result[0][0] + 1) if result else 1

        db.execute_query(
            "UPDATE ticket_reparto SET numero_massimo = %s WHERE id_reparto = %s",
            (ticket_number, reparto_id), commit=True
        )

        db.close()

        return jsonify({
            "reparto_id": reparto_id,
            "reparto_nome": reparto_nome,
            "ticket_number": ticket_number
        })


        db.close()

        if not ticket_dati:
            return jsonify({"success": False, "message": "Errore nel generare i ticket"}), 500

        return render_template("visualizza_tutti_ticket.html", tickets=ticket_dati)

    db.close()
    return render_template("ritira_ticket_qr.html", reparti=reparti, user_id=user_id)

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

@app.route("/ticket_chiamato_cronologia")
def ticket_chiamato_cronologia():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
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
    return render_template(
        "ticket_chiamato_cronologia.html",
        user_id=user_id,
        reparti=reparti,
        numeri_chiamati=numeri_chiamati_dict,
        immagini=immagini_list
    )
        
@app.route("/api/cronologia_utente")
def api_cronologia_utente():
    # usa ?user=... se presente, altrimenti la sessione
    user_id = request.args.get("user", type=int) or session.get("user_id")
    if not user_id:
        return jsonify([])

    limit = request.args.get("limit", default=50, type=int)

    db = Database()
    rows = db.execute_query("""
        SELECT r.nome        AS reparto,
               c.numero      AS numero,
               c.azione      AS azione,
               c.created_at  AS created_at
        FROM cronologia_ticket c
        JOIN reparti r  ON r.id = c.reparto_id
        JOIN licenze l  ON r.id_licenza = l.id
        WHERE l.id_utente = %s
          AND c.azione = 'chiamata'          -- togli questa riga se vuoi tutte le azioni
        ORDER BY c.created_at DESC
        LIMIT %s
    """, (user_id, limit))
    db.close()

    data = [{
        "reparto":   r[0],
        "numero":    r[1],
        "azione":    r[2],
        "created_at": r[3].isoformat(),
        "ora":       r[3].strftime("%H:%M")   # comodo per la UI
    } for r in rows]
    return jsonify(data)

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

@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory("downloads", filename, as_attachment=True)

if __name__ == "__main__":
    db = Database()
    db.crea_tabelle()
    db.close()
    port = int(os.environ.get("PORT", 8000))
    # eventlet è consigliato con Flask-SocketIO
    socketio.run(app, host="0.0.0.0", port=port)
