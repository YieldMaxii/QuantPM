"""
Evaluate external strategy trade logs using the engine.

Usage example:

    python evaluate_trade_logs.py \
        --meta data/markets_meta.csv \
        --prices-dir data \
        --log-file logs/example_strategy_trades.csv \
        --out-dir outputs \
        --bankroll 100.0

Input trade log CSV must have columns:
    strategy_name,market_id,entry_index,side,size,p_hat

The engine ignores any price/outcome fields in the log; it uses canonical
prices from prices_{market_id}.csv and outcomes from markets_meta.csv.
"""

import argparse
import csv
from pathlib import Path
from typing import List

from engine import (
    MarketSeries,
    StrategyDecision,
    TradeRecord,
    StrategyScores,
    StrategyMarketScores,
    load_markets,
    evaluate_trade_log,
    write_trades_csv,
    write_scores_csv,
    compute_scores_by_market,
    write_scores_by_market_csv,
)


def read_trade_log(log_path: Path) -> List[StrategyDecision]:
    """
    Read a trade log CSV into a list of StrategyDecision objects.

    Expected columns:
        strategy_name,market_id,entry_index,side,size,p_hat

    You can extend this format later (e.g., add an optional 'tag' column),
    but this is enough for the POC.
    """
    decisions: List[StrategyDecision] = []

    with log_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            strategy_name = row["strategy_name"]
            market_id = row["market_id"]
            entry_index = int(row["entry_index"])
            side = row["side"].strip().upper()
            size = float(row["size"])
            p_hat = float(row["p_hat"]) if row.get("p_hat") not in (None, "") else 0.5

            if side not in ("BUY_YES", "SELL_YES"):
                # Skip invalid sides
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name=strategy_name,
                    market_id=market_id,
                    entry_index=entry_index,
                    side=side,
                    size=size,
                    p_hat=p_hat,
                )
            )

    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate external strategy trade logs using engine.py"
    )
    parser.add_argument("--meta", type=str, required=True, help="markets_meta.csv path")
    parser.add_argument(
        "--prices-dir",
        type=str,
        required=True,
        help="directory with prices_<market_id>.csv files",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        required=True,
        help="trade log CSV file (strategy_name,market_id,entry_index,side,size,p_hat)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        required=True,
        help="output directory for evaluated trades/scores",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=100.0,
        help="reference bankroll used for sizing (default: 100.0)",
    )
    args = parser.parse_args()

    meta_csv = Path(args.meta)
    prices_dir = Path(args.prices_dir)
    log_path = Path(args.log_file)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load markets
    markets = load_markets(meta_csv, prices_dir)

    # 2. Load trade log
    trade_specs = read_trade_log(log_path)

    # 3. Evaluate
    trades, scores = evaluate_trade_log(markets, trade_specs, bankroll=args.bankroll)

    # 4. Write outputs
    write_trades_csv(trades, out_dir / "trades_from_logs.csv")
    write_scores_csv(scores, out_dir / "scores_from_logs.csv")

    # Per-strategy, per-market scores from log evaluation
    scores_by_market = compute_scores_by_market(trades)
    write_scores_by_market_csv(
        scores_by_market,
        out_dir / "scores_by_market_from_logs.csv",
    )

    print(f"Wrote {len(trades)} evaluated trades to {out_dir/'trades_from_logs.csv'}")
    print(f"Wrote {len(scores)} strategy scores to {out_dir/'scores_from_logs.csv'}")
    print(
        f"Wrote {len(scores_by_market)} per-market strategy scores to "
        f"{out_dir/'scores_by_market_from_logs.csv'}"
    )


if __name__ == "__main__":
    main()

