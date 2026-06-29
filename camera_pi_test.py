#!/usr/bin/env python
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from camera_source import CameraSource


def main():
    width = int(os.getenv("PARKHAUS_CAMERA_TEST_WIDTH", "1280"))
    height = int(os.getenv("PARKHAUS_CAMERA_TEST_HEIGHT", "720"))
    source = int(os.getenv("PARKHAUS_CAMERA_SOURCE", "0"))
    output = ROOT / "data" / "kamera_test.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)

    import cv2

    with CameraSource(width=width, height=height, source=source) as camera:
        frame = camera.read()
        ok = cv2.imwrite(str(output), frame)
        if not ok:
            raise RuntimeError("Testbild konnte nicht gespeichert werden.")

        print(f"Kamera OK: {camera.kind}")
        print(f"Aufloesung: {frame.shape[1]}x{frame.shape[0]}")
        print(f"Testbild: {output}")


if __name__ == "__main__":
    main()
