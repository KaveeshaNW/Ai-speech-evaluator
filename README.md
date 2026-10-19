# AI Speech Evaluator for Toastmasters (Raspberry Pi 3)

An embedded Python application designed for Raspberry Pi 3 running Raspberry Pi OS (64-bit) featuring a **dual-interface architecture**:
1. **Physical Timer-Only Display**: Dedicated 16x2 I2C LCD screen showing live speech time (`Time: MM:SS`) and operational state (`Ready...`, `Recording...`, `Evaluating...`, `Done!`).
2. **Interactive Web Dashboard**: Streamlit web application automatically spawned on `0.0.0.0:8501`, accessible over the local network from any smartphone, tablet, or laptop to review the speech score, disfluency timeline, and grammarian report.

---

## Architecture Overview

```
                         +-----------------------------------+
                         |      Physical Toggle Switch       |
                         |      (GPIO 18 <-> GND, PUD_UP)    |
                         +-----------------+-----------------+
                                           |
                                           v
+--------------------------+    +--------------------+    +---------------------------+
| M-305 USB Microphone     |--->|      main.py       |--->| 16x2 I2C LCD (PCF8574)    |
| (PyAudio 16kHz PCM mono) |    | (Core Orchestrator)|    | Line 1: Time: MM:SS       |
+--------------------------+    +----+----------+----+    | Line 2: Status Message    |
                                     |          |         +---------------------------+
                                     |          |
                                     |          +--------> [Spawns Subprocess on Boot]
                                     v                                  |
                   +----------------------------------+                 v
                   | Deepgram STT (filler_words=true) |       +-------------------+
                   | LanguageTool Cloud API           |       |   dashboard.py    |
                   | Generates evaluation_report.json |------>| (Streamlit 8501)  |
                   +----------------------------------+       | Auto-refreshing   |
                                                              +-------------------+
```

---

## Hardware Configuration & Wiring

### Bill of Materials
| Component | Specification | Connection / Interface |
|---|---|---|
| **Host** | Raspberry Pi 3 Model B / B+ | Raspberry Pi OS (64-bit Debian) |
| **Display** | LCM1602A 16x2 Character LCD | PCF8574 I2C Backpack (Default I2C address `0x27`) |
| **Input** | M-305 Microphone | USB Audio Adapter (mono 16-bit PCM @ 16kHz) |
| **Control Switch** | SPST Physical Toggle Switch | GPIO 18 (BCM) with internal pull-up (`GPIO.PUD_UP`) |

### Wiring Pinout Table

```
Raspberry Pi 3 (40-Pin Header)
------------------------------------------------------------
Pin 02  (5V Power)      -------->  LCD Backpack VCC
Pin 06  (Ground)        -------->  LCD Backpack GND
Pin 03  (GPIO 2 / SDA)  -------->  LCD Backpack SDA
Pin 05  (GPIO 3 / SCL)  -------->  LCD Backpack SCL

Pin 12  (GPIO 18 / BCM) -------->  Toggle Switch Terminal A
Pin 14  (Ground)        -------->  Toggle Switch Terminal B

USB Port                -------->  USB Audio Adapter + M-305 Mic
------------------------------------------------------------
```

> **Switch Logic**:
> - **Switch ON (Closed circuit to GND / `GPIO.LOW`)**: Starts audio recording, resets timers, initiates live STT, and starts 1Hz LCD timer refresh. *(Does NOT restart Streamlit).*
> - **Switch OFF (Open circuit / `GPIO.HIGH`)**: Stops audio recording, displays `Evaluating...` on LCD, finalizes STT, queries remaining grammar checks, updates `evaluation_report.json`, and updates LCD to `Done!`.

---

## Project Structure

```
ai-speech-evaluator/
├── .env.example                # Configuration template for API keys and GPIO pins
├── requirements.txt            # Production dependencies (including Streamlit)
├── config.py                   # Configuration loader with type validation
├── lcd_controller.py           # Simplified Timer-Only 16x2 LCD Controller
├── main.py                     # Main application orchestrator & dashboard spawner
├── dashboard.py                # Interactive Streamlit Web Dashboard (0.0.0.0:8501)
├── evaluation_report.json      # Current/latest evaluation report consumed by dashboard
├── ai-speech-evaluator.service # systemd service unit for autostart
├── hardware/
│   ├── __init__.py
│   ├── lcd.py                  # Module forwarder to lcd_controller.py
│   ├── switch.py               # Debounced GPIO 18 switch monitor with callbacks
│   └── audio_input.py          # PyAudio USB audio stream with live VU meter calculation
├── services/
│   ├── __init__.py
│   ├── ah_counter.py           # Ah-Counter and multi-word verbal crutch detector with timestamps
│   ├── grammarian.py           # Asynchronous LanguageTool Cloud API client
│   ├── stt_stream.py           # Deepgram live STT streaming (filler_words=true)
│   └── report_generator.py     # Toastmasters evaluation JSON report builder
├── tests/
│   ├── __init__.py
│   ├── test_hardware.py        # Interactive CLI diagnostic for LCD, Audio VU meter, and Switch
│   └── test_pipeline.py        # Mock-driven unit and integration test suite
└── reports/                    # Historical archive of session JSON reports
```

---

## Raspberry Pi 3 Setup & Installation

### 1. System Packages (on Raspberry Pi OS 64-bit)

```bash
sudo apt update
sudo apt install -y python3-dev python3-venv python3-pip libportaudio2 libportaudio-dev i2c-tools alsa-utils
```

### 2. Enable I2C Interface

1. Run `sudo raspi-config` -> **Interface Options** -> **I2C** -> Enable.
2. Add your user to hardware groups:
   ```bash
   sudo usermod -a -G i2c,gpio,audio $USER
   ```
3. Verify the LCD backpack is detected on I2C bus 1:
   ```bash
   sudo i2cdetect -y 1
   ```

---

## Application Setup

### 1. Virtual Environment & Dependencies

```bash
cd /home/pi/ai-speech-evaluator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Ensure `DEEPGRAM_API_KEY` is set.

---

## Running the Application

### Launch Orchestrator (`main.py`)
```bash
python main.py
```

When `main.py` starts:
1. It **automatically spawns** the Streamlit web dashboard in the background (`http://0.0.0.0:8501`).
2. The LCD displays `Time: 00:00` / `Ready...`.
3. Connecting devices on the local Wi-Fi can open `http://<raspberry-pi-ip>:8501`.
4. When you toggle the switch ON, the timer starts ticking `Time: MM:SS` / `Recording...`.
5. When you toggle the switch OFF, the LCD transitions to `Evaluating...`, writes `evaluation_report.json`, and settles on `Done!`.
6. The web dashboard detects the new report and updates automatically within 3 seconds.
7. Pressing **Ctrl+C** triggers a clean shutdown: terminates the Streamlit subprocess, closes audio streams, blanks the LCD screen, and releases GPIO.

### Running with Simulated Hardware (Laptop Development)
```bash
python main.py --simulate
```

---

## Web Dashboard Features (`dashboard.py`)

Access via web browser at `http://<raspberry-pi-ip>:8501`:

- **Overall Speech Score Card**: Score out of 100 with Toastmasters grade badge (`A Distinguished`, `B Proficient`, etc.).
- **Summary Metrics Grid**: Speech Duration, Words Per Minute (WPM) with pacing badge, Total Fillers, and Grammar Issues.
- **Disfluency Breakdown**:
  - Vocalized pauses ("ah", "um", "er", "uh") vs. verbal crutches ("like", "you know", "actually", "basically", "so").
  - Frequency distribution ranking.
  - **Exact Timeline Table**: Chronological log of each filler word with timestamp (`MM:SS`), category tag, and confidence score.
- **Grammarian Report**:
  - Full speech transcript with highlighted error spans.
  - Interactive accordions with rule ID, message explanation, and suggested corrections.
- **Auto-Refresh**: Automatically polls every 3 seconds so the dashboard updates as soon as the speaker finishes.

---

## Hardware Diagnostics & Tests

```bash
# Run interactive hardware diagnostic tool
python tests/test_hardware.py --all

# Run mock-driven unit/pipeline test suite (offline)
python -m unittest tests/test_pipeline.py
```

---

## Autostart with systemd

```bash
sudo cp ai-speech-evaluator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-speech-evaluator.service
sudo systemctl start ai-speech-evaluator.service
```
