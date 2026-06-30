from flask import Flask, Response, render_template, request, jsonify
import csv
import io
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from camera_recognition import CameraPlateRecognizer, camera_recognizer


app_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(app_dir, "templates"),
    static_folder=os.path.join(app_dir, "static"),
)

PRICE_PERMANENT = 365.0
PAYMENT_WINDOW_MINUTES = 10
MAX_PARKPLAETZE = 15
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROTOKOLL_DIR = PROJECT_ROOT / "data" / "protokoll"
PROTOKOLL_CSV = PROTOKOLL_DIR / "parkhaus_protokoll.csv"
WHITELIST_CSV = PROJECT_ROOT / "data" / "whitelist.csv"
GATE_PULSE_SECONDS = 0.18
gate_outputs = {}
gate_states = {
    "entry": {"open": False, "updated_at": 0.0},
    "exit": {"open": False, "updated_at": 0.0},
}

exit_camera_source = os.getenv("PARKHAUS_EXIT_CAMERA_SOURCE", "").strip()
exit_camera_recognizer = (
    CameraPlateRecognizer(source=int(exit_camera_source))
    if exit_camera_source
    else camera_recognizer
)


def get_db():
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "parkhaus.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_gate_pin(gate):
    env_name = "PARKHAUS_GATE_ENTRY_GPIO" if gate == "entry" else "PARKHAUS_GATE_EXIT_GPIO"
    value = os.getenv(env_name, "").strip()
    return int(value) if value else None


def pulse_gate(gate):
    pin = get_gate_pin(gate)
    if pin is None:
        return False

    try:
        from gpiozero import OutputDevice
    except Exception:
        return False

    if gate not in gate_outputs:
        gate_outputs[gate] = OutputDevice(pin, active_high=True, initial_value=False)

    gate_outputs[gate].on()
    time.sleep(GATE_PULSE_SECONDS)
    gate_outputs[gate].off()
    return True


def is_gate_open(gate):
    return bool(gate_states.get(gate, {}).get("open"))


def set_gate_state(gate, open_state):
    gate_states[gate] = {"open": bool(open_state), "updated_at": time.time()}


def normalize_plate(kennzeichen):
    return " ".join((kennzeichen or "").strip().upper().replace("-", " ").split())


def read_whitelist():
    if not WHITELIST_CSV.exists():
        return set()

    with WHITELIST_CSV.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        return {
            normalize_plate(row.get("Kennzeichen"))
            for row in reader
            if normalize_plate(row.get("Kennzeichen"))
        }


def write_whitelist(kennzeichen_set):
    WHITELIST_CSV.parent.mkdir(parents=True, exist_ok=True)
    with WHITELIST_CSV.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerow(["Kennzeichen"])
        for kennzeichen in sorted(kennzeichen_set):
            writer.writerow([kennzeichen])


def add_to_whitelist(kennzeichen):
    kennzeichen = normalize_plate(kennzeichen)
    if not kennzeichen:
        return

    whitelist = read_whitelist()
    if kennzeichen not in whitelist:
        whitelist.add(kennzeichen)
        write_whitelist(whitelist)


def is_whitelisted(kennzeichen):
    return normalize_plate(kennzeichen) in read_whitelist()


def sync_dauerparker_whitelist(conn):
    whitelist = read_whitelist()
    rows = conn.execute(
        "SELECT kennzeichen FROM fahrzeuge WHERE fahrzeug_typ = 'dauerparker'"
    ).fetchall()
    updated = False
    for row in rows:
        kennzeichen = normalize_plate(row["kennzeichen"])
        if kennzeichen and kennzeichen not in whitelist:
            whitelist.add(kennzeichen)
            updated = True

    if updated or not WHITELIST_CSV.exists():
        write_whitelist(whitelist)


def calculate_cost(einfahrt_zeit, fahrzeug_typ="normal"):
    if fahrzeug_typ == "dauerparker":
        return 0.0

    einfahrt = datetime.fromisoformat(einfahrt_zeit)
    dauer_sekunden = (datetime.now() - einfahrt).total_seconds()
    return 2.0 + (dauer_sekunden // 20) * 1.0


def ensure_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def log_event(
    conn,
    kennzeichen,
    richtung,
    entscheidung,
    grund="",
    aktion="",
    fahrzeug_typ="",
    kosten=None,
    details="",
):
    conn.execute(
        """
        INSERT INTO protokoll (
            datum_zeit, kennzeichen, richtung, entscheidung, grund,
            aktion, fahrzeug_typ, kosten, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (datetime.now(), kennzeichen, richtung, entscheidung, grund, aktion, fahrzeug_typ, kosten, details),
    )
    write_protokoll_csv(conn)


def write_protokoll_csv(conn):
    PROTOKOLL_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT datum_zeit, kennzeichen, richtung, aktion, entscheidung, grund,
               fahrzeug_typ, kosten, details
        FROM protokoll
        ORDER BY datum_zeit DESC
        """
    ).fetchall()

    with PROTOKOLL_CSV.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerow([
            "Datum/Uhrzeit",
            "Kennzeichen",
            "Richtung",
            "Aktion",
            "Annahme/Ablehnung",
            "Grund",
            "Fahrzeugtyp",
            "Kosten",
            "Details",
        ])
        for row in rows:
            writer.writerow([
                row["datum_zeit"],
                row["kennzeichen"],
                row["richtung"],
                row["aktion"],
                row["entscheidung"],
                row["grund"],
                row["fahrzeug_typ"],
                "" if row["kosten"] is None else f"{float(row['kosten']):.2f}",
                row["details"],
            ])


def migrate_plate_format(conn):
    fahrzeuge = conn.execute("SELECT kennzeichen FROM fahrzeuge WHERE kennzeichen LIKE '%-%'").fetchall()
    for row in fahrzeuge:
        old_plate = row["kennzeichen"]
        new_plate = normalize_plate(old_plate)
        exists = conn.execute("SELECT 1 FROM fahrzeuge WHERE kennzeichen = ?", (new_plate,)).fetchone()
        if exists:
            continue

        conn.execute("UPDATE fahrzeuge SET kennzeichen = ? WHERE kennzeichen = ?", (new_plate, old_plate))
        conn.execute("UPDATE parkvorgaenge SET kennzeichen = ? WHERE kennzeichen = ?", (new_plate, old_plate))

    conn.execute("UPDATE parkvorgaenge SET kennzeichen = replace(kennzeichen, '-', ' ') WHERE kennzeichen LIKE '%-%'")


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fahrzeuge (
                kennzeichen TEXT PRIMARY KEY,
                name TEXT,
                status TEXT DEFAULT 'aktiv',
                erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(conn, "fahrzeuge", "fahrzeug_typ", "TEXT DEFAULT 'normal'")
        ensure_column(conn, "fahrzeuge", "dauerparker_bezahlt", "BOOLEAN DEFAULT FALSE")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parkvorgaenge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kennzeichen TEXT,
                einfahrt_zeit TIMESTAMP,
                ausfahrt_zeit TIMESTAMP,
                kosten REAL DEFAULT 0.0,
                bezahlt BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (kennzeichen) REFERENCES fahrzeuge (kennzeichen)
            )
            """
        )
        ensure_column(conn, "parkvorgaenge", "bezahlt_bis", "TIMESTAMP")
        ensure_column(conn, "parkvorgaenge", "ausfahrt_blockiert", "BOOLEAN DEFAULT FALSE")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS protokoll (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datum_zeit TIMESTAMP,
                kennzeichen TEXT,
                richtung TEXT,
                entscheidung TEXT,
                grund TEXT
            )
            """
        )
        ensure_column(conn, "protokoll", "aktion", "TEXT DEFAULT ''")
        ensure_column(conn, "protokoll", "fahrzeug_typ", "TEXT DEFAULT ''")
        ensure_column(conn, "protokoll", "kosten", "REAL")
        ensure_column(conn, "protokoll", "details", "TEXT DEFAULT ''")
        migrate_plate_format(conn)
        sync_dauerparker_whitelist(conn)
        write_protokoll_csv(conn)
        conn.commit()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/kamera/kennzeichen", methods=["GET"])
def get_kamera_kennzeichen():
    return jsonify(camera_recognizer.get_state())


@app.route("/api/kamera/kennzeichen/ausfahrt", methods=["GET"])
def get_ausfahrt_kamera_kennzeichen():
    return jsonify(exit_camera_recognizer.get_state())


@app.route("/api/whitelist/pruefen/<path:kennzeichen>", methods=["GET"])
def pruefe_whitelist(kennzeichen):
    kennzeichen = normalize_plate(kennzeichen)
    return jsonify({"kennzeichen": kennzeichen, "allowed": is_whitelisted(kennzeichen)})


@app.route("/api/kamera/stream")
def get_kamera_stream():
    return stream_camera(camera_recognizer)


@app.route("/api/kamera/stream/ausfahrt")
def get_ausfahrt_kamera_stream():
    return stream_camera(exit_camera_recognizer)


def stream_camera(recognizer):
    def generate():
        while True:
            frame = recognizer.get_jpeg()
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.02)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/fahrzeuge", methods=["GET"])
def get_fahrzeuge():
    with get_db() as conn:
        fahrzeuge = conn.execute("SELECT * FROM fahrzeuge ORDER BY erstellt_am DESC").fetchall()
    return jsonify([dict(row) for row in fahrzeuge])


@app.route("/api/fahrzeuge", methods=["POST"])
def add_fahrzeug():
    data = request.get_json(silent=True) or {}
    kennzeichen = normalize_plate(data.get("kennzeichen"))
    name = data.get("name", "")
    fahrzeug_typ = data.get("fahrzeug_typ", "normal")

    if not kennzeichen:
        return jsonify({"error": "Kennzeichen erforderlich"}), 400

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO fahrzeuge (kennzeichen, name, fahrzeug_typ, dauerparker_bezahlt)
                VALUES (?, ?, ?, ?)
                """,
                (kennzeichen, name, fahrzeug_typ, fahrzeug_typ == "dauerparker"),
            )
            conn.commit()
        return jsonify({"success": True, "message": "Fahrzeug hinzugefuegt"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Kennzeichen bereits vorhanden"}), 400


@app.route("/api/dauerparker", methods=["GET"])
def get_dauerparker():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT kennzeichen, name, erstellt_am
            FROM fahrzeuge
            WHERE fahrzeug_typ = 'dauerparker'
            ORDER BY kennzeichen ASC
            """
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/dauerparker", methods=["POST"])
def book_dauerparker():
    data = request.get_json(silent=True) or {}
    kennzeichen = normalize_plate(data.get("kennzeichen"))
    name = data.get("name", "")

    if not kennzeichen:
        return jsonify({"error": "Kennzeichen erforderlich"}), 400

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO fahrzeuge (kennzeichen, name, fahrzeug_typ, dauerparker_bezahlt)
            VALUES (?, ?, 'dauerparker', TRUE)
            ON CONFLICT(kennzeichen) DO UPDATE SET
                name = excluded.name,
                fahrzeug_typ = 'dauerparker',
                dauerparker_bezahlt = TRUE
            """,
            (kennzeichen, name),
        )
        add_to_whitelist(kennzeichen)
        log_event(
            conn,
            kennzeichen,
            "Verwaltung",
            "Annahme",
            "Dauerparker gebucht",
            aktion="Dauerparker gebucht",
            fahrzeug_typ="dauerparker",
            kosten=PRICE_PERMANENT,
            details="Dauerparker darf dauerhaft ein- und ausfahren",
        )
        conn.commit()

    return jsonify({"success": True, "kennzeichen": kennzeichen})


@app.route("/api/dauerparker/<path:kennzeichen>", methods=["DELETE"])
def delete_dauerparker(kennzeichen):
    kennzeichen = normalize_plate(kennzeichen)
    if not kennzeichen:
        return jsonify({"error": "Kennzeichen erforderlich"}), 400

    with get_db() as conn:
        fahrzeug = conn.execute(
            "SELECT fahrzeug_typ FROM fahrzeuge WHERE kennzeichen = ?",
            (kennzeichen,),
        ).fetchone()
        if not fahrzeug or fahrzeug["fahrzeug_typ"] != "dauerparker":
            return jsonify({"error": "Dauerparker nicht gefunden"}), 404

        conn.execute(
            """
            UPDATE fahrzeuge
            SET fahrzeug_typ = 'normal', dauerparker_bezahlt = FALSE
            WHERE kennzeichen = ?
            """,
            (kennzeichen,),
        )
        conn.execute(
            """
            UPDATE parkvorgaenge
            SET bezahlt = FALSE, bezahlt_bis = NULL
            WHERE kennzeichen = ? AND ausfahrt_zeit IS NULL
            """,
            (kennzeichen,),
        )
        log_event(
            conn,
            kennzeichen,
            "Verwaltung",
            "Annahme",
            "Dauerparker entfernt",
            aktion="Dauerparker entfernt",
            fahrzeug_typ="normal",
            details="Abo abgelaufen oder manuell geloescht",
        )
        conn.commit()

    return jsonify({"success": True, "kennzeichen": kennzeichen})

@app.route("/api/parkvorgang/start/<path:kennzeichen>", methods=["POST"])
def start_parkvorgang(kennzeichen):
    kennzeichen = normalize_plate(kennzeichen)
    data = request.get_json(silent=True) or {}
    fahrzeug_typ = data.get("fahrzeug_typ", "normal")
    automatisch = bool(data.get("automatisch"))
    if fahrzeug_typ not in {"normal", "dauerparker"}:
        fahrzeug_typ = "normal"

    if not kennzeichen:
        return jsonify({"error": "Kennzeichen erforderlich"}), 400

    with get_db() as conn:
        if automatisch and not is_whitelisted(kennzeichen):
            log_event(
                conn,
                kennzeichen,
                "Einfahrt",
                "Ablehnung",
                "Kennzeichen nicht auf White-List",
                aktion="Automatische Einfahrt",
                fahrzeug_typ=fahrzeug_typ,
                details="Neue Kennzeichen muessen haendisch bestaetigt werden",
            )
            conn.commit()
            return jsonify({"error": "Kennzeichen muss zuerst haendisch bestaetigt werden."}), 403

        if is_gate_open("entry"):
            log_event(
                conn,
                kennzeichen,
                "Einfahrt",
                "Ablehnung",
                "Einfahrtsschranke ist noch offen",
                aktion="Einfahrt angefordert",
                fahrzeug_typ=fahrzeug_typ,
                details="Kennzeichenerkennung bis Schranke zu gesperrt",
            )
            conn.commit()
            return jsonify({"error": "Einfahrt gesperrt: Schranke ist noch offen."}), 409

        belegte_plaetze = conn.execute(
            "SELECT COUNT(*) AS anzahl FROM parkvorgaenge WHERE ausfahrt_zeit IS NULL"
        ).fetchone()["anzahl"]
        if belegte_plaetze >= MAX_PARKPLAETZE:
            log_event(
                conn,
                kennzeichen,
                "Einfahrt",
                "Ablehnung",
                "Zu viele Autos im Parkhaus",
                aktion="Einfahrt angefordert",
                fahrzeug_typ=fahrzeug_typ,
                details=f"{belegte_plaetze}/{MAX_PARKPLAETZE} Plaetze belegt",
            )
            conn.commit()
            return jsonify({"error": "Parkhaus ist voll. Keine Einfahrt moeglich."}), 400

        fahrzeug = conn.execute(
            "SELECT * FROM fahrzeuge WHERE kennzeichen = ?",
            (kennzeichen,),
        ).fetchone()

        if not fahrzeug:
            conn.execute(
                """
                INSERT INTO fahrzeuge (kennzeichen, fahrzeug_typ, dauerparker_bezahlt)
                VALUES (?, ?, ?)
                """,
                (kennzeichen, fahrzeug_typ, fahrzeug_typ == "dauerparker"),
            )
        elif fahrzeug_typ == "dauerparker" and fahrzeug["fahrzeug_typ"] != "dauerparker":
            conn.execute(
                """
                UPDATE fahrzeuge
                SET fahrzeug_typ = 'dauerparker', dauerparker_bezahlt = TRUE
                WHERE kennzeichen = ?
                """,
                (kennzeichen,),
            )
        elif fahrzeug["fahrzeug_typ"] == "dauerparker":
            fahrzeug_typ = "dauerparker"

        aktiv = conn.execute(
            """
            SELECT id FROM parkvorgaenge
            WHERE kennzeichen = ? AND ausfahrt_zeit IS NULL
            LIMIT 1
            """,
            (kennzeichen,),
        ).fetchone()
        if aktiv:
            log_event(
                conn,
                kennzeichen,
                "Einfahrt",
                "Ablehnung",
                "Fahrzeug ist bereits aktiv",
                aktion="Einfahrt angefordert",
                fahrzeug_typ=fahrzeug_typ,
            )
            conn.commit()
            return jsonify({"error": "Fahrzeug ist bereits im Parkhaus"}), 400

        conn.execute(
            """
            INSERT INTO parkvorgaenge (kennzeichen, einfahrt_zeit, bezahlt)
            VALUES (?, ?, ?)
            """,
            (kennzeichen, datetime.now(), fahrzeug_typ == "dauerparker"),
        )
        log_event(
            conn,
            kennzeichen,
            "Einfahrt",
            "Annahme",
            "Dauerparker" if fahrzeug_typ == "dauerparker" else "Normal",
            aktion="Einfahrt gestartet",
            fahrzeug_typ=fahrzeug_typ,
            kosten=PRICE_PERMANENT if fahrzeug_typ == "dauerparker" else None,
            details="Dauerparker-Festpreis 365 EUR" if fahrzeug_typ == "dauerparker" else "Normaler Parkvorgang",
        )
        conn.commit()

    add_to_whitelist(kennzeichen)
    return jsonify({"success": True, "message": "Parkvorgang gestartet", "kennzeichen": kennzeichen})


@app.route("/api/parkvorgang/end/<path:kennzeichen>", methods=["POST"])
def end_parkvorgang(kennzeichen):
    kennzeichen = normalize_plate(kennzeichen)

    with get_db() as conn:
        if is_gate_open("exit"):
            log_event(
                conn,
                kennzeichen,
                "Ausfahrt",
                "Ablehnung",
                "Ausfahrtsschranke ist noch offen",
                aktion="Ausfahrt erkannt",
                details="Kennzeichenerkennung bis Schranke zu gesperrt",
            )
            conn.commit()
            return jsonify({"error": "Ausfahrt gesperrt: Schranke ist noch offen."}), 409

        vorgang = conn.execute(
            """
            SELECT p.*, f.fahrzeug_typ
            FROM parkvorgaenge p
            JOIN fahrzeuge f ON p.kennzeichen = f.kennzeichen
            WHERE p.kennzeichen = ? AND p.ausfahrt_zeit IS NULL
            ORDER BY p.einfahrt_zeit DESC LIMIT 1
            """,
            (kennzeichen,),
        ).fetchone()

        if not vorgang:
            fahrzeug = conn.execute(
                "SELECT fahrzeug_typ FROM fahrzeuge WHERE kennzeichen = ?",
                (kennzeichen,),
            ).fetchone()
            if fahrzeug and fahrzeug["fahrzeug_typ"] == "dauerparker":
                log_event(
                    conn,
                    kennzeichen,
                    "Ausfahrt",
                    "Annahme",
                    "Dauerparker-Ausfahrt erlaubt",
                    aktion="Ausfahrt automatisch",
                    fahrzeug_typ="dauerparker",
                    kosten=0.0,
                    details="Gebuchter Dauerparker ohne aktiven Parkvorgang",
                )
                conn.commit()
                return jsonify({"success": True, "kosten": 0.0, "dauer_minuten": 0})

            log_event(
                conn,
                kennzeichen,
                "Ausfahrt",
                "Ablehnung",
                "Kein aktiver Parkvorgang gefunden",
                aktion="Ausfahrt erkannt",
            )
            conn.commit()
            return jsonify({"error": "Kein aktiver Parkvorgang gefunden"}), 404

        if vorgang["fahrzeug_typ"] != "dauerparker" and not vorgang["bezahlt"]:
            conn.execute("UPDATE parkvorgaenge SET ausfahrt_blockiert = TRUE WHERE id = ?", (vorgang["id"],))
            log_event(
                conn,
                kennzeichen,
                "Ausfahrt",
                "Ablehnung",
                "Bitte vor Ausfahrt bezahlen",
                aktion="Ausfahrt erkannt",
                fahrzeug_typ=vorgang["fahrzeug_typ"],
                kosten=calculate_cost(vorgang["einfahrt_zeit"], vorgang["fahrzeug_typ"]),
                details="Bezahlt-Haekchen fehlt",
            )
            conn.commit()
            return jsonify({"error": "Bitte vor Ausfahrt bezahlen"}), 402

        if vorgang["fahrzeug_typ"] != "dauerparker" and vorgang["bezahlt_bis"]:
            bezahlt_bis = datetime.fromisoformat(vorgang["bezahlt_bis"])
            if datetime.now() > bezahlt_bis:
                conn.execute(
                    """
                    UPDATE parkvorgaenge
                    SET bezahlt = FALSE, bezahlt_bis = NULL, ausfahrt_blockiert = TRUE
                    WHERE id = ?
                    """,
                    (vorgang["id"],),
                )
                log_event(
                    conn,
                    kennzeichen,
                    "Ausfahrt",
                    "Ablehnung",
                    "Bezahlzeit abgelaufen",
                    aktion="Ausfahrt erkannt",
                    fahrzeug_typ=vorgang["fahrzeug_typ"],
                    kosten=calculate_cost(vorgang["einfahrt_zeit"], vorgang["fahrzeug_typ"]),
                    details="10-Minuten-Zeitfenster ueberschritten",
                )
                conn.commit()
                return jsonify({"error": "Bitte vor Ausfahrt bezahlen"}), 402

        ausfahrt = datetime.now()
        einfahrt = datetime.fromisoformat(vorgang["einfahrt_zeit"])
        dauer_sekunden = (ausfahrt - einfahrt).total_seconds()
        kosten = calculate_cost(vorgang["einfahrt_zeit"], vorgang["fahrzeug_typ"])

        conn.execute(
            """
            UPDATE parkvorgaenge
            SET ausfahrt_zeit = ?, kosten = ?, bezahlt = TRUE, ausfahrt_blockiert = FALSE
            WHERE id = ?
            """,
            (ausfahrt, kosten, vorgang["id"]),
        )
        log_event(
            conn,
            kennzeichen,
            "Ausfahrt",
            "Annahme",
            "Ausfahrt erlaubt",
            aktion="Ausfahrt automatisch",
            fahrzeug_typ=vorgang["fahrzeug_typ"],
            kosten=kosten,
            details="Dauerparker" if vorgang["fahrzeug_typ"] == "dauerparker" else "Bezahlt und innerhalb des Zeitfensters",
        )
        conn.commit()

    return jsonify({"success": True, "kosten": kosten, "dauer_minuten": round(dauer_sekunden / 60, 1)})


@app.route("/api/parkvorgang/notfall-ausfahrt/<path:kennzeichen>", methods=["POST"])
def notfall_ausfahrt(kennzeichen):
    kennzeichen = normalize_plate(kennzeichen)
    if not kennzeichen:
        return jsonify({"error": "Kennzeichen erforderlich"}), 400

    with get_db() as conn:
        if is_gate_open("exit"):
            log_event(
                conn,
                kennzeichen,
                "Ausfahrt",
                "Ablehnung",
                "Ausfahrtsschranke ist noch offen",
                aktion="Notfall-Ausfahrt",
                details="Notfall-Ausfahrt erst nach geschlossener Schranke moeglich",
            )
            conn.commit()
            return jsonify({"error": "Ausfahrt gesperrt: Schranke ist noch offen."}), 409

        vorgang = conn.execute(
            """
            SELECT p.*, f.fahrzeug_typ
            FROM parkvorgaenge p
            JOIN fahrzeuge f ON p.kennzeichen = f.kennzeichen
            WHERE p.kennzeichen = ? AND p.ausfahrt_zeit IS NULL
            ORDER BY p.einfahrt_zeit DESC LIMIT 1
            """,
            (kennzeichen,),
        ).fetchone()

        if not vorgang:
            log_event(
                conn,
                kennzeichen,
                "Ausfahrt",
                "Ablehnung",
                "Kein aktiver Parkvorgang gefunden",
                aktion="Notfall-Ausfahrt",
            )
            conn.commit()
            return jsonify({"error": "Kein aktiver Parkvorgang gefunden"}), 404

        ausfahrt = datetime.now()
        einfahrt = datetime.fromisoformat(vorgang["einfahrt_zeit"])
        dauer_sekunden = (ausfahrt - einfahrt).total_seconds()
        kosten = calculate_cost(vorgang["einfahrt_zeit"], vorgang["fahrzeug_typ"])

        conn.execute(
            """
            UPDATE parkvorgaenge
            SET ausfahrt_zeit = ?, kosten = ?, ausfahrt_blockiert = FALSE
            WHERE id = ?
            """,
            (ausfahrt, kosten, vorgang["id"]),
        )
        log_event(
            conn,
            kennzeichen,
            "Ausfahrt",
            "Annahme",
            "Manuelle Notfall-Ausfahrt",
            aktion="Notfall-Ausfahrt",
            fahrzeug_typ=vorgang["fahrzeug_typ"],
            kosten=kosten,
            details="Ausfahrt wurde haendisch ausgeloest",
        )
        conn.commit()

    return jsonify({"success": True, "kosten": kosten, "dauer_minuten": round(dauer_sekunden / 60, 1)})


@app.route("/api/parkvorgaenge/aktiv", methods=["GET"])
def get_aktive_parkvorgaenge():
    result = []

    with get_db() as conn:
        vorgaenge = conn.execute(
            """
            SELECT p.*, f.name, f.fahrzeug_typ
            FROM parkvorgaenge p
            JOIN fahrzeuge f ON p.kennzeichen = f.kennzeichen
            WHERE p.ausfahrt_zeit IS NULL
            ORDER BY p.einfahrt_zeit DESC
            """
        ).fetchall()

        for v in vorgaenge:
            einfahrt = datetime.fromisoformat(v["einfahrt_zeit"])
            dauer_sekunden = (datetime.now() - einfahrt).total_seconds()
            kosten = calculate_cost(v["einfahrt_zeit"], v["fahrzeug_typ"])
            bezahlt = bool(v["bezahlt"])
            bezahlt_bis = v["bezahlt_bis"]

            if bezahlt and bezahlt_bis and datetime.now() > datetime.fromisoformat(bezahlt_bis):
                conn.execute(
                    """
                    UPDATE parkvorgaenge
                    SET bezahlt = FALSE, bezahlt_bis = NULL
                    WHERE id = ?
                    """,
                    (v["id"],),
                )
                log_event(
                    conn,
                    v["kennzeichen"],
                    "Kasse",
                    "Ablehnung",
                    "Bezahlzeit abgelaufen",
                    aktion="Bezahlfenster abgelaufen",
                    fahrzeug_typ=v["fahrzeug_typ"],
                    kosten=kosten,
                    details="Bezahlt-Haekchen wurde nach 10 Minuten automatisch entfernt",
                )
                conn.commit()
                bezahlt = False
                bezahlt_bis = None

            result.append(
                {
                    "id": v["id"],
                    "kennzeichen": v["kennzeichen"],
                    "name": v["name"],
                    "fahrzeug_typ": v["fahrzeug_typ"],
                    "einfahrt_zeit": v["einfahrt_zeit"],
                    "dauer_minuten": round(dauer_sekunden / 60, 1),
                    "kosten": kosten,
                    "bezahlt": bezahlt,
                    "bezahlt_bis": bezahlt_bis,
                    "ausfahrt_blockiert": bool(v["ausfahrt_blockiert"]),
                }
            )

    return jsonify(result)


@app.route("/api/parkvorgang/<int:vorgang_id>/bezahlt", methods=["POST"])
def set_bezahlt(vorgang_id):
    data = request.get_json(silent=True) or {}
    bezahlt = bool(data.get("bezahlt"))
    bezahlt_bis = datetime.now() + timedelta(minutes=PAYMENT_WINDOW_MINUTES) if bezahlt else None

    with get_db() as conn:
        vorgang = conn.execute(
            """
            SELECT p.*, f.fahrzeug_typ
            FROM parkvorgaenge p
            JOIN fahrzeuge f ON p.kennzeichen = f.kennzeichen
            WHERE p.id = ? AND p.ausfahrt_zeit IS NULL
            """,
            (vorgang_id,),
        ).fetchone()
        if not vorgang:
            return jsonify({"error": "Aktiver Parkvorgang nicht gefunden"}), 404

        if vorgang["fahrzeug_typ"] == "dauerparker":
            bezahlt = True
            bezahlt_bis = None

        conn.execute(
            """
            UPDATE parkvorgaenge
            SET bezahlt = ?, bezahlt_bis = ?, ausfahrt_blockiert = FALSE
            WHERE id = ?
            """,
            (bezahlt, bezahlt_bis, vorgang_id),
        )
        log_event(
            conn,
            vorgang["kennzeichen"],
            "Kasse",
            "Annahme",
            "Kunde hat gezahlt" if bezahlt else "Bezahlstatus entfernt",
            aktion="Bezahlstatus geaendert",
            fahrzeug_typ=vorgang["fahrzeug_typ"],
            kosten=calculate_cost(vorgang["einfahrt_zeit"], vorgang["fahrzeug_typ"]),
            details=(
                f"Ausfahrt bis {bezahlt_bis.isoformat(timespec='seconds')} erlaubt"
                if bezahlt_bis
                else "Kein Ausfahrt-Zeitfenster aktiv"
            ),
        )
        conn.commit()

    return jsonify({"success": True, "bezahlt": bezahlt, "bezahlt_bis": bezahlt_bis})


@app.route("/api/schranke/<gate>/<action>", methods=["POST"])
def schalte_schranke(gate, action):
    if gate not in {"entry", "exit"} or action not in {"open", "close"}:
        return jsonify({"error": "Ungueltige Schrankenaktion"}), 400

    set_gate_state(gate, action == "open")
    richtung = "Einfahrt" if gate == "entry" else "Ausfahrt"
    hardware_enabled = pulse_gate(gate)
    with get_db() as conn:
        log_event(
            conn,
            "",
            richtung,
            "Annahme",
            "Schranke geoeffnet" if action == "open" else "Schranke geschlossen",
            aktion=f"Schranke {action}",
            details="GPIO-Impuls gesendet" if hardware_enabled else "Kein GPIO-Pin konfiguriert",
        )
        conn.commit()

    return jsonify({"success": True, "hardware_enabled": hardware_enabled})


@app.route("/api/protokoll", methods=["GET"])
def get_protokoll():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT datum_zeit, kennzeichen, richtung, aktion, entscheidung, grund,
                   fahrzeug_typ, kosten, details
            FROM protokoll
            ORDER BY datum_zeit DESC
            LIMIT 100
            """
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/protokoll.csv", methods=["GET"])
def download_protokoll():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT datum_zeit, kennzeichen, richtung, aktion, entscheidung, grund,
                   fahrzeug_typ, kosten, details
            FROM protokoll
            ORDER BY datum_zeit DESC
            """
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Datum/Uhrzeit", "Kennzeichen", "Richtung", "Aktion", "Annahme/Ablehnung", "Grund", "Fahrzeugtyp", "Kosten", "Details"])
    for row in rows:
        writer.writerow([
            row["datum_zeit"],
            row["kennzeichen"],
            row["richtung"],
            row["aktion"],
            row["entscheidung"],
            row["grund"],
            row["fahrzeug_typ"],
            "" if row["kosten"] is None else f"{float(row['kosten']):.2f}",
            row["details"],
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=parkhaus_protokoll.csv"},
    )


init_db()


if __name__ == "__main__":
    camera_recognizer.start()
    if exit_camera_recognizer is not camera_recognizer:
        exit_camera_recognizer.start()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
