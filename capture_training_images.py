from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PLATE_PATTERN = re.compile(r"[^A-Z0-9_-]+")


def normalize_plate(value: str) -> str:
    value = value.strip().upper().replace(" ", "_")
    value = PLATE_PATTERN.sub("", value)
    return value or "UNBEKANNT"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def append_manifest(manifest_path: Path, row: dict[str, str]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not manifest_path.exists()

    with manifest_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["created_at", "plate", "image_path", "source", "width", "height"],
        )
        if write_header:
            writer.writeheader()
        writer.writerow(row)


class Camera:
    def __init__(self, width: int, height: int, source: int) -> None:
        self.width = width
        self.height = height
        self.source = source
        self.kind = ""
        self._camera: Any = None

    def __enter__(self) -> "Camera":
        try:
            from picamera2 import Picamera2

            camera = Picamera2()
            config = camera.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            camera.configure(config)
            camera.start()
            self._camera = camera
            self.kind = "picamera2"
            return self
        except Exception as pi_error:
            try:
                import cv2

                camera = cv2.VideoCapture(self.source)
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                if not camera.isOpened():
                    raise RuntimeError("OpenCV konnte keine Kamera oeffnen.")
                self._camera = camera
                self.kind = "opencv"
                return self
            except Exception as cv_error:
                raise RuntimeError(
                    "Keine Kamera gefunden. Auf dem Raspberry Pi bitte picamera2 installieren "
                    "und die Kamera aktivieren."
                ) from cv_error

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.kind == "picamera2":
            self._camera.stop()
        elif self.kind == "opencv":
            self._camera.release()

    def read(self) -> Any:
        if self.kind == "picamera2":
            import cv2

            frame = self._camera.capture_array()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        ok, frame = self._camera.read()
        if not ok:
            raise RuntimeError("Kamerabild konnte nicht gelesen werden.")
        return frame


def save_frame(frame: Any, target: Path) -> None:
    import cv2

    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), frame):
        raise RuntimeError(f"Bild konnte nicht gespeichert werden: {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nimmt Trainingsbilder von Kennzeichen fuer die Parkhaussteuerung auf."
    )
    parser.add_argument("--plate", "-p", default="", help="Kennzeichen/Label, z.B. RO-AB123.")
    parser.add_argument("--output", "-o", default="data/raw", help="Zielordner fuer Bilder.")
    parser.add_argument("--manifest", default="data/manifest.csv", help="CSV-Datei mit Bildindex.")
    parser.add_argument("--width", type=int, default=1280, help="Bildbreite.")
    parser.add_argument("--height", type=int, default=720, help="Bildhoehe.")
    parser.add_argument("--source", type=int, default=0, help="OpenCV-Kameraindex als Fallback.")
    parser.add_argument("--interval", type=float, default=0.0, help="Automatisch alle N Sekunden speichern.")
    parser.add_argument("--limit", type=int, default=0, help="Nach N Bildern automatisch beenden.")
    parser.add_argument("--warmup", type=float, default=1.5, help="Sekunden warten, bis Kamera hell ist.")
    parser.add_argument("--no-preview", action="store_true", help="Ohne Vorschaufenster arbeiten.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plate = normalize_plate(args.plate or input("Kennzeichen/Label: "))
    output_dir = Path(args.output) / plate
    manifest_path = Path(args.manifest)

    try:
        import cv2
    except ImportError:
        print("OpenCV fehlt. Installiere es auf dem Pi mit: sudo apt install python3-opencv")
        return 2

    print("Starte Kamera...")
    with Camera(args.width, args.height, args.source) as camera:
        time.sleep(args.warmup)
        print(f"Kamera: {camera.kind}")
        print("Tasten: s = Bild speichern, q = beenden")
        if args.interval > 0:
            print(f"Automatik: alle {args.interval:g} Sekunden speichern")

        saved = 0
        next_auto_save = time.monotonic() + args.interval if args.interval > 0 else 0

        while True:
            frame = camera.read()
            should_save = False

            if not args.no_preview:
                preview = frame.copy()
                cv2.putText(
                    preview,
                    f"{plate} | gespeichert: {saved} | s=speichern q=ende",
                    (20, 36),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("Parkhaus Trainingsbilder", preview)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    should_save = True

            if args.no_preview:
                time.sleep(0.05)

            if args.interval > 0 and time.monotonic() >= next_auto_save:
                should_save = True
                next_auto_save = time.monotonic() + args.interval

            if should_save:
                image_path = output_dir / f"{plate}_{timestamp()}_{saved + 1:04d}.jpg"
                save_frame(frame, image_path)
                append_manifest(
                    manifest_path,
                    {
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "plate": plate,
                        "image_path": str(image_path),
                        "source": camera.kind,
                        "width": str(args.width),
                        "height": str(args.height),
                    },
                )
                saved += 1
                print(f"Gespeichert: {image_path}")

            if args.limit and saved >= args.limit:
                break

        cv2.destroyAllWindows()

    print(f"Fertig. {saved} Bilder fuer {plate} gespeichert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
