"""
Sandi Bot - UI components: avatar, customer entry form, radar chart,
score bars (traffic colors), recommendation cards with feedback buttons.
"""
import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional, List, Any

# Senior-friendly: large fonts, high contrast
HEADER_CSS = """
<style>
.sandi-header { font-size: 42px; font-weight: 700; color: #1a365d; margin-bottom: 8px; }
.sandi-status { font-size: 18px; color: #2d3748; }
.sandi-body { font-size: 18px; line-height: 1.5; color: #2d3748; }
.score-bar-green { background: #38a169; height: 24px; border-radius: 4px; }
.score-bar-yellow { background: #d69e2e; height: 24px; border-radius: 4px; }
.score-bar-red { background: #e53e3e; height: 24px; border-radius: 4px; }
.recommend-card { padding: 16px; border-radius: 8px; margin: 8px 0; font-size: 18px; }
.recommend-push { border-left: 6px solid #38a169; background: #f0fff4; }
.recommend-nurture { border-left: 6px solid #d69e2e; background: #fffff0; }
.recommend-pause { border-left: 6px solid #e53e3e; background: #fff5f5; }
</style>
"""


def render_sandi_avatar(show_name: bool = True, status: str = "Ready to help"):
    """Sandi Bot avatar and header in sidebar."""
    st.markdown(HEADER_CSS, unsafe_allow_html=True)
    st.markdown("🧢")
    if show_name:
        st.markdown('<p class="sandi-header">Sandi Bot</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="sandi-status">{status}</p>', unsafe_allow_html=True)


def render_customer_entry_form(on_start_callback=None):
    """
    Customer # and Name fields plus Start button.
    Returns (prospect_id, name) from session or form; on_start_callback(prospect_id, name) called on Start.
    """
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


def score_color(score: int) -> str:
    """Traffic light: green >=4, yellow 3, red <=2."""
    if score >= 4:
        return "#38a169"
    if score >= 3:
        return "#d69e2e"
    return "#e53e3e"


def render_score_bars(prospect: dict, key_prefix: str = "score"):
    """Four horizontal score bars with traffic colors."""
    dims = [
        ("Identity", prospect.get("identity_score", 0)),
        ("Commitment", prospect.get("commitment_score", 0)),
        ("Financial", prospect.get("financial_score", 0)),
        ("Execution", prospect.get("execution_score", 0)),
    ]
    for i, (label, val) in enumerate(dims):
        v = max(0, min(5, int(val) if val is not None else 0))
        pct = (v / 5.0) * 100
        c = score_color(v)
        st.markdown(f"**{label}**")
        st.markdown(
            f'<div style="background: #e2e8f0; border-radius: 4px; height: 24px;">'
            f'<div style="width: {pct}%; background: {c}; height: 24px; border-radius: 4px;"></div></div>',
            unsafe_allow_html=True,
        )


def render_radar_chart(prospect: dict, key: str = "radar"):
    """Simple radar-style display of 4 dimensions (as bar or polar). Using plotly if available else text."""
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
        line=dict(color="#3182ce"),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
        showlegend=False,
        margin=dict(l=80, r=80, t=40, b=40),
        height=280,
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
    """Recommendation card with PUSH/NURTURE/PAUSE styling and 👍/👎 buttons."""
    css_class = "recommend-push" if action == "PUSH" else "recommend-nurture" if action == "NURTURE" else "recommend-pause"
    conf_text = f" ({int(round((confidence or 0) * 100))}% confidence)" if confidence is not None else ""
    st.markdown(f'<div class="recommend-card {css_class}">**{action}**{conf_text}<br/><br/>{reason}</div>', unsafe_allow_html=True)
    if script:
        st.markdown("**Suggested script:**")
        st.code(script, language=None)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👍 Helpful", key=f"{key_prefix}_up"):
            if on_thumbs_up:
                on_thumbs_up()
    with col2:
        if st.button("👎 Not helpful", key=f"{key_prefix}_down"):
            if on_thumbs_down:
                on_thumbs_down()


def render_chat_message(role: str, content: str, key: str = None):
    """One chat bubble (user or assistant)."""
    if role == "user":
        st.markdown(f'<p class="sandi-body" style="text-align:right; background:#e6fffa; padding:8px; border-radius:8px;">{content}</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="sandi-body" style="background:#f7fafc; padding:8px; border-radius:8px;">{content}</p>', unsafe_allow_html=True)
