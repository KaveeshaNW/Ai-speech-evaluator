"""
Microphone and Audio Hardware Diagnostic Tool.
Tests:
1. ALSA mixer capture unmuting.
2. USB microphone audio stream acquisition.
3. Live audio volume levels (RMS dBFS).
4. Deepgram Nova-2 transcription of spoken audio.
5. Grammarian syntax evaluation.
"""

import math
import os
import struct
import subprocess
import sys
import time
import wave
import io
import requests

from config import load_config
from services.grammarian import GrammarianEngine

def run_unmute():
    print("[*] Unmuting ALSA microphone capture channels...")
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


def check_alsa_hardware():
    print("[*] Detecting ALSA recording hardware (arecord -l)...")
    try:
        out = subprocess.check_output(["arecord", "-l"], universal_newlines=True, stderr=subprocess.STDOUT)
        cards = [line.strip() for line in out.splitlines() if line.startswith("card")]
        for c in cards:
            print(f"    {c}")
        if not cards:
            print("    [!] WARNING: No sound card found for recording! USB audio adapter may be unplugged.")
    except Exception as e:
        print(f"    [*] arecord note: {e}")


def main():
    print("=" * 65)
    print(" AI SPEECH EVALUATOR - MICROPHONE & HARDWARE DIAGNOSTIC")
    print("=" * 65)

    check_alsa_hardware()
    run_unmute()

    cfg = load_config()
    print(f"[*] Deepgram Configured: {'YES' if cfg.is_deepgram_configured() else 'NO (Check .env)'}")

    try:
        import pyaudio
    except ImportError:
        print("[!] PyAudio not installed in this environment. Run: pip install pyaudio")
        return

    pa = pyaudio.PyAudio()
    device_count = pa.get_device_count()
    print(f"[*] Found {device_count} audio device(s):")

    usb_device_idx = -1
    first_input_idx = -1
    for i in range(device_count):
        try:
            info = pa.get_device_info_by_host_api_device_index(0, i)
            if info.get("maxInputChannels", 0) > 0:
                if first_input_idx == -1:
                    first_input_idx = i
                name = info.get("name", "")
                rate = int(info.get("defaultSampleRate", 0))
                print(f"    [{i}] {name} ({rate}Hz, {info.get('maxInputChannels')} in)")
                lower_name = name.lower()
                if any(k in lower_name for k in ["usb", "m-305", "microphone", "mic", "pnp", "c-media", "codec", "sound"]):
                    usb_device_idx = i
        except Exception:
            pass

    target_idx = usb_device_idx if usb_device_idx >= 0 else (first_input_idx if first_input_idx >= 0 else None)
    print(f"[*] Target recording device index: {target_idx}")

    # Open stream
    rates = [16000, 44100, 48000]
    stream = None
    chosen_rate = 16000

    for r in rates:
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=r,
                input=True,
                input_device_index=target_idx,
                frames_per_buffer=1024,
            )
            chosen_rate = r
            print(f"[+] Successfully opened audio stream at {r}Hz.")
            break
        except Exception:
            continue

    if not stream:
        print("[!] ERROR: Could not open any audio stream on this hardware.")
        pa.terminate()
        return

    duration_seconds = 5
    total_chunks = int(chosen_rate / 1024 * duration_seconds)

    print("\n" + "=" * 65)
    print(" 🎙️ RECORDING 5 SECONDS OF AUDIO... SPEAK INTO THE M-305 NOW!")
    print(" (Say something loud like: 'Hello Toastmasters testing 1 2 3')")
    print("=" * 65)
    print(" Live VU Meter (dBFS):")

    frames = []
    peak_db = -96.0

    for _ in range(total_chunks):
        try:
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

            count = len(data) // 2
            if count > 0:
                shorts = struct.unpack(f"{count}h", data)
                sum_sq = sum(s * s for s in shorts)
                rms = math.sqrt(sum_sq / count)
                db = 20 * math.log10(max(rms, 1.0) / 32767.0)
                db = max(-96.0, db)
                if db > peak_db:
                    peak_db = db

                clamped_db = max(-60.0, min(0.0, db))
                bar_len = int(((clamped_db + 60.0) / 60.0) * 30)
                meter = "=" * bar_len + " " * (30 - bar_len)
                status = " [VOICE DETECTED]" if db > -35.0 else ""
                sys.stdout.write(f"\r    [{meter}] {db:5.1f} dBFS{status.ljust(18)}")
                sys.stdout.flush()
        except Exception as e:
            print(f"\n[-] Error reading stream: {e}")
            break

    sys.stdout.write("\n")
    stream.stop_stream()
    stream.close()
    pa.terminate()

    pcm_data = b"".join(frames)
    print(f"\n[*] Audio Capture Complete: {len(pcm_data)} bytes recorded.")
    print(f"[*] Peak Volume Level: {peak_db:.1f} dBFS")

    if peak_db < -45.0:
        print("\n" + "!" * 65)
        print(" [WARNING] SILENCE OR VERY LOW AUDIO DETECTED!")
        print(" Checklist to fix:")
        print(" 1. Check physical switch on Carol M-305 handle (Slide UP to 'ON').")
        print(" 2. Ensure microphone 3.5mm plug is firmly seated in the PINK jack (Mic).")
        print("    (Do NOT plug into the Green headphone jack).")
        print(" 3. Check ALSA mixer volume:")
        print("    Run 'alsamixer' -> Press F6 -> Select USB Audio Card.")
        print("    Press F4 (Capture) -> Press Space to toggle [CAPTURE] -> Press Up Arrow to 100%.")
        print("!" * 65)
    else:
        print("[+] Strong audio signal detected! Microphone is capturing clearly.")

    # Transcribe via Deepgram if configured
    if cfg.is_deepgram_configured():
        print("\n[*] Sending audio to Deepgram Nova-2...")
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
                timeout=25.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                transcript = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                print(f"[+] DEEPGRAM TRANSCRIPT: \"{transcript}\"")

                if transcript:
                    print("\n[*] Sending transcript to Grammarian engine...")
                    engine = GrammarianEngine()
                    issues = engine.check_text_sync(transcript)
                    print(f"[+] Identified Spoken Grammar Issues: {len(issues)}")
                    for idx, issue in enumerate(issues):
                        print(f"    Issue #{idx+1}: {issue.rule_id} -> {issue.message} | Suggestions: {issue.suggestions}")
                else:
                    print("[!] Deepgram returned empty transcript (no speech detected in audio).")
            else:
                print(f"[!] Deepgram HTTP error: {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"[!] Network error calling Deepgram: {e}")

if __name__ == "__main__":
    main()
