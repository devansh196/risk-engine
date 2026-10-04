# Portfolio Risk & Initial Margin Engine

A Python risk engine for a multi-asset INR portfolio (Indian equities, index ETF, gold, government bonds, USD cash).
It estimates how much the portfolio could lose and how much margin a bank should hold against it.

## Status
- [x] **Day 1:** data pipeline, 99% VaR (historical, parametric, Monte Carlo), Expected Shortfall, diversification benefit
- [x] **Day 2:** VaR backtesting (Kupiec POF, Christoffersen independence, Basel traffic light), EWMA VaR
- [x] **Day 3:** stress testing (historical + hypothetical scenarios) and initial margin (10-day MPOR, stressed calibration, anti-procyclicality, collateral haircuts)
- [ ] **Day 4:** Excel reporting with day-on-day commentary

## How to run
```bash
pip install -r requirements.txt
python run_var.py              # downloads real prices from Yahoo Finance
python run_var.py --synthetic  # offline test with fake data
python run_var.py --refresh    # re-download prices
python run_backtest.py              # backtest the last 250 days
python run_backtest.py --days 2000  # longer backtest, includes the 2020 COVID crash
python run_stress.py                # stress tests on today's portfolio
python run_margin.py                # initial margin, collateral and margin call
```
Prices are cached in `data/prices.csv`. Results go to `outputs/`.
Change holdings, confidence level or window in `risk_engine/config.py`.

## Methods
| Method | Idea | Strength | Weakness |
|---|---|---|---|
| Historical | Reuse the last 500 days of actual P&L | No distribution assumption; captures real fat tails | Depends on the chosen window; only knows what has happened |
| Parametric | Assume normal returns; VaR = 2.326 x portfolio std dev | Fast; easy to break down by asset | Normality underestimates crash days |
| Monte Carlo (normal) | Simulate 100k correlated days from the covariance matrix | Flexible; extends to non-linear products | Slow; only as good as its assumed distribution |
| Monte Carlo (Student-t) | Same, with fat-tailed draws | Produces more realistic extreme losses | Needs a choice of degrees of freedom |

- **Expected Shortfall:** the average loss on the worst 1% of days. FRTB uses ES instead of VaR because ES measures how bad the tail is.
- **10-day VaR:** 1-day VaR x sqrt(10). This assumes days are independent, which is not true in a crisis.
- **Diversification benefit:** the sum of each asset's standalone VaR minus the portfolio VaR.

## Backtesting
Each day, VaR is forecast using only data up to the day before, then compared with that day's actual P&L.
A loss bigger than VaR is an **exception**. At 99% over 250 days, about 2.5 are expected.

| Test | Question it answers | Fails when |
|---|---|---|
| Basel traffic light | Is the exception count acceptable? | 5-9 = yellow (capital multiplier rises), 10+ = red |
| Kupiec POF | Is the exception rate consistent with 1%? | p-value < 0.05 |
| Christoffersen independence | Do exceptions cluster together? | p-value < 0.05 (model reacts too slowly to volatility) |

Models compared: historical (500-day window), parametric (500-day window), and EWMA (RiskMetrics, lambda = 0.94), which weights recent days more heavily.

## Stress testing
VaR describes a normal bad day; stress tests ask what happens in a crisis.
- **Historical scenarios** replay real crises on today's positions: IL&FS (2018), COVID-19 (2020), Russia-Ukraine (2022), election-result day and yen carry unwind (2024), FPI sell-off (2024-25), plus the worst 10-day window in the data.
- **Hypothetical scenarios** apply designed shocks by asset class: equity crash, 2008-style crisis, rate shock, and "hedges fail" (everything falls together).

Edit scenarios in `risk_engine/scenarios.py`.

## Initial margin
If a client defaults, the bank needs about 10 days (the margin period of risk) to close out the positions.
Initial margin is set at the 99% loss over those 10 days, using actual overlapping 10-day P&L rather than the sqrt(10) shortcut.
- **Recent vs stressed calibration:** last 2 years vs the 2020 COVID year.
- **Anti-procyclicality:** 25% weight on the stressed IM, so margin doesn't collapse in calm markets and spike in a crisis.
- **By asset class:** IM summed across classes (SIMM-style, no netting) vs full portfolio netting.
- **Collateral:** haircuts by collateral type, excess/shortfall, and a stress case where equity collateral falls as IM rises (wrong-way risk).

## Project layout
```
risk_engine/config.py   portfolio and model settings
risk_engine/data.py     download, cache, align calendars, returns
risk_engine/var.py      VaR and ES methods
risk_engine/backtest.py rolling VaR, Kupiec, Christoffersen, Basel traffic light
run_var.py              Day 1: VaR/ES table and P&L distribution chart
risk_engine/scenarios.py stress scenarios, margin and collateral settings
risk_engine/stress.py   historical and hypothetical stress tests
risk_engine/margin.py   initial margin, calibration, collateral, margin calls
run_backtest.py         Day 2: backtest table, exception list and chart
run_stress.py           Day 3: stress test table and chart
run_margin.py           Day 3: initial margin report and IM-over-time chart
```
