from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from camera_source import CameraSource


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
    parser.add_argument(
        "--button-gpio",
        type=int,
        default=0,
        help="BCM-GPIO-Pin fuer einen physischen Taster. Jeder Tastendruck speichert ein Bild.",
    )
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

    button = None
    button_pressed = False
    if args.button_gpio:
        try:
            from gpiozero import Button

            button = Button(args.button_gpio, pull_up=True, bounce_time=0.15)

            def mark_button_pressed() -> None:
                nonlocal button_pressed
                button_pressed = True

            button.when_pressed = mark_button_pressed
        except ImportError:
            print("gpiozero fehlt. Installiere es mit: sudo apt install python3-gpiozero")
            return 2

    print("Starte Kamera...")
    with CameraSource(args.width, args.height, args.source) as camera:
        time.sleep(args.warmup)
        print(f"Kamera: {camera.kind}")
        print("Tasten: s = Bild speichern, q = beenden")
        if button:
            print(f"GPIO-Taster: BCM {args.button_gpio} speichert ein Bild")
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
                    f"{plate} | gespeichert: {saved} | s/GPIO=speichern q=ende",
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

            if button_pressed:
                should_save = True
                button_pressed = False

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
