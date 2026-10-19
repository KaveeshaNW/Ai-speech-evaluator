"""
Grammarian Engine for AI Speech Evaluator.
Asynchronously sends transcribed sentences to the LanguageTool Cloud API
(https://api.languagetoolplus.com/v2/check), extracts grammatical and stylistic errors,
provides replacement suggestions, and maintains real-time error counts for LCD updates.
"""

import concurrent.futures
import hashlib
import logging
import threading
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
            logger.debug("[Grammarian] Reset state for new session.")

    def check_sentence_async(self, sentence: str) -> None:
        """
        Asynchronously queue a sentence for LanguageTool analysis.
        Returns immediately.
        """
        clean_sentence = sentence.strip()
        if not clean_sentence or len(clean_sentence) < 4:
            return

        # Deduplicate sentences (e.g. if partial transcripts overlap)
        sentence_hash = hashlib.sha256(clean_sentence.encode("utf-8")).hexdigest()
        with self._lock:
            if sentence_hash in self._processed_hashes:
                return
            self._processed_hashes.add(sentence_hash)

        # Submit to thread pool
        self._executor.submit(self._analyze_worker, clean_sentence)

    def _analyze_worker(self, sentence: str) -> None:
        """Worker method running inside ThreadPoolExecutor."""
        try:
            issues = self.check_text_sync(sentence)
            if issues:
                with self._lock:
                    self._issues.extend(issues)
                logger.info(
                    f"[Grammarian] Detected {len(issues)} issue(s) in: '{sentence[:40]}...' "
                    f"| Total Errors: {self.get_error_count()}"
                )
        except Exception as e:
            logger.error(f"[Grammarian] Error processing sentence '{sentence[:30]}': {e}")

    def check_text_sync(self, text: str) -> List[GrammarIssue]:
        """
        Synchronously send text to LanguageTool API and return parsed issues.
        Useful for testing or batch finalization.
        """
        if not text or not text.strip():
            return []

        payload = {
            "text": text,
            "language": self.language,
        }

        # Include credentials if provided
        if self.api_key:
            payload["apiKey"] = self.api_key
        if self.username:
            payload["username"] = self.username

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "AI-Speech-Evaluator/1.0 (Raspberry Pi Toastmasters Assistant)",
        }

        try:
            response = self._session.post(
                self.api_url,
                data=payload,
                headers=headers,
                timeout=5.0,  # Strict timeout for embedded responsiveness
            )

            if response.status_code != 200:
                logger.warning(
                    f"[Grammarian] LanguageTool HTTP {response.status_code}: {response.text[:120]}"
                )
                return []

            data = response.json()
            return self._parse_languagetool_response(text, data)

        except requests.exceptions.Timeout:
            logger.warning("[Grammarian] LanguageTool API timed out (5s limit).")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"[Grammarian] Network error calling LanguageTool: {e}")
            return []
        except Exception as e:
            logger.error(f"[Grammarian] Unexpected parsing error: {e}")
            return []

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
