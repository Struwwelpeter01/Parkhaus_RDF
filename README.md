# Parkhaus Management System

## Übersicht
Ein vollständiges Web-Dashboard für die Verwaltung eines Parkhauses mit Kennzeichen-Erkennung, Parkzeit-Verfolgung und Kostenberechnung basierend auf YOLO11 und OCR.

## Features
- ✅ **Einfache Kennzeichen-Eingabe**: Format "AB-1234" (1-2 Buchstaben + 4 Ziffern)
- ✅ **Automatische Fahrzeug-Erstellung**: Keine separate Registrierung nötig
- ✅ **Zwei Ampeln**: Parkhaus-Status (0/15) + Schranken-Status
- ✅ **Schranken-Steuerung**: 3 Sek warten → 5 Sek offen → automatisch zu
- ✅ **Live-Kostenberechnung**: 2€ Start + 1€ pro 20 Sekunden
- ✅ **Responsive Design**: Funktioniert auf Desktop und Mobile

## Installation & Start

### 1. Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 2. Dashboard starten
```bash
cd src
python app.py
```

### 3. Dashboard öffnen
Öffne deinen Browser und gehe zu: **http://127.0.0.1:5000**

## Projekt-Struktur
```
Parkhaus_RDF/
├── src/
│   ├── app.py              # Flask-Hauptapplikation
│   ├── templates/
│   │   └── dashboard.html  # HTML-Dashboard
│   └── static/
│       ├── css/
│       │   └── dashboard.css
│       └── js/
│           └── dashboard.js
├── data/
│   └── parkhaus.db         # SQLite-Datenbank
├── config/                 # Konfigurationsdateien
├── tests/                  # Tests
├── docs/                   # Dokumentation
├── build/                  # Kompilierte Dateien
├── requirements.txt        # Python-Abhängigkeiten
└── README.md
```

## API-Endpunkte

### Fahrzeuge
- `GET /api/fahrzeuge` - Alle registrierten Fahrzeuge abrufen (für Debugging)

### Parkvorgänge
- `POST /api/parkvorgang/start/<kennzeichen>` - Parkvorgang starten (Fahrzeug wird automatisch erstellt)
- `POST /api/parkvorgang/end/<kennzeichen>` - Parkvorgang beenden
- `GET /api/parkvorgaenge/aktiv` - Aktive Parkvorgänge abrufen

## Demo-Modus
Das Dashboard enthält einen Demo-Button zum Simulieren von Kennzeichen-Eingaben für Tests.

## Technologien
- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript
- **Datenbank**: SQLite
- **KI**: YOLO11 + OCR für Kennzeichen-Erkennung (geplant)
- **Kommunikation**: MQTT zwischen Raspberry Pi und ESP32 (geplant)
- **Hardware**: Raspberry Pi, ESP32, Kameras, Schranken, Ampel (geplant)

## Nächste Schritte
1. **Hardware-Integration**: Raspberry Pi und ESP32 anschließen
2. **MQTT-Setup**: Kommunikation zwischen den Geräten
3. **YOLO11-Integration**: Echte Kennzeichen-Erkennung implementieren
4. **OCR-Integration**: Text aus Bildern extrahieren
5. **GPIO-Schaltung**: Schranken-Motoren und Ampel-LEDs ansteuern
sudo apt install -y python3-opencv python3-picamera2
```

Die Kamera sollte im Raspberry-Pi-System aktiviert sein. Bei aktuellen Raspberry
Pi OS Versionen funktioniert das normalerweise direkt mit `picamera2`.

### 2. Programm starten

Im Projektordner:

```bash
python3 capture_training_images.py --plate RO-AB123
```

Dann im Vorschaufenster:

- `s` speichert ein Bild
- `q` beendet das Programm

Die Bilder landen nach Kennzeichen sortiert in:

```text
data/raw/RO-AB123/
```

Zusaetzlich wird eine CSV-Datei geschrieben:

```text
data/manifest.csv
```

### Automatisch viele Bilder aufnehmen

Alle 2 Sekunden ein Bild speichern und nach 50 Bildern stoppen:

```bash
python3 capture_training_images.py --plate RO-AB123 --interval 2 --limit 50
```

Ohne Vorschaufenster, z.B. per SSH:

```bash
python3 capture_training_images.py --plate RO-AB123 --interval 2 --limit 50 --no-preview
```

### Tipps fuer gute Trainingsdaten

- Pro Kennzeichen mehrere Bilder aus leicht unterschiedlichen Winkeln aufnehmen.
- Unterschiedliche Helligkeit testen: hell, schattig, abends.
- Kennzeichen nicht nur perfekt mittig fotografieren.
- Unscharfe oder stark verdeckte Bilder spaeter aussortieren.
- Fuer den Anfang lieber wenige saubere Klassen/Bilder statt sehr viele schlechte.
>>>>>>> 59cfdc23729f74e0ccd2bde96062732258b8e9ad
