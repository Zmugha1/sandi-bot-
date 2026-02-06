"""
Sandi Bot - Visual coaching UI components.
Warm coaching aesthetic: cards, kanban, score bars, script boxes, timeline, metrics.
"""
import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional, List, Any, Callable

# ---- Design system ----
COLORS = {
    "push": "#2e7d32",
    "nurture": "#f57c00",
    "pause": "#c2185b",
    "bg": "#fafafa",
    "card": "#ffffff",
    "text": "#2c3e50",
    "accent": "#1976d2",
}

COACHING_CSS = """
<style>
:root { --push: #2e7d32; --nurture: #f57c00; --pause: #c2185b; --bg: #fafafa; --card: #ffffff; --text: #2c3e50; --accent: #1976d2; }
.sandi-coach .metric-card { background: #ffffff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 16px; }
.sandi-coach .metric-number { font-size: 36px; font-weight: 700; color: #2c3e50; line-height: 1.2; }
.sandi-coach .metric-label { font-size: 16px; color: #2c3e50; margin-top: 4px; }
.sandi-coach .client-card { background: #ffffff; border-radius: 10px; padding: 14px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); margin-bottom: 10px; cursor: pointer; border-left: 4px solid #1976d2; min-height: 44px; display: flex; align-items: center; }
.sandi-coach .client-card.push-border { border-left-color: #2e7d32; }
.sandi-coach .client-card.nurture-border { border-left-color: #f57c00; }
.sandi-coach .client-card.pause-border { border-left-color: #c2185b; }
.sandi-coach .client-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.sandi-coach .score-bar-wrap { margin: 10px 0; }
.sandi-coach .score-bar-label { font-size: 16px; color: #2c3e50; margin-bottom: 4px; }
.sandi-coach .score-bar-track { background: #e0e0e0; border-radius: 6px; height: 20px; overflow: hidden; }
.sandi-coach .score-bar-fill { height: 20px; border-radius: 6px; transition: width 0.3s; }
.sandi-coach .script-box { background: #f5f5f5; border-radius: 8px; padding: 14px; font-size: 16px; color: #2c3e50; border-left: 4px solid #1976d2; margin: 8px 0; }
.sandi-coach .timeline-step { display: inline-block; padding: 6px 12px; margin: 2px; border-radius: 8px; font-size: 14px; }
.sandi-coach .timeline-current { background: #1976d2; color: white; font-weight: 700; }
.sandi-coach .timeline-past { background: #e8f5e9; color: #2e7d32; }
.sandi-coach .timeline-future { background: #f5f5f5; color: #9e9e9e; }
.sandi-coach .action-card { padding: 20px; border-radius: 12px; color: white; font-size: 18px; font-weight: 700; }
.sandi-coach .action-card.push { background: #2e7d32; }
.sandi-coach .action-card.nurture { background: #f57c00; }
.sandi-coach .action-card.pause { background: #c2185b; }
.sandi-coach .sandi-header { font-size: 28px; font-weight: 700; color: #2c3e50; }
.sandi-coach .sandi-body { font-size: 16px; line-height: 1.5; color: #2c3e50; }
.sandi-coach button { min-height: 44px; }
</style>
"""

# Legacy alias for app that still references it
HEADER_CSS = COACHING_CSS


def first_name_only(full_name: Optional[str]) -> str:
    """Return first name only for display. Never show prospect_id in UI."""
    if not full_name or not isinstance(full_name, str):
        return "Client"
    return full_name.strip().split()[0] if full_name.strip() else "Client"


def action_color(action: str) -> str:
    return COLORS.get(action.lower(), COLORS["accent"])


# ---- Avatar & form (keep for sidebar) ----
def render_sandi_avatar(show_name: bool = True, status: str = "Ready to help"):
    st.markdown(COACHING_CSS, unsafe_allow_html=True)
    st.markdown("🧢")
    if show_name:
        st.markdown('<p class="sandi-coach sandi-header" style="font-size: 22px;">Sandi Bot</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="sandi-coach sandi-body" style="font-size: 16px;">{status}</p>', unsafe_allow_html=True)


def render_customer_entry_form(on_start_callback=None):
    st.subheader("Strategy session")
    prospect_id = st.text_input("Customer #", placeholder="e.g. P001", key="sandi_customer_id")
    name = st.text_input("Name", placeholder="e.g. James Smith", key="sandi_customer_name")
    if st.button("Start ▶", type="primary", key="sandi_start_btn"):
        if prospect_id and name:
            if on_start_callback:
                on_start_callback(prospect_id.strip(), name.strip())
            st.session_state["sandi_prospect_id"] = prospect_id.strip()
            st.session_state["sandi_prospect_name"] = name.strip()
            st.rerun()
        else:
            st.warning("Please enter both Customer # and Name.")
    return (
        st.session_state.get("sandi_prospect_id"),
        st.session_state.get("sandi_prospect_name"),
    )


# ---- New components ----
def render_insight_metric(number: int, label: str, trend: Optional[str] = None, key: str = "metric"):
    """Big number card for dashboard (e.g. Ready for Decision count)."""
    st.markdown(COACHING_CSS, unsafe_allow_html=True)
    trend_html = f'<div class="metric-label">{trend}</div>' if trend else ""
    st.markdown(
        f'<div class="sandi-coach metric-card">'
        f'<div class="metric-number">{number}</div>'
        f'<div class="metric-label">{label}</div>{trend_html}</div>',
        unsafe_allow_html=True,
    )


def render_client_card(
    client: dict,
    action: str,
    on_click: Optional[Callable[[str], None]] = None,
    key_prefix: str = "card",
    show_subtitle: bool = True,
):
    """
    Priority/coaching card: first name, persona, days, action badge.
    on_click(prospect_id) called when user clicks the card (via button).
    """
    first = first_name_only(client.get("name"))
    persona = client.get("persona", "Strategic")
    comp = client.get("compartment", "Discovery")
    days = client.get("compartment_days", 0)
    pid = client.get("prospect_id", "")
    action_lower = (action or "NURTURE").upper()
    border = "push-border" if action_lower == "PUSH" else "nurture-border" if action_lower == "NURTURE" else "pause-border"
    badge = "🎯" if action_lower == "PUSH" else "💡" if action_lower == "NURTURE" else "🌱"
    subtitle = f"In stage {comp} for {days} days" + (" – might be stuck" if days > 21 and comp == "Exploration" else "") if show_subtitle else ""
    with st.container():
        st.markdown(f"**{first}** · {persona} · {badge} {action_lower}")
        if show_subtitle and subtitle:
            st.caption(subtitle)
        if on_click and pid:
            if st.button("👁️ View full profile", key=f"{key_prefix}_{pid}", type="secondary"):
                on_click(pid)
                st.rerun()


def render_pipeline_kanban(
    clients: List[dict],
    get_action: Callable[[dict], str],
    on_select: Callable[[str], None],
    key_prefix: str = "kanban",
):
    """
    5-column Kanban by stage. Each card shows first name, persona icon, days, action badge.
    on_select(prospect_id) when user clicks View profile.
    """
    stages = ["Discovery", "Exploration", "Serious Consideration", "Decision Prep", "Commitment"]
    cols = st.columns(5)
    for idx, stage_name in enumerate(stages):
        with cols[idx]:
            st.markdown(f"**Stage: {stage_name}**")
            in_stage = [c for c in clients if c.get("compartment") == stage_name]
            for c in in_stage[:15]:  # cap per column
                action = get_action(c)
                first = first_name_only(c.get("name"))
                days = c.get("compartment_days", 0)
                pid = c.get("prospect_id", "")
                badge = "🎯" if action == "PUSH" else "💡" if action == "NURTURE" else "🌱"
                st.markdown(f"{first} · {badge} · {days}d")
                if st.button("View", key=f"{key_prefix}_{pid}_{idx}", type="secondary"):
                    on_select(pid)
                    st.rerun()
                st.markdown("---")


def render_score_visual(score: int, label: str, note: Optional[str] = None, key_prefix: str = "score"):
    """Single horizontal bar: label, score out of 5, optional note."""
    v = max(0, min(5, int(score) if score is not None else 0))
    pct = (v / 5.0) * 100
    if v >= 4:
        fill_color = COLORS["push"]
    elif v >= 3:
        fill_color = COLORS["nurture"]
    else:
        fill_color = COLORS["pause"]
    st.markdown(f"**{label}**")
    st.markdown(
        f'<div class="sandi-coach score-bar-wrap">'
        f'<div class="score-bar-track"><div class="score-bar-fill" style="width:{pct}%; background:{fill_color};"></div></div>'
        f'<div class="sandi-coach sandi-body">{v}/5</div></div>',
        unsafe_allow_html=True,
    )
    if note:
        st.caption(note)


def render_script_box(title: str, script_text: str, key: str = "script"):
    """Copy-paste friendly script: expander with code block (user can select and copy)."""
    with st.expander(f"📞 {title}", expanded=False):
        st.code(script_text, language=None)
        st.caption("Select the text above and copy (Ctrl+C) to use in your call.")


def render_timeline(current_stage: str, days_in_stage: int, key_prefix: str = "timeline"):
    """Visual 5-step progress: Discovery → ... → Commitment, current highlighted. Stuck warning if >21 days."""
    steps = ["Discovery", "Exploration", "Serious Consideration", "Decision Prep", "Commitment"]
    try:
        idx = steps.index(current_stage)
    except ValueError:
        idx = 0
    parts = []
    for i, s in enumerate(steps):
        if i == idx:
            parts.append(f'<span class="timeline-step timeline-current">{s}</span>')
        elif i < idx:
            parts.append(f'<span class="timeline-step timeline-past">{s}</span>')
        else:
            parts.append(f'<span class="timeline-step timeline-future">{s}</span>')
    st.markdown(COACHING_CSS, unsafe_allow_html=True)
    st.markdown('<div class="sandi-coach">' + " → ".join(parts) + "</div>", unsafe_allow_html=True)
    st.caption(f"Stage {idx + 1} of 5 · {days_in_stage} days in this stage.")
    if days_in_stage > 21:
        st.warning("⚠️ Over 21 days in this stage – consider a gentle nudge or pause.")


def score_color(score: int) -> str:
    """For legacy compatibility; uses new palette."""
    if score >= 4:
        return COLORS["push"]
    if score >= 3:
        return COLORS["nurture"]
    return COLORS["pause"]


def render_score_bars(prospect: dict, key_prefix: str = "score"):
    """Four horizontal score bars (legacy + new style)."""
    dims = [
        ("Identity", prospect.get("identity_score", 0), "Ownership vs blame"),
        ("Commitment", prospect.get("commitment_score", 0), "Ability to decide"),
        ("Financial", prospect.get("financial_score", 0), "Comfort with money"),
        ("Execution", prospect.get("execution_score", 0), "Follow-through"),
    ]
    for i, (label, val, note) in enumerate(dims):
        render_score_visual(val, label, note, f"{key_prefix}_{i}")


def render_radar_chart(prospect: dict, key: str = "radar"):
    """Plotly radar for 4 dimensions (kept for optional use)."""
    try:
        import plotly.graph_objects as go
    except Exception:
        render_score_bars(prospect, key)
        return
    dims = ["Identity", "Commitment", "Financial", "Execution"]
    vals = [
        prospect.get("identity_score", 0) or 0,
        prospect.get("commitment_score", 0) or 0,
        prospect.get("financial_score", 0) or 0,
        prospect.get("execution_score", 0) or 0,
    ]
    vals = [max(0, min(5, v)) for v in vals]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]],
        theta=dims + [dims[0]],
        fill="toself",
        name="Scores",
        line=dict(color=COLORS["accent"]),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
        showlegend=False,
        margin=dict(l=80, r=80, t=40, b=40),
        height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, key=key)


def render_recommendation_card(
    action: str,
    reason: str,
    script: Optional[str] = None,
    confidence: Optional[float] = None,
    on_thumbs_up=None,
    on_thumbs_down=None,
    key_prefix: str = "rec",
):
    """Recommendation card with PUSH/NURTURE/PAUSE styling and 👍/👎 (touch-friendly)."""
    action_lower = (action or "NURTURE").upper()
    bg = COLORS["push"] if action_lower == "PUSH" else COLORS["nurture"] if action_lower == "NURTURE" else COLORS["pause"]
    conf_pct = int(round((confidence or 0) * 100))
    st.markdown(
        f'<div class="sandi-coach action-card {action_lower.lower()}" style="background:{bg}; padding:20px; border-radius:12px; color:white; font-size:18px;">'
        f'<strong>{action_lower}</strong> ({conf_pct}% confidence)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"**Why:** {reason}")
    if script:
        render_script_box("Suggested script", script, f"{key_prefix}_script")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("👍 Helpful", key=f"{key_prefix}_up"):
            if on_thumbs_up:
                on_thumbs_up()
    with c2:
        if st.button("👎 Not helpful", key=f"{key_prefix}_down"):
            if on_thumbs_down:
                on_thumbs_down()


def render_chat_message(role: str, content: str, key: str = None):
    if role == "user":
        st.markdown(f'<p class="sandi-coach sandi-body" style="text-align:right; background:#e3f2fd; padding:10px; border-radius:8px;">{content}</p>', unsafe_allow_html=True)


# ---- ROI & celebration ----

def celebrate_time_saved(hours: float) -> None:
    """Show celebration toasts at 1hr, 5hr, 10hr thresholds (balloons / encouraging message)."""
    if hours >= 10:
        st.balloons()
        st.success("🍷 Go get some wine, you've earned it! You've saved **10+ hours** this week.")
    elif hours >= 5:
        st.snow()
        st.success("🎉 **5 hours saved** – you're on fire! Keep it up.")
    elif hours >= 1:
        st.success("⭐ **1 hour saved** – great start! Every minute counts.")


def roi_dashboard_card(time_saved_hours: float, revenue_projection: float, clients_contacted: int, key_prefix: str = "roi") -> None:
    """Three beautiful metric cards: Time saved, $ projected, Clients contacted."""
    st.markdown(COACHING_CSS, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("⏱️ Time saved (hrs)", f"{time_saved_hours:.1f}", help="Based on baseline vs actual time in app")
    with c2:
        st.metric("💰 Revenue projection ($)", f"{revenue_projection:,.0f}", help="From time reinvested and client outcomes")
    with c3:
        st.metric("👤 Clients contacted", str(clients_contacted), help="Marked as contacted this period")


def gentle_nudge_context(efficiency_pct: float) -> Optional[str]:
    """Suggest lead gen research when efficiency > 80%. Returns message or None."""
    if efficiency_pct >= 80:
        return "Ready for some research on how to grow your clientele? You're using your time so well – consider filling saved hours with new leads."
    return None


def render_research_button(hours_saved: float, key: str = "research_btn") -> bool:
    """When Sandi has saved >10 hours, show button 'Research: How to fill these 10 hours with new clients'. Returns True if clicked."""
    if hours_saved < 10:
        return False
    if st.button("📚 Research: How to fill these 10 hours with new clients", key=key, type="secondary"):
        return True
    return False
