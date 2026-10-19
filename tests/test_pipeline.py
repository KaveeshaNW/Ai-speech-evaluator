"""
Mock-driven Unit and Integration Test Suite for AI Speech Evaluator.
Verifies the Ah-Counter, LanguageTool Parser, Report Generator, and State Machine
without requiring physical Raspberry Pi hardware, I2C connections, or live Cloud API keys.

Usage:
    python -m unittest tests/test_pipeline.py
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig
from hardware.lcd import LCDController
from services.ah_counter import AhCounter, FillerEvent
from services.grammarian import GrammarianEngine, GrammarIssue
from services.report_generator import ReportGenerator
from services.stt_stream import STTStreamManager


class TestAhCounter(unittest.TestCase):
    """Test suite for Toastmasters Ah-Counter and Verbal Crutch Analyzer."""

    def setUp(self):
        self.counter = AhCounter()

    def test_single_vocalized_pauses(self):
        """Verify standard vocalized pauses ('ah', 'um', 'er', 'uh')."""
        words = [
            {"word": "Good", "start": 0.0, "end": 0.3, "confidence": 0.99},
            {"word": "evening", "start": 0.4, "end": 0.8, "confidence": 0.99},
            {"word": "um", "start": 1.2, "end": 1.5, "confidence": 0.95},
            {"word": "fellow", "start": 1.6, "end": 2.0, "confidence": 0.99},
            {"word": "Toastmasters", "start": 2.1, "end": 2.8, "confidence": 0.98},
            {"word": "ah", "start": 3.0, "end": 3.4, "confidence": 0.92},
            {"word": "and", "start": 3.5, "end": 3.7, "confidence": 0.99},
            {"word": "er", "start": 4.0, "end": 4.3, "confidence": 0.91},
            {"word": "uh", "start": 4.5, "end": 4.8, "confidence": 0.94},
        ]

        events = self.counter.process_words(words)
        self.assertEqual(len(events), 4)
        self.assertEqual(self.counter.get_total_count(), 4)
        self.assertEqual(self.counter.get_vocalized_pause_count(), 4)
        self.assertEqual(self.counter.get_verbal_crutch_count(), 0)

        # Check breakdown
        breakdown = self.counter.get_breakdown()
        self.assertEqual(breakdown.get("um"), 1)
        self.assertEqual(breakdown.get("ah"), 1)
        self.assertEqual(breakdown.get("er"), 1)
        self.assertEqual(breakdown.get("uh"), 1)

    def test_verbal_crutches_and_multi_word(self):
        """Verify single-word and multi-word verbal crutches ('like', 'you know', 'actually', 'basically')."""
        words = [
            {"word": "I", "start": 0.0, "end": 0.2, "confidence": 0.99},
            {"word": "actually", "start": 0.3, "end": 0.8, "confidence": 0.95},
            {"word": "wanted", "start": 0.9, "end": 1.2, "confidence": 0.99},
            {"word": "to", "start": 1.3, "end": 1.4, "confidence": 0.99},
            {"word": "say", "start": 1.5, "end": 1.8, "confidence": 0.99},
            {"word": "like", "start": 2.0, "end": 2.3, "confidence": 0.93},
            {"word": "that", "start": 2.4, "end": 2.6, "confidence": 0.99},
            {"word": "basically", "start": 2.8, "end": 3.4, "confidence": 0.94},
            {"word": "it", "start": 3.5, "end": 3.7, "confidence": 0.99},
            {"word": "was", "start": 3.8, "end": 4.0, "confidence": 0.99},
            {"word": "you", "start": 4.2, "end": 4.4, "confidence": 0.96},
            {"word": "know", "start": 4.5, "end": 4.8, "confidence": 0.97},
            {"word": "great", "start": 5.0, "end": 5.4, "confidence": 0.99},
        ]

        events = self.counter.process_words(words)
        self.assertEqual(len(events), 4)
        self.assertEqual(self.counter.get_verbal_crutch_count(), 4)
        self.assertEqual(self.counter.get_vocalized_pause_count(), 0)

        # Check multi-word "you know"
        you_know_event = next(e for e in events if e.word == "you know")
        self.assertEqual(you_know_event.start_time, 4.2)
        self.assertEqual(you_know_event.end_time, 4.8)
        self.assertEqual(you_know_event.category, "verbal_crutch")

    def test_punctuation_and_casing(self):
        """Verify tokens with uppercase and trailing punctuation are normalized."""
        words = [
            {"word": "Um...", "start": 0.0, "end": 0.5, "confidence": 0.90},
            {"word": "ACTUALLY,", "start": 0.6, "end": 1.1, "confidence": 0.91},
            {"word": "AH!", "start": 1.2, "end": 1.6, "confidence": 0.92},
        ]
        events = self.counter.process_words(words)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].word, "um")
        self.assertEqual(events[1].word, "actually")
        self.assertEqual(events[2].word, "ah")

    def test_timeline_integrity(self):
        """Verify exact start and end timestamps stored in timeline events."""
        words = [
            {"word": "um", "start": 12.34, "end": 12.89, "confidence": 0.95},
            {"word": "like", "start": 45.67, "end": 46.10, "confidence": 0.92},
        ]
        self.counter.process_words(words)
        timeline = self.counter.get_timeline()
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["start_time"], 12.34)
        self.assertEqual(timeline[0]["end_time"], 12.89)
        self.assertEqual(timeline[1]["start_time"], 45.67)
        self.assertEqual(timeline[1]["end_time"], 46.10)

    def test_reset(self):
        """Verify reset clears all metrics."""
        self.counter.process_text_string("Um ah er like you know")
        self.assertGreater(self.counter.get_total_count(), 0)
        self.counter.reset()
        self.assertEqual(self.counter.get_total_count(), 0)
        self.assertEqual(len(self.counter.get_timeline()), 0)
        self.assertEqual(len(self.counter.get_breakdown()), 0)


class TestGrammarianEngine(unittest.TestCase):
    """Test suite for LanguageTool Cloud API parsing and asynchronous queue."""

    def setUp(self):
        self.grammarian = GrammarianEngine(
            api_url="https://api.languagetoolplus.com/v2/check",
            api_key=None,
        )

    def tearDown(self):
        self.grammarian.close()

    @patch("requests.Session.post")
    def test_successful_languagetool_response(self, mock_post):
        """Verify correct parsing of rule ID, offsets, and suggestions from LanguageTool JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "software": {"name": "LanguageTool"},
            "matches": [
                {
                    "message": "Use 'an' instead of 'a' before vowel sounds.",
                    "shortMessage": "Wrong article",
                    "offset": 7,
                    "length": 1,
                    "context": {
                        "text": "This is a apple.",
                        "offset": 7,
                        "length": 1,
                    },
                    "rule": {
                        "id": "A_OR_AN",
                        "description": "Use of 'a' vs. 'an'",
                        "issueType": "misspelling",
                    },
                    "replacements": [
                        {"value": "an"},
                    ],
                }
            ],
        }
        mock_post.return_value = mock_response

        text = "This is a apple."
        issues = self.grammarian.check_text_sync(text)

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.rule_id, "A_OR_AN")
        self.assertEqual(issue.offset, 7)
        self.assertEqual(issue.length, 1)
        self.assertEqual(issue.suggestions, ["an"])
        self.assertIn("instead of 'a'", issue.message)

    @patch("requests.Session.post")
    def test_api_timeout_graceful_handling(self, mock_post):
        """Verify network timeouts are handled without crashing."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        issues = self.grammarian.check_text_sync("Testing timeout resilience.")
        self.assertEqual(issues, [])
        self.assertEqual(self.grammarian.get_error_count(), 0)

    @patch("requests.Session.post")
    def test_async_sentence_checking_and_deduplication(self, mock_post):
        """Verify async background queue and deduplication of repeated sentences."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "message": "Agreement error.",
                    "offset": 5,
                    "length": 3,
                    "rule": {"id": "SUBJECT_VERB_AGREEMENT"},
                    "replacements": [{"value": "are"}],
                    "context": {"text": "They is here", "offset": 5, "length": 3},
                }
            ]
        }
        mock_post.return_value = mock_response

        # Submit identical sentence multiple times
        self.grammarian.check_sentence_async("They is here.")
        self.grammarian.check_sentence_async("They is here.")

        # Give executor thread a short moment to complete
        time.sleep(0.3)

        # Should only have processed once due to hash deduplication
        self.assertEqual(self.grammarian.get_error_count(), 1)

    def test_chunk_text_under_limit(self):
        """Verify chunk_text splits large text into pieces strictly <= 1000 characters."""
        long_speech = (
            "Good evening fellow Toastmasters and honored guests. "
            "Public speaking is an extraordinary journey that requires vulnerability, preparation, and passion. "
        ) * 40  # ~6,000 characters
        self.assertGreater(len(long_speech), 5000)

        chunks = GrammarianEngine.chunk_text(long_speech, max_chars=1000)
        self.assertGreater(len(chunks), 1)
        for i, chunk in enumerate(chunks):
            self.assertLessEqual(
                len(chunk),
                1000,
                f"Chunk {i} exceeded 1000 chars (was {len(chunk)})",
            )
            self.assertGreater(len(chunk), 0)

    @patch("requests.Session.post")
    def test_large_text_chunking_sync_no_413(self, mock_post):
        """Verify that a 7,000 character transcript is chunked and posted without exceeding limits."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "message": "Stylistic improvement.",
                    "offset": 0,
                    "length": 4,
                    "rule": {"id": "STYLE_RULE"},
                    "replacements": [{"value": "better"}],
                    "context": {"text": "Good evening", "offset": 0, "length": 4},
                }
            ]
        }
        mock_post.return_value = mock_response

        # 7,000 character speech text
        speech_text = "Good evening fellow Toastmasters. This is an inspiring story. " * 115
        self.assertGreater(len(speech_text), 7000)

        issues = self.grammarian.check_text_sync(speech_text)
        # All posted payloads must have text <= 1000 chars
        for call_args in mock_post.call_args_list:
            data = call_args.kwargs.get("data", {})
            sent_text = data.get("text", "")
            self.assertLessEqual(len(sent_text), 1000)

        self.assertGreaterEqual(len(issues), 1)

    @patch("requests.Session.post")
    def test_wait_completion(self, mock_post):
        """Verify wait_completion blocks until all active background tasks finish."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"matches": []}
        mock_post.return_value = mock_response

        self.grammarian.check_sentence_async("Testing completion synchronization.")
        self.grammarian.wait_completion(timeout=5.0)
        self.assertEqual(len(self.grammarian._active_futures), 0)


class TestReportGenerator(unittest.TestCase):
    """Test suite for Toastmasters JSON Evaluation Report generation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.generator = ReportGenerator(output_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_generate_complete_report(self):
        """Verify report structure, calculations (WPM, filler rate), and JSON output."""
        ah_counter = AhCounter()
        words = [
            {"word": "Welcome", "start": 0.0, "end": 0.4},
            {"word": "um", "start": 0.5, "end": 0.8},
            {"word": "Toastmasters", "start": 0.9, "end": 1.5},
            {"word": "like", "start": 1.6, "end": 1.9},
            {"word": "today", "start": 2.0, "end": 2.4},
        ]
        ah_counter.process_words(words)

        grammarian = GrammarianEngine()
        # Mock an issue
        with grammarian._lock:
            grammarian._issues.append(
                GrammarIssue(
                    sentence="Welcome um Toastmasters like today",
                    message="Example grammar note",
                    rule_id="RULE_TEST",
                    rule_description="Test rule",
                    issue_type="grammar",
                    offset=0,
                    length=7,
                    context_text="Welcome",
                    context_offset=0,
                    suggestions=["Greetings"],
                )
            )

        start_time = 1000.0
        end_time = 1060.0  # Exactly 60 seconds (1 minute)
        transcript = "Welcome um Toastmasters like today"

        filepath, data = self.generator.generate(
            session_id="20261019_test",
            start_time=start_time,
            end_time=end_time,
            full_transcript=transcript,
            ah_counter=ah_counter,
            grammarian=grammarian,
        )

        self.assertTrue(os.path.exists(filepath))

        # Validate Timing
        self.assertEqual(data["timing"]["duration_seconds"], 60.0)
        self.assertEqual(data["timing"]["formatted_duration"], "01:00")

        # Validate Transcript & WPM
        self.assertEqual(data["transcript_summary"]["total_words"], 5)
        self.assertEqual(data["transcript_summary"]["words_per_minute"], 5.0)

        # Validate Ah-Counter section
        self.assertEqual(data["ah_counter"]["total_fillers"], 2)
        self.assertEqual(data["ah_counter"]["vocalized_pauses_count"], 1)
        self.assertEqual(data["ah_counter"]["verbal_crutches_count"], 1)
        self.assertEqual(len(data["ah_counter"]["timeline_events"]), 2)

        # Validate Grammarian section
        self.assertEqual(data["grammarian"]["total_errors"], 1)
        self.assertEqual(len(data["grammarian"]["issues"]), 1)

        # Validate Toastmasters Evaluation
        self.assertIn("summary", data["toastmasters_evaluation"])


class TestLCDFormatting(unittest.TestCase):
    """Test LCD Controller string formatting and thread safety for Timer-Only display."""

    def test_timer_formatting_constraints(self):
        """Verify LCD Line 1 (Time: MM:SS) and Line 2 (Status) never exceed 16 characters."""
        lcd = LCDController(simulate=True, cols=16, rows=2)

        # Recording state
        lcd.display_timer(time_str="05:23", status="Recording...")
        self.assertEqual(len(lcd._last_line1), 16)
        self.assertEqual(len(lcd._last_line2), 16)
        self.assertEqual(lcd._last_line1, "Time: 05:23     ")
        self.assertEqual(lcd._last_line2, "Recording...    ")

        # Evaluating state
        lcd.display_timer(time_str="07:15", status="Evaluating...")
        self.assertEqual(len(lcd._last_line1), 16)
        self.assertEqual(len(lcd._last_line2), 16)
        self.assertEqual(lcd._last_line1, "Time: 07:15     ")
        self.assertEqual(lcd._last_line2, "Evaluating...   ")

        # Done state
        lcd.display_timer(time_str="07:15", status="Done!")
        self.assertEqual(lcd._last_line1, "Time: 07:15     ")
        self.assertEqual(lcd._last_line2, "Done!           ")

        lcd.close()


class TestThreadSafety(unittest.TestCase):
    """Test concurrent thread safety across AhCounter and evaluation state."""

    def test_concurrent_ah_counter_increments(self):
        """Run multiple threads pushing words concurrently to AhCounter."""
        counter = AhCounter()
        threads = []

        def worker(word, count):
            for _ in range(count):
                counter.process_words([{"word": word, "start": 0.1, "end": 0.2}])

        # 4 threads adding 50 fillers each = 200 total
        for w in ["ah", "um", "like", "actually"]:
            t = threading.Thread(target=worker, args=(w, 50))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(counter.get_total_count(), 200)
        self.assertEqual(len(counter.get_timeline()), 200)


if __name__ == "__main__":
    unittest.main()
