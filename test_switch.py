"""
Physical Toggle Switch and LCD Timer Verification Tool.
Tests:
1. GPIO pin 18 configuration with internal pull-up resistor.
2. Real-time switch state transitions (OFF = HIGH/3.3V, ON = LOW/GND).
3. Live LCD timer countdown/up when switch is toggled ON.
"""

import os
import sys
import time

def main():
    print("=" * 65)
    print(" AI SPEECH EVALUATOR - TOGGLE SWITCH & TIMER TEST")
    print("=" * 65)

    print("""
Raspberry Pi 40-Pin Header Wiring Guide:
  Pin 1  (3.3V)        Pin 2  (5V)    <-- LCD VCC
  Pin 3  (SDA )        Pin 4  (5V)
  Pin 5  (SCL )        Pin 6  (GND)   <-- LCD GND
  Pin 7  (GPIO 4)      Pin 8  (GPIO 14)
  Pin 9  (GND)         Pin 10 (GPIO 15)
  Pin 11 (GPIO 17)     Pin 12 (GPIO 18) <-- SWITCH WIRE 1 (BCM 18)
  Pin 13 (GPIO 27)     Pin 14 (GND)     <-- SWITCH WIRE 2 (GROUND)

NOTE:
- The toggle switch must be wired between Pin 12 (GPIO 18) and Pin 14 (GND).
- When switch is OFF (open circuit), GPIO 18 is pulled HIGH (3.3V).
- When switch is ON (closed circuit), GPIO 18 connects to GND (0V).
- If you don't have a switch yet, touch a jumper wire between Pin 12 and Pin 14!
""")
    print("=" * 65)

    # 1. Initialize LCD (optional, for visual feedback)
    lcd = None
    try:
        from RPLCD.i2c import CharLCD
        for addr in [0x27, 0x3F]:
            try:
                lcd = CharLCD(
                    i2c_expander="PCF8574",
                    address=addr,
                    port=1,
                    cols=16,
                    rows=2,
                    dotsize=8,
                    charmap="A00",
                    auto_linebreaks=False,
                    backlight_enabled=True,
                )
                lcd.clear()
                print(f"[+] LCD detected at {hex(addr)}. Live timer will show on screen!")
                break
            except Exception:
                pass
    except Exception as e:
        print(f"[*] LCD not initialized ({e}). Testing via console only.")

    # 2. Initialize GPIO (Try RPi.GPIO then gpiozero)
    backend = None
    gpio_obj = None
    button_obj = None
    pin = 18

    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        backend = "rpi.gpio"
        gpio_obj = GPIO
        print("[+] Initialized via RPi.GPIO (BCM Pin 18 / Physical Pin 12).")
    except Exception as e:
        print(f"[*] RPi.GPIO failed ({e}), trying gpiozero...")

    if not backend:
        try:
            from gpiozero import Button
            button_obj = Button(pin, pull_up=True, bounce_time=0.1)
            backend = "gpiozero"
            print("[+] Initialized via gpiozero (BCM Pin 18 / Physical Pin 12).")
        except Exception as e:
            print(f"[!] FAILED: Neither RPi.GPIO nor gpiozero could be initialized: {e}")
            print("    Run: pip install RPi.GPIO gpiozero")
            sys.exit(1)

    def read_switch():
        if backend == "rpi.gpio":
            return gpio_obj.input(pin) == gpio_obj.LOW
        elif backend == "gpiozero":
            return bool(button_obj.is_pressed)
        return False

    print("\n[*] Monitoring Switch on GPIO 18 (Press Ctrl+C to exit)...")
    print("[*] Flip your toggle switch ON / connect Pin 12 to Pin 14 now!\n")

    last_state = None
    timer_start = None

    try:
        while True:
            is_on = read_switch()

            # State transition
            if is_on != last_state:
                last_state = is_on
                if is_on:
                    timer_start = time.time()
                    print("\n>>> [EVENT] SWITCH FLIPPED ON! Starting live timer... <<<")
                    if lcd:
                        lcd.cursor_pos = (0, 0)
                        lcd.write_string("Time: 00:00     ")
                        lcd.cursor_pos = (1, 0)
                        lcd.write_string("Recording...    ")
                else:
                    if timer_start:
                        elapsed = int(time.time() - timer_start)
                        mins, secs = divmod(elapsed, 60)
                        t_str = f"{mins:02d}:{secs:02d}"
                        print(f"\n<<< [EVENT] SWITCH FLIPPED OFF! Final Duration: {t_str} >>>\n")
                        if lcd:
                            lcd.cursor_pos = (0, 0)
                            lcd.write_string(f"Time: {t_str}     "[:16])
                            lcd.cursor_pos = (1, 0)
                            lcd.write_string("Done!           ")
                    else:
                        print("\n<<< [EVENT] Switch is OFF (Waiting for ON) >>>")
                        if lcd:
                            lcd.cursor_pos = (0, 0)
                            lcd.write_string("Time: 00:00     ")
                            lcd.cursor_pos = (1, 0)
                            lcd.write_string("Ready...        ")
                    timer_start = None

            # Active timer tick while ON (strictly MM:SS format)
            if is_on and timer_start:
                elapsed = int(time.time() - timer_start)
                mins, secs = divmod(elapsed, 60)
                t_str = f"{mins:02d}:{secs:02d}"
                sys.stdout.write(f"\r⏱️  Live Timer: {t_str} (Switch is ON / Recording) ")
                sys.stdout.flush()
                if lcd:
                    lcd.cursor_pos = (0, 0)
                    lcd.write_string(f"Time: {t_str}     "[:16])
                    lcd.cursor_pos = (1, 0)
                    lcd.write_string("Recording...    ")

            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n\n[*] Switch test stopped.")
        if backend == "rpi.gpio":
            gpio_obj.cleanup()
        elif backend == "gpiozero":
            button_obj.close()
        if lcd:
            lcd.clear()
            lcd.write_string("Test Finished   ")

if __name__ == "__main__":
    main()
