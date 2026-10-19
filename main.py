"""
Main Application Entrypoint for AI Speech Evaluator.
Coordinates:
1. Automatic background spawning of the Streamlit web dashboard (0.0.0.0:8501).
2. Physical 16x2 LCD Timer-Only display:
   - Line 1: Time: MM:SS
   - Line 2: Status messages (Ready..., Recording..., Evaluating..., Done!)
3. Physical toggle switch (GPIO 18) controlling audio recording, timer, and evaluation.
4. Clean shutdown on SIGINT / SIGTERM terminating Streamlit, closing audio, and clearing LCD.
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Optional

from config import AppConfig, load_config
from hardware.audio_input import AudioCapture
from hardware.switch import SwitchController
from lcd_controller import LCDController
from services.ah_counter import AhCounter
from services.grammarian import GrammarianEngine
from services.report_generator import ReportGenerator
from services.stt_stream import STTStreamManager

logger = logging.getLogger("speech_evaluator.main")


class MainSpeechEvaluator:
    """
    Application orchestrator managing the background Streamlit process,
    hardware switch events, and the timer-only LCD updates.
    """

    STATE_READY = "Ready..."
    STATE_RECORDING = "Recording..."
    STATE_EVALUATING = "Evaluating..."
    STATE_DONE = "Done!"

    def __init__(self, config: AppConfig):
        self.config = config
        self._state_lock = threading.Lock()
        self._is_recording = False
        self._is_app_running = False

        # Session metrics
        self._session_id = ""
        self._speech_start_time = 0.0
        self._speech_end_time = 0.0

        # Subprocesses & background threads
        self._streamlit_proc: Optional[subprocess.Popen] = None
        self._lcd_thread: Optional[threading.Thread] = None

        # Core evaluation services
        self.ah_counter = AhCounter()
        self.grammarian = GrammarianEngine(
            api_url=self.config.languagetool_api_url,
            api_key=self.config.languagetool_api_key,
            username=self.config.languagetool_username,
            language=self.config.languagetool_language,
        )
        self.report_generator = ReportGenerator(
            output_dir=self.config.report_output_dir
        )

        # Hardware drivers
        self.lcd = LCDController(
            address=self.config.lcd_i2c_address,
            port=self.config.lcd_i2c_port,
            cols=self.config.lcd_cols,
            rows=self.config.lcd_rows,
            simulate=self.config.simulate_hardware,
        )
        self.audio = AudioCapture(
            device_index=self.config.audio_device_index,
            sample_rate=self.config.audio_sample_rate,
            channels=self.config.audio_channels,
            chunk_size=self.config.audio_chunk_size,
            on_data_callback=self._on_audio_data,
            simulate=self.config.simulate_hardware,
        )

        # Initialize STT stream with actual hardware sample rate
        self.stt_stream = STTStreamManager(
            api_key=self.config.deepgram_api_key,
            ah_counter=self.ah_counter,
            grammarian=self.grammarian,
            sample_rate=self.audio.sample_rate,
            channels=self.config.audio_channels,
            simulate=self.config.simulate_hardware or not self.config.is_deepgram_configured(),
        )
        self.switch = SwitchController(
            gpio_pin=self.config.switch_gpio_pin,
            bounce_time_ms=self.config.switch_bounce_time_ms,
            on_switch_on=self.handle_switch_turned_on,
            on_switch_off=self.handle_switch_turned_off,
            simulate=self.config.simulate_hardware,
        )

    def _on_audio_data(self, pcm_bytes: bytes) -> None:
        """PyAudio data callback: forward bytes directly to STT streaming engine."""
        with self._state_lock:
            if not self._is_recording:
                return
        self.stt_stream.send_audio(pcm_bytes)

    def spawn_streamlit_dashboard(self) -> None:
        """
        Immediately spawn the Streamlit dashboard in a non-blocking background process.
        Listens on 0.0.0.0 so any device on the local network can connect.
        """
        logger.info("[Main] Spawning Streamlit web dashboard in background...")
        dashboard_script = os.path.join(os.path.dirname(__file__), "dashboard.py")

        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_script,
            "--server.headless=true",
            "--server.address=0.0.0.0",
            "--server.port=8501",
        ]

        try:
            self._streamlit_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info(f"[Main] Streamlit dashboard spawned (PID {self._streamlit_proc.pid}). Accessible at http://0.0.0.0:8501")
        except Exception as e:
            logger.error(f"[Main] Failed to spawn Streamlit dashboard: {e}")

    def start(self) -> None:
        """Start the application, dashboard server, and switch monitor."""
        self._is_app_running = True

        # Register OS signal handlers for graceful teardown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("=" * 65)
        logger.info("TOASTMASTERS AI SPEECH EVALUATOR - DUAL ARCHITECTURE")
        logger.info("Physical Interface: 16x2 LCD (Timer-Only) & GPIO 18 Switch")
        logger.info("Evaluation Interface: Streamlit Dashboard (http://0.0.0.0:8501)")
        logger.info("=" * 65)

        # 1. Immediately launch Streamlit dashboard process
        self.spawn_streamlit_dashboard()

        # 2. Initialize LCD in Ready state
        # Line 1: 'Time: 00:00'
        # Line 2: 'Ready...'
        self.lcd.display_timer("00:00", self.STATE_READY)

        # 3. Start switch monitoring thread
        self.switch.start_monitoring()

        # If switch is already ON at boot, begin capture immediately
        if self.switch.is_switch_on():
            logger.info("[Main] Switch is in ON position at boot. Starting capture.")
            self.handle_switch_turned_on()

    def handle_switch_turned_on(self) -> None:
        """
        Switch ON (GPIO.LOW):
        Starts audio capture, resets timers, and begins 1Hz LCD timer refresh.
        Does NOT restart the Streamlit server.
        """
        with self._state_lock:
            if self._is_recording:
                logger.warning("[Main] Switch toggled ON, but session already active.")
                return
            self._is_recording = True
            self._speech_start_time = time.time()
            self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"[Main] >>> SWITCH ON: Started Speech Session [{self._session_id}] <<<")

        # Reset evaluation services
        self.ah_counter.reset()
        self.grammarian.reset()

        # Start audio recording first to negotiate hardware sample rate
        self.audio.start(on_data=self._on_audio_data)
        self.stt_stream.sample_rate = self.audio.sample_rate
        self.stt_stream.start_session()

        # Start 1Hz timer-only LCD update worker
        self._launch_lcd_timer_worker()

    def handle_switch_turned_off(self) -> None:
        """
        Switch OFF (GPIO.HIGH):
        Stops audio capture, updates LCD to 'Evaluating...', finalizes report,
        writes evaluation_report.json for the dashboard, and displays 'Done!'.
        Does NOT restart or affect the Streamlit server.
        """
        with self._state_lock:
            if not self._is_recording:
                return
            self._is_recording = False
            self._speech_end_time = time.time()
            session_id = self._session_id
            start_t = self._speech_start_time
            end_t = self._speech_end_time

        duration = max(0.0, end_t - start_t)
        final_time_str = ReportGenerator.format_duration(duration)

        logger.info(f"[Main] <<< SWITCH OFF: Stopping Speech Session [{session_id}] (Duration: {final_time_str}) >>>")

        # 1. Stop audio input immediately
        self.audio.stop()

        # 2. Update LCD: 'Evaluating...'
        self.lcd.display_timer(final_time_str, self.STATE_EVALUATING)

        # 3. Stop STT session and close stream
        self.stt_stream.sample_rate = self.audio.sample_rate
        self.stt_stream.stop_session()

        # 4. Wait for any in-flight LanguageTool grammar analysis to finish
        self.grammarian.wait_completion(timeout=12.0)

        # 5. Compile full transcript and write evaluation_report.json
        full_transcript = self.stt_stream.get_full_transcript()
        report_path, report_data = self.report_generator.generate(
            session_id=session_id,
            start_time=start_t,
            end_time=end_t,
            full_transcript=full_transcript,
            ah_counter=self.ah_counter,
            grammarian=self.grammarian,
        )

        total_ah = self.ah_counter.get_total_count()
        total_err = self.grammarian.get_error_count()
        score = report_data.get("overall_score", 0.0)

        logger.info(
            f"[Main] Evaluation Finalized: Score={score}, Fillers={total_ah}, Errors={total_err} "
            f"| Dashboard updated via evaluation_report.json"
        )

        # 6. Update LCD: 'Done!'
        # Line 1: 'Time: MM:SS'
        # Line 2: 'Done!'
        self.lcd.display_timer(final_time_str, self.STATE_DONE)

    def _launch_lcd_timer_worker(self) -> None:
        """Launch non-blocking 1Hz timer updater thread."""
        if self._lcd_thread and self._lcd_thread.is_alive():
            return

        self._lcd_thread = threading.Thread(
            target=self._lcd_timer_loop,
            name="LCDTimerWorker",
            daemon=True,
        )
        self._lcd_thread.start()

    def _lcd_timer_loop(self) -> None:
        """
        Background loop refreshing LCD every 1 second:
        Line 1: 'Time: MM:SS'
        Line 2: 'Recording...'
        """
        logger.debug("[Main] LCD timer loop active.")
        while self._is_app_running:
            with self._state_lock:
                recording = self._is_recording
                start_t = self._speech_start_time

            if not recording:
                break

            elapsed = max(0.0, time.time() - start_t)
            time_str = ReportGenerator.format_duration(elapsed)

            # Timer-only display: Line 1: Time, Line 2: Status
            self.lcd.display_timer(time_str, self.STATE_RECORDING)
            time.sleep(1.0)

        logger.debug("[Main] LCD timer loop finished.")

    def _signal_handler(self, sig: int, frame) -> None:
        """Handle SIGINT (Ctrl+C) and SIGTERM cleanly."""
        logger.info(f"\n[Main] Caught signal {sig}. Initiating graceful shutdown...")
        self.shutdown()
        sys.exit(0)

    def shutdown(self) -> None:
        """
        Clean Graceful Shutdown:
        1. Terminate Streamlit subprocess.
        2. Stop switch monitor and audio stream.
        3. Stop STT and close Grammarian.
        4. Clear and blank the physical LCD screen.
        5. Release GPIO resources.
        """
        logger.info("[Main] Shutting down hardware, services, and web dashboard...")
        self._is_app_running = False

        with self._state_lock:
            self._is_recording = False

        # 1. Terminate Streamlit dashboard subprocess cleanly
        if self._streamlit_proc is not None and self._streamlit_proc.poll() is None:
            logger.info(f"[Main] Terminating Streamlit subprocess (PID {self._streamlit_proc.pid})...")
            self._streamlit_proc.terminate()
            try:
                self._streamlit_proc.wait(timeout=3.0)
                logger.info("[Main] Streamlit subprocess terminated successfully.")
            except subprocess.TimeoutExpired:
                logger.warning("[Main] Streamlit did not terminate in time. Killing process...")
                self._streamlit_proc.kill()
            finally:
                self._streamlit_proc = None

        # 2. Stop switch monitoring
        try:
            self.switch.stop_monitoring()
        except Exception as e:
            logger.error(f"[Main] Error stopping switch: {e}")

        # 3. Stop audio stream
        try:
            self.audio.close()
        except Exception as e:
            logger.error(f"[Main] Error closing audio: {e}")

        # 4. Stop STT and Grammarian
        try:
            self.stt_stream.stop_session()
        except Exception as e:
            logger.error(f"[Main] Error stopping STT: {e}")

        try:
            self.grammarian.close()
        except Exception as e:
            logger.error(f"[Main] Error closing grammarian: {e}")

        # 5. Clear and blank LCD screen
        try:
            self.lcd.clear()
            self.lcd.blank()
            self.lcd.close()
        except Exception as e:
            logger.error(f"[Main] Error closing LCD: {e}")

        logger.info("[Main] Graceful shutdown complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Toastmasters AI Speech Evaluator - Timer & Streamlit Dashboard"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Force simulation mode for LCD, Switch, and Audio hardware",
    )
    args = parser.parse_args()

    config = load_config()
    if args.simulate:
        config = AppConfig(
            deepgram_api_key=config.deepgram_api_key,
            languagetool_api_key=config.languagetool_api_key,
            languagetool_username=config.languagetool_username,
            languagetool_api_url=config.languagetool_api_url,
            languagetool_language=config.languagetool_language,
            lcd_i2c_address=config.lcd_i2c_address,
            lcd_i2c_port=config.lcd_i2c_port,
            lcd_cols=config.lcd_cols,
            lcd_rows=config.lcd_rows,
            switch_gpio_pin=config.switch_gpio_pin,
            switch_bounce_time_ms=config.switch_bounce_time_ms,
            audio_device_index=config.audio_device_index,
            audio_sample_rate=config.audio_sample_rate,
            audio_channels=config.audio_channels,
            audio_chunk_size=config.audio_chunk_size,
            log_level=config.log_level,
            report_output_dir=config.report_output_dir,
            simulate_hardware=True,
        )

    app = MainSpeechEvaluator(config)
    app.start()

    # Keep main thread alive awaiting signals
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        app.shutdown()


if __name__ == "__main__":
    main()
