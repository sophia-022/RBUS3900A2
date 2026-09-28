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

# 8-minute trading period
TRADING_SECONDS = 8 * 60

# Market prices update every 5 seconds
TICK_SECONDS = 5

VOLATILITY_MULTIPLIER = 5.0

DB_PATH = os.getenv(
    "TRADING_DB_PATH",
    "trading_simulation.db"
)


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
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Trading Simulation",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# DATABASE
# ============================================================

def get_conn():

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.execute(
        "PRAGMA journal_mode=WAL;"
    )

    return conn


def init_db():

    conn = get_conn()

    # --------------------------------------------------------
    # PARTICIPANTS
    # --------------------------------------------------------

    conn.execute(
        """
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
        """
    )

    # --------------------------------------------------------
    # TRADES
    # --------------------------------------------------------

    conn.execute(
        """
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
        """
    )

    # --------------------------------------------------------
    # SNAPSHOTS
    # --------------------------------------------------------

    conn.execute(
        """
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
        """
    )

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

    gamified_count = counts.get(
        "Gamified",
        0
    )

    non_gamified_count = counts.get(
        "Non-gamified",
        0
    )

    # Keep groups approximately balanced
    if gamified_count < non_gamified_count:
        return "Gamified"

    if non_gamified_count < gamified_count:
        return "Non-gamified"

    return random.SystemRandom().choice(
        [
            "Gamified",
            "Non-gamified"
        ]
    )


def insert_participant():

    s = st.session_state

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO participants (
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
        INSERT INTO trades (
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
        INSERT INTO snapshots (
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
            ended_at = ?,
            final_cash = ?,
            final_portfolio_value = ?,
            final_total_value = ?
        WHERE participant_id = ?
        """,
        (
            datetime.now(
                timezone.utc
            ).isoformat(),

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

    number_of_points = (
        total_seconds // step
    ) + 1

    market = {}

    for asset, specification in ASSETS.items():

        prices = [
            specification["start"]
        ]

        step_volatility = (
            specification["daily_vol"]
            * VOLATILITY_MULTIPLIER
        ) / np.sqrt(78)

        for _ in range(
            number_of_points - 1
        ):

            return_value = rng.normal(
                0,
                step_volatility
            )

            next_price = (
                prices[-1]
                * (1 + return_value)
            )

            prices.append(
                max(
                    1.0,
                    next_price
                )
            )

        market[asset] = np.array(
            prices
        )

    return market


def current_prices():

    elapsed = (
        time.monotonic()
        - st.session_state.start_monotonic
    )

    elapsed = min(
        TRADING_SECONDS,
        max(0, elapsed)
    )

    first_asset_prices = next(
        iter(
            st.session_state.market.values()
        )
    )

    index = min(
        len(first_asset_prices) - 1,
        int(elapsed // TICK_SECONDS)
    )

    return {
        asset: float(
            prices[index]
        )
        for asset, prices
        in st.session_state.market.items()
    }


# ============================================================
# PORTFOLIO CALCULATIONS
# ============================================================

def portfolio_value(s):

    prices = current_prices()

    return sum(
        quantity * prices[asset]
        for asset, quantity
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
        s.positions[asset]
        * prices[asset]

        for asset in s.positions

        if ASSETS[asset]["risk"]
        == "High"
    )


def invested_pct(s):

    total = total_value(s)

    if total <= 0:
        return 0.0

    return (
        portfolio_value(s)
        / total
    )


def high_risk_pct(s):

    portfolio = portfolio_value(s)

    if portfolio <= 0:
        return 0.0

    return (
        high_risk_value(s)
        / portfolio
    )


# ============================================================
# SESSION STATE
# ============================================================

def initialise():

    if "page" not in st.session_state:

        st.session_state.page = (
            "instructions"
        )

        st.session_state.participant_id = (
            str(uuid.uuid4())
        )

        st.session_state.condition = None

        st.session_state.market_seed = (
            random.randint(
                1,
                2_000_000_000
            )
        )

        st.session_state.positions = {
            asset: 0
            for asset in ASSETS
        }

        st.session_state.position_cost_basis = {
            asset: 0.0
            for asset in ASSETS
        }

        st.session_state.cash = (
            STARTING_CREDITS
        )

        st.session_state.total_bought_value = 0.0
        st.session_state.total_sold_value = 0.0

        # No trade limit
        st.session_state.trade_count = 0

        st.session_state.started_at = None
        st.session_state.start_monotonic = None

        st.session_state.performance_history = []

        st.session_state.last_snapshot_bucket = -1

        st.session_state.finished = False

        st.session_state.exit_reason = None

        st.session_state.celebration_until = 0

        st.session_state.reward_message = None

        st.session_state.reward_variant = None


initialise()

init_db()


# ============================================================
# GENERAL STYLING
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
        padding: 20px 25px;
        border-radius: 18px;
        background: linear-gradient(
            90deg,
            #ff9bc5,
            #b7a8ff
        );
        margin-bottom: 20px;
    }

    .hero h1,
    .hero h2,
    .hero p {
        color: #111111 !important;
    }

    .badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 999px;
        background: #ffffffaa;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .live-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        margin-right: 6px;
        border-radius: 50%;
        background: #111111;
        animation: livePulse 1s ease-in-out infinite;
    }

    .celebration-card {
        padding: 24px;
        margin: 10px 0 20px 0;
        border-radius: 20px;
        text-align: center;
        background: linear-gradient(
            135deg,
            #ff9bc5,
            #b7a8ff
        );
        box-shadow:
            0 8px 25px
            rgba(0,0,0,0.15);
        animation: celebrationPop
            0.45s ease-out;
    }

    .celebration-emoji {
        font-size: 60px;
        animation: celebrationBounce
            0.65s ease-in-out
            infinite alternate;
    }

    .celebration-title {
        font-size: 32px;
        font-weight: 800;
        margin-top: 5px;
        color: #111111 !important;
    }

    .celebration-subtitle {
        font-size: 18px;
        font-weight: 600;
        color: #111111 !important;
        margin-top: 5px;
    }

    @keyframes celebrationPop {

        0% {
            transform: scale(0.7);
            opacity: 0;
        }

        70% {
            transform: scale(1.05);
            opacity: 1;
        }

        100% {
            transform: scale(1);
            opacity: 1;
        }
    }

    @keyframes celebrationBounce {

        0% {
            transform:
                translateY(0px)
                rotate(-8deg)
                scale(1);
        }

        100% {
            transform:
                translateY(-12px)
                rotate(8deg)
                scale(1.12);
        }
    }

    @keyframes livePulse {

        0%, 100% {
            transform: scale(1);
            opacity: 1;
        }

        50% {
            transform: scale(1.5);
            opacity: 0.45;
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
                Thank you for participating in this
                simulated trading study.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.info(
        "You will receive $10,000 in simulated credits. "
        "These credits have no real monetary value."
    )

    st.subheader(
        "Rules of the simulation"
    )

    st.markdown(
        """
        1. You will begin with **$10,000 in simulated credits**.

        2. You may buy and sell shares using your simulated credits.

        3. You may make **as many trades as you wish** during the simulation.

        4. You can only buy shares when you have enough simulated credits.

        5. You can only sell shares that you currently own.

        6. Share prices will change throughout the simulation.

        7. The trading period will last for **8 minutes**.

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
        "I understand the instructions and agree to participate.",
        key="understand_checkbox"
    )

    if st.button(
        "Start Trading",
        type="primary",
        use_container_width=True,
        disabled=not understood,
        key="start_trading_button"
    ):

        # ----------------------------------------------------
        # Assign experimental condition
        # ----------------------------------------------------

        st.session_state.condition = (
            assign_condition()
        )

        # ----------------------------------------------------
        # Start timer
        # ----------------------------------------------------

        st.session_state.started_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        st.session_state.start_monotonic = (
            time.monotonic()
        )

        # ----------------------------------------------------
        # Generate private market path
        # ----------------------------------------------------

        st.session_state.market = (
            make_market(
                st.session_state.market_seed
            )
        )

        # ----------------------------------------------------
        # Reset trading state
        # ----------------------------------------------------

        st.session_state.positions = {
            asset: 0
            for asset in ASSETS
        }

        st.session_state.position_cost_basis = {
            asset: 0.0
            for asset in ASSETS
        }

        st.session_state.cash = (
            STARTING_CREDITS
        )

        st.session_state.total_bought_value = 0.0
        st.session_state.total_sold_value = 0.0

        st.session_state.trade_count = 0

        st.session_state.performance_history = []

        st.session_state.last_snapshot_bucket = -1

        st.session_state.finished = False

        st.session_state.exit_reason = None

        # ----------------------------------------------------
        # Save participant
        # ----------------------------------------------------

        insert_participant()

        # ----------------------------------------------------
        # Move to trading page
        # ----------------------------------------------------

        st.session_state.page = "trading"

        st.rerun()


# ============================================================
# PAGE 2: TRADING
# ============================================================

elif st.session_state.page == "trading":

    # --------------------------------------------------------
    # Calculate elapsed time
    # --------------------------------------------------------

    elapsed = (
        time.monotonic()
        - st.session_state.start_monotonic
    )

    remaining = max(
        0,
        TRADING_SECONDS - elapsed
    )


    # --------------------------------------------------------
    # End automatically after 8 minutes
    # --------------------------------------------------------

    if remaining <= 0:

        st.session_state.exit_reason = (
            "Time completed"
        )

        st.session_state.page = (
            "thank_you"
        )

        finish_participant()

        st.rerun()


    # --------------------------------------------------------
    # Current prices
    # --------------------------------------------------------

    prices = current_prices()


    # ========================================================
    # GAMIFIED CELEBRATION
    # ========================================================

    if (
        st.session_state.get(
            "celebration_until",
            0
        )
        > time.monotonic()
    ):

        reward_message = (
            st.session_state.get(
                "reward_message",
                "Great trade!"
            )
        )

        reward_variant = (
            st.session_state.get(
                "reward_variant",
                "balloons"
            )
        )

        # Native Streamlit animations
        if reward_variant == "balloons":

            st.balloons()

        elif reward_variant == "snow":

            st.snow()


        # Animated celebration card
        st.markdown(
            f"""
            <div class="celebration-card">

                <div class="celebration-emoji">
                    🎉
                </div>

                <div class="celebration-title">
                    {reward_message}
                </div>

                <div class="celebration-subtitle">
                    Trade successfully recorded!
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )


    # ========================================================
    # PERFORMANCE HISTORY
    # ========================================================

    current_total_value = (
        total_value(
            st.session_state
        )
    )

    st.session_state.performance_history.append(
        {
            "Elapsed minutes":
                round(
                    elapsed / 60,
                    2
                ),

            "Total value":
                current_total_value,

            "Portfolio value":
                portfolio_value(
                    st.session_state
                ),

            "Available credits":
                st.session_state.cash
        }
    )


    # ========================================================
    # PERIODIC SNAPSHOT
    # ========================================================

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

        snapshot_total_value = (
            total_value(
                st.session_state
            )
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
                    round(
                        elapsed,
                        2
                    ),

                "cash":
                    st.session_state.cash,

                "portfolio_value":
                    portfolio_value(
                        st.session_state
                    ),

                "total_value":
                    snapshot_total_value,

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


    # ========================================================
    # HEADER
    # ========================================================

    minutes, seconds = divmod(
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

            <h1>
                Trading Simulation
            </h1>

            <h2>
                Time remaining:
                {minutes:02d}:{seconds:02d}
            </h2>

        </div>
        """,
        unsafe_allow_html=True
    )


    # ========================================================
    # EXIT BUTTON
    # ========================================================

    exit_left, exit_right = st.columns(
        [5, 1]
    )

    with exit_right:

        if st.button(
            "Exit simulation",
            type="secondary",
            use_container_width=True,
            key="exit_simulation_button"
        ):

            st.session_state.exit_reason = (
                "Participant exited early"
            )

            st.session_state.page = (
                "thank_you"
            )

            finish_participant()

            st.rerun()


    # ========================================================
    # SUMMARY METRICS
    # ========================================================

    metric1, metric2, metric3, metric4 = (
        st.columns(4)
    )

    metric1.metric(
        "Available credits",
        f"${st.session_state.cash:,.0f}"
    )

    metric2.metric(
        "Portfolio value",
        f"${portfolio_value(st.session_state):,.0f}"
    )

    metric3.metric(
        "Total value",
        f"${total_value(st.session_state):,.0f}"
    )

    metric4.metric(
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

    st.subheader(
        "Investment performance"
    )

    performance = (
        pd.DataFrame(
            st.session_state.performance_history
        )
        .drop_duplicates(
            subset=["Elapsed minutes"],
            keep="last"
        )
        .set_index(
            "Elapsed minutes"
        )
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

    st.subheader(
        "Share price history"
    )

    history_choice = st.selectbox(
        "Choose a share to inspect",
        [
            "All shares"
        ] + list(ASSETS.keys()),
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
                    (
                        st.session_state.market[
                            asset
                        ]
                        /
                        st.session_state.market[
                            asset
                        ][0]
                        * 100
                    )

                for asset in ASSETS
            },
            index=history_minutes
        )

        history.index.name = "Minutes"

        st.caption(
            "All shares are indexed to 100 at "
            "the start so their performance "
            "can be compared fairly."
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

    for asset, specification in ASSETS.items():

        current_price = prices[asset]

        starting_price = (
            st.session_state.market[
                asset
            ][0]
        )

        price_change = (
            current_price
            - starting_price
        )

        rows.append(
            {
                "Asset":
                    asset,

                "Risk":
                    specification["risk"],

                "Current price":
                    current_price,

                "Change":
                    price_change,

                "Change %":
                    (
                        price_change
                        / starting_price
                        * 100
                    ),

                "Units held":
                    st.session_state.positions[
                        asset
                    ],

                "Position value":
                    (
                        st.session_state.positions[
                            asset
                        ]
                        * current_price
                    )
            }
        )

    asset_table = pd.DataFrame(
        rows
    )

    st.dataframe(
        asset_table.style.format(
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
    # SINGLE TRADING BOX
    # ========================================================

    left, right = st.columns(
        [1, 2]
    )


    # ========================================================
    # TRADE FORM
    # ========================================================

    with left:

        st.subheader(
            "Place a trade"
        )

        # IMPORTANT:
        # There is ONE form and ONE quantity input.
        # This prevents the duplicated trading controls.

        with st.form(
            "single_trade_form",
            clear_on_submit=False
        ):

            trade_asset = st.selectbox(
                "Asset",
                list(ASSETS.keys()),
                key="trade_asset"
            )

            trade_action = st.radio(
                "Action",
                [
                    "Buy",
                    "Sell"
                ],
                horizontal=True,
                key="trade_action"
            )

            trade_price = prices[
                trade_asset
            ]


            # ------------------------------------------------
            # BUY
            # ------------------------------------------------

            if trade_action == "Buy":

                maximum_quantity = int(
                    st.session_state.cash
                    // trade_price
                )

                if maximum_quantity > 0:

                    st.caption(
                        f"Maximum affordable: "
                        f"{maximum_quantity:,} units"
                    )

                else:

                    st.caption(
                        "You do not currently "
                        "have enough credits "
                        "to buy this asset."
                    )


            # ------------------------------------------------
            # SELL
            # ------------------------------------------------

            else:

                maximum_quantity = int(
                    st.session_state.positions[
                        trade_asset
                    ]
                )

                if maximum_quantity > 0:

                    st.caption(
                        f"Units available to sell: "
                        f"{maximum_quantity:,}"
                    )

                else:

                    st.caption(
                        "You do not currently "
                        "own this asset."
                    )


            # ------------------------------------------------
            # QUANTITY
            # ------------------------------------------------

            if maximum_quantity > 0:

                trade_quantity = st.number_input(
                    "Number of units",
                    min_value=1,
                    max_value=maximum_quantity,
                    value=1,
                    step=1,
                    key="trade_quantity"
                )

                trade_available = True

            else:

                trade_quantity = 0

                trade_available = False


            # ------------------------------------------------
            # EXECUTE
            # ------------------------------------------------

            execute_trade = st.form_submit_button(
                "Execute trade",
                type="primary",
                use_container_width=True,
                disabled=not trade_available
            )


    # ========================================================
    # PROCESS TRADE
    # ========================================================

    if execute_trade and trade_available:

        # Recalculate the price at execution
        execution_prices = current_prices()

        execution_price = (
            execution_prices[
                trade_asset
            ]
        )

        quantity = int(
            trade_quantity
        )

        trade_completed = False


        # ----------------------------------------------------
        # BUY VALIDATION
        # ----------------------------------------------------

        if trade_action == "Buy":

            maximum_affordable = int(
                st.session_state.cash
                // execution_price
            )

            if quantity < 1:

                st.error(
                    "Please select a valid "
                    "quantity."
                )

            elif quantity > maximum_affordable:

                st.error(
                    "You do not have enough "
                    "credits for that trade."
                )

            else:

                trade_value = (
                    quantity
                    * execution_price
                )

                st.session_state.cash -= (
                    trade_value
                )

                st.session_state.positions[
                    trade_asset
                ] += quantity

                st.session_state.position_cost_basis[
                    trade_asset
                ] += trade_value

                st.session_state.total_bought_value += (
                    trade_value
                )

                trade_completed = True


        # ----------------------------------------------------
        # SELL VALIDATION
        # ----------------------------------------------------

        elif trade_action == "Sell":

            units_owned = (
                st.session_state.positions[
                    trade_asset
                ]
            )

            if quantity < 1:

                st.error(
                    "Please select a valid "
                    "quantity."
                )

            elif quantity > units_owned:

                st.error(
                    "You do not own enough "
                    "units for that trade."
                )

            else:

                trade_value = (
                    quantity
                    * execution_price
                )

                current_units = (
                    st.session_state.positions[
                        trade_asset
                    ]
                )

                current_cost_basis = (
                    st.session_state.position_cost_basis[
                        trade_asset
                    ]
                )

                average_cost = (
                    current_cost_basis
                    / current_units
                    if current_units > 0
                    else 0.0
                )

                st.session_state.cash += (
                    trade_value
                )

                st.session_state.positions[
                    trade_asset
                ] -= quantity

                st.session_state.position_cost_basis[
                    trade_asset
                ] = max(
                    0.0,
                    current_cost_basis
                    - (
                        average_cost
                        * quantity
                    )
                )

                st.session_state.total_sold_value += (
                    trade_value
                )

                trade_completed = True


        # ====================================================
        # SAVE SUCCESSFUL TRADE
        # ====================================================

        if trade_completed:

            st.session_state.trade_count += 1

            trade_elapsed = (
                time.monotonic()
                - st.session_state.start_monotonic
            )

            new_portfolio_value = (
                portfolio_value(
                    st.session_state
                )
            )

            new_total_value = (
                total_value(
                    st.session_state
                )
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
                            trade_elapsed,
                            2
                        ),

                    "action":
                        trade_action,

                    "asset":
                        trade_asset,

                    "quantity":
                        quantity,

                    "price":
                        execution_price,

                    "trade_value":
                        trade_value,

                    "cash_after":
                        st.session_state.cash,

                    "portfolio_value_after":
                        new_portfolio_value,

                    "total_value_after":
                        new_total_value,

                    "risk_score":
                        RISK_SCORE[
                            ASSETS[
                                trade_asset
                            ]["risk"]
                        ]
                }
            )


            # =================================================
            # GAMIFIED CONDITION
            # =================================================

            if (
                st.session_state.condition
                == "Gamified"
            ):

                st.session_state.reward_variant = (
                    random.choice(
                        [
                            "balloons",
                            "snow"
                        ]
                    )
                )

                reward_messages = [
                    "Great choice!",
                    "Brilliant move!",
                    "Excellent call!",
                    "Nice work!",
                    "Trade success!",
                    "Keep it moving!",
                    "Well played!",
                    "Good momentum!"
                ]

                st.session_state.reward_message = (
                    random.choice(
                        reward_messages
                    )
                )

                st.session_state.celebration_until = (
                    time.monotonic()
                    + 3
                )

            else:

                st.session_state.reward_message = None

                st.session_state.celebration_until = 0


            # ------------------------------------------------
            # ONE AND ONLY ONE RERUN
            # ------------------------------------------------

            st.rerun()


    # ========================================================
    # PORTFOLIO DISPLAY
    # ========================================================

    with right:

        st.subheader(
            "Your portfolio"
        )

        portfolio_rows = []

        for asset in ASSETS:

            quantity = (
                st.session_state.positions[
                    asset
                ]
            )

            if quantity > 0:

                current_value = (
                    quantity
                    * prices[asset]
                )

                cost_basis = (
                    st.session_state.position_cost_basis[
                        asset
                    ]
                )

                return_percentage = (
                    (
                        current_value
                        - cost_basis
                    )
                    / cost_basis
                    * 100
                    if cost_basis > 0
                    else 0.0
                )

                portfolio_rows.append(
                    {
                        "Asset":
                            asset,

                        "Risk":
                            ASSETS[asset]["risk"],

                        "Units":
                            quantity,

                        "Current value":
                            current_value,

                        "Return %":
                            return_percentage
                    }
                )


        if portfolio_rows:

            portfolio_table = pd.DataFrame(
                portfolio_rows
            )

            st.dataframe(
                portfolio_table.style.format(
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


        # ====================================================
        # BEHAVIOUR INDICATORS
        # ====================================================

        st.subheader(
            "Behaviour indicators"
        )

        behaviour1, behaviour2, behaviour3 = (
            st.columns(3)
        )

        behaviour1.metric(
            "Invested",
            f"{invested_pct(st.session_state) * 100:.1f}%"
        )

        behaviour2.metric(
            "High-risk exposure",
            f"{high_risk_pct(st.session_state) * 100:.1f}%"
        )

        behaviour3.metric(
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

elif st.session_state.page == "thank_you":

    st.markdown(
        """
        <div class="hero">

            <h1>
                Thank you for participating! 🎉
            </h1>

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
