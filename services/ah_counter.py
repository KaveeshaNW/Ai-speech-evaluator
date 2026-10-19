"""
Ah-Counter & Verbal Crutch Analysis Engine for AI Speech Evaluator.
Detects vocalized pauses ("ah", "um", "er", "uh") and verbal crutches
("like", "you know", "actually", "basically", "so"), tracks word frequencies,
and records exact start-time timestamps for speech timeline visualization.
"""

import logging
import re
import string
import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("speech_evaluator.ah_counter")


@dataclass
class FillerEvent:
    """Represents a single detected filler occurrence on the speech timeline."""
    word: str
    category: str  # 'vocalized_pause' or 'verbal_crutch'
    start_time: float  # Start time in seconds relative to speech start
    end_time: float    # End time in seconds relative to speech start
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AhCounter:
    """
    Thread-safe detector and accumulator of Toastmasters vocalized pauses
    and verbal crutches with exact timeline timestamps.
    """

    # Primary Toastmasters Vocalized Pauses
    VOCALIZED_PAUSES = {
        "ah", "um", "er", "uh", "ahm", "eh", "mm", "erm", "err", "umm", "ahh"
    }

    # Primary Toastmasters Single-word Verbal Crutches
    SINGLE_VERBAL_CRUTCHES = {
        "like", "actually", "basically", "literally", "seriously",
        "honestly", "right", "well"
    }

    # Multi-word Verbal Crutches
    MULTI_VERBAL_CRUTCHES = [
        ("you", "know"),
        ("i", "mean"),
        ("kind", "of"),
        ("sort", "of"),
        ("you", "see"),
        ("as", "well"),
    ]

    def __init__(self):
        self._lock = threading.Lock()
        self._events: List[FillerEvent] = []
        self._counts: Dict[str, int] = {}
        self._vocalized_pause_count: int = 0
        self._verbal_crutch_count: int = 0

    def reset(self) -> None:
        """Reset all counters and timeline events for a new speech session."""
        with self._lock:
            self._events.clear()
            self._counts.clear()
            self._vocalized_pause_count = 0
            self._verbal_crutch_count = 0
            logger.debug("[AhCounter] Reset state for new speech session.")

    @staticmethod
    def clean_token(token: str) -> str:
        """Strip punctuation and lowercase a word token."""
        if not token:
            return ""
        # Strip trailing/leading punctuation
        cleaned = token.strip(string.punctuation + " \t\r\n").lower()
        return cleaned

    def _is_crutch_so(self, words: List[Dict[str, Any]], idx: int) -> bool:
        """
        Context-aware evaluation for 'so'.
        In Toastmasters, 'so' used at sentence beginnings or standalone pauses
        is a crutch. Conjunctions like 'so that' or intensive 'so much', 'so fast'
        are natural grammar.
        """
        current_word = self.clean_token(words[idx].get("word", ""))
        if current_word != "so":
            return False

        # If at the very beginning of transcript
        if idx == 0:
            return True

        # Check previous word punctuation (if previous word ended with . ? !)
        prev_raw = words[idx - 1].get("punctuated_word", words[idx - 1].get("word", ""))
        if any(prev_raw.endswith(p) for p in [".", "?", "!", "..."]):
            return True

        # Check if followed by intensifier / conjunction
        if idx + 1 < len(words):
            next_token = self.clean_token(words[idx + 1].get("word", ""))
            if next_token in {"that", "much", "many", "far", "long", "fast", "well", "great", "good"}:
                return False

        # Check if followed by pause (>0.4s between 'so' and next word)
        if idx + 1 < len(words):
            curr_end = float(words[idx].get("end", 0.0))
            next_start = float(words[idx + 1].get("start", 0.0))
            if next_start - curr_end > 0.4:
                return True

        return False

    def process_words(self, words: List[Dict[str, Any]]) -> List[FillerEvent]:
        """
        Process a list of word dictionaries from Deepgram STT stream.
        Each word dict expected to have:
            - word (str)
            - start (float)
            - end (float)
            - confidence (float, optional)
            - punctuated_word (str, optional)
        """
        if not words:
            return []

        detected_events: List[FillerEvent] = []
        i = 0
        n = len(words)

        while i < n:
            word_obj = words[i]
            token = self.clean_token(word_obj.get("word", ""))
            start_t = float(word_obj.get("start", 0.0))
            end_t = float(word_obj.get("end", start_t))
            conf = float(word_obj.get("confidence", 1.0))

            if not token:
                i += 1
                continue

            # 1. Check Multi-word crutches (e.g. "you know", "i mean")
            matched_multi = False
            for multi in self.MULTI_VERBAL_CRUTCHES:
                m_len = len(multi)
                if i + m_len <= n:
                    tokens_slice = [self.clean_token(words[i + k].get("word", "")) for k in range(m_len)]
                    if tokens_slice == list(multi):
                        phrase = " ".join(multi)
                        multi_end_t = float(words[i + m_len - 1].get("end", end_t))
                        event = FillerEvent(
                            word=phrase,
                            category="verbal_crutch",
                            start_time=round(start_t, 2),
                            end_time=round(multi_end_t, 2),
                            confidence=round(conf, 3),
                        )
                        detected_events.append(event)
                        i += m_len
                        matched_multi = True
                        break

            if matched_multi:
                continue

            # 2. Check Vocalized Pauses ("ah", "um", "er", "uh", etc.)
            if token in self.VOCALIZED_PAUSES:
                event = FillerEvent(
                    word=token,
                    category="vocalized_pause",
                    start_time=round(start_t, 2),
                    end_time=round(end_t, 2),
                    confidence=round(conf, 3),
                )
                detected_events.append(event)
                i += 1
                continue

            # 3. Check Context-aware "so"
            if self._is_crutch_so(words, i):
                event = FillerEvent(
                    word="so",
                    category="verbal_crutch",
                    start_time=round(start_t, 2),
                    end_time=round(end_t, 2),
                    confidence=round(conf, 3),
                )
                detected_events.append(event)
                i += 1
                continue

            # 4. Check Single-word Verbal Crutches ("like", "actually", "basically", etc.)
            if token in self.SINGLE_VERBAL_CRUTCHES:
                event = FillerEvent(
                    word=token,
                    category="verbal_crutch",
                    start_time=round(start_t, 2),
                    end_time=round(end_t, 2),
                    confidence=round(conf, 3),
                )
                detected_events.append(event)
                i += 1
                continue

            i += 1

        # Atomically update global totals
        with self._lock:
            for ev in detected_events:
                self._events.append(ev)
                self._counts[ev.word] = self._counts.get(ev.word, 0) + 1
                if ev.category == "vocalized_pause":
                    self._vocalized_pause_count += 1
                else:
                    self._verbal_crutch_count += 1

        if detected_events:
            logger.info(
                f"[AhCounter] Detected {len(detected_events)} filler(s): "
                f"{[e.word for e in detected_events]} | Running Total: {self.get_total_count()}"
            )

        return detected_events

    def process_text_string(self, text: str, base_time: float = 0.0) -> List[FillerEvent]:
        """
        Convenience method to parse plain text sentences (e.g. for testing
        or chunked transcripts where word timings are synthetic).
        """
        raw_words = text.split()
        simulated_words = []
        curr_time = base_time
        for w in raw_words:
            simulated_words.append({
                "word": w,
                "punctuated_word": w,
                "start": curr_time,
                "end": curr_time + 0.3,
                "confidence": 0.95,
            })
            curr_time += 0.4
        return self.process_words(simulated_words)

    def get_total_count(self) -> int:
        """Return combined total of all vocalized pauses and verbal crutches."""
        with self._lock:
            return self._vocalized_pause_count + self._verbal_crutch_count

    def get_vocalized_pause_count(self) -> int:
        """Return count of pure vocalized pauses ('ah', 'um', etc.)."""
        with self._lock:
            return self._vocalized_pause_count

    def get_verbal_crutch_count(self) -> int:
        """Return count of verbal crutches ('like', 'you know', etc.)."""
        with self._lock:
            return self._verbal_crutch_count

    def get_breakdown(self) -> Dict[str, int]:
        """Return copy of per-word count dictionary."""
        with self._lock:
            return dict(self._counts)

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Return timeline list of detected events as dicts."""
        with self._lock:
            return [e.to_dict() for e in self._events]
