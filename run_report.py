"""Day 4: generate the daily risk & margin report as an Excel workbook.

Usage:
    python run_report.py                    # report for the latest date
    python run_report.py --date 2020-03-23  # report for any past date (e.g. the COVID crash)
    python run_report.py --synthetic
"""
from pathlib import Path

import pandas as pd

from risk_engine import scenarios as S
from risk_engine.common import get_prices_and_positions, parse_args
from risk_engine.excel import write_report
from risk_engine.margin import im_by_asset_class
from risk_engine.report import (VAR_LIMIT, backtest_status, collateral_units_on, commentary,
                                snapshot, stress_table, units_on, var_history)

OUT = Path(__file__).resolve().parent / "outputs"


def main():
    args = parse_args(lambda ap: ap.add_argument("--date", help="report date YYYY-MM-DD (default: latest)"))
    OUT.mkdir(exist_ok=True)
    prices, _ = get_prices_and_positions(args)

    # Report date T = last trading day on or before --date; T-1 = the trading day before it.
    if args.date:
        pos = prices.index.searchsorted(pd.Timestamp(args.date), side="right") - 1
        if pos < 1:
            raise SystemExit(f"No data on or before {args.date}")
        prices = prices.iloc[:pos + 1]
    d_t, d_y = prices.index[-1], prices.index[-2]

    units = units_on(prices, d_t)
    coll_units = collateral_units_on(prices, d_t)
    t = snapshot(prices, units, coll_units)
    y = snapshot(prices.loc[:d_y], units, coll_units)

    asset_pnl = units * (t["prices"] - y["prices"])
    pnl_series, history = var_history(prices, units)
    bt_summary, bt_daily = backtest_status(pnl_series)
    # Exception = today's actual P&L (units held over T-1 -> T) beyond yesterday's VaR.
    today_exception = bool(asset_pnl.sum() < -y["hist_var"])
    stress = stress_table(prices, t["mv"].to_dict())
    by_class, _ = im_by_asset_class(prices, t["mv"].to_dict(), S.MPOR, S.IM_CONFIDENCE, S.IM_RECENT_WINDOW)

    comments = commentary(t, y, asset_pnl, bt_summary, today_exception, stress)

    path = OUT / f"risk_report_{d_t.date()}.xlsx"
    write_report(path, t, y, asset_pnl, units, bt_summary, bt_daily, stress, history,
                 comments, VAR_LIMIT, by_class)

    print(f"Daily risk report for {d_t.date()} (vs {d_y.date()})\n")
    for status, text in comments:
        print(f"[{status:<7}] {text}")
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main()
