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
        padding: 1.5rem;
        font-size: 1.12rem;
        line-height: 2.3;
        min-height: 180px;
        position: relative;
        overflow: visible !important;
    }
    .grammar-highlight {
        position: relative;
        display: inline-block;
        background-color: rgba(220, 53, 69, 0.16);
        color: #e63946;
        border-bottom: 2.5px wavy #d90429;
        padding: 1px 5px;
        border-radius: 4px;
        font-weight: 600;
        cursor: pointer;
    }
    .grammar-highlight:hover {
        background-color: rgba(220, 53, 69, 0.28);
    }
    .grammar-highlight:hover .grammar-tooltip {
        display: block !important;
        opacity: 1 !important;
        visibility: visible !important;
        transform: translateX(-50%) translateY(0) !important;
    }
    .grammar-tooltip {
        display: none;
        position: absolute;
        bottom: calc(100% + 8px);
        left: 50%;
        transform: translateX(-50%) translateY(6px);
        width: 290px;
        background: #181c24;
        color: #f1f5f9;
        padding: 12px 14px;
        border-radius: 8px;
        font-size: 0.85rem;
        line-height: 1.45;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(255, 255, 255, 0.16);
        z-index: 999999;
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


def build_highlighted_transcript(full_transcript: str, issues: List[Dict[str, Any]]) -> str:
    """
    Produce HTML for the transcript where each grammatical error is underlined with
    a red wavy line and features a Grammarly-style hover popover card explaining
    the rule and suggesting corrections.
    """
    if not full_transcript:
        return ""
    if not issues:
        return html.escape(full_transcript)

    replacements = []
    lower_transcript = full_transcript.lower()

    for idx, issue in enumerate(issues):
        context_text = issue.get("context_text", "")
        c_off = int(issue.get("context_offset", 0))
        c_len = int(issue.get("length", 0))
        sentence = issue.get("sentence", "")
        off = int(issue.get("offset", 0))

        err_phrase = ""
        # 1. Try extracting from context_text
        if context_text and 0 <= c_off < len(context_text) and c_len > 0:
            err_phrase = context_text[c_off : c_off + c_len].strip()
        # 2. Try extracting from sentence
        if not err_phrase and sentence and 0 <= off < len(sentence) and c_len > 0:
            err_phrase = sentence[off : off + c_len].strip()

        if not err_phrase:
            continue

        # Locate err_phrase in full_transcript
        lower_err = err_phrase.lower()
        pos = lower_transcript.find(lower_err)
        if pos != -1:
            end_pos = pos + len(err_phrase)
            actual_err_word = full_transcript[pos:end_pos]
            replacements.append((pos, end_pos, actual_err_word, issue, idx))

    if not replacements:
        return html.escape(full_transcript)

    # Sort replacements in reverse order (right-to-left) to preserve character offsets
    replacements.sort(key=lambda x: x[0], reverse=True)

    # Filter out any overlapping slices
    filtered = []
    last_start = float("inf")
    for start, end, actual_err_word, issue, idx in replacements:
        if end <= last_start:
            filtered.append((start, end, actual_err_word, issue, idx))
            last_start = start

    # Construct the HTML
    result = []
    cursor = len(full_transcript)
    for start, end, actual_err_word, issue, idx in filtered:
        # Text between this error and the next (or end)
        result.append(html.escape(full_transcript[end:cursor]))

        rule_id = html.escape(issue.get("rule_id", "Grammar Rule"))
        msg = html.escape(issue.get("message", "Grammar rule opportunity."))
        suggestions = issue.get("suggestions", [])

        sug_html = ""
        if suggestions:
            pills = "".join(
                [f"<span class='tooltip-suggestion'>{html.escape(s)}</span>" for s in suggestions[:3]]
            )
            sug_html = f"<div style='margin-top:6px;'><b>Suggested Fix:</b> {pills}</div>"

        esc_word = html.escape(actual_err_word)
        tooltip_card = (
            f"<span class='grammar-highlight' title='{rule_id}: {msg}'>"
            f"{esc_word}"
            f"<span class='grammar-tooltip'>"
            f"<span class='tooltip-badge'>Issue #{idx+1} · {rule_id}</span>"
            f"<div class='tooltip-msg'>{msg}</div>"
            f"{sug_html}"
            f"</span>"
            f"</span>"
        )
        result.append(tooltip_card)
        cursor = start

    # Add text before the first error
    result.append(html.escape(full_transcript[:cursor]))
    result.reverse()
    return "".join(result)


def render_speech_details(sp: Dict[str, Any]) -> None:
    """Render full metrics, disfluencies, and transcript with Grammarly cards for a past speech record."""
    c1, c2, c3, c4 = st.columns(4)
    c1.write(f"⏱️ **Duration:** {sp.get('formatted_duration', '00:00')}")
    c2.write(f"🏃 **Pacing:** {sp.get('wpm', 0.0):.0f} WPM ({sp.get('pacing_rating', 'Normal')})")
    c3.write(f"🗣️ **Fillers:** {sp.get('total_fillers', 0)} (Pauses: {sp.get('vocalized_pauses', 0)}, Crutches: {sp.get('verbal_crutches', 0)})")
    c4.write(f"📖 **Grammar Errors:** {sp.get('grammar_errors', 0)}")

    archive_file = os.path.join("reports", f"speech_report_{sp['session_id']}.json")
    if not os.path.exists(archive_file) and sp.get("report_file"):
        archive_file = sp["report_file"]

    past_rep = load_report_file(archive_file) if os.path.exists(archive_file) else None

    t_text = sp.get("transcript", "")
    past_issues = []
    if past_rep:
        t_text = past_rep.get("transcript_summary", {}).get("full_transcript", t_text)
        past_issues = past_rep.get("grammarian", {}).get("issues", [])
        past_ah = past_rep.get("ah_counter", {})
        freq = past_ah.get("frequency_breakdown", {})
        if freq:
            top_f = ", ".join([f"`{k}` ({v}x)" for k, v in freq.items()])
            st.markdown(f"**Top Disfluencies:** {top_f}")

    if t_text:
        if past_issues:
            st.markdown("**Transcript & Grammar Review (Hover over red highlights for insights):**")
            st.markdown(
                f"<div class='transcript-box'>{build_highlighted_transcript(t_text, past_issues)}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"**Transcript:**\n> {t_text}")
    else:
        st.caption("No transcript recorded for this session.")


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
    # Strictly target the active live evaluation report (no fallback to archived history)
    selected_file = "evaluation_report.json"

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

    # Navigation guidance notice
    hist_dest = "📊 My Speech History" if st.session_state["user_role"] != "admin" else "📋 All Speech Records"
    st.caption(
        f"💡 **Looking for past speech reports?** This screen strictly tracks the current live speech. "
        f"Switch to **'{hist_dest}'** in the navigation menu (open sidebar with `>` on mobile) to view and inspect previous evaluations."
    )

    # --------------------------------------------------------------------------
    # Active Speaker indicator & Admin Podium Assignment
    # --------------------------------------------------------------------------
    active_speaker = db.get_active_speaker()

    if st.session_state["user_role"] == "admin":
        with st.expander(f"🎤 Podium Speaker Assignment · Current: **{active_speaker['full_name']}**", expanded=True):
            col_adm1, col_adm2 = st.columns([2, 1])
            with col_adm1:
                all_students = db.get_all_students()
                options = ["Guest Speaker", "Custom Guest Speaker..."] + [
                    f"{s['full_name']} (@{s['username']})" for s in all_students
                ]

                # Determine active index
                if active_speaker["username"] == "guest":
                    if active_speaker["full_name"] == "Guest Speaker":
                        curr_idx = 0
                    else:
                        curr_idx = 1
                else:
                    target_str = f"{active_speaker['full_name']} (@{active_speaker['username']})"
                    curr_idx = options.index(target_str) if target_str in options else 0

                sel_speaker = st.selectbox(
                    "Select Active Speaker at Podium (Admin Decides):",
                    options,
                    index=curr_idx,
                    help="Only the Admin can assign who is delivering a speech at the physical podium.",
                )

                custom_guest_name = ""
                if sel_speaker == "Custom Guest Speaker...":
                    prev_name = active_speaker["full_name"] if active_speaker["username"] == "guest" else "Guest Speaker"
                    custom_guest_name = st.text_input("Guest Speaker Full Name:", value=prev_name)

            with col_adm2:
                st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
                if st.button("🎤 Assign to Podium", type="primary", use_container_width=True):
                    if sel_speaker == "Guest Speaker":
                        db.set_active_speaker("guest", "Guest Speaker")
                        st.success("Podium assigned to: Guest Speaker")
                    elif sel_speaker == "Custom Guest Speaker...":
                        g_clean = custom_guest_name.strip() or "Guest Speaker"
                        db.set_active_speaker("guest", g_clean)
                        st.success(f"Podium assigned to: {g_clean}")
                    else:
                        s_uname = sel_speaker.split("(@")[-1].replace(")", "").strip()
                        s_fname = sel_speaker.split(" (@")[0].strip()
                        db.set_active_speaker(s_uname, s_fname)
                        st.success(f"Podium assigned to: {s_fname}")

                    # Reset evaluation report so the new speaker starts with score 0
                    for f in ["evaluation_report.json", os.path.join("reports", "evaluation_report.json")]:
                        if os.path.exists(f):
                            try:
                                os.remove(f)
                            except Exception:
                                pass

                    time.sleep(0.3)
                    st.rerun()

        with st.expander("🧪 Test Speech Simulator (Admin Evaluation Tool)", expanded=False):
            st.caption("Instantly test Grammarian error detection and Ah-Counter without speaking into the microphone.")
            test_sample_text = st.text_area(
                "Speech text with grammatical errors to test:",
                value="Good morning fellow Toastmasters um today they was very happy and we goes to the conference like you know.",
                height=80,
                key="test_speech_input",
            )
            if st.button("▶️ Run Test Speech Evaluation", use_container_width=True):
                from services.ah_counter import AhCounter
                from services.grammarian import GrammarianEngine
                from services.report_generator import ReportGenerator

                sim_ah = AhCounter()
                words = test_sample_text.split()
                sim_words = []
                for idx, w in enumerate(words):
                    clean = w.strip(".,?!")
                    sim_words.append({
                        "word": clean,
                        "punctuated_word": w,
                        "start": round(idx * 0.4, 2),
                        "end": round(idx * 0.4 + 0.3, 2),
                        "confidence": 0.98,
                    })
                sim_ah.process_words(sim_words)

                sim_gram = GrammarianEngine()
                sim_issues = sim_gram.check_text_sync(test_sample_text)
                sim_gram._issues = sim_issues

                sim_rep_gen = ReportGenerator()
                rep_path, rep_data = sim_rep_gen.generate(
                    session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
                    start_time=time.time() - 30.0,
                    end_time=time.time(),
                    full_transcript=test_sample_text,
                    ah_counter=sim_ah,
                    grammarian=sim_gram,
                )
                db.record_speech_session(rep_data, "evaluation_report.json")
                st.success("Test speech evaluated! Refreshing...")
                time.sleep(0.5)
                st.rerun()
    else:
        # Students / Viewers see the podium speaker assigned by the Admin
        st.info(
            f"🎤 **Active Speaker at Podium:** **{active_speaker['full_name']}** "
            f"(`@{active_speaker['username']}`) · *Assigned by Admin*"
        )

    report = load_report_file(selected_file) if selected_file and os.path.exists(selected_file) else None

    # Strict Speaker Attribution: If report on disk was generated BEFORE current speaker was assigned, ignore it!
    if report:
        rep_time = report.get("generated_at", "")
        assigned_time = active_speaker.get("updated_at", "")
        if assigned_time and rep_time and rep_time < assigned_time:
            report = None

    if not report:
        # Ready / Zero State (Awaiting speech capture for active speaker)
        session_id = "Awaiting Delivery"
        overall_score = 0.0
        overall_grade = "Ready (Awaiting Delivery)"
        timing = {"formatted_duration": "00:00", "timing_status": "Ready for Speech"}
        transcript_summary = {"words_per_minute": 0.0, "pacing_rating": "Ready", "full_transcript": ""}
        ah_counter = {
            "total_fillers": 0,
            "vocalized_pauses_count": 0,
            "verbal_crutches_count": 0,
            "fillers_per_minute": 0.0,
            "frequency_breakdown": {},
            "timeline_events": [],
        }
        grammarian = {
            "total_errors": 0,
            "error_density_per_100_words": 0.0,
            "issues": [],
        }
        evaluation = {
            "summary": [
                f"Speaker '{active_speaker['full_name']}' is assigned to the podium.",
                "Step up to the microphone, toggle the physical switch ON (GPIO 18) to begin, and toggle OFF when done.",
                "Real-time duration is shown on the 16x2 LCD screen.",
                "Evaluation score and breakdown will display automatically once speech is finished.",
            ]
        }
        st.info(
            f"🎙️ **Podium Ready for {active_speaker['full_name']}** · "
            f"Flip the physical toggle switch **ON** to start your speech. "
            f"Evaluation and score will populate automatically once the speech is finished!"
        )
    else:
        # Link report to database: ALWAYS attributes to the active speaker assigned by Admin!
        if selected_file == "evaluation_report.json" or "reports" in selected_file:
            db.record_speech_session(report, selected_file)

        # Extract Data
        session_id = report.get("session_id", "N/A")
        timing = report.get("timing", {})
        transcript_summary = report.get("transcript_summary", {})
        ah_counter = report.get("ah_counter", {})
        grammarian = report.get("grammarian", {})
        evaluation = report.get("toastmasters_evaluation", {})

        overall_score = report.get("overall_score", evaluation.get("overall_score", 0.0))
        overall_grade = report.get("overall_grade", evaluation.get("overall_grade", "Awaiting Delivery"))

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
        if not report:
            st.info(
                f"🎙️ **Ready for {active_speaker['full_name']}.** "
                f"Flip the physical toggle switch ON at the podium to start recording. "
                f"The transcribed speech and grammar evaluations will appear here as soon as you finish!"
            )
        else:
            st.warning(
                "⚠️ **No words were detected in this audio recording.**\n\n"
                "If you spoke into the microphone, check:\n"
                "1. Is the physical switch on the M-305 microphone handle switched to **ON**?\n"
                "2. Is the microphone cable plugged into the **MIC (pink)** input jack of the USB adapter?\n"
                "3. Is the microphone unmuted in **alsamixer**? (Run `alsamixer`, press `F4` for Capture, press `Space` to unmute, and press `Up Arrow` to raise gain)."
            )
    else:
        # Build Grammarly-style highlighted transcript with hover cards
        highlighted_html = build_highlighted_transcript(full_transcript, issues)

        t_col1, t_col2 = st.columns([3, 2])

        with t_col1:
            st.markdown("**Transcript (Hover over red highlights for Grammarly-style insights):**")
            st.markdown(
                f"""
                <div class="transcript-box">
                    {highlighted_html}
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

    tab_my, tab_all = st.tabs(["👤 My Personal Speeches", "🌐 All Meeting Speeches (Including Guests)"])

    with tab_my:
        st.markdown(f"#### Personal Speech Log (`@{st.session_state['username']}`)")
        if speeches:
            for idx, sp in enumerate(speeches):
                with st.expander(f"Speech #{len(speeches)-idx}: {sp['created_at']} — Score: {sp['overall_score']} pts ({sp['overall_grade']})"):
                    render_speech_details(sp)
        else:
            st.info(
                f"No recorded speeches found under `@{st.session_state['username']}` yet. "
                "If you delivered a speech while the podium was set to 'Guest Speaker' (or before logging in), "
                "switch to the **'🌐 All Meeting Speeches'** tab above to view and inspect it!"
            )

    with tab_all:
        st.markdown("#### All Speech Sessions (Club Audit Trail)")
        all_club = db.get_all_speech_sessions()
        if all_club:
            st.caption(f"Displaying all {len(all_club)} speech session(s) recorded in the evaluator:")
            for idx, sp in enumerate(all_club):
                with st.expander(
                    f"[{sp['session_id']}] {sp['full_name']} (@{sp['username']}) — {sp['created_at']} — Score: {sp['overall_score']} pts ({sp['overall_grade']})"
                ):
                    render_speech_details(sp)
        else:
            st.info("No speech sessions recorded yet in the system.")


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

        st.markdown("---")
        st.subheader("🎤 Quick Podium Assignment")
        q_options = ["Guest Speaker"] + [f"{s['full_name']} (@{s['username']})" for s in all_students]
        q_sel = st.selectbox("Assign Student or Guest to Podium:", q_options, key="q_podium")
        if st.button("Set as Active Podium Speaker", key="btn_q_podium"):
            if q_sel == "Guest Speaker":
                db.set_active_speaker("guest", "Guest Speaker")
                st.success("Assigned Guest Speaker to podium!")
            else:
                s_u = q_sel.split("(@")[-1].replace(")", "").strip()
                s_f = q_sel.split(" (@")[0].strip()
                db.set_active_speaker(s_u, s_f)
                st.success(f"Assigned {s_f} to podium!")

            # Reset evaluation report so the new speaker starts with score 0
            for f in ["evaluation_report.json", os.path.join("reports", "evaluation_report.json")]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            time.sleep(0.3)
            st.rerun()
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

        st.markdown("---")
        st.subheader("🔍 Inspect Detailed Speech Report")
        session_opts = [
            f"{s['session_id']} — {s['full_name']} ({s['created_at']}, {s['overall_score']:.0f} pts)"
            for s in all_sessions
        ]
        chosen_opt = st.selectbox("Select Past Speech to Inspect:", session_opts)
        chosen_sid = chosen_opt.split(" — ")[0].strip()
        chosen_sp = next((s for s in all_sessions if s["session_id"] == chosen_sid), None)

        if chosen_sp:
            st.markdown(f"##### Speech Session: `{chosen_sp['session_id']}` · Speaker: **{chosen_sp['full_name']}** (`@{chosen_sp['username']}`)")
            render_speech_details(chosen_sp)
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
