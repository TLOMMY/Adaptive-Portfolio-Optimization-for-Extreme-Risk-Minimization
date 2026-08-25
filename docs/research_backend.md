# Research Backend

The Bowen implementation is a model-independent validation framework. It
accepts adjusted-close prices or aligned simple returns, creates explicit
walk-forward windows, fits a model on the training slice, and evaluates only
the later test slice.

## Main files

- `implementation/portfolio_backtest.py`: windows, return validation,
  rebalancing, metrics, and weight checks.
- `implementation/models/mvo.py`: mean-variance adapter.
- `implementation/models/cvar.py`: historical CVaR adapter.
- `implementation/models/robust_mvo.py`: covariance-uncertainty robust MVO
  adapter used for research comparison.
- `implementation/models/profile_config.py`: investor constraints and profile
  inputs.
- `implementation/models/registry.py`: common model lookup interface.
- `implementation/yesh_backend_contract.md`: the JSON contract that would be
  used if a future exporter regenerated the website data.

## Conventions

Weights are long-only and fully invested unless a profile explicitly reserves
cash. Returns are daily simple returns and annualisation uses 252 trading
periods. A model never receives test-period observations during fitting. An
infeasible profile is reported explicitly rather than silently relaxed.

Run the tests from the repository root:

```powershell
python -m unittest discover -s implementation -p "test_*.py"
```

The current code is a research/validation artifact. It does not replace the
frozen AMPL configurations or the static JSON already used by the Netlify
presentation.
