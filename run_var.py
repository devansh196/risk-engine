"""Day 1: compute 1-day and 10-day 99% VaR and ES three ways.

Usage:
    python run_var.py               # real data from Yahoo Finance
    python run_var.py --synthetic   # fake data, works offline
    python run_var.py --refresh     # re-download prices
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from risk_engine import config as C
from risk_engine.data import compute_returns, load_prices, synthetic_prices
from risk_engine.var import (historical_var_es, monte_carlo_var_es, parametric_var_es,
                             portfolio_pnl, scale_to_horizon, standalone_vs_diversified)

OUT = Path(__file__).resolve().parent / "outputs"


def inr(x):
    return f"Rs {x:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    # 1. Data
    tickers = list(C.PORTFOLIO)
    if args.synthetic:
        prices = synthetic_prices(tickers, seed=C.SEED)
    else:
        prices = load_prices(tickers, C.START_DATE, C.END_DATE,
                             reference=C.REFERENCE_TICKER, refresh=args.refresh)
    positions = {t: C.PORTFOLIO[t] for t in prices.columns}

    returns = compute_returns(prices).tail(C.WINDOW)   # last ~2 years only
    pnl = portfolio_pnl(returns, positions)
    total = sum(positions.values())

    print(f"Portfolio value: {inr(total)} across {len(positions)} assets")
    print(f"Window: {returns.index[0].date()} to {returns.index[-1].date()} ({len(returns)} days)")
    print(f"Daily P&L std dev: {inr(pnl.std())}  |  worst day: {inr(pnl.min())}\n")

    # 2. VaR and ES, three ways
    a = C.CONFIDENCE
    h_var, h_es = historical_var_es(pnl, a)
    p_var, p_es, _ = parametric_var_es(returns, positions, a)
    mn_var, mn_es, sim_n = monte_carlo_var_es(returns, positions, a, C.MC_SIMULATIONS, "normal", seed=C.SEED)
    mt_var, mt_es, _ = monte_carlo_var_es(returns, positions, a, C.MC_SIMULATIONS, "t", C.MC_T_DOF, C.SEED)

    rows = []
    for name, var, es in [("Historical", h_var, h_es),
                          ("Parametric (normal)", p_var, p_es),
                          ("Monte Carlo (normal)", mn_var, mn_es),
                          (f"Monte Carlo (Student-t, dof={C.MC_T_DOF})", mt_var, mt_es)]:
        row = {"Method": name}
        for d in C.HORIZONS:
            row[f"VaR {d}d"] = scale_to_horizon(var, d)
            row[f"ES {d}d"] = scale_to_horizon(es, d)
        row["VaR 1d % of portfolio"] = 100 * var / total
        rows.append(row)
    table = pd.DataFrame(rows).set_index("Method")

    with pd.option_context("display.float_format", "{:,.0f}".format, "display.width", 140):
        print(f"{a:.0%} VaR and Expected Shortfall (INR)")
        print(table.drop(columns="VaR 1d % of portfolio"))
    print()

    # 3. Diversification benefit
    standalone, diversified = standalone_vs_diversified(returns, positions, a)
    print(f"Sum of standalone 1-day VaRs: {inr(standalone.sum())}")
    print(f"Diversified portfolio VaR:    {inr(diversified)}")
    print(f"Diversification benefit:      {inr(standalone.sum() - diversified)} "
          f"({100 * (1 - diversified / standalone.sum()):.1f}%)")

    table.to_csv(OUT / "var_summary.csv", float_format="%.2f")
    standalone.rename("standalone_var_1d").to_csv(OUT / "standalone_var.csv", float_format="%.2f")

    # 4. Plot: historical P&L distribution with the VaR lines
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(pnl, bins=60, color="#9bb7d4", edgecolor="white", density=True, label="Historical daily P&L")
    for x, lbl, col in [(-h_var, "Historical VaR", "#c0392b"),
                        (-p_var, "Parametric VaR", "#2c3e50"),
                        (-mt_var, "MC Student-t VaR", "#8e44ad")]:
        ax.axvline(x, color=col, linestyle="--", linewidth=1.5, label=f"{lbl}: {inr(-x)}")
    ax.axvline(-h_es, color="#c0392b", linestyle=":", linewidth=1.5, label=f"Historical ES: {inr(h_es)}")
    ax.set_title(f"Portfolio daily P&L and {a:.0%} 1-day VaR ({len(returns)}-day window)")
    ax.set_xlabel("Daily P&L (INR)")
    ax.set_ylabel("Density")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "pnl_distribution.png", dpi=150)
    print(f"\nSaved results and chart to {OUT}/")


if __name__ == "__main__":
    main()
