from __future__ import annotations

from typing import Any


class CameraSource:
    """Camera wrapper that prefers Raspberry Pi Camera Module via picamera2."""

    def __init__(self, width: int = 1280, height: int = 720, source: int = 0) -> None:
        self.width = width
        self.height = height
        self.source = source
        self.kind = ""
        self._camera: Any = None

    def __enter__(self) -> "CameraSource":
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
                    "Keine Kamera gefunden. Auf dem Raspberry Pi bitte python3-picamera2 "
                    "installieren und die Kamera korrekt anschliessen."
                ) from cv_error

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.kind == "picamera2" and self._camera is not None:
            self._camera.stop()
        elif self.kind == "opencv" and self._camera is not None:
            self._camera.release()
        self._camera = None
        self.kind = ""

    def read(self) -> Any:
        if self.kind == "picamera2":
            import cv2

            frame = self._camera.capture_array()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        ok, frame = self._camera.read()
        if not ok:
            raise RuntimeError("Kamerabild konnte nicht gelesen werden.")
        return frame
