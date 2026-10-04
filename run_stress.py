"""Day 3a: stress test today's portfolio with historical and hypothetical scenarios.

Usage:
    python run_stress.py
    python run_stress.py --synthetic
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from risk_engine import config as C
from risk_engine import scenarios as S
from risk_engine.common import get_prices_and_positions, inr, parse_args
from risk_engine.data import compute_returns
from risk_engine.stress import historical_scenario, hypothetical_scenario, worst_historical_window
from risk_engine.var import historical_var_es, portfolio_pnl

OUT = Path(__file__).resolve().parent / "outputs"


def main():
    args = parse_args()
    OUT.mkdir(exist_ok=True)
    prices, positions = get_prices_and_positions(args)
    total = sum(positions.values())

    # Reference point: today's 10-day 99% VaR (historical, sqrt-of-time)
    pnl = portfolio_pnl(compute_returns(prices).tail(C.WINDOW), positions)
    var10 = historical_var_es(pnl, C.CONFIDENCE)[0] * np.sqrt(10)

    rows, breakdown = [], {}

    def add(name, kind, res, period=""):
        p = res["asset_pnl"]
        worst = p.idxmin()
        rows.append({"Scenario": name, "Type": kind, "Period": period,
                     "P&L": p.sum(), "% of portfolio": 100 * p.sum() / total,
                     "x 10d VaR": -p.sum() / var10 if p.sum() < 0 else 0.0,
                     "Biggest loser": f"{worst} ({inr(p[worst])})"})
        breakdown[name] = p

    for name, (start, end) in S.HISTORICAL_SCENARIOS.items():
        res = historical_scenario(prices, positions, start, end)
        if res is None:
            print(f"[skip] {name}: dates not in data")
            continue
        add(name, "Historical", res, f"{res['start'].date()} to {res['end'].date()}")

    s, e = worst_historical_window(prices, positions, 10)
    add("Worst 10 days in history", "Historical", historical_scenario(prices, positions, s, e),
        f"{s.date()} to {e.date()}")

    for name, shocks in S.HYPOTHETICAL_SCENARIOS.items():
        add(name, "Hypothetical", hypothetical_scenario(positions, shocks))

    table = pd.DataFrame(rows).set_index("Scenario").sort_values("P&L")
    print(f"Portfolio: {inr(total)}  |  today's 99% 10-day VaR (historical): {inr(var10)}\n")
    with pd.option_context("display.width", 220, "display.max_colwidth", 40):
        print(table.to_string(formatters={"P&L": "{:,.0f}".format, "% of portfolio": "{:.1f}".format,
                                          "x 10d VaR": "{:.1f}".format}))

    detail = pd.DataFrame(breakdown).T.loc[table.index]
    detail["TOTAL"] = detail.sum(axis=1)
    print("\nP&L by asset in each scenario (INR):")
    with pd.option_context("display.width", 220):
        print(detail.round(0).to_string(float_format="{:,.0f}".format))

    table.to_csv(OUT / "stress_summary.csv", float_format="%.2f")
    detail.to_csv(OUT / "stress_by_asset.csv", float_format="%.2f")

    # Chart: scenario losses vs 10-day VaR
    fig, ax = plt.subplots(figsize=(10, 0.45 * len(table) + 1.5))
    colors = ["#c0392b" if t == "Historical" else "#e08e45" for t in table["Type"]]
    ax.barh(table.index, table["P&L"], color=colors)
    ax.axvline(-var10, color="#2c3e50", linestyle="--", linewidth=1.5, label=f"-99% 10-day VaR ({inr(var10)})")
    ax.axvline(0, color="black", linewidth=0.6)
    for y, v in enumerate(table["P&L"]):
        ax.text(v, y, f" {v / 1000:,.0f}k ", va="center", ha="right" if v < 0 else "left", fontsize=8)
    lo, hi = min(table["P&L"].min(), -var10), max(table["P&L"].max(), 0)
    ax.set_xlim(lo * 1.15, hi * 1.25 + 0.02 * abs(lo))
    ax.invert_yaxis()
    ax.set_xlabel("Scenario P&L on today's portfolio (INR)")
    ax.set_title("Stress tests: historical (red) and hypothetical (orange) scenarios")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "stress_scenarios.png", dpi=150)
    print(f"\nSaved results and chart to {OUT}/")


if __name__ == "__main__":
    main()
