from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any


PLATE_REGEX = re.compile(r"^[A-Z]{1,2}-[0-9]{4}$")


@dataclass
class CameraState:
    plate: str = ""
    status: str = "Kamera nicht gestartet"
    active: bool = False
    updated_at: float = 0.0


class CameraPlateRecognizer:
    def __init__(self, source: int = 0, width: int = 1280, height: int = 720) -> None:
        self.source = source
        self.width = width
        self.height = height
        self._state = CameraState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._templates: dict[str, list[Any]] = {}
        self._latest_jpeg: bytes = b""

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
                "status": self._state.status,
                "active": self._state.active,
                "updated_at": self._state.updated_at,
            }

    def get_jpeg(self) -> bytes:
        with self._lock:
            return self._latest_jpeg

    def _set_state(self, *, plate: str | None = None, status: str | None = None, active: bool | None = None) -> None:
        with self._lock:
            if plate is not None:
                self._state.plate = plate
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
        camera = cv2.VideoCapture(self.source)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not camera.isOpened():
            self._set_state(status="Laptop-Kamera konnte nicht geoeffnet werden", active=False)
            return

        self._set_state(status="Kamera aktiv", active=True)
        stable_plate = ""
        stable_hits = 0

        try:
            while not self._stop_event.is_set():
                ok, frame = camera.read()
                if not ok:
                    self._set_state(status="Kamerabild konnte nicht gelesen werden", active=False)
                    time.sleep(0.5)
                    continue

                detected = self._detect_plate(frame, cv2)
                self._update_preview(frame, detected, cv2)
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
                    self._set_state(status="Kamera aktiv", active=True)

                time.sleep(0.15)
        finally:
            camera.release()
            self._set_state(status="Kamera beendet", active=False)

    def _update_preview(self, frame: Any, detected: str, cv2: Any) -> None:
        preview = frame.copy()
        height, width = preview.shape[:2]
        guide_x1 = int(width * 0.18)
        guide_x2 = int(width * 0.82)
        guide_y1 = int(height * 0.36)
        guide_y2 = int(height * 0.64)
        cv2.rectangle(preview, (guide_x1, guide_y1), (guide_x2, guide_y2), (52, 152, 219), 2)

        label = f"Erkannt: {detected}" if detected else "Kennzeichen in den blauen Rahmen halten"
        cv2.rectangle(preview, (0, 0), (width, 42), (44, 62, 80), -1)
        cv2.putText(preview, label, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

        ok, encoded = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if ok:
            self._set_jpeg(encoded.tobytes())

    def _detect_plate(self, frame: Any, cv2: Any) -> str:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        candidates = self._candidate_regions(gray, cv2)

        for candidate in candidates:
            plate = self._read_candidate(candidate, cv2)
            if PLATE_REGEX.match(plate):
                return plate

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
        if len(plate) >= 6 and "-" not in plate:
            plate = f"{plate[:2]}-{plate[2:]}"
        return plate[:7]

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

    def _classify_char(self, char_img: Any, cv2: Any) -> str:
        normalized = cv2.resize(char_img, (24, 36), interpolation=cv2.INTER_AREA)
        best_char = ""
        best_score = -1.0

        for char, templates in self._templates.items():
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
