import os
import sqlite3
import random
import time
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

STARTING_CREDITS = 10_000.0

# 8 MINUTES
TRADING_SECONDS = 8 * 60

# Market prices update every 5 seconds
TICK_SECONDS = 5

VOLATILITY_MULTIPLIER = 5.0

DB_PATH = os.getenv("TRADING_DB_PATH", "trading_simulation.db")


# ============================================================
# ASSETS
# ============================================================

ASSETS = {
    "AUS Tech": {
        "start": 100.0,
        "daily_vol": 0.025,
        "risk": "High"
    },
    "Green Energy": {
        "start": 80.0,
        "daily_vol": 0.022,
        "risk": "High"
    },
    "Global Bank": {
        "start": 65.0,
        "daily_vol": 0.014,
        "risk": "Medium"
    },
    "Healthcare": {
        "start": 55.0,
        "daily_vol": 0.012,
        "risk": "Medium"
    },
    "Consumer": {
        "start": 45.0,
        "daily_vol": 0.010,
        "risk": "Low"
    },
    "Infrastructure": {
        "start": 70.0,
        "daily_vol": 0.009,
        "risk": "Low"
    },
}

RISK_SCORE = {
    "Low": 1,
    "Medium": 2,
    "High": 3
}


# ============================================================
# PAGE SETTINGS
# ============================================================

st.set_page_config(
    page_title="Trading Simulation",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# DATABASE
# ============================================================

def get_conn():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():

    conn = get_conn()

    # Participant information
    conn.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            participant_id TEXT PRIMARY KEY,
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

    # Individual trades
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

    # Periodic behavioural snapshots
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


def assign_condition():

    conn = get_conn()

    counts = dict(
        conn.execute(
            """
            SELECT condition, COUNT(*)
            FROM participants
            GROUP BY condition
            """
        ).fetchall()
    )

    conn.close()

    gamified_count = counts.get("Gamified", 0)
    standard_count = counts.get("Non-gamified", 0)

    # Keep the groups approximately balanced
    if gamified_count < standard_count:
        return "Gamified"

    if standard_count < gamified_count:
        return "Non-gamified"

    return random.SystemRandom().choice(
        ["Gamified", "Non-gamified"]
    )


def insert_participant():

    s = st.session_state

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO participants
        (
            participant_id,
            condition,
            market_seed,
            started_at,
            starting_credits
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            s.participant_id,
            s.condition,
            s.market_seed,
            s.started_at,
            STARTING_CREDITS
        )
    )

    conn.commit()
    conn.close()


def log_trade(trade):

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO trades
        (
            trade_id,
            participant_id,
            timestamp,
            elapsed_seconds,
            action,
            asset,
            quantity,
            price,
            trade_value,
            cash_after,
            portfolio_value_after,
            total_value_after,
            risk_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(trade.values())
    )

    conn.commit()
    conn.close()


def log_snapshot(snapshot):

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO snapshots
        (
            snapshot_id,
            participant_id,
            timestamp,
            elapsed_seconds,
            cash,
            portfolio_value,
            total_value,
            invested_pct,
            high_risk_pct,
            turnover
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(snapshot.values())
    )

    conn.commit()
    conn.close()


def finish_participant():

    s = st.session_state

    conn = get_conn()

    conn.execute(
        """
        UPDATE participants
        SET
            ended_at=?,
            final_cash=?,
            final_portfolio_value=?,
            final_total_value=?
        WHERE participant_id=?
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            s.cash,
            portfolio_value(s),
            total_value(s),
            s.participant_id
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# MARKET GENERATION
# ============================================================

def make_market(
    seed,
    total_seconds=TRADING_SECONDS,
    step=TICK_SECONDS
):

    rng = np.random.default_rng(seed)

    n = total_seconds // step + 1

    market = {}

    for asset, spec in ASSETS.items():

        prices = [spec["start"]]

        step_vol = (
            spec["daily_vol"] * VOLATILITY_MULTIPLIER
        ) / np.sqrt(78)

        for _ in range(n - 1):

            ret = rng.normal(
                0,
                step_vol
            )

            next_price = prices[-1] * (1 + ret)

            prices.append(
                max(1.0, next_price)
            )

        market[asset] = np.array(prices)

    return market


def current_prices():

    elapsed = min(
        TRADING_SECONDS,
        max(
            0,
            time.monotonic()
            - st.session_state.start_monotonic
        )
    )

    first_market = next(
        iter(st.session_state.market.values())
    )

    idx = min(
        len(first_market) - 1,
        int(elapsed // TICK_SECONDS)
    )

    return {
        asset: float(prices[idx])
        for asset, prices
        in st.session_state.market.items()
    }


# ============================================================
# PORTFOLIO CALCULATIONS
# ============================================================

def portfolio_value(s):

    prices = current_prices()

    return sum(
        qty * prices[asset]
        for asset, qty
        in s.positions.items()
    )


def total_value(s):

    return (
        s.cash
        + portfolio_value(s)
    )


def turnover(s):

    return (
        s.total_bought_value
        + s.total_sold_value
    )


def high_risk_value(s):

    prices = current_prices()

    return sum(
        s.positions[asset] * prices[asset]
        for asset in s.positions
        if ASSETS[asset]["risk"] == "High"
    )


def invested_pct(s):

    tv = total_value(s)

    if tv <= 0:
        return 0

    return portfolio_value(s) / tv


def high_risk_pct(s):

    pv = portfolio_value(s)

    if pv <= 0:
        return 0

    return high_risk_value(s) / pv


# ============================================================
# SESSION STATE
# ============================================================

def initialise():

    if "page" not in st.session_state:

        st.session_state.page = "instructions"

        st.session_state.participant_id = str(
            uuid.uuid4()
        )

        st.session_state.condition = None

        st.session_state.market_seed = random.randint(
            1,
            2_000_000_000
        )

        st.session_state.positions = {
            asset: 0
            for asset in ASSETS
        }

        st.session_state.position_cost_basis = {
            asset: 0.0
            for asset in ASSETS
        }

        st.session_state.cash = STARTING_CREDITS

        st.session_state.total_bought_value = 0.0
        st.session_state.total_sold_value = 0.0

        # No artificial trade limit
        st.session_state.trade_count = 0

        st.session_state.started_at = None
        st.session_state.start_monotonic = None

        st.session_state.performance_history = []

        st.session_state.last_snapshot_bucket = -1

        st.session_state.finished = False

        st.session_state.exit_reason = None


initialise()

init_db()


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
<style>

:root {
    color-scheme: light !important;
}

html,
body,
[data-testid="stAppViewContainer"],
[data-testid="stHeader"] {
    background: #f6f7f9 !important;
    color: #111111 !important;
}

[data-testid="stAppViewContainer"] *,
[data-testid="stSidebar"] * {
    color: #111111;
}

[data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stCaptionContainer"] {
    color: #111111 !important;
}

input,
textarea,
[data-baseweb="select"] > div,
[data-baseweb="base-input"] {
    background: #ffffff !important;
    color: #111111 !important;
}

[data-testid="stDataFrame"] {
    background: #ffffff !important;
}

.hero {
    padding: 18px 24px;
    border-radius: 18px;
    background: linear-gradient(
        90deg,
        #ff9bc5,
        #b7a8ff
    );
    color: #111111;
    margin-bottom: 18px;
}

.hero h1,
.hero h2,
.hero p,
.badge {
    color: #111111 !important;
}

.badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    background: #ffffffaa;
    font-weight: 700;
}

.live-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    margin-right: 6px;
    border-radius: 50%;
    background: #111111;
    animation: live-pulse 1s ease-in-out infinite;
}

.celebration-overlay {
    position: fixed;
    z-index: 9999;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: rgba(61,179,92,.2);
    animation: overlay-in .2s ease-out;
}

.celebration-content {
    position: relative;
    z-index: 2;
    text-align: center;
    animation: content-pop .3s ease-out;
}

.celebration-content h1 {
    margin: 0 0 8px;
    color: #075b2a !important;
    font-size: clamp(2rem,6vw,4.2rem);
    line-height: 1;
}

.celebration-content p {
    margin: 0;
    color: #075b2a !important;
    font-size: clamp(1rem,2.5vw,1.35rem);
    font-weight: 700;
}

.reward-effect {
    height: 104px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 8px;
}

.reward-star {
    position: relative;
    width: 82px;
    height: 82px;
    background: #ffd43b;
    clip-path: polygon(
        50% 0%,
        61% 35%,
        98% 35%,
        68% 56%,
        79% 92%,
        50% 70%,
        21% 92%,
        32% 56%,
        2% 35%,
        39% 35%
    );
    filter: drop-shadow(
        0 5px 10px rgba(145,94,0,.35)
    );
    animation: star-pop .55s ease-in-out infinite alternate;
}

.reward-star::after {
    content: "";
    position: absolute;
    inset: 18px;
    background: #fff3a3;
    clip-path: inherit;
}

.reward-balloons {
    gap: 22px;
    align-items: flex-start;
    padding-top: 8px;
}

.balloon {
    position: relative;
    width: 40px;
    height: 52px;
    border-radius: 50% 50% 46% 46%;
    animation: balloon-bob .7s ease-in-out infinite alternate;
}

.balloon::before {
    content: "";
    position: absolute;
    left: 15px;
    bottom: -43px;
    width: 1px;
    height: 44px;
    background: #075b2a;
}

.balloon::after {
    content: "";
    position: absolute;
    left: 16px;
    bottom: -3px;
    width: 9px;
    height: 9px;
    background: inherit;
    clip-path: polygon(
        0 0,
        100% 0,
        50% 100%
    );
}

.balloon:nth-child(1) {
    background: #ff5f8f;
}

.balloon:nth-child(2) {
    background: #ffd43b;
    animation-delay: .15s;
}

.balloon:nth-child(3) {
    background: #4dabf7;
    animation-delay: .3s;
}

.confetti {
    position: absolute;
    inset: 0;
    pointer-events: none;
}

.confetti span {
    position: absolute;
    top: -12vh;
    width: 12px;
    height: 26px;
    animation: confetti-fall 1.5s linear infinite;
}

.confetti span:nth-child(1) {
    left: 8%;
    background: #ff5fa2;
    transform: rotate(18deg);
}

.confetti span:nth-child(2) {
    left: 21%;
    background: #7c5cff;
    animation-delay: .35s;
    transform: rotate(72deg);
}

.confetti span:nth-child(3) {
    left: 35%;
    background: #00a896;
    animation-delay: .8s;
    transform: rotate(42deg);
}

.confetti span:nth-child(4) {
    left: 53%;
    background: #ffb703;
    animation-delay: .15s;
    transform: rotate(88deg);
}

.confetti span:nth-child(5) {
    left: 68%;
    background: #fb5607;
    animation-delay: .6s;
    transform: rotate(28deg);
}

.confetti span:nth-child(6) {
    left: 84%;
    background: #3a86ff;
    animation-delay: 1s;
    transform: rotate(64deg);
}

@keyframes overlay-in {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}

@keyframes content-pop {
    from {
        transform: scale(.75);
        opacity: 0;
    }
    to {
        transform: scale(1);
        opacity: 1;
    }
}

@keyframes confetti-fall {
    0% {
        top: -12vh;
        opacity: 1;
    }

    100% {
        top: 112vh;
        opacity: .2;
        transform:
            translateX(80px)
            rotate(520deg);
    }
}

@keyframes star-pop {
    from {
        transform:
            scale(.8)
            rotate(-8deg);
    }

    to {
        transform:
            scale(1.08)
            rotate(8deg);
    }
}

@keyframes balloon-bob {
    from {
        transform: translateY(4px);
    }

    to {
        transform: translateY(-8px);
    }
}

@keyframes live-pulse {
    0%, 100% {
        transform: scale(1);
        opacity: 1;
    }

    50% {
        transform: scale(1.55);
        opacity: .45;
    }
}

</style>
""",
    unsafe_allow_html=True
)


# ============================================================
# PAGE 1: INSTRUCTIONS
# ============================================================

if st.session_state.page == "instructions":

    st.markdown(
        """
        <div class="hero">
            <h1>📈 Trading Simulation</h1>
            <p>
                Thank you for participating in this simulated trading study.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.info(
        "The simulation uses artificial credits only. "
        "They have no real monetary value."
    )

    st.subheader("Before you begin")

    st.markdown(
        """
        **Rules of the simulation:**

        1. You will receive **$10,000 in simulated credits**.
        2. You may buy and sell shares using these credits.
        3. You may trade **as many times as you wish** during the simulation.
        4. You can only buy shares when you have sufficient simulated credits.
        5. You can only sell shares that you currently own.
        6. Share prices will change throughout the simulation.
        7. The simulation will run for **8 minutes**.
        8. You may exit the simulation at any time.
        9. All credits and market movements are simulated and have no real monetary value.
        10. The simulation does not represent real financial markets or actual investment outcomes.
        """
    )

    st.warning(
        "Please make your trading decisions independently. "
        "There are no right or wrong decisions."
    )

    st.divider()

    understood = st.checkbox(
        "I understand the instructions and agree to participate."
    )

    if st.button(
        "Start Trading",
        type="primary",
        use_container_width=True,
        disabled=not understood,
        key="start_simulation_button"
    ):

        # Assign condition only when the participant starts
        st.session_state.condition = assign_condition()

        st.session_state.started_at = (
            datetime.now(timezone.utc).isoformat()
        )

        st.session_state.start_monotonic = time.monotonic()

        st.session_state.market = make_market(
            st.session_state.market_seed
        )

        # Reset trading state in case of accidental reruns
        st.session_state.positions = {
            asset: 0
            for asset in ASSETS
        }

        st.session_state.position_cost_basis = {
            asset: 0.0
            for asset in ASSETS
        }

        st.session_state.cash = STARTING_CREDITS
        st.session_state.total_bought_value = 0.0
        st.session_state.total_sold_value = 0.0
        st.session_state.trade_count = 0
        st.session_state.performance_history = []
        st.session_state.last_snapshot_bucket = -1

        insert_participant()

        st.session_state.page = "trading"

        st.rerun()


# ============================================================
# PAGE 2: TRADING
# ============================================================

elif st.session_state.page == "trading":

    elapsed = (
        time.monotonic()
        - st.session_state.start_monotonic
    )

    remaining = max(
        0,
        TRADING_SECONDS - elapsed
    )

    # --------------------------------------------------------
    # AUTOMATIC END AFTER 8 MINUTES
    # --------------------------------------------------------

    if remaining <= 0:

        st.session_state.exit_reason = "Time completed"
        st.session_state.page = "results"

        finish_participant()

        st.rerun()


    prices = current_prices()


    # --------------------------------------------------------
    # GAMIFIED CELEBRATION
    # --------------------------------------------------------

    if (
        st.session_state.get("celebration_until", 0)
        > time.monotonic()
    ):

        reward_variant = st.session_state.get(
            "reward_variant",
            "star"
        )

        reward_content = {
            "balloons":
                """
                <div class="reward-effect reward-balloons">
                    <span class="balloon"></span>
                    <span class="balloon"></span>
                    <span class="balloon"></span>
                </div>
                """,

            "star":
                """
                <div class="reward-effect">
                    <div class="reward-star"></div>
                </div>
                """,

            "confetti":
                """
                <div class="reward-effect">
                    <div class="confetti">
                        <span></span>
                        <span></span>
                        <span></span>
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
                """
        }[reward_variant]

        reward_message = st.session_state.get(
            "reward_message",
            "Trade recorded!"
        )

        st.markdown(
            f"""
            <div class="celebration-overlay">
                <div class="celebration-content">
                    {reward_content}
                    <h1>{reward_message}</h1>
                    <p>Trade recorded.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


    # --------------------------------------------------------
    # PERFORMANCE HISTORY
    # --------------------------------------------------------

    current_total_value = total_value(
        st.session_state
    )

    st.session_state.performance_history.append(
        {
            "Elapsed minutes":
                round(elapsed / 60, 2),

            "Total value":
                current_total_value,

            "Portfolio value":
                portfolio_value(st.session_state),

            "Available credits":
                st.session_state.cash,
        }
    )


    # --------------------------------------------------------
    # PERIODIC SNAPSHOT
    # --------------------------------------------------------

    current_bucket = int(
        elapsed // TICK_SECONDS
    )

    if (
        current_bucket
        != st.session_state.last_snapshot_bucket
    ):

        st.session_state.last_snapshot_bucket = (
            current_bucket
        )

        tv = total_value(
            st.session_state
        )

        log_snapshot(
            {
                "snapshot_id":
                    str(uuid.uuid4()),

                "participant_id":
                    st.session_state.participant_id,

                "timestamp":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

                "elapsed_seconds":
                    round(elapsed, 2),

                "cash":
                    st.session_state.cash,

                "portfolio_value":
                    portfolio_value(
                        st.session_state
                    ),

                "total_value":
                    tv,

                "invested_pct":
                    invested_pct(
                        st.session_state
                    ),

                "high_risk_pct":
                    high_risk_pct(
                        st.session_state
                    ),

                "turnover":
                    turnover(
                        st.session_state
                    )
            }
        )


    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    mins, secs = divmod(
        int(remaining),
        60
    )

    st.markdown(
        f"""
        <div class="hero">
            <span class="badge">
                <span class="live-dot"></span>
                LIVE MARKET
            </span>

            <h1>Trading Simulation</h1>

            <h2>
                Time remaining:
                {mins:02d}:{secs:02d}
            </h2>
        </div>
        """,
        unsafe_allow_html=True
    )


    # --------------------------------------------------------
    # EXIT BUTTON
    # --------------------------------------------------------

    exit_col1, exit_col2 = st.columns(
        [5, 1]
    )

    with exit_col2:

        if st.button(
            "Exit simulation",
            type="secondary",
            use_container_width=True,
            key="exit_simulation_button"
        ):

            st.session_state.exit_reason = (
                "Participant exited early"
            )

            st.session_state.page = "results"

            finish_participant()

            st.rerun()


    # --------------------------------------------------------
    # SUMMARY METRICS
    # --------------------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Available credits",
        f"${st.session_state.cash:,.0f}"
    )

    c2.metric(
        "Portfolio value",
        f"${portfolio_value(st.session_state):,.0f}"
    )

    c3.metric(
        "Total value",
        f"${total_value(st.session_state):,.0f}"
    )

    c4.metric(
        "Trades",
        st.session_state.trade_count
    )

    st.caption(
        "You may buy and sell whole units. "
        "Prices update every five seconds. "
        "There is no limit on the number of trades."
    )


    # ========================================================
    # PERFORMANCE CHART
    # ========================================================

    st.subheader("Investment performance")

    performance = (
        pd.DataFrame(
            st.session_state.performance_history
        )
        .drop_duplicates(
            subset=["Elapsed minutes"],
            keep="last"
        )
        .set_index("Elapsed minutes")
    )

    if not performance.empty:

        st.line_chart(
            performance,
            y=[
                "Total value",
                "Portfolio value",
                "Available credits"
            ],
            use_container_width=True
        )


    # ========================================================
    # SHARE PRICE HISTORY
    # ========================================================

    st.subheader("Share price history")

    history_choice = st.selectbox(
        "Choose a share to inspect",
        ["All shares"] + list(ASSETS.keys()),
        key="history_choice"
    )

    history_minutes = (
        np.arange(
            len(
                next(
                    iter(
                        st.session_state.market.values()
                    )
                )
            )
        )
        * TICK_SECONDS
        / 60
    )

    if history_choice == "All shares":

        history = pd.DataFrame(
            {
                asset:
                    st.session_state.market[asset]
                    / st.session_state.market[asset][0]
                    * 100

                for asset in ASSETS
            },
            index=history_minutes
        )

        history.index.name = "Minutes"

        st.caption(
            "All shares are indexed to 100 at the start "
            "so their performance can be compared fairly."
        )

    else:

        history = pd.DataFrame(
            {
                "Price":
                    st.session_state.market[
                        history_choice
                    ]
            },
            index=history_minutes
        )

        history.index.name = "Minutes"

    st.line_chart(
        history,
        use_container_width=True
    )


    # ========================================================
    # ASSET TABLE
    # ========================================================

    rows = []

    for asset, spec in ASSETS.items():

        current_price = prices[asset]

        starting_price = (
            st.session_state.market[asset][0]
        )

        price_change = (
            current_price
            - starting_price
        )

        rows.append(
            {
                "Asset": asset,
                "Risk": spec["risk"],
                "Current price": current_price,
                "Change": price_change,
                "Change %":
                    price_change
                    / starting_price
                    * 100,
                "Units held":
                    st.session_state.positions[asset],
                "Position value":
                    st.session_state.positions[asset]
                    * current_price
            }
        )

    asset_df = pd.DataFrame(rows)

    st.dataframe(
        asset_df.style.format(
            {
                "Current price":
                    "${:,.2f}",

                "Change":
                    "${:+,.2f}",

                "Change %":
                    "{:+.2f}%",

                "Position value":
                    "${:,.2f}"
            }
        ),
        use_container_width=True,
        hide_index=True
    )


    st.divider()


    # ========================================================
    # SINGLE TRADING INTERFACE
    # ========================================================

    left, right = st.columns(
        [1, 2]
    )


    # --------------------------------------------------------
    # TRADE CONTROLS
    # --------------------------------------------------------

    with left:

        st.subheader("Place a trade")

        asset = st.selectbox(
            "Asset",
            list(ASSETS.keys()),
            key="trade_asset"
        )

        action = st.radio(
            "Action",
            ["Buy", "Sell"],
            horizontal=True,
            key="trade_action"
        )

        price = prices[asset]

        max_buy = int(
            st.session_state.cash
            // price
        )

        max_sell = (
            st.session_state.positions[asset]
        )


        # ----------------------------------------------------
        # QUANTITY
        # ----------------------------------------------------

        if action == "Buy":

            available_quantity = max_buy

            st.caption(
                f"Maximum affordable: "
                f"{available_quantity:,} units"
            )

        else:

            available_quantity = max_sell

            st.caption(
                f"Units available to sell: "
                f"{available_quantity:,}"
            )


        # FIX:
        # Do not force max_qty to 1 when zero is available.
        # This was one source of the confusing trade behaviour.

        if available_quantity > 0:

            quantity = st.number_input(
                "Quantity",
                min_value=1,
                max_value=available_quantity,
                value=1,
                step=1,
                key="trade_quantity"
            )

            trade_disabled = False

        else:

            quantity = 0

            trade_disabled = True

            if action == "Buy":

                st.warning(
                    "You do not have enough credits "
                    "to buy this asset."
                )

            else:

                st.warning(
                    "You do not currently own "
                    "this asset."
                )


        # ----------------------------------------------------
        # EXECUTE TRADE
        # ----------------------------------------------------

        if st.button(
            "Execute trade",
            type="primary",
            use_container_width=True,
            disabled=trade_disabled,
            key="execute_trade_button"
        ):

            qty = int(quantity)

            # Re-read current price and balances
            # immediately before executing.
            prices_now = current_prices()

            price_now = prices_now[asset]

            if action == "Buy":

                max_buy_now = int(
                    st.session_state.cash
                    // price_now
                )

                if qty < 1 or qty > max_buy_now:

                    st.error(
                        "You do not have enough "
                        "credits for that trade."
                    )

                    st.stop()

                value = (
                    qty
                    * price_now
                )

                st.session_state.cash -= value

                st.session_state.positions[
                    asset
                ] += qty

                st.session_state.position_cost_basis[
                    asset
                ] += value

                st.session_state.total_bought_value += value


            else:

                max_sell_now = (
                    st.session_state.positions[
                        asset
                    ]
                )

                if qty < 1 or qty > max_sell_now:

                    st.error(
                        "You do not own enough "
                        "units for that trade."
                    )

                    st.stop()

                value = (
                    qty
                    * price_now
                )

                current_units = (
                    st.session_state.positions[
                        asset
                    ]
                )

                current_cost_basis = (
                    st.session_state.position_cost_basis[
                        asset
                    ]
                )

                average_cost = (
                    current_cost_basis
                    / current_units
                    if current_units > 0
                    else 0.0
                )

                st.session_state.cash += value

                st.session_state.positions[
                    asset
                ] -= qty

                st.session_state.position_cost_basis[
                    asset
                ] = max(
                    0.0,
                    current_cost_basis
                    - average_cost * qty
                )

                st.session_state.total_sold_value += value


            # ------------------------------------------------
            # RECORD TRADE
            # ------------------------------------------------

            st.session_state.trade_count += 1

            now_elapsed = (
                time.monotonic()
                - st.session_state.start_monotonic
            )

            pv = portfolio_value(
                st.session_state
            )

            tv = total_value(
                st.session_state
            )

            log_trade(
                {
                    "trade_id":
                        str(uuid.uuid4()),

                    "participant_id":
                        st.session_state.participant_id,

                    "timestamp":
                        datetime.now(
                            timezone.utc
                        ).isoformat(),

                    "elapsed_seconds":
                        round(
                            now_elapsed,
                            2
                        ),

                    "action":
                        action,

                    "asset":
                        asset,

                    "quantity":
                        qty,

                    "price":
                        price_now,

                    "trade_value":
                        value,

                    "cash_after":
                        st.session_state.cash,

                    "portfolio_value_after":
                        pv,

                    "total_value_after":
                        tv,

                    "risk_score":
                        RISK_SCORE[
                            ASSETS[asset]["risk"]
                        ]
                }
            )


            # ------------------------------------------------
            # GAMIFICATION
            # ------------------------------------------------

            if (
                st.session_state.condition
                == "Gamified"
            ):

                st.session_state.reward_variant = (
                    random.choice(
                        [
                            "balloons",
                            "star",
                            "confetti"
                        ]
                    )
                )

                reward_messages = {

                    "balloons":
                        [
                            "Great choice!",
                            "Keep it moving!",
                            "Up you go!",
                            "Nice lift!"
                        ],

                    "star":
                        [
                            "Brilliant move!",
                            "Sharp thinking!",
                            "You saw it!",
                            "Excellent call!"
                        ],

                    "confetti":
                        [
                            "Nice work!",
                            "Trade success!",
                            "Well played!",
                            "Good momentum!"
                        ]
                }

                st.session_state.reward_message = (
                    random.choice(
                        reward_messages[
                            st.session_state.reward_variant
                        ]
                    )
                )

                if (
                    st.session_state.reward_variant
                    == "balloons"
                ):

                    st.balloons()

                st.session_state.celebration_until = (
                    time.monotonic() + 2
                )

            else:

                st.success(
                    "Trade executed."
                )


            # Rerun once after the trade so that
            # balances, charts and tables update.
            st.rerun()


    # ========================================================
    # PORTFOLIO
    # ========================================================

    with right:

        st.subheader("Your portfolio")

        portfolio_rows = []

        for asset in ASSETS:

            qty = (
                st.session_state.positions[
                    asset
                ]
            )

            if qty > 0:

                current_value = (
                    qty
                    * prices[asset]
                )

                cost_basis = (
                    st.session_state.position_cost_basis[
                        asset
                    ]
                )

                return_pct = (
                    (
                        current_value
                        - cost_basis
                    )
                    / cost_basis
                    * 100
                    if cost_basis
                    else 0.0
                )

                portfolio_rows.append(
                    {
                        "Asset":
                            asset,

                        "Risk":
                            ASSETS[asset]["risk"],

                        "Units":
                            qty,

                        "Current value":
                            current_value,

                        "Return %":
                            return_pct
                    }
                )


        if portfolio_rows:

            st.dataframe(
                pd.DataFrame(
                    portfolio_rows
                ).style.format(
                    {
                        "Current value":
                            "${:,.2f}",

                        "Return %":
                            "{:+.2f}%"
                    }
                ),
                use_container_width=True,
                hide_index=True
            )

        else:

            st.write(
                "No positions yet."
            )


        st.subheader(
            "Behaviour indicators"
        )

        b1, b2, b3 = st.columns(3)

        b1.metric(
            "Invested",
            f"{invested_pct(st.session_state) * 100:.1f}%"
        )

        b2.metric(
            "High-risk exposure",
            f"{high_risk_pct(st.session_state) * 100:.1f}%"
        )

        b3.metric(
            "Turnover",
            f"${turnover(st.session_state):,.0f}"
        )


    # ========================================================
    # LIVE REFRESH
    # ========================================================

    time.sleep(1)

    st.rerun()


# ============================================================
# PAGE 3: THANK YOU
# ============================================================

elif st.session_state.page == "results":

    st.markdown(
        """
        <div class="hero">
            <h1>Thank you for participating!</h1>
            <p>
                Your participation has been recorded.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.success(
        "The trading simulation is now complete. "
        "You may close this page."
    )
