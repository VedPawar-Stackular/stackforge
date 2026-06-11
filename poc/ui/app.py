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
import time
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
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

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
.sf-step-done .sf-step-label    { color: #00d4aa; }
.sf-step-active .sf-step-label  { color: #4f8ef7; }
.sf-step-failed .sf-step-label  { color: #f43f5e; }
.sf-dot-failed  { background: #f43f5e; color: #fff; }
.sf-step-failed::after { background: rgba(244,63,94,0.3); }

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

/* ── Expanders — Streamlit 1.40+ layout fix ─────────────────────────── */
/* The summary element holds both the label text and the expand icon.
   Without explicit flex layout, the icon (or its fallback text when the
   Material Symbols font fails to load) overlaps the label. */
[data-testid="stExpander"] details > summary {
    list-style: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 10px !important;
    padding: 10px 14px !important;
    background: #1a1d2e !important;
    border: 1px solid #2e3250 !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    transition: border-color 0.15s ease !important;
}
[data-testid="stExpander"] details > summary:hover {
    border-color: #4f8ef7 !important;
}
/* Remove the native browser triangle marker */
[data-testid="stExpander"] details > summary::-webkit-details-marker {
    display: none !important;
}
/* Label text — take all available space */
[data-testid="stExpander"] details > summary p {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    margin: 0 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #e8eaf0 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}
/* Icon — must not grow or shrink; hidden if font fails to load */
[data-testid="stExpander"] details > summary svg,
[data-testid="stExpander"] details > summary [data-testid="stExpanderToggleIcon"] {
    flex: 0 0 auto !important;
    display: flex !important;
    align-items: center !important;
    color: #8b92a5 !important;
    transition: transform 0.15s ease !important;
}
/* Hide icon fallback text (renders when Material Symbols font is absent) */
[data-testid="stExpander"] details > summary [data-testid="stExpanderToggleIcon"] span {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
    font-size: 20px !important;
    overflow: hidden !important;
    width: 20px !important;
    height: 20px !important;
    display: inline-block !important;
    line-height: 20px !important;
    color: #8b92a5 !important;
}
[data-testid="stExpander"] details[open] > summary svg,
[data-testid="stExpander"] details[open] > summary [data-testid="stExpanderToggleIcon"] {
    transform: rotate(180deg) !important;
}
/* Content area */
[data-testid="stExpander"] details > div {
    border: 1px solid #2e3250 !important;
    border-top: none !important;
    border-radius: 0 0 8px 8px !important;
    padding: 12px 14px !important;
    background: #12141f !important;
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

@st.cache_resource
def _http() -> httpx.Client:
    """Single persistent HTTP client — reuses TCP connections across reruns."""
    return httpx.Client(base_url=API_BASE, timeout=30)


def api_get(path: str) -> dict | list | None:
    """Uncached GET — use only inside fragments for real-time polling."""
    try:
        r = _http().get(path)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, json: dict = None, files: dict = None) -> dict | list | None:
    try:
        r = _http().post(path, json=json, files=files, timeout=120)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_delete(path: str) -> bool:
    try:
        r = _http().delete(path)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"API error: {e}")
        return False


# ─── Scoped GET cache (replaces @st.cache_data — supports per-path invalidation) ─

_cache_store: dict[str, tuple] = {}
_CACHE_TTL = 15


def cached_get(path: str) -> dict | list | None:
    """GET with 15s per-path TTL. Use invalidate_cache() after mutations."""
    now = time.time()
    if path in _cache_store:
        val, ts = _cache_store[path]
        if now - ts < _CACHE_TTL:
            return val
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=30)
        r.raise_for_status()
        result = r.json()
        _cache_store[path] = (result, now)
        return result
    except Exception:
        return None


def invalidate_cache(*paths: str) -> None:
    """Invalidate specific cache paths after a mutating operation."""
    for p in paths:
        _cache_store.pop(p, None)


def invalidate_project_cache(project_id: str) -> None:
    """Invalidate all cached paths that reference a specific project."""
    stale = [k for k in _cache_store if project_id in k]
    for k in stale:
        _cache_store.pop(k, None)


def get_projects() -> list[dict]:
    return cached_get("/projects") or []


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
    cls = {
        "done": "teal", "ready": "teal",
        "partial": "amber",
        "processing": "blue",
        "failed": "rose",
        "pending": "slate",
    }.get(status.lower(), "slate")
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

tab_setup, tab_upload, tab_review, tab_docs, tab_clarify, tab_epics = st.tabs([
    "🏗️  Setup",
    "📂  Upload",
    "📋  Requirements",
    "📄  Documents",
    "💬  Clarifications",
    "🗂️  Epics & Stories",
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
            confirm_key = f"confirm_delete_{pid_str}"
            is_confirming = st.session_state.get(confirm_key, False)

            border_style = (
                "border-color:#f43f5e;box-shadow:0 0 0 1px rgba(244,63,94,0.15);"
                if is_confirming
                else ("border-color:#4f8ef7;box-shadow:0 0 0 1px rgba(79,142,247,0.15);" if is_active else "")
            )
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

                if is_confirming:
                    # ── Confirmation state ─────────────────────────────────
                    st.markdown(
                        '<div style="font-size:0.78rem;color:#f43f5e;padding:6px 2px 8px;">'
                        '  Permanently delete this project and all its data? This cannot be undone.'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    c_cancel, c_confirm = st.columns(2)
                    with c_cancel:
                        if st.button("Cancel", key=f"btn_cancel_{pid_str}", use_container_width=True):
                            del st.session_state[confirm_key]
                            st.rerun()
                    with c_confirm:
                        if st.button("Delete", key=f"btn_confirm_del_{pid_str}",
                                     type="primary", use_container_width=True):
                            if api_delete(f"/projects/{pid_str}"):
                                invalidate_cache("/projects")
                                del st.session_state[confirm_key]
                                # If the deleted project was active, clear it
                                if is_active:
                                    for k in ("project_id", "project_name",
                                              "pipeline_auto_refresh", "upload_notification",
                                              "last_upload_queued", "last_upload_errors"):
                                        st.session_state.pop(k, None)
                                st.rerun()
                else:
                    # ── Normal state ───────────────────────────────────────
                    btn_cols = st.columns([3, 1])
                    with btn_cols[0]:
                        btn_label = "✓ Active" if is_active else "Make Active"
                        btn_type = "secondary" if is_active else "primary"
                        if st.button(btn_label, key=f"btn_activate_{pid_str}",
                                     type=btn_type, use_container_width=True, disabled=is_active):
                            st.session_state["project_id"] = pid_str
                            st.session_state["project_name"] = name
                            st.rerun()
                    with btn_cols[1]:
                        if st.button("🗑", key=f"btn_delete_{pid_str}",
                                     use_container_width=True, help="Delete project"):
                            st.session_state[confirm_key] = True
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
                    invalidate_cache("/projects")
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

        # ── Show notification from a completed upload action ───────────────
        if "upload_notification" in st.session_state:
            notif = st.session_state.pop("upload_notification")
            if notif["type"] == "success":
                st.success(notif["message"])
            elif notif["type"] == "warning":
                st.warning(notif["message"])
            else:
                st.error(notif["message"])

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
                queued_count = 0
                upload_fail_names = []
                progress_ph = st.empty()

                for i, f in enumerate(uploaded):
                    progress_ph.markdown(
                        f'<div style="font-size:0.82rem;color:#8b92a5;padding:6px 0;">'
                        f'Uploading {i + 1} of {len(uploaded)}: '
                        f'<strong style="color:#e8eaf0;">{f.name}</strong>…</div>',
                        unsafe_allow_html=True,
                    )
                    files = {"file": (f.name, f.getvalue(), f.type)}
                    result = api_post(f"/projects/{project_id}/documents", files=files)
                    if result:
                        queued_count += 1
                    else:
                        upload_fail_names.append(f.name)

                progress_ph.empty()

                if upload_fail_names:
                    st.session_state["upload_notification"] = {
                        "type": "warning",
                        "message": (
                            f"Queued {queued_count} document{'s' if queued_count != 1 else ''} for processing. "
                            f"{len(upload_fail_names)} file(s) could not be accepted by the server: "
                            f"{', '.join(upload_fail_names)}."
                        ),
                    }
                else:
                    st.session_state["upload_notification"] = {
                        "type": "success",
                        "message": (
                            f"✓ {queued_count} document{'s' if queued_count != 1 else ''} accepted. "
                            f"The AI pipeline is now running in the background — "
                            f"see Pipeline Status below for live progress."
                        ),
                    }

                # Activate auto-refresh and re-render so the fragment
                # picks up run_every=5 from the updated session state.
                st.session_state["pipeline_auto_refresh"] = True
                st.rerun()

        st.divider()
        st.markdown('<div class="sf-section-header">Pipeline Status</div>', unsafe_allow_html=True)

        # ── Pipeline step tracker helper ───────────────────────────────────
        def _pipeline_steps_html(pipeline_status: str) -> str:
            steps = ["Parse", "Chunk", "Summarize", "Extract", "Clarify", "Embed"]

            if pipeline_status == "ready":
                step_states = [("sf-step sf-step-done", "sf-dot sf-dot-done", "✓")] * len(steps)
            elif pipeline_status == "partial":
                # Some docs succeeded — show pipeline as complete with a note
                step_states = [("sf-step sf-step-done", "sf-dot sf-dot-done", "✓")] * len(steps)
            elif pipeline_status == "failed":
                step_states = [("sf-step sf-step-failed", "sf-dot sf-dot-failed", "✗")] * len(steps)
            elif pipeline_status == "processing":
                # We don't track per-step progress, so show the first step active
                step_states = [("sf-step", "sf-dot sf-dot-pending", str(i + 1)) for i in range(len(steps))]
                step_states[0] = ("sf-step sf-step-active", "sf-dot sf-dot-active", "1")
            else:
                step_states = [("sf-step", "sf-dot sf-dot-pending", str(i + 1)) for i in range(len(steps))]

            dots = "".join(
                f'<div class="{cls}">'
                f'  <div class="{dot_cls}">{dot_inner}</div>'
                f'  <div class="sf-step-label">{steps[i]}</div>'
                f'</div>'
                for i, (cls, dot_cls, dot_inner) in enumerate(step_states)
            )
            return f'<div class="sf-pipeline">{dots}</div>'

        # ── Auto-refreshing fragment ───────────────────────────────────────
        # run_every is computed from session state at page-render time.
        # Calling st.rerun() from inside the fragment restarts the full page,
        # which re-evaluates this line and gives the fragment the new interval.
        _pipeline_auto_refresh = st.session_state.get("pipeline_auto_refresh", False)

        @st.fragment(run_every=5 if _pipeline_auto_refresh else None)
        def _pipeline_status():
            _pid = st.session_state.get("project_id")
            if not _pid:
                return
            status = api_get(f"/projects/{_pid}/status")
            if not status:
                return

            ps = status["status"]
            doc_count = status["document_count"]
            ready_count = status["ready_count"]
            failed_count = status.get("failed_count", 0)

            # ── Auto-refresh lifecycle ─────────────────────────────────────
            # Start auto-refresh the moment we detect processing
            if ps == "processing" and not st.session_state.get("pipeline_auto_refresh"):
                st.session_state["pipeline_auto_refresh"] = True
                st.rerun()
                return
            # Stop auto-refresh once the pipeline has settled
            if ps in ("ready", "failed", "partial") and st.session_state.get("pipeline_auto_refresh"):
                st.session_state["pipeline_auto_refresh"] = False
                st.rerun()
                return

            # ── Empty state ────────────────────────────────────────────────
            if doc_count == 0:
                st.markdown(
                    '<div class="sf-card" style="text-align:center;padding:28px;">'
                    '<div style="color:#4a5070;font-size:0.85rem;">'
                    'No documents uploaded yet. Select files above and click <strong>Run AI Pipeline</strong>.'
                    '</div></div>',
                    unsafe_allow_html=True,
                )
                return

            # ── Step tracker ───────────────────────────────────────────────
            st.markdown(_pipeline_steps_html(ps), unsafe_allow_html=True)

            # ── Metrics row ────────────────────────────────────────────────
            col1, col2, col3, col4 = st.columns(4)

            STATUS_META = {
                "processing": ("blue",  "Processing"),
                "ready":      ("teal",  "Complete"),
                "partial":    ("amber", "Partial"),
                "failed":     ("rose",  "Failed"),
                "pending":    ("slate", "Pending"),
            }
            status_cls, status_label = STATUS_META.get(ps, ("slate", ps.upper()))

            with col1:
                st.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">'
                    f'    <span class="sf-badge sf-badge-{status_cls}" style="font-size:0.8rem;padding:4px 10px;">'
                    f'      {status_label.upper()}'
                    f'    </span>'
                    f'  </div>'
                    f'  <div class="sf-metric-label">Pipeline</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                failed_html = (
                    f'<span style="font-size:0.75rem;color:#f43f5e;margin-left:3px;">({failed_count} failed)</span>'
                    if failed_count > 0 else ""
                )
                st.markdown(
                    f'<div class="sf-metric">'
                    f'  <div class="sf-metric-value">'
                    f'    {ready_count}'
                    f'    <span style="font-size:1rem;color:#8b92a5;">/{doc_count}</span>'
                    f'    {failed_html}'
                    f'  </div>'
                    f'  <div class="sf-metric-label">Docs Processed</div>'
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

            # ── Status message ─────────────────────────────────────────────
            if ps == "processing":
                st.markdown(
                    '<div class="sf-card" style="border-color:rgba(79,142,247,0.3);padding:12px 16px;">'
                    '  <span class="sf-spinner"></span>'
                    '  <span style="color:#4f8ef7;font-size:0.85rem;">'
                    '    AI pipeline running — page auto-refreshes every 5 seconds…'
                    '  </span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            elif ps == "ready":
                st.success(
                    f"All {ready_count} document{'s' if ready_count != 1 else ''} processed successfully. "
                    f"Switch to the **Requirements** tab to review extracted items."
                )
            elif ps == "partial":
                st.warning(
                    f"{ready_count} of {doc_count} documents processed. "
                    f"{failed_count} document{'s' if failed_count != 1 else ''} failed — "
                    f"see the list below for error details. "
                    f"Requirements extracted from the successful documents are available in the **Requirements** tab."
                )
            elif ps == "failed":
                st.error(
                    f"Pipeline failed — all {failed_count} document{'s' if failed_count != 1 else ''} "
                    f"could not be processed. See the list below for error details. "
                    f"Common causes: LLM API rate limits, unsupported file encoding, or network timeouts."
                )

            # ── Documents list ─────────────────────────────────────────────
            docs = api_get(f"/projects/{_pid}/documents") or []
            if docs:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="sf-section-header">Document Processing Log</div>', unsafe_allow_html=True)
                for doc in docs:
                    doc_status = doc["status"]
                    badge = render_status_badge(doc_status)
                    error_msg = doc.get("error_message") or ""

                    # Truncate long error messages for display
                    if error_msg and len(error_msg) > 140:
                        error_msg = error_msg[:140] + "…"

                    error_html = (
                        f'<div style="font-size:0.72rem;color:#f43f5e;margin-top:5px;line-height:1.45;">'
                        f'  ⚠ {error_msg}'
                        f'</div>'
                        if doc_status == "failed" and error_msg else ""
                    )

                    border_style = "border-left:3px solid #f43f5e;" if doc_status == "failed" else (
                        "border-left:3px solid #00d4aa;" if doc_status == "done" else ""
                    )

                    st.markdown(
                        f'<div class="sf-card" style="padding:10px 16px;margin-bottom:6px;{border_style}">'
                        f'  <div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'    <span style="font-size:0.85rem;color:#e8eaf0;">{doc["filename"]}</span>'
                        f'    {badge}'
                        f'  </div>'
                        f'  {error_html}'
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
        reqs = cached_get(f"/projects/{project_id}/requirements") or []

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
        doc_meta = cached_get(f"/projects/{project_id}/docs") or []
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

                    doc = cached_get(f"/projects/{project_id}/docs/{selected_topic}")
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
                                invalidate_cache(
                                    f"/projects/{project_id}/docs/{selected_topic}",
                                    f"/projects/{project_id}/docs",
                                )
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
                stitch_data = cached_get(f"/projects/{project_id}/stitch") or {}
                stitch_status = stitch_data.get("status", "not_generated")

                if stitch_status == "not_generated":
                    st.caption("Generate high-fidelity UI screens from the design requirements using Google Stitch.")
                    if st.button("🎨  Generate in Stitch", key="btn_stitch_generate", type="primary"):
                        result = api_post(f"/projects/{project_id}/stitch/generate")
                        if result:
                            invalidate_cache(f"/projects/{project_id}/stitch")
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
                        invalidate_cache(f"/projects/{project_id}/stitch")
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
                            invalidate_cache(f"/projects/{project_id}/stitch")
                            st.info("Regenerating…")
                            st.rerun()

                elif stitch_status == "error":
                    err = stitch_data.get("error", "Unknown error")
                    st.error(f"Stitch generation failed: {err}")
                    st.caption("Check that STITCH_API_KEY is set in poc/.env and Node.js is installed.")
                    if st.button("🔄  Retry", key="btn_stitch_retry", type="primary"):
                        result = api_post(f"/projects/{project_id}/stitch/generate")
                        if result:
                            invalidate_cache(f"/projects/{project_id}/stitch")
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

            open_qs = cached_get(f"/projects/{project_id}/clarifications?status=open") or []
            answered_qs = cached_get(f"/projects/{project_id}/clarifications?status=answered") or []

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
                                invalidate_cache(
                                    f"/projects/{project_id}/clarifications?status=open",
                                    f"/projects/{project_id}/clarifications?status=answered",
                                )
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 6: Epics & Stories
# ═══════════════════════════════════════════════════════════════════════════════

with tab_epics:
    st.markdown('<div class="sf-section-header">Epics & User Stories</div>', unsafe_allow_html=True)

    project_id = active_project_guard()
    if project_id:

        # ── Status + action bar ────────────────────────────────────────────
        stage2 = cached_get(f"/projects/{project_id}/stage2-status") or {}
        s2_status = stage2.get("status", "idle")
        epic_count = stage2.get("epic_count", 0)
        story_count = stage2.get("story_count", 0)
        ado_pushed = stage2.get("ado_pushed", False)

        top_left, top_right = st.columns([2, 1])

        with top_left:
            status_color = {
                "idle":       ("#4a5070", "#2e3250"),
                "generating": ("#4f8ef7", "rgba(79,142,247,0.15)"),
                "ready":      ("#00d4aa", "rgba(0,212,170,0.12)"),
                "failed":     ("#f43f5e", "rgba(244,63,94,0.12)"),
            }.get(s2_status, ("#8b92a5", "#2e3250"))

            m1, m2, m3 = st.columns(3)
            m1.markdown(
                f'<div class="sf-metric">'
                f'  <div class="sf-metric-value">'
                f'    <span style="font-size:0.85rem;padding:3px 10px;border-radius:6px;'
                f'background:{status_color[1]};color:{status_color[0]};font-weight:600;">'
                f'{s2_status.upper()}</span>'
                f'  </div>'
                f'  <div class="sf-metric-label">Stage 2 Status</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            m2.markdown(
                f'<div class="sf-metric">'
                f'  <div class="sf-metric-value">{epic_count}</div>'
                f'  <div class="sf-metric-label">Epics</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            m3.markdown(
                f'<div class="sf-metric">'
                f'  <div class="sf-metric-value">{story_count}</div>'
                f'  <div class="sf-metric-label">User Stories</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with top_right:
            if s2_status in ("idle", "failed"):
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("⚡  Generate Epics & Stories", key="btn_generate_epics", type="primary", use_container_width=True):
                    result = api_post(f"/projects/{project_id}/generate-epics")
                    if result:
                        invalidate_cache(
                            f"/projects/{project_id}/stage2-status",
                            f"/projects/{project_id}/epics",
                            f"/projects/{project_id}/stories",
                            f"/projects/{project_id}/stage2-metrics",
                        )
                        st.info("Generation started — this takes ~30 seconds. Refresh to check progress.")
                        st.rerun()
            elif s2_status == "generating":
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(
                    '<div class="sf-card" style="padding:14px 18px;">'
                    '  <span class="sf-spinner"></span>'
                    '  <span style="color:#4f8ef7;font-size:0.85rem;">Generating epics and stories…</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if st.button("🔄 Refresh", key="btn_s2_refresh"):
                    invalidate_cache(f"/projects/{project_id}/stage2-status")
                    st.rerun()
            elif s2_status == "ready":
                st.markdown("<br>", unsafe_allow_html=True)

                # Show push result that survived the last rerun (session_state persists across reruns)
                _push_msg = st.session_state.pop("_ado_push_result", None)
                if _push_msg:
                    if _push_msg.get("errors"):
                        st.warning(f"Pushed {_push_msg['epics_pushed']} epics, {_push_msg['stories_pushed']} stories — {len(_push_msg['errors'])} errors.")
                        for err in _push_msg["errors"][:5]:
                            st.caption(f"  • {err}")
                    else:
                        st.success(f"Pushed {_push_msg['epics_pushed']} epics and {_push_msg['stories_pushed']} user stories to Azure DevOps.")

                # ADO area path config — pre-filled with project name, user can override
                _ap_key = f"_ado_area_path_{project_id}"
                if _ap_key not in st.session_state:
                    st.session_state[_ap_key] = st.session_state.get("project_name", "")
                with st.expander("⚙️ ADO Settings", expanded=False):
                    st.text_input(
                        "Area path (sub-area under your ADO project)",
                        key=_ap_key,
                        placeholder="e.g. MediBook",
                        help=(
                            "StackForge will create StackForge\\<area path> in ADO automatically. "
                            "Clear this field to push to the ADO project default area instead."
                        ),
                    )
                    st.caption(
                        "If auto-create fails (permissions), create the area in ADO first: "
                        "**Project Settings → Boards → Area → New child node**, then push."
                    )
                _area_path = st.session_state.get(_ap_key, "")

                ado_label = "✓ Pushed to ADO" if ado_pushed else "🚀  Push to Azure DevOps"
                ado_type = "secondary" if ado_pushed else "primary"
                _push_url = f"/projects/{project_id}/push-to-ado"
                if _area_path:
                    _push_url += f"?area_path={_area_path}"
                if st.button(ado_label, key="btn_push_ado", type=ado_type, use_container_width=True):
                    push_result = api_post(_push_url)
                    if push_result:
                        if push_result.get("status") == "pushing":
                            # Background push started — counts not available yet
                            st.info("ADO push started. Refresh the page in a moment to see updated status.")
                        else:
                            # Legacy sync response (future fallback)
                            st.session_state["_ado_push_result"] = {
                                "epics_pushed": push_result.get("epics_pushed", 0),
                                "stories_pushed": push_result.get("stories_pushed", 0),
                                "errors": push_result.get("errors", []),
                            }
                        invalidate_cache(
                            f"/projects/{project_id}/stage2-status",
                            f"/projects/{project_id}/epics",
                        )
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Empty state ────────────────────────────────────────────────────
        if s2_status == "idle":
            st.markdown(
                '<div class="sf-card" style="text-align:center;padding:40px;">'
                '<div style="font-size:2rem;margin-bottom:10px;">🗂️</div>'
                '<div class="sf-card-title">Stage 2 not started</div>'
                '<div class="sf-card-desc" style="text-align:center;">'
                'Generate Epics & Stories from your extracted requirements.<br>'
                'Make sure Stage 1 (document ingestion) is complete first.'
                '</div></div>',
                unsafe_allow_html=True,
            )

        elif s2_status == "failed":
            st.error("Generation failed. Check that Stage 1 requirements exist, then retry.")

        elif s2_status in ("generating",):
            st.info("Generation in progress — refresh in ~30 seconds.")

        else:
            # ── Epic accordion tree ────────────────────────────────────────
            epics_data = cached_get(f"/projects/{project_id}/epics") or []

            if not epics_data:
                st.info("No epics found. Try regenerating.")
            else:
                # One call for all stories — avoids N per-epic round trips
                _all_stories = cached_get(f"/projects/{project_id}/stories") or []
                _stories_by_epic: dict[str, list] = {}
                for _s in _all_stories:
                    _stories_by_epic.setdefault(str(_s.get("epic_id", "")), []).append(_s)

                for epic in epics_data:
                    epic_id = str(epic["id"])
                    ado_id = epic.get("ado_work_item_id")
                    ado_url = epic.get("ado_work_item_url", "")
                    ado_badge = (
                        f'<a href="https://dev.azure.com" target="_blank" style="text-decoration:none;">'
                        f'<span class="sf-badge sf-badge-teal">ADO #{ado_id}</span></a>'
                        if ado_id else
                        '<span class="sf-badge sf-badge-slate">Not pushed</span>'
                    )
                    sc = epic.get("story_count", 0)
                    expander_label = f"📦  {epic['title']}  ·  {sc} {'story' if sc == 1 else 'stories'}"

                    with st.expander(expander_label, expanded=False):
                        st.markdown(
                            f'<div style="margin-bottom:12px;">'
                            f'  <div class="sf-card-meta">'
                            f'    <span class="sf-badge sf-badge-violet">{epic.get("theme", "")}</span>'
                            f'    {ado_badge}'
                            f'  </div>'
                            f'  <div class="sf-card-desc" style="margin-top:8px;">{epic.get("description","")}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        stories_data = _stories_by_epic.get(epic_id, [])

                        if not stories_data:
                            st.caption("No stories generated for this epic.")
                        else:
                            for story in stories_data:
                                s_ado_id = story.get("ado_work_item_id")
                                s_ado_badge = (
                                    f'<span class="sf-badge sf-badge-teal">ADO #{s_ado_id}</span>'
                                    if s_ado_id else ""
                                )
                                pts = story.get("story_points")
                                pts_badge = (
                                    f'<span class="sf-badge sf-badge-blue">{pts} pts</span>'
                                    if pts else ""
                                )
                                ac_list = story.get("acceptance_criteria") or []
                                ac_html = "".join(
                                    f'<div style="font-size:0.77rem;color:#8b92a5;padding:2px 0;">'
                                    f'  <span style="color:#4a5070;margin-right:5px;">▸</span>{ac}'
                                    f'</div>'
                                    for ac in ac_list
                                )
                                st.markdown(
                                    f'<div class="sf-card" style="margin-bottom:8px;">'
                                    f'  <div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                                    f'    <div class="sf-card-title" style="flex:1;">{story["title"]}</div>'
                                    f'    <div style="display:flex;gap:5px;margin-left:8px;">{pts_badge}{s_ado_badge}</div>'
                                    f'  </div>'
                                    f'  <div class="sf-card-desc" style="color:#94a3b8;font-style:italic;">'
                                    f'    {story.get("description","")}'
                                    f'  </div>'
                                    f'  {ac_html}'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )

        # ── Metrics panel (visible once generation is done) ────────────────
        if s2_status == "ready":
            st.divider()
            st.markdown('<div class="sf-section-header">Token Cost Optimization Report</div>', unsafe_allow_html=True)

            metrics = cached_get(f"/projects/{project_id}/stage2-metrics")
            if metrics and metrics.get("naive_cost_usd", 0) > 0:
                savings_pct = metrics.get("savings_pct", 0)
                actual = metrics.get("actual_cost_usd", 0)
                naive = metrics.get("naive_cost_usd", 0)
                tokens_saved = metrics.get("tokens_saved", 0)

                # ── Headline savings banner ────────────────────────────────
                st.markdown(
                    f'<div class="sf-card" style="background:linear-gradient(135deg,rgba(0,212,170,0.06),rgba(79,142,247,0.06));'
                    f'border-color:rgba(0,212,170,0.25);padding:20px 24px;">'
                    f'  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;">'
                    f'    <div>'
                    f'      <div style="font-size:2rem;font-weight:700;color:#00d4aa;">{savings_pct:.0f}% cheaper</div>'
                    f'      <div style="font-size:0.8rem;color:#8b92a5;margin-top:2px;">vs naive unoptimized approach</div>'
                    f'    </div>'
                    f'    <div style="text-align:center;">'
                    f'      <div style="font-size:1.3rem;font-weight:600;color:#e8eaf0;">${actual:.4f}</div>'
                    f'      <div style="font-size:0.68rem;color:#8b92a5;text-transform:uppercase;letter-spacing:0.05em;">Actual cost</div>'
                    f'    </div>'
                    f'    <div style="text-align:center;opacity:0.5;">'
                    f'      <div style="font-size:1.3rem;font-weight:600;color:#e8eaf0;text-decoration:line-through;">${naive:.4f}</div>'
                    f'      <div style="font-size:0.68rem;color:#8b92a5;text-transform:uppercase;letter-spacing:0.05em;">Naive baseline</div>'
                    f'    </div>'
                    f'    <div style="text-align:center;">'
                    f'      <div style="font-size:1.3rem;font-weight:600;color:#4f8ef7;">{tokens_saved:,}</div>'
                    f'      <div style="font-size:0.68rem;color:#8b92a5;text-transform:uppercase;letter-spacing:0.05em;">Tokens saved</div>'
                    f'    </div>'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                st.markdown("<br>", unsafe_allow_html=True)

                # ── Comparison bar chart ───────────────────────────────────
                try:
                    import plotly.graph_objects as go

                    steps = metrics.get("steps", [])
                    if steps:
                        step_names = [s["step"].replace("_", " ").replace("story generation epic ", "Epic ") for s in steps]
                        actual_costs = [s["cost_usd"] for s in steps]

                        fig = go.Figure()
                        fig.add_trace(go.Bar(
                            name="Actual (optimized)",
                            x=step_names,
                            y=actual_costs,
                            marker_color="#4f8ef7",
                            text=[f"${c:.4f}" for c in actual_costs],
                            textposition="outside",
                            textfont=dict(size=10, color="#8b92a5"),
                        ))
                        fig.update_layout(
                            height=220,
                            margin=dict(t=10, b=30, l=0, r=0),
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#8b92a5", size=10, family="Inter, system-ui"),
                            xaxis=dict(showgrid=False, tickfont=dict(size=9, color="#8b92a5")),
                            yaxis=dict(showgrid=False, visible=False),
                            legend=dict(font=dict(color="#8b92a5"), bgcolor="rgba(0,0,0,0)"),
                            bargap=0.35,
                            showlegend=False,
                        )
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                except ImportError:
                    pass

                # ── Per-step breakdown table ───────────────────────────────
                st.markdown('<div class="sf-section-header" style="margin-top:8px;">Step-by-Step Breakdown</div>', unsafe_allow_html=True)

                for step in metrics.get("steps", []):
                    tier_badge_cls = {"haiku": "teal", "sonnet": "blue", "opus": "violet"}.get(step["tier"], "slate")
                    st.markdown(
                        f'<div class="sf-card" style="margin-bottom:8px;">'
                        f'  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">'
                        f'    <div style="flex:1;">'
                        f'      <div class="sf-card-title">{step["step"].replace("_", " ").title()}</div>'
                        f'      <div class="sf-card-meta" style="margin-top:6px;">'
                        f'        <span class="sf-badge sf-badge-{tier_badge_cls}">{step["tier"].upper()} tier</span>'
                        f'        <span class="sf-badge sf-badge-slate">{step["model"]}</span>'
                        f'        <span class="sf-badge sf-badge-slate">{step["input_tokens"]:,} in / {step["output_tokens"]:,} out tokens</span>'
                        f'        <span class="sf-badge sf-badge-slate">{step["duration_ms"]}ms</span>'
                        f'      </div>'
                        f'      <div style="font-size:0.77rem;color:#8b92a5;margin-top:8px;line-height:1.5;">'
                        f'        {step["why_this_model"]}'
                        f'      </div>'
                        f'    </div>'
                        f'    <div style="text-align:right;white-space:nowrap;">'
                        f'      <div style="font-size:1.1rem;font-weight:600;color:#e8eaf0;">${step["cost_usd"]:.4f}</div>'
                        f'      <div style="font-size:0.68rem;color:#8b92a5;">at Anthropic rates</div>'
                        f'    </div>'
                        f'  </div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # ── Optimization decisions summary ─────────────────────────
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="sf-section-header">What Made It Cheap</div>', unsafe_allow_html=True)
                optimizations = [
                    ("Model routing", "Cheap model for decomposition, mid model for generation — not everything on Opus.", "teal"),
                    ("Context scoping", "Each story-generation call receives only that epic's requirements (~15-20), not all 130.", "blue"),
                    ("Titles-only decomposition", "Epic grouping uses titles only, not full descriptions — 77% input token reduction.", "blue"),
                    ("Parallel execution", "All epic story calls run simultaneously via asyncio.gather — ~7x faster than serial.", "violet"),
                    ("Structured JSON output", "max_tokens cap + strict schema — eliminates prose padding (~40% output reduction).", "amber"),
                    ("Caching-ready architecture", "Static system prompts eligible for Anthropic prompt caching — 90% cost reduction on cache hits in production.", "slate"),
                ]
                cols = st.columns(2)
                for i, (title, desc, badge_cls) in enumerate(optimizations):
                    cols[i % 2].markdown(
                        f'<div class="sf-card" style="padding:12px 16px;margin-bottom:6px;">'
                        f'  <div style="display:flex;align-items:flex-start;gap:10px;">'
                        f'    <span class="sf-badge sf-badge-{badge_cls}" style="margin-top:2px;white-space:nowrap;">{title}</span>'
                        f'    <div style="font-size:0.78rem;color:#8b92a5;line-height:1.5;">{desc}</div>'
                        f'  </div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Metrics will appear here after generation completes.")
