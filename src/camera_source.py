from __future__ import annotations

import os
from typing import Any


class CameraSource:
    """Camera wrapper that prefers Raspberry Pi Camera Module via picamera2."""

    def __init__(self, width: int = 1280, height: int = 720, source: int = 0) -> None:
        self.width = width
        self.height = height
        self.source = source
        self.kind = ""
        self._pi_format = ""
        self._color_fix = os.getenv("PARKHAUS_CAMERA_COLOR_FIX", "warm").strip().lower()
        self._red_gain = self._read_float_env("PARKHAUS_CAMERA_RED_GAIN", 1.18)
        self._blue_gain = self._read_float_env("PARKHAUS_CAMERA_BLUE_GAIN", 0.88)
        self._camera: Any = None

    def __enter__(self) -> "CameraSource":
        try:
            from picamera2 import Picamera2

            camera = Picamera2()
            config = self._create_pi_config(camera)
            camera.configure(config)
            camera.start()
            self._apply_pi_controls(camera)
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

    def _create_pi_config(self, camera: Any) -> Any:
        try:
            config = camera.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "BGR888"}
            )
            self._pi_format = "BGR888"
            return config
        except Exception:
            config = camera.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            self._pi_format = "RGB888"
            return config

    def _apply_pi_controls(self, camera: Any) -> None:
        controls_to_set: dict[str, Any] = {
            "AwbEnable": True,
        }

        try:
            from libcamera import controls

            controls_to_set["AwbMode"] = controls.AwbModeEnum.Indoor
            controls_to_set["AfMode"] = controls.AfModeEnum.Continuous
        except Exception:
            pass

        try:
            camera.set_controls(controls_to_set)
        except Exception:
            pass

    def _read_float_env(self, name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)).replace(",", "."))
        except ValueError:
            return default

    def _apply_color_fix(self, frame: Any, cv2: Any) -> Any:
        if self._color_fix in {"none", "off", "false", "0"}:
            return frame

        if self._color_fix in {"swap", "swap_rb", "rgb"}:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if self._color_fix == "warm":
            blue, green, red = cv2.split(frame)
            blue = cv2.convertScaleAbs(blue, alpha=self._blue_gain)
            red = cv2.convertScaleAbs(red, alpha=self._red_gain)
            return cv2.merge((blue, green, red))

        return frame

    def read(self) -> Any:
        if self.kind == "picamera2":
            import cv2

            frame = self._camera.capture_array()
            if self._pi_format == "RGB888":
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                return self._apply_color_fix(frame, cv2)
            if frame.shape[2] == 3:
                return self._apply_color_fix(frame, cv2)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            return self._apply_color_fix(frame, cv2)

        ok, frame = self._camera.read()
        if not ok:
            raise RuntimeError("Kamerabild konnte nicht gelesen werden.")
        return frame
