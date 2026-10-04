"""Day 2: backtest 99% 1-day VaR models over the last 250 days (or more).

Usage:
    python run_backtest.py               # last 250 days (Basel standard)
    python run_backtest.py --days 2000   # longer history, includes the 2020 COVID crash
    python run_backtest.py --synthetic   # offline test
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from risk_engine import config as C
from risk_engine.backtest import (backtest, ewma_var, rolling_historical_var,
                                  rolling_parametric_var)
from risk_engine.data import compute_returns, load_prices, synthetic_prices
from risk_engine.var import portfolio_pnl

OUT = Path(__file__).resolve().parent / "outputs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--days", type=int, default=C.BACKTEST_DAYS)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    tickers = list(C.PORTFOLIO)
    if args.synthetic:
        prices = synthetic_prices(tickers, seed=C.SEED)
    else:
        prices = load_prices(tickers, C.START_DATE, C.END_DATE,
                             reference=C.REFERENCE_TICKER, refresh=args.refresh)
    positions = {t: C.PORTFOLIO[t] for t in prices.columns}
    pnl = portfolio_pnl(compute_returns(prices), positions)   # full history

    a, W = C.CONFIDENCE, C.WINDOW
    forecasts = {
        f"Historical ({W}d)": rolling_historical_var(pnl, W, a),
        f"Parametric ({W}d)": rolling_parametric_var(pnl, W, a),
        f"EWMA (lambda={C.EWMA_LAMBDA})": ewma_var(pnl, C.EWMA_LAMBDA, a),
    }

    # Backtest only the last N days, and only days where every model has a forecast.
    start = max(f.first_valid_index() for f in forecasts.values())
    test_pnl = pnl.loc[start:].tail(args.days)
    print(f"Backtest period: {test_pnl.index[0].date()} to {test_pnl.index[-1].date()} "
          f"({len(test_pnl)} days), {a:.0%} 1-day VaR\n")

    rows, daily = [], {}
    for name, f in forecasts.items():
        s, df = backtest(test_pnl, f.loc[test_pnl.index], a)
        rows.append({"Model": name, **s})
        daily[name] = df

    table = pd.DataFrame(rows).set_index("Model")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(table[["Days", "Exceptions", "Expected", "Basel zone", "Capital multiplier"]])
        print()
        print(table[["Kupiec LR", "Kupiec p-value", "Kupiec result",
                     "Indep. LR", "Indep. p-value", "Indep. result"]])

    # List the exception days: in a real risk team, each one gets investigated.
    hist_name = next(iter(forecasts))
    exc = daily[hist_name].query("exception")[["pnl", "var"]].rename(
        columns={"pnl": "Actual P&L", "var": "VaR forecast"})
    exc["Excess loss"] = -exc["Actual P&L"] - exc["VaR forecast"]
    print(f"\nException days ({hist_name}):")
    print(exc.round(0).to_string() if len(exc) else "  none")

    table.to_csv(OUT / f"backtest_summary_{args.days}d.csv")
    exc.to_csv(OUT / f"backtest_exceptions_{args.days}d.csv", float_format="%.2f")

    # Plot: actual P&L vs -VaR, exceptions marked
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(test_pnl.index, test_pnl, width=1.0, color="#b8c7d9", label="Actual daily P&L")
    colors = ["#c0392b", "#2c3e50", "#27ae60"]
    for (name, df), col in zip(daily.items(), colors):
        ax.plot(df.index, -df["var"], color=col, linewidth=1.3, label=f"-VaR: {name}")
    hits = daily[hist_name].query("exception")
    ax.scatter(hits.index, hits["pnl"], color="#c0392b", zorder=5, s=28,
               label=f"Exceptions, historical ({len(hits)})")
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title(f"VaR backtest: actual P&L vs {a:.0%} 1-day VaR ({len(test_pnl)} days)")
    ax.set_ylabel("P&L (INR)")
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
    fig.tight_layout()
    fig.savefig(OUT / f"backtest_{args.days}d.png", dpi=150)
    print(f"\nSaved results and chart to {OUT}/")


if __name__ == "__main__":
    main()
