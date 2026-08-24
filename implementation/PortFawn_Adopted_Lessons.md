# What We Adopt From the PortFawn Paper

## Adopt

The 2021 PortFawn paper provides a useful separation of responsibilities:

```text
market data -> returns -> risk statistics -> optimizer -> weights -> backtest -> metrics
```

We adopt this as our project architecture. In particular:

- price data are converted into returns before optimization;
- expected returns and covariance are estimated from a fitting window;
- the optimizer returns portfolio weights;
- later observations are held out for evaluation;
- equal-weight and other transparent portfolios are useful benchmarks.

The new `portfolio_backtest.py` implements the data, weights, evaluation, and backtest layers. Mana's model can be plugged in without rewriting these layers.

## Do not copy directly

- The quantum-computing section is outside our scope.
- PortFawn's old daily 40-day fitting / 5-day evaluation example is not our agreed convention.
- PortFawn does not provide our investor-profile layer, CVaR, or a reproducible Robust MVO uncertainty set.
- A package dependency should not replace understanding the train/test boundary.

## Practical lesson for our project

The most important rule is: estimate parameters and solve weights using the training period only, then evaluate the fixed weights on unseen returns. This is the part that makes the comparison meaningful and addresses the professor's concern about generalizable results.
