from __future__ import annotations

import re
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from camera_source import CameraSource


PLATE_REGEX = re.compile(r"^[A-Z]-[0-9]{4}$")


@dataclass
class CameraState:
    plate: str = ""
    ocr_raw: str = ""
    status: str = "Kamera nicht gestartet"
    active: bool = False
    updated_at: float = 0.0


class CameraPlateRecognizer:
    def __init__(self, source: int = 0, width: int = 960, height: int = 540) -> None:
        self.source = source
        self.width = width
        self.height = height
        self._state = CameraState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._templates: dict[str, list[Any]] = {}
        self._latest_jpeg: bytes = b""
        self._yolo_model = None
        self._ocr_reader = None
        self._use_yolo = False
        self._last_ocr_raw = ""
        self._ocr_thread: threading.Thread | None = None
        self._ocr_running = False
        self._ocr_lock = threading.Lock()
        self._detection_thread: threading.Thread | None = None
        self._detection_event = threading.Event()
        self._detection_lock = threading.Lock()
        self._detection_frame: Any = None
        self._camera_kind = ""
        self._stable_box: tuple[float, float, float, float] | None = None
        self._stable_since = 0.0
        self._last_ocr_attempt_at = 0.0
        self._stable_seconds_required = self._read_float_env("PARKHAUS_STABLE_SECONDS", 0.0)
        self._ocr_retry_seconds = self._read_float_env("PARKHAUS_OCR_RETRY_SECONDS", 0.8)
        self._plate_hold_seconds = self._read_float_env("PARKHAUS_PLATE_HOLD_SECONDS", 2.5)
        self._ocr_votes: deque[tuple[str, float]] = deque(maxlen=6)
        self._ocr_min_votes = int(os.getenv("PARKHAUS_OCR_MIN_VOTES", "2"))
        self._ocr_min_score = self._read_float_env("PARKHAUS_OCR_MIN_SCORE", 2.0)
        self._ocr_char_min_score = self._read_float_env("PARKHAUS_OCR_CHAR_MIN_SCORE", 1.6)
        self._last_detected = ""
        self._last_valid_plate = ""
        self._last_plate_seen_at = 0.0
        self._last_detection_at = 0.0
        self._detection_interval = self._read_float_env("PARKHAUS_DETECTION_INTERVAL", 0.18)
        self._yolo_conf = self._read_float_env("PARKHAUS_YOLO_CONF", 0.35)
        self._yolo_imgsz = int(os.getenv("PARKHAUS_YOLO_IMGSZ", "640"))
        self._jpeg_quality = int(os.getenv("PARKHAUS_JPEG_QUALITY", "65"))
        self._ocr_canvas_size = int(os.getenv("PARKHAUS_OCR_CANVAS_SIZE", "768"))
        self._ocr_scale_width = int(os.getenv("PARKHAUS_OCR_SCALE_WIDTH", "360"))
        self._ocr_fast_mode = os.getenv("PARKHAUS_OCR_FAST_MODE", "1") == "1"
        self._ocr_early_score = self._read_float_env("PARKHAUS_OCR_EARLY_SCORE", 1.05)
        self._stable_plate = ""
        self._stable_hits = 0
        
        # Versuche YOLO11-Modell zu laden
        self._load_yolo_model()
        
        # Versuche EasyOCR zu laden
        self._load_ocr_reader()

    def _load_yolo_model(self) -> None:
        """Versucht das trainierte YOLO11-Modell zu laden"""
        try:
            from ultralytics import YOLO
            
            # Pfad zum trainierten Modell
            project_root = Path(__file__).parent.parent
            model_path = project_root / "runs" / "detect" / "license_plate_detection" / "weights" / "best.pt"
            
            # Alternatives Verzeichnis wenn obiges nicht existiert
            if not model_path.exists():
                # Suche nach dem Verzeichnis (könnte auch -3, -4 etc. sein)
                detect_dir = project_root / "runs" / "detect"
                if detect_dir.exists():
                    for sub_dir in sorted(detect_dir.iterdir(), reverse=True):
                        alt_model = sub_dir / "weights" / "best.pt"
                        if alt_model.exists():
                            model_path = alt_model
                            break
            
            if model_path.exists():
                print(f"📦 Lade YOLO11-Modell: {model_path}")
                self._yolo_model = YOLO(str(model_path))
                self._use_yolo = True
                print("✅ YOLO11-Modell erfolgreich geladen!")
            else:
                print(f"⚠️  YOLO11-Modell nicht gefunden: {model_path}")
                self._use_yolo = False
                
        except ImportError:
            print("⚠️  ultralytics nicht installiert - verwende Template Matching")
            self._use_yolo = False
        except Exception as e:
            print(f"⚠️  Fehler beim Laden von YOLO11: {e}")
            self._use_yolo = False

    def _load_ocr_reader(self) -> None:
        """Versucht EasyOCR für Kennzeichen-Lesefunktion zu laden"""
        try:
            import easyocr
            
            print("📦 Lade EasyOCR Reader für Kennzeichenerkennung...")
            # Lade Reader für Deutsch und Englisch (für deutsche/englische Kennzeichen)
            self._ocr_reader = easyocr.Reader(['de', 'en'], gpu=False)
            print("✅ EasyOCR Reader erfolgreich geladen!")
            
        except ImportError:
            print("⚠️  easyocr nicht installiert - Kennzeichen-Text wird nicht gelesen")
            self._ocr_reader = None
        except Exception as e:
            print(f"⚠️  Fehler beim Laden von EasyOCR: {e}")
            self._ocr_reader = None

    def _read_float_env(self, name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)).replace(",", "."))
        except ValueError:
            return default

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "plate": self._state.plate,
                "ocr_raw": self._state.ocr_raw,
                "status": self._state.status,
                "active": self._state.active,
                "updated_at": self._state.updated_at,
            }

    def get_jpeg(self) -> bytes:
        with self._lock:
            return self._latest_jpeg

    def _set_state(
        self,
        *,
        plate: str | None = None,
        ocr_raw: str | None = None,
        status: str | None = None,
        active: bool | None = None,
    ) -> None:
        with self._lock:
            if plate is not None:
                self._state.plate = plate
            if ocr_raw is not None:
                self._state.ocr_raw = ocr_raw
            if status is not None:
                self._state.status = status
            if active is not None:
                self._state.active = active
            self._state.updated_at = time.time()

    def _set_jpeg(self, jpeg: bytes) -> None:
        with self._lock:
            self._latest_jpeg = jpeg

    def _run(self) -> None:
        try:
            import cv2
        except ImportError:
            self._set_state(status="OpenCV ist nicht installiert", active=False)
            return

        self._templates = self._build_templates(cv2)
        try:
            camera = CameraSource(self.width, self.height, self.source).__enter__()
        except RuntimeError as error:
            self._set_state(status=str(error), active=False)
            return

        self._camera_kind = camera.kind
        self._set_state(status=f"Kamera aktiv ({camera.kind})", active=True)
        self._detection_thread = threading.Thread(
            target=self._run_detection_worker,
            args=(cv2,),
            daemon=True,
        )
        self._detection_thread.start()
        stable_plate = ""
        stable_hits = 0

        try:
            while not self._stop_event.is_set():
                try:
                    frame = camera.read()
                except RuntimeError:
                    self._set_state(status="Kamerabild konnte nicht gelesen werden", active=False)
                    time.sleep(0.5)
                    continue

                now = time.time()
                if now - self._last_detection_at >= self._detection_interval:
                    self._queue_detection_frame(frame)
                    self._last_detection_at = now
                detected = self._last_detected
                self._update_preview(frame, detected, cv2)
                
                # Unterschiedliche Logik für YOLO vs. Template Matching
                if self._use_yolo and self._yolo_model:
                    if detected == "WARTET":
                        self._set_state(
                            plate="",
                            ocr_raw="",
                            status="Kennzeichen erkannt, warte auf Stillstand",
                            active=True,
                        )
                    elif detected and detected != "ERKANNT":
                        self._set_state(
                            plate=detected,
                            ocr_raw=self._last_ocr_raw,
                            status=f"Kennzeichen erkannt: {detected}",
                            active=True,
                        )
                    elif detected == "ERKANNT":
                        if self._ocr_reader is None:
                            status = "Kennzeichen erkannt, aber EasyOCR ist nicht geladen"
                        elif self._ocr_running:
                            status = "Kennzeichen erkannt, OCR liest..."
                        elif self._last_ocr_raw:
                            status = f"Kennzeichen erkannt, OCR-Rohtext: {self._last_ocr_raw}"
                        else:
                            status = "Kennzeichen erkannt, OCR konnte den Text nicht lesen"

                        self._set_state(ocr_raw=self._last_ocr_raw, status=status, active=True)
                    else:
                        if self._last_valid_plate and time.time() - self._last_plate_seen_at < self._plate_hold_seconds:
                            self._set_state(
                                plate=self._last_valid_plate,
                                ocr_raw=self._last_ocr_raw,
                                status=f"Kennzeichen erkannt: {self._last_valid_plate}",
                                active=True,
                            )
                        else:
                            self._set_state(plate="", status="Kennzeichen nicht erkannt", active=True)

                    time.sleep(0.02)
                    continue

                    # YOLO11-Modus mit OCR
                    if detected and detected != "ERKANNT":
                        # OCR hat ein Kennzeichen gelesen
                        self._set_state(plate=detected, status=f"✅ Kennzeichen erkannt: {detected}", active=True)
                    elif detected == "ERKANNT":
                        # YOLO hat erkannt, aber OCR konnte nicht lesen
                        self._set_state(status="✅ Kennzeichen erkannt (OCR lädt...)", active=True)
                    else:
                        # Nichts erkannt
                        self._set_state(status="❌ Kennzeichen nicht erkannt", active=True)
                else:
                    # Template Matching Modus: Mit Stabilisierung
                    if detected and detected == stable_plate:
                        stable_hits += 1
                    elif detected:
                        stable_plate = detected
                        stable_hits = 1
                    else:
                        stable_hits = 0

                    if detected and stable_hits >= 2:
                        self._set_state(plate=detected, status="Kennzeichen erkannt", active=True)
                    else:
                        self._set_state(status=f"Kamera aktiv ({camera.kind})", active=True)

                time.sleep(0.02)
        finally:
            self._detection_event.set()
            camera.close()
            self._set_state(status="Kamera beendet", active=False)

    def _queue_detection_frame(self, frame: Any) -> None:
        with self._detection_lock:
            self._detection_frame = frame.copy()
        self._detection_event.set()

    def _run_detection_worker(self, cv2: Any) -> None:
        while not self._stop_event.is_set():
            self._detection_event.wait(0.2)
            self._detection_event.clear()

            with self._detection_lock:
                frame = self._detection_frame
                self._detection_frame = None

            if frame is None:
                continue

            self._last_detected = self._detect_plate(frame, cv2)

    def _update_preview(self, frame: Any, detected: str, cv2: Any) -> None:
        preview = frame.copy()
        height, width = preview.shape[:2]

        # Angepasste Label-Anzeige für YOLO vs. Template Matching
        if self._use_yolo and self._yolo_model:
            # YOLO11 + OCR Modus
            if detected == "WARTET":
                label = "Kennzeichen erkannt - bitte kurz stillhalten"
            elif detected and detected != "ERKANNT":
                # OCR hat erfolgreich gelesen
                label = f"🎯 Erkannt: {detected}"
            elif detected == "ERKANNT":
                # Nur YOLO erkannt, OCR lädt noch
                label = "🎯 Kennzeichen erkannt (OCR lädt...)"
            else:
                # Nichts erkannt
                label = "Kennzeichen in den Bereich halten"
        else:
            # Template Matching Modus
            label = f"Erkannt: {detected}" if detected else "Kennzeichen in den blauen Rahmen halten"
        
        cv2.rectangle(preview, (0, 0), (width, 42), (44, 62, 80), -1)
        cv2.putText(preview, label, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

        ok, encoded = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality])
        if ok:
            self._set_jpeg(encoded.tobytes())

    def _detect_plate(self, frame: Any, cv2: Any) -> str:
        """Erkennt Kennzeichen entweder mit YOLO11 oder Template Matching"""
        
        # Verwende YOLO11 falls verfügbar
        if self._use_yolo and self._yolo_model:
            return self._detect_plate_yolo(frame, cv2)
        
        # Fallback auf Template Matching
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        candidates = self._candidate_regions(gray, cv2)

        for candidate in candidates:
            plate = self._read_candidate(candidate, cv2)
            if PLATE_REGEX.match(plate):
                return plate

        return ""
    
    def _detect_plate_yolo(self, frame: Any, cv2: Any) -> str:
        """
        Verwendet YOLO11 zur Kennzeichen-Erkennung und EasyOCR zum Auslesen.
        Gibt das erkannte Kennzeichen zurück oder leeres String wenn nicht erkannt.
        """
        try:
            # YOLO-Inferenz durchführen
            results = self._yolo_model.predict(
                source=frame,
                conf=self._yolo_conf,
                imgsz=self._yolo_imgsz,
                verbose=False,
                device='cpu'
            )
            
            # Prüfe ob Detektionen gefunden wurden
            if results and len(results) > 0:
                result = results[0]
                if result.boxes is not None and len(result.boxes) > 0:
                    # Mindestens ein Kennzeichen erkannt
                    # Nimm die erste Box (höchster Confidence Score)
                    box = max(result.boxes, key=lambda current_box: float(current_box.conf[0]))
                    
                    # Extrahiere die Bounding Box Koordinaten
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    stable_seconds = self._update_box_stability((x1, y1, x2, y2), frame.shape)
                    
                    # Füge kleine Margen hinzu für bessere OCR-Ergebnisse
                    margin = 8
                    x1 = max(0, x1 - margin)
                    y1 = max(0, y1 - margin)
                    x2 = min(frame.shape[1], x2 + margin)
                    y2 = min(frame.shape[0], y2 + margin)
                    
                    # Extrahiere den Kennzeichen-Bereich
                    plate_roi = frame[y1:y2, x1:x2]

                    if stable_seconds < self._stable_seconds_required:
                        return "WARTET"

                    now = time.time()
                    if now - self._last_ocr_attempt_at < self._ocr_retry_seconds:
                        return "ERKANNT"

                    self._last_ocr_attempt_at = now
                    
                    # Versuche OCR zu lesen falls verfügbar
                    if self._ocr_reader and plate_roi.size > 0:
                        self._start_ocr_worker(plate_roi.copy(), cv2)
                    
                    # Fallback: Nur "ERKANNT" wenn OCR nicht funktioniert
                    return "ERKANNT"
            
            # Kein Kennzeichen erkannt
            self._reset_box_stability()
            return ""
            
        except Exception as e:
            print(f"⚠️  YOLO11-Fehler: {e}")
            return ""
    
    def _update_box_stability(self, box: tuple[int, int, int, int], frame_shape: Any) -> float:
        height, width = frame_shape[:2]
        x1, y1, x2, y2 = box
        normalized = (
            x1 / max(width, 1),
            y1 / max(height, 1),
            x2 / max(width, 1),
            y2 / max(height, 1),
        )

        now = time.time()
        if self._stable_box is None:
            self._stable_box = normalized
            self._stable_since = now
            return 0.0

        max_delta = max(abs(current - previous) for current, previous in zip(normalized, self._stable_box))
        if max_delta > 0.035:
            self._stable_box = normalized
            self._stable_since = now
            self._last_ocr_attempt_at = 0.0
            self._ocr_votes.clear()
            return 0.0

        self._stable_box = normalized
        return now - self._stable_since

    def _reset_box_stability(self) -> None:
        self._stable_box = None
        self._stable_since = 0.0
        self._last_ocr_attempt_at = 0.0
        self._ocr_votes.clear()

    def _remember_ocr_vote(self, plate: str, score: float) -> str:
        self._ocr_votes.append((plate, score))

        counts = Counter(plate for plate, _ in self._ocr_votes)
        scores: dict[str, float] = {}
        for current_plate, current_score in self._ocr_votes:
            scores[current_plate] = scores.get(current_plate, 0.0) + current_score

        winner = max(scores, key=lambda candidate: (scores[candidate], counts[candidate]))
        if counts[winner] >= self._ocr_min_votes and scores[winner] >= self._ocr_min_score:
            return winner

        character_vote = self._plate_from_character_votes()
        if character_vote:
            return character_vote

        return ""

    def _plate_from_character_votes(self) -> str:
        if len(self._ocr_votes) < self._ocr_min_votes:
            return ""

        positions: list[dict[str, float]] = [{} for _ in range(5)]
        counts: list[Counter[str]] = [Counter() for _ in range(5)]
        for plate, score in self._ocr_votes:
            compact = plate.replace("-", "")
            if len(compact) != 5:
                continue
            for index, char in enumerate(compact):
                positions[index][char] = positions[index].get(char, 0.0) + score
                counts[index][char] += 1

        chars = []
        for index, scores in enumerate(positions):
            if not scores:
                return ""
            winner = max(scores, key=lambda char: (scores[char], counts[index][char]))
            allowed = winner.isalpha() if index == 0 else winner.isdigit()
            if not allowed:
                return ""
            if counts[index][winner] < self._ocr_min_votes and scores[winner] < self._ocr_char_min_score:
                return ""
            chars.append(winner)

        plate = f"{chars[0]}-{''.join(chars[1:])}"
        return plate if PLATE_REGEX.match(plate) else ""

    def _start_ocr_worker(self, plate_roi: Any, cv2: Any) -> None:
        with self._ocr_lock:
            if self._ocr_running:
                return

            self._ocr_running = True

        self._ocr_thread = threading.Thread(
            target=self._run_ocr_worker,
            args=(plate_roi, cv2),
            daemon=True,
        )
        self._ocr_thread.start()

    def _run_ocr_worker(self, plate_roi: Any, cv2: Any) -> None:
        try:
            plate_text, plate_score = self._read_plate_ocr(plate_roi, cv2)
            if not plate_text:
                if self._last_ocr_raw:
                    self._set_state(
                        ocr_raw=self._last_ocr_raw,
                        status=f"Kennzeichen wird geprueft, OCR-Rohtext: {self._last_ocr_raw}",
                        active=True,
                    )
                return

            detected_plate = self._remember_ocr_vote(plate_text, plate_score)
            if not detected_plate:
                self._set_state(
                    plate="",
                    ocr_raw=self._last_ocr_raw,
                    status=f"Kennzeichen wird stabilisiert: {plate_text}",
                    active=True,
                )
                return

            self._last_valid_plate = detected_plate
            self._last_plate_seen_at = time.time()
            self._set_state(
                plate=detected_plate,
                ocr_raw=self._last_ocr_raw,
                status=f"Kennzeichen erkannt: {detected_plate}",
                active=True,
            )
        finally:
            with self._ocr_lock:
                self._ocr_running = False

    def _read_plate_ocr(self, plate_image: Any, cv2: Any) -> tuple[str, float]:
        """
        Liest den Kennzeichen-Text mittels OCR.
        Gibt das formatierte Kennzeichen zurück (z.B. A-1234) oder leer wenn nicht lesbar.
        """
        try:
            if self._ocr_reader is None:
                return "", 0.0

            plate_scores: dict[str, float] = {}
            raw_texts: list[str] = []

            for prepared in self._prepare_plate_for_ocr(plate_image, cv2):
                results = self._ocr_reader.readtext(
                    prepared,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ",
                    detail=1,
                    paragraph=False,
                    text_threshold=0.3,
                    low_text=0.2,
                    width_ths=0.7,
                    canvas_size=self._ocr_canvas_size,
                    mag_ratio=1.0,
                )

                for raw_text, confidence in self._ocr_candidates(results):
                    if raw_text.strip():
                        raw_texts.append(raw_text.strip())
                    for plate, weight in self._plate_candidate_variants_from_text(raw_text):
                        exact_bonus = 0.25 if len(re.sub(r"[^A-Z0-9]", "", raw_text.upper())) == 5 else 0.0
                        plate_scores[plate] = plate_scores.get(plate, 0.0) + (confidence + exact_bonus) * weight

                if plate_scores and max(plate_scores.values()) >= self._ocr_early_score:
                    break

            template_plate = self._read_plate_by_templates(plate_image, cv2)
            if template_plate:
                plate_scores[template_plate] = plate_scores.get(template_plate, 0.0) + 1.4

            unique_raw_texts = list(dict.fromkeys(raw_texts))
            self._last_ocr_raw = " | ".join(unique_raw_texts[:3])

            if plate_scores:
                return max(plate_scores.items(), key=lambda item: item[1])

            return "", 0.0
            
            # OCR durchführen
            
            
            # Kombiniere alle erkannten Texte
            
            # Bereinige den Text: nur Großbuchstaben und Zahlen, entferne Leerzeichen
            
            # Validiere deutsches Kennzeichen-Format: 1-2 Buchstaben, 4 Zahlen
            # Beispiel: AB1234 oder A1234
            
            # Versuche Muster zu finden: [1-2 Buchstaben][4 Zahlen]
            
            # Wenn Regex nicht passt, prüfe ob wir zumindest gültige Zeichen haben
            
        except Exception as e:
            print(f"⚠️  OCR-Fehler: {e}")
            return "", 0.0

    def _prepare_plate_for_ocr(self, plate_image: Any, cv2: Any) -> list[Any]:
        """Erzeugt mehrere OCR-Varianten des Kennzeichen-Crops."""
        if plate_image.size == 0:
            return []

        import numpy as np

        plate_image = cv2.copyMakeBorder(
            plate_image,
            10,
            10,
            18,
            18,
            cv2.BORDER_REPLICATE,
        )
        height, width = plate_image.shape[:2]
        scale = max(2.2, self._ocr_scale_width / max(width, 1))
        resized = cv2.resize(
            plate_image,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 7, 45, 45)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)
        sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(contrast, -1, sharpen_kernel)
        _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary = cv2.adaptiveThreshold(
            sharpened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            8,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        otsu = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel)
        inverted = cv2.bitwise_not(binary)
        inverted_otsu = cv2.bitwise_not(otsu)

        if self._ocr_fast_mode:
            return [resized, contrast, sharpened, otsu, binary]

        return [resized, gray, contrast, sharpened, otsu, binary, inverted, inverted_otsu]

    def _ocr_candidates(self, results: list[Any]) -> list[tuple[str, float]]:
        if not results:
            return []

        candidates: list[tuple[str, float]] = []
        parts = []
        confidences = []

        for result in results:
            if len(result) < 3:
                continue

            box, text, confidence = result[0], str(result[1]), float(result[2])
            x_position = min(point[0] for point in box) if box else 0
            parts.append((x_position, text))
            confidences.append(confidence)
            candidates.append((text, confidence))

        if parts:
            combined = "".join(text for _, text in sorted(parts, key=lambda item: item[0]))
            average_confidence = sum(confidences) / max(len(confidences), 1)
            candidates.append((combined, average_confidence))

        return candidates

    def _normalize_plate_text(self, text: str) -> str:
        candidates = self._plate_candidates_from_text(text)
        return candidates[0] if candidates else ""

    def _plate_candidates_from_text(self, text: str) -> list[str]:
        return [plate for plate, _ in self._plate_candidate_variants_from_text(text)]

    def _plate_candidate_variants_from_text(self, text: str) -> list[tuple[str, float]]:
        cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
        if len(cleaned) < 5:
            return []

        letter_map = str.maketrans({"0": "O", "1": "I", "2": "Z", "4": "A", "5": "S", "6": "G", "7": "T", "8": "B"})
        number_map = str.maketrans({"A": "4", "B": "8", "D": "0", "G": "6", "I": "1", "L": "1", "O": "0", "Q": "0", "S": "5", "T": "7", "Z": "2"})

        possible_parts: list[tuple[str, str]] = []
        for index in range(0, len(cleaned) - 4):
            compact = cleaned[index:index + 5]
            possible_parts.append((compact[:1], compact[1:]))

        candidates: list[tuple[str, float]] = []
        for letters, numbers in possible_parts:
            normalized_letters = letters.translate(letter_map)
            normalized_numbers = numbers.translate(number_map)
            plate = f"{normalized_letters}-{normalized_numbers}"
            if PLATE_REGEX.match(plate):
                candidates.append((plate, 1.0))
                candidates.extend(self._common_confusion_variants(plate))

        unique: dict[str, float] = {}
        for plate, weight in candidates:
            unique[plate] = max(unique.get(plate, 0.0), weight)

        return list(unique.items())

    def _common_confusion_variants(self, plate: str) -> list[tuple[str, float]]:
        letter, numbers = plate.split("-", 1)
        variants: dict[str, float] = {}

        number_options = [(char,) for char in numbers]
        for index, char in enumerate(numbers):
            if char == "0":
                number_options[index] = ("0", "6")
            elif char == "6":
                number_options[index] = ("6", "0")

        for first in number_options[0]:
            for second in number_options[1]:
                for third in number_options[2]:
                    for fourth in number_options[3]:
                        variant_numbers = f"{first}{second}{third}{fourth}"
                        if variant_numbers != numbers:
                            variants[f"{letter}-{variant_numbers}"] = 0.72

        return list(variants.items())

    def _read_plate_by_templates(self, plate_image: Any, cv2: Any) -> str:
        if plate_image.size == 0:
            return ""

        try:
            if len(plate_image.shape) == 3:
                gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = plate_image.copy()

            gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            height, width = binary.shape[:2]
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            boxes = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if h < height * 0.25 or h > height * 0.95:
                    continue
                if w < width * 0.025 or w > width * 0.28:
                    continue
                if w * h < 120:
                    continue
                boxes.append((x, y, w, h))

            boxes.sort(key=lambda box: box[0])
            boxes = self._merge_boxes(boxes)
            if len(boxes) < 5:
                return ""

            best_boxes = sorted(boxes, key=lambda box: box[2] * box[3], reverse=True)[:5]
            best_boxes.sort(key=lambda box: box[0])

            chars = []
            for index, (x, y, w, h) in enumerate(best_boxes):
                pad = 4
                char_img = binary[
                    max(0, y - pad):min(height, y + h + pad),
                    max(0, x - pad):min(width, x + w + pad),
                ]
                allowed_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if index == 0 else "0123456789"
                chars.append(self._classify_char(char_img, cv2, allowed_chars))

            if len(chars) != 5 or not chars[0].isalpha() or not all(char.isdigit() for char in chars[1:]):
                return ""

            plate = f"{chars[0]}-{''.join(chars[1:])}"
            return plate if PLATE_REGEX.match(plate) else ""
        except Exception:
            return ""

    def _candidate_regions(self, gray: Any, cv2: Any) -> list[Any]:
        height, width = gray.shape[:2]
        scaled = gray
        if width > 900:
            factor = 900 / width
            scaled = cv2.resize(gray, (900, int(height * factor)))

        edges = cv2.Canny(scaled, 60, 180)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            aspect = w / max(h, 1)
            if 2.2 <= aspect <= 7.0 and area > 2500:
                margin_x = int(w * 0.08)
                margin_y = int(h * 0.25)
                sx = max(0, x - margin_x)
                sy = max(0, y - margin_y)
                ex = min(scaled.shape[1], x + w + margin_x)
                ey = min(scaled.shape[0], y + h + margin_y)
                regions.append((area, scaled[sy:ey, sx:ex]))

        regions.sort(key=lambda item: item[0], reverse=True)
        if not regions:
            center = scaled[
                int(scaled.shape[0] * 0.25):int(scaled.shape[0] * 0.75),
                int(scaled.shape[1] * 0.15):int(scaled.shape[1] * 0.85),
            ]
            return [center]

        return [region for _, region in regions[:5]]

    def _read_candidate(self, image: Any, cv2: Any) -> str:
        if image.size == 0:
            return ""

        image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        binary = cv2.adaptiveThreshold(
            image,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            12,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h < image.shape[0] * 0.18 or h > image.shape[0] * 0.9:
                continue
            if w < 4 or w > image.shape[1] * 0.25:
                continue
            if w * h < 80:
                continue
            boxes.append((x, y, w, h))

        if len(boxes) < 5:
            return ""

        boxes.sort(key=lambda box: box[0])
        boxes = self._merge_boxes(boxes)
        if len(boxes) < 5:
            return ""

        chars = []
        for box in boxes[:7]:
            x, y, w, h = box
            pad = 3
            char_img = binary[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
            chars.append(self._classify_char(char_img, cv2))

        plate = "".join(chars)
        if len(plate) >= 5 and "-" not in plate:
            plate = f"{plate[:1]}-{plate[1:]}"
        return plate[:6]

    def _merge_boxes(self, boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        merged: list[tuple[int, int, int, int]] = []
        for box in boxes:
            x, y, w, h = box
            if merged and x < merged[-1][0] + merged[-1][2] + 3:
                px, py, pw, ph = merged[-1]
                nx = min(px, x)
                ny = min(py, y)
                nr = max(px + pw, x + w)
                nb = max(py + ph, y + h)
                merged[-1] = (nx, ny, nr - nx, nb - ny)
            else:
                merged.append(box)
        return merged

    def _classify_char(self, char_img: Any, cv2: Any, allowed_chars: str | None = None) -> str:
        normalized = cv2.resize(char_img, (24, 36), interpolation=cv2.INTER_AREA)
        best_char = ""
        best_score = -1.0

        for char, templates in self._templates.items():
            if allowed_chars is not None and char not in allowed_chars:
                continue
            for template in templates:
                score = cv2.matchTemplate(normalized, template, cv2.TM_CCOEFF_NORMED)[0][0]
                if score > best_score:
                    best_score = score
                    best_char = char

        return best_char

    def _build_templates(self, cv2: Any) -> dict[str, list[Any]]:
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        templates: dict[str, list[Any]] = {}
        fonts = [
            cv2.FONT_HERSHEY_SIMPLEX,
            cv2.FONT_HERSHEY_DUPLEX,
            cv2.FONT_HERSHEY_TRIPLEX,
        ]

        for char in chars:
            templates[char] = []
            for font in fonts:
                canvas = self._template_canvas(cv2, char, font)
                templates[char].append(canvas)

        return templates

    def _template_canvas(self, cv2: Any, char: str, font: int) -> Any:
        import numpy as np

        canvas = np.zeros((60, 45), dtype=np.uint8)
        (w, h), _ = cv2.getTextSize(char, font, 1.35, 2)
        x = max(0, (canvas.shape[1] - w) // 2)
        y = max(h + 4, (canvas.shape[0] + h) // 2 - 4)
        cv2.putText(canvas, char, (x, y), font, 1.35, 255, 2, cv2.LINE_AA)
        return cv2.resize(canvas, (24, 36), interpolation=cv2.INTER_AREA)


camera_recognizer = CameraPlateRecognizer()
