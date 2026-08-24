# Copy-ready Team Messages

## Message to Yeshwanth

Hi Yeshwanth, to avoid overlap I will own the executable backtesting layer: price/return preprocessing, explicit train-test windows, equal-weight baseline, metric calculations, and the generic `run_backtest` interface. I will not decide the investor-factor values, model assumptions, or real-world MVO modifications. Could you own the convention sheet: asset universe, lookback/test/rebalance rules, long-only and max-weight constraints, transaction-cost assumption, annualization factor, and the definition of each metric? Once you confirm those conventions, I will encode them and keep the code model-independent so Mana can plug in her optimizer.

## Message to Mana

Hi Mana, I suggest using constrained MVO as the common baseline first, then implementing CVaR as the extension if you want a model focused on extreme downside risk. MVO is convex, transparent, and gives us a reliable reference for comparing any new model. CVaR is more aligned with our project title because it directly targets tail losses, but it needs a clear loss-scenario and confidence-level definition. Robust MVO is interesting but requires an explicit uncertainty set for returns/covariance and is the hardest to make reproducible in a short time. Please provide a model adapter that uses training returns only and returns one labelled weight per asset; I will plug it into the backtester and evaluate it on unseen test data.
