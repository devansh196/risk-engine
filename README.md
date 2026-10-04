# Portfolio Risk & Initial Margin Engine

A Python risk engine for a multi-asset INR portfolio (Indian equities, index ETF, gold, government bonds, USD cash).
It estimates how much the portfolio could lose and how much margin a bank should hold against it.

## Status
- [x] **Day 1:** data pipeline, 99% VaR (historical, parametric, Monte Carlo), Expected Shortfall, diversification benefit
- [ ] **Day 2:** VaR backtesting (Kupiec POF test, Basel traffic light)
- [ ] **Day 3:** stress testing (2008, COVID-19, hypothetical shocks) and initial margin (10-day MPOR)
- [ ] **Day 4:** Excel reporting with day-on-day commentary

## How to run
```bash
pip install -r requirements.txt
python run_var.py              # downloads real prices from Yahoo Finance
python run_var.py --synthetic  # offline test with fake data
python run_var.py --refresh    # re-download prices
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

## Project layout
```
risk_engine/config.py   portfolio and model settings
risk_engine/data.py     download, cache, align calendars, returns
risk_engine/var.py      VaR and ES methods
run_var.py              runs everything, prints a table, saves a CSV and chart
```
