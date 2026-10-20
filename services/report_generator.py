"""
Report Generator for AI Speech Evaluator.
Aggregates session timing, full transcripts, Ah-Counter timeline occurrences,
and Grammarian error reports into a standardized Toastmasters JSON evaluation report.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from services.ah_counter import AhCounter
from services.grammarian import GrammarianEngine

logger = logging.getLogger("speech_evaluator.report")


class ReportGenerator:
    """
    Produces detailed Toastmasters Speech Evaluation JSON reports
    with timeline breakdowns, pacing stats, and grammar recommendations.
    """

    def __init__(self, output_dir: str = "reports", latest_filepath: Optional[str] = None):
        self.output_dir = output_dir
        self.latest_filepath = latest_filepath or os.path.join(os.getcwd(), "evaluation_report.json")
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format seconds into MM:SS format."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    @staticmethod
    def evaluate_pacing(wpm: float) -> Dict[str, str]:
        """Assess speech pacing based on Toastmasters guidelines."""
        if wpm < 100:
            return {
                "rating": "Slow",
                "recommendation": "Pacing was deliberate; consider varying vocal variety and picking up speed.",
            }
        elif 100 <= wpm <= 165:
            return {
                "rating": "Optimal",
                "recommendation": "Excellent conversational pacing within standard Toastmasters speech range.",
            }
        else:
            return {
                "rating": "Fast",
                "recommendation": "Pacing was rapid; incorporate strategic pauses to allow ideas to resonate.",
            }

    @staticmethod
    def evaluate_speech_length(duration_seconds: float) -> str:
        """Classify standard Toastmasters speech timing (5 to 7 minute prepared speech)."""
        if duration_seconds < 300:  # < 5:00
            return "Under Time (Standard speech is 5:00 - 7:00)"
        elif 300 <= duration_seconds <= 420:  # 5:00 - 7:00
            return "On Time (Green to Amber - Ideal)"
        elif 420 < duration_seconds <= 450:  # 7:00 - 7:30
            return "Grace Period (Red card active)"
        else:
            return "Over Time (Exceeded 7:30 limit)"

    def generate(
        self,
        session_id: str,
        start_time: float,
        end_time: float,
        full_transcript: str,
        ah_counter: AhCounter,
        grammarian: GrammarianEngine,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build and write the JSON evaluation report.
        Returns tuple of (file_path, report_dict).
        """
        duration = max(0.1, end_time - start_time)
        formatted_time = self.format_duration(duration)

        # Word count and WPM
        words = full_transcript.split()
        word_count = len(words)
        minutes = duration / 60.0
        wpm = round(word_count / minutes, 1) if minutes > 0 else 0.0

        pacing_eval = self.evaluate_pacing(wpm)
        timing_status = self.evaluate_speech_length(duration)

        # Ah-Counter Stats
        total_fillers = ah_counter.get_total_count()
        vocalized_pauses = ah_counter.get_vocalized_pause_count()
        verbal_crutches = ah_counter.get_verbal_crutch_count()
        filler_breakdown = ah_counter.get_breakdown()
        timeline = ah_counter.get_timeline()

        fillers_per_min = round(total_fillers / minutes, 2) if minutes > 0 else 0.0
        filler_density_pct = round((total_fillers / word_count) * 100.0, 2) if word_count > 0 else 0.0

        # Grammarian Stats
        total_errors = grammarian.get_error_count()
        grammar_issues = grammarian.get_issues()
        errors_per_100_words = round((total_errors / word_count) * 100.0, 2) if word_count > 0 else 0.0

        # Construct Actionable Feedback
        feedback_notes = []
        if total_fillers == 0:
            feedback_notes.append("Flawless delivery: Zero filler words or verbal crutches detected.")
        else:
            top_fillers = sorted(filler_breakdown.items(), key=lambda x: x[1], reverse=True)[:3]
            top_str = ", ".join(f"'{w}' ({c}x)" for w, c in top_fillers)
            feedback_notes.append(f"Most frequent crutches: {top_str}. Practice embracing silent pauses.")

        if total_errors == 0:
            feedback_notes.append("High grammatical precision: No structural syntax errors flagged.")
        else:
            feedback_notes.append(f"Noted {total_errors} grammatical or stylistic opportunity areas.")

        feedback_notes.append(pacing_eval["recommendation"])

        # Compute Overall Speech Score (0 - 100)
        base_score = 100.0
        # Deductions
        filler_penalty = min(35.0, fillers_per_min * 4.0)
        grammar_penalty = min(35.0, errors_per_100_words * 5.0)
        pacing_penalty = 0.0 if pacing_eval["rating"] == "Optimal" else 8.0
        overall_score = max(0.0, round(base_score - filler_penalty - grammar_penalty - pacing_penalty, 1))

        if overall_score >= 90:
            grade = "A (Distinguished)"
        elif overall_score >= 80:
            grade = "B (Proficient)"
        elif overall_score >= 70:
            grade = "C (Competent)"
        elif overall_score >= 60:
            grade = "D (Needs Focus)"
        else:
            grade = "E (Requires Practice)"

        report_data: Dict[str, Any] = {
            "session_id": session_id,
            "generated_at": datetime.now().isoformat(),
            "overall_score": overall_score,
            "overall_grade": grade,
            "timing": {
                "start_time_epoch": round(start_time, 2),
                "end_time_epoch": round(end_time, 2),
                "duration_seconds": round(duration, 2),
                "formatted_duration": formatted_time,
                "timing_status": timing_status,
            },
            "transcript_summary": {
                "full_transcript": full_transcript,
                "total_words": word_count,
                "words_per_minute": wpm,
                "pacing_rating": pacing_eval["rating"],
            },
            "ah_counter": {
                "total_fillers": total_fillers,
                "vocalized_pauses_count": vocalized_pauses,
                "verbal_crutches_count": verbal_crutches,
                "fillers_per_minute": fillers_per_min,
                "filler_density_percent": filler_density_pct,
                "frequency_breakdown": dict(
                    sorted(filler_breakdown.items(), key=lambda x: x[1], reverse=True)
                ),
                "timeline_events": timeline,
            },
            "grammarian": {
                "total_errors": total_errors,
                "error_density_per_100_words": errors_per_100_words,
                "issues": grammar_issues,
            },
            "toastmasters_evaluation": {
                "overall_score": overall_score,
                "overall_grade": grade,
                "summary": feedback_notes,
                "speech_length_status": timing_status,
                "pacing": pacing_eval["rating"],
            },
        }

        # 1. Write timestamped archive file
        filename = f"speech_report_{session_id}.json"
        filepath = os.path.join(self.output_dir, filename)

        # 2. Write latest evaluation_report.json for the Streamlit dashboard
        latest_filepath = self.latest_filepath
        output_latest_path = os.path.join(self.output_dir, "evaluation_report.json")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            logger.info(f"[Report] Successfully generated archived evaluation report: {filepath}")

            # Overwrite evaluation_report.json at root and in reports/
            with open(latest_filepath, "w", encoding="utf-8") as f_latest:
                json.dump(report_data, f_latest, indent=2, ensure_ascii=False)
            with open(output_latest_path, "w", encoding="utf-8") as f_out:
                json.dump(report_data, f_out, indent=2, ensure_ascii=False)
            logger.info(f"[Report] Updated latest evaluation_report.json for dashboard: {latest_filepath}")
        except Exception as e:
            logger.error(f"[Report] Error writing report files: {e}")

        return filepath, report_data
