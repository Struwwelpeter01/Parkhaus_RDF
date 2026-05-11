# Parkhaus Management System

## Uebersicht

Ein Web-Dashboard fuer die Verwaltung eines Parkhauses mit Kennzeichen-Erkennung,
Parkzeit-Verfolgung und Kostenberechnung.

## Features

- Einfache Kennzeichen-Eingabe im Format `AB-1234`
- Automatische Fahrzeug-Erstellung ohne separate Registrierung
- Zwei Ampeln: Parkhaus-Status und Schranken-Status
- Schranken-Steuerung mit automatischem Schliessen
- Live-Kostenberechnung
- Raspberry-Pi-5-Kamera im Dashboard
- Separates Programm zum Speichern von Kamerabildern

## Installation & Start

### 1. Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

Auf dem Raspberry Pi 5:

```bash
sudo apt update
sudo apt install -y python3-opencv python3-picamera2 python3-gpiozero
```

### 2. Dashboard starten

Im Projektordner:

```bash
python3 run.py
```

### 3. Dashboard oeffnen

Oeffne den Browser und gehe zu:

```text
http://127.0.0.1:5000
```

Auf dem Raspberry Pi wird automatisch die Pi-Kamera ueber `picamera2`
verwendet. Wenn `picamera2` nicht verfuegbar ist, nutzt das Projekt als
Fallback eine OpenCV/Webcam mit Kameraindex `0`.

## Bilder aufnehmen

Die Bildaufnahme laeuft separat vom Flask-Dashboard. Das Dashboard muss dafuer
nicht benutzt werden.

### Mit Tastatur im Vorschaufenster

```bash
python3 capture_training_images.py --plate RO-AB123
```

Im Vorschaufenster:

- `s` speichert das aktuelle Bild
- `q` beendet das Programm

Die Bilder landen nach Kennzeichen sortiert in:

```text
data/raw/RO-AB123/
```

Zusaetzlich wird eine CSV-Datei geschrieben:

```text
data/manifest.csv
```

### Mit physischem GPIO-Taster

Beispiel: Taster zwischen GPIO17 und GND anschliessen und starten mit:

```bash
python3 capture_training_images.py --plate RO-AB123 --button-gpio 17
```

Jeder Tastendruck speichert das aktuelle Kamerabild.

### Automatisch viele Bilder aufnehmen

Alle 2 Sekunden ein Bild speichern und nach 50 Bildern stoppen:

```bash
python3 capture_training_images.py --plate RO-AB123 --interval 2 --limit 50
```

Ohne Vorschaufenster, z.B. per SSH:

```bash
python3 capture_training_images.py --plate RO-AB123 --interval 2 --limit 50 --no-preview
```

## Projekt-Struktur

```text
Parkhaus_RDF/
├── capture_training_images.py
├── run.py
├── src/
│   ├── app.py
│   ├── camera_recognition.py
│   ├── camera_source.py
│   ├── templates/
│   └── static/
├── data/
├── config/
├── tests/
├── docs/
└── requirements.txt
```

## API-Endpunkte

- `GET /api/fahrzeuge` - Alle registrierten Fahrzeuge abrufen
- `POST /api/parkvorgang/start/<kennzeichen>` - Parkvorgang starten
- `POST /api/parkvorgang/end/<kennzeichen>` - Parkvorgang beenden
- `GET /api/parkvorgaenge/aktiv` - Aktive Parkvorgaenge abrufen

## Naechste Schritte

1. Hardware-Integration mit Raspberry Pi und ESP32 abschliessen
2. MQTT-Kommunikation zwischen den Geraeten einbauen
3. YOLO/OCR-Erkennung weiter verbessern
4. GPIO-Schaltung fuer Schranke und Ampel anbinden
