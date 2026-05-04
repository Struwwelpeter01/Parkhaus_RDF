from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime
import json
import os

# Flask-App mit korrekten Pfaden initialisieren
app_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, 
            template_folder=os.path.join(app_dir, 'templates'),
            static_folder=os.path.join(app_dir, 'static'))

# Datenbank-Verbindung
def get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'parkhaus.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Datenbank initialisieren
def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fahrzeuge (
                kennzeichen TEXT PRIMARY KEY,
                name TEXT,
                status TEXT DEFAULT 'aktiv',
                erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS parkvorgaenge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kennzeichen TEXT,
                einfahrt_zeit TIMESTAMP,
                ausfahrt_zeit TIMESTAMP,
                kosten REAL DEFAULT 0.0,
                bezahlt BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (kennzeichen) REFERENCES fahrzeuge (kennzeichen)
            )
        ''')

        conn.commit()

# Hauptseite - Dashboard
@app.route('/')
def dashboard():
    return render_template('dashboard.html')

# API: Alle Fahrzeuge abrufen (für Debugging/Entwicklung)
@app.route('/api/fahrzeuge', methods=['GET'])
def get_fahrzeuge():
    with get_db() as conn:
        fahrzeuge = conn.execute('SELECT * FROM fahrzeuge ORDER BY erstellt_am DESC').fetchall()
    return jsonify([dict(row) for row in fahrzeuge])

# API: Neues Fahrzeug hinzufügen (nicht mehr verwendet, Fahrzeuge werden automatisch erstellt)
@app.route('/api/fahrzeuge', methods=['POST'])
def add_fahrzeug():
    data = request.get_json()
    kennzeichen = data.get('kennzeichen')
    name = data.get('name', '')

    if not kennzeichen:
        return jsonify({'error': 'Kennzeichen erforderlich'}), 400

    try:
        with get_db() as conn:
            conn.execute('INSERT INTO fahrzeuge (kennzeichen, name) VALUES (?, ?)',
                        (kennzeichen.upper(), name))
            conn.commit()
        return jsonify({'success': True, 'message': 'Fahrzeug hinzugefügt'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Kennzeichen bereits vorhanden'}), 400

# API: Parkvorgang starten (Einfahrt) - Erstellt Fahrzeug automatisch falls nicht vorhanden
@app.route('/api/parkvorgang/start/<kennzeichen>', methods=['POST'])
def start_parkvorgang(kennzeichen):
    kennzeichen = kennzeichen.upper()

    # Fahrzeug automatisch erstellen falls nicht vorhanden
    with get_db() as conn:
        fahrzeug = conn.execute('SELECT * FROM fahrzeuge WHERE kennzeichen = ?',
                               (kennzeichen,)).fetchone()

        if not fahrzeug:
            # Neues Fahrzeug erstellen
            conn.execute('INSERT INTO fahrzeuge (kennzeichen) VALUES (?)',
                        (kennzeichen,))
            conn.commit()

    # Parkvorgang starten
    with get_db() as conn:
        conn.execute('''
            INSERT INTO parkvorgaenge (kennzeichen, einfahrt_zeit)
            VALUES (?, ?)
        ''', (kennzeichen, datetime.now()))
        conn.commit()

    return jsonify({'success': True, 'message': 'Parkvorgang gestartet'})

# API: Parkvorgang beenden (Ausfahrt)
@app.route('/api/parkvorgang/end/<kennzeichen>', methods=['POST'])
def end_parkvorgang(kennzeichen):
    kennzeichen = kennzeichen.upper()

    # Aktuellen Parkvorgang finden
    with get_db() as conn:
        vorgaenge = conn.execute('''
            SELECT * FROM parkvorgaenge
            WHERE kennzeichen = ? AND ausfahrt_zeit IS NULL
            ORDER BY einfahrt_zeit DESC LIMIT 1
        ''', (kennzeichen,)).fetchall()

    if not vorgaenge:
        return jsonify({'error': 'Kein aktiver Parkvorgang gefunden'}), 404

    vorgang = vorgaenge[0]
    einfahrt = datetime.fromisoformat(vorgang['einfahrt_zeit'])
    ausfahrt = datetime.now()

    # Kosten berechnen: 2€ Start + 1€ pro 20 Sekunden
    dauer_sekunden = (ausfahrt - einfahrt).total_seconds()
    kosten = 2.0 + (dauer_sekunden // 20) * 1.0

    # Parkvorgang aktualisieren
    with get_db() as conn:
        conn.execute('''
            UPDATE parkvorgaenge
            SET ausfahrt_zeit = ?, kosten = ?, bezahlt = TRUE
            WHERE id = ?
        ''', (ausfahrt, kosten, vorgang['id']))
        conn.commit()

    return jsonify({
        'success': True,
        'kosten': kosten,
        'dauer_minuten': round(dauer_sekunden / 60, 1)
    })

# API: Aktuelle Parkvorgänge abrufen
@app.route('/api/parkvorgaenge/aktiv', methods=['GET'])
def get_aktive_parkvorgaenge():
    with get_db() as conn:
        vorgaenge = conn.execute('''
            SELECT p.*, f.name
            FROM parkvorgaenge p
            JOIN fahrzeuge f ON p.kennzeichen = f.kennzeichen
            WHERE p.ausfahrt_zeit IS NULL
            ORDER BY p.einfahrt_zeit DESC
        ''').fetchall()

    result = []
    for v in vorgaenge:
        einfahrt = datetime.fromisoformat(v['einfahrt_zeit'])
        dauer_sekunden = (datetime.now() - einfahrt).total_seconds()
        kosten = 2.0 + (dauer_sekunden // 20) * 1.0

        result.append({
            'id': v['id'],
            'kennzeichen': v['kennzeichen'],
            'name': v['name'],
            'einfahrt_zeit': v['einfahrt_zeit'],
            'dauer_minuten': round(dauer_sekunden / 60, 1),
            'kosten': kosten
        })

    return jsonify(result)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)