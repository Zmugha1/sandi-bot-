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
import roi_calculator
from datetime import datetime, timezone
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
    celebrate_time_saved,
    roi_dashboard_card,
    gentle_nudge_context,
    render_research_button,
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
if "roi_timer_start" not in st.session_state:
    st.session_state.roi_timer_start = None
if "roi_timer_prospect_id" not in st.session_state:
    st.session_state.roi_timer_prospect_id = None
if "roi_celebration_shown_10hr" not in st.session_state:
    st.session_state.roi_celebration_shown_10hr = False


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
    st.session_state.goto_tab_index = 2  # Coaching Session

def _parse_iso(s: str):
    if not s:
        return datetime.now(timezone.utc)
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)


def _record_time_and_outcome(prospect_id: str, activity_type: str, baseline_key: str):
    """Stop ROI timer, record time_tracking and outcome, update weekly_roi, show delights."""
    now = datetime.now(timezone.utc).isoformat()
    start = st.session_state.get("roi_timer_start")
    st.session_state.roi_timer_start = None
    st.session_state.roi_timer_prospect_id = None
    if not start:
        return
    start_dt = _parse_iso(start)
    end_dt = datetime.now(timezone.utc)
    duration_seconds = max(0, (end_dt - start_dt).total_seconds())
    baseline_seconds = roi_calculator.BASELINE_SECONDS.get(baseline_key, roi_calculator.BASELINE_SECONDS["per_client_session"])
    time_saved_seconds = roi_calculator.time_saved_for_session(baseline_key, duration_seconds)
    database.insert_time_tracking(prospect_id, activity_type, start, now, duration_seconds, baseline_seconds, time_saved_seconds)
    if activity_type == "mark_contacted":
        database.insert_outcome(prospect_id, "contacted", 1)
        if database.get_outcomes_count("contacted") == 1:
            st.balloons()
            st.success("First win! You marked your first client as contacted.")
    week_start = roi_calculator.get_week_start(datetime.now(timezone.utc))
    total_hr = database.get_time_saved_total()
    contacted = database.get_outcomes_count("contacted")
    advanced = database.get_outcomes_count("advancement")
    rev = roi_calculator.revenue_projection(total_hr, contacted, advanced)
    database.upsert_weekly_roi(week_start, time_saved_hours=total_hr, revenue_projection=rev, clients_contacted=contacted, clients_advanced=advanced)
    if total_hr >= 1:
        celebrate_time_saved(total_hr)
    if total_hr >= 10 and not st.session_state.get("roi_celebration_shown_10hr"):
        st.session_state.roi_celebration_shown_10hr = True
        st.success("🍷 Go get some wine, you've earned it! You've saved **10+ hours**.")
    usage_dates = database.get_usage_dates()
    consecutive = roi_calculator.get_consecutive_usage_days(usage_dates)
    if consecutive >= 5:
        st.toast("You're building a powerful habit 💪")


if not st.session_state.prospects:
    load_data()

# Apply tab switch requested by "View full profile" (cannot set main_tab inside button callback)
tab_names = ["How to use", "Today's Dashboard", "Coaching Session", "People Like Them", "Insights", "ROI"]
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

# ---- Tab 0: How to use this dashboard ----
if selected_tab == "How to use":
    st.header("📖 How to use this dashboard")
    st.markdown("Follow these steps to get the most from Sandi Bot. Use the **sidebar** on the left and the **tabs** at the top.")
    st.markdown("---")
    st.subheader("🧢 1. Start a strategy session (sidebar)")
    st.markdown("""
    - In the **left sidebar**, find **Strategy session**.
    - Enter **Customer #** (e.g. `P001`, `P086`).
    - Enter **Name** (e.g. the client’s full name).
    - Click **Start ▶**.
    - You will see **Current session: [Customer #] · [Name]** once loaded. The name comes from the system so it stays correct.
    - Sandi is then ready for chat. You can ask things like *Should I push or pause?* or *Help me plan my next call with the customer.*
    """)
    st.markdown("---")
    st.subheader("💬 2. Chat with Sandi (sidebar)")
    st.markdown("""
    - Below the strategy session you’ll see **Chat with Sandi**.
    - Type in the chat box and press Enter.
    - **Good questions to ask:**
      - *Should I push or pause?*
      - *What homework should I give them?*
      - *Help me plan my next call with the customer.*
      - *What should I say on the call?*
    - Sandi uses the **current session** client. Load a customer first with **Start ▶** if you see a message asking you to.
    """)
    st.markdown("---")
    st.subheader("📊 3. Today’s Dashboard tab")
    st.markdown("""
    - At the top, click **Today's Dashboard** to see your pipeline.
    - **Three metric cards** at the top:
      - **🎯 Ready for Decision** – number of clients where the system suggests PUSH (call today).
      - **💡 Need Nurturing** – number where it suggests NURTURE (keep engaging, assign homework).
      - **⚠️ Stuck >21 days** – clients in Exploration for more than 21 days (may need a nudge or pause).
    - **View:** Choose **Pipeline (by stage)** or **Priority stack**.
      - **Pipeline (by stage):** Five columns (Discovery → … → Commitment). Each client has a **View** button; click it to open their Coaching Session.
      - **Priority stack:** List of PUSH + NURTURE clients, sorted by time in stage. Each card has **👁️ View full profile** – click to go to Coaching Session for that client.
    - **Show today's priorities only:** Check this to hide PAUSE clients and focus on people to act on.
    """)
    st.markdown("---")
    st.subheader("👤 4. Coaching Session tab")
    st.markdown("""
    - Click **Coaching Session** to work with one client in detail.
    - **Select client** from the dropdown (shown by first name).
    - You’ll see **Customer #** and **Name** at the top so you know who you’re viewing.
    - **The story so far:** A timeline shows their stage (Discovery → … → Commitment). If they’ve been in a stage over 21 days, you’ll see a short warning.
    - **Today’s playbook:**
      - **Action:** 🎯 PUSH, 💡 NURTURE, or 🌱 PAUSE with a **confidence %**.
      - **Why this action** – short plain-English reason.
      - **📞 Suggested script** – expand the section to see opening line, if they resist, and closing/homework. Select the text and copy to use on your call.
    - **Readiness:** Four bars – **Identity**, **Commitment**, **Financial**, **Execution** (each 1–5 with a short note).
    - **👍 Helpful / 👎 Not helpful** – see the section below for how to use these.
    """)
    st.markdown("---")
    st.subheader("👍 Helpful and 👎 Not helpful")
    st.markdown("""
    On the **Coaching Session** tab, under the recommendation (PUSH / NURTURE / PAUSE), you’ll see two buttons:

    - **👍 Helpful** – Click this when the recommendation and script were useful (e.g. you followed the advice and it worked, or it matched what you’d do).
    - **👎 Not helpful** – Click this when the recommendation didn’t fit (e.g. wrong action, script didn’t work, or the reason didn’t match this client).

    **What happens when you click:**
    - Your choice is **saved** (which client, which recommendation, and whether it was helpful or not).
    - The **readiness bars** and **confidence %** on the screen **do not change**. They are based on this client’s data only.
    - Over time, saved feedback is used to **improve** how Sandi suggests PUSH, NURTURE, or PAUSE for future clients.

    **When to use which:**
    - Use **Helpful** when the suggestion felt right or you used it successfully.
    - Use **Not helpful** when the suggestion felt off or you chose a different action—so the system can learn.
    """)
    st.markdown("---")
    st.subheader("🔗 5. People Like Them tab")
    st.markdown("""
    - Click **People Like Them** to find clients similar to one you choose.
    - **Find people similar to…** – pick a client from the dropdown.
    - You’ll see a **hero card** for that person and a **👁️ View full profile** button to open their Coaching Session.
    - Below, a **grid of similar clients** (same persona/stage patterns). Each has **View profile** to open their Coaching Session.
    - An **insight box** at the bottom suggests a pattern or tactic for that type of client.
    """)
    st.markdown("---")
    st.subheader("📈 6. Insights tab")
    st.markdown("""
    - Click **Insights** for a high-level view of your pipeline.
    - **Where people get stuck (by stage)** – bar chart of how many are in each stage.
    - **Persona distribution** – pie chart of the four types (Quiet Decider, Overthinker, Burning Bridge, Strategic).
    - **Success indicators** – average readiness by stage.
    - **Sandi’s insights** – short bullets (e.g. Overthinkers in Exploration, Burning Bridge at Decision Prep).
    """)
    st.markdown("---")
    st.subheader("🎯 Icon guide")
    st.markdown("""
    | Icon | Meaning |
    |------|---------|
    | 🧢 | Sandi Bot |
    | 👤 | Client / person |
    | 🎯 | PUSH – ready for decision, call today |
    | 💡 | NURTURE – keep engaging, assign homework |
    | 🌱 | PAUSE – step back for about 2 weeks |
    | 📞 | Call / script |
    | ⚠️ | Stuck or warning (e.g. >21 days in stage) |
    | 👁️ | View full profile / open Coaching Session |
    | 👍 | Helpful – the recommendation was useful; your feedback is saved. |
    | 👎 | Not helpful – the recommendation didn’t fit; your feedback is saved to improve future suggestions. (Neither button changes the bars or confidence on screen.) |
    """)
    st.markdown("---")
    st.caption("Need help? Start with the sidebar: enter a Customer # and Name, click Start ▶, then ask Sandi in chat.")

# ---- Tab 1: Today's Coaching Dashboard ----
elif selected_tab == "Today's Dashboard":
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
            # Start ROI timer when opening this client card (or restart if switched client)
            if st.session_state.roi_timer_prospect_id != sel_id or not st.session_state.roi_timer_start:
                st.session_state.roi_timer_start = datetime.now(timezone.utc).isoformat()
                st.session_state.roi_timer_prospect_id = sel_id
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
                st.caption("👍 👎 Your feedback is saved to improve future recommendations. It does not change the readiness bars or confidence above—those are based on this client's data.")
                st.markdown("---")
                st.caption("Quick actions (these record time saved and outcomes):")
                q1, q2 = st.columns(2)
                with q1:
                    if st.button("✓ Mark as Contacted", key="tab2_mark_contacted", type="primary"):
                        _record_time_and_outcome(p["prospect_id"], "mark_contacted", "mark_contacted")
                        st.rerun()
                with q2:
                    if st.button("📞 I planned my call", key="tab2_plan_call"):
                        _record_time_and_outcome(p["prospect_id"], "plan_call", "plan_call")
                        st.rerun()
                st.caption("Move to Next Stage · Add Red Flag (coming soon)")

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
elif selected_tab == "Insights":
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

# ---- Tab 5: ROI ----
elif selected_tab == "ROI":
    total_hr = database.get_time_saved_total()
    contacted = database.get_outcomes_count("contacted")
    advanced = database.get_outcomes_count("advancement")
    rev = roi_calculator.revenue_projection(total_hr, contacted, advanced)
    roi_dashboard_card(total_hr, rev, contacted, key_prefix="roi_tab")
    st.markdown("---")
    st.subheader("Weekly trends")
    by_week = database.get_time_tracking_by_week(12)
    if by_week:
        # Chart: oldest first for trend left-to-right
        ordered = list(reversed(by_week))
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Scatter(
                x=[r["date"] for r in ordered],
                y=[r["time_saved_hours"] for r in ordered],
                mode="lines+markers",
                line=dict(color=COLORS["accent"], width=2),
                marker=dict(size=8),
            ))
            fig.update_layout(
                height=320,
                margin=dict(t=20, b=60),
                xaxis_title="Date",
                yaxis_title="Time saved (hours)",
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig, use_container_width=True, key="roi_trend")
        except Exception:
            st.write("Time saved by day: ", ordered)
    else:
        st.caption("Complete client sessions (Mark as Contacted or Plan Call) to see your time-saved trend here.")
    # Efficiency nudge: this week's time saved vs 10 hr target
    week_start = roi_calculator.get_week_start(datetime.now(timezone.utc))
    by_day = database.get_time_tracking_by_week(2)
    this_week_hr = sum(r["time_saved_hours"] for r in by_day if r.get("date") and r["date"] >= week_start)
    efficiency_pct = min(100.0, (this_week_hr / 10.0) * 100.0) if this_week_hr else 0
    nudge = gentle_nudge_context(efficiency_pct)
    if nudge:
        st.info(nudge)
    if total_hr >= 10:
        render_research_button(total_hr, key="roi_research_btn")
