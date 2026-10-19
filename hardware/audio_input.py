"""
Audio Input Stream Manager for AI Speech Evaluator.
Handles USB microphone audio capture using PyAudio, streaming chunks to
Deepgram STT, computing real-time RMS levels, and device discovery.
"""

import logging
import math
import struct
import threading
import time
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger("speech_evaluator.audio")


class AudioCapture:
    """
    Thread-safe PyAudio input stream manager.
    Streams 16-bit PCM mono audio at 16kHz to registered consumers.
    """

    def __init__(
        self,
        device_index: int = -1,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        on_data_callback: Optional[Callable[[bytes], None]] = None,
        simulate: bool = False,
    ):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.on_data_callback = on_data_callback
        self.simulate = simulate

        self._lock = threading.Lock()
        self._is_capturing = False
        self._thread: Optional[threading.Thread] = None
        self._pyaudio_instance = None
        self._stream = None
        self._actual_device_index = device_index

        self._init_audio_system()

    def _init_audio_system(self) -> None:
        """Initialize PyAudio instance and resolve device index."""
        if self.simulate:
            logger.info("[Audio] Simulation mode active. Generating synthetic audio chunks.")
            return

        try:
            import pyaudio

            self._pyaudio_instance = pyaudio.PyAudio()
            self._actual_device_index = self._resolve_device_index()
            logger.info(
                f"[Audio] PyAudio initialized. Resolved device index: {self._actual_device_index} "
                f"({self.sample_rate}Hz, {self.channels}ch, chunk={self.chunk_size})"
            )
        except Exception as e:
            logger.warning(
                f"[Audio] Failed to initialize PyAudio ({e}). "
                "Falling back to simulated audio mode."
            )
            self.simulate = True
            self._pyaudio_instance = None

    def _resolve_device_index(self) -> int:
        """
        Resolve device index. If device_index is -1, search for 'USB' or 'M-305'
        in device names, or fall back to system default input.
        """
        if self._pyaudio_instance is None:
            return -1

        if self.device_index >= 0:
            return self.device_index

        try:
            default_index = self._pyaudio_instance.get_default_input_device_info().get("index", 0)
        except Exception:
            default_index = 0

        # Scan for USB audio devices
        device_count = self._pyaudio_instance.get_device_count()
        for idx in range(device_count):
            try:
                info = self._pyaudio_instance.get_device_info_by_host_api_device_index(0, idx)
                if info.get("maxInputChannels", 0) > 0:
                    name = info.get("name", "").lower()
                    if "usb" in name or "m-305" in name or "microphone" in name:
                        logger.info(f"[Audio] Auto-detected USB Audio device: [{idx}] {info.get('name')}")
                        return idx
            except Exception:
                continue

        logger.info(f"[Audio] Using default audio input device: index {default_index}")
        return default_index

    @staticmethod
    def list_devices() -> List[Tuple[int, str, int, float]]:
        """
        List all available audio input devices.
        Returns list of tuples: (index, name, max_input_channels, default_sample_rate).
        """
        devices = []
        try:
            import pyaudio

            pa = pyaudio.PyAudio()
            for idx in range(pa.get_device_count()):
                try:
                    info = pa.get_device_info_by_host_api_device_index(0, idx)
                    if info.get("maxInputChannels", 0) > 0:
                        devices.append(
                            (
                                idx,
                                info.get("name", "Unknown"),
                                int(info.get("maxInputChannels", 0)),
                                float(info.get("defaultSampleRate", 0)),
                            )
                        )
                except Exception:
                    continue
            pa.terminate()
        except Exception as e:
            logger.error(f"[Audio] Failed to list devices: {e}")
        return devices

    @staticmethod
    def calculate_rms_db(pcm_data: bytes) -> float:
        """
        Calculate RMS (Root Mean Square) volume level in decibels (dBFS)
        from 16-bit mono signed integer PCM bytes.
        """
        if not pcm_data:
            return -96.0

        count = len(pcm_data) // 2
        if count == 0:
            return -96.0

        # Unpack signed 16-bit integers
        try:
            shorts = struct.unpack(f"{count}h", pcm_data)
            sum_squares = sum(s * s for s in shorts)
            mean_square = sum_squares / count
            if mean_square <= 0:
                return -96.0
            rms = math.sqrt(mean_square)
            # dBFS reference is 32767 for 16-bit audio
            db = 20 * math.log10(max(rms, 1.0) / 32767.0)
            return max(-96.0, db)
        except Exception:
            return -96.0

    def start(self, on_data: Optional[Callable[[bytes], None]] = None) -> None:
        """Start non-blocking audio capture in background thread."""
        with self._lock:
            if self._is_capturing:
                return
            if on_data is not None:
                self.on_data_callback = on_data
            self._is_capturing = True

            self._thread = threading.Thread(
                target=self._capture_worker,
                name="AudioCaptureThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("[Audio] Capture thread started.")

    def stop(self) -> None:
        """Stop audio capture."""
        with self._lock:
            if not self._is_capturing:
                return
            self._is_capturing = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception as e:
                    logger.error(f"[Audio] Error closing audio stream: {e}")
                finally:
                    self._stream = None

        logger.info("[Audio] Capture stopped.")

    def _capture_worker(self) -> None:
        """Continuous audio chunk acquisition loop."""
        import pyaudio

        if not self.simulate and self._pyaudio_instance is not None:
            # USB audio dongles often only support 44100Hz or 48000Hz in ALSA hw mode
            rates_to_try = [self.sample_rate]
            for candidate in [44100, 48000, 16000, 8000]:
                if candidate not in rates_to_try:
                    rates_to_try.append(candidate)

            opened = False
            for rate in rates_to_try:
                try:
                    self._stream = self._pyaudio_instance.open(
                        format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=rate,
                        input=True,
                        input_device_index=self._actual_device_index if self._actual_device_index >= 0 else None,
                        frames_per_buffer=self.chunk_size,
                    )
                    self.sample_rate = rate
                    opened = True
                    logger.info(f"[Audio] PyAudio stream opened successfully at {rate}Hz ({self.channels}ch, chunk={self.chunk_size}).")
                    break
                except Exception as ex:
                    logger.debug(f"[Audio] Rate {rate}Hz failed on device {self._actual_device_index}: {ex}")

            if not opened:
                logger.error("[Audio] Failed to open PyAudio input stream on all candidate sample rates. Switching to simulation.")
                self.simulate = True

        # Main acquisition loop
        while True:
            with self._lock:
                if not self._is_capturing:
                    break

            try:
                if self.simulate or self._stream is None:
                    # Synthetic silence chunk (1024 16-bit zeros ~ 64ms)
                    chunk_duration = self.chunk_size / self.sample_rate
                    time.sleep(chunk_duration)
                    data = b"\x00" * (self.chunk_size * 2 * self.channels)
                else:
                    data = self._stream.read(self.chunk_size, exception_on_overflow=False)

                if self.on_data_callback and data:
                    self.on_data_callback(data)

            except Exception as e:
                logger.error(f"[Audio] Error reading audio stream: {e}")
                time.sleep(0.05)

    def close(self) -> None:
        """Cleanly terminate PyAudio instance."""
        self.stop()
        with self._lock:
            if self._pyaudio_instance is not None:
                try:
                    self._pyaudio_instance.terminate()
                except Exception as e:
                    logger.error(f"[Audio] Error terminating PyAudio: {e}")
                finally:
                    self._pyaudio_instance = None
            logger.info("[Audio] PyAudio terminated cleanly.")
