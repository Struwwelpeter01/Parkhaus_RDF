#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Parkhaus Management System - Starter Script
Startet die Flask-App und öffnet automatisch den Browser
"""

import webbrowser
import time
import os
import sys

# src-Verzeichnis zum Python-Path hinzufügen
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

# Flask-App importieren
from app import app

print("🚗 Parkhaus Management System wird gestartet...\n")
print("=" * 50)
print("Dashboard wird unter http://127.0.0.1:5000 bereitgestellt")
print("=" * 50)
print("\n⏳ Warten auf Serverstart (1-2 Sekunden)...\n")

# Browser nach kurzer Verzögerung öffnen
def open_browser():
    time.sleep(2)  # Warten, bis Flask startet
    webbrowser.open('http://127.0.0.1:5000')
    print("✅ Browser sollte sich automatisch öffnen!\n")
    print("Falls nicht, öffne manuell: http://127.0.0.1:5000\n")
    print("=" * 50)
    print("Zum Beenden: CTRL+C drücken")
    print("=" * 50)

# Browser in separatem Thread starten (damit Flask nicht blockiert wird)
import threading
browser_thread = threading.Thread(target=open_browser, daemon=True)
browser_thread.start()

# Flask-App starten
try:
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
except KeyboardInterrupt:
    print("\n\n🛑 Server wurde beendet.")
    sys.exit(0)

#test
#test2
