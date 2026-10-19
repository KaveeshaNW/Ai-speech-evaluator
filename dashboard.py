"""
Streamlit Web Dashboard for AI Speech Evaluator (Toastmasters Assistant).
Runs on 0.0.0.0:8501 for local network accessibility from phones, tablets, or laptops.
Displays:
1. Overall Speech Score & Summary Metrics (WPM, Pacing, Duration, Toastmasters evaluation).
2. Disfluency Breakdown (Total count, category breakdown, frequency distribution, exact timeline).
3. Grammarian Report (Full transcript with highlighted errors and suggested corrections).
Features automatic background refresh when new evaluation reports are generated.
"""

import glob
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import streamlit as st

# Configure page layout and Toastmasters aesthetic
st.set_page_config(
    page_title="AI Speech Evaluator | Toastmasters Dashboard",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Toastmasters styling, score badge, and error highlights
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #772432; /* Toastmasters Burgundy */
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .score-card {
        background: linear-gradient(135deg, #772432 0%, #004165 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .score-number {
        font-size: 3.5rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .score-grade {
        font-size: 1.3rem;
        font-weight: 600;
        opacity: 0.95;
    }
    .grammar-error {
        background-color: #ffd2d2;
        color: #900;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
        border-bottom: 2px dashed #d00;
        cursor: help;
    }
    .grammar-fix {
        background-color: #d4edda;
        color: #155724;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
    }
    .filler-badge-pause {
        background-color: #ffeeba;
        color: #856404;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .filler-badge-crutch {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def load_report_file(filepath: str) -> Optional[Dict[str, Any]]:
    """Load and parse JSON evaluation report."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading report: {e}")
        return None


def get_available_reports() -> List[str]:
    """Find all evaluation reports in workspace and reports/ directory."""
    files = []
    if os.path.exists("evaluation_report.json"):
        files.append("evaluation_report.json")
    for f in glob.glob("reports/speech_report_*.json"):
        if f not in files:
            files.append(f)
    files.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
    return files


# ------------------------------------------------------------------------------
# Auto-refresh setup
# ------------------------------------------------------------------------------
refresh_rate_sec = 3
try:
    from streamlit_autorefresh import st_autorefresh

    # Auto-refresh every N seconds
    st_autorefresh(interval=refresh_rate_sec * 1000, key="speech_evaluator_autorefresh")
except ImportError:
    # Graceful fallback: show a manual refresh button in sidebar
    pass


# ------------------------------------------------------------------------------
# Sidebar Navigation & Session Selection
# ------------------------------------------------------------------------------
st.sidebar.image("https://upload.wikimedia.org/wikipedia/en/thumb/9/9f/Toastmasters_International_logo.svg/320px-Toastmasters_International_logo.svg.png", width=180)
st.sidebar.title("Speech Evaluator")
st.sidebar.markdown("**Host:** Raspberry Pi 3 (0.0.0.0)")

available_reports = get_available_reports()
selected_file = "evaluation_report.json"

if available_reports:
    selected_file = st.sidebar.selectbox(
        "Select Speech Session:",
        available_reports,
        index=0,
        format_func=lambda x: "Current / Latest Session" if x == "evaluation_report.json" else os.path.basename(x),
    )
    if os.path.exists(selected_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(selected_file)).strftime("%Y-%m-%d %H:%M:%S")
        st.sidebar.caption(f"Last updated: {mtime}")
else:
    st.sidebar.info("No speech reports found yet.")

if st.sidebar.button("🔄 Manual Refresh"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Hardware Status:**
    - ⏱️ **Timer:** Active on 16x2 I2C LCD
    - 🔘 **Switch (GPIO 18):** Listening
    - 🎙️ **Microphone:** M-305 USB Audio
    """
)

# ------------------------------------------------------------------------------
# Main Content
# ------------------------------------------------------------------------------
st.markdown('<div class="main-header">🎙️ Toastmasters AI Speech Evaluator</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Automated Timer, Ah-Counter, and Grammarian Dashboard</div>', unsafe_allow_html=True)

report = load_report_file(selected_file) if selected_file and os.path.exists(selected_file) else None

if not report:
    # Standby Screen when no speech has occurred yet
    st.warning("⏳ **Awaiting Speech Capture...**")
    st.info(
        """
        The physical toggle switch is currently **OFF** (or no evaluation report has been finalized yet).
        
        **How to start:**
        1. Flip the physical toggle switch connected to **GPIO 18 ON**.
        2. Speak into the **M-305 microphone**. The physical 16x2 LCD will display the live timer (`Time: MM:SS`).
        3. Flip the switch **OFF** when you finish. The evaluation will process and instantly appear on this dashboard!
        """
    )
    st.stop()

# Extract Data
session_id = report.get("session_id", "N/A")
timing = report.get("timing", {})
transcript_summary = report.get("transcript_summary", {})
ah_counter = report.get("ah_counter", {})
grammarian = report.get("grammarian", {})
evaluation = report.get("toastmasters_evaluation", {})

overall_score = report.get("overall_score", evaluation.get("overall_score", 85.0))
overall_grade = report.get("overall_grade", evaluation.get("overall_grade", "B (Proficient)"))

# ------------------------------------------------------------------------------
# 1. Overall Speech Score & Summary Metrics
# ------------------------------------------------------------------------------
score_col, summary_col = st.columns([1, 2])

with score_col:
    st.markdown(
        f"""
        <div class="score-card">
            <div style="text-transform: uppercase; letter-spacing: 1px; font-size: 0.9rem;">Overall Speech Score</div>
            <div class="score-number">{overall_score:.0f}</div>
            <div class="score-grade">{overall_grade}</div>
            <div style="font-size: 0.85rem; margin-top: 0.5rem; opacity: 0.85;">Session: {session_id}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with summary_col:
    # Top Metrics Grid
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            label="Speech Duration",
            value=timing.get("formatted_duration", "00:00"),
            help=timing.get("timing_status", "Standard speech"),
        )
    with m2:
        st.metric(
            label="Pacing (WPM)",
            value=f"{transcript_summary.get('words_per_minute', 0):.0f}",
            delta=transcript_summary.get("pacing_rating", "Optimal"),
            delta_color="normal" if transcript_summary.get("pacing_rating") == "Optimal" else "inverse",
        )
    with m3:
        st.metric(
            label="Total Fillers",
            value=ah_counter.get("total_fillers", 0),
            delta=f"{ah_counter.get('fillers_per_minute', 0):.1f} / min",
            delta_color="inverse" if ah_counter.get("total_fillers", 0) > 0 else "normal",
        )
    with m4:
        st.metric(
            label="Grammar Issues",
            value=grammarian.get("total_errors", 0),
            delta=f"{grammarian.get('error_density_per_100_words', 0):.1f} / 100w",
            delta_color="inverse" if grammarian.get("total_errors", 0) > 0 else "normal",
        )

    # Toastmasters Feedback Box
    with st.container():
        st.markdown("**Evaluator Feedback & Observations:**")
        feedback_list = evaluation.get("summary", [])
        if feedback_list:
            for item in feedback_list:
                st.markdown(f"- {item}")
        else:
            st.markdown("- Speech was delivered clearly.")

st.markdown("---")

# ------------------------------------------------------------------------------
# 2. Disfluency Breakdown & Timeline
# ------------------------------------------------------------------------------
st.subheader("🗣️ Disfluency & Ah-Counter Breakdown")

f_col1, f_col2 = st.columns([1, 1])

with f_col1:
    vocal_pauses = ah_counter.get("vocalized_pauses_count", 0)
    crutches = ah_counter.get("verbal_crutches_count", 0)
    total_fillers = ah_counter.get("total_fillers", 0)

    p1, p2, p3 = st.columns(3)
    p1.metric("Total Fillers", total_fillers)
    p2.metric("Vocalized Pauses ('ah', 'um')", vocal_pauses)
    p3.metric("Verbal Crutches ('like', 'you know')", crutches)

    # Frequency breakdown table
    freq = ah_counter.get("frequency_breakdown", {})
    if freq:
        st.markdown("**Most Frequent Fillers:**")
        # Format as simple bar list
        for word, count in freq.items():
            pct = int((count / max(1, total_fillers)) * 100)
            st.markdown(
                f"- **`{word}`**: {count} time(s) &nbsp; "
                f"<div style='display:inline-block; width:{pct}%; max-width:200px; height:8px; background-color:#772432; border-radius:4px;'></div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("🎉 No filler words detected! Excellent vocal discipline.")

with f_col2:
    timeline_events = ah_counter.get("timeline_events", [])
    st.markdown("**Chronological Disfluency Timeline:**")

    if timeline_events:
        # Display scrollable table with timestamps and tags
        table_rows = []
        for ev in timeline_events:
            t_str = format_timestamp(ev.get("start_time", 0.0))
            w = ev.get("word", "")
            cat = ev.get("category", "")
            badge = "vocalized_pause" if "pause" in cat else "verbal_crutch"
            badge_class = "filler-badge-pause" if badge == "vocalized_pause" else "filler-badge-crutch"
            table_rows.append(
                f"<tr>"
                f"<td style='padding:6px 12px; font-family:monospace; font-weight:bold;'>{t_str}</td>"
                f"<td style='padding:6px 12px; font-weight:bold;'>{w}</td>"
                f"<td style='padding:6px 12px;'><span class='{badge_class}'>{cat.replace('_', ' ').title()}</span></td>"
                f"</tr>"
            )

        html_table = f"""
        <div style="max-height: 240px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px;">
            <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
                <thead style="background-color:#f8f9fa; position:sticky; top:0;">
                    <tr>
                        <th style="padding:6px 12px; text-align:left;">Time</th>
                        <th style="padding:6px 12px; text-align:left;">Word / Phrase</th>
                        <th style="padding:6px 12px; text-align:left;">Category</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>
        """
        st.markdown(html_table, unsafe_allow_html=True)
    else:
        st.info("No timeline events to display.")

st.markdown("---")

# ------------------------------------------------------------------------------
# 3. Grammarian Report & Highlighted Transcript
# ------------------------------------------------------------------------------
st.subheader("📖 Grammarian Report & Transcript")

full_transcript = transcript_summary.get("full_transcript", "")
issues = grammarian.get("issues", [])

if not full_transcript:
    st.info("No speech transcript recorded for this session.")
else:
    # Build highlighted transcript
    # Replace matched error context spans with highlighted HTML spans
    highlighted_text = full_transcript
    for idx, issue in enumerate(issues):
        context_text = issue.get("context_text", "")
        if context_text and context_text in highlighted_text:
            replacement = (
                f"<span class='grammar-error' title='Issue #{idx+1}: {issue.get('message', '')}'>"
                f"{context_text}</span>"
            )
            # Replace only first occurrence
            highlighted_text = highlighted_text.replace(context_text, replacement, 1)

    t_col1, t_col2 = st.columns([3, 2])

    with t_col1:
        st.markdown("**Transcript (Grammatical Opportunities Highlighted):**")
        st.markdown(
            f"""
            <div style="background-color: #fdfdfd; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1.2rem; font-size: 1.05rem; line-height: 1.7; min-height: 200px;">
                {highlighted_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t_col2:
        st.markdown(f"**Identified Issues ({len(issues)}):**")
        if issues:
            for idx, issue in enumerate(issues):
                with st.expander(f"Issue #{idx+1}: {issue.get('rule_id', 'Grammar Notice')}"):
                    st.markdown(f"**Explanation:** {issue.get('message', '')}")
                    suggestions = issue.get("suggestions", [])
                    if suggestions:
                        sug_html = " ".join([f"<span class='grammar-fix'>{s}</span>" for s in suggestions])
                        st.markdown(f"**Suggested Correction(s):** {sug_html}", unsafe_allow_html=True)
                    st.caption(f"Rule: {issue.get('rule_description', '')}")
        else:
            st.success("✨ Zero grammatical errors identified. Excellent syntax!")

st.markdown("---")
st.caption("AI Speech Evaluator for Toastmasters | Running on Raspberry Pi 3 | Auto-refreshing every 3 seconds")
