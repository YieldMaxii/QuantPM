from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

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

if scores.empty and scores_by_market.empty and trades.empty:
    st.error(
        "No data found. Make sure you've run the engine and evaluator so that "
        "outputs/scores*.csv and outputs/trades*.csv exist."
    )
    st.stop()

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

tab_leaderboard, tab_per_market, tab_strategy, tab_perf = st.tabs(
    ["Leaderboard", "Per Market", "Strategy Detail", "Performance Over Time"]
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
