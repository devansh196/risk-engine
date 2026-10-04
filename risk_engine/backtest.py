"""VaR backtesting: did the model's VaR actually hold up day by day?

Idea: every day, compute VaR using ONLY the data available up to yesterday,
then compare it with today's actual P&L. If today's loss is bigger than VaR,
that's an "exception" (also called a breach or exceedance).

At 99% confidence over 250 days we expect about 2.5 exceptions.
  - Far more  -> model UNDERestimates risk (dangerous).
  - Zero      -> model may be too conservative (wastes capital), or just lucky.

Because positions are held fixed in INR, the portfolio P&L series alone is enough:
std of portfolio P&L over a window = sqrt(v' Cov v), the same number as Day 1's parametric VaR.
"""
import numpy as np
import pandas as pd
from scipy.special import xlogy
from scipy.stats import binom, chi2, norm


# ---------- Rolling VaR forecasts (no look-ahead: .shift(1) uses only past data) ----------
def rolling_historical_var(pnl, window, alpha=0.99):
    return -pnl.rolling(window).quantile(1 - alpha).shift(1)


def rolling_parametric_var(pnl, window, alpha=0.99):
    return norm.ppf(alpha) * pnl.rolling(window).std().shift(1)


def ewma_var(pnl, lam=0.94, alpha=0.99):
    """RiskMetrics EWMA: sigma_t^2 = lam * sigma_{t-1}^2 + (1 - lam) * pnl_{t-1}^2.

    Recent days get more weight, so VaR jumps quickly when markets get volatile.
    This targets the main weakness of equal-weighted windows: volatility clustering.
    """
    var_t = (pnl ** 2).ewm(alpha=1 - lam, adjust=False).mean().shift(1)
    return norm.ppf(alpha) * np.sqrt(var_t)


# ---------- Statistical tests ----------
def kupiec_pof(exceptions, days, alpha=0.99):
    """Kupiec Proportion of Failures test: is the exception RATE consistent with 1%?

    LR = -2 ln[(1-p)^(T-x) p^x] + 2 ln[(1-x/T)^(T-x) (x/T)^x]   ~ chi-square(1)
    p = expected exception rate (1%), x = exceptions, T = days.
    Reject the model at 95% confidence if LR > 3.84 (p-value < 0.05).
    """
    p, x, T = 1 - alpha, exceptions, days
    phat = x / T
    log_null = xlogy(T - x, 1 - p) + xlogy(x, p)
    log_alt = xlogy(T - x, 1 - phat) + xlogy(x, phat)
    lr = -2 * (log_null - log_alt)
    return lr, 1 - chi2.cdf(lr, 1)


def christoffersen_independence(hits):
    """Christoffersen test: do exceptions CLUSTER (one breach followed by another)?

    A good model's exceptions should be independent. Clustering means the model
    reacts too slowly when volatility rises -- exactly what happens in a crisis.
    """
    h = np.asarray(hits, dtype=int)
    prev, curr = h[:-1], h[1:]
    n00 = np.sum((prev == 0) & (curr == 0)); n01 = np.sum((prev == 0) & (curr == 1))
    n10 = np.sum((prev == 1) & (curr == 0)); n11 = np.sum((prev == 1) & (curr == 1))

    pi0 = n01 / (n00 + n01) if (n00 + n01) else 0.0   # P(breach | no breach yesterday)
    pi1 = n11 / (n10 + n11) if (n10 + n11) else 0.0   # P(breach | breach yesterday)
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)

    log_null = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    log_alt = xlogy(n00, 1 - pi0) + xlogy(n01, pi0) + xlogy(n10, 1 - pi1) + xlogy(n11, pi1)
    lr = -2 * (log_null - log_alt)
    return lr, 1 - chi2.cdf(lr, 1)


def basel_traffic_light(exceptions, days=250, alpha=0.99):
    """Basel traffic-light zone for a VaR model.

    Zones come from the binomial distribution: how likely is it to see this many
    exceptions or fewer if the model were correct?
      GREEN  if that probability is below 95%
      RED    if it is 99.99% or higher (model almost certainly wrong)
      YELLOW in between
    For 250 days at 99% this gives the familiar table: green 0-4, yellow 5-9, red 10+.
    The capital multiplier (base 3.0) only applies to the standard 250-day test.
    """
    cum = binom.cdf(exceptions, days, 1 - alpha)
    zone = "GREEN" if cum < 0.95 else ("RED" if cum >= 0.9999 else "YELLOW")
    mult = None
    if days == 250:
        mult = 3.0 if exceptions <= 4 else 4.0 if exceptions >= 10 else \
            {5: 3.40, 6: 3.50, 7: 3.65, 8: 3.75, 9: 3.85}[exceptions]
    return zone, mult


# ---------- Put it together ----------
def backtest(pnl, var_forecast, alpha=0.99):
    """Compare forecasts with actual P&L. Returns a summary dict and a daily frame."""
    df = pd.DataFrame({"pnl": pnl, "var": var_forecast}).dropna()
    df["exception"] = df["pnl"] < -df["var"]
    T, x = len(df), int(df["exception"].sum())

    zone, mult = basel_traffic_light(x, T, alpha)
    lr_pof, p_pof = kupiec_pof(x, T, alpha)
    lr_ind, p_ind = christoffersen_independence(df["exception"])

    summary = {
        "Days": T,
        "Exceptions": x,
        "Expected": round(T * (1 - alpha), 1),
        "Exception rate %": round(100 * x / T, 2),
        "Basel zone": zone,
        "Capital multiplier": mult,
        "Kupiec LR": round(lr_pof, 3),
        "Kupiec p-value": round(p_pof, 3),
        "Kupiec result": "Reject" if p_pof < 0.05 else "Accept",
        "Indep. LR": round(lr_ind, 3),
        "Indep. p-value": round(p_ind, 3),
        "Indep. result": "Clustered" if p_ind < 0.05 else "Independent",
    }
    return summary, df
