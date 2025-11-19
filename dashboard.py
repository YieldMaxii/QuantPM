import json
import time
import uuid  # <--- Added for unique DOM IDs
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

# -------------------------------------------------------------------
# Basic app config
# -------------------------------------------------------------------

st.set_page_config(
    page_title="META-PM Strategy Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
DATA_DIR = BASE_DIR / "data"
LOGS_LIVE_DIR = BASE_DIR / "logs_live"
LOGS_LIVE_DIR.mkdir(parents=True, exist_ok=True)

# File to persist timer state
TIMER_STATE_FILE = LOGS_LIVE_DIR / "timer_state.json"


def load_timer_state() -> dict:
    """Load timer state from file."""
    if TIMER_STATE_FILE.exists():
        try:
            with TIMER_STATE_FILE.open("r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_timer_state(start_time: datetime) -> None:
    """Save timer state to file."""
    try:
        with TIMER_STATE_FILE.open("w") as f:
            json.dump({
                "start_time": start_time.isoformat(),
            }, f)
    except Exception as e:
        st.error(f"Error saving timer state: {e}")


def get_persistent_start_time() -> datetime:
    """Get start time from file or create new one."""
    state = load_timer_state()
    if "start_time" in state:
        try:
            saved_start = datetime.fromisoformat(state["start_time"])
            # Check if timer has expired (more than 24 hours old)
            elapsed = datetime.now(timezone.utc) - saved_start
            if elapsed.total_seconds() < 86400:  # Less than 24 hours
                return saved_start
            # Timer expired, create new one
        except Exception:
            pass
    # Create new start time
    new_start = datetime.now(timezone.utc)
    save_timer_state(new_start)
    return new_start

# -------------------------------------------------------------------
# Data loading helpers
# -------------------------------------------------------------------

def read_csv_if_exists(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


@st.cache_data
def load_scores() -> pd.DataFrame:
    """Load overall per-strategy scores (built-in + plugin)."""
    scores_builtin = read_csv_if_exists(OUTPUTS_DIR / "scores.csv")
    if not scores_builtin.empty:
        scores_builtin["source"] = "built_in"

    scores_logs = read_csv_if_exists(OUTPUTS_DIR / "scores_from_logs.csv")
    if not scores_logs.empty:
        scores_logs["source"] = "plugin"

    scores = pd.concat([scores_builtin, scores_logs], ignore_index=True)
    if scores.empty:
        return scores

    for col in ["total_pnl", "brier_mean", "max_drawdown"]:
        if col in scores.columns:
            scores[col] = pd.to_numeric(scores[col], errors="coerce")
    if "n_trades" in scores.columns:
        scores["n_trades"] = pd.to_numeric(scores["n_trades"], errors="coerce")

    return scores


@st.cache_data
def load_scores_by_market() -> pd.DataFrame:
    """Load per-strategy, per-market scores."""
    sbm_builtin = read_csv_if_exists(OUTPUTS_DIR / "scores_by_market.csv")
    if not sbm_builtin.empty:
        sbm_builtin["source"] = "built_in"

    sbm_logs = read_csv_if_exists(OUTPUTS_DIR / "scores_by_market_from_logs.csv")
    if not sbm_logs.empty:
        sbm_logs["source"] = "plugin"

    sbm = pd.concat([sbm_builtin, sbm_logs], ignore_index=True)
    if sbm.empty:
        return sbm

    for col in ["total_pnl", "brier_mean", "max_drawdown"]:
        if col in sbm.columns:
            sbm[col] = pd.to_numeric(sbm[col], errors="coerce")
    if "n_trades" in sbm.columns:
        sbm["n_trades"] = pd.to_numeric(sbm["n_trades"], errors="coerce")

    return sbm


@st.cache_data
def load_trades() -> pd.DataFrame:
    """Load all trades (built-in + plugin)."""
    trades_builtin = read_csv_if_exists(
        OUTPUTS_DIR / "trades.csv", parse_dates=["entry_time"]
    )
    if not trades_builtin.empty:
        trades_builtin["source"] = "built_in"

    trades_logs = read_csv_if_exists(
        OUTPUTS_DIR / "trades_from_logs.csv", parse_dates=["entry_time"]
    )
    if not trades_logs.empty:
        trades_logs["source"] = "plugin"

    trades = pd.concat([trades_builtin, trades_logs], ignore_index=True)
    if trades.empty:
        return trades

    numeric_cols = ["entry_price", "size", "p_hat", "outcome", "pnl"]
    for col in numeric_cols:
        if col in trades.columns:
            trades[col] = pd.to_numeric(trades[col], errors="coerce")

    return trades


@st.cache_data
def load_markets_meta() -> pd.DataFrame:
    """Load markets_meta.csv if it exists, for names."""
    meta = read_csv_if_exists(DATA_DIR / "markets_meta.csv")
    if meta.empty:
        return meta

    expected = ["market_id", "name", "outcome"]
    for col in expected:
        if col not in meta.columns:
            meta[col] = None

    return meta


# -------------------------------------------------------------------
# Load all data once
# -------------------------------------------------------------------

scores = load_scores()
scores_by_market = load_scores_by_market()
trades = load_trades()
markets_meta = load_markets_meta()

st.title("META-PM Strategy Dashboard")

# -------------------------------------------------------------------
# Sidebar filters
# -------------------------------------------------------------------

st.sidebar.header("Filters")

available_sources = []
if not scores.empty:
    available_sources = sorted(scores["source"].dropna().unique().tolist())

if not available_sources:
    selected_sources = []
else:
    selected_sources = st.sidebar.multiselect(
        "Data sources",
        options=available_sources,
        default=available_sources,
        help="Built-in engine strategies vs plugin/log-evaluated strategies.",
    )


def filter_by_sources(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not selected_sources:
        return df
    if "source" not in df.columns:
        return df
    return df[df["source"].isin(selected_sources)]


scores_filtered = filter_by_sources(scores)
scores_by_market_filtered = filter_by_sources(scores_by_market)
trades_filtered = filter_by_sources(trades)

all_strategies = (
    sorted(scores_filtered["strategy_name"].unique().tolist())
    if not scores_filtered.empty
    else []
)

strategy_selection = st.sidebar.multiselect(
    "Strategies",
    options=all_strategies,
    default=all_strategies,
)


def filter_by_strategies(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not strategy_selection:
        return df
    return df[df["strategy_name"].isin(strategy_selection)]


scores_filtered = filter_by_strategies(scores_filtered)
scores_by_market_filtered = filter_by_strategies(scores_by_market_filtered)
trades_filtered = filter_by_strategies(trades_filtered)

all_markets = (
    sorted(scores_by_market_filtered["market_id"].unique().tolist())
    if not scores_by_market_filtered.empty
    else []
)

market_selection = st.sidebar.multiselect(
    "Markets",
    options=all_markets,
    default=all_markets,
)


def filter_by_markets(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not market_selection:
        return df
    if "market_id" not in df.columns:
        return df
    return df[df["market_id"].isin(market_selection)]


scores_by_market_filtered = filter_by_markets(scores_by_market_filtered)
trades_filtered = filter_by_markets(trades_filtered)

# -------------------------------------------------------------------
# High-level KPIs
# -------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

n_strategies = (
    scores_filtered["strategy_name"].nunique() if not scores_filtered.empty else 0
)
n_markets = (
    scores_by_market_filtered["market_id"].nunique()
    if not scores_by_market_filtered.empty
    else 0
)
total_pnl_all = (
    scores_filtered["total_pnl"].sum()
    if "total_pnl" in scores_filtered.columns
    else 0.0
)
avg_brier = (
    scores_filtered["brier_mean"].mean()
    if "brier_mean" in scores_filtered.columns
    and not scores_filtered["brier_mean"].isna().all()
    else None
)

col1.metric("Strategies", n_strategies)
col2.metric("Markets", n_markets)
col3.metric("Total P&L", f"{total_pnl_all:0.3f}")
col4.metric("Avg. Brier", f"{avg_brier:0.4f}" if avg_brier is not None else "N/A")

# -------------------------------------------------------------------
# Tabs: Leaderboard | Per Market | Strategy Detail | Performance Over Time
# -------------------------------------------------------------------

tab_leaderboard, tab_per_market, tab_strategy, tab_perf, tab_live = st.tabs(
    ["Leaderboard", "Per Market", "Strategy Detail", "Performance Over Time", "Live Trading"]
)

# -------------------------------------------------------------------
# Leaderboard tab
# -------------------------------------------------------------------

with tab_leaderboard:
    st.subheader("Overall Strategy Leaderboard")

    if scores_filtered.empty:
        st.info("No scores available for the selected filters.")
    else:
        df_lb = scores_filtered.copy()
        df_lb = df_lb.sort_values("total_pnl", ascending=False)

        st.dataframe(
            df_lb.reset_index(drop=True),
            use_container_width=True,
            height=400,
        )

        fig = px.bar(
            df_lb,
            x="strategy_name",
            y="total_pnl",
            color="source",
            hover_data=["brier_mean", "max_drawdown", "n_trades"],
            title="Total P&L by Strategy",
        )
        fig.update_layout(xaxis_title="", yaxis_title="Total P&L")
        st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------------------------
# Per Market tab
# -------------------------------------------------------------------

with tab_per_market:
    st.subheader("Per-Market P&L by Strategy")

    if scores_by_market_filtered.empty:
        st.info("No per-market scores available for the selected filters.")
    else:
        sbm = scores_by_market_filtered.copy()

        if not markets_meta.empty:
            sbm = sbm.merge(
                markets_meta[["market_id", "name"]],
                on="market_id",
                how="left",
                suffixes=("", "_market_name"),
            )
            sbm["market_label"] = sbm["market_id"]
            sbm.loc[~sbm["name"].isna(), "market_label"] = (
                sbm["market_id"] + " – " + sbm["name"]
            )
        else:
            sbm["market_label"] = sbm["market_id"]

        pivot = sbm.pivot_table(
            index="strategy_name",
            columns="market_label",
            values="total_pnl",
            aggfunc="sum",
            fill_value=0.0,
        )

        st.markdown("**P&L matrix (strategy × market)**")
        st.dataframe(pivot, use_container_width=True, height=400)

        if not pivot.empty:
            fig_hm = px.imshow(
                pivot.values,
                x=pivot.columns,
                y=pivot.index,
                labels=dict(color="Total P&L"),
                aspect="auto",
                title="Per-Market P&L Heatmap",
            )
            st.plotly_chart(fig_hm, use_container_width=True)

        st.markdown("**Per-market leaderboards**")
        for m_id in market_selection:
            sbm_m = sbm[sbm["market_id"] == m_id].copy()
            if sbm_m.empty:
                continue
            st.markdown(f"**Market {m_id}**")
            sbm_m = sbm_m.sort_values("total_pnl", ascending=False)
            st.dataframe(
                sbm_m[
                    [
                        "strategy_name",
                        "total_pnl",
                        "brier_mean",
                        "max_drawdown",
                        "n_trades",
                    ]
                ],
                use_container_width=True,
            )

# -------------------------------------------------------------------
# Strategy Detail tab
# -------------------------------------------------------------------

with tab_strategy:
    st.subheader("Strategy Detail")

    if not all_strategies:
        st.info("No strategies available.")
    else:
        strat_choice = st.selectbox(
            "Select a strategy",
            options=all_strategies,
        )

        strat_scores = scores_filtered[scores_filtered["strategy_name"] == strat_choice]
        strat_sbm = scores_by_market_filtered[
            scores_by_market_filtered["strategy_name"] == strat_choice
        ]
        strat_trades = trades_filtered[
            trades_filtered["strategy_name"] == strat_choice
        ]

        if strat_scores.empty:
            st.info("No scores for this strategy under current filters.")
        else:
            col_a, col_b, col_c, col_d = st.columns(4)
            row = strat_scores.iloc[0]
            col_a.metric("Total P&L", f"{row['total_pnl']:0.3f}")
            col_b.metric(
                "Max Drawdown",
                f"{row['max_drawdown']:0.3f}"
                if pd.notna(row["max_drawdown"])
                else "N/A",
            )
            col_c.metric(
                "Brier (mean)",
                f"{row['brier_mean']:0.4f}"
                if pd.notna(row["brier_mean"])
                else "N/A",
            )
            col_d.metric("Trades", int(row["n_trades"]))

        if not strat_sbm.empty:
            strat_sbm_plot = strat_sbm.copy()
            if not markets_meta.empty:
                strat_sbm_plot = strat_sbm_plot.merge(
                    markets_meta[["market_id", "name"]],
                    on="market_id",
                    how="left",
                    suffixes=("", "_market_name"),
                )
                strat_sbm_plot["market_label"] = strat_sbm_plot["market_id"]
                strat_sbm_plot.loc[~strat_sbm_plot["name"].isna(), "market_label"] = (
                    strat_sbm_plot["market_id"] + " – " + strat_sbm_plot["name"]
                )
            else:
                strat_sbm_plot["market_label"] = strat_sbm_plot["market_id"]

            fig_bar = px.bar(
                strat_sbm_plot,
                x="market_label",
                y="total_pnl",
                title=f"Per-Market P&L – {strat_choice}",
                hover_data=["brier_mean", "max_drawdown", "n_trades"],
            )
            fig_bar.update_layout(xaxis_title="", yaxis_title="Total P&L")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No per-market stats for this strategy under current filters.")

        if not strat_trades.empty:
            strat_trades = strat_trades.sort_values("entry_time")
            strat_trades["cum_pnl"] = strat_trades["pnl"].cumsum()

            col_left, col_right = st.columns(2)

            with col_left:
                fig_eq = px.line(
                    strat_trades,
                    x="entry_time",
                    y="cum_pnl",
                    color="market_id",
                    title=f"Equity Curve by Market – {strat_choice}",
                )
                fig_eq.update_layout(xaxis_title="Time", yaxis_title="Cumulative P&L")
                st.plotly_chart(fig_eq, use_container_width=True)

            with col_right:
                fig_trades = px.scatter(
                    strat_trades,
                    x="entry_time",
                    y="entry_price",
                    size="size",
                    color="market_id",
                    symbol="side",
                    title=f"Trades Over Time – {strat_choice}",
                    hover_data=["pnl", "p_hat", "outcome"],
                )
                fig_trades.update_layout(
                    xaxis_title="Time",
                    yaxis_title="Entry Price",
                )
                st.plotly_chart(fig_trades, use_container_width=True)

            st.markdown("**Raw trades for this strategy**")
            st.dataframe(
                strat_trades[
                    [
                        "market_id",
                        "entry_time",
                        "side",
                        "entry_price",
                        "size",
                        "p_hat",
                        "outcome",
                        "pnl",
                    ]
                ],
                use_container_width=True,
                height=300,
            )
        else:
            st.info("No trades for this strategy under current filters.")

# -------------------------------------------------------------------
# Performance Over Time tab
# -------------------------------------------------------------------

with tab_perf:
    st.subheader("Performance Over Time")

    if trades_filtered.empty:
        st.info("No trades available for the selected filters.")
    else:
        # ---------- FULL-SPAN GLOBAL EQUITY CURVES ----------
        st.markdown("**Global equity curves (all markets combined)**")

        # Work on a sorted copy
        perf_df = trades_filtered.copy().sort_values("entry_time")

        # Step 1: aggregate PnL per (time, strategy) – in case there are multiple trades
        step_df = (
            perf_df.groupby(["entry_time", "strategy_name"], as_index=False)["pnl"]
            .sum()
        )

        # Step 2: pivot to wide form: index=time, columns=strategy, values=pnl_at_that_time
        pivot = (
            step_df.pivot(index="entry_time", columns="strategy_name", values="pnl")
            .fillna(0.0)
        )

        # Step 3: cumulative sum down the index → full-span cumulative P&L per strategy
        eq_wide = pivot.cumsum()

        # Step 4: melt back to long form for plotting
        eq_global_long = (
            eq_wide.reset_index()
            .melt(
                id_vars="entry_time",
                var_name="strategy_name",
                value_name="cum_pnl_global",
            )
            .sort_values("entry_time")
        )

        # Optional: restrict to currently selected strategies (safety)
        if strategy_selection:
            eq_global_long = eq_global_long[
                eq_global_long["strategy_name"].isin(strategy_selection)
            ]

        # Plot global full-span curves
        fig_global = px.line(
            eq_global_long,
            x="entry_time",
            y="cum_pnl_global",
            color="strategy_name",
            title="Cumulative P&L Over Time – All Markets",
        )

        if not eq_global_long.empty:
            x_min = eq_global_long["entry_time"].min()
            x_max = eq_global_long["entry_time"].max()
        else:
            x_min = x_max = None

        fig_global.update_layout(
            xaxis_title="Time",
            yaxis_title="Cumulative P&L",
            xaxis_range=[x_min, x_max] if x_min is not None else None,
        )

        st.plotly_chart(fig_global, use_container_width=True)

        # ---------- FULL-SPAN PER-MARKET EQUITY CURVES ----------
        st.markdown("**Per-market equity curves**")

        if not all_markets:
            st.info("No markets available for per-market curves.")
        else:
            selected_markets_perf = st.multiselect(
                "Markets to show",
                options=all_markets,
                default=all_markets,
            )

            if selected_markets_perf:
                # We'll build a full-span equity curve per market, per strategy
                eq_market_list = []

                for m_id in selected_markets_perf:
                    perf_m = perf_df[perf_df["market_id"] == m_id]
                    if perf_m.empty:
                        continue

                    step_m = (
                        perf_m.groupby(["entry_time", "strategy_name"], as_index=False)[
                            "pnl"
                        ]
                        .sum()
                    )

                    pivot_m = (
                        step_m.pivot(
                            index="entry_time", columns="strategy_name", values="pnl"
                        )
                        .fillna(0.0)
                    )

                    eq_wide_m = pivot_m.cumsum()

                    eq_long_m = (
                        eq_wide_m.reset_index()
                        .melt(
                            id_vars="entry_time",
                            var_name="strategy_name",
                            value_name="cum_pnl_market",
                        )
                        .sort_values("entry_time")
                    )

                    eq_long_m["market_id"] = m_id

                    # Optional: filter to selected strategies
                    if strategy_selection:
                        eq_long_m = eq_long_m[
                            eq_long_m["strategy_name"].isin(strategy_selection)
                        ]

                    eq_market_list.append(eq_long_m)

                if eq_market_list:
                    perf_sub = pd.concat(eq_market_list, ignore_index=True)

                    fig_pm = px.line(
                        perf_sub,
                        x="entry_time",
                        y="cum_pnl_market",
                        color="strategy_name",
                        facet_col="market_id",
                        facet_col_wrap=2,
                        title="Cumulative P&L Over Time by Market",
                    )

                    fig_pm.update_layout(
                        xaxis_title="Time",
                        yaxis_title="Cumulative P&L",
                    )

                    # IMPORTANT: let each facet auto-scale its own axes
                    fig_pm.update_yaxes(matches=None)
                    fig_pm.update_xaxes(matches=None)

                    st.plotly_chart(fig_pm, use_container_width=True)
                else:
                    st.info("No trades in the selected markets for current filters.")
            else:
                st.info("Select at least one market to see per-market curves.")

# -------------------------------------------------------------------
# Live Trading tab (FIXED with Unique IDs for Timer)
# -------------------------------------------------------------------

with tab_live:
    # Always read timer directly from file (single source of truth)
    # This ensures frontend and backend are always in sync
    timer_start_time = get_persistent_start_time()
    
    # Store in session state for this render cycle only
    st.session_state.live_start_time = timer_start_time
    
    # Initialize session state for live trading config
    if "live_auto_refresh" not in st.session_state:
        st.session_state.live_auto_refresh = True
    if "last_refresh_time" not in st.session_state:
        st.session_state.last_refresh_time = time.time()
    if "refresh_interval" not in st.session_state:
        st.session_state.refresh_interval = 5
    
    # --- AUTO REFRESH LOGIC ---
    # Check for auto-refresh BEFORE rendering
    auto_refresh = st.session_state.live_auto_refresh
    if auto_refresh:
        current_time = time.time()
        time_since_refresh = current_time - st.session_state.last_refresh_time
        
        if time_since_refresh >= st.session_state.refresh_interval:
            st.session_state.last_refresh_time = current_time
            st.rerun()
    
    st.subheader("Live Trading Dashboard")
    
    # Control panel
    col_control1, col_control2, col_control3, col_control4 = st.columns(4)
    
    with col_control1:
        auto_refresh_checkbox = st.checkbox("🔄 Auto-refresh", value=st.session_state.live_auto_refresh)
        if auto_refresh_checkbox != st.session_state.live_auto_refresh:
            st.session_state.live_auto_refresh = auto_refresh_checkbox
            st.session_state.last_refresh_time = time.time()
            st.rerun()
    
    with col_control2:
        interval_options = [3, 5, 10, 15, 30, 60]
        current_interval = st.session_state.refresh_interval
        try:
            current_index = interval_options.index(current_interval)
        except ValueError:
            current_index = 1
        
        refresh_interval = st.selectbox(
            "Refresh interval",
            options=interval_options,
            index=current_index,
            format_func=lambda x: f"{x}s",
            key="refresh_interval_select"
        )
        if refresh_interval != st.session_state.refresh_interval:
            st.session_state.refresh_interval = refresh_interval
            st.session_state.last_refresh_time = time.time()
            st.rerun()
    
    with col_control3:
        if st.button("🔄 Refresh Now"):
            st.session_state.last_refresh_time = time.time()
            st.rerun()
    
    with col_control4:
        if st.button("⏱️ Reset Timer"):
            new_start = datetime.now(timezone.utc)
            save_timer_state(new_start)  # Save to file (single source of truth)
            st.session_state.last_refresh_time = time.time()
            st.rerun()
    
    # Auto-refresh status display
    refresh_status_placeholder = st.empty()
    if auto_refresh:
        current_time = time.time()
        time_since_refresh = current_time - st.session_state.last_refresh_time
        time_until_refresh = max(0, st.session_state.refresh_interval - time_since_refresh)
        
        refresh_status_placeholder.info(
            f"🔄 Auto-refreshing every {st.session_state.refresh_interval}s. "
            f"Next refresh in {int(time_until_refresh)}s | "
            f"Last update: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
    else:
        refresh_status_placeholder.empty()
    
    # Timer Logic - Always use the timer from file (single source of truth)
    # Re-read from file to ensure we have the latest state (in case backend updated it)
    timer_start_time = get_persistent_start_time()
    
    # Check if expired and reset if needed
    elapsed_check = datetime.now(timezone.utc) - timer_start_time
    elapsed_seconds_check = elapsed_check.total_seconds()
    
    # If timer expired (>= 24 hours) or is negative (timezone issue), reset it
    if elapsed_seconds_check >= 86400 or elapsed_seconds_check < 0:
        new_start = datetime.now(timezone.utc)
        save_timer_state(new_start)
        timer_start_time = new_start
        st.info("⏱️ Timer expired. Starting new 24-hour session.")
        # Force rerun to use the new timer
        st.rerun()
    
    # --- TIMER DISPLAY - Always sync with backend timer file ---
    # Calculate Unix timestamp in milliseconds for JavaScript (from shared timer file)
    start_time_unix = int(timer_start_time.timestamp() * 1000)
    
    # Calculate remaining time for display
    elapsed_for_display = datetime.now(timezone.utc) - timer_start_time
    remaining_seconds_display = max(0, 86400 - elapsed_for_display.total_seconds())
    hours_display = int(remaining_seconds_display // 3600)
    minutes_display = int((remaining_seconds_display % 3600) // 60)
    seconds_display = int(remaining_seconds_display % 60)
    progress_display = min(100, (elapsed_for_display.total_seconds() / 86400) * 100)
    
    # Show timer status
    st.info(f"⏱️ **Competition Timer**: Started at {timer_start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC | "
            f"Remaining: ~{hours_display}h {minutes_display}m | "
            f"Timer file: `{TIMER_STATE_FILE.name}`")
    
    # Generate a unique ID for this specific render
    timer_uid = str(uuid.uuid4())
    
    # Use Streamlit components for reliable JavaScript execution
    timer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            .timer-container {{
                margin: 20px 0;
                font-family: Arial, sans-serif;
            }}
            .timer-display {{
                display: flex;
                gap: 20px;
                justify-content: center;
            }}
            .timer-item {{
                text-align: center;
            }}
            .timer-label {{
                font-size: 14px;
                color: #666;
                margin-bottom: 5px;
            }}
            .timer-value {{
                font-size: 32px;
                font-weight: bold;
                color: #1f77b4;
            }}
            .progress-container {{
                margin-top: 20px;
            }}
            .progress-label {{
                font-size: 12px;
                color: #666;
                margin-bottom: 5px;
            }}
            .progress-bar-bg {{
                width: 100%;
                background-color: #f0f0f0;
                border-radius: 10px;
                height: 20px;
                overflow: hidden;
            }}
            .progress-bar-fill {{
                height: 100%;
                background-color: #1f77b4;
                transition: width 1s linear;
            }}
            .progress-text {{
                text-align: center;
                margin-top: 5px;
                font-size: 12px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="timer-container">
            <div class="timer-display">
                <div class="timer-item">
                    <div class="timer-label">Hours</div>
                    <div class="timer-value" id="hours-{timer_uid}">{hours_display:02d}</div>
                </div>
                <div class="timer-item">
                    <div class="timer-label">Minutes</div>
                    <div class="timer-value" id="minutes-{timer_uid}">{minutes_display:02d}</div>
                </div>
                <div class="timer-item">
                    <div class="timer-label">Seconds</div>
                    <div class="timer-value" id="seconds-{timer_uid}">{seconds_display:02d}</div>
                </div>
            </div>
            <div class="progress-container">
                <div class="progress-label">Session Progress</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="progress-bar-{timer_uid}" style="width: {progress_display}%;"></div>
                </div>
                <div class="progress-text" id="progress-text-{timer_uid}">{progress_display:.1f}%</div>
            </div>
        </div>
        <script>
        (function() {{
            const startTimeMs = {start_time_unix};
            const totalDurationMs = 86400000;
            
            function updateTimer() {{
                const elHours = document.getElementById('hours-{timer_uid}');
                const elMinutes = document.getElementById('minutes-{timer_uid}');
                const elSeconds = document.getElementById('seconds-{timer_uid}');
                const elProgress = document.getElementById('progress-bar-{timer_uid}');
                const elText = document.getElementById('progress-text-{timer_uid}');
                
                if (!elHours || !elMinutes || !elSeconds) {{
                    setTimeout(updateTimer, 100);
                    return;
                }}
                
                const now = Date.now();
                const elapsed = now - startTimeMs;
                const remaining = Math.max(0, totalDurationMs - elapsed);
                
                if (remaining <= 0) {{
                    elHours.textContent = '00';
                    elMinutes.textContent = '00';
                    elSeconds.textContent = '00';
                    if (elProgress) elProgress.style.width = '100%';
                    if (elText) elText.textContent = '100.0% - Session Complete';
                    return;
                }}
                
                const hours = Math.floor(remaining / 3600000);
                const minutes = Math.floor((remaining % 3600000) / 60000);
                const secs = Math.floor((remaining % 60000) / 1000);
                
                elHours.textContent = String(hours).padStart(2, '0');
                elMinutes.textContent = String(minutes).padStart(2, '0');
                elSeconds.textContent = String(secs).padStart(2, '0');
                
                const progress = (elapsed / totalDurationMs) * 100;
                if (elProgress) elProgress.style.width = Math.min(100, progress) + '%';
                if (elText) elText.textContent = Math.min(100, progress).toFixed(1) + '%';
            }}
            
            // Start immediately
            updateTimer();
            setInterval(updateTimer, 1000);
        }})();
        </script>
    </body>
    </html>
    """
    
    components.html(timer_html, height=200)
    
    # Load live data
    DATA_LIVE_DIR = BASE_DIR / "data_live"
    LOGS_LIVE_DIR = BASE_DIR / "logs_live"
    
    live_meta_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    live_trades_path = LOGS_LIVE_DIR / "live_trades.csv"
    
    if not live_meta_path.exists():
        st.warning("No live market data found. Run `python fetch_polymarket_live_24h.py` first, then start the live data service.")
        st.code("python live_data_service.py --interval 60")
    else:
        # Load live markets
        try:
            live_markets_meta = read_csv_if_exists(live_meta_path)
            live_trades_df = read_csv_if_exists(
                live_trades_path,
                parse_dates=["entry_time"]
            )
            
            if live_markets_meta.empty:
                st.warning("No live markets configured.")
            else:
                # Live market status
                st.markdown("### Live Markets")
                
                # Group by event_slug (preferred) or slug
                group_col = "event_slug" if "event_slug" in live_markets_meta.columns else "slug"
                
                if group_col in live_markets_meta.columns:
                    grouped = live_markets_meta.groupby(group_col)
                    for group_name, group in grouped:
                        # Use group name as header
                        header_name = str(group_name).replace("-", " ").title()
                        
                        # Sort group by outcome probability desc
                        if "outcome" in group.columns:
                            group["outcome_val"] = pd.to_numeric(group["outcome"], errors="coerce").fillna(0)
                            group = group.sort_values("outcome_val", ascending=False)
                        
                        with st.expander(f"{header_name} ({len(group)} outcomes)", expanded=True):
                            market_cols = st.columns(min(4, len(group)))
                            for idx, (_, market) in enumerate(group.iterrows()):
                                with market_cols[idx % len(market_cols)]:
                                    outcome = float(market.get("outcome", 0)) if market.get("outcome") else 0.0
                                    # Use Question/Outcome name
                                    name = market.get("name", market.get("market_id", "Unknown"))
                                    # Truncate long names but keep them identifiable
                                    if "will-the-" in name.lower():
                                        name = name.lower().replace("will-the-", "").replace("-win-super-bowl-2026", "").title()
                                    elif "will-" in name.lower():
                                        name = name.lower().replace("will-", "").replace("-win-the-chilean-presidential-election", "").title()
                                        
                                    st.metric(
                                        name[:40],
                                        f"{outcome:.3f}",
                                        delta=None,
                                        help=f"Last updated: {market.get('last_updated', 'N/A')}"
                                    )
                else:
                    # Fallback if no slug
                    market_cols = st.columns(min(5, len(live_markets_meta)))
                    for idx, (_, market) in enumerate(live_markets_meta.iterrows()):
                        with market_cols[idx % len(market_cols)]:
                            outcome = float(market.get("outcome", 0)) if market.get("outcome") else 0.0
                            st.metric(
                                market.get("name", market.get("market_id", "Unknown"))[:30],
                                f"{outcome:.3f}",
                                delta=None,
                            )
                
                # Live trades feed
                st.markdown("### Recent Trades")
                
                if live_trades_df.empty:
                    st.info("No trades yet. Waiting for strategies to generate trades...")
                else:
                    # Process trades
                    for col in ["entry_price", "size", "p_hat", "outcome", "pnl", "capital_at_entry"]:
                        if col in live_trades_df.columns:
                            live_trades_df[col] = pd.to_numeric(live_trades_df[col], errors="coerce")
                    
                    # Show last 20 trades
                    recent_trades = live_trades_df.tail(20).sort_values("entry_time", ascending=False)
                    
                    # Trade feed table
                    st.dataframe(
                        recent_trades[
                            ["strategy_name", "market_id", "entry_time", "side", "entry_price", "pnl", "capital_at_entry"]
                        ],
                        use_container_width=True,
                        height=400,
                    )
                    
                    # Strategy performance
                    st.markdown("### Strategy Performance (Live)")
                    
                    if not live_trades_df.empty:
                        # Calculate cumulative P&L per strategy
                        live_trades_sorted = live_trades_df.sort_values("entry_time")
                        strategy_perf = []
                        
                        for strategy in live_trades_sorted["strategy_name"].unique():
                            strat_trades = live_trades_sorted[live_trades_sorted["strategy_name"] == strategy]
                            total_pnl = strat_trades["pnl"].sum()
                            n_trades = len(strat_trades)
                            # Calculate current capital
                            if len(strat_trades) > 0:
                                last_capital = strat_trades["capital_at_entry"].iloc[-1]
                                last_pnl = strat_trades["pnl"].iloc[-1]
                                current_capital = last_capital + last_pnl
                            else:
                                current_capital = 100.0
                            
                            strategy_perf.append({
                                "strategy_name": strategy,
                                "total_pnl": total_pnl,
                                "current_capital": current_capital,
                                "n_trades": n_trades,
                            })
                        
                        perf_df = pd.DataFrame(strategy_perf)
                        perf_df = perf_df.sort_values("total_pnl", ascending=False)
                        
                        # Performance metrics
                        perf_cols = st.columns(4)
                        with perf_cols[0]:
                            st.metric("Total Strategies", len(perf_df))
                        with perf_cols[1]:
                            st.metric("Total Trades", int(perf_df["n_trades"].sum()))
                        with perf_cols[2]:
                            st.metric("Total P&L", f"{perf_df['total_pnl'].sum():.3f}")
                        with perf_cols[3]:
                            best_strat = perf_df.iloc[0]["strategy_name"] if not perf_df.empty else "N/A"
                            st.metric("Best Strategy", best_strat[:20])
                        
                        # Leaderboard
                        st.dataframe(
                            perf_df,
                            use_container_width=True,
                            height=300,
                        )
                        
                        # Live equity curves
                        st.markdown("### Live Equity Curves")
                        
                        live_trades_sorted["cum_pnl"] = live_trades_sorted.groupby("strategy_name")["pnl"].cumsum()
                        
                        fig_live = px.line(
                            live_trades_sorted,
                            x="entry_time",
                            y="cum_pnl",
                            color="strategy_name",
                            title="Cumulative P&L Over Time (Live)",
                        )
                        fig_live.update_layout(
                            xaxis_title="Time",
                            yaxis_title="Cumulative P&L",
                        )
                        st.plotly_chart(fig_live, use_container_width=True)
                        
                        # Per-strategy breakdown
                        st.markdown("### Per-Strategy Breakdown")
                        
                        selected_live_strategy = st.selectbox(
                            "Select strategy",
                            options=perf_df["strategy_name"].tolist(),
                            key="live_strategy_select",
                        )
                        
                        if selected_live_strategy:
                            strat_trades_live = live_trades_sorted[
                                live_trades_sorted["strategy_name"] == selected_live_strategy
                            ]
                            
                            if not strat_trades_live.empty:
                                col_live1, col_live2 = st.columns(2)
                                
                                with col_live1:
                                    fig_strat_pnl = px.line(
                                        strat_trades_live,
                                        x="entry_time",
                                        y="cum_pnl",
                                        title=f"{selected_live_strategy} - Equity Curve",
                                    )
                                    fig_strat_pnl.update_layout(
                                        xaxis_title="Time",
                                        yaxis_title="Cumulative P&L",
                                    )
                                    st.plotly_chart(fig_strat_pnl, use_container_width=True)
                                
                                with col_live2:
                                    fig_strat_trades = px.scatter(
                                        strat_trades_live,
                                        x="entry_time",
                                        y="entry_price",
                                        size="size",
                                        color="pnl",
                                        symbol="side",
                                        title=f"{selected_live_strategy} - Trades",
                                        color_continuous_scale="RdYlGn",
                                    )
                                    fig_strat_trades.update_layout(
                                        xaxis_title="Time",
                                        yaxis_title="Entry Price",
                                    )
                                    st.plotly_chart(fig_strat_trades, use_container_width=True)
        except Exception as e:
            st.error(f"Error loading live data: {e}")
            
    # Note: Auto-refresh logic is handled at the top of this tab block via st.rerun()
    # No extra JS injection needed for reloading the page.