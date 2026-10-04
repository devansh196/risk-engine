"""Day 3 settings: stress scenarios, margin model and collateral.

Kept separate from config.py so you can edit scenarios without touching the portfolio.
"""

def asset_class(ticker):
    """Map a ticker to a broad risk class (used by hypothetical shocks and IM by class)."""
    t = ticker.upper()
    if t.endswith("=X"):
        return "FX"
    if "GOLD" in t:
        return "Gold"
    if any(k in t for k in ("GILT", "GSEC", "GSC", "BOND", "EBBETF", "LIQUID")):
        return "Bonds"
    return "Equity"     # single stocks and equity index ETFs


# ---------- Historical scenarios: replay a real crisis on TODAY's portfolio ----------
# Each asset's cumulative return between the two dates is applied to current positions.
# Our data starts in 2016, so 2008 is covered by a hypothetical scenario below instead.
HISTORICAL_SCENARIOS = {
    "IL&FS crisis (Aug-Oct 2018)":          ("2018-08-28", "2018-10-26"),
    "COVID-19 crash (Feb-Mar 2020)":        ("2020-02-19", "2020-03-23"),
    "Russia-Ukraine war (Jan-Mar 2022)":    ("2022-01-17", "2022-03-07"),
    "Election result day (4 Jun 2024)":     ("2024-06-03", "2024-06-04"),
    "Yen carry-trade unwind (Aug 2024)":    ("2024-08-01", "2024-08-05"),
    "FPI sell-off (Sep 2024-Mar 2025)":     ("2024-09-26", "2025-03-03"),
}

# ---------- Hypothetical scenarios: shocks we design, by asset class ----------
# FX shock = change in USD/INR: +10% means the rupee weakens, so USD cash GAINS in INR.
# Bonds: a 10-year gilt ETF has duration ~7, so +100bp in yields is roughly -7%.
HYPOTHETICAL_SCENARIOS = {
    "Equity crash -20%":             {"Equity": -0.20, "Gold": +0.05, "Bonds": +0.02, "FX": +0.05},
    "2008-style crisis":             {"Equity": -0.40, "Gold": +0.10, "Bonds": +0.03, "FX": +0.15},
    "Rate shock (+150bp yields)":    {"Equity": -0.10, "Gold": -0.05, "Bonds": -0.10, "FX": +0.03},
    "Hedges fail (everything falls)": {"Equity": -0.15, "Gold": -0.10, "Bonds": -0.05, "FX": -0.05},
}

# ---------- Initial margin ----------
MPOR = 10                          # margin period of risk (days to close out a defaulted client)
IM_CONFIDENCE = 0.99
IM_RECENT_WINDOW = 500             # recent calibration: last ~2 years of 10-day P&L
STRESS_PERIOD = ("2020-01-01", "2020-12-31")   # stressed calibration: the COVID year
APC_STRESS_WEIGHT = 0.25           # anti-procyclicality: give 25% weight to the stressed IM

# Collateral the client has posted against the portfolio: value in INR, haircut.
# Haircut = how much the bank discounts the collateral, since it could fall in value
# while being sold. Riskier collateral gets a bigger haircut.
COLLATERAL = {
    "Cash (INR)":              (40_000, 0.00),
    "Government bonds":        (30_000, 0.04),
    "Nifty 50 ETF units":      (30_000, 0.15),   # correlated with the portfolio -> wrong-way risk
}
