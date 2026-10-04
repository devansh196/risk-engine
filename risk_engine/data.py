"""Load prices and turn them into daily returns."""
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data"


def download_prices(tickers, start, end=None):
    """Download adjusted close prices from Yahoo Finance."""
    import yfinance as yf

    raw = yf.download(list(tickers), start=start, end=end,
                      auto_adjust=True, progress=False)
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    return prices.reindex(columns=list(tickers))


def align_to_calendar(prices, reference):
    """Keep only the reference market's trading days.

    FX trades on Indian market holidays and stocks don't, so we use NSE days
    and carry forward the last known price of anything that didn't trade.
    """
    days = prices[reference].dropna().index
    return prices.ffill().reindex(days)


def load_prices(tickers, start, end=None, reference=None, refresh=False):
    """Download prices once, cache them to data/prices.csv, then reuse the cache."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "prices.csv"

    if path.exists() and not refresh:
        prices = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        prices = download_prices(tickers, start, end)
        if prices.dropna(how="all").empty:
            raise RuntimeError("No prices downloaded. Check your internet connection or the "
                               "tickers in config.py, or run with --synthetic to test offline.")
        prices.to_csv(path)

    # Drop any ticker that failed to download or has very little history.
    good = [t for t in tickers if t in prices and prices[t].notna().sum() > 250]
    for t in set(tickers) - set(good):
        print(f"[warning] dropping {t}: not enough price data")
    prices = prices[good]

    if reference in good:
        prices = align_to_calendar(prices, reference)
    return prices.dropna()


def synthetic_prices(tickers, n_days=2500, seed=0):
    """Fake but realistic prices (correlated, fat-tailed) for testing without internet."""
    rng = np.random.default_rng(seed)
    n = len(tickers)
    vols = rng.uniform(0.005, 0.02, n)                  # daily vols 0.5% to 2%
    corr = 0.4 * np.ones((n, n)) + 0.6 * np.eye(n)       # 0.4 pairwise correlation
    cov = np.outer(vols, vols) * corr
    dof = 4
    z = rng.multivariate_normal(np.zeros(n), cov * (dof - 2) / dof, n_days)
    rets = z / np.sqrt(rng.chisquare(dof, (n_days, 1)) / dof)   # Student-t returns
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=list(tickers))


def compute_returns(prices):
    """Daily simple returns: r_t = P_t / P_{t-1} - 1.

    Simple (not log) returns are used for P&L because they add up across assets:
    portfolio P&L = sum(position_i * r_i).
    """
    return prices.pct_change().dropna()
