"""Stress testing: how much would the portfolio lose in a crisis?

VaR describes a normal bad day (1-in-100). Stress tests ask about extreme but plausible
events that may sit far beyond VaR, which is why regulators require both.
"""
import pandas as pd

from .scenarios import asset_class


def _nearest_on_or_before(index, date):
    pos = index.searchsorted(pd.Timestamp(date), side="right") - 1
    return index[pos] if pos >= 0 else None


def historical_scenario(prices, positions, start, end):
    """Apply each asset's actual return between start and end to today's positions."""
    d0, d1 = _nearest_on_or_before(prices.index, start), _nearest_on_or_before(prices.index, end)
    if d0 is None or d1 is None or d0 >= d1:
        return None
    asset_ret = prices.loc[d1] / prices.loc[d0] - 1
    v = pd.Series(positions)
    return {"start": d0, "end": d1, "asset_returns": asset_ret[v.index], "asset_pnl": asset_ret[v.index] * v}


def hypothetical_scenario(positions, shocks):
    """Apply a designed shock to each asset based on its asset class."""
    v = pd.Series(positions)
    asset_ret = pd.Series({t: shocks.get(asset_class(t), 0.0) for t in v.index})
    return {"asset_returns": asset_ret, "asset_pnl": asset_ret * v}


def worst_historical_window(prices, positions, days=10):
    """Data-driven scenario: the worst `days`-day loss in the entire history."""
    v = pd.Series(positions)
    pnl_h = prices.pct_change(days).dropna() @ v
    end = pnl_h.idxmin()
    start = prices.index[prices.index.get_loc(end) - days]
    return start, end
