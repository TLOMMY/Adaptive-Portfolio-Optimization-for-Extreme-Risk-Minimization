# Discovery Brief

## Scope

The current weekend task is Bowen's implementation slice for the portfolio project:

- standardize prices and returns;
- separate training data from evaluation data;
- provide an equal-weight baseline;
- calculate common out-of-sample metrics;
- expose a model-independent interface for Mana's optimizer.

The workspace contains literature notes, but no existing portfolio implementation. The new code is therefore isolated in `implementation/` and uses only pandas and NumPy at runtime.

## Explicit non-goals

- selecting investor-factor weights;
- implementing CVaR or Robust MVO;
- building a Streamlit UI;
- claiming that any strategy is universally superior;
- using future observations while fitting weights.

## Interface assumption

Every optimizer should eventually provide a callable with the shape:

```python
weights = model.fit(train_returns, profile_config)
```

The backtest evaluates the returned weights only on the later test period.
