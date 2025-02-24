import psycopg2
from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "supersecretkey"
socketio = SocketIO(app)

# Configurazione Database Online
DATABASE_URL = "postgres://postgres:UtxXzInfMUgaiaLsAHQODWUkeaKkfIcl@maglev.proxy.rlwy.net:59078/railway"

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

@app.route("/dashboard_utente")
def dashboard_utente():
    if not session.get("user_id"):
        return redirect("/login")
    return render_template("dashboard_utente.html")

@app.route("/ritira_ticket", methods=["GET", "POST"])
def ritira_ticket():
    if "user_id" not in session:
        return redirect("/login")

    db = Database()
    reparti = db.execute_query("SELECT id, nome FROM reparti")

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        reparto_nome = request.form.get("reparto_nome")
        
        if reparto_id and reparto_nome:
            result = db.execute_query("SELECT numero_massimo FROM ticket_reparto WHERE id_reparto = %s", (reparto_id,))
            if result:
                ticket_number = result[0][0] + 1
                db.execute_query("UPDATE ticket_reparto SET numero_massimo = %s WHERE id_reparto = %s", (ticket_number, reparto_id), commit=True)
            else:
                ticket_number = 1
                db.execute_query("INSERT INTO ticket_reparto (id_reparto, numero_attuale, numero_massimo) VALUES (%s, 0, %s)", (reparto_id, ticket_number), commit=True)
            db.close()
            return redirect(f"/visualizza_ticket/{reparto_nome}/{ticket_number}")

    db.close()
    return render_template("ritira_ticket.html", reparti=reparti)

@app.route("/visualizza_ticket/<reparto_nome>/<int:ticket_number>")
def visualizza_ticket(reparto_nome, ticket_number):
    return render_template("visualizza_ticket.html", reparto_nome=reparto_nome, ticket_number=ticket_number)

@app.route("/ticket_chiamato")
def ticket_chiamato():
    if "user_id" not in session:
        return redirect("/login")

    db = Database()
    numeri_chiamati = db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto")
    db.close()
    return render_template("ticket_chiamato.html", numeri_chiamati=dict(numeri_chiamati))

@app.route("/aggiorna_ticket", methods=["POST"])
def aggiorna_ticket():
    db = Database()
    numeri_chiamati = dict(db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto"))
    db.close()
    socketio.emit("update_tickets", numeri_chiamati)
    return "OK", 200

@app.route("/gestione_ticket", methods=["GET", "POST"])
def gestione_ticket():
    if "user_id" not in session:
        return redirect("/login")

    db = Database()
    reparti = db.execute_query("SELECT id, nome FROM reparti")
    numeri_ticket = dict(db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto"))

    if request.method == "POST":
        reparto_id = request.form.get("reparto")
        azione = request.form.get("azione")

        if reparto_id and azione:
            if azione == "avanti":
                db.execute_query("UPDATE ticket_reparto SET numero_attuale = numero_attuale + 1 WHERE id_reparto = %s", (reparto_id,), commit=True)
            elif azione == "indietro":
                db.execute_query("UPDATE ticket_reparto SET numero_attuale = numero_attuale - 1 WHERE id_reparto = %s", (reparto_id,), commit=True)
            elif azione == "reset":
                db.execute_query("UPDATE ticket_reparto SET numero_attuale = 0 WHERE id_reparto = %s", (reparto_id,), commit=True)
            numeri_ticket = dict(db.execute_query("SELECT id_reparto, numero_attuale FROM ticket_reparto"))
            socketio.emit("update_tickets", numeri_ticket)

    db.close()
    return render_template("gestione_ticket.html", reparti=reparti, numeri_ticket=numeri_ticket)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
