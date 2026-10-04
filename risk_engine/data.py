"""Load prices and turn them into daily returns."""
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data"


def download_prices(tickers, start, end=None, retries=3):
    """Download adjusted close prices from Yahoo Finance.

    threads=False avoids yfinance's "database is locked" error on Windows,
    and any ticker that still fails is retried on its own.
    """
    import time
    import yfinance as yf

    def fetch(tks):
        raw = yf.download(list(tks), start=start, end=end, auto_adjust=True,
                          progress=False, threads=False)
        if raw.empty:
            return pd.DataFrame()
        close = raw["Close"]
        return close if isinstance(close, pd.DataFrame) else close.to_frame(tks[0])

    prices = fetch(tickers)
    for attempt in range(retries):
        missing = [t for t in tickers if t not in prices or prices[t].notna().sum() == 0]
        if not missing:
            break
        time.sleep(2)
        for t in missing:
            got = fetch([t])
            if not got.empty and got.iloc[:, 0].notna().any():
                prices = prices.drop(columns=t, errors="ignore").join(got.iloc[:, :1].set_axis([t], axis=1), how="outer")
    return prices.reindex(columns=list(tickers))


SPLIT_FACTORS = [2, 3, 4, 5, 10, 20, 25, 50, 100]


def fix_unadjusted_splits(prices, threshold=0.5):
    """Detect and undo price-scale errors: unadjusted splits or temporarily mis-scaled prices.

    A 1:10 split makes the price drop ~90% overnight, which looks like a crash.
    Yahoo also sometimes shows a few days at the wrong scale and then reverts
    (NIFTYBEES and GOLDBEES on 19-20 Dec 2019); the down-jump and up-jump corrections cancel out.
    Rule: if a price falls below half (or more than doubles) in one day, treat it as a
    split, find the closest standard split ratio, and rescale all earlier prices.
    The genuine market move on that day is kept (only the split factor is removed).
    """
    prices = prices.copy()
    for col in prices.columns:
        s = prices[col].dropna()
        ratio = s / s.shift(1)
        for date, r in ratio[(ratio < threshold) | (ratio > 1 / threshold)].items():
            jump = 1 / r if r < 1 else r
            k = min(SPLIT_FACTORS, key=lambda f: abs(np.log(f / jump)))
            earlier = prices.index < date
            if r < 1:
                prices.loc[earlier, col] /= k      # split: shrink old prices
            else:
                prices.loc[earlier, col] *= k      # reverse split: grow old prices
            print(f"[data fix] {col}: price scale jump x{'1/' if r < 1 else ''}{k} on {date.date()} "
                  f"(ratio {r:.4f}), corrected")
    return prices


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
        # If the cache is missing a ticker (e.g. a failed download last time), fetch again.
        if any(t not in prices or prices[t].notna().sum() <= 250 for t in tickers):
            print("[info] cached prices incomplete, re-downloading")
            refresh = True
    if not path.exists() or refresh:
        prices = download_prices(tickers, start, end)
        if prices.dropna(how="all").empty:
            raise RuntimeError("No prices downloaded. Check your internet connection or the "
                               "tickers in config.py, or run with --synthetic to test offline.")
        prices.to_csv(path)

    # Drop any ticker that failed to download or has very little history.
    good = [t for t in tickers if t in prices and prices[t].notna().sum() > 250]
    for t in set(tickers) - set(good):
        print(f"[warning] dropping {t}: not enough price data")
    prices = fix_unadjusted_splits(prices[good])

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
