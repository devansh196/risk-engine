"""Portfolio and model settings. Change these to experiment."""

# Position value of each holding, in INR (total = Rs 10,00,000).
# Think of this as a client's portfolio the bank has exposure to.
PORTFOLIO = {
    "RELIANCE.NS":   200_000,  # equity
    "HDFCBANK.NS":   150_000,  # equity (bank)
    "TCS.NS":        150_000,  # equity (IT)
    "INFY.NS":       100_000,  # equity (IT)
    "NIFTYBEES.NS":  150_000,  # Nifty 50 index ETF
    "GOLDBEES.NS":   100_000,  # gold ETF
    "SETF10GILT.NS": 100_000,  # 5-year government bond ETF
    "INR=X":          50_000,  # USD cash, valued in INR (USD/INR rate)
}

# Trading calendar to align everything to (NSE trading days).
REFERENCE_TICKER = "NIFTYBEES.NS"

START_DATE = "2015-01-01"   # long history, so later we can replay 2020 and other stress periods
END_DATE = None             # None = up to today

CONFIDENCE = 0.99           # 99% VaR, the regulatory standard
WINDOW = 500                # look-back window in trading days (~2 years)
HORIZONS = [1, 10]          # 1-day VaR and 10-day VaR (10 days = Basel / margin period of risk)

MC_SIMULATIONS = 100_000
MC_T_DOF = 5                # degrees of freedom for the fat-tailed Student-t Monte Carlo
SEED = 42

# ---------- Day 2: backtesting ----------
BACKTEST_DAYS = 250         # Basel backtests on the last 250 trading days (~1 year)
EWMA_LAMBDA = 0.94          # RiskMetrics decay factor: recent days count more
