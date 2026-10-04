"""Day 3b: initial margin for the client's portfolio, collateral check and margin call.

Usage:
    python run_margin.py
    python run_margin.py --synthetic
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from risk_engine import scenarios as S
from risk_engine.common import get_prices_and_positions, inr, parse_args
from risk_engine.margin import (collateral_table, im_by_asset_class, im_calibrations,
                                margin_call, rolling_im)

OUT = Path(__file__).resolve().parent / "outputs"


def main():
    args = parse_args()
    OUT.mkdir(exist_ok=True)
    prices, positions = get_prices_and_positions(args)
    total = sum(positions.values())
    a, mpor, W = S.IM_CONFIDENCE, S.MPOR, S.IM_RECENT_WINDOW

    # 1. IM under different calibrations
    cal = im_calibrations(prices, positions, mpor, a, W, S.STRESS_PERIOD, S.APC_STRESS_WEIGHT)
    print(f"Portfolio: {inr(total)}  |  {a:.0%} IM over a {mpor}-day margin period of risk\n")
    print("Initial margin by calibration:")
    for k, v in cal.items():
        print(f"  {k:<34} {inr(v):>12}   ({100 * v / total:.1f}% of portfolio)")

    # 2. IM by asset class
    by_class, netted = im_by_asset_class(prices, positions, mpor, a, W)
    print("\nIM by asset class (recent calibration):")
    for k, v in by_class.items():
        print(f"  {k:<34} {inr(v):>12}")
    print(f"  {'Sum across classes (no netting)':<34} {inr(by_class.sum()):>12}")
    print(f"  {'Whole portfolio (full netting)':<34} {inr(netted):>12}")
    print(f"  {'Netting benefit':<34} {inr(by_class.sum() - netted):>12}")

    # 3. Collateral and margin call
    coll = collateral_table(S.COLLATERAL)
    posted = coll["Value after haircut"].sum()
    required = cal[f"APC blend ({S.APC_STRESS_WEIGHT:.0%} stressed)"]
    call = margin_call(required, posted)
    print("\nCollateral posted:")
    print(coll.to_string(formatters={"Market value": "{:,.0f}".format, "Haircut": "{:.0%}".format,
                                     "Value after haircut": "{:,.0f}".format}))
    print(f"\nIM required (APC blend): {inr(required)}")
    print(f"Collateral after haircuts: {inr(posted)}")
    if call > 0:
        print(f"MARGIN CALL: client must post {inr(call)} more collateral")
    else:
        print(f"Excess collateral: {inr(-call)} (no margin call)")

    # Same collateral, but in a COVID-style stress the Nifty ETF collateral falls too (wrong-way risk)
    stressed_im = cal["Stressed (2020)"]
    stress_required = max(required, stressed_im) if not pd.isna(stressed_im) else required
    nifty_drop = 0.30
    coll_stress = coll.copy()
    coll_stress.loc["Nifty 50 ETF units", "Value after haircut"] *= (1 - nifty_drop)
    posted_stress = coll_stress["Value after haircut"].sum()
    call_stress = margin_call(stress_required, posted_stress)
    print(f"\nStress case: IM rises to {inr(stress_required)} and the Nifty ETF collateral falls "
          f"{nifty_drop:.0%}, so collateral after haircuts drops to {inr(posted_stress)}.")
    if call_stress > 0:
        print(f"  MARGIN CALL of {inr(call_stress)} -- collateral weakens exactly when IM rises "
              f"(wrong-way risk).")
    else:
        print(f"  Still covered, with {inr(-call_stress)} excess (down from {inr(-call)} today).")

    summary = pd.Series({**cal, "Sum by class": by_class.sum(), "Netted": netted,
                         "Collateral after haircut": posted, "Margin call (today)": max(call, 0),
                         "IM (stress)": stress_required, "Margin call (stress)": max(call_stress, 0)}, name="INR")
    summary.to_csv(OUT / "margin_summary.csv", float_format="%.2f")

    # 4. Chart: how IM moves through time (procyclicality)
    roll = rolling_im(prices, positions, mpor, a, W).dropna()
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(roll.index, roll, color="#c0392b", linewidth=1.4, label=f"IM, rolling {W}-day calibration")
    if not pd.isna(stressed_im):
        apc = roll.where(roll > stressed_im,
                         (1 - S.APC_STRESS_WEIGHT) * roll + S.APC_STRESS_WEIGHT * stressed_im)
        ax.plot(apc.index, apc, color="#2c3e50", linewidth=1.4,
                label=f"IM with anti-procyclicality ({S.APC_STRESS_WEIGHT:.0%} stressed weight)")
        ax.axvspan(pd.Timestamp(S.STRESS_PERIOD[0]), pd.Timestamp(S.STRESS_PERIOD[1]),
                   color="#f2d7d5", alpha=0.5, label="Stressed calibration period")
    ax.set_ylabel("Initial margin (INR)")
    ax.set_title(f"Initial margin over time: {a:.0%}, {mpor}-day MPOR")
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
    fig.tight_layout()
    fig.savefig(OUT / "margin_over_time.png", dpi=150)
    print(f"\nSaved results and chart to {OUT}/")


if __name__ == "__main__":
    main()
