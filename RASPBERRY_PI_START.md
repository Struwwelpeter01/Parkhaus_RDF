# Parkhaus-Projekt komplett auf Raspberry Pi 5 starten

Diese Anleitung ist fuer den Praesentationsbetrieb gedacht: Der Raspberry Pi
startet das komplette Parkhaus-Programm selbst, nutzt seine Kamera selbst und
zeigt das Dashboard auf einem direkt angeschlossenen Bildschirm an. Ein Laptop
wird bei der Praesentation nicht benoetigt.

Du brauchst am Raspberry Pi:

- Netzteil
- Bildschirm per HDMI
- Maus/Tastatur
- Raspberry-Pi-Kamera oder USB-Kamera
- Internet nur fuer Installation/Updates, danach kann das Programm lokal laufen

## 1. Raspberry Pi vorbereiten

Auf dem Pi ein Terminal oeffnen.

System aktualisieren und Grundpakete installieren:

```bash
sudo apt update
sudo apt install -y git chromium-browser python3-venv python3-pip python3-opencv python3-picamera2 python3-gpiozero
```

Falls du die offizielle Raspberry-Pi-Kamera nutzt, pruefen ob sie erkannt wird:

```bash
rpicam-hello --timeout 3000
```

## 2. Projekt auf den Pi holen

Vor dem ersten Installieren auf dem Pi muss der aktuelle Stand vom Laptop auf
GitHub hochgeladen werden.

Auf dem Laptop im Projektordner:

```bash
git status
git add .
git commit -m "Aktueller Stand fuer Raspberry Pi"
git push
```

Wenn `git status` sagt, dass es keine Aenderungen gibt, brauchst du keinen neuen
Commit.

Danach auf dem Raspberry Pi:

```bash
cd ~
git clone https://github.com/Struwwelpeter01/Parkhaus_RDF.git
cd Parkhaus_RDF
```

Wenn das Projekt schon auf dem Pi liegt und du spaeter neue Aenderungen von
GitHub holen willst:

```bash
cd Parkhaus_RDF
git pull
```

Der Laptop muss dafuer bei der Praesentation nicht dabei sein. GitHub wird nur
zum Uebertragen des Projekts auf den Pi benutzt.

Wichtig: Laufzeitdaten wie `data/parkhaus.db`, `data/manifest.csv`,
`data/whitelist.csv`, `data/raw/`, `.venv/` und `__pycache__/` gehoeren nicht in
Git. Sie bleiben lokal auf dem Pi, damit spaetere Updates mit `git pull` nicht
blockiert werden.

## 3. Python-Umgebung einrichten

Auf dem Pi:

```bash
cd ~/Parkhaus_RDF
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install Flask==2.3.3 Flask-SocketIO==5.3.6 python-socketio==5.8.0 easyocr==1.7.1 ultralytics
```

Wichtig: `--system-site-packages` ist hier absichtlich gesetzt, damit Python die per `apt` installierten Raspberry-Pi-Pakete wie `picamera2` und `cv2` findet.

## 4. Dashboard komplett auf dem Pi starten

```bash
cd ~/Parkhaus_RDF
source .venv/bin/activate
python run.py
```

`run.py` startet den Flask-Server auf dem Pi und oeffnet automatisch den lokalen
Browser auf:

```text
http://127.0.0.1:5000
```

Das ist genau richtig, wenn alles auf dem Raspberry Pi laufen soll. Der Browser
zeigt dann die Website direkt auf dem Bildschirm an, der am Pi angeschlossen ist.

Wenn die Kamera auf dem Pi noch ruckelt, kannst du die Erkennung weiter entlasten:

```bash
PARKHAUS_DETECTION_INTERVAL=0.5 PARKHAUS_YOLO_IMGSZ=416 python run.py
```

Wenn die Erkennung wichtiger ist als maximale Fluessigkeit:

```bash
PARKHAUS_DETECTION_INTERVAL=0.2 PARKHAUS_YOLO_IMGSZ=736 PARKHAUS_YOLO_CONF=0.25 python run.py
```

Wenn OCR bei schwierigen Winkeln wieder gruendlicher statt schneller arbeiten soll:

```bash
PARKHAUS_OCR_FAST_MODE=0 python run.py
```

Standardmaessig wird OCR sofort gestartet, sobald YOLO ein Kennzeichen findet. Wenn du doch wieder nur sehr ruhige Kennzeichen auslesen willst:

```bash
PARKHAUS_STABLE_SECONDS=0.5 python run.py
```

## 5. GPIO-Ausgaenge fuer die Schranken

Die Raspberry-Pi-Ausgaenge sind im Programm standardmaessig so eingestellt:

```text
GPIO17, physischer Pin 11 -> Signal Schranke Einfahrt oeffnen
GPIO27, physischer Pin 13 -> Signal Schranke Ausfahrt oeffnen
GND, z.B. physischer Pin 6 -> GND vom ESP32-C6
```

Verdrahtung zum ESP32-C6:

```text
Raspberry Pi GPIO17 -> ESP32-C6 GPIO2
Raspberry Pi GPIO27 -> ESP32-C6 GPIO3
Raspberry Pi GND    -> ESP32-C6 GND
```

Die Signale sind 3.3 V/HIGH-Impulse. Falls du andere Raspberry-Pins nutzen
willst, kannst du sie beim Start ueberschreiben:

```bash
PARKHAUS_GATE_ENTRY_GPIO=17 PARKHAUS_GATE_EXIT_GPIO=27 python run.py
```

## 6. Praesentationsmodus mit Vollbild-Browser

Wenn der Browser bei der Praesentation schoener im Vollbild laufen soll, kannst
du ihn nach dem Start des Programms mit `F11` in den Vollbildmodus schalten.

Alternativ kannst du Chromium im Kiosk-Modus starten:

```bash
chromium-browser --kiosk http://127.0.0.1:5000
```

Falls `run.py` den Browser schon selbst geoeffnet hat, kannst du fuer den
Kiosk-Modus den automatischen Browserstart abschalten:

```bash
PARKHAUS_OPEN_BROWSER=0 python run.py
```

Dann ein zweites Terminal oeffnen und dort starten:

```bash
chromium-browser --kiosk http://127.0.0.1:5000
```

## 7. Automatisch nach dem Einschalten starten

Wenn das Projekt beim Einschalten des Raspberry Pi automatisch starten soll,
kannst du im Autostart des Pi einen Befehl eintragen.

Autostart-Ordner anlegen:

```bash
mkdir -p ~/.config/autostart
```

Desktop-Datei erstellen:

```bash
nano ~/.config/autostart/parkhaus.desktop
```

Diesen Inhalt einfuegen:

```ini
[Desktop Entry]
Type=Application
Name=Parkhaus
Exec=lxterminal -e bash -lc "cd ~/Parkhaus_RDF && source .venv/bin/activate && python run.py"
Terminal=false
```

Speichern mit `CTRL+O`, Enter, dann beenden mit `CTRL+X`.

Nach einem Neustart startet der Pi das Parkhaus-Programm automatisch:

```bash
sudo reboot
```

## 8. Projekt spaeter updaten

Wenn du am Laptop etwas am Code geaendert hast, erst auf GitHub hochladen.

Auf dem Laptop im Projektordner:

```bash
git status
git add .
git commit -m "Update"
git push
```

Dann auf dem Raspberry Pi das laufende Programm beenden:

```bash
CTRL+C
```

Danach auf dem Pi:

```bash
cd ~/Parkhaus_RDF
git pull
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Normalerweise ist das alles. Die Datenbank und CSV-Dateien auf dem Pi bleiben
dabei erhalten, weil sie nicht mehr von Git verwaltet werden.

Falls `git pull` trotzdem meldet, dass lokale Aenderungen vorhanden sind:

```bash
cd ~/Parkhaus_RDF
git status
```

Wenn dort nur lokale Laufzeitdateien stehen, die nicht wichtig sind, kannst du
sie ignorieren oder sichern. Wenn dort echte Code-Dateien stehen, hast du auf
dem Pi Code geaendert. Dann gibt es zwei sinnvolle Wege:

Weg A, Pi-Aenderungen verwerfen und Laptop/GitHub als Hauptstand benutzen:

```bash
git restore <DATEINAME>
git pull
```

Beispiel:

```bash
git restore run.py
git pull
```

Weg B, Pi-Aenderungen behalten und nach GitHub hochladen:

```bash
git add .
git commit -m "Aenderungen vom Raspberry Pi"
git push
```

Danach kannst du am Laptop wieder `git pull` machen.

Empfehlung fuer euer Projekt: Code nur am Laptop bearbeiten und auf dem Pi nur
`git pull` machen. Der Pi ist dann das Geraet zum Ausfuehren und Praesentieren.

### Einmalig, wenn der Pi wegen `data/parkhaus.db` nicht pullen will

Falls der Pi beim ersten Update meldet, dass `data/parkhaus.db` geaendert wurde
und deshalb kein `git pull` moeglich ist, sichere die Datenbank einmal kurz:

```bash
cd ~/Parkhaus_RDF
cp data/parkhaus.db data/parkhaus.db.backup
git restore data/parkhaus.db
git pull
mv data/parkhaus.db.backup data/parkhaus.db
```

Danach ist `data/parkhaus.db` lokal auf dem Pi und wird von Git ignoriert. Ab
dann sollte ein normales `git pull` funktionieren.

## 8. Kamera und KI-Modell

Das Programm verwendet auf dem Pi automatisch `picamera2`. Wenn das nicht klappt, versucht es als Fallback eine normale USB-/OpenCV-Kamera mit Kameraindex `0`.

Das trainierte YOLO-Modell wird aus diesem Projekt geladen, zum Beispiel aus:

```text
runs/detect/license_plate_detection-3/weights/best.pt
```

Deshalb sollte der Ordner `runs` mit auf den Pi kopiert werden.

## 9. Haefige Probleme

Wenn der Browser nicht automatisch aufgeht:

```bash
cd ~/Parkhaus_RDF
source .venv/bin/activate
python run.py
```

Dann auf dem Pi im Browser manuell oeffnen:

```text
http://127.0.0.1:5000
```

Wenn `picamera2` nicht gefunden wird:

```bash
sudo apt install -y python3-picamera2
python3 -m venv --system-site-packages .venv
```

Wenn `cv2` nicht gefunden wird:

```bash
sudo apt install -y python3-opencv
```

Wenn EasyOCR oder Ultralytics sehr langsam sind: Das ist auf dem Raspberry Pi normal. Fuer den Live-Betrieb kann spaeter ein kleineres Modell oder weniger OCR-Aufrufe sinnvoll sein.
