# Portfolio Risk & Initial Margin Engine

A Python risk engine for a multi-asset INR portfolio (Indian equities, index ETF, gold, government bonds, USD cash).
It estimates how much the portfolio could lose and how much margin a bank should hold against it.

## Status
- [x] **Day 1:** data pipeline, 99% VaR (historical, parametric, Monte Carlo), Expected Shortfall, diversification benefit
- [x] **Day 2:** VaR backtesting (Kupiec POF, Christoffersen independence, Basel traffic light), EWMA VaR
- [ ] **Day 3:** stress testing (2008, COVID-19, hypothetical shocks) and initial margin (10-day MPOR)
- [ ] **Day 4:** Excel reporting with day-on-day commentary

## How to run
```bash
pip install -r requirements.txt
python run_var.py              # downloads real prices from Yahoo Finance
python run_var.py --synthetic  # offline test with fake data
python run_var.py --refresh    # re-download prices
python run_backtest.py              # backtest the last 250 days
python run_backtest.py --days 2000  # longer backtest, includes the 2020 COVID crash
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

## Project layout
```
risk_engine/config.py   portfolio and model settings
risk_engine/data.py     download, cache, align calendars, returns
risk_engine/var.py      VaR and ES methods
risk_engine/backtest.py rolling VaR, Kupiec, Christoffersen, Basel traffic light
run_var.py              Day 1: VaR/ES table and P&L distribution chart
run_backtest.py         Day 2: backtest table, exception list and chart
```
