# Sandi Bot – Coaching Command Center

Sales coaching assistant that recommends **PUSH**, **NURTURE**, or **PAUSE** per prospect, with word-for-word scripts and persona-based tactics.

## Features

- **Sandi Bot chat** in the sidebar: enter Customer # and Name, ask "Should I push or pause?", get recommendations with scripts and confidence.
- **5-compartment model**: Discovery → Exploration → Serious Consideration → Decision Prep → Commitment.
- **4 readiness dimensions**: Identity, Commitment, Financial, Execution (1–5 scores).
- **4 personas**: Quiet Decider, Overthinker, Burning Bridge, Strategic.
- **ML**: K-Means persona clustering, conversion probability, similar-prospect lookup.
- **Feedback**: 👍 / 👎 on recommendations to train the system (stored in DB).

## Setup

1. **Clone or open** this repo (e.g. `sandi-bot`).

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   # or: source venv/bin/activate  # Mac/Linux
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**:
   ```bash
   streamlit run app.py
   ```

5. The app opens with **100 synthetic prospects** loaded. No extra setup needed.

## Usage

1. In the **sidebar**, enter a **Customer #** (e.g. `P001`) and **Name**, then click **Start ▶**.
2. Sandi loads that prospect. In the chat you can ask:
   - *Should I push or pause?*
   - *What homework should I give them?*
   - *What should I say on the call?*
   - *Financial angle?*
3. Use the **tabs**:
   - **Command Center**: list of all prospects.
   - **Person Detail**: one prospect’s scores, radar, recommendation card, advancement tip.
   - **Similar Groups**: prospects most similar to a chosen one.
   - **Patterns**: aggregates by persona and compartment.

## Deploy on Streamlit Cloud

1. Push this repo to GitHub (e.g. `https://github.com/Zmugha1/sandi-bot-`).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, and **New app**.
3. Set **Repository** to `Zmugha1/sandi-bot-`, **Branch** to `main`, **Main file path** to `app.py`.
4. Add the same dependencies (Streamlit will use `requirements.txt` in the repo root).
5. Deploy. The app will create `sandi_bot.db` in the container (data is ephemeral unless you add a persistent volume).

## File overview

| File | Purpose |
|------|--------|
| `app.py` | Streamlit UI: tabs + sidebar Sandi chat |
| `database.py` | SQLite: prospects, interactions, chat_history, feedback |
| `synthetic_data.py` | Generates 100 prospects (4 personas, compartments, scores) |
| `ml_models.py` | K-Means clustering, conversion probability, similar prospects |
| `sandi_bot.py` | Chat engine: intents, response text, scripts, tactics DB |
| `components.py` | UI: Sandi avatar, customer form, score bars, radar, recommendation cards |
| `requirements.txt` | Dependencies |
| `README.md` | This file |

## Design (senior-friendly)

- Large fonts (e.g. 42px headers, 18px body).
- High contrast (e.g. navy on white, green/yellow/red for actions).
- Plain language; big buttons and clear next steps.
