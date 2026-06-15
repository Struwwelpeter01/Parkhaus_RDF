from machine import Pin, PWM
from time import sleep_ms, ticks_ms, ticks_diff


# =========================
# PINBELEGUNG ESP32-C6
# =========================
# Diese GPIO-Nummern bei Bedarf an eure Verkabelung anpassen.

# Eingangssignale vom Raspberry Pi
SIGNAL_EINFAHRT_PIN = 2
SIGNAL_AUSFAHRT_PIN = 3

# PWM-Ausgaenge zu den Servos
SERVO_EINFAHRT_PIN = 4
SERVO_AUSFAHRT_PIN = 5

# Ampel Einfahrt
LED_EINFAHRT_ROT_PIN = 15
LED_EINFAHRT_GRUEN_PIN = 18

# Ampel Ausfahrt
LED_AUSFAHRT_ROT_PIN = 19
LED_AUSFAHRT_GRUEN_PIN = 20


# =========================
# EINSTELLUNGEN
# =========================

SERVO_FREQUENZ = 50
SERVO_MIN_US = 500
SERVO_MAX_US = 2500

# Falls die Schranke falsch herum faehrt, diese beiden Werte tauschen.
WINKEL_ZU = 0
WINKEL_OFFEN = 90

OFFEN_ZEIT_MS = 10_000
ENTPRELL_ZEIT_MS = 300

# True: Eingang ist aktiv, wenn 3.3 V/HIGH anliegt.
# Finaler Aufbau:
# ESP-GPIO hat einen 10-kOhm-Widerstand nach GND.
# Raspberry Pi gibt beim erkannten Auto kurz 3.3 V/HIGH auf den ESP-GPIO.
SIGNAL_AKTIV_HIGH = True

# Zum Testen in Wokwi/Thonny auf True stellen.
# Dann werden die Eingangswerte alle 500 ms ausgegeben.
DEBUG_EINGAENGE = False


class Servo:
    def __init__(self, pin):
        self.pwm = PWM(Pin(pin), freq=SERVO_FREQUENZ)
        self.winkel = WINKEL_ZU
        self.set_winkel(WINKEL_ZU)

    def set_winkel(self, winkel):
        winkel = max(0, min(180, winkel))
        self.winkel = winkel

        puls_us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * winkel // 180

        # 50 Hz bedeutet 20 ms Periodendauer.
        # duty_ns ist genauer, duty_u16 ist der Fallback fuer andere Firmware-Versionen.
        if hasattr(self.pwm, "duty_ns"):
            self.pwm.duty_ns(puls_us * 1000)
        else:
            self.pwm.duty_u16(int(puls_us * 65535 / 20_000))


class Schranke:
    def __init__(self, name, signal_pin, servo_pin, led_rot_pin, led_gruen_pin):
        self.name = name
        self.signal = Pin(signal_pin, Pin.IN)
        self.servo = Servo(servo_pin)
        self.led_rot = Pin(led_rot_pin, Pin.OUT)
        self.led_gruen = Pin(led_gruen_pin, Pin.OUT)

        self.ist_offen = False
        self.offen_bis = 0
        self.letzter_impuls_ms = 0
        self.letztes_signal_aktiv = self.signal_ist_aktiv()

        self.schliessen()

    def ampel_rot(self):
        self.led_rot.value(1)
        self.led_gruen.value(0)

    def ampel_gruen(self):
        self.led_rot.value(0)
        self.led_gruen.value(1)

    def oeffnen(self):
        print(self.name, "oeffnet")
        self.servo.set_winkel(WINKEL_OFFEN)
        self.ampel_gruen()
        self.ist_offen = True
        self.offen_bis = ticks_ms() + OFFEN_ZEIT_MS

    def schliessen(self):
        print(self.name, "geschlossen")
        self.servo.set_winkel(WINKEL_ZU)
        self.ampel_rot()
        self.ist_offen = False

    def signal_ist_aktiv(self):
        wert = self.signal.value()
        if SIGNAL_AKTIV_HIGH:
            return wert == 1
        return wert == 0

    def signal_erkannt(self):
        signal_aktiv = self.signal_ist_aktiv()
        neuer_impuls = signal_aktiv and not self.letztes_signal_aktiv
        self.letztes_signal_aktiv = signal_aktiv

        if not neuer_impuls:
            return False

        jetzt = ticks_ms()
        if ticks_diff(jetzt, self.letzter_impuls_ms) < ENTPRELL_ZEIT_MS:
            return False

        self.letzter_impuls_ms = jetzt
        return True

    def update(self):
        if self.signal_erkannt():
            self.oeffnen()

        if self.ist_offen and ticks_diff(ticks_ms(), self.offen_bis) >= 0:
            self.schliessen()


einfahrt = Schranke(
    "Einfahrt",
    SIGNAL_EINFAHRT_PIN,
    SERVO_EINFAHRT_PIN,
    LED_EINFAHRT_ROT_PIN,
    LED_EINFAHRT_GRUEN_PIN,
)

ausfahrt = Schranke(
    "Ausfahrt",
    SIGNAL_AUSFAHRT_PIN,
    SERVO_AUSFAHRT_PIN,
    LED_AUSFAHRT_ROT_PIN,
    LED_AUSFAHRT_GRUEN_PIN,
)


print("ESP32 Schrankensteuerung laeuft")

letzter_debug_ms = 0

while True:
    einfahrt.update()
    ausfahrt.update()

    if DEBUG_EINGAENGE and ticks_diff(ticks_ms(), letzter_debug_ms) >= 500:
        letzter_debug_ms = ticks_ms()
        print(
            "Einfahrt:",
            einfahrt.signal.value(),
            "Ausfahrt:",
            ausfahrt.signal.value(),
        )

    sleep_ms(20)
