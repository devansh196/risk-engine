"""Day 4: daily risk snapshot and auto-generated day-on-day commentary.

Positions are set to their config.py INR values on the report date (T), which fixes the
number of units held. The previous day (T-1) is valued with the same units at T-1 prices,
so the change between the two days is the real P&L of holding the portfolio.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

from . import config as C
from . import scenarios as S
from .backtest import backtest, ewma_var, rolling_historical_var, rolling_parametric_var
from .data import compute_returns
from .margin import im_calibrations
from .scenarios import asset_class
from .stress import historical_scenario, hypothetical_scenario
from .var import historical_var_es, parametric_var_es

VAR_LIMIT = 25_000          # 1-day 99% historical VaR limit for this client (INR)
LIMIT_WARNING = 0.90        # warn above 90% utilisation
APC_KEY = f"APC blend ({S.APC_STRESS_WEIGHT:.0%} stressed)"


def collateral_driver(name, tickers):
    """Which price drives each collateral item's value (None = fixed value, e.g. cash)."""
    n = name.lower()
    if "bond" in n or "gilt" in n:
        return next((t for t in tickers if asset_class(t) == "Bonds"), None)
    if "nifty" in n:
        return next((t for t in tickers if "NIFTY" in t.upper()), None)
    return None


def units_on(prices, date):
    """Number of units held, so that positions equal their config values on `date`."""
    p = prices.loc[date]
    return pd.Series({t: C.PORTFOLIO[t] / p[t] for t in prices.columns})


def collateral_units_on(prices, date):
    out = {}
    for name, (value, haircut) in S.COLLATERAL.items():
        drv = collateral_driver(name, prices.columns)
        out[name] = (drv, value / prices.loc[date, drv] if drv else value, haircut)
    return out


def snapshot(prices, units, coll_units):
    """Every risk number for the last date in `prices`, using only data up to that date."""
    a, W = C.CONFIDENCE, C.WINDOW
    z = norm.ppf(a)
    p = prices.iloc[-1]
    mv = units * p
    positions = mv.to_dict()

    all_rets = compute_returns(prices)
    rets = all_rets.tail(W)
    pnl = rets @ mv
    h_var, h_es = historical_var_es(pnl, a)
    p_var, p_es, sigma = parametric_var_es(rets, positions, a)
    full_pnl = all_rets @ mv
    e_var = z * np.sqrt((full_pnl ** 2).ewm(alpha=1 - C.EWMA_LAMBDA, adjust=False).mean().iloc[-1])

    # Component VaR: each asset's share of parametric VaR (they add up to the total).
    cov = rets.cov().values
    comp = pd.Series(z * mv.values * (cov @ mv.values) / sigma, index=mv.index)
    standalone = z * rets.std() * mv

    im = im_calibrations(prices, positions, S.MPOR, S.IM_CONFIDENCE, S.IM_RECENT_WINDOW,
                         S.STRESS_PERIOD, S.APC_STRESS_WEIGHT)

    coll_rows = []
    for name, (drv, qty, haircut) in coll_units.items():
        value = qty * p[drv] if drv else qty
        coll_rows.append({"Collateral": name, "Price driver": drv or "-", "Units": qty if drv else None,
                          "Price": p[drv] if drv else None, "Market value": value, "Haircut": haircut,
                          "Value after haircut": value * (1 - haircut)})
    coll = pd.DataFrame(coll_rows).set_index("Collateral")

    return {"date": prices.index[-1], "prices": p, "mv": mv, "total": mv.sum(),
            "hist_var": h_var, "hist_es": h_es, "param_var": p_var, "ewma_var": e_var,
            "component_var": comp, "standalone_var": standalone, "im": im,
            "im_required": im[APC_KEY], "collateral": coll,
            "collateral_after_haircut": coll["Value after haircut"].sum()}


def var_history(prices, units, days=60):
    """Rolling VaR forecasts vs actual P&L over the last `days` days (positions held fixed)."""
    pnl = compute_returns(prices) @ (units * prices.iloc[-1])
    a, W = C.CONFIDENCE, C.WINDOW
    df = pd.DataFrame({"Actual P&L": pnl,
                       "Historical VaR": rolling_historical_var(pnl, W, a),
                       "Parametric VaR": rolling_parametric_var(pnl, W, a),
                       "EWMA VaR": ewma_var(pnl, C.EWMA_LAMBDA, a)}).dropna()
    df["Exception"] = df["Actual P&L"] < -df["Historical VaR"]
    return pnl, df.tail(days)


def backtest_status(pnl):
    a, W = C.CONFIDENCE, C.WINDOW
    f = rolling_historical_var(pnl, W, a)
    test = pnl.loc[f.first_valid_index():].tail(C.BACKTEST_DAYS)
    summary, daily = backtest(test, f.loc[test.index], a)
    return summary, daily


def stress_table(prices, positions):
    rows = []
    for name, (s, e) in S.HISTORICAL_SCENARIOS.items():
        if pd.Timestamp(e) > prices.index[-1]:
            continue
        res = historical_scenario(prices, positions, s, e)
        if res is not None:
            rows.append({"Scenario": name, "Type": "Historical", "P&L": res["asset_pnl"].sum()})
    for name, shocks in S.HYPOTHETICAL_SCENARIOS.items():
        rows.append({"Scenario": name, "Type": "Hypothetical",
                     "P&L": hypothetical_scenario(positions, shocks)["asset_pnl"].sum()})
    df = pd.DataFrame(rows).set_index("Scenario").sort_values("P&L")
    df["% of portfolio"] = df["P&L"] / sum(positions.values())
    return df


def inr(x):
    sign = "-" if x < 0 else ""
    return f"{sign}Rs {abs(x):,.0f}"


def pct(x):
    return f"{x:+.1%}"


def commentary(t, y, asset_pnl, bt_summary, today_exception, stress):
    """Write the day-on-day comments a risk analyst would put at the top of the report.

    Returns a list of (status, text). Status is INFO, WARNING or ALERT.
    """
    out = []

    # 1. P&L and its main driver
    pnl = asset_pnl.sum()
    worst, best = asset_pnl.idxmin(), asset_pnl.idxmax()
    driver = worst if pnl < 0 else best
    ret = t["prices"] / y["prices"] - 1
    text = (f"Portfolio value {inr(t['total'])}. Daily P&L {inr(pnl)} ({pct(pnl / y['total'])}), "
            f"driven mainly by {driver} ({inr(asset_pnl[driver])}, {pct(ret[driver])}).")
    other = best if pnl < 0 else worst
    if np.sign(asset_pnl[other]) != np.sign(pnl) and abs(asset_pnl[other]) > 0.2 * abs(pnl):
        text += f" Partly offset by {other} ({inr(asset_pnl[other])})."
    out.append(("INFO", text))

    # 2. VaR move and what drove it
    dv = t["hist_var"] - y["hist_var"]
    dcomp = t["component_var"] - y["component_var"]
    top = dcomp.abs().idxmax()
    util = t["hist_var"] / VAR_LIMIT
    status = "ALERT" if util > 1 else "WARNING" if util > LIMIT_WARNING else "INFO"
    text = (f"1-day 99% historical VaR {'up' if dv >= 0 else 'down'} {abs(dv / y['hist_var']):.1%} "
            f"to {inr(t['hist_var'])} ({util:.0%} of the {inr(VAR_LIMIT)} limit). "
            f"Largest change in VaR contribution: {top} ({'+' if dcomp[top] >= 0 else ''}{inr(dcomp[top])}).")
    if util > 1:
        text += " LIMIT BREACH: escalate and consider reducing exposure."
    elif util > LIMIT_WARNING:
        text += " Approaching limit."
    out.append((status, text))

    # 3. Volatility regime: EWMA vs historical
    ratio = t["ewma_var"] / t["hist_var"]
    if ratio > 1.2:
        out.append(("WARNING", f"EWMA VaR ({inr(t['ewma_var'])}) is {ratio - 1:.0%} above historical VaR: "
                               f"recent volatility is elevated, so the 2-year window may understate risk."))
    elif ratio < 0.8:
        out.append(("INFO", f"EWMA VaR ({inr(t['ewma_var'])}) is {1 - ratio:.0%} below historical VaR: "
                            f"markets have been calmer recently than over the 2-year window."))

    # 4. Margin and collateral
    im_t, im_y = t["im_required"], y["im_required"]
    c_t, c_y = t["collateral_after_haircut"], y["collateral_after_haircut"]
    excess_t = c_t - im_t
    text = (f"Initial margin requirement {inr(im_t)} ({'+' if im_t >= im_y else ''}{inr(im_t - im_y)} DoD); "
            f"collateral after haircuts {inr(c_t)} ({'+' if c_t >= c_y else ''}{inr(c_t - c_y)} DoD).")
    if excess_t < 0:
        out.append(("ALERT", text + f" MARGIN CALL of {inr(-excess_t)} to be issued to the client."))
    else:
        cushion = excess_t / im_t
        status = "WARNING" if cushion < 0.10 else "INFO"
        text += f" Excess collateral {inr(excess_t)} ({cushion:.0%} cushion)."
        if cushion < 0.10:
            text += " Cushion below 10%: a small move could trigger a margin call."
        out.append((status, text))

    # 5. Backtest
    x, zone = bt_summary["Exceptions"], bt_summary["Basel zone"]
    status = {"GREEN": "INFO", "YELLOW": "WARNING", "RED": "ALERT"}[zone]
    if today_exception:
        text = (f"VaR EXCEPTION today: loss of {inr(-pnl)} exceeded yesterday's VaR of {inr(y['hist_var'])}. "
                f"{x} exceptions in the last {bt_summary['Days']} days ({zone} zone).")
        status = "ALERT" if zone == "RED" else "WARNING"
    else:
        text = f"No VaR exception today. {x} exceptions in the last {bt_summary['Days']} days ({zone} zone)."
    out.append((status, text))

    # 6. Stress loss beyond collateral
    worst_name = stress["P&L"].idxmin()
    worst_loss = -stress.loc[worst_name, "P&L"]
    uncovered = worst_loss - c_t
    out.append(("INFO", f"Worst stress scenario: {worst_name}, loss {inr(worst_loss)} "
                        f"({worst_loss / t['total']:.1%}). Collateral covers {c_t / worst_loss:.0%} of it, "
                        f"leaving {inr(uncovered)} of uncollateralised stress exposure."))
    return out
