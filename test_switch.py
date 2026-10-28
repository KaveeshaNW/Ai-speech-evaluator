"""
Physical Toggle Switch, LCD Timer, and Audio Recording Verification Tool.
Tests:
1. GPIO pin 18 configuration with internal pull-up resistor.
2. Real-time switch state transitions (OFF = HIGH/3.3V, ON = LOW/GND).
3. Live LCD timer counting up in MM:SS format when switch is ON.
4. Real audio capture from USB microphone while switch is ON.
5. Automatic transcription via Deepgram Nova-2 and Grammarian evaluation on switch OFF.
6. Immediate publishing to the website dashboard (http://ai-speech-evaluator.local:8501).
"""

import io
import math
import os
import struct
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
import requests

from config import load_config
from services.ah_counter import AhCounter
from services.grammarian import GrammarianEngine
from services.report_generator import ReportGenerator
from services.auth_db import AuthDB


def run_unmute():
    commands = [
        "amixer set 'Mic' 100% unmute cap 2>/dev/null || true",
        "amixer set 'Capture' 100% unmute cap 2>/dev/null || true",
        "amixer -c 0 set 'Mic' 100% unmute cap 2>/dev/null || true",
        "amixer -c 0 set 'Capture' 100% unmute cap 2>/dev/null || true",
        "amixer -c 1 set 'Mic' 100% unmute cap 2>/dev/null || true",
        "amixer -c 1 set 'Capture' 100% unmute cap 2>/dev/null || true",
        "amixer -c 1 sset 'Mic' 100% cap 2>/dev/null || true",
        "amixer -c 1 sset 'Capture' 100% cap 2>/dev/null || true",
        "amixer -c 2 set 'Mic' 100% unmute cap 2>/dev/null || true",
        "amixer -c 2 set 'Capture' 100% unmute cap 2>/dev/null || true",
    ]
    for cmd in commands:
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    print("=" * 65)
    print(" AI SPEECH EVALUATOR - TOGGLE SWITCH, MIC & LCD TEST")
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
""")
    print("=" * 65)

    run_unmute()
    cfg = load_config()

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

    # 2. Initialize Audio Capture (PyAudio)
    pa = None
    target_idx = None
    chosen_rate = 16000
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        first_input_idx = -1
        usb_device_idx = -1
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_host_api_device_index(0, i)
                if info.get("maxInputChannels", 0) > 0:
                    if first_input_idx == -1:
                        first_input_idx = i
                    name = info.get("name", "").lower()
                    if any(k in name for k in ["usb", "m-305", "microphone", "mic", "pnp", "c-media", "codec", "sound"]):
                        usb_device_idx = i
            except Exception:
                pass
        target_idx = usb_device_idx if usb_device_idx >= 0 else (first_input_idx if first_input_idx >= 0 else None)
        for r in [16000, 44100, 48000]:
            try:
                test_s = pa.open(format=pyaudio.paInt16, channels=1, rate=r, input=True, input_device_index=target_idx, frames_per_buffer=1024)
                test_s.stop_stream()
                test_s.close()
                chosen_rate = r
                break
            except Exception:
                continue
        print(f"[+] Audio recording ready: device [{target_idx}] at {chosen_rate}Hz.")
    except Exception as e:
        print(f"[*] Audio capture not available ({e}).")

    # 3. Initialize GPIO (Try RPi.GPIO then gpiozero)
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
    print("[*] Flip your toggle switch ON to start recording audio!\n")

    last_state = None
    timer_start = None
    last_lcd_time = ""

    audio_frames = []
    audio_recording = False
    audio_thread = None

    def record_audio_loop():
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=chosen_rate,
                input=True,
                input_device_index=target_idx,
                frames_per_buffer=1024,
            )
            while audio_recording:
                data = stream.read(1024, exception_on_overflow=False)
                audio_frames.append(data)
            stream.stop_stream()
            stream.close()
        except Exception as err:
            print(f"\n[-] Audio record error: {err}")

    try:
        while True:
            is_on = read_switch()

            # State transition
            if is_on != last_state:
                last_state = is_on
                last_lcd_time = ""

                if is_on:
                    timer_start = time.time()
                    print("\n>>> [EVENT] SWITCH FLIPPED ON! Recording speech from microphone... <<<")
                    audio_frames = []
                    audio_recording = True

                    if pa:
                        audio_thread = threading.Thread(target=record_audio_loop, daemon=True)
                        audio_thread.start()

                    if lcd:
                        try:
                            lcd.clear()
                            time.sleep(0.01)
                            lcd.cursor_pos = (0, 0)
                            lcd.write_string("Time: 00:00     ")
                            time.sleep(0.002)
                            lcd.cursor_pos = (1, 0)
                            lcd.write_string("Recording...    ")
                        except Exception:
                            pass
                else:
                    if timer_start:
                        audio_recording = False
                        if audio_thread:
                            audio_thread.join(timeout=1.5)
                            audio_thread = None

                        elapsed = max(1, int(time.time() - timer_start))
                        mins, secs = divmod(elapsed, 60)
                        t_str = f"{mins:02d}:{secs:02d}"
                        print(f"\n<<< [EVENT] SWITCH FLIPPED OFF! Final Duration: {t_str} >>>")

                        if lcd:
                            try:
                                lcd.clear()
                                time.sleep(0.01)
                                lcd.cursor_pos = (0, 0)
                                lcd.write_string(f"Time: {t_str}     "[:16])
                                time.sleep(0.002)
                                lcd.cursor_pos = (1, 0)
                                lcd.write_string("Evaluating...   ")
                            except Exception:
                                pass

                        # Transcribe captured audio via Deepgram Nova-2
                        pcm_data = b"".join(audio_frames)
                        print(f"[*] Audio capture complete: {len(pcm_data)} bytes recorded.")

                        transcript = ""
                        words = []
                        if len(pcm_data) > 1000 and cfg.is_deepgram_configured():
                            print("[*] Sending audio to Deepgram Nova-2...")
                            wav_io = io.BytesIO()
                            with wave.open(wav_io, "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(chosen_rate)
                                wf.writeframes(pcm_data)

                            try:
                                resp = requests.post(
                                    "https://api.deepgram.com/v1/listen",
                                    params={"model": "nova-2", "language": "en-US", "smart_format": "true", "filler_words": "true"},
                                    headers={"Authorization": f"Token {cfg.deepgram_api_key}", "Content-Type": "audio/wav"},
                                    data=wav_io.getvalue(),
                                    timeout=35.0,
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    alt = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
                                    transcript = alt.get("transcript", "")
                                    words = alt.get("words", [])
                                    print(f"[+] DEEPGRAM TRANSCRIPT: \"{transcript}\"")
                                else:
                                    print(f"[!] Deepgram returned HTTP {resp.status_code}: {resp.text[:100]}")
                            except Exception as ex:
                                print(f"[!] Network error sending to Deepgram: {ex}")

                        # Evaluate Disfluencies and Grammar
                        ah = AhCounter()
                        if words:
                            ah.process_words(words)

                        engine = GrammarianEngine()
                        issues = []
                        if transcript:
                            print("[*] Analyzing spoken grammar...")
                            issues = engine.check_text_sync(transcript)
                            print(f"[+] Identified Spoken Grammar Issues: {len(issues)}")
                            for idx, issue in enumerate(issues):
                                print(f"    Issue #{idx+1}: {issue.rule_id} -> {issue.message} | Suggestions: {issue.suggestions}")
                        engine._issues = issues

                        # Generate report and write directly to evaluation_report.json and database
                        try:
                            rep_gen = ReportGenerator()
                            now_t = time.time()
                            rep_path, rep_data = rep_gen.generate(
                                session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
                                start_time=now_t - elapsed,
                                end_time=now_t,
                                full_transcript=transcript,
                                ah_counter=ah,
                                grammarian=engine,
                            )
                            adb = AuthDB()
                            adb.record_speech_session(rep_data, "evaluation_report.json")
                            print("\n" + "=" * 65)
                            print(" [+] Website dashboard successfully updated with your speech!")
                            print("     Open http://ai-speech-evaluator.local:8501 to see your evaluation report.")
                            print("=" * 65 + "\n")
                        except Exception as rep_err:
                            print(f"[*] Note: Could not update website report: {rep_err}")

                        if lcd:
                            try:
                                lcd.clear()
                                time.sleep(0.01)
                                lcd.cursor_pos = (0, 0)
                                lcd.write_string(f"Time: {t_str}     "[:16])
                                time.sleep(0.002)
                                lcd.cursor_pos = (1, 0)
                                lcd.write_string("Done!           ")
                            except Exception:
                                pass
                    else:
                        print("\n<<< [EVENT] Switch is OFF (Waiting for ON) >>>")
                        if lcd:
                            try:
                                lcd.clear()
                                time.sleep(0.01)
                                lcd.cursor_pos = (0, 0)
                                lcd.write_string("Time: 00:00     ")
                                time.sleep(0.002)
                                lcd.cursor_pos = (1, 0)
                                lcd.write_string("Ready...        ")
                            except Exception:
                                pass
                    timer_start = None

            # Active timer tick while ON (strictly MM:SS format, update ONLY when second changes)
            if is_on and timer_start:
                elapsed = int(time.time() - timer_start)
                mins, secs = divmod(elapsed, 60)
                t_str = f"{mins:02d}:{secs:02d}"
                sys.stdout.write(f"\r⏱️  Live Timer: {t_str} (Switch is ON / Recording speech) ")
                sys.stdout.flush()
                if lcd and t_str != last_lcd_time:
                    last_lcd_time = t_str
                    try:
                        lcd.cursor_pos = (0, 0)
                        lcd.write_string(f"Time: {t_str}     "[:16])
                        time.sleep(0.002)
                        lcd.cursor_pos = (1, 0)
                        lcd.write_string("Recording...    ")
                    except Exception:
                        pass

            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n\n[*] Switch test stopped.")
        audio_recording = False
        if backend == "rpi.gpio":
            gpio_obj.cleanup()
        elif backend == "gpiozero":
            button_obj.close()
        if pa:
            pa.terminate()
        if lcd:
            lcd.clear()
            lcd.write_string("Test Finished   ")

if __name__ == "__main__":
    main()
