"""
StackForge POC — Streamlit UI (redesigned for demos)

5 tabs:
  1. Setup          — select or create a client/project
  2. Upload         — upload docs, watch pipeline progress
  3. Requirements   — browse extracted requirements with chart
  4. Documents      — view & edit SDLC topic docs
  5. Clarifications — answer open questions, run RAG queries
"""

import sys
import os
import json as _json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="StackForge — AI SDLC Automation",
    page_icon="⚙️",
    layout="wide",
)

# ─── Design system constants ──────────────────────────────────────────────────

TYPE_META = {
    "functional":     ("⚡", "Functional",     "blue"),
    "non_functional": ("🔒", "Non-Functional",  "violet"),
    "constraint":     ("📌", "Constraint",      "amber"),
    "assumption":     ("💭", "Assumption",      "slate"),
}
TYPE_ORDER = ["functional", "non_functional", "constraint", "assumption"]

SDLC_META = {
    "requirements":     ("📋", "Requirements",    "#4f8ef7", "blue"),
    "design":           ("🎨", "Design",           "#a78bfa", "violet"),
    "technical":        ("⚙️",  "Technical",        "#22d3ee", "blue"),
    "timeline":         ("📅", "Timeline",         "#34d399", "teal"),
    "budget":           ("💰", "Budget",           "#fb923c", "amber"),
    "testing":          ("🧪", "Testing",          "#f87171", "rose"),
    "integrations":     ("🔗", "Integrations",     "#60a5fa", "blue"),
    "team_and_process": ("👥", "Team & Process",   "#94a3b8", "slate"),
}
SDLC_ORDER = [
    "requirements", "design", "technical", "timeline",
    "budget", "testing", "integrations", "team_and_process",
]

SDLC_TOPICS_UI = SDLC_ORDER
TOPIC_LABELS_UI = {k: f"{v[0]} {v[1]}" for k, v in SDLC_META.items()}

PRIORITY_STYLES = {
    "high":   ("rose",  "#f43f5e"),
    "medium": ("amber", "#f59e0b"),
    "low":    ("teal",  "#00d4aa"),
}

SDLC_COLORS_PLOTLY = {k: v[2] for k, v in SDLC_META.items()}

# ─── CSS injection ────────────────────────────────────────────────────────────

STYLES = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stMarkdown, .stText, p, div, span, label {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}

/* ── Tab bar: pill style ───────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #1a1d2e;
    padding: 6px 8px;
    border-radius: 12px;
    border: 1px solid #2e3250;
    margin-bottom: 8px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 500;
    font-size: 0.875rem;
    color: #8b92a5;
    background: transparent;
    border: none;
    transition: all 0.15s ease;
}
.stTabs [aria-selected="true"] {
    background: #4f8ef7 !important;
    color: #ffffff !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none; }
.stTabs [data-baseweb="tab-border"] { display: none; }

/* ── Hero header ───────────────────────────────────────────────────── */
.sf-hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 28px;
    background: linear-gradient(135deg, #1a1d2e 0%, #1e2240 60%, #1a2035 100%);
    border: 1px solid #2e3250;
    border-radius: 16px;
    margin-bottom: 20px;
}
.sf-hero-left {}
.sf-hero-logo {
    font-size: 1.45rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #e8eaf0;
    margin: 0;
}
.sf-hero-logo .accent { color: #4f8ef7; }
.sf-hero-sub {
    font-size: 0.78rem;
    color: #8b92a5;
    margin-top: 3px;
}
.sf-hero-badge {
    background: rgba(79,142,247,0.1);
    border: 1px solid rgba(79,142,247,0.3);
    border-radius: 8px;
    padding: 8px 14px;
    text-align: right;
}
.sf-hero-badge-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #8b92a5;
}
.sf-hero-badge-value {
    font-size: 0.9rem;
    font-weight: 600;
    color: #4f8ef7;
    margin-top: 2px;
}

/* ── Cards ─────────────────────────────────────────────────────────── */
.sf-card {
    background: #1a1d2e;
    border: 1px solid #2e3250;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 10px;
    transition: border-color 0.15s ease;
}
.sf-card-active {
    border-color: #4f8ef7 !important;
    box-shadow: 0 0 0 1px rgba(79,142,247,0.15);
}
.sf-card-title {
    font-size: 0.9rem;
    font-weight: 500;
    color: #e8eaf0;
    margin-bottom: 4px;
}
.sf-card-meta {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 8px;
    align-items: center;
}
.sf-card-desc {
    font-size: 0.8rem;
    color: #8b92a5;
    line-height: 1.5;
    margin: 5px 0 8px;
}

/* ── Badges ─────────────────────────────────────────────────────────── */
.sf-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    white-space: nowrap;
}
.sf-badge-blue   { background: rgba(79,142,247,0.12); color: #4f8ef7; border: 1px solid rgba(79,142,247,0.25); }
.sf-badge-teal   { background: rgba(0,212,170,0.12);  color: #00d4aa; border: 1px solid rgba(0,212,170,0.25); }
.sf-badge-amber  { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.25); }
.sf-badge-rose   { background: rgba(244,63,94,0.12);  color: #f43f5e; border: 1px solid rgba(244,63,94,0.25); }
.sf-badge-violet { background: rgba(167,139,250,0.12);color: #a78bfa; border: 1px solid rgba(167,139,250,0.25); }
.sf-badge-slate  { background: rgba(148,163,184,0.08);color: #94a3b8; border: 1px solid rgba(148,163,184,0.18); }
.sf-badge-green  { background: rgba(0,212,170,0.12);  color: #00d4aa; border: 1px solid rgba(0,212,170,0.25); }

/* ── Metric tiles ───────────────────────────────────────────────────── */
.sf-metric {
    background: #1a1d2e;
    border: 1px solid #2e3250;
    border-radius: 10px;
    padding: 14px 16px;
    text-align: center;
}
.sf-metric-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #e8eaf0;
    line-height: 1.2;
}
.sf-metric-label {
    font-size: 0.68rem;
    color: #8b92a5;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Pipeline step tracker ──────────────────────────────────────────── */
.sf-pipeline {
    display: flex;
    align-items: flex-start;
    gap: 0;
    margin: 18px 0;
    padding: 16px 20px;
    background: #1a1d2e;
    border: 1px solid #2e3250;
    border-radius: 12px;
}
.sf-step {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    position: relative;
}
.sf-step::after {
    content: '';
    position: absolute;
    top: 15px;
    left: 50%;
    width: 100%;
    height: 2px;
    background: #2e3250;
    z-index: 0;
}
.sf-step:last-child::after { display: none; }
.sf-step-done::after  { background: #00d4aa; }
.sf-step-active::after { background: linear-gradient(90deg, #4f8ef7, #2e3250); }
.sf-dot {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 600;
    position: relative;
    z-index: 1;
}
.sf-dot-done    { background: #00d4aa; color: #0f1117; }
.sf-dot-active  { background: #4f8ef7; color: #fff; box-shadow: 0 0 0 4px rgba(79,142,247,0.2); }
.sf-dot-pending { background: #2e3250; color: #4a5070; }
.sf-step-label {
    font-size: 0.65rem;
    color: #8b92a5;
    margin-top: 7px;
    text-align: center;
    white-space: nowrap;
}
.sf-step-done .sf-step-label   { color: #00d4aa; }
.sf-step-active .sf-step-label { color: #4f8ef7; }

/* ── Section headers ────────────────────────────────────────────────── */
.sf-section-header {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #8b92a5;
    padding-bottom: 8px;
    border-bottom: 1px solid #2e3250;
    margin-bottom: 14px;
}

/* ── Upload zone ────────────────────────────────────────────────────── */
.sf-upload-zone {
    border: 2px dashed #2e3250;
    border-radius: 12px;
    padding: 8px 16px 16px;
    margin-bottom: 16px;
    background: #1a1d2e;
    transition: border-color 0.2s ease;
}

/* ── CSS spinner (for Stitch generating state) ─────────────────────── */
@keyframes sf-spin { to { transform: rotate(360deg); } }
.sf-spinner {
    display: inline-block;
    width: 12px; height: 12px;
    border: 2px solid #2e3250;
    border-top-color: #4f8ef7;
    border-radius: 50%;
    animation: sf-spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 5px;
}

/* ── Form container ─────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: #1a1d2e;
    border: 1px solid #2e3250 !important;
    border-radius: 12px !important;
    padding: 4px 8px !important;
}

/* ── Buttons ────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"] {
    background: #4f8ef7 !important;
    border: none !important;
    color: #fff !important;
}
.stButton > button[kind="primary"]:hover {
    background: #3a7de8 !important;
    box-shadow: 0 4px 14px rgba(79,142,247,0.3) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid #2e3250 !important;
    color: #8b92a5 !important;
}

/* ── Expanders ──────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: #1a1d2e !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}

/* ── Misc ───────────────────────────────────────────────────────────── */
hr { border-color: #2e3250 !important; }
.stAlert { border-radius: 10px !important; }
[data-testid="stMetricValue"] { color: #e8eaf0 !important; }
"""


def inject_styles():
    st.markdown(f"<style>{STYLES}</style>", unsafe_allow_html=True)


inject_styles()

# ─── Helpers ─────────────────────────────────────────────────────────────────

def api_get(path: str) -> dict | list | None:
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, json: dict = None, files: dict = None) -> dict | list | None:
    try:
        r = httpx.post(f"{API_BASE}{path}", json=json, files=files, timeout=120)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def get_projects() -> list[dict]:
    return api_get("/projects") or []


def active_project_guard() -> str | None:
    pid = st.session_state.get("project_id")
    if not pid:
        st.markdown(
            '<div class="sf-card" style="text-align:center;padding:32px;">'
            '<div style="font-size:1.5rem;margin-bottom:8px;">🏗️</div>'
            '<div class="sf-card-title">No project selected</div>'
            '<div class="sf-card-desc" style="text-align:center;">'
            'Go to the <strong>Setup</strong> tab to select or create a project first.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return None
    return pid


def render_requirement_card(r: dict):
    conf_pct = int(r["confidence"] * 100)
    conf_class = "teal" if r["confidence"] >= 0.8 else "amber"
    topic = r.get("sdlc_topic") or "requirements"
    t_icon, t_label, t_color, _ = SDLC_META.get(topic, ("•", topic, "#94a3b8", "slate"))
    rt = r.get("req_type", "functional")
    rt_icon, rt_label, rt_class = TYPE_META.get(rt, ("•", rt, "slate"))
    desc = r.get("description", "")
    st.markdown(
        f'<div class="sf-card">'
        f'  <div class="sf-card-title">{r["title"]}</div>'
        f'  <div class="sf-card-desc">{desc}</div>'
        f'  <div class="sf-card-meta">'
        f'    <span class="sf-badge sf-badge-{conf_class}">{conf_pct}% confidence</span>'
        f'    <span class="sf-badge" style="background:rgba(255,255,255,0.04);color:{t_color};border-color:rgba(255,255,255,0.08)">'
        f'      {t_icon} {t_label}'
        f'    </span>'
        f'    <span class="sf-badge sf-badge-{rt_class}">{rt_icon} {rt_label}</span>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_status_badge(status: str) -> str:
    cls = {"done": "teal", "ready": "teal", "processing": "blue", "failed": "rose", "pending": "slate"}.get(
        status.lower(), "slate"
    )
    return f'<span class="sf-badge sf-badge-{cls}">{status.upper()}</span>'


# ─── Hero header ──────────────────────────────────────────────────────────────

def render_hero():
    pid = st.session_state.get("project_id")
    pname = st.session_state.get("project_name", "")
    if pid:
        badge_html = (
            f'<div class="sf-hero-badge">'
            f'  <div class="sf-hero-badge-label">Active Project</div>'
            f'  <div class="sf-hero-badge-value">{pname}</div>'
            f'</div>'
        )
    else:
        badge_html = (
            '<div class="sf-hero-badge" style="border-color:rgba(148,163,184,0.2);background:rgba(148,163,184,0.05);">'
            '  <div class="sf-hero-badge-label" style="color:#4a5070">Active Project</div>'
            '  <div class="sf-hero-badge-value" style="color:#4a5070">None selected</div>'
            '</div>'
        )
    st.markdown(
        f'<div class="sf-hero">'
        f'  <div class="sf-hero-left">'
        f'    <div class="sf-hero-logo">Stack<span class="accent">Forge</span></div>'
        f'    <div class="sf-hero-sub">AI-Powered SDLC Automation &nbsp;·&nbsp; Stackular Technologies</div>'
        f'  </div>'
        f'  {badge_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


render_hero()

# ─── Tab layout ───────────────────────────────────────────────────────────────

tab_setup, tab_upload, tab_review, tab_docs, tab_clarify = st.tabs([
    "🏗️  Setup",
    "📂  Upload",
    "📋  Requirements",
    "📄  Documents",
    "💬  Clarifications",
])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1: Setup
# ═══════════════════════════════════════════════════════════════════════════════

with tab_setup:
    st.markdown('<div class="sf-section-header">Projects</div>', unsafe_allow_html=True)
    st.caption("Select an existing project or create a new one to begin ingesting client documents.")

    projects = get_projects()

    # ── Existing projects grid ─────────────────────────────────────────────
    if projects:
        active_pid = st.session_state.get("project_id")
        cols = st.columns(min(len(projects), 3))
        for i, p in enumerate(projects):
            pid_str = str(p["id"])
            is_active = pid_str == active_pid
            border_style = "border-color: #4f8ef7; box-shadow: 0 0 0 1px rgba(79,142,247,0.15);" if is_active else ""
            status = p.get("status", "pending")
            status_badge = render_status_badge(status)
            created = str(p.get("created_at", ""))[:10]
            client = p.get("client_name", "")
            name = p.get("name", p.get("project_name", str(p["id"])))

            with cols[i % 3]:
                st.markdown(
                    f'<div class="sf-card" style="{border_style}">'
                    f'  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">'
                    f'    <div class="sf-card-title">{name}</div>'
                    f'    {status_badge}'
                    f'  </div>'
                    f'  <div style="font-size:0.75rem;color:#8b92a5;">{client}</div>'
                    f'  <div style="font-size:0.7rem;color:#4a5070;margin-top:3px;">Created {created}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                btn_label = "✓ Active" if is_active else "Make Active"
                btn_type = "secondary" if is_active else "primary"
                if st.button(btn_label, key=f"btn_activate_{pid_str}", type=btn_type, use_container_width=True, disabled=is_active):
                    st.session_state["project_id"] = pid_str
                    st.session_state["project_name"] = name
                    st.rerun()
    else:
        st.markdown(
            '<div class="sf-card" style="text-align:center;padding:28px;">'
            '<div style="color:#4a5070;font-size:0.85rem;">No projects yet — create one below.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sf-section-header">Create New Project</div>', unsafe_allow_html=True)

    # ── Create new project form ────────────────────────────────────────────
    with st.form("create_project_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            client_name = st.text_input("Client name", placeholder="e.g. CareFlow Health")
        with c2:
            project_name = st.text_input("Project name", placeholder="e.g. Telehealth Platform v2")
        submitted = st.form_submit_button("Create Project", type="primary", use_container_width=False)
        if submitted:
            if client_name and project_name:
                result = api_post("/projects", json={"client_name": client_name, "project_name": project_name})
                if result:
                    st.session_state["project_id"] = str(result["id"])
                    st.session_state["project_name"] = result.get("name", project_name)
                    st.success(f"Created **{result.get('name', project_name)}** — now active.")
                    st.rerun()
            else:
                st.warning("Enter both client name and project name.")

    # ── Active project banner ──────────────────────────────────────────────
    if "project_id" in st.session_state:
        pid = st.session_state["project_id"]
        pname = st.session_state.get("project_name", "")
        st.markdown(
            f'<div class="sf-card" style="margin-top:16px;border-color:#2e3250;">'
            f'  <div style="display:flex;align-items:center;justify-content:space-between;">'
            f'    <div>'
            f'      <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.08em;color:#8b92a5;margin-bottom:4px;">Active Project</div>'
            f'      <div class="sf-card-title" style="font-size:1rem;">{pname}</div>'
            f'      <div style="font-size:0.72rem;color:#4a5070;font-family:monospace;margin-top:2px;">{pid}</div>'
            f'    </div>'
            f'    <span class="sf-badge sf-badge-green">ACTIVE</span>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2: Upload
# ═══════════════════════════════════════════════════════════════════════════════

with tab_upload:
    st.markdown('<div class="sf-section-header">Upload & Ingest</div>', unsafe_allow_html=True)

    project_id = active_project_guard()
    if project_id:

        # ── Upload zone ────────────────────────────────────────────────────
        st.markdown('<div class="sf-upload-zone">', unsafe_allow_html=True)
        st.markdown("**Upload Client Documents**")
        st.caption("Supported: PDF, DOCX, TXT &nbsp;·&nbsp; Multi-file upload supported")
        uploaded = st.file_uploader(
            "Drop files here or click to browse",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="file_uploader",
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if uploaded:
            if st.button("🚀  Run AI Pipeline", key="btn_ingest", type="primary"):
                for f in uploaded:
                    with st.spinner(f"Uploading {f.name}…"):
                        files = {"file": (f.name, f.getvalue(), f.type)}
                        result = api_post(f"/projects/{project_id}/documents", files=files)
                    if result:
                        st.success(f"✓ {f.name} — pipeline started")

        st.divider()
        st.markdown('<div class="sf-section-header">Pipeline Status</div>', unsafe_allow_html=True)

        # ── Pipeline step tracker helper ───────────────────────────────────
        def _pipeline_steps_html(pipeline_status: str) -> str:
            steps = ["Parse", "Chunk", "Summarize", "Extract", "Clarify", "Embed"]
            if pipeline_status == "ready":
                done_up_to = len(steps)
                active_idx = -1
            elif pipeline_status == "processing":
                done_up_to = 2
                active_idx = 3
            else:
                done_up_to = 0
                active_idx = 0

            dots = ""
            for i, label in enumerate(steps):
                if i < done_up_to:
                    cls = "sf-step sf-step-done"
                    dot_cls = "sf-dot sf-dot-done"
                    dot_inner = "✓"
                elif i == active_idx:
                    cls = "sf-step sf-step-active"
                    dot_cls = "sf-dot sf-dot-active"
                    dot_inner = str(i + 1)
                else:
                    cls = "sf-step"
                    dot_cls = "sf-dot sf-dot-pending"
                    dot_inner = str(i + 1)
                dots += (
                    f'<div class="{cls}">'
                    f'  <div class="{dot_cls}">{dot_inner}</div>'
                    f'  <div class="sf-step-label">{label}</div>'
                    f'</div>'
                )
            return f'<div class="sf-pipeline">{dots}</div>'

        # ── Auto-refreshing fragment ───────────────────────────────────────
        @st.fragment(run_every=5)
        def _pipeline_status():
            _pid = st.session_state.get("project_id")
            if not _pid:
                return
            status = api_get(f"/projects/{_pid}/status")
            if not status:
                return

            ps = status["status"]

            # Step tracker
            st.markdown(_pipeline_steps_html(ps), unsafe_allow_html=True)

            # Metrics row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                status_cls = {"ready": "teal", "processing": "blue", "failed": "rose"}.get(ps, "slate")
                st.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">'
                    f'    <span class="sf-badge sf-badge-{status_cls}" style="font-size:0.8rem;padding:4px 10px;">{ps.upper()}</span>'
                    f'  </div>'
                    f'  <div class="sf-metric-label">Pipeline</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">{status["ready_count"]}<span style="font-size:1rem;color:#8b92a5;">/{status["document_count"]}</span></div>'
                    f'  <div class="sf-metric-label">Docs Ready</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">{status["requirement_count"]}</div>'
                    f'  <div class="sf-metric-label">Requirements</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col4:
                st.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">{status["clarification_count"]}</div>'
                    f'  <div class="sf-metric-label">Open Questions</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            if ps == "processing":
                st.info("Pipeline running — auto-refreshing every 5 seconds…")
            elif ps == "ready":
                st.success("Pipeline complete — switch to **Requirements** to review extracted items.")

            # Documents list
            docs = api_get(f"/projects/{_pid}/documents") or []
            if docs:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="sf-section-header">Uploaded Documents</div>', unsafe_allow_html=True)
                for doc in docs:
                    doc_status = doc["status"]
                    badge = render_status_badge(doc_status)
                    st.markdown(
                        f'<div class="sf-card" style="padding:10px 16px;margin-bottom:6px;">'
                        f'  <div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'    <span style="font-size:0.85rem;color:#e8eaf0;">{doc["filename"]}</span>'
                        f'    {badge}'
                        f'  </div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        _pipeline_status()


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3: Requirements
# ═══════════════════════════════════════════════════════════════════════════════

with tab_review:
    st.markdown('<div class="sf-section-header">Extracted Requirements</div>', unsafe_allow_html=True)

    project_id = active_project_guard()
    if project_id:
        reqs = api_get(f"/projects/{project_id}/requirements") or []

        if not reqs:
            st.markdown(
                '<div class="sf-card" style="text-align:center;padding:32px;">'
                '<div style="font-size:1.4rem;margin-bottom:8px;">📋</div>'
                '<div class="sf-card-title">No requirements yet</div>'
                '<div class="sf-card-desc" style="text-align:center;">Upload documents and run the pipeline to extract requirements.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # ── Summary metric tiles ───────────────────────────────────────
            type_counts = Counter(r["req_type"] for r in reqs)
            sdlc_counts = Counter((r.get("sdlc_topic") or "requirements") for r in reqs)

            m1, m2, m3, m4 = st.columns(4)
            def _metric_tile(col, value, label):
                col.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">{value}</div>'
                    f'  <div class="sf-metric-label">{label}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            _metric_tile(m1, len(reqs), "Total")
            _metric_tile(m2, type_counts.get("functional", 0), "Functional")
            _metric_tile(m3, type_counts.get("non_functional", 0), "Non-Functional")
            _metric_tile(m4, type_counts.get("constraint", 0) + type_counts.get("assumption", 0), "Constraints & Assumptions")

            # ── Plotly SDLC chart ──────────────────────────────────────────
            try:
                import plotly.graph_objects as go
                chart_topics = [t for t in SDLC_ORDER if sdlc_counts.get(t, 0) > 0]
                chart_values = [sdlc_counts[t] for t in chart_topics]
                chart_colors = [SDLC_COLORS_PLOTLY.get(t, "#94a3b8") for t in chart_topics]
                chart_labels = [SDLC_META[t][1] for t in chart_topics]

                fig = go.Figure(go.Bar(
                    x=chart_labels,
                    y=chart_values,
                    marker_color=chart_colors,
                    text=chart_values,
                    textposition="outside",
                    textfont=dict(color="#8b92a5", size=11),
                ))
                fig.update_layout(
                    height=200,
                    margin=dict(t=10, b=30, l=0, r=0),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#8b92a5", size=11, family="Inter, system-ui"),
                    xaxis=dict(showgrid=False, tickfont=dict(color="#8b92a5")),
                    yaxis=dict(showgrid=False, visible=False),
                    bargap=0.35,
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            except ImportError:
                pass  # Plotly not available — skip chart

            st.divider()

            # ── View toggle ────────────────────────────────────────────────
            tv1, tv2, _ = st.columns([1.1, 1.3, 6])
            view = st.session_state.get("req_view_mode_v2", "type")
            with tv1:
                if st.button("By Type", key="btn_view_type",
                             type="primary" if view == "type" else "secondary"):
                    st.session_state["req_view_mode_v2"] = "type"
                    st.rerun()
            with tv2:
                if st.button("By SDLC Topic", key="btn_view_sdlc",
                             type="primary" if view == "sdlc" else "secondary"):
                    st.session_state["req_view_mode_v2"] = "sdlc"
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            if view == "type":
                grouped: dict[str, list] = {t: [] for t in TYPE_ORDER}
                for r in reqs:
                    grouped.setdefault(r["req_type"], []).append(r)

                for req_type in TYPE_ORDER:
                    items = grouped.get(req_type, [])
                    if not items:
                        continue
                    icon, label, _ = TYPE_META[req_type]
                    with st.expander(f"{icon}  {label} — {len(items)} items", expanded=(req_type == "functional")):
                        for r in items:
                            render_requirement_card(r)
            else:
                sdlc_grouped: dict[str, list] = {t: [] for t in SDLC_ORDER}
                for r in reqs:
                    sdlc_grouped.setdefault(r.get("sdlc_topic") or "requirements", []).append(r)

                for i, topic in enumerate(SDLC_ORDER):
                    items = sdlc_grouped.get(topic, [])
                    if not items:
                        continue
                    t_icon, t_label, _, _ = SDLC_META[topic]
                    with st.expander(f"{t_icon}  {t_label} — {len(items)} items", expanded=(i == 0)):
                        for r in items:
                            render_requirement_card(r)

            # ── Export ─────────────────────────────────────────────────────
            st.markdown("<br>", unsafe_allow_html=True)
            _, export_col = st.columns([5, 1])
            with export_col:
                st.download_button(
                    "⬇️ Export JSON",
                    data=_json.dumps(
                        [{k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                          for k, v in r.items()} for r in reqs],
                        indent=2,
                    ),
                    file_name="requirements.json",
                    mime="application/json",
                    use_container_width=True,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 4: Documents
# ═══════════════════════════════════════════════════════════════════════════════

with tab_docs:
    st.markdown('<div class="sf-section-header">SDLC Topic Documents</div>', unsafe_allow_html=True)

    project_id = active_project_guard()
    if project_id:
        doc_meta = api_get(f"/projects/{project_id}/docs") or []
        existing = {d["topic"] for d in doc_meta if d.get("exists")}

        if not existing:
            st.markdown(
                '<div class="sf-card" style="text-align:center;padding:32px;">'
                '<div style="font-size:1.4rem;margin-bottom:8px;">📄</div>'
                '<div class="sf-card-title">No documents generated yet</div>'
                '<div class="sf-card-desc" style="text-align:center;">Upload documents and run the pipeline — SDLC docs are created automatically.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # ── Topic pill grid ────────────────────────────────────────────
            available_topics = [t for t in SDLC_TOPICS_UI if t in existing]
            # Ensure there's always a default selected topic in session state
            if "doc_topic_active" not in st.session_state or st.session_state["doc_topic_active"] not in available_topics:
                st.session_state["doc_topic_active"] = available_topics[0]

            topic_cols = st.columns(len(available_topics))
            for i, topic in enumerate(available_topics):
                is_active = st.session_state["doc_topic_active"] == topic
                with topic_cols[i]:
                    if st.button(
                        TOPIC_LABELS_UI[topic],
                        key=f"btn_topic_{topic}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["doc_topic_active"] = topic
                        st.rerun()

            selected_topic = st.session_state["doc_topic_active"]
            st.markdown("<br>", unsafe_allow_html=True)

            col_left, col_right = st.columns([3, 2])

            with col_left:
                if selected_topic:
                    # Metadata bar
                    meta_row = next((d for d in doc_meta if d["topic"] == selected_topic), None)
                    if meta_row:
                        modified = str(meta_row.get("last_modified", ""))[:19].replace("T", " ")
                        size = meta_row.get("size_bytes", 0)
                        st.markdown(
                            f'<div class="sf-card-meta" style="margin-bottom:10px;">'
                            f'  <span class="sf-badge sf-badge-slate">Modified {modified} UTC</span>'
                            f'  <span class="sf-badge sf-badge-slate">{size:,} bytes</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    doc = api_get(f"/projects/{project_id}/docs/{selected_topic}")
                    if doc:
                        view_raw = st.toggle("Show raw markdown", key="doc_raw_toggle")
                        if view_raw:
                            st.code(doc["content"], language="markdown")
                        else:
                            st.markdown(doc["content"])

            with col_right:
                st.markdown(
                    '<div class="sf-card-title" style="margin-bottom:6px;">Edit this Document</div>'
                    '<div class="sf-card-desc">Describe the change in plain English — the model applies it while preserving structure.</div>',
                    unsafe_allow_html=True,
                )
                if selected_topic:
                    edit_instruction = st.text_area(
                        "Edit instruction",
                        height=130,
                        key="doc_edit_instruction",
                        label_visibility="collapsed",
                        placeholder=(
                            "e.g. Add a note under budget that all costs require CFO approval.\n"
                            "e.g. Remove the assumption about single-region deployment.\n"
                            "e.g. Clarify that the timeline assumes a 5-person team."
                        ),
                    )
                    if st.button("Apply Edit", key="btn_apply_edit", type="primary", use_container_width=True):
                        if edit_instruction.strip():
                            with st.spinner("Applying edit…"):
                                result = api_post(
                                    f"/projects/{project_id}/docs/{selected_topic}/edit",
                                    json={"instruction": edit_instruction.strip()},
                                )
                            if result:
                                st.success("Edit applied.")
                                st.rerun()
                        else:
                            st.warning("Enter an edit instruction first.")

            # ── Stitch design generation ───────────────────────────────────
            if selected_topic == "design":
                st.divider()
                st.markdown(
                    '<div class="sf-card-title">🎨 Generate Designs in Google Stitch</div>',
                    unsafe_allow_html=True,
                )
                stitch_data = api_get(f"/projects/{project_id}/stitch") or {}
                stitch_status = stitch_data.get("status", "not_generated")

                if stitch_status == "not_generated":
                    st.caption("Generate high-fidelity UI screens from the design requirements using Google Stitch.")
                    if st.button("🎨  Generate in Stitch", key="btn_stitch_generate", type="primary"):
                        result = api_post(f"/projects/{project_id}/stitch/generate")
                        if result:
                            st.info("Generating designs — click Refresh in a few seconds.")
                            st.rerun()

                elif stitch_status == "generating":
                    st.markdown(
                        '<div class="sf-card" style="padding:14px 18px;">'
                        '  <span class="sf-spinner"></span>'
                        '  <span style="color:#4f8ef7;font-size:0.85rem;">Stitch is generating UI screens (~30 seconds)…</span>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("🔄  Refresh", key="btn_stitch_refresh"):
                        st.rerun()

                elif stitch_status == "ready":
                    stitch_url = stitch_data.get("stitch_url", "")
                    screens = stitch_data.get("screens", [])
                    gen_at = stitch_data.get("generated_at", "")
                    st.success("Stitch designs ready.")
                    if stitch_url:
                        st.markdown(f"**[Open project in Stitch →]({stitch_url})**")
                    if screens:
                        sc1, sc2 = st.columns(2)
                        for i, s in enumerate(screens):
                            has_html = bool(s.get("html_path"))
                            status_badge = (
                                '<span style="font-size:0.65rem;color:#4ade80;">✓ generated</span>'
                                if has_html
                                else '<span style="font-size:0.65rem;color:#f59e0b;">⚠ add manually in Stitch</span>'
                            )
                            link = stitch_url or "https://stitch.withgoogle.com"
                            (sc1 if i % 2 == 0 else sc2).markdown(
                                f'<a href="{link}" target="_blank" style="text-decoration:none;">'
                                f'  <div class="sf-card" style="padding:10px 14px;margin-bottom:6px;cursor:pointer;">'
                                f'    <div style="font-size:0.8rem;color:#e8eaf0;">{s["label"]}</div>'
                                f'    <div style="margin-top:3px;">{status_badge}</div>'
                                f'  </div>'
                                f'</a>',
                                unsafe_allow_html=True,
                            )
                    if gen_at:
                        st.caption(f"Generated: {gen_at[:19].replace('T', ' ')} UTC")
                    if st.button("🔄  Regenerate", key="btn_stitch_regen"):
                        result = api_post(f"/projects/{project_id}/stitch/generate")
                        if result:
                            st.info("Regenerating…")
                            st.rerun()

                elif stitch_status == "error":
                    err = stitch_data.get("error", "Unknown error")
                    st.error(f"Stitch generation failed: {err}")
                    st.caption("Check that STITCH_API_KEY is set in poc/.env and Node.js is installed.")
                    if st.button("🔄  Retry", key="btn_stitch_retry", type="primary"):
                        result = api_post(f"/projects/{project_id}/stitch/generate")
                        if result:
                            st.info("Retrying…")
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 5: Clarifications & Query
# ═══════════════════════════════════════════════════════════════════════════════

with tab_clarify:
    st.markdown('<div class="sf-section-header">Clarifications & Knowledge Base</div>', unsafe_allow_html=True)

    project_id = active_project_guard()
    if project_id:
        col_clarify, col_query = st.columns([3, 2])

        with col_clarify:
            st.markdown('<div class="sf-section-header">Open Questions</div>', unsafe_allow_html=True)
            st.caption("Gaps identified during ingestion. Answer them to enrich the knowledge base.")

            open_qs = api_get(f"/projects/{project_id}/clarifications?status=open") or []
            answered_qs = api_get(f"/projects/{project_id}/clarifications?status=answered") or []

            if not open_qs and not answered_qs:
                st.markdown(
                    '<div class="sf-card" style="text-align:center;padding:24px;">'
                    '<div style="color:#4a5070;font-size:0.85rem;">No clarifications yet. Run the pipeline first.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                for q in open_qs:
                    p_class, p_color = PRIORITY_STYLES.get(q["priority"], ("slate", "#94a3b8"))
                    context_html = (
                        f'<div style="font-size:0.75rem;color:#8b92a5;margin:5px 0 0;">{q["context"]}</div>'
                        if q.get("context") else ""
                    )
                    st.markdown(
                        f'<div class="sf-card" style="border-left:3px solid {p_color};padding-left:17px;margin-bottom:6px;">'
                        f'  <div style="margin-bottom:6px;">'
                        f'    <span class="sf-badge sf-badge-{p_class}">{q["priority"].upper()} PRIORITY</span>'
                        f'  </div>'
                        f'  <div class="sf-card-title">{q["question"]}</div>'
                        f'  {context_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    answer_text = st.text_area(
                        "Answer",
                        key=f"answer_{q['id']}",
                        height=72,
                        label_visibility="collapsed",
                        placeholder="Type your answer here…",
                    )
                    if st.button("Submit Answer", key=f"submit_{q['id']}", type="primary"):
                        if answer_text.strip():
                            result = api_post(
                                f"/projects/{project_id}/clarifications/{q['id']}/answer",
                                json={"answer": answer_text.strip()},
                            )
                            if result:
                                st.success("Answer saved and added to the knowledge base.")
                                st.rerun()
                        else:
                            st.warning("Answer cannot be empty.")
                    st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)

                if answered_qs:
                    with st.expander(f"✅  Answered ({len(answered_qs)})", expanded=False):
                        for q in answered_qs:
                            st.markdown(
                                f'<div class="sf-card" style="padding:12px 16px;margin-bottom:6px;">'
                                f'  <div style="font-size:0.78rem;color:#8b92a5;margin-bottom:4px;font-weight:500;">Q</div>'
                                f'  <div class="sf-card-title" style="font-size:0.85rem;">{q["question"]}</div>'
                                f'  <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:#00d4aa;margin:8px 0 3px;">Answer</div>'
                                f'  <div style="font-size:0.82rem;color:#e8eaf0;">{q["answer"]}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

        with col_query:
            st.markdown('<div class="sf-section-header">Ask the Knowledge Base</div>', unsafe_allow_html=True)
            st.caption("Hybrid BM25 + semantic search across requirements, documents, and answered clarifications.")

            query_text = st.text_input(
                "Query",
                placeholder="e.g. What are the authentication requirements?",
                key="rag_query",
                label_visibility="collapsed",
            )
            if st.button("🔍  Search", key="btn_query", type="primary", use_container_width=True) and query_text:
                with st.spinner("Searching…"):
                    results = api_post(f"/projects/{project_id}/query", json={"query": query_text})
                if results:
                    st.markdown(
                        f'<div style="font-size:0.72rem;color:#8b92a5;margin:10px 0 8px;">'
                        f'  {len(results)} result{"s" if len(results) != 1 else ""} for <em>"{query_text}"</em>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    ct_labels = {
                        "chunk_summary": ("📄", "Doc Summary", "violet"),
                        "requirement":   ("📌", "Requirement", "blue"),
                        "clarification": ("💬", "Clarification", "teal"),
                    }
                    for i, chunk in enumerate(results, 1):
                        ct = chunk["content_type"]
                        icon, label, badge_cls = ct_labels.get(ct, ("•", ct, "slate"))
                        score_pct = int(chunk["score"] * 100)
                        preview = chunk["text"][:280] + ("…" if len(chunk["text"]) > 280 else "")
                        st.markdown(
                            f'<div class="sf-card">'
                            f'  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                            f'    <div style="display:flex;align-items:center;gap:8px;">'
                            f'      <span style="font-size:0.95rem;font-weight:700;color:#4f8ef7">#{i}</span>'
                            f'      <span class="sf-badge sf-badge-{badge_cls}">{icon} {label}</span>'
                            f'    </div>'
                            f'    <span style="font-size:0.72rem;color:#8b92a5">{score_pct}% match</span>'
                            f'  </div>'
                            f'  <div style="font-size:0.8rem;color:#e8eaf0;line-height:1.55;">{preview}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("No results found. Try a different query or upload more documents.")
