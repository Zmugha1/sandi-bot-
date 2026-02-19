# Sandi Bot – Complete Project Specification

**Version:** Current (as of project state)  
**Repository:** https://github.com/Zmugha1/sandi-bot-  
**Deployment:** Streamlit Cloud (optional)

---

## 1. Project Overview

### 1.1 Purpose

Sandi Bot is a **sales coaching assistant** that helps salespeople decide how to act with each prospect: **PUSH** (call today, ask for the decision), **NURTURE** (continue engagement, assign homework), or **PAUSE** (step back ~2 weeks). It uses a 5-stage compartment model, 4 readiness dimensions, 4 personas, and optional ML (clustering, conversion probability) to support recommendations and word-for-word scripts. A **ROI tracking and celebration layer** measures time and money saved and ties metrics to in-app actions (opening a client card, Mark as Contacted, Plan Call), with delight messages and a dedicated ROI tab.

### 1.2 Goals

- Reduce time on Monday review and pre-call prep.
- Stop chasing dead-end prospects and surface “quiet deciders” and stuck “overthinkers.”
- Give specific, actionable advice (including scripts) without requiring an API key for chat.
- **Measure and show ROI:** time saved vs manual baselines, revenue projection, clients contacted; celebrate milestones and nudge toward lead-gen research when efficiency is high.

### 1.3 Target User

- **Primary:** Sales reps/coaches (e.g. “Sandi”) who manage a pipeline and want quick, consistent coaching.
- **Design:** Senior-friendly (large fonts, high contrast, plain language, clear buttons).

### 1.4 Duplicating for Another Client

To reuse this app for a different client (e.g. another coach or vertical):

- **Branding:** Change page title and avatar text in `app.py` and `components.py` (e.g. "Sandi Bot" → client name). Icon (🧢) can stay or be swapped in `st.set_page_config` and `render_sandi_avatar`.
- **Data:** Replace or extend `synthetic_data.py` with the new client's persona/stage taxonomy if different; keep the same DB schema or add columns as needed.
- **ROI baselines:** Edit `roi_calculator.py`: `BASELINE_SECONDS` (manual process estimates), `AVG_DEAL_VALUE`, `CONVERSION_LIFT_FROM_APP`, and `value_per_hour_saved` in `revenue_projection()` to match the client's business.
- **Delight copy:** In `app.py` and `components.py`, adjust the exact delight messages (e.g. "Go get some wine" → client-appropriate reward) and thresholds (1 hr, 5 hr, 10 hr) in `celebrate_time_saved` and `_record_time_and_outcome`.
- **Efficiency nudge:** In `components.py`, `gentle_nudge_context()` message and the 80% threshold can be tuned; in `app.py`, the "this week" target (10 hr) for efficiency is used to compute `efficiency_pct`.
- **Repo:** Clone or fork; rename app in Streamlit Cloud and update `README.md` / `PROJECT_SPEC.md` with the new repo and client name.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Streamlit UI (app.py)                                           │
│  • Sidebar: Sandi avatar, Customer #/Name, Start, Chat           │
│  • Main: 6 tabs (How to use, Today's Dashboard, Coaching Session, │
│           People Like Them, Insights, ROI)                      │
└─────────────────────────────────────────────────────────────────┘
         │
         ├── components.py (avatar, forms, score bars, cards, ROI/celebration UI)
         ├── natural_sandi_bot.py (SimpleSandiBot – chat, no API key)
         ├── sandi_bot.py (tactics DB, intent/recommendation logic)
         ├── ml_models.py (K-Means, conversion prob, similar prospects)
         ├── roi_calculator.py (baselines, time saved, weekly agg, revenue projection)
         ├── database.py (SQLite CRUD + time_tracking, outcomes, weekly_roi)
         ├── synthetic_data.py (100 prospects, 4 personas)
         └── config.py (optional API key helpers; not used for chat currently)
```

- **Data:** SQLite (`sandi_bot.db`) next to app code. No external APIs required for core or chat.
- **Chat:** 100% **SimpleSandiBot** (rule-based). No OpenAI key needed for chat.

---

## 3. Data Model

### 3.1 Database (SQLite)

**File:** `sandi_bot.db` (created at runtime; path: same directory as `database.py`)

| Table           | Purpose |
|----------------|--------|
| **prospects**  | One row per prospect: IDs, name, email, persona, compartment, days in compartment, 4 scores, conversion probability, red flags (JSON), context (JSON), timestamps. |
| **interactions** | Log of prospect interactions (type, notes, outcome). |
| **chat_history** | Chat messages (prospect_id, role, message, optional context_snapshot JSON). |
| **feedback**    | Thumbs up/down on recommendations (prospect_id, recommendation_type, user_rating, optional message_id). |
| **time_tracking** | ROI: per-session records (prospect_id, activity_type, started_at, ended_at, duration_seconds, baseline_seconds, time_saved_seconds). Activity types: mark_contacted, plan_call. |
| **outcomes**   | ROI: outcome events (prospect_id, outcome_type, value, notes). Types: contacted, advancement. |
| **weekly_roi**  | ROI: one row per week (week_start_date, time_saved_hours, revenue_projection, clients_contacted, clients_advanced). Upserted when recording time/outcomes. |

### 3.2 Prospect Schema (logical)

| Field                    | Type    | Description |
|--------------------------|---------|-------------|
| prospect_id              | string  | Unique (e.g. P001). |
| name                     | string  | Full name. |
| email                    | string  | Optional. |
| persona                  | string  | Quiet Decider, Overthinker, Burning Bridge, Strategic. |
| compartment              | string  | Discovery, Exploration, Serious Consideration, Decision Prep, Commitment. |
| compartment_days         | int     | Days in current compartment. |
| identity_score           | int     | 1–5. |
| commitment_score         | int     | 1–5. |
| financial_score          | int     | 1–5. |
| execution_score          | int     | 1–5. |
| conversion_probability   | float   | 0–1. |
| last_interaction_date    | string  | ISO date. |
| red_flags                | list/JSON | e.g. avoiding_money_talk, no_follow_through. |
| context_json             | object  | Optional extra context. |

### 3.3 Synthetic Data

- **Count:** 100 prospects (25 per persona).
- **Source:** `synthetic_data.py` (no external files).
- **Behavior:** Overthinkers can be stuck in Exploration 30+ days; score correlations and red flags align with persona. On first run, if DB has fewer than 100 prospects, data is generated and inserted.

---

## 4. Core Concepts

### 4.1 Five Compartments (stages)

1. **Discovery**  
2. **Exploration**  
3. **Serious Consideration**  
4. **Decision Prep**  
5. **Commitment**

Advancement is suggested when prospect scores meet compartment rules (e.g. min count of dimensions ≥3 or ≥4).

### 4.2 Four Readiness Dimensions (scores 1–5)

- **Identity** – ownership vs blame.
- **Commitment** – ability to decide.
- **Financial** – comfort with money/investment.
- **Execution** – follow-through.

Display: traffic-light colors (e.g. green ≥4, yellow 3, red ≤2).

### 4.3 Three Actions

- **PUSH** (green) – Call today; use specific scripts.
- **NURTURE** (yellow) – Continue engagement; assign homework.
- **PAUSE** (red) – Step back ~2 weeks.

### 4.4 Four Personas

- **Quiet Decider** – Decides quietly; often high execution.
- **Overthinker** – Gets stuck; needs homework and clarity.
- **Burning Bridge** – Urgent; high commitment.
- **Strategic** – Balanced; process-oriented.

Persona drives which tactics/scripts are shown (see `sandi_bot.TACTICS_DB`).

---

## 5. Module Specification

### 5.1 database.py

- **Role:** Single SQLite DB; all CRUD and JSON (de)serialization for app; ROI tables and helpers.
- **Exports:**  
  - `init_db()`  
  - Prospects: `insert_prospect`, `get_prospect`, `get_all_prospects`, `update_prospect`, `delete_prospect`  
  - Interactions: `insert_interaction`, `get_interactions`  
  - Chat: `insert_chat_message`, `get_chat_history`  
  - Feedback: `insert_feedback`, `get_feedback_stats`  
  - **Time tracking:** `insert_time_tracking`, `get_time_saved_total`, `get_time_tracking_by_week(weeks)`, `get_usage_dates()`  
  - **Outcomes:** `insert_outcome`, `get_outcomes_count(outcome_type)`, `has_any_advancement()`  
  - **Weekly ROI:** `upsert_weekly_roi(week_start_date, ...)`, `get_weekly_roi(weeks)`  
- **Storage:** `red_flags` and `context_json` stored as JSON text where needed.

### 5.2 synthetic_data.py

- **Role:** Generate 100 realistic prospects and load into DB.
- **Key functions:**  
  - `generate_one_prospect(prospect_id, persona, compartment)`  
  - `generate_all_prospects(count=100)`  
  - `load_synthetic_into_db(records)`  
  - `ensure_synthetic_data()` – ensures ≥100 prospects in DB; used at app startup.

### 5.3 ml_models.py

- **Role:** K-Means clustering and conversion/scoring helpers.
- **Class:** `SandiML(n_clusters=4)`  
  - `fit(prospects)`  
  - `predict_persona(prospect)`, `predict_personas_batch(prospects)`  
  - `conversion_probability(prospect)`  
  - `get_similar_prospects(prospects, reference, top_n=10)`  
- **Helper:** `build_and_fit_ml(prospects)` returns a fitted `SandiML` instance.
- **Features:** identity/commitment/financial/execution scores, compartment ordinal, compartment_days.

### 5.4 sandi_bot.py

- **Role:** Tactics database and recommendation logic for **Person Detail** (not sidebar chat).
- **TACTICS_DB:** Nested dict `persona -> action (PUSH/NURTURE/PAUSE) -> list of script/tactic strings`.
- **Functions:**  
  - `get_recommendation(prospect)` → (action, confidence, reason)  
  - `get_tactics(persona, action)` → list of script strings  
  - `recommend_advancement(prospect)` → (can_advance, reason)  
  - Intent/template helpers used by Person Detail tab (not by sidebar chat in current build).

### 5.5 natural_sandi_bot.py

- **Role:** **Sidebar chat** – all responses come from here; no API key required.
- **Class:** `SimpleSandiBot`  
  - `generate_response(question, prospect, history)`  
  - Uses prospect `name` and `compartment_days` (or `days_in_compartment`).  
  - Rules:  
    - **Call planning:** When user says e.g. “help me plan my next call with the customer”, “plan my next call”, or “next call” → returns a **detailed call plan template** (see below).  
    - “push” in question → if days > 21 → PAUSE; else → push / schedule decision call.  
    - “homework” → one specific thing with deadline.  
    - “pause” → step back 2 weeks.  
    - Else → nurture and ask what they’re unsure about.
- **Call planning template** (no API key):  
  - **Trigger:** Phrases containing “plan” + “call”, or “next call”, or “help me plan”.  
  - **Requires:** A prospect loaded (Customer # and Name started).  
  - **Output:** A structured, demo-ready message that includes:  
    - **Cluster (persona):** Name and a one-line **cluster strategy** per persona (e.g. Quiet Decider: “One clear ask and a deadline”; Overthinker: “One homework item and short follow-up”).  
    - **Compartment band:** All 5 stages with current stage highlighted; current compartment name, stage index (1–5), and days in stage.  
    - **Readiness scores:** Table of Identity, Commitment, Financial, Execution (1–5) with short notes.  
    - **Conversion probability** and **red flags**.  
    - **Recommended action:** PUSH / NURTURE / PAUSE with confidence % and reason (from `sandi_bot.get_recommendation`).  
    - **What to do next / scripts:** Up to 3 tactics from `sandi_bot.get_tactics(persona, action)`.  
    - **Compartment advancement:** Whether scores support moving to the next stage (from `sandi_bot.recommend_advancement`).  
  - Implemented in `_build_call_plan_template(prospect)`; uses `sandi_bot` for recommendation, tactics, and advancement.
- **API:** `simple_chat_response(question, prospect, history)` – used by `app.py` for every chat turn.
- **Optional:** OpenAI-related code remains in file but is **not** used when SimpleSandiBot is active.

### 5.6 components.py

- **Role:** Reusable UI building blocks and ROI/celebration UI.
- **Exports:**  
  - `render_sandi_avatar(show_name, status)` – coach cap icon, “Sandi Bot” header.  
  - `render_customer_entry_form(on_start_callback)` – Customer #, Name, Start ▶; returns (prospect_id, name).  
  - `render_score_bars(prospect, key_prefix)` – 4 bars with traffic-light colors.  
  - `render_radar_chart(prospect, key)` – Plotly radar for 4 dimensions.  
  - `render_recommendation_card(action, reason, script, confidence, on_thumbs_up, on_thumbs_down, key_prefix)` – PUSH/NURTURE/PAUSE card with 👍/👎.  
  - **ROI/celebration:** `celebrate_time_saved(hours)`, `roi_dashboard_card(...)`, `gentle_nudge_context(efficiency_pct)`, `render_research_button(hours_saved, key)`.
  - `score_color(score)`, `HEADER_CSS`, `COLORS` for senior-friendly styling.

### 5.7 roi_calculator.py

- **Role:** ROI and time-saved calculations; baseline estimates, weekly aggregation, revenue projection.
- **Exports:**  
  - `BASELINE_SECONDS` – dict of baseline keys (e.g. `monday_review`, `pre_call_prep`, `per_client_session`, `plan_call`, `mark_contacted`) to seconds (manual process estimates).  
  - `time_saved_for_session(baseline_key, actual_seconds)` – returns max(0, baseline − actual).  
  - `get_week_start(dt)` – Monday-based week start as YYYY-MM-DD.  
  - `aggregate_week_time_saved(records)` – sum time_saved_seconds from records, return hours.  
  - `revenue_projection(time_saved_hours, clients_contacted, clients_advanced)` – value from time saved and outcomes (configurable AVG_DEAL_VALUE, CONVERSION_LIFT_FROM_APP, value_per_hour_saved).  
  - `get_consecutive_usage_days(session_dates)` – count consecutive days including today from list of YYYY-MM-DD dates.

### 5.8 config.py

- **Role:** Optional API key handling (validation, session get/set). **Not used** for chat in current flow; chat is 100% SimpleSandiBot.
- **Exports:** `validate_openai_key`, `get_api_key_from_session`, `set_api_key_in_session`.

### 5.9 app.py

- **Role:** Single Streamlit entrypoint.
- **Page config:** Title “Sandi Bot – Coaching Command Center”, icon 🧢, wide layout, expanded sidebar.
- **Session state:** prospects, ml_model, chat_messages, sandi_prospect_id, sandi_prospect_name, current_prospect, selected_prospect, goto_tab_index; **ROI:** roi_timer_start, roi_timer_prospect_id, roi_celebration_shown_10hr.
- **Startup:** `load_data()` → ensure synthetic data, load prospects, fit ML model.
- **Sidebar:**  
  - Sandi avatar.  
  - Customer # and Name inputs + Start ▶ (loads prospect into `current_prospect`). After Start, **Current session** shows the loaded Customer # and **name from the database** (canonical name). Form input values are not overwritten by the callback (Streamlit widget-key constraint).  
  - **Current session:** When a session is loaded, a line displays **Customer #** and **Name** (e.g. `Current session: P001 · William Williams`). Name comes from the DB when the prospect is found, so the displayed name is always correct.  
  - Chat history (user/assistant bubbles).  
  - Chat input → `natural_sandi_bot.simple_chat_response(question, prospect, history)`; append to history and DB.
- **ROI timer:** On **Coaching Session**, when a client is selected, a session timer starts (or restarts if selection changes). Stored in `roi_timer_start` (ISO) and `roi_timer_prospect_id`. Stopped when user clicks **Mark as Contacted** or **I planned my call**; `_record_time_and_outcome(...)` records time_tracking, outcomes (for mark_contacted), weekly_roi upsert, and delight messages.
- **Main area (6 tabs):**  
  - **Tab 0 – How to use:** In-app instructions: starting a strategy session, chat with Sandi, Today’s Dashboard, Coaching Session, People Like Them, Insights. Dedicated subsection on **👍 Helpful** and **👎 Not helpful** (what they do, when to use each; feedback is saved and does not change bars or confidence). Icon guide (🧢 👤 🎯 💡 🌱 📞 ⚠️ 👁️ 👍 👎).  
  - **Tab 1 – Today's Dashboard:** Metric cards (🎯 Ready for Decision, 💡 Need Nurturing, ⚠️ Stuck >21 days), Pipeline (by stage) or Priority stack, client cards with “View full profile” (switches to Coaching Session tab).  
  - **Tab 2 – Coaching Session:** Select client (by first name). Header shows **Customer #** and **Name** (from DB). Timeline, playbook, readiness bars, recommendation card with 👍/👎. **Quick actions:** **✓ Mark as Contacted**, **📞 I planned my call**. Caption clarifies that feedback is saved and does not change the scores on screen.  
  - **Tab 3 – People Like Them:** Hero card + similar clients grid; insight box.
  - **Tab 4 – Insights:** Charts (where people get stuck, persona distribution, success indicators, momentum); Sandi’s insights text.
  - **Tab 5 – ROI:** Three metric cards (time saved hrs, revenue projection $, clients contacted); Weekly trends line chart; efficiency nudge (>=80% of 10 hr target); Research button when total time saved >= 10 hrs.

---

## 6. User Flows (End-to-End)

### 6.1 First run

1. User runs `streamlit run app.py`.
2. App calls `ensure_synthetic_data()` → creates DB if needed, generates 100 prospects, loads them.
3. Prospects and fitted ML model are stored in session state; UI shows Command Center table and tabs.

### 6.2 Strategy session and chat

1. User enters **Customer #** (e.g. P001) and **Name** in sidebar, clicks **Start ▶**.
2. App loads prospect from DB into `current_prospect`. The **name is taken from the database** when the prospect exists, so the displayed name updates to the canonical record (e.g. “William Williams”). Form fields are synced to show the loaded Customer # and name. Sidebar shows **Current session: [Customer #] · [Name]**.
3. User types in chat (e.g. “Should I push or pause?” or “Help me plan my next call with the customer”).
4. App calls `simple_chat_response(question, current_prospect, chat_messages)` and appends response to history and to `chat_history` table.
5. No API key is required; all chat is SimpleSandiBot.

### 6.2.2 Customer number and name display

- **Sidebar:** After a session is started, **Current session** shows Customer # and Name. Name is from the database when the prospect is found, so it stays correct even if the user typed a different spelling.
- **Coaching Session tab:** The selected client’s **Customer #** and **Name** are shown under the client header (from the DB), so it is always clear who is being viewed and the name matches the record.

### 6.2.1 Call planning (demo highlight)

1. With a prospect loaded, user asks: **“Help me plan my next call with the customer”** (or “plan my next call” / “next call”).
2. Sandi returns a **detailed call plan** in chat: cluster (persona) and strategy, full compartment band with current stage, readiness scores table, conversion % and red flags, recommended action with confidence and reason, next steps/scripts (from tactics DB), and compartment advancement guidance.
3. All content is driven from algorithm outputs (cluster, compartment, scores, recommendation, tactics, advancement) so the demo shows full pipeline logic in one place.

### 6.3 Coaching Session and feedback (👍 Helpful / 👎 Not helpful)

1. User opens **Coaching Session** tab, selects a client (or arrives via “View full profile” from dashboard).
2. App shows Customer # and Name, timeline, playbook (PUSH/NURTURE/PAUSE with confidence), script expanders, readiness bars.
3. **👍 Helpful** – User clicks when the recommendation was useful. Saves feedback (prospect_id, action, rating=1). Does **not** change readiness bars or confidence on screen.
4. **👎 Not helpful** – User clicks when the recommendation didn’t fit. Saves feedback (prospect_id, action, rating=0). Does **not** change readiness bars or confidence. Feedback is stored for future use to improve recommendations.
5. In-app **How to use** tab documents both buttons and when to use each.

### 6.4 ROI tracking and delight messages

1. **Timer:** On **Coaching Session**, when the user selects a client, a session timer starts (or restarts if they switch client). Timer is stored in session state until the user takes an action that "completes" the session.
2. **Mark as Contacted:** User clicks **✓ Mark as Contacted**. App calls `_record_time_and_outcome(prospect_id, "mark_contacted", "mark_contacted")`: stops timer, computes duration and time saved vs baseline, inserts into `time_tracking`, inserts outcome "contacted", upserts `weekly_roi`, then runs celebration logic.
3. **I planned my call:** User clicks **📞 I planned my call**. Same flow with activity_type `plan_call` and baseline `plan_call`; no outcome row.
4. **Delight messages (triggers):**  
   - **1 hr saved:** Success toast.  
   - **5 hr saved:** Snow effect + "You're on fire!" message.  
   - **10 hr saved:** "Go get some wine, you've earned it 🍷" (once per session via `roi_celebration_shown_10hr`).  
   - **First client contacted:** Balloons + "First win! You marked your first client as contacted."  
   - **5 consecutive days of usage:** Toast "You're building a powerful habit 💪".
5. **ROI tab:** User opens **ROI** tab to see time saved, revenue projection, clients contacted; weekly trends line chart; when efficiency (this week's time saved vs 10 hr target) ≥ 80%, gentle nudge: "Ready for some research on how to grow your clientele?"; when total time saved ≥ 10 hrs, button **Research: How to fill these 10 hours with new clients**.

---

## 7. Technology Stack

| Layer     | Technology |
|----------|------------|
| UI       | Streamlit |
| Language | Python 3 |
| Database | SQLite |
| ML       | scikit-learn (K-Means, StandardScaler), pandas, numpy |
| Charts   | Plotly |
| Repo     | Git; GitHub (Zmugha1/sandi-bot-) |
| Deploy   | Streamlit Cloud (optional); `requirements.txt` at repo root |

### 7.1 Dependencies (requirements.txt)

```
streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
plotly>=5.18.0
openai>=1.0.0
```

(`openai` is present for optional/future use; chat does not use it in current spec.)

---

## 8. File Inventory

| File / Dir        | Purpose |
|-------------------|--------|
| app.py            | Streamlit app: sidebar + 6 tabs (How to use, Today's Dashboard, Coaching Session, People Like Them, Insights, ROI); chat uses SimpleSandiBot; ROI timer and _record_time_and_outcome. |
| database.py       | SQLite and CRUD for prospects, interactions, chat_history, feedback, time_tracking, outcomes, weekly_roi. |
| roi_calculator.py  | Baselines (BASELINE_SECONDS), time_saved_for_session, get_week_start, aggregate_week_time_saved, revenue_projection, get_consecutive_usage_days. |
| synthetic_data.py | Generate and load 100 prospects (4 personas, compartments). |
| ml_models.py      | K-Means, conversion probability, similar prospects. |
| sandi_bot.py      | Tactics DB, get_recommendation, get_tactics, recommend_advancement (Person Detail). |
| natural_sandi_bot.py | SimpleSandiBot + simple_chat_response (sidebar chat); call planning template for “plan my next call”. |
| components.py     | Avatar, customer form, score bars, radar, recommendation cards, ROI/celebration (celebrate_time_saved, roi_dashboard_card, gentle_nudge_context, render_research_button). |
| config.py         | Optional API key helpers (unused for chat). |
| requirements.txt  | Python dependencies. |
| README.md         | Setup, usage, deploy notes. |
| PROJECT_SPEC.md   | This specification. |
| .streamlit/config.toml | Streamlit theme (senior-friendly). |
| .gitignore        | DB files, __pycache__, venv, etc. |

---

## 9. Design Guidelines (Senior-Friendly)

- **Typography:** Large headers (e.g. 42px), body 18px.
- **Contrast:** Navy on white; green/yellow/red for PUSH/NURTURE/PAUSE.
- **Language:** Plain English; avoid jargon.
- **Actions:** Prominent buttons (e.g. Start ▶); clear next steps.
- **Icon:** Coach cap (🧢) for Sandi Bot.

---

## 10. Deployment (Streamlit Cloud)

1. Repo on GitHub: `Zmugha1/sandi-bot-`, branch `main`.
2. At [share.streamlit.io](https://share.streamlit.io): New app → Repository `Zmugha1/sandi-bot-`, Branch `main`, Main file path `app.py`.
3. Streamlit uses repo root `requirements.txt`. No secrets required for chat (no OpenAI key).
4. Note: `sandi_bot.db` is created in the container; data is ephemeral unless a persistent volume is added.

---

## 11. Out of Scope (Current Spec)

- Persistent storage of API keys or chat history across deployments.
- Authentication / multi-user isolation.
- Real CRM or email integration.
- Using OpenAI for chat (current design: SimpleSandiBot only).

---

## 12. Quick Reference – How to Run

```bash
# From repo root (sandi-bot)
pip install -r requirements.txt
streamlit run app.py
```

Then: open the **How to use** tab for full instructions (sidebar, chat, each tab, 👍 Helpful / 👎 Not helpful). Or: open sidebar → enter Customer # (e.g. P001) and Name → Start ▶ → ask in chat (e.g. “Should I push or pause?”). No OpenAI key required.

---

*End of project specification.*
