
import os
import sqlite3
import random
import time
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
STARTING_CREDITS = 10_000.0
TRADING_SECONDS = 5 * 60
TICK_SECONDS = 5
DB_PATH = os.getenv("TRADING_DB_PATH", "trading_simulation.db")

# Fixed market specification: the same instruments/volatility are used
# regardless of experimental condition. Each participant gets a private
# deterministic price path generated from their market_seed.
ASSETS = {
    "AUS Tech": {"start": 100.0, "daily_vol": 0.025, "risk": "High"},
    "Green Energy": {"start": 80.0, "daily_vol": 0.022, "risk": "High"},
    "Global Bank": {"start": 65.0, "daily_vol": 0.014, "risk": "Medium"},
    "Healthcare": {"start": 55.0, "daily_vol": 0.012, "risk": "Medium"},
    "Consumer": {"start": 45.0, "daily_vol": 0.010, "risk": "Low"},
    "Infrastructure": {"start": 70.0, "daily_vol": 0.009, "risk": "Low"},
}

RISK_SCORE = {"Low": 1, "Medium": 2, "High": 3}

st.set_page_config(
    page_title="Trading Simulation",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------
# Database
# ------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            participant_id TEXT PRIMARY KEY,
            name TEXT,
            age INTEGER,
            investment_experience TEXT,
            financial_knowledge INTEGER,
            condition TEXT,
            market_seed INTEGER,
            started_at TEXT,
            ended_at TEXT,
            final_cash REAL,
            final_portfolio_value REAL,
            final_total_value REAL,
            starting_credits REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            participant_id TEXT,
            timestamp TEXT,
            elapsed_seconds REAL,
            action TEXT,
            asset TEXT,
            quantity INTEGER,
            price REAL,
            trade_value REAL,
            cash_after REAL,
            portfolio_value_after REAL,
            total_value_after REAL,
            risk_score REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id TEXT PRIMARY KEY,
            participant_id TEXT,
            timestamp TEXT,
            elapsed_seconds REAL,
            cash REAL,
            portfolio_value REAL,
            total_value REAL,
            invested_pct REAL,
            high_risk_pct REAL,
            turnover REAL
        )
    """)
    conn.commit()
    conn.close()

def insert_participant():
    s = st.session_state
    conn = get_conn()
    conn.execute("""
        INSERT INTO participants
        (participant_id, name, age, investment_experience, financial_knowledge,
         condition, market_seed, started_at, starting_credits)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        s.participant_id, s.name, s.age, s.experience, s.financial_knowledge,
        s.condition, s.market_seed, s.started_at, STARTING_CREDITS
    ))
    conn.commit()
    conn.close()

def log_trade(trade):
    conn = get_conn()
    conn.execute("""
        INSERT INTO trades
        (trade_id, participant_id, timestamp, elapsed_seconds, action, asset,
         quantity, price, trade_value, cash_after, portfolio_value_after,
         total_value_after, risk_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tuple(trade.values()))
    conn.commit()
    conn.close()

def log_snapshot(s):
    conn = get_conn()
    conn.execute("""
        INSERT INTO snapshots
        (snapshot_id, participant_id, timestamp, elapsed_seconds, cash,
         portfolio_value, total_value, invested_pct, high_risk_pct, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tuple(s.values()))
    conn.commit()
    conn.close()

def finish_participant():
    s = st.session_state
    conn = get_conn()
    conn.execute("""
        UPDATE participants
        SET ended_at=?, final_cash=?, final_portfolio_value=?, final_total_value=?
        WHERE participant_id=?
    """, (
        datetime.now(timezone.utc).isoformat(),
        s.cash,
        portfolio_value(s),
        total_value(s),
        s.participant_id
    ))
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# Market generation
# ------------------------------------------------------------
def make_market(seed, total_seconds=TRADING_SECONDS, step=TICK_SECONDS):
    rng = np.random.default_rng(seed)
    n = total_seconds // step + 1
    market = {}
    for asset, spec in ASSETS.items():
        prices = [spec["start"]]
        # Approximate continuous random walk. The condition never affects prices.
        step_vol = spec["daily_vol"] / np.sqrt(78)  # roughly 5-min intervals in a 6.5h session
        for _ in range(n - 1):
            ret = rng.normal(0, step_vol)
            prices.append(max(1.0, prices[-1] * (1 + ret)))
        market[asset] = np.array(prices)
    return market

def current_prices():
    elapsed = min(
        TRADING_SECONDS,
        max(0, time.monotonic() - st.session_state.start_monotonic)
    )
    idx = min(len(next(iter(st.session_state.market.values()))) - 1,
              int(elapsed // TICK_SECONDS))
    return {asset: float(prices[idx]) for asset, prices in st.session_state.market.items()}

# ------------------------------------------------------------
# Portfolio calculations
# ------------------------------------------------------------
def portfolio_value(s):
    prices = current_prices()
    return sum(qty * prices[a] for a, qty in s.positions.items())

def total_value(s):
    return s.cash + portfolio_value(s)

def turnover(s):
    return s.total_bought_value + s.total_sold_value

def high_risk_value(s):
    prices = current_prices()
    return sum(
        s.positions[a] * prices[a]
        for a in s.positions
        if ASSETS[a]["risk"] == "High"
    )

def invested_pct(s):
    tv = total_value(s)
    return portfolio_value(s) / tv if tv else 0

def high_risk_pct(s):
    pv = portfolio_value(s)
    return high_risk_value(s) / pv if pv else 0

# ------------------------------------------------------------
# Session state
# ------------------------------------------------------------
def initialise():
    if "page" not in st.session_state:
        st.session_state.page = "questionnaire"
        st.session_state.participant_id = str(uuid.uuid4())
        st.session_state.condition = random.choice(["Gamified", "Non-gamified"])
        st.session_state.market_seed = random.randint(1, 2_000_000_000)
        st.session_state.positions = {a: 0 for a in ASSETS}
        st.session_state.cash = STARTING_CREDITS
        st.session_state.total_bought_value = 0.0
        st.session_state.total_sold_value = 0.0
        st.session_state.trade_count = 0
        st.session_state.started_at = None
        st.session_state.start_monotonic = None
        st.session_state.finished = False

initialise()
init_db()

# ------------------------------------------------------------
# Styling
# ------------------------------------------------------------
if st.session_state.condition == "Gamified":
    st.markdown("""
    <style>
    .stApp {background: linear-gradient(135deg,#fff7fb 0%,#f5f0ff 50%,#eefcff 100%);}
    .hero {padding: 18px 24px; border-radius: 18px; background: linear-gradient(90deg,#ff5fa2,#7c5cff);
            color:white; margin-bottom:18px;}
    .badge {display:inline-block; padding:6px 12px; border-radius:999px; background:#ffffff55; font-weight:700;}
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
    .stApp {background:#f6f7f9;}
    .hero {padding: 18px 24px; border-radius: 10px; background:#263238; color:white; margin-bottom:18px;}
    .badge {display:inline-block; padding:6px 12px; border-radius:999px; background:#ffffff22; font-weight:500;}
    </style>
    """, unsafe_allow_html=True)

# ------------------------------------------------------------
# Questionnaire
# ------------------------------------------------------------
if st.session_state.page == "questionnaire":
    st.markdown("""
    <div class="hero">
      <h1>📈 Trading Simulation</h1>
      <p>Thank you for participating. You will complete a short questionnaire,
      then trade in a simulated market for five minutes.</p>
    </div>
    """, unsafe_allow_html=True)

    st.info(
        "Your starting credits are simulated only and have no monetary value. "
        "Your platform assignment is random."
    )

    with st.form("participant_form"):
        name = st.text_input("Participant name")
        age = st.number_input("Age", min_value=18, max_value=99, step=1)
        experience = st.selectbox(
            "Investment experience",
            ["None", "Less than 1 year", "1–3 years", "More than 3 years"]
        )
        knowledge = st.slider(
            "How would you rate your financial knowledge?",
            min_value=1, max_value=5, value=3,
            help="1 = very low, 5 = very high"
        )
        consent = st.checkbox(
            "I understand that this is a simulated trading study and agree to participate."
        )
        submitted = st.form_submit_button("Start simulation", type="primary")

    if submitted:
        if not name.strip():
            st.error("Please enter a participant name.")
        elif not consent:
            st.error("Please confirm the participation statement.")
        else:
            st.session_state.name = name.strip()
            st.session_state.age = int(age)
            st.session_state.experience = experience
            st.session_state.financial_knowledge = int(knowledge)
            st.session_state.started_at = datetime.now(timezone.utc).isoformat()
            st.session_state.start_monotonic = time.monotonic()
            st.session_state.market = make_market(st.session_state.market_seed)
            insert_participant()
            st.session_state.page = "trading"
            st.rerun()

# ------------------------------------------------------------
# Trading screen
# ------------------------------------------------------------
elif st.session_state.page == "trading":
    elapsed = time.monotonic() - st.session_state.start_monotonic
    remaining = max(0, TRADING_SECONDS - elapsed)
    prices = current_prices()

    if remaining <= 0:
        st.session_state.page = "results"
        finish_participant()
        st.rerun()

    # Snapshot approximately every 5 seconds.
    current_bucket = int(elapsed // TICK_SECONDS)
    if current_bucket != st.session_state.get("last_snapshot_bucket", -1):
        st.session_state.last_snapshot_bucket = current_bucket
        tv = total_value(st.session_state)
        log_snapshot({
            "snapshot_id": str(uuid.uuid4()),
            "participant_id": st.session_state.participant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "cash": st.session_state.cash,
            "portfolio_value": portfolio_value(st.session_state),
            "total_value": tv,
            "invested_pct": invested_pct(st.session_state),
            "high_risk_pct": high_risk_pct(st.session_state),
            "turnover": turnover(st.session_state)
        })

    mins, secs = divmod(int(remaining), 60)
    st.markdown(f"""
    <div class="hero">
      <span class="badge">{'🎮 GAMIFIED MODE' if st.session_state.condition == 'Gamified' else 'STANDARD MODE'}</span>
      <h1>Trading Simulation</h1>
      <h2>Time remaining: {mins:02d}:{secs:02d}</h2>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Available credits", f"${st.session_state.cash:,.0f}")
    c2.metric("Portfolio value", f"${portfolio_value(st.session_state):,.0f}")
    c3.metric("Total value", f"${total_value(st.session_state):,.0f}")
    c4.metric("Trades", st.session_state.trade_count)

    st.caption("You may buy and sell whole units. Prices update every five seconds. The market path is independent of your platform condition.")

    # Asset table
    rows = []
    for asset, spec in ASSETS.items():
        rows.append({
            "Asset": asset,
            "Risk": spec["risk"],
            "Price": prices[asset],
            "Units held": st.session_state.positions[asset],
            "Position value": st.session_state.positions[asset] * prices[asset]
        })
    st.dataframe(pd.DataFrame(rows).style.format({"Price": "${:,.2f}", "Position value": "${:,.2f}"}),
                 use_container_width=True, hide_index=True)

    st.divider()

    left, right = st.columns([1, 2])

    with left:
        asset = st.selectbox("Asset", list(ASSETS.keys()))
        action = st.radio("Action", ["Buy", "Sell"], horizontal=True)
        price = prices[asset]
        max_buy = int(st.session_state.cash // price)
        max_sell = st.session_state.positions[asset]
        max_qty = max_buy if action == "Buy" else max_sell
        quantity = st.number_input(
            "Quantity", min_value=1, max_value=max(1, max_qty),
            value=1, step=1
        )

        if action == "Buy":
            st.caption(f"Maximum affordable: {max_buy} units")
        else:
            st.caption(f"Units available to sell: {max_sell}")

        if st.button("Execute trade", type="primary", use_container_width=True):
            qty = int(quantity)
            value = qty * price

            if action == "Buy" and qty <= max_buy:
                st.session_state.cash -= value
                st.session_state.positions[asset] += qty
                st.session_state.total_bought_value += value
            elif action == "Sell" and qty <= max_sell:
                st.session_state.cash += value
                st.session_state.positions[asset] -= qty
                st.session_state.total_sold_value += value
            else:
                st.error("That trade cannot be completed.")
                st.stop()

            st.session_state.trade_count += 1
            now_elapsed = time.monotonic() - st.session_state.start_monotonic
            pv = portfolio_value(st.session_state)
            tv = total_value(st.session_state)

            log_trade({
                "trade_id": str(uuid.uuid4()),
                "participant_id": st.session_state.participant_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(now_elapsed, 2),
                "action": action,
                "asset": asset,
                "quantity": qty,
                "price": price,
                "trade_value": value,
                "cash_after": st.session_state.cash,
                "portfolio_value_after": pv,
                "total_value_after": tv,
                "risk_score": RISK_SCORE[ASSETS[asset]["risk"]]
            })

            if st.session_state.condition == "Gamified":
                st.balloons()
                st.success("✨ Trade executed! Keep going.")
            else:
                st.success("Trade executed.")

            st.rerun()

    with right:
        st.subheader("Your portfolio")
        portfolio_rows = []
        for a in ASSETS:
            qty = st.session_state.positions[a]
            if qty:
                portfolio_rows.append({
                    "Asset": a,
                    "Risk": ASSETS[a]["risk"],
                    "Units": qty,
                    "Current value": qty * prices[a]
                })
        if portfolio_rows:
            st.dataframe(pd.DataFrame(portfolio_rows).style.format({"Current value": "${:,.2f}"}),
                         use_container_width=True, hide_index=True)
        else:
            st.write("No positions yet.")

        st.subheader("Behaviour indicators")
        b1, b2, b3 = st.columns(3)
        b1.metric("Invested", f"{invested_pct(st.session_state)*100:.1f}%")
        b2.metric("High-risk exposure", f"{high_risk_pct(st.session_state)*100:.1f}%")
        b3.metric("Turnover", f"${turnover(st.session_state):,.0f}")

    # Automatic refresh for the live timer/market.
    time.sleep(1)
    st.rerun()

# ------------------------------------------------------------
# Results
# ------------------------------------------------------------
elif st.session_state.page == "results":
    tv = total_value(st.session_state)
    profit = tv - STARTING_CREDITS

    st.markdown("""
    <div class="hero">
      <h1>Simulation complete 🎉</h1>
      <p>Thank you for participating.</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Starting credits", f"${STARTING_CREDITS:,.0f}")
    c2.metric("Final value", f"${tv:,.2f}")
    c3.metric("Profit / loss", f"${profit:,.2f}")
    c4.metric("Trades", st.session_state.trade_count)

    st.write("### Your recorded trading summary")
    summary = pd.DataFrame([{
        "Participant ID": st.session_state.participant_id,
        "Condition": st.session_state.condition,
        "Trades": st.session_state.trade_count,
        "Turnover": turnover(st.session_state),
        "Final total value": tv,
        "Profit/Loss": profit,
        "Final invested %": invested_pct(st.session_state) * 100,
        "Final high-risk exposure %": high_risk_pct(st.session_state) * 100
    }])
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.info(
        "The research team can analyse your trading behaviour alongside the questionnaire responses. "
        "The simulated credits have no monetary value."
    )

    if st.button("Finish"):
        st.session_state.page = "done"
        st.rerun()

elif st.session_state.page == "done":
    st.success("Thank you. Your participation has been recorded.")
    st.write("You may now close this page.")
