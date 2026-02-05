"""
Sandi Bot - Streamlit application.
Tabs: Command Center, Person Detail, Similar Groups, Patterns.
Sidebar: Sandi Bot chat, customer entry, real-time updates.
"""
import sys
import streamlit as st
import pandas as pd
from pathlib import Path

# Add app directory to path
sys_path = str(Path(__file__).parent)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

import database
import synthetic_data
import ml_models
import sandi_bot
from components import (
    render_sandi_avatar,
    render_customer_entry_form,
    render_score_bars,
    render_radar_chart,
    render_recommendation_card,
    HEADER_CSS,
)

# Page config - senior-friendly
st.set_page_config(
    page_title="Sandi Bot – Coaching Command Center",
    page_icon="👩‍💼",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(HEADER_CSS, unsafe_allow_html=True)

# Session state
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


def load_data():
    """Ensure DB and synthetic data; load prospects and fit ML."""
    synthetic_data.ensure_synthetic_data()
    st.session_state.prospects = database.get_all_prospects()
    st.session_state.ml_model = ml_models.build_and_fit_ml(st.session_state.prospects)


def on_start_session(prospect_id: str, name: str):
    """Load prospect into context for Sandi."""
    load_data()
    prospect = database.get_prospect(prospect_id)
    if prospect:
        st.session_state.current_prospect = prospect
        st.session_state.sandi_prospect_id = prospect_id
        st.session_state.sandi_prospect_name = prospect.get("name") or name
    else:
        st.session_state.current_prospect = None
        st.session_state.sandi_prospect_id = prospect_id
        st.session_state.sandi_prospect_name = name


# Load data once
if not st.session_state.prospects:
    load_data()

prospects = st.session_state.prospects
ml_model = st.session_state.ml_model
df = pd.DataFrame(prospects) if prospects else pd.DataFrame()

# ----- Sidebar: Sandi Bot -----
with st.sidebar:
    render_sandi_avatar(
        show_name=True,
        status="Ready to help" if st.session_state.sandi_prospect_id else "Enter customer to start",
    )
    prospect_id, prospect_name = render_customer_entry_form(on_start_callback=on_start_session)
    current = st.session_state.current_prospect

    # Chat
    st.divider()
    st.subheader("Chat with Sandi")

    # Display history
    for msg in st.session_state.chat_messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        if role == "user":
            st.chat_message("user").write(content)
        else:
            st.chat_message("assistant").write(content)

    # Input
    user_input = st.chat_input("Ask Sandi...")
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        intent = sandi_bot.detect_intent(user_input)
        response, action, confidence, script_snippet, tactics_list = sandi_bot.generate_response(
            intent, current, prospect_id, prospect_name
        )
        st.session_state.chat_messages.append({"role": "assistant", "content": response})
        database.insert_chat_message(prospect_id, "user", user_input)
        database.insert_chat_message(prospect_id, "assistant", response, {"action": action, "confidence": confidence})
        st.rerun()

# ----- Main: Tabs -----
st.title("👩‍💼 Sandi Bot – Coaching Command Center")
st.caption("100 prospects loaded. Use the sidebar to start a strategy session with Sandi.")

tab1, tab2, tab3, tab4 = st.tabs(["Command Center", "Person Detail", "Similar Groups", "Patterns"])

with tab1:
    st.header("Command Center")
    if not df.empty:
        # Summary table: prospect_id, name, persona, compartment, action recommendation
        display_df = df[["prospect_id", "name", "persona", "compartment", "conversion_probability"]].copy()
        display_df["Conversion %"] = (display_df["conversion_probability"] * 100).round(0).astype(int).astype(str) + "%"
        display_df = display_df.drop(columns=["conversion_probability"])
        st.dataframe(display_df, use_container_width=True, height=400)
    else:
        st.info("No prospects. Run synthetic_data.ensure_synthetic_data() to load 100 prospects.")

with tab2:
    st.header("Person Detail")
    sel_id = st.selectbox(
        "Select prospect",
        options=[p["prospect_id"] for p in prospects],
        key="tab2_sel",
    )
    if sel_id:
        p = database.get_prospect(sel_id)
        if p:
            st.subheader(p.get("name", sel_id))
            c1, c2 = st.columns(2)
            with c1:
                render_score_bars(p, "tab2_bars")
            with c2:
                render_radar_chart(p, "tab2_radar")
            st.write("**Persona:**", p.get("persona"), "| **Compartment:**", p.get("compartment"), "| **Days:**", p.get("compartment_days"))
            st.write("**Conversion probability:**", f"{float(p.get('conversion_probability', 0))*100:.0f}%")
            can_advance, advance_reason = sandi_bot.recommend_advancement(p)
            st.write("**Advancement:**", advance_reason)
            action, conf, reason = sandi_bot.get_recommendation(p)
            def on_up():
                database.insert_feedback(p["prospect_id"], action, 1)
                st.toast("Thanks! Feedback recorded.")
            def on_down():
                database.insert_feedback(p["prospect_id"], action, 0)
                st.toast("Thanks! We'll improve.")
            render_recommendation_card(
                action, reason,
                script=sandi_bot.get_tactics(p.get("persona", "Strategic"), action)[0] if sandi_bot.get_tactics(p.get("persona", "Strategic"), action) else None,
                confidence=conf,
                on_thumbs_up=on_up,
                on_thumbs_down=on_down,
                key_prefix="tab2_rec",
            )

with tab3:
    st.header("Similar Groups")
    ref_id = st.selectbox("Reference prospect", options=[p["prospect_id"] for p in prospects], key="tab3_ref")
    if ref_id and ml_model:
        ref = database.get_prospect(ref_id)
        if ref:
            similar = ml_model.get_similar_prospects(prospects, ref, top_n=10)
            sim_df = pd.DataFrame(similar)[["prospect_id", "name", "persona", "compartment", "conversion_probability"]]
            st.dataframe(sim_df, use_container_width=True)

with tab4:
    st.header("Patterns")
    if not df.empty:
        by_persona = df.groupby("persona").agg(
            count=("prospect_id", "count"),
            avg_conversion=("conversion_probability", "mean"),
        ).reset_index()
        st.subheader("By persona")
        st.dataframe(by_persona, use_container_width=True)
        by_comp = df.groupby("compartment").agg(
            count=("prospect_id", "count"),
            avg_conversion=("conversion_probability", "mean"),
        ).reset_index()
        st.subheader("By compartment")
        st.dataframe(by_comp, use_container_width=True)
    else:
        st.info("Load prospects to see patterns.")
