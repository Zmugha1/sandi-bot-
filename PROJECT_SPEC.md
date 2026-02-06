# Sandi Bot – Complete Project Specification

**Version:** Current (as of project state)  
**Repository:** https://github.com/Zmugha1/sandi-bot-  
**Deployment:** Streamlit Cloud (optional)

---

## 1. Project Overview

### 1.1 Purpose

Sandi Bot is a **sales coaching assistant** that helps salespeople decide how to act with each prospect: **PUSH** (call today, ask for the decision), **NURTURE** (continue engagement, assign homework), or **PAUSE** (step back ~2 weeks). It uses a 5-stage compartment model, 4 readiness dimensions, 4 personas, and optional ML (clustering, conversion probability) to support recommendations and word-for-word scripts.

### 1.2 Goals

- Reduce time on Monday review and pre-call prep.
- Stop chasing dead-end prospects and surface “quiet deciders” and stuck “overthinkers.”
- Give specific, actionable advice (including scripts) without requiring an API key for chat.

### 1.3 Target User

- **Primary:** Sales reps/coaches (e.g. “Sandi”) who manage a pipeline and want quick, consistent coaching.
- **Design:** Senior-friendly (large fonts, high contrast, plain language, clear buttons).

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Streamlit UI (app.py)                                           │
│  • Sidebar: Sandi avatar, Customer #/Name, Start, Chat           │
│  • Main: 4 tabs (Command Center, Person Detail, Similar, Patterns)│
└─────────────────────────────────────────────────────────────────┘
         │
         ├── components.py (avatar, forms, score bars, radar, cards)
         ├── natural_sandi_bot.py (SimpleSandiBot – chat, no API key)
         ├── sandi_bot.py (tactics DB, intent/recommendation logic for Person Detail)
         ├── ml_models.py (K-Means, conversion prob, similar prospects)
         ├── database.py (SQLite CRUD)
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

- **Role:** Single SQLite DB; all CRUD and JSON (de)serialization for app.
- **Exports:**  
  - `init_db()`  
  - Prospects: `insert_prospect`, `get_prospect`, `get_all_prospects`, `update_prospect`, `delete_prospect`  
  - Interactions: `insert_interaction`, `get_interactions`  
  - Chat: `insert_chat_message`, `get_chat_history`  
  - Feedback: `insert_feedback`, `get_feedback_stats`  
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

- **Role:** Reusable UI building blocks.
- **Exports:**  
  - `render_sandi_avatar(show_name, status)` – coach cap icon, “Sandi Bot” header.  
  - `render_customer_entry_form(on_start_callback)` – Customer #, Name, Start ▶; returns (prospect_id, name).  
  - `render_score_bars(prospect, key_prefix)` – 4 bars with traffic-light colors.  
  - `render_radar_chart(prospect, key)` – Plotly radar for 4 dimensions.  
  - `render_recommendation_card(action, reason, script, confidence, on_thumbs_up, on_thumbs_down, key_prefix)` – PUSH/NURTURE/PAUSE card with 👍/👎.  
  - `score_color(score)`, `HEADER_CSS` for senior-friendly styling.

### 5.7 config.py

- **Role:** Optional API key handling (validation, session get/set). **Not used** for chat in current flow; chat is 100% SimpleSandiBot.
- **Exports:** `validate_openai_key`, `get_api_key_from_session`, `set_api_key_in_session`.

### 5.8 app.py

- **Role:** Single Streamlit entrypoint.
- **Page config:** Title “Sandi Bot – Coaching Command Center”, icon 🧢, wide layout, expanded sidebar.
- **Session state:** prospects, ml_model, chat_messages, sandi_prospect_id, sandi_prospect_name, current_prospect.
- **Startup:** `load_data()` → ensure synthetic data, load prospects, fit ML model.
- **Sidebar:**  
  - Sandi avatar.  
  - Customer # and Name + Start ▶ (loads prospect into `current_prospect`).  
  - Chat history (user/assistant bubbles).  
  - Chat input → `natural_sandi_bot.simple_chat_response(question, prospect, history)`; append to history and DB.
- **Main area:**  
  - **Tab 1 – Command Center:** Table of prospects (id, name, persona, compartment, conversion %).  
  - **Tab 2 – Person Detail:** Select prospect → score bars, radar, persona/compartment/days, conversion %, advancement note, recommendation card (from `sandi_bot.get_recommendation` + `get_tactics`) with 👍/👎 (persisted via `database.insert_feedback`).  
  - **Tab 3 – Similar Groups:** Pick reference prospect → table of most similar (from `ml_model.get_similar_prospects`).  
  - **Tab 4 – Patterns:** Aggregates by persona and by compartment (counts, avg conversion).

---

## 6. User Flows (End-to-End)

### 6.1 First run

1. User runs `streamlit run app.py`.
2. App calls `ensure_synthetic_data()` → creates DB if needed, generates 100 prospects, loads them.
3. Prospects and fitted ML model are stored in session state; UI shows Command Center table and tabs.

### 6.2 Strategy session and chat

1. User enters **Customer #** (e.g. P001) and **Name** in sidebar, clicks **Start ▶**.
2. App loads prospect from DB into `current_prospect` and shows “Ready to help” in avatar.
3. User types in chat (e.g. “Should I push or pause?” or “Help me plan my next call with the customer”).
4. App calls `simple_chat_response(question, current_prospect, chat_messages)` and appends response to history and to `chat_history` table.
5. No API key is required; all chat is SimpleSandiBot.

### 6.2.1 Call planning (demo highlight)

1. With a prospect loaded, user asks: **“Help me plan my next call with the customer”** (or “plan my next call” / “next call”).
2. Sandi returns a **detailed call plan** in chat: cluster (persona) and strategy, full compartment band with current stage, readiness scores table, conversion % and red flags, recommended action with confidence and reason, next steps/scripts (from tactics DB), and compartment advancement guidance.
3. All content is driven from algorithm outputs (cluster, compartment, scores, recommendation, tactics, advancement) so the demo shows full pipeline logic in one place.

### 6.3 Person Detail and feedback

1. User opens **Person Detail**, selects a prospect.
2. App shows scores, radar, recommendation (PUSH/NURTURE/PAUSE) and script from `sandi_bot.get_recommendation` and `get_tactics`.
3. User clicks 👍 or 👎 → `insert_feedback(prospect_id, action, 1 or 0)`.

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
| app.py            | Streamlit app: sidebar + 4 tabs; chat uses SimpleSandiBot. |
| database.py       | SQLite and CRUD for prospects, interactions, chat_history, feedback. |
| synthetic_data.py | Generate and load 100 prospects (4 personas, compartments). |
| ml_models.py      | K-Means, conversion probability, similar prospects. |
| sandi_bot.py      | Tactics DB, get_recommendation, get_tactics, recommend_advancement (Person Detail). |
| natural_sandi_bot.py | SimpleSandiBot + simple_chat_response (sidebar chat); call planning template for “plan my next call”. |
| components.py     | Avatar, customer form, score bars, radar, recommendation cards. |
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

Then: open sidebar → enter Customer # (e.g. P001) and Name → Start ▶ → ask in chat (e.g. “Should I push or pause?”). No OpenAI key required.

---

*End of project specification.*
