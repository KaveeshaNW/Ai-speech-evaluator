"""
Authentication and Student Management Database Service.
Provides local SQLite storage for:
1. Student registration & login.
2. Admin authentication via Master Password.
3. Active Speaker podium tracking.
4. Per-student speech evaluation history and progress analytics.
Zero external pip dependencies (uses Python built-in sqlite3 and hashlib).
"""

import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("speech_evaluator.auth")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "speech_evaluator.db")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_MASTER_PASSWORD", "admin123")


class AuthDB:
    """Manages users, authentication, and speech session associations."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a connection with row factory for dictionary-like access."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema if not present."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Users Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',
                    created_at TEXT NOT NULL
                )
                """
            )

            # 2. Speech Sessions Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS speech_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    overall_score REAL NOT NULL,
                    overall_grade TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    formatted_duration TEXT NOT NULL,
                    total_words INTEGER NOT NULL,
                    wpm REAL NOT NULL,
                    pacing_rating TEXT NOT NULL,
                    total_fillers INTEGER NOT NULL,
                    vocalized_pauses INTEGER NOT NULL,
                    verbal_crutches INTEGER NOT NULL,
                    grammar_errors INTEGER NOT NULL,
                    report_file TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # 3. Active Speaker State Table (single row)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS active_speaker (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # Seed default active speaker if empty
            cursor.execute("SELECT COUNT(*) FROM active_speaker")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    """
                    INSERT INTO active_speaker (id, username, full_name, updated_at)
                    VALUES (1, 'guest', 'Guest Speaker', ?)
                    """,
                    (datetime.now().isoformat(),),
                )

            conn.commit()
            logger.debug("[AuthDB] Database schema initialized.")

    @staticmethod
    def _hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Generate secure SHA-256 hash with random 16-byte hex salt."""
        if not salt:
            salt = secrets.token_hex(16)
        salted = f"{salt}:{password}".encode("utf-8")
        h = hashlib.sha256(salted).hexdigest()
        return h, salt

    @staticmethod
    def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
        """Verify password matches stored hash and salt."""
        salted = f"{salt}:{password}".encode("utf-8")
        calc_hash = hashlib.sha256(salted).hexdigest()
        return secrets.compare_digest(calc_hash, stored_hash)

    def register_student(self, username: str, full_name: str, password: str) -> Tuple[bool, str]:
        """
        Register a new student account.
        Returns (success: bool, message: str).
        """
        clean_user = username.strip().lower()
        clean_name = full_name.strip()
        clean_pass = password.strip()

        if not clean_user or len(clean_user) < 3:
            return False, "Username must be at least 3 characters."
        if not clean_name:
            return False, "Full Name is required."
        if not clean_pass or len(clean_pass) < 4:
            return False, "Password must be at least 4 characters."

        pw_hash, salt = self._hash_password(clean_pass)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (username, full_name, password_hash, salt, role, created_at)
                    VALUES (?, ?, ?, ?, 'student', ?)
                    """,
                    (clean_user, clean_name, pw_hash, salt, now),
                )
                conn.commit()
                logger.info(f"[AuthDB] Registered student: {clean_user} ({clean_name})")
                return True, f"Account '{clean_user}' created successfully! You can now log in."
        except sqlite3.IntegrityError:
            return False, f"Username '{clean_user}' is already registered. Please choose another."
        except Exception as e:
            logger.error(f"[AuthDB] Error registering student: {e}")
            return False, f"Registration failed: {e}"

    def authenticate_student(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate a student with username and password.
        Returns user dictionary if valid, None otherwise.
        """
        clean_user = username.strip().lower()
        clean_pass = password.strip()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (clean_user,))
            row = cursor.fetchone()
            if not row:
                return None

            user = dict(row)
            if self._verify_password(clean_pass, user["password_hash"], user["salt"]):
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "full_name": user["full_name"],
                    "role": user["role"],
                    "created_at": user["created_at"],
                }
        return None

    def verify_admin_master_password(self, password: str) -> bool:
        """Check if entered password matches the admin master password."""
        clean_pass = password.strip()
        expected = os.environ.get("ADMIN_MASTER_PASSWORD", DEFAULT_ADMIN_PASSWORD).strip()
        return secrets.compare_digest(clean_pass, expected)

    def set_active_speaker(self, username: str, full_name: Optional[str] = None) -> None:
        """Set the active speaker for the current podium speech."""
        clean_user = username.strip().lower()
        if not full_name:
            user = self.get_student(clean_user)
            full_name = user["full_name"] if user else clean_user.title()

        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE active_speaker
                SET username = ?, full_name = ?, updated_at = ?
                WHERE id = 1
                """,
                (clean_user, full_name, now),
            )
            conn.commit()
            logger.info(f"[AuthDB] Active speaker set to: {clean_user} ({full_name})")

    def get_active_speaker(self) -> Dict[str, str]:
        """Return currently active podium speaker."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, full_name, updated_at FROM active_speaker WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
        return {"username": "guest", "full_name": "Guest Speaker", "updated_at": ""}

    def get_student(self, username: str) -> Optional[Dict[str, Any]]:
        """Get student details by username."""
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, full_name, role, created_at FROM users WHERE username = ?", (clean_user,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_students(self) -> List[Dict[str, Any]]:
        """Get list of all registered students with their aggregate speech statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    u.id,
                    u.username,
                    u.full_name,
                    u.created_at,
                    COUNT(s.id) as speech_count,
                    COALESCE(ROUND(AVG(s.overall_score), 1), 0.0) as avg_score,
                    COALESCE(SUM(s.total_fillers), 0) as total_fillers_sum,
                    COALESCE(SUM(s.grammar_errors), 0) as total_grammar_sum,
                    COALESCE(ROUND(AVG(s.wpm), 1), 0.0) as avg_wpm
                FROM users u
                LEFT JOIN speech_sessions s ON LOWER(u.username) = LOWER(s.username)
                WHERE u.role = 'student'
                GROUP BY u.id
                ORDER BY u.full_name ASC
                """
            )
            return [dict(r) for r in cursor.fetchall()]

    def record_speech_session(
        self,
        report_data: Dict[str, Any],
        report_file: str,
        override_username: Optional[str] = None,
        override_name: Optional[str] = None,
    ) -> None:
        """
        Record a finalized speech report linked to a student account.
        If no user specified, links to the currently active speaker.
        """
        session_id = report_data.get("session_id", "session")
        if override_username and override_name:
            username = override_username.strip().lower()
            full_name = override_name.strip()
        else:
            active = self.get_active_speaker()
            username = active["username"]
            full_name = active["full_name"]

        timing = report_data.get("timing", {})
        transcript = report_data.get("transcript_summary", {})
        ah = report_data.get("ah_counter", {})
        gram = report_data.get("grammarian", {})

        score = float(report_data.get("overall_score", 0.0))
        grade = str(report_data.get("overall_grade", "N/A"))
        duration = float(timing.get("duration_seconds", 0.0))
        fmt_dur = str(timing.get("formatted_duration", "00:00"))
        words = int(transcript.get("total_words", 0))
        wpm = float(transcript.get("words_per_minute", 0.0))
        pacing = str(transcript.get("pacing_rating", "Optimal"))
        fillers = int(ah.get("total_fillers", 0))
        pauses = int(ah.get("vocalized_pauses_count", 0))
        crutches = int(ah.get("verbal_crutches_count", 0))
        errors = int(gram.get("total_errors", 0))
        created = report_data.get("generated_at", datetime.now().isoformat())

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO speech_sessions (
                        session_id, username, full_name, overall_score, overall_grade,
                        duration_seconds, formatted_duration, total_words, wpm, pacing_rating,
                        total_fillers, vocalized_pauses, verbal_crutches, grammar_errors,
                        report_file, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        username=excluded.username,
                        full_name=excluded.full_name,
                        overall_score=excluded.overall_score,
                        overall_grade=excluded.overall_grade,
                        total_fillers=excluded.total_fillers,
                        grammar_errors=excluded.grammar_errors,
                        report_file=excluded.report_file
                    """,
                    (
                        session_id, username, full_name, score, grade,
                        duration, fmt_dur, words, wpm, pacing,
                        fillers, pauses, crutches, errors,
                        report_file, created,
                    ),
                )
                conn.commit()
                logger.info(f"[AuthDB] Linked speech [{session_id}] to student '{username}' ({score} pts)")
        except Exception as e:
            logger.error(f"[AuthDB] Error saving speech session: {e}")

    def get_speeches_for_student(self, username: str) -> List[Dict[str, Any]]:
        """Get all speech records for a specific student, most recent first."""
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM speech_sessions
                WHERE LOWER(username) = ?
                ORDER BY created_at DESC
                """,
                (clean_user,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_all_speech_sessions(self) -> List[Dict[str, Any]]:
        """Get all speech sessions across all students, most recent first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM speech_sessions ORDER BY created_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    def get_student_summary(self, username: str) -> Dict[str, Any]:
        """Compute aggregate stats for a student's dashboard."""
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_speeches,
                    COALESCE(ROUND(AVG(overall_score), 1), 0.0) as avg_score,
                    COALESCE(MAX(overall_score), 0.0) as best_score,
                    COALESCE(ROUND(AVG(total_fillers), 1), 0.0) as avg_fillers,
                    COALESCE(ROUND(AVG(grammar_errors), 1), 0.0) as avg_errors,
                    COALESCE(ROUND(AVG(wpm), 1), 0.0) as avg_wpm,
                    COALESCE(SUM(total_words), 0) as total_words_spoken
                FROM speech_sessions
                WHERE LOWER(username) = ?
                """,
                (clean_user,),
            )
            row = cursor.fetchone()
            return dict(row) if row else {}
