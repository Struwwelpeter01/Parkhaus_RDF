#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Parkhaus Management System - Starter Script
Startet die Flask-App.
"""

import os
import sys
import time
import webbrowser


# src-Verzeichnis zum Python-Path hinzufuegen
src_path = os.path.join(os.path.dirname(__file__), "src")
sys.path.insert(0, src_path)

# Flask-App importieren
from app import app
from app import camera_recognizer, exit_camera_recognizer


host = os.getenv("PARKHAUS_HOST", "0.0.0.0")
port = int(os.getenv("PARKHAUS_PORT", "5000"))
local_url = f"http://127.0.0.1:{port}"
network_url = f"http://<IP-DES-RASPBERRY-PI>:{port}"
open_browser_enabled = os.getenv("PARKHAUS_OPEN_BROWSER", "1") == "1"

print("Parkhaus Management System wird gestartet...\n")
print("=" * 50)
print(f"Dashboard lokal:       {local_url}")
print(f"Dashboard im Netzwerk: {network_url}")
print("=" * 50)
print("\nWarten auf Serverstart (1-2 Sekunden)...\n")


def open_browser() -> None:
    time.sleep(2)
    webbrowser.open(local_url)
    print("Browser sollte sich automatisch oeffnen!\n")
    print(f"Falls nicht, oeffne manuell: {local_url}\n")
    print("=" * 50)
    print("Zum Beenden: CTRL+C druecken")
    print("=" * 50)


if open_browser_enabled:
    import threading

    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()


try:
    camera_recognizer.start()
    if exit_camera_recognizer is not camera_recognizer:
        exit_camera_recognizer.start()
    app.run(host=host, port=port, debug=True, use_reloader=False)
except KeyboardInterrupt:
    print("\n\nServer wurde beendet.")
    sys.exit(0)
