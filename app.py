"""
Sandi Bot - Streamlit application.
Visual coaching UI: Today's Dashboard, Coaching Session, People Like Them, Insights.
Sidebar: Sandi Bot chat, customer entry. Backend logic unchanged.
"""
import sys
import streamlit as st
import pandas as pd
from pathlib import Path

sys_path = str(Path(__file__).parent)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

import database
import synthetic_data
import ml_models
import sandi_bot
import natural_sandi_bot
from components import (
    render_sandi_avatar,
    render_customer_entry_form,
    render_insight_metric,
    render_client_card,
    render_pipeline_kanban,
    render_score_visual,
    render_score_bars,
    render_script_box,
    render_timeline,
    render_recommendation_card,
    first_name_only,
    action_color,
    COACHING_CSS,
    HEADER_CSS,
    COLORS,
)

st.set_page_config(
    page_title="Sandi Bot – Coaching Command Center",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(COACHING_CSS, unsafe_allow_html=True)
st.markdown(HEADER_CSS, unsafe_allow_html=True)

# ---- Global styling ----
st.markdown("""
<style>
.stMetric { background: #ffffff; padding: 16px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { font-size: 16px; min-height: 44px; padding: 10px 20px; }
div[data-testid="stVerticalBlock"] > div { font-size: 16px; }
button { min-height: 44px !important; }
</style>
""", unsafe_allow_html=True)

# ---- Session state ----
if "prospects" not in st.session_state:
    st.session_state.prospects = []
if "ml_model" not in st.session_state:
    st.session_state.ml_model = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "sandi_prospect_id" not in st.session_state:
    st.session_state.sandi_prospect_id = None
if "sandi_prospect_name" not in st.session_state:
    st.session_state.sandi_prospect_name = None
if "current_prospect" not in st.session_state:
    st.session_state.current_prospect = None
if "selected_prospect" not in st.session_state:
    st.session_state.selected_prospect = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = 0
if "show_priorities_only" not in st.session_state:
    st.session_state.show_priorities_only = False


def load_data():
    synthetic_data.ensure_synthetic_data()
    st.session_state.prospects = database.get_all_prospects()
    st.session_state.ml_model = ml_models.build_and_fit_ml(st.session_state.prospects)


def on_start_session(prospect_id: str, name: str):
    """Load prospect into session. Do not set sandi_customer_id/sandi_customer_name here (widget keys)."""
    load_data()
    prospect = database.get_prospect(prospect_id)
    if prospect:
        st.session_state.current_prospect = prospect
        st.session_state.sandi_prospect_id = prospect_id
        db_name = prospect.get("name") or name
        st.session_state.sandi_prospect_name = db_name
    else:
        st.session_state.current_prospect = None
        st.session_state.sandi_prospect_id = prospect_id
        st.session_state.sandi_prospect_name = name


def on_select_prospect(prospect_id: str):
    """Set selected prospect and request tab switch. Do not set main_tab here (widget key)."""
    st.session_state.selected_prospect = prospect_id
    st.session_state.goto_tab_index = 1  # switch to Coaching Session on next run


if not st.session_state.prospects:
    load_data()

# Apply tab switch requested by "View full profile" (cannot set main_tab inside button callback)
tab_names = ["Today's Dashboard", "Coaching Session", "People Like Them", "Insights"]
if "goto_tab_index" in st.session_state:
    idx = st.session_state.goto_tab_index
    del st.session_state.goto_tab_index
    st.session_state.main_tab = tab_names[idx]
    st.session_state.active_tab = idx
    st.rerun()

prospects = st.session_state.prospects
ml_model = st.session_state.ml_model
df = pd.DataFrame(prospects) if prospects else pd.DataFrame()

# ---- Sidebar ----
with st.sidebar:
    render_sandi_avatar(
        show_name=True,
        status="Ready to help" if st.session_state.sandi_prospect_id else "Enter customer to start",
    )
    prospect_id, prospect_name = render_customer_entry_form(on_start_callback=on_start_session)
    current = st.session_state.current_prospect
    # Show loaded customer number and name (from DB when available so name is always correct)
    if prospect_id or current:
        sid = prospect_id or (current.get("prospect_id") if current else "")
        sname = (current.get("name") if current else None) or prospect_name or ""
        if sid or sname:
            st.markdown(f"**Current session:** {sid} · **{sname}**")
    st.divider()
    st.subheader("Chat with Sandi")
    for msg in st.session_state.chat_messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        if role == "user":
            st.chat_message("user").write(content)
        else:
            st.chat_message("assistant").write(content)
    user_input = st.chat_input("Ask Sandi...")
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        response = natural_sandi_bot.simple_chat_response(user_input, prospect=current, history=st.session_state.chat_messages[:-1])
        st.session_state.chat_messages.append({"role": "assistant", "content": response})
        database.insert_chat_message(prospect_id, "user", user_input)
        database.insert_chat_message(prospect_id, "assistant", response, None)
        st.rerun()

# ---- Main: tab selector (radio; switch via goto_tab_index from "View full profile") ----
if "main_tab" not in st.session_state:
    st.session_state.main_tab = tab_names[0]
selected_tab = st.radio("", tab_names, key="main_tab", horizontal=True)
st.session_state.active_tab = tab_names.index(selected_tab)

st.title("🧢 Sandi Bot – Coaching Command Center")
st.caption("Your pipeline at a glance. Use the sidebar to start a strategy session with Sandi.")

# ---- Tab 1: Today's Coaching Dashboard ----
if selected_tab == "Today's Dashboard":
    if df.empty:
        st.info("No clients loaded. Data will load automatically.")
    else:
        # Metric cards: PUSH count, NURTURE count, Stuck >21 days in Exploration
        push_count = sum(1 for p in prospects if sandi_bot.get_recommendation(p)[0] == "PUSH")
        nurture_count = sum(1 for p in prospects if sandi_bot.get_recommendation(p)[0] == "NURTURE")
        stuck_count = sum(1 for p in prospects if p.get("compartment") == "Exploration" and (p.get("compartment_days") or 0) > 21)
        m1, m2, m3 = st.columns(3)
        with m1:
            render_insight_metric(push_count, "🎯 Ready for Decision", key="met1")
        with m2:
            render_insight_metric(nurture_count, "💡 Need Nurturing", key="met2")
        with m3:
            render_insight_metric(stuck_count, "⚠️ Stuck >21 days", key="met3")
        def get_action(p):
            return sandi_bot.get_recommendation(p)[0]
        view_mode = st.radio(
            "View",
            ["Pipeline (by stage)", "Priority stack"],
            key="dashboard_view_radio",
            horizontal=True,
        )
        st.session_state.show_priorities_only = st.checkbox("Show today's priorities only (PUSH + NURTURE)", value=st.session_state.show_priorities_only, key="prio_only")
        if view_mode == "Priority stack":
            # Stacked cards: PUSH + NURTURE only, sorted by urgency (days in stage desc)
            stack_list = [p for p in prospects if get_action(p) in ("PUSH", "NURTURE")]
            stack_list.sort(key=lambda p: (p.get("compartment_days") or 0), reverse=True)
            st.caption("People ready for a decision or who need nurturing. Sorted by time in current stage (longest first).")
            for p in stack_list:
                action = get_action(p)
                with st.container():
                    render_client_card(p, action, on_click=on_select_prospect, key_prefix=f"stack_{p.get('prospect_id')}", show_subtitle=True)
        else:
            # Kanban: 5 columns by stage
            if st.session_state.show_priorities_only:
                show_list = [p for p in prospects if get_action(p) in ("PUSH", "NURTURE")]
                show_list.sort(key=lambda p: (p.get("compartment_days") or 0), reverse=True)
            else:
                show_list = prospects
            render_pipeline_kanban(show_list, get_action, on_select_prospect, key_prefix="dash_kanban")

# ---- Tab 2: Coaching Session View ----
elif selected_tab == "Coaching Session":
    if not prospects:
        st.info("No clients loaded. Data will load automatically.")
    else:
        sel_id = st.session_state.selected_prospect
        if not sel_id:
            sel_id = prospects[0].get("prospect_id")
        options = [p["prospect_id"] for p in prospects]
        labels = [first_name_only(p.get("name")) for p in prospects]
        default_ix = options.index(sel_id) if sel_id and sel_id in options else 0
        choice_idx = st.selectbox(
            "Select client",
            range(len(options)),
            format_func=lambda i: labels[i] if i is not None else "—",
            index=default_ix,
            key="tab2_sel",
        )
        sel_id = options[choice_idx] if choice_idx is not None else None
    if prospects and sel_id:
        p = database.get_prospect(sel_id)
        if p:
            first = first_name_only(p.get("name"))
            st.subheader(f"👤 {p.get('name', first)}")
            st.markdown(f"**Customer #:** {p.get('prospect_id', '—')} · **Name:** {p.get('name', '—')}")
            st.markdown(f"**{p.get('persona', 'Strategic')}** · Current stage: **{p.get('compartment', 'Discovery')}**")
            left, right = st.columns([2, 3])
            with left:
                st.markdown("**The story so far**")
                render_timeline(p.get("compartment", "Discovery"), p.get("compartment_days", 0), "tab2_tl")
                st.caption(f"Last interaction: {p.get('last_interaction_date', '—')}. Ready for next step: {int(round(float(p.get('conversion_probability', 0)) * 100))}%")
            with right:
                st.markdown("**Today's playbook**")
                action, conf, reason = sandi_bot.get_recommendation(p)
                conf_pct = int(round(conf * 100))
                st.progress(conf_pct / 100.0)
                st.caption(f"Confidence: {conf_pct}%")
                st.markdown(f"**Why this action:** {reason}")
                tactics = sandi_bot.get_tactics(p.get("persona", "Strategic"), action)
                if tactics:
                    render_script_box("Opening line", tactics[0], "tab2_open")
                    if len(tactics) > 1:
                        render_script_box("If they resist", tactics[1], "tab2_resist")
                    if len(tactics) > 2:
                        render_script_box("Closing / homework", tactics[2], "tab2_close")
                st.markdown("**Readiness**")
                for label, key, note in [
                    ("Identity", "identity_score", "Ownership vs blame"),
                    ("Commitment", "commitment_score", "Ability to decide"),
                    ("Financial", "financial_score", "Comfort with money"),
                    ("Execution", "execution_score", "Follow-through"),
                ]:
                    render_score_visual(p.get(key, 0), label, note, f"tab2_{key}")
                def on_up():
                    database.insert_feedback(p["prospect_id"], action, 1)
                    st.toast("Thanks! Feedback recorded.")
                def on_down():
                    database.insert_feedback(p["prospect_id"], action, 0)
                    st.toast("Thanks! We'll improve.")
                render_recommendation_card(action, reason, script=tactics[0] if tactics else None, confidence=conf, on_thumbs_up=on_up, on_thumbs_down=on_down, key_prefix="tab2_rec")
                st.markdown("---")
                st.caption("Quick actions: Mark as Contacted Today · Move to Next Stage · Add Red Flag (coming soon)")

# ---- Tab 3: People Like [Name] ----
elif selected_tab == "People Like Them":
    if not prospects or not ml_model:
        st.info("Load clients first.")
    else:
        ref_options = [p["prospect_id"] for p in prospects]
        ref_labels = [first_name_only(p.get("name")) for p in prospects]
        ref_idx = st.selectbox("Find people similar to...", range(len(ref_options)), format_func=lambda i: ref_labels[i], key="tab3_ref")
        ref_id = ref_options[ref_idx]
        ref = database.get_prospect(ref_id)
        if ref:
            similar = ml_model.get_similar_prospects(prospects, ref, top_n=9)
            st.subheader(f"People like {first_name_only(ref.get('name'))}")
            # Hero card
            action_r = sandi_bot.get_recommendation(ref)[0]
            with st.container():
                st.markdown(f"**{ref.get('name')}** · {ref.get('persona')} · Stage: {ref.get('compartment')} · {ref.get('compartment_days', 0)} days")
                if st.button("👁️ View full profile", key="tab3_hero"):
                    on_select_prospect(ref_id)
                    st.rerun()
            st.markdown("---")
            # Grid of similar (3 columns)
            cols = st.columns(3)
            for i, sim in enumerate(similar):
                with cols[i % 3]:
                    first = first_name_only(sim.get("name"))
                    st.markdown(f"**{first}** · {sim.get('persona')} · Stage: {sim.get('compartment')}")
                    st.caption(f"Both {sim.get('persona')} in stage: {sim.get('compartment')}")
                    if st.button("View profile", key=f"tab3_sim_{sim.get('prospect_id')}_{i}"):
                        on_select_prospect(sim["prospect_id"])
                        st.rerun()
            st.markdown("---")
            # Insight box
            persona = ref.get("persona", "Strategic")
            comp = ref.get("compartment", "Discovery")
            tactics = sandi_bot.get_tactics(persona, sandi_bot.get_recommendation(ref)[0])
            insight = f"**Pattern:** {persona} in {comp} often respond well to: *{tactics[0][:80]}...*" if tactics else f"Focus on one clear next step for {persona} in {comp}."
            st.info(insight)

# ---- Tab 4: Coaching Insights Dashboard ----
else:
    if df.empty:
        st.info("Load clients to see insights.")
    else:
        comp_order = ["Discovery", "Exploration", "Serious Consideration", "Decision Prep", "Commitment"]
        by_comp = df.groupby("compartment", sort=False).size().reindex(comp_order).fillna(0)
        by_persona = df.groupby("persona").size()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Where people get stuck (by stage)")
            try:
                import plotly.graph_objects as go
                fig = go.Figure(go.Bar(x=by_comp.index, y=by_comp.values, marker_color=COLORS["accent"]))
                fig.update_layout(height=280, margin=dict(t=20, b=60), xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="insight_bar")
            except Exception:
                st.write(by_comp)
        with c2:
            st.subheader("Persona distribution")
            try:
                import plotly.graph_objects as go
                fig = go.Figure(go.Pie(labels=by_persona.index, values=by_persona.values, hole=0.5))
                fig.update_layout(height=280, margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True, key="insight_pie")
            except Exception:
                st.write(by_persona)
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Success indicators (avg readiness by stage)")
            try:
                import plotly.graph_objects as go
                comp_means = df.groupby("compartment")[["identity_score", "commitment_score", "financial_score", "execution_score"]].mean()
                comp_means["avg"] = comp_means.mean(axis=1)
                comp_means = comp_means.reindex(comp_order).dropna(how="all")
                fig = go.Figure(go.Bar(x=comp_means.index, y=comp_means["avg"].values, marker_color=COLORS["push"]))
                fig.update_layout(height=260, margin=dict(t=20, b=80), xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="insight_adv")
            except Exception:
                st.write("—")
        with c4:
            st.subheader("This week's momentum")
            st.caption("Stage distribution (snapshot). Movement over time can be added when you track history.")
            st.write(by_comp)
        st.markdown("---")
        st.subheader("Sandi's insights")
        overthinker_avg = df[df["persona"] == "Overthinker"]["compartment_days"].mean() if "Overthinker" in df["persona"].values else 0
        other_avg = df[df["persona"] != "Overthinker"]["compartment_days"].mean() if len(df[df["persona"] != "Overthinker"]) else 0
        insight1 = "Overthinkers tend to stay in Exploration longer than others. Assign one clear homework and a short follow-up." if overthinker_avg > other_avg else "Spread across personas is balanced. Focus on Ready for Decision first."
        burning = df[df["persona"] == "Burning Bridge"]
        insight2 = "Most of your Burning Bridge clients move fast; watch for those who pause at Decision Prep." if len(burning) else ""
        st.markdown(f"- {insight1}")
        if insight2:
            st.markdown(f"- {insight2}")
