"""Shared helpers for the run scripts."""
import argparse

from . import config as C
from .data import load_prices, synthetic_prices


def parse_args(extra=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="offline test with fake data")
    ap.add_argument("--refresh", action="store_true", help="re-download prices")
    if extra:
        extra(ap)
    return ap.parse_args()


def get_prices_and_positions(args):
    tickers = list(C.PORTFOLIO)
    if args.synthetic:
        prices = synthetic_prices(tickers, seed=C.SEED)
    else:
        prices = load_prices(tickers, C.START_DATE, C.END_DATE,
                             reference=C.REFERENCE_TICKER, refresh=args.refresh)
    positions = {t: C.PORTFOLIO[t] for t in prices.columns}
    return prices, positions


def inr(x):
    return f"Rs {x:,.0f}"
