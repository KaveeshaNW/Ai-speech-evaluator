"""
Grammarian Engine for AI Speech Evaluator.
Asynchronously sends transcribed sentences to the LanguageTool Cloud API
(https://api.languagetoolplus.com/v2/check), extracts grammatical and stylistic errors,
provides replacement suggestions, and maintains real-time error counts for LCD updates.
Handles automatic chunking to respect LanguageTool free tier request limits (1,500 chars).
"""

import concurrent.futures
import hashlib
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("speech_evaluator.grammarian")


@dataclass
class GrammarIssue:
    """Represents a single grammar/style issue detected by LanguageTool."""
    sentence: str
    message: str
    rule_id: str
    rule_description: str
    issue_type: str
    offset: int
    length: int
    context_text: str
    context_offset: int
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GrammarianEngine:
    """
    Thread-safe, non-blocking client for LanguageTool Cloud API.
    Uses a worker thread pool to submit sentences in the background,
    preventing any latency or blocking on the main audio or STT loop.
    Supports intelligent sentence-based chunking for speeches of any length.
    """

    def __init__(
        self,
        api_url: str = "https://api.languagetoolplus.com/v2/check",
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        language: str = "en-US",
        max_workers: int = 2,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.username = username
        self.language = language

        self._lock = threading.Lock()
        self._issues: List[GrammarIssue] = []
        self._processed_hashes: set[str] = set()
        self._active_futures: List[concurrent.futures.Future] = []
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="GrammarianWorker",
        )
        self._session = requests.Session()

    def reset(self) -> None:
        """Reset state for a new speech session."""
        with self._lock:
            self._issues.clear()
            self._processed_hashes.clear()
            self._active_futures.clear()
            logger.debug("[Grammarian] Reset state for new session.")

    @staticmethod
    def chunk_text(text: str, max_chars: int = 1000) -> List[str]:
        """
        Split text into chunks of at most max_chars, respecting sentence
        boundaries and word boundaries to comply with LanguageTool's free tier
        limit (1500 chars) while preserving grammatical context.
        """
        if not text or not text.strip():
            return []
        text = text.strip()
        if len(text) <= max_chars:
            return [text]

        # Split on sentence boundaries (. ! ?) followed by whitespace
        raw_sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences: List[str] = []
        for s in raw_sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) <= max_chars:
                sentences.append(s)
            else:
                # Individual sentence exceeds max_chars (e.g. continuous run-on speech)
                # Split along clause or whitespace boundaries
                words = s.split(" ")
                cur_clause: List[str] = []
                cur_len = 0
                for w in words:
                    if cur_len + len(w) + 1 > max_chars and cur_clause:
                        sentences.append(" ".join(cur_clause))
                        cur_clause = [w]
                        cur_len = len(w)
                    else:
                        cur_clause.append(w)
                        cur_len += len(w) + 1
                if cur_clause:
                    sentences.append(" ".join(cur_clause))

        # Group sentences into chunks <= max_chars
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for s in sentences:
            added_len = len(s) + (1 if current_chunk else 0)
            if current_len + added_len <= max_chars:
                current_chunk.append(s)
                current_len += added_len
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [s]
                current_len = len(s)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def check_sentence_async(self, sentence: str) -> None:
        """
        Asynchronously queue text for LanguageTool analysis.
        Automatically breaks long transcripts into chunks <= 1000 chars
        so that LanguageTool HTTP 413 limits are never exceeded.
        Returns immediately.
        """
        clean_sentence = sentence.strip()
        if not clean_sentence or len(clean_sentence) < 4:
            return

        chunks = self.chunk_text(clean_sentence, max_chars=1000)
        for chunk in chunks:
            chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            with self._lock:
                if chunk_hash in self._processed_hashes:
                    continue
                self._processed_hashes.add(chunk_hash)

            fut = self._executor.submit(self._analyze_worker, chunk)
            with self._lock:
                self._active_futures.append(fut)

    def wait_completion(self, timeout: float = 12.0) -> None:
        """
        Wait for all queued LanguageTool analysis requests to finish.
        Ensures all chunks of a speech are evaluated before report generation.
        """
        with self._lock:
            futures = list(self._active_futures)
        if not futures:
            return

        logger.info(f"[Grammarian] Awaiting completion of {len(futures)} analysis task(s)...")
        done, not_done = concurrent.futures.wait(futures, timeout=timeout)
        if not_done:
            logger.warning(
                f"[Grammarian] {len(not_done)} tasks did not finish within {timeout}s timeout."
            )
        else:
            logger.info(f"[Grammarian] All {len(done)} grammar analysis tasks completed.")
        with self._lock:
            self._active_futures = [f for f in self._active_futures if not f.done()]

    def _analyze_worker(self, chunk: str) -> None:
        """Worker method running inside ThreadPoolExecutor for a single chunk."""
        try:
            issues = self._send_single_request(chunk)
            if issues:
                with self._lock:
                    self._issues.extend(issues)
                logger.info(
                    f"[Grammarian] Detected {len(issues)} issue(s) in: '{chunk[:40]}...' "
                    f"| Total Errors: {self.get_error_count()}"
                )
        except Exception as e:
            logger.error(f"[Grammarian] Error processing chunk '{chunk[:30]}': {e}")

    def _send_single_request(self, text: str) -> List[GrammarIssue]:
        """Send a single chunk of text (<= 1500 chars) to LanguageTool Cloud API."""
        if not text or not text.strip():
            return []

        payload = {
            "text": text,
            "language": self.language,
        }

        if self.api_key:
            payload["apiKey"] = self.api_key
        if self.username:
            payload["username"] = self.username

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "AI-Speech-Evaluator/1.0 (Raspberry Pi Toastmasters Assistant)",
        }

        for attempt in range(2):
            try:
                response = self._session.post(
                    self.api_url,
                    data=payload,
                    headers=headers,
                    timeout=8.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_languagetool_response(text, data)
                elif response.status_code == 429:
                    logger.warning("[Grammarian] LanguageTool HTTP 429 rate limit. Retrying in 1.5s...")
                    time.sleep(1.5)
                    continue
                else:
                    logger.warning(
                        f"[Grammarian] LanguageTool HTTP {response.status_code}: {response.text[:120]}"
                    )
                    return []

            except requests.exceptions.Timeout:
                logger.warning("[Grammarian] LanguageTool API timed out (8s limit).")
                return []
            except requests.exceptions.RequestException as e:
                logger.error(f"[Grammarian] Network error calling LanguageTool: {e}")
                return []
            except Exception as e:
                logger.error(f"[Grammarian] Unexpected parsing error: {e}")
                return []

        return []

    def check_text_sync(self, text: str) -> List[GrammarIssue]:
        """
        Synchronously send text to LanguageTool API and return parsed issues.
        Automatically chunks text into pieces <= 1000 characters to comply
        with LanguageTool's free tier request limit.
        """
        if not text or not text.strip():
            return []

        chunks = self.chunk_text(text, max_chars=1000)
        all_issues: List[GrammarIssue] = []
        for i, chunk in enumerate(chunks):
            issues = self._send_single_request(chunk)
            all_issues.extend(issues)
            if i < len(chunks) - 1:
                time.sleep(0.2)

        return all_issues

    def _parse_languagetool_response(self, original_text: str, data: Dict[str, Any]) -> List[GrammarIssue]:
        """Parse the JSON response from LanguageTool Cloud API."""
        issues: List[GrammarIssue] = []
        matches = data.get("matches", [])

        for match in matches:
            rule = match.get("rule", {})
            rule_id = rule.get("id", "UNKNOWN_RULE")
            rule_desc = rule.get("description", "")
            issue_type = rule.get("issueType", "grammar")
            message = match.get("message", "")
            offset = int(match.get("offset", 0))
            length = int(match.get("length", 0))

            context = match.get("context", {})
            context_text = context.get("text", "")
            context_offset = int(context.get("offset", 0))

            # Extract replacement suggestions (take up to top 3)
            raw_replacements = match.get("replacements", [])
            suggestions = [r.get("value", "") for r in raw_replacements[:3] if r.get("value")]

            issue = GrammarIssue(
                sentence=original_text,
                message=message,
                rule_id=rule_id,
                rule_description=rule_desc,
                issue_type=issue_type,
                offset=offset,
                length=length,
                context_text=context_text,
                context_offset=context_offset,
                suggestions=suggestions,
            )
            issues.append(issue)

        return issues

    def get_error_count(self) -> int:
        """Thread-safe count of all detected grammar errors."""
        with self._lock:
            return len(self._issues)

    def get_issues(self) -> List[Dict[str, Any]]:
        """Return list of all detected issues as dictionaries."""
        with self._lock:
            return [issue.to_dict() for issue in self._issues]

    def close(self) -> None:
        """Shutdown thread pool executor and HTTP session."""
        self._executor.shutdown(wait=False)
        self._session.close()
        logger.info("[Grammarian] Shutdown executor and closed session.")
