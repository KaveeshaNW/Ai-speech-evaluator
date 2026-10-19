"""
Speech-to-Text Stream Manager for AI Speech Evaluator.
Integrates Deepgram Python SDK (live streaming or chunked processing with filler_words=true),
dispatches word objects with timestamps to AhCounter, and forwards final sentences
to the Grammarian engine.
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from services.ah_counter import AhCounter
from services.grammarian import GrammarianEngine

logger = logging.getLogger("speech_evaluator.stt")


class STTStreamManager:
    """
    Manages audio forwarding to Deepgram STT, consumes live transcription events,
    dispatches word-level events to AhCounter, and coordinates sentence checks
    with GrammarianEngine.
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
        self._transcript_chunks: List[str] = []
        self._all_words: List[Dict] = []
        self._live_client = None
        self._connection = None

        if self.simulate:
            logger.info("[STT] Simulation / Mock mode active for Deepgram STT.")

    def reset(self) -> None:
        """Reset session transcripts."""
        with self._lock:
            self._transcript_chunks.clear()
            self._all_words.clear()
        self.ah_counter.reset()
        self.grammarian.reset()
        logger.debug("[STT] State reset for new speech session.")

    def start_session(self) -> bool:
        """Initialize live Deepgram streaming connection."""
        with self._lock:
            if self._is_active:
                return True
            self._is_active = True

        self.reset()

        if self.simulate:
            logger.info("[STT SIM] Started simulated STT session.")
            self._is_connected = True
            return True

        try:
            from deepgram import (
                DeepgramClient,
                LiveOptions,
                LiveTranscriptionEvents,
            )

            try:
                from deepgram import DeepgramClientOptions
                client_config = DeepgramClientOptions(options={"keepalive": "true"})
                deepgram_client = DeepgramClient(self.api_key, client_config)
            except Exception:
                deepgram_client = DeepgramClient(self.api_key)

            self._connection = deepgram_client.listen.websocket.v("1")

            # Register event handlers
            def on_open(conn, *args, **kwargs):
                logger.info("[STT] Deepgram WebSocket connection opened.")
                self._is_connected = True

            def on_message(conn, result, *args, **kwargs):
                self._handle_transcript_result(result)

            def on_error(conn, error, *args, **kwargs):
                logger.error(f"[STT] Deepgram error: {error}")

            def on_close(conn, *args, **kwargs):
                logger.info("[STT] Deepgram connection closed.")
                self._is_connected = False

            self._connection.on(LiveTranscriptionEvents.Open, on_open)
            self._connection.on(LiveTranscriptionEvents.Transcript, on_message)
            self._connection.on(LiveTranscriptionEvents.Error, on_error)
            self._connection.on(LiveTranscriptionEvents.Close, on_close)

            # Deepgram Live Options with filler_words=True
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

            addons = {"filler_words": "true"}
            if not self._connection.start(options, addons=addons):
                logger.warning("[STT] Deepgram connection start returned False. Falling back to simulation.")
                self.simulate = True
                self._is_connected = True
                return False

            self._is_connected = True
            logger.info("[STT] Live Deepgram stream started with filler_words=true.")
            return True

        except Exception as e:
            logger.warning(
                f"[STT] Could not start live Deepgram stream ({e}). "
                "Switching to simulation mode."
            )
            self.simulate = True
            self._is_connected = True
            return False

    def send_audio(self, audio_data: bytes) -> None:
        """Send PCM audio chunk to Deepgram stream."""
        if not self._is_active:
            return

        if self.simulate:
            return

        if self._connection and self._is_connected:
            try:
                self._connection.send(audio_data)
            except Exception as e:
                logger.error(f"[STT] Failed to send audio chunk: {e}")

    def _handle_transcript_result(self, result: Any) -> None:
        """Process incoming Deepgram transcript message."""
        try:
            # Result can be a Pydantic object or dict
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

            # Normalize word dicts
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
                # 1. Dispatch word-level tokens with exact timestamps to AhCounter
                self.ah_counter.process_words(words)

                with self._lock:
                    self._all_words.extend(words)

            if is_final:
                with self._lock:
                    self._transcript_chunks.append(transcript.strip())

                # 2. Dispatch finalized sentence to Grammarian Engine asynchronously
                self.grammarian.check_sentence_async(transcript.strip())
                logger.info(f"[STT Final] \"{transcript.strip()}\"")

        except Exception as e:
            logger.error(f"[STT] Error parsing transcript result: {e}", exc_info=True)

    def feed_simulated_speech(self, text: str, word_delay: float = 0.3) -> None:
        """
        Helper for testing: simulates Deepgram transcribing a spoken sentence
        with realistic timestamps, filler words, and punctuation.
        """
        words_raw = text.split()
        simulated_words = []
        base_time = time.time()

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

    def stop_session(self) -> None:
        """Stop current session and close WebSocket connection."""
        with self._lock:
            self._is_active = False

        if self._connection and self._is_connected and not self.simulate:
            try:
                self._connection.finish()
            except Exception as e:
                logger.error(f"[STT] Error finishing Deepgram connection: {e}")
            finally:
                self._is_connected = False
                self._connection = None

        logger.info("[STT] Session stopped.")

    def get_full_transcript(self) -> str:
        """Return combined full speech transcript."""
        with self._lock:
            return " ".join(self._transcript_chunks).strip()

    def get_all_words(self) -> List[Dict]:
        """Return list of all recognized words with timestamps."""
        with self._lock:
            return list(self._all_words)
