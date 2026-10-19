#!/usr/bin/env python3
"""
Interactive Hardware Diagnostic Tool for AI Speech Evaluator.
Target Platform: Raspberry Pi 3 (Raspberry Pi OS 64-bit).

Tests:
1. LCM1602A 16x2 LCD with PCF8574 I2C Backpack (Pins: SDA=GPIO 2, SCL=GPIO 3, 5V, GND).
2. USB Audio Adapter & M-305 Microphone (PyAudio device scan & live ASCII VU meter).
3. Physical Toggle Switch on GPIO 18 (Internal pull-up GPIO.PUD_UP).

Usage:
    python tests/test_hardware.py --all
    python tests/test_hardware.py --lcd
    python tests/test_hardware.py --audio
    python tests/test_hardware.py --switch
"""

import argparse
import math
import os
import struct
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import load_config


def print_banner(title: str) -> None:
    print("\n" + "=" * 65)
    print(f"  {title.center(61)}")
    print("=" * 65)


# -----------------------------------------------------------------------------
# 1. I2C LCD Diagnostic
# -----------------------------------------------------------------------------
def test_i2c_lcd(address: int = 0x27, port: int = 1) -> bool:
    print_banner(f"TEST 1: LCM1602A LCD Display (I2C {hex(address)}, Port {port})")
    print(f"[*] Checking I2C bus {port} for device at address {hex(address)}...")

    # Step 1: Scan I2C bus with smbus2
    try:
        import smbus2

        bus = smbus2.SMBus(port)
        try:
            bus.read_byte(address)
            print(f"[+] Device ACK received at address {hex(address)}!")
        except Exception as e:
            print(f"[-] No I2C ACK at {hex(address)}: {e}")
            print("[!] Troubleshooting hints:")
            print("    1. Run 'i2cdetect -y 1' to check actual backpack address (often 0x27 or 0x3F).")
            print("    2. Verify SDA is on GPIO 2 (Pin 3) and SCL is on GPIO 3 (Pin 5).")
            print("    3. Ensure I2C is enabled in 'sudo raspi-config' -> Interface Options -> I2C.")
            bus.close()
            return False
        bus.close()
    except ImportError:
        print("[!] Note: smbus2 not installed or platform is non-Linux. Proceeding with RPLCD directly.")
    except Exception as e:
        print(f"[-] I2C bus access error: {e}")

    # Step 2: Drive display using RPLCD
    try:
        from RPLCD.i2c import CharLCD

        print("[*] Initializing RPLCD CharLCD driver...")
        lcd = CharLCD(
            i2c_expander="PCF8574",
            address=address,
            port=port,
            cols=16,
            rows=2,
            dotsize=8,
            charmap="A00",
            auto_linebreaks=False,
            backlight_enabled=True,
        )

        lcd.clear()
        print("[*] Writing test pattern to LCD...")
        lcd.cursor_pos = (0, 0)
        lcd.write_string("LCD Test: OK!   ")
        lcd.cursor_pos = (1, 0)
        lcd.write_string(f"Addr:{hex(address)} Port:{port}")
        time.sleep(2.0)

        # Step 3: Backlight blink test
        print("[*] Blinking backlight...")
        for _ in range(3):
            lcd.backlight_enabled = False
            time.sleep(0.3)
            lcd.backlight_enabled = True
            time.sleep(0.3)

        # Step 4: Toastmasters timer-only status simulation
        print("[*] Testing speech timer format (Line 1: Time, Line 2: Status)...")
        lcd.clear()
        lcd.cursor_pos = (0, 0)
        lcd.write_string("Time: 05:23     ")
        lcd.cursor_pos = (1, 0)
        lcd.write_string("Recording...    ")
        time.sleep(2.0)

        lcd.cursor_pos = (1, 0)
        lcd.write_string("Evaluating...   ")
        time.sleep(1.5)

        lcd.clear()
        lcd.write_string("Diag Complete!  ")
        time.sleep(1.0)
        lcd.clear()
        lcd.close(clear=True)

        print("[+] LCD Diagnostic: SUCCESS! Text and backlight verified.")
        return True

    except ImportError:
        print("[-] RPLCD is not installed. Run: pip install RPLCD smbus2")
        return False
    except Exception as e:
        print(f"[-] LCD Test failed with error: {e}")
        return False


# -----------------------------------------------------------------------------
# 2. USB Audio & Microphone Diagnostic
# -----------------------------------------------------------------------------
def test_audio_input(device_index: int = -1, sample_rate: int = 16000, duration_seconds: int = 5) -> bool:
    print_banner("TEST 2: USB Audio & M-305 Microphone")
    print("[*] Scanning audio input devices using PyAudio...")

    try:
        import pyaudio

        pa = pyaudio.PyAudio()
    except ImportError:
        print("[-] PyAudio is not installed. Run: sudo apt-get install portaudio19-dev && pip install pyaudio")
        return False

    devices = []
    device_count = pa.get_device_count()
    print(f"[*] Found {device_count} audio device(s) on host:")

    selected_idx = device_index
    for idx in range(device_count):
        try:
            info = pa.get_device_info_by_host_api_device_index(0, idx)
            in_ch = info.get("maxInputChannels", 0)
            name = info.get("name", "Unknown")
            rate = int(info.get("defaultSampleRate", 0))
            if in_ch > 0:
                is_usb = "usb" in name.lower() or "m-305" in name.lower() or "microphone" in name.lower()
                tag = " [DETECTED USB MIC]" if is_usb else ""
                print(f"    Index [{idx}]: {name} (Inputs: {in_ch}, Rate: {rate}Hz){tag}")
                devices.append((idx, name))
                if selected_idx < 0 and is_usb:
                    selected_idx = idx
        except Exception:
            continue

    if not devices:
        print("[-] No audio input devices found! Is the USB audio adapter plugged in?")
        pa.terminate()
        return False

    if selected_idx < 0:
        try:
            selected_idx = pa.get_default_input_device_info().get("index", 0)
        except Exception:
            selected_idx = devices[0][0]

    dev_name = pa.get_device_info_by_host_api_device_index(0, selected_idx).get("name", "Unknown")
    print(f"\n[*] Testing Audio Capture on Device [{selected_idx}]: '{dev_name}'")
    print(f"[*] Settings: {sample_rate}Hz, 16-bit Mono PCM, 1024 chunk size")

    chunk_size = 1024
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            input_device_index=selected_idx,
            frames_per_buffer=chunk_size,
        )
    except Exception as e:
        print(f"[-] Could not open PyAudio stream on device [{selected_idx}]: {e}")
        pa.terminate()
        return False

    print(f"[*] Recording for {duration_seconds} seconds. Please SPEAK into the M-305 microphone...")
    print("    Live VU Meter (dBFS):")

    total_chunks = int(sample_rate / chunk_size * duration_seconds)
    peak_db = -96.0
    detected_speech = False

    for _ in range(total_chunks):
        try:
            data = stream.read(chunk_size, exception_on_overflow=False)
            count = len(data) // 2
            if count > 0:
                shorts = struct.unpack(f"{count}h", data)
                sum_sq = sum(s * s for s in shorts)
                rms = math.sqrt(sum_sq / count)
                db = 20 * math.log10(max(rms, 1.0) / 32767.0)
                db = max(-96.0, db)
                if db > peak_db:
                    peak_db = db

                # Render ASCII VU Bar
                # Range: -60 dB to 0 dB
                clamped_db = max(-60.0, min(0.0, db))
                bar_len = int(((clamped_db + 60.0) / 60.0) * 30)
                meter = "=" * bar_len + " " * (30 - bar_len)
                status = " [VOICE DETECTED]" if db > -35.0 else ""
                if db > -35.0:
                    detected_speech = True

                sys.stdout.write(f"\r    [{meter}] {db:5.1f} dBFS{status.ljust(18)}")
                sys.stdout.flush()
        except Exception as e:
            print(f"\n[-] Error reading stream: {e}")
            break

    sys.stdout.write("\n")
    stream.stop_stream()
    stream.close()
    pa.terminate()

    print(f"\n[*] Peak Audio Level Recorded: {peak_db:.1f} dBFS")
    if peak_db < -60.0:
        print("[-] Warning: Recorded audio level was extremely quiet or silent.")
        print("    Check: Microphone volume in 'alsamixer', mute switch on USB adapter.")
        return False
    elif detected_speech:
        print("[+] Audio Diagnostic: SUCCESS! Vocal levels cleanly captured.")
        return True
    else:
        print("[~] Audio captured successfully, but vocal volume was low (< -35 dBFS).")
        return True


# -----------------------------------------------------------------------------
# 3. GPIO Switch Diagnostic
# -----------------------------------------------------------------------------
def test_gpio_switch(pin: int = 18, timeout_seconds: int = 15) -> bool:
    print_banner(f"TEST 3: Physical Toggle Switch (GPIO {pin} BCM)")
    print(f"[*] Testing GPIO {pin} with internal pull-up resistor (GPIO.PUD_UP)...")
    print("    Expected Circuit: Switch connected between GPIO 18 (Pin 12) and GND (Pin 14).")
    print("    Switch ON  = Closed circuit to GND -> Reads GPIO.LOW (0)")
    print("    Switch OFF = Open circuit          -> Reads GPIO.HIGH (1)")

    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("[-] RPi.GPIO is not available. This test requires Raspberry Pi OS.")
        return False

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        initial = GPIO.input(pin)
        state_str = "ON (LOW)" if initial == GPIO.LOW else "OFF (HIGH)"
        print(f"[*] Initial Switch State: {state_str}")

        print(f"\n[*] Please TOGGLE the switch now (listening for up to {timeout_seconds} seconds)...")

        t_end = time.time() + timeout_seconds
        last_val = initial
        toggles_observed = 0

        while time.time() < t_end:
            curr_val = GPIO.input(pin)
            if curr_val != last_val:
                time.sleep(0.05)  # Debounce delay
                curr_val = GPIO.input(pin)
                if curr_val != last_val:
                    toggles_observed += 1
                    last_val = curr_val
                    now_str = "ON (LOW - Capturing)" if curr_val == GPIO.LOW else "OFF (HIGH - Stopped)"
                    print(f"    [+] Event #{toggles_observed}: Switch toggled to {now_str}")
                    if toggles_observed >= 2:
                        print("[+] Both transitions (ON and OFF) verified!")
                        break
            time.sleep(0.05)

        GPIO.cleanup(pin)

        if toggles_observed >= 1:
            print("[+] Switch Diagnostic: SUCCESS! Toggle transitions registered cleanly.")
            return True
        else:
            print(f"[-] No state transitions observed within {timeout_seconds} seconds.")
            print("    Check physical wiring between GPIO 18 and GND.")
            return False

    except Exception as e:
        print(f"[-] Switch test error: {e}")
        try:
            GPIO.cleanup(pin)
        except Exception:
            pass
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Interactive Hardware Diagnostics for Toastmasters AI Speech Evaluator"
    )
    parser.add_argument("--all", action="store_true", help="Run all hardware tests sequentially")
    parser.add_argument("--lcd", action="store_true", help="Test LCM1602A I2C LCD Display")
    parser.add_argument("--audio", action="store_true", help="Test M-305 USB Audio Input with VU meter")
    parser.add_argument("--switch", action="store_true", help="Test GPIO 18 Toggle Switch")
    args = parser.parse_args()

    # If no flags passed, run all tests
    if not (args.all or args.lcd or args.audio or args.switch):
        args.all = True

    config = load_config()
    results = {}

    print("\n" + "#" * 65)
    print("  TOASTMASTERS AI SPEECH EVALUATOR - HARDWARE DIAGNOSTICS")
    print("#" * 65)

    if args.all or args.lcd:
        results["LCM1602A LCD Display"] = test_i2c_lcd(
            address=config.lcd_i2c_address,
            port=config.lcd_i2c_port,
        )

    if args.all or args.audio:
        results["USB Audio & M-305 Mic"] = test_audio_input(
            device_index=config.audio_device_index,
            sample_rate=config.audio_sample_rate,
        )

    if args.all or args.switch:
        results["GPIO 18 Toggle Switch"] = test_gpio_switch(
            pin=config.switch_gpio_pin,
        )

    # Print summary
    print_banner("DIAGNOSTIC TEST SUMMARY")
    all_passed = True
    for test_name, passed in results.items():
        status = "PASSED [OK]" if passed else "FAILED [X]"
        if not passed:
            all_passed = False
        print(f"  - {test_name.ljust(30)} : {status}")
    print("=" * 65 + "\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
