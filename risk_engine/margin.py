"""Initial margin (IM): collateral that protects the bank if a client defaults.

If a client defaults, the bank needs some days to close out (sell or hedge) the positions.
That is the margin period of risk (MPOR), typically 10 days. Prices can move against the
bank during that time, so IM is set at roughly the 99% loss over the MPOR:
    IM = 99% 10-day VaR

Variation margin (VM) is different: it settles each day's mark-to-market change in cash.
IM covers the FUTURE loss after a default; VM covers losses that have ALREADY happened.
"""
import numpy as np
import pandas as pd

from .scenarios import asset_class


def horizon_pnl(prices, positions, days):
    """Overlapping `days`-day P&L series: P&L from holding the portfolio for `days` days.

    Using real 10-day returns avoids the sqrt(10) shortcut, which assumes days are
    independent (they are not in a crisis). Overlapping windows share data, so the
    observations are correlated -- a known limitation.
    """
    v = pd.Series(positions)
    return prices[v.index].pct_change(days).dropna() @ v


def historical_im(pnl_h, alpha=0.99):
    return -np.percentile(pnl_h, 100 * (1 - alpha))


def im_calibrations(prices, positions, mpor, alpha, recent_window, stress_period, apc_weight):
    """IM under recent vs stressed calibration, plus an anti-procyclical blend.

    Recent:   reacts to current markets, but is LOW in calm times and jumps in a crisis.
    Stressed: calibrated on a crisis year, stable but expensive for the client.
    APC:      blend that stops IM collapsing in calm times, so margin calls in a crisis
              are smaller. Regulation (EMIR) allows a 25% stressed weighting for this.
    """
    pnl_h = horizon_pnl(prices, positions, mpor)
    recent = historical_im(pnl_h.tail(recent_window), alpha)
    stressed_pnl = pnl_h.loc[stress_period[0]:stress_period[1]]
    stressed = historical_im(stressed_pnl, alpha) if len(stressed_pnl) > 50 else np.nan
    apc = max(recent, (1 - apc_weight) * recent + apc_weight * stressed) if not np.isnan(stressed) else recent

    one_day = prices[list(positions)].pct_change().dropna().tail(recent_window) @ pd.Series(positions)
    sqrt_rule = historical_im(one_day, alpha) * np.sqrt(mpor)
    return {"Recent (last 2y)": recent, "Stressed (2020)": stressed,
            f"APC blend ({apc_weight:.0%} stressed)": apc, "sqrt(10) x 1-day VaR (recent)": sqrt_rule}


def im_by_asset_class(prices, positions, mpor, alpha, recent_window):
    """IM for each asset class on its own, vs the whole portfolio with full netting.

    SIMM-style models add up IM across risk classes with little or no diversification,
    which is more conservative than full netting.
    """
    pnl_all = horizon_pnl(prices, positions, mpor).tail(recent_window)
    rows = {}
    for cls in sorted({asset_class(t) for t in positions}):
        sub = {t: v for t, v in positions.items() if asset_class(t) == cls}
        rows[cls] = historical_im(horizon_pnl(prices, sub, mpor).tail(recent_window), alpha)
    by_class = pd.Series(rows, name="Standalone IM")
    return by_class, historical_im(pnl_all, alpha)


def rolling_im(prices, positions, mpor, alpha, window):
    """IM recalculated every day on a rolling window -- shows how IM moves through time."""
    pnl_h = horizon_pnl(prices, positions, mpor)
    return -pnl_h.rolling(window).quantile(1 - alpha)


def collateral_table(collateral):
    df = pd.DataFrame(collateral, index=["Market value", "Haircut"]).T
    df["Value after haircut"] = df["Market value"] * (1 - df["Haircut"])
    return df


def margin_call(im_required, collateral_after_haircut):
    """Positive = client must post more collateral; negative = excess collateral."""
    return im_required - collateral_after_haircut
