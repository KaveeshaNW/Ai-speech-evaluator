"""
Streamlit Web Dashboard for AI Speech Evaluator (Toastmasters Assistant).
Runs on 0.0.0.0:8501 for local network accessibility from phones, tablets, or laptops.

Website-Style Authentication & Access Control:
- Full-screen login / registration portal: Users must log in to access the system.
- Student Accounts: Sign up, log in, view personal speech history, and progress analytics.
- Admin Portal (Master Password): View all registered students, performance analytics, and manage active speaker.
- Live Evaluation Dashboard:
  * Overall Speech Score & Summary Metrics (WPM, Pacing, Duration, Toastmasters evaluation).
  * Disfluency Breakdown (Total count, category breakdown, frequency distribution, exact timeline).
  * Grammarly-Style Interactive Transcript: Highlighted grammar errors with instant hover cards explaining rules and suggestions.
"""

import glob
import html
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import streamlit as st

from services.auth_db import AuthDB

# ------------------------------------------------------------------------------
# 1. Page Configuration & Custom CSS
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Speech Evaluator | Toastmasters Portal",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Toastmasters styling, score badge, and Grammarly-style tooltips
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
        opacity: 0.85;
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

    /* ------------------------------------------------------------- */
    /* Grammarly-Style Interactive Hover Tooltip Cards                */
    /* ------------------------------------------------------------- */
    .transcript-box {
        background-color: rgba(255, 255, 255, 0.05);
        color: inherit;
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 8px;
        padding: 1.3rem;
        font-size: 1.08rem;
        line-height: 2.0;
        min-height: 180px;
        position: relative;
    }
    .grammar-highlight {
        position: relative;
        display: inline-block;
        background-color: rgba(220, 53, 69, 0.16);
        color: #e63946;
        border-bottom: 2.5px wavy #d90429;
        padding: 1px 4px;
        border-radius: 4px;
        font-weight: 600;
        cursor: pointer;
    }
    .grammar-highlight:hover .grammar-tooltip {
        opacity: 1;
        visibility: visible;
        transform: translateY(0);
    }
    .grammar-tooltip {
        position: absolute;
        bottom: 125%;
        left: 50%;
        transform: translateY(6px);
        width: 290px;
        background: #181c24;
        color: #f1f5f9;
        padding: 12px 14px;
        border-radius: 9px;
        font-size: 0.86rem;
        line-height: 1.45;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.12);
        opacity: 0;
        visibility: hidden;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        z-index: 9999;
        pointer-events: none;
        text-align: left;
        white-space: normal;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .grammar-tooltip::after {
        content: '';
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -6px;
        border-width: 6px;
        border-style: solid;
        border-color: #181c24 transparent transparent transparent;
    }
    .tooltip-badge {
        display: inline-block;
        background: #772432;
        color: #ffffff;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 2px 7px;
        border-radius: 3px;
        margin-bottom: 6px;
    }
    .tooltip-msg {
        font-size: 0.85rem;
        color: #e2e8f0;
        margin-bottom: 6px;
        font-weight: normal;
    }
    .tooltip-suggestion {
        background: rgba(40, 167, 69, 0.22);
        color: #4ade80;
        border: 1px solid rgba(40, 167, 69, 0.45);
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
        display: inline-block;
        font-size: 0.82rem;
        margin-right: 4px;
    }
    .grammar-fix {
        background-color: #d4edda;
        color: #155724;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
    }

    /* ------------------------------------------------------------- */
    /* Website Portal Login Styles                                   */
    /* ------------------------------------------------------------- */
    .portal-box {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 14px;
        padding: 2rem;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
        margin-top: 1rem;
    }
    .portal-title {
        font-size: 1.85rem;
        font-weight: 700;
        color: #772432;
        text-align: center;
        margin-top: 0.5rem;
        margin-bottom: 0.2rem;
    }
    .portal-subtitle {
        font-size: 0.95rem;
        opacity: 0.82;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# 2. Database & Session State Initialization
# ------------------------------------------------------------------------------
db = AuthDB()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_role" not in st.session_state:
    st.session_state["user_role"] = "guest"  # guest, student, admin
if "username" not in st.session_state:
    st.session_state["username"] = "guest"
if "full_name" not in st.session_state:
    st.session_state["full_name"] = "Guest Speaker"

# ------------------------------------------------------------------------------
# 3. WEBSITE AUTHENTICATION GATE (Visible when not logged in)
# ------------------------------------------------------------------------------
if not st.session_state["logged_in"]:
    # Hide sidebar while on login gate
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Centered modern web portal container
    c_left, c_center, c_right = st.columns([1, 2, 1])

    with c_center:
        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
        st.markdown('<div class="portal-title">🎙️ AI Speech Evaluator Portal</div>', unsafe_allow_html=True)
        st.markdown('<div class="portal-subtitle">Sign in to access your speech analytics and podium evaluations</div>', unsafe_allow_html=True)

        tab_login, tab_signup, tab_admin = st.tabs(["🔑 Student Sign In", "📝 Create Account", "🛡️ Admin Access"])

        with tab_login:
            st.markdown("#### Student Sign In")
            with st.form("student_login_form"):
                u_name = st.text_input("Username:", placeholder="e.g. sarah", key="login_u")
                u_pass = st.text_input("Password:", type="password", placeholder="••••••••", key="login_p")
                submit_login = st.form_submit_button("Sign In to Evaluator", use_container_width=True)

                if submit_login:
                    user = db.authenticate_student(u_name, u_pass)
                    if user:
                        st.session_state["logged_in"] = True
                        st.session_state["user_role"] = "student"
                        st.session_state["username"] = user["username"]
                        st.session_state["full_name"] = user["full_name"]
                        db.set_active_speaker(user["username"], user["full_name"])
                        st.success(f"Welcome back, {user['full_name']}!")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error("Invalid username or password. Please verify and try again.")

        with tab_signup:
            st.markdown("#### Student Registration")
            with st.form("student_signup_form"):
                su_fullname = st.text_input("Full Name:", placeholder="e.g. Sarah Jenkins", key="su_fn")
                su_username = st.text_input("Choose Username:", placeholder="e.g. sarah", key="su_un")
                su_password = st.text_input("Create Password:", type="password", placeholder="••••••••", key="su_pw")
                submit_signup = st.form_submit_button("Create Account & Sign In", use_container_width=True)

                if submit_signup:
                    ok, msg = db.register_student(su_username, su_fullname, su_password)
                    if ok:
                        st.session_state["logged_in"] = True
                        st.session_state["user_role"] = "student"
                        st.session_state["username"] = su_username.strip().lower()
                        st.session_state["full_name"] = su_fullname.strip()
                        db.set_active_speaker(su_username.strip().lower(), su_fullname.strip())
                        st.success(f"Welcome to Toastmasters, {su_fullname}!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)

        with tab_admin:
            st.markdown("#### Meeting Evaluator / Administrator")
            with st.form("admin_login_form"):
                admin_pw = st.text_input("Master Password:", type="password", placeholder="Enter Master Password", key="ad_pw")
                submit_admin = st.form_submit_button("Unlock Admin Portal", use_container_width=True)

                if submit_admin:
                    if db.verify_admin_master_password(admin_pw):
                        st.session_state["logged_in"] = True
                        st.session_state["user_role"] = "admin"
                        st.session_state["username"] = "admin"
                        st.session_state["full_name"] = "Meeting Administrator"
                        st.success("Admin portal unlocked!")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error("Incorrect Master Password.")

        st.markdown("---")
        st.markdown(
            "<div style='text-align:center; font-size: 0.85rem; opacity: 0.7;'>"
            "🔒 Protected Speech Evaluator Web Portal · Raspberry Pi Standalone Appliance"
            "</div>",
            unsafe_allow_html=True,
        )

    # Stop execution here: Unauthenticated users CANNOT see the evaluator dashboard!
    st.stop()


# ------------------------------------------------------------------------------
# 4. Helper Functions (Loaded for Authenticated Users)
# ------------------------------------------------------------------------------
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
# 5. Authenticated Sidebar Branding & Navigation
# ------------------------------------------------------------------------------
st.sidebar.title("🎙️ Speech Evaluator")
st.sidebar.markdown("**Host:** Raspberry Pi 3")

# User Badge & Logout in Sidebar
role_icon = "🛡️" if st.session_state["user_role"] == "admin" else "👤"
st.sidebar.markdown(f"**{role_icon} Current User:**")
st.sidebar.markdown(f"### {st.session_state['full_name']}")
st.sidebar.caption(f"Role: {st.session_state['user_role'].title()} (@{st.session_state['username']})")

if st.sidebar.button("🚪 Log Out", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["user_role"] = "guest"
    st.session_state["username"] = "guest"
    st.session_state["full_name"] = "Guest Speaker"
    st.rerun()

st.sidebar.markdown("---")

# Navigation Options Based on Role
if st.session_state["user_role"] == "admin":
    current_view = st.sidebar.radio(
        "Navigation Menu:",
        ["🎙️ Live Speech Evaluation", "👥 Student Directory & Analytics", "📋 All Speech Records"],
        key="nav_admin",
    )
else:
    current_view = st.sidebar.radio(
        "Navigation Menu:",
        ["🎙️ Live Speech Evaluation", "📊 My Speech History"],
        key="nav_student",
    )

# ------------------------------------------------------------------------------
# 6. Auto-Refresh Setup (Active ONLY in Live Speech View to prevent form disruption)
# ------------------------------------------------------------------------------
if current_view == "🎙️ Live Speech Evaluation":
    refresh_rate_sec = 3
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=refresh_rate_sec * 1000, key="speech_evaluator_autorefresh")
    except ImportError:
        st.markdown(f'<meta http-equiv="refresh" content="{refresh_rate_sec}">', unsafe_allow_html=True)
        st.sidebar.caption("⚡ Auto-refresh active (browser meta tag)")


# ------------------------------------------------------------------------------
# 7. Sidebar: Live Session Status (Directly uses current session, no JSON dropdown)
# ------------------------------------------------------------------------------
if current_view == "🎙️ Live Speech Evaluation":
    # Always target current / latest evaluation report
    selected_file = "evaluation_report.json"
    if not os.path.exists(selected_file):
        rep_alt = os.path.join("reports", "evaluation_report.json")
        if os.path.exists(rep_alt):
            selected_file = rep_alt
        else:
            archived = glob.glob("reports/speech_report_*.json")
            if archived:
                archived.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
                selected_file = archived[0]

    st.sidebar.markdown("**Session Mode:** 🟢 Current Speech")
    if os.path.exists(selected_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(selected_file)).strftime("%Y-%m-%d %H:%M:%S")
        st.sidebar.caption(f"🕒 Last evaluated: {mtime}")
    else:
        st.sidebar.caption("🕒 Ready for speech (toggle switch ON)")

    if st.sidebar.button("🔄 Refresh Evaluation", use_container_width=True):
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


# ==============================================================================
# VIEW 1: LIVE SPEECH EVALUATION DASHBOARD
# ==============================================================================
if current_view == "🎙️ Live Speech Evaluation":
    st.markdown('<div class="main-header">🎙️ Toastmasters AI Speech Evaluator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Automated Timer, Ah-Counter, and Grammarian Dashboard</div>', unsafe_allow_html=True)

    # Active Speaker indicator at podium
    active_speaker = db.get_active_speaker()
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.info(f"🎤 **Current Speaker at Podium:** {active_speaker['full_name']} (`@{active_speaker['username']}`)")
    with col_b:
        if st.session_state["user_role"] == "admin":
            all_students = db.get_all_students()
            options = ["Guest Speaker"] + [f"{s['full_name']} ({s['username']})" for s in all_students]
            selected_speaker = st.selectbox("Assign Active Speaker:", options, index=0)
            if st.button("Set Active Speaker", use_container_width=True):
                if selected_speaker == "Guest Speaker":
                    db.set_active_speaker("guest", "Guest Speaker")
                else:
                    uname = selected_speaker.split("(")[-1].replace(")", "").strip()
                    s_name = selected_speaker.split("(")[0].strip()
                    db.set_active_speaker(uname, s_name)
                st.rerun()

    report = load_report_file(selected_file) if selected_file and os.path.exists(selected_file) else None

    if not report:
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

    # Link report to database for student history
    if selected_file == "evaluation_report.json" or "reports" in selected_file:
        if st.session_state["user_role"] == "student":
            db.record_speech_session(
                report,
                selected_file,
                override_username=st.session_state["username"],
                override_name=st.session_state["full_name"],
            )
        else:
            db.record_speech_session(report, selected_file)

    # Extract Data
    session_id = report.get("session_id", "N/A")
    timing = report.get("timing", {})
    transcript_summary = report.get("transcript_summary", {})
    ah_counter = report.get("ah_counter", {})
    grammarian = report.get("grammarian", {})
    evaluation = report.get("toastmasters_evaluation", {})

    overall_score = report.get("overall_score", evaluation.get("overall_score", 85.0))
    overall_grade = report.get("overall_grade", evaluation.get("overall_grade", "B (Proficient)"))

    # 1. Overall Speech Score & Summary Metrics
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

        with st.container():
            st.markdown("**Evaluator Feedback & Observations:**")
            feedback_list = evaluation.get("summary", [])
            if feedback_list:
                for item in feedback_list:
                    st.markdown(f"- {item}")
            else:
                st.markdown("- Speech was delivered clearly.")

    st.markdown("---")

    # 2. Disfluency Breakdown & Timeline
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

        freq = ah_counter.get("frequency_breakdown", {})
        if freq:
            st.markdown("**Most Frequent Fillers:**")
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
            <div style="max-height: 240px; overflow-y: auto; border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 8px;">
                <table style="width:100%; border-collapse:collapse; font-size:0.9rem; color: inherit;">
                    <thead style="background-color: rgba(255, 255, 255, 0.08); position:sticky; top:0;">
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

    # 3. Grammarian Report & Interactive Hover Tooltip Transcript
    st.subheader("📖 Grammarian Report & Transcript")
    full_transcript = transcript_summary.get("full_transcript", "")
    issues = grammarian.get("issues", [])

    if not full_transcript:
        st.warning(
            "⚠️ **No words were detected in this audio recording.**\n\n"
            "If you spoke into the microphone, check:\n"
            "1. Is the physical switch on the M-305 microphone handle switched to **ON**?\n"
            "2. Is the microphone cable plugged into the **MIC (pink)** input jack of the USB adapter?\n"
            "3. Is the microphone unmuted in **alsamixer**? (Run `alsamixer`, press `F4` for Capture, press `Space` to unmute, and press `Up Arrow` to raise gain)."
        )
    else:
        # Build Grammarly-style highlighted transcript with hover cards
        highlighted_text = html.escape(full_transcript)
        for idx, issue in enumerate(issues):
            context_text = issue.get("context_text", "")
            c_off = int(issue.get("context_offset", 0))
            c_len = int(issue.get("length", 0))
            rule_id = html.escape(issue.get("rule_id", "Grammar Opportunity"))
            msg = html.escape(issue.get("message", "Grammar rule opportunity."))
            suggestions = issue.get("suggestions", [])

            sug_html = ""
            if suggestions:
                sug_pills = "".join([f"<span class='tooltip-suggestion'>{html.escape(s)}</span>" for s in suggestions[:2]])
                sug_html = f"<div style='margin-top:6px;'><b>Suggested Fix:</b> {sug_pills}</div>"

            esc_context = html.escape(context_text)
            if esc_context and esc_context in highlighted_text:
                if 0 <= c_off < len(context_text) and (c_off + c_len) <= len(context_text) and c_len > 0:
                    raw_err_word = context_text[c_off : c_off + c_len]
                    err_word = html.escape(raw_err_word)
                    hover_span = (
                        f"<span class='grammar-highlight'>{err_word}"
                        f"<span class='grammar-tooltip'>"
                        f"<span class='tooltip-badge'>Issue #{idx+1} · {rule_id}</span>"
                        f"<div class='tooltip-msg'>{msg}</div>"
                        f"{sug_html}"
                        f"</span>"
                        f"</span>"
                    )
                    prefix = html.escape(context_text[:c_off])
                    suffix = html.escape(context_text[c_off + c_len :])
                    highlighted_context = prefix + hover_span + suffix
                    highlighted_text = highlighted_text.replace(esc_context, highlighted_context, 1)
                else:
                    hover_span = (
                        f"<span class='grammar-highlight'>{esc_context}"
                        f"<span class='grammar-tooltip'>"
                        f"<span class='tooltip-badge'>Issue #{idx+1} · {rule_id}</span>"
                        f"<div class='tooltip-msg'>{msg}</div>"
                        f"{sug_html}"
                        f"</span>"
                        f"</span>"
                    )
                    highlighted_text = highlighted_text.replace(esc_context, hover_span, 1)

        t_col1, t_col2 = st.columns([3, 2])

        with t_col1:
            st.markdown("**Transcript (Hover over red highlights for Grammarly-style insights):**")
            st.markdown(
                f"""
                <div class="transcript-box">
                    {highlighted_text}
                </div>
                """,
                unsafe_allow_html=True,
            )

        with t_col2:
            st.markdown(f"**Identified Spoken Grammar Issues ({len(issues)}):**")
            if issues:
                for idx, issue in enumerate(issues):
                    with st.expander(f"Issue #{idx+1}: {issue.get('rule_id', 'Grammar Opportunity')}"):
                        st.markdown(f"**Explanation:** {issue.get('message', '')}")
                        suggestions = issue.get("suggestions", [])
                        if suggestions:
                            sug_html = " ".join([f"<span class='grammar-fix'>{s}</span>" for s in suggestions])
                            st.markdown(f"**Suggested Correction(s):** {sug_html}", unsafe_allow_html=True)
                        st.caption(f"Rule: {issue.get('rule_description', '')}")
            else:
                st.success("✨ Zero spoken grammar errors identified. Excellent vocal syntax!")


# ==============================================================================
# VIEW 2: STUDENT SPEECH HISTORY (For Logged In Students)
# ==============================================================================
elif current_view == "📊 My Speech History":
    st.markdown(f'<div class="main-header">📊 {st.session_state["full_name"]}\'s Speech Journey</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">Personal evaluation history and progression metrics (@{st.session_state["username"]})</div>', unsafe_allow_html=True)

    summary = db.get_student_summary(st.session_state["username"])
    speeches = db.get_speeches_for_student(st.session_state["username"])

    # Top summary metrics
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Speeches Given", summary.get("total_speeches", 0))
    s2.metric("Average Score", f"{summary.get('avg_score', 0.0):.1f}")
    s3.metric("Personal Best", f"{summary.get('best_score', 0.0):.1f}")
    s4.metric("Avg Fillers / Speech", f"{summary.get('avg_fillers', 0.0):.1f}")
    s5.metric("Avg WPM Pacing", f"{summary.get('avg_wpm', 0.0):.0f}")

    st.markdown("---")
    st.subheader("📜 Past Speech Evaluations")

    if speeches:
        for idx, sp in enumerate(speeches):
            with st.expander(f"Speech #{len(speeches)-idx}: {sp['created_at']} — Score: {sp['overall_score']} pts ({sp['overall_grade']})"):
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"⏱️ **Duration:** {sp['formatted_duration']}")
                c2.write(f"🏃 **Pacing:** {sp['wpm']:.0f} WPM ({sp['pacing_rating']})")
                c3.write(f"🗣️ **Fillers:** {sp['total_fillers']} (Pauses: {sp['vocalized_pauses']}, Crutches: {sp['verbal_crutches']})")
                c4.write(f"📖 **Grammar Errors:** {sp['grammar_errors']}")

                t_text = sp.get("transcript", "")
                if not t_text:
                    rep_path = sp.get("report_file", "")
                    if rep_path and os.path.exists(rep_path):
                        sp_rep = load_report_file(rep_path)
                        if sp_rep:
                            t_text = sp_rep.get("transcript_summary", {}).get("full_transcript", "")
                if t_text:
                    st.markdown(f"**Transcript:**\n> {t_text}")
    else:
        st.info("No recorded speeches found yet under your account. Step up to the podium and flip the switch to record your first speech!")


# ==============================================================================
# VIEW 3: ADMIN DIRECTORY & ANALYTICS (Master Password Protected)
# ==============================================================================
elif current_view == "👥 Student Directory & Analytics":
    st.markdown('<div class="main-header">👥 Toastmasters Student Directory</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Master Administrator Roster and Performance Tracking</div>', unsafe_allow_html=True)

    all_students = db.get_all_students()
    all_sessions = db.get_all_speech_sessions()

    # Club summary
    m1, m2, m3 = st.columns(3)
    m1.metric("Registered Students", len(all_students))
    m2.metric("Total Club Speeches", len(all_sessions))
    avg_club_score = (
        round(sum(s["overall_score"] for s in all_sessions) / max(1, len(all_sessions)), 1)
        if all_sessions
        else 0.0
    )
    m3.metric("Club Average Score", f"{avg_club_score} pts")

    st.markdown("---")
    st.subheader("📋 Student Roster & Summary")

    if all_students:
        st.dataframe(
            [
                {
                    "Name": s["full_name"],
                    "Username": f"@{s['username']}",
                    "Speeches Given": s["speech_count"],
                    "Avg Score": s["avg_score"],
                    "Total Fillers Logged": s["total_fillers_sum"],
                    "Avg WPM": s["avg_wpm"],
                    "Registered Date": s["created_at"],
                }
                for s in all_students
            ],
            use_container_width=True,
        )
    else:
        st.info("No students registered yet. Students can register anytime using the registration form.")


# ==============================================================================
# VIEW 4: ADMIN ALL SPEECH RECORDS
# ==============================================================================
elif current_view == "📋 All Speech Records":
    st.markdown('<div class="main-header">📋 Master Speech Session Log</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Complete historical audit trail of all speeches recorded by the evaluator</div>', unsafe_allow_html=True)

    all_sessions = db.get_all_speech_sessions()

    if all_sessions:
        st.dataframe(
            [
                {
                    "Session ID": s["session_id"],
                    "Speaker Name": s["full_name"],
                    "Username": f"@{s['username']}",
                    "Score": s["overall_score"],
                    "Grade": s["overall_grade"],
                    "Duration": s["formatted_duration"],
                    "Words": s["total_words"],
                    "WPM": f"{s['wpm']:.0f}",
                    "Pacing": s["pacing_rating"],
                    "Fillers": s["total_fillers"],
                    "Grammar Errors": s["grammar_errors"],
                    "Date & Time": s["created_at"],
                }
                for s in all_sessions
            ],
            use_container_width=True,
        )
    else:
        st.info("No speech sessions recorded yet in database.")

    # History Management Section
    st.markdown("---")
    st.subheader("⚙️ History Management")
    with st.expander("🗑️ Clear / Reset All Speech Records & Reports", expanded=False):
        st.warning(
            "⚠️ **Danger Zone:** This will permanently delete all past speech sessions, "
            "archived report JSON files, and database records. "
            "Registered student user accounts and passwords will remain safe."
        )
        confirm_clear = st.checkbox("I confirm I want to permanently delete all speech history.")
        if st.button("🗑️ Delete All Speech History Now", type="primary", disabled=not confirm_clear, use_container_width=True):
            deleted_db = db.clear_all_speeches()
            purged_files = 0
            for rf in glob.glob("reports/speech_report_*.json") + glob.glob("reports/evaluation_report.json"):
                try:
                    if os.path.exists(rf):
                        os.remove(rf)
                        purged_files += 1
                except Exception:
                    pass
            if os.path.exists("evaluation_report.json"):
                try:
                    os.remove("evaluation_report.json")
                    purged_files += 1
                except Exception:
                    pass
            st.success(f"Cleaned {deleted_db} database record(s) and purged {purged_files} report file(s)!")
            time.sleep(1.0)
            st.rerun()


# ------------------------------------------------------------------------------
# 8. Footer
# ------------------------------------------------------------------------------
st.markdown("---")
st.caption("AI Speech Evaluator for Toastmasters | Auto-refreshing every 3 seconds")
