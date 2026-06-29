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

Am einfachsten ueber GitHub:

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

## 5. Praesentationsmodus mit Vollbild-Browser

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

## 6. Automatisch nach dem Einschalten starten

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

## 7. Kamera und KI-Modell

Das Programm verwendet auf dem Pi automatisch `picamera2`. Wenn das nicht klappt, versucht es als Fallback eine normale USB-/OpenCV-Kamera mit Kameraindex `0`.

Das trainierte YOLO-Modell wird aus diesem Projekt geladen, zum Beispiel aus:

```text
runs/detect/license_plate_detection-3/weights/best.pt
```

Deshalb sollte der Ordner `runs` mit auf den Pi kopiert werden.

## 8. Haefige Probleme

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
