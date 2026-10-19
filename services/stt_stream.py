"""
Speech-to-Text Stream Manager for AI Speech Evaluator.
Integrates Deepgram STT (live streaming and pre-recorded chunking with filler_words=true).
Buffers recorded audio from the microphone and guarantees transcription via Deepgram's
Nova-2 API, extracting word-level timestamps, vocalized pauses, and verbal crutches.
"""

import io
import json
import logging
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional
import requests

from services.ah_counter import AhCounter
from services.grammarian import GrammarianEngine

logger = logging.getLogger("speech_evaluator.stt")


class STTStreamManager:
    """
    Manages audio capture forwarding to Deepgram STT.
    Supports both live streaming and automatic audio buffer transcription,
    ensuring speech is transcribed with word-level filler words and timestamps.
    """

    def __init__(
        self,
        api_key: str,
        ah_counter: AhCounter,
        grammarian: GrammarianEngine,
        sample_rate: int = 16000,
        channels: int = 1,
        simulate: bool = False,
    ):
        self.api_key = api_key
        self.ah_counter = ah_counter
        self.grammarian = grammarian
        self.sample_rate = sample_rate
        self.channels = channels
        self.simulate = simulate or not api_key

        self._lock = threading.Lock()
        self._is_connected = False
        self._is_active = False
        self._audio_buffer = bytearray()
        self._transcript_chunks: List[str] = []
        self._all_words: List[Dict] = []
        self._connection = None

        if self.simulate:
            logger.info("[STT] Simulation / Mock mode active for Deepgram STT.")

    def reset(self) -> None:
        """Reset session audio buffer and transcripts."""
        with self._lock:
            self._audio_buffer.clear()
            self._transcript_chunks.clear()
            self._all_words.clear()
        self.ah_counter.reset()
        self.grammarian.reset()
        logger.debug("[STT] State reset for new speech session.")

    def start_session(self) -> bool:
        """Initialize session and attempt live Deepgram connection if SDK available."""
        with self._lock:
            if self._is_active:
                return True
            self._is_active = True

        self.reset()

        if self.simulate:
            logger.info("[STT SIM] Started simulated STT session.")
            self._is_connected = True
            return True

        # Attempt live streaming via deepgram-sdk if installed and functional
        try:
            import deepgram
            # Try v3 client
            if hasattr(deepgram, "DeepgramClient"):
                DeepgramClient = deepgram.DeepgramClient
                try:
                    from deepgram.clients.live.v1 import LiveOptions, LiveTranscriptionEvents
                except Exception:
                    LiveOptions = getattr(deepgram, "LiveOptions", None)
                    LiveTranscriptionEvents = getattr(deepgram, "LiveTranscriptionEvents", None)

                if LiveOptions and LiveTranscriptionEvents:
                    deepgram_client = DeepgramClient(self.api_key)
                    self._connection = deepgram_client.listen.websocket.v("1")

                    def on_open(conn, *args, **kwargs):
                        logger.info("[STT] Deepgram WebSocket connection opened.")
                        self._is_connected = True

                    def on_message(conn, result, *args, **kwargs):
                        self._handle_transcript_result(result)

                    def on_error(conn, error, *args, **kwargs):
                        logger.warning(f"[STT] Deepgram live stream notice: {error}")

                    def on_close(conn, *args, **kwargs):
                        self._is_connected = False

                    self._connection.on(LiveTranscriptionEvents.Open, on_open)
                    self._connection.on(LiveTranscriptionEvents.Transcript, on_message)
                    self._connection.on(LiveTranscriptionEvents.Error, on_error)
                    self._connection.on(LiveTranscriptionEvents.Close, on_close)

                    options = LiveOptions(
                        model="nova-2",
                        language="en-US",
                        smart_format=True,
                        filler_words=True,
                        punctuate=True,
                        encoding="linear16",
                        channels=self.channels,
                        sample_rate=self.sample_rate,
                        interim_results=False,
                    )
                    try:
                        self._connection.start(options)
                        self._is_connected = True
                        logger.info("[STT] Live Deepgram stream started successfully.")
                        return True
                    except Exception as ex:
                        logger.debug(f"[STT] Live stream start exception: {ex}")
        except Exception as e:
            logger.debug(f"[STT] Live SDK connection skipped ({e}). Audio buffer fallback active.")

        # If live WebSocket was not initialized, audio buffer transcription will handle it at switch OFF
        self._is_connected = False
        return True

    def send_audio(self, audio_data: bytes) -> None:
        """Record PCM audio bytes into session buffer and forward to live stream if connected."""
        if not self._is_active or not audio_data:
            return

        with self._lock:
            self._audio_buffer.extend(audio_data)

        if self._connection and self._is_connected and not self.simulate:
            try:
                self._connection.send(audio_data)
            except Exception as e:
                logger.debug(f"[STT] Live audio chunk send error: {e}")

    def stop_session(self) -> None:
        """Stop session, finalize live connection, and transcribe audio buffer if needed."""
        with self._lock:
            self._is_active = False

        if self._connection and self._is_connected:
            try:
                self._connection.finish()
            except Exception as e:
                logger.debug(f"[STT] Live connection finish: {e}")
            finally:
                self._is_connected = False
                self._connection = None

        # Check if live stream already produced transcripts
        with self._lock:
            has_transcript = bool(self._transcript_chunks)
            buffer_len = len(self._audio_buffer)

        # If live stream didn't produce transcript, transcribe captured audio buffer via Nova-2 REST API
        if not has_transcript and buffer_len > 1000 and self.api_key and not self.simulate:
            logger.info(f"[STT] Transcribing {buffer_len} audio bytes via Deepgram Nova-2 REST API...")
            self._transcribe_audio_buffer_rest()

        logger.info("[STT] Session stopped.")

    def _transcribe_audio_buffer_rest(self) -> None:
        """Transcribe audio buffer using Deepgram Nova-2 REST API with filler_words=true."""
        with self._lock:
            pcm_data = bytes(self._audio_buffer)

        if not pcm_data:
            return

        # Check audio volume before sending
        from hardware.audio_input import AudioCapture
        rms_db = AudioCapture.calculate_rms_db(pcm_data)
        logger.info(f"[STT] Audio buffer volume level: {rms_db:.1f} dBFS")
        if rms_db < -50.0:
            logger.warning(
                f"[STT] WARNING: Audio buffer volume is extremely low ({rms_db:.1f} dBFS - near silence). "
                "Ensure the M-305 microphone physical switch is ON and unmuted in 'alsamixer'."
            )

        # Package raw PCM into standard 16-bit WAV
        wav_io = io.BytesIO()
        try:
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(pcm_data)
            wav_bytes = wav_io.getvalue()
        except Exception as e:
            logger.error(f"[STT] Error packaging WAV audio: {e}")
            return

        url = "https://api.deepgram.com/v1/listen"
        params = {
            "model": "nova-2",
            "language": "en-US",
            "smart_format": "true",
            "filler_words": "true",
            "punctuate": "true",
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
            "User-Agent": "AI-Speech-Evaluator/1.0",
        }

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                data=wav_bytes,
                timeout=45.0,
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", {})
                channels = results.get("channels", [])
                if channels:
                    alt = channels[0].get("alternatives", [{}])[0]
                    transcript = alt.get("transcript", "").strip()
                    words = alt.get("words", [])

                    logger.info(f"[STT] Deepgram response: transcript='{transcript}' ({len(words)} words)")

                    if words:
                        self.ah_counter.process_words(words)
                        with self._lock:
                            self._all_words.extend(words)

                    if transcript:
                        with self._lock:
                            self._transcript_chunks.append(transcript)
                        self.grammarian.check_sentence_async(transcript)
                    else:
                        logger.warning(
                            "[STT] Deepgram returned an empty transcript. If you spoke, "
                            "check microphone volume in 'alsamixer' (press F4 -> Space to unmute, Up Arrow to 100%)."
                        )
            else:
                logger.error(f"[STT] Deepgram API returned HTTP {response.status_code}: {response.text[:150]}")
        except Exception as e:
            logger.error(f"[STT] Network error transcribing audio: {e}")

    def _handle_transcript_result(self, result: Any) -> None:
        """Process incoming Deepgram transcript message from live WebSocket."""
        try:
            if hasattr(result, "channel"):
                alternatives = result.channel.alternatives
                is_final = getattr(result, "is_final", True)
            elif isinstance(result, dict):
                channel = result.get("channel", {})
                alternatives = channel.get("alternatives", [])
                is_final = result.get("is_final", True)
            else:
                return

            if not alternatives:
                return

            alt = alternatives[0]
            transcript = getattr(alt, "transcript", "") if hasattr(alt, "transcript") else alt.get("transcript", "")
            raw_words = getattr(alt, "words", []) if hasattr(alt, "words") else alt.get("words", [])

            if not transcript or not transcript.strip():
                return

            words: List[Dict] = []
            for w in raw_words:
                if isinstance(w, dict):
                    words.append(w)
                else:
                    words.append({
                        "word": getattr(w, "word", ""),
                        "start": getattr(w, "start", 0.0),
                        "end": getattr(w, "end", 0.0),
                        "confidence": getattr(w, "confidence", 1.0),
                        "punctuated_word": getattr(w, "punctuated_word", getattr(w, "word", "")),
                    })

            if words:
                self.ah_counter.process_words(words)
                with self._lock:
                    self._all_words.extend(words)

            if is_final:
                with self._lock:
                    self._transcript_chunks.append(transcript.strip())
                self.grammarian.check_sentence_async(transcript.strip())
                logger.info(f"[STT Live Final] \"{transcript.strip()}\"")

        except Exception as e:
            logger.error(f"[STT] Error parsing transcript result: {e}", exc_info=True)

    def feed_simulated_speech(self, text: str, word_delay: float = 0.3) -> None:
        """Helper for testing: simulates Deepgram transcribing a spoken sentence."""
        words_raw = text.split()
        simulated_words = []
        for idx, w in enumerate(words_raw):
            clean = w.strip(".,?!")
            simulated_words.append({
                "word": clean,
                "punctuated_word": w,
                "start": round(idx * word_delay, 2),
                "end": round(idx * word_delay + 0.25, 2),
                "confidence": 0.98,
            })

        self.ah_counter.process_words(simulated_words)
        with self._lock:
            self._transcript_chunks.append(text)
            self._all_words.extend(simulated_words)

        self.grammarian.check_sentence_async(text)

    def get_full_transcript(self) -> str:
        """Return combined full speech transcript."""
        with self._lock:
            return " ".join(self._transcript_chunks).strip()

    def get_all_words(self) -> List[Dict]:
        """Return list of all recognized words with timestamps."""
        with self._lock:
            return list(self._all_words)
