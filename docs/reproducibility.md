# Reproducibility

## Research checks

```powershell
python -m unittest discover -s implementation -p "test_*.py"
```

The research adapters require NumPy, pandas, SciPy, CVXPY, and one of the
configured open-source solvers. See `implementation/requirements.txt`.

## Website checks

```powershell
cd site
npm ci
npm run check
npm run build
```

The build consumes the committed static data under `site/static/data`; it does
not call a live market-data API. This is deliberate: the final demonstration
must replay the same figures for every presenter.
