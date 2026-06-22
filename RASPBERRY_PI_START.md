# Parkhaus-Projekt auf Raspberry Pi 5 starten

Diese Anleitung geht davon aus, dass auf dem Raspberry Pi Raspberry Pi OS installiert ist und der Pi im gleichen WLAN/LAN wie dein PC ist.

## 1. Raspberry Pi vorbereiten

Auf dem Pi ein Terminal oeffnen oder per SSH verbinden:

```bash
ssh pi@raspberrypi.local
```

System aktualisieren und Grundpakete installieren:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-opencv python3-picamera2 python3-gpiozero
```

Falls du die offizielle Raspberry-Pi-Kamera nutzt, pruefen ob sie erkannt wird:

```bash
rpicam-hello --timeout 3000
```

## 2. Projekt auf den Pi kopieren

### Variante A: Mit Git

Wenn dein Projekt in einem Git-Repository liegt:

```bash
cd ~
git clone <DEIN-REPOSITORY-LINK> Parkhaus_RDF
cd Parkhaus_RDF
```

### Variante B: Direkt vom Windows-PC kopieren

Auf deinem Windows-PC im Projektordner ausfuehren:

```powershell
scp -r . pi@raspberrypi.local:~/Parkhaus_RDF
```

Wenn der Pi nicht unter `raspberrypi.local` erreichbar ist, nimm seine IP-Adresse:

```powershell
scp -r . pi@192.168.178.50:~/Parkhaus_RDF
```

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

## 4. Dashboard starten

```bash
cd ~/Parkhaus_RDF
source .venv/bin/activate
python run.py
```

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

Die IP-Adresse des Pi findest du mit:

```bash
hostname -I
```

Dann im Browser auf deinem PC oeffnen:

```text
http://<IP-DES-RASPBERRY-PI>:5000
```

Beispiel:

```text
http://192.168.178.50:5000
```

## 5. Kamera und KI-Modell

Das Programm verwendet auf dem Pi automatisch `picamera2`. Wenn das nicht klappt, versucht es als Fallback eine normale USB-/OpenCV-Kamera mit Kameraindex `0`.

Das trainierte YOLO-Modell wird aus diesem Projekt geladen, zum Beispiel aus:

```text
runs/detect/license_plate_detection-3/weights/best.pt
```

Deshalb sollte der Ordner `runs` mit auf den Pi kopiert werden.

## 6. Haefige Probleme

Wenn das Dashboard auf dem Pi laeuft, aber am PC nicht erreichbar ist:

```bash
hostname -I
python run.py
```

Dann im PC-Browser wirklich `http://PI-IP:5000` verwenden, nicht `127.0.0.1`.

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
