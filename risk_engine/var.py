"""Value at Risk (VaR) and Expected Shortfall (ES).

Sign convention: VaR and ES are reported as POSITIVE numbers = size of the loss.
"99% 1-day VaR = Rs 25,000" means: on 99% of days we lose less than Rs 25,000.
ES = the average loss on the worst 1% of days (always >= VaR).
"""
import numpy as np
import pandas as pd
from scipy.stats import norm


def portfolio_pnl(returns, positions):
    """Daily P&L of the portfolio in INR, if it had been held over each past day."""
    v = pd.Series(positions)[returns.columns]
    return returns @ v


def scale_to_horizon(one_day_value, days):
    """Square-root-of-time rule: 10-day VaR ~ 1-day VaR * sqrt(10).

    Assumes returns are independent and identically distributed day to day.
    It breaks down when volatility clusters (e.g. in a crisis).
    """
    return one_day_value * np.sqrt(days)


# ---------- 1. Historical simulation ----------
def historical_var_es(pnl, alpha=0.99):
    """Reuse actual past P&L. No distribution assumption.

    VaR = loss at the (1 - alpha) percentile of past P&L.
    ES  = average of the losses worse than VaR.
    """
    cutoff = np.percentile(pnl, 100 * (1 - alpha))
    var = -cutoff
    es = -pnl[pnl <= cutoff].mean()
    return var, es


# ---------- 2. Parametric (variance-covariance) ----------
def parametric_var_es(returns, positions, alpha=0.99, include_mean=False):
    """Assume returns are jointly normal.

    Portfolio std dev:  sigma_p = sqrt(v' * Cov * v)   (v = position values)
    VaR = z * sigma_p          (z = 2.326 at 99%)
    ES  = sigma_p * pdf(z) / (1 - alpha)
    The mean is usually ignored for 1-day VaR because it is tiny.
    """
    v = pd.Series(positions)[returns.columns].values
    cov = returns.cov().values
    sigma = np.sqrt(v @ cov @ v)
    mu = (returns.mean().values @ v) if include_mean else 0.0

    z = norm.ppf(alpha)
    var = z * sigma - mu
    es = sigma * norm.pdf(z) / (1 - alpha) - mu
    return var, es, sigma


def standalone_vs_diversified(returns, positions, alpha=0.99):
    """Sum of each asset's own VaR vs the VaR of the whole portfolio.

    The gap is the diversification benefit: assets don't all crash together.
    """
    z = norm.ppf(alpha)
    v = pd.Series(positions)[returns.columns]
    standalone = z * returns.std() * v.abs()
    diversified, _, _ = parametric_var_es(returns, positions, alpha)
    return standalone, diversified


# ---------- 3. Monte Carlo ----------
def monte_carlo_var_es(returns, positions, alpha=0.99, n_sims=100_000,
                       dist="normal", dof=5, seed=42):
    """Simulate many possible tomorrows, then read off VaR/ES like historical.

    Correlated random returns come from the covariance matrix (via Cholesky).
    dist="normal": same assumption as parametric, so results should match it closely.
    dist="t":      Student-t with fat tails, gives more extreme crash days.
    """
    rng = np.random.default_rng(seed)
    v = pd.Series(positions)[returns.columns].values
    mu = returns.mean().values
    cov = returns.cov().values
    L = np.linalg.cholesky(cov)          # cov = L @ L.T, used to correlate the draws

    z = rng.standard_normal((n_sims, len(v)))
    if dist == "t":
        # Rescale so the t draws have the same variance as the data, then fatten tails.
        z = z * np.sqrt((dof - 2) / dof) / np.sqrt(rng.chisquare(dof, (n_sims, 1)) / dof)
    sim_returns = mu + z @ L.T
    sim_pnl = pd.Series(sim_returns @ v)

    var, es = historical_var_es(sim_pnl, alpha)
    return var, es, sim_pnl
