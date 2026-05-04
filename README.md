# Parkhaus_RDF

Code fuer eine Parkhaussteuerung mit Raspberry Pi 4 und Pi-Kamera.

Der erste Schritt ist ein kleines Aufnahmeprogramm fuer Trainingsbilder von
Kennzeichen. Die spaetere Steuerung kann darauf aufbauen:

- Kennzeichen beim Einfahren erkennen, anzeigen und speichern
- pro Kennzeichen eine Parkzeit starten
- beim Ausfahren Kennzeichen eingeben, Kosten berechnen und nach Zahlung die
  Schranke oeffnen

## Trainingsbilder aufnehmen

### 1. Raspberry Pi vorbereiten

Auf dem Raspberry Pi:

```bash
sudo apt update
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
