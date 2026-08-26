# Poster

A0 landscape academic poster, built with LaTeX (`tikzposter`). Everything here is
derived from the backtest grid in `site/static/data/runs/`.

## Build

Run from the repo root.

```bash
# 1. Experiments (~2 min): regime sub-periods + block bootstrap + correlation matrices
#    -> poster/experiments/out/  (gitignored, regenerable)
uv run python poster/experiments/run_experiments.py

# 2. Figures and the summary table  -> poster/figures/
uv run python poster/experiments/make_figures.py

# 3. The PDF  -> poster/poster.pdf
cd poster && latexmk -pdf poster.tex && latexmk -c
```

Step 3 alone is enough after editing `poster.tex`; rerun steps 1–2 only when the
backtest runs change. Pass a number to step 1 for a quick smoke test
(`run_experiments.py 20`).

Optional preview PNG (macOS): `sips -s format png -Z 2400 poster.pdf --out preview.png`

## Requirements

- TeX Live with `tikzposter`, `pgfplots`, `booktabs`, `qrcode`, `enumitem` (all in a full TeX Live).
- The project's Python environment (`uv sync`); figures use matplotlib, already a dependency via quantstats.

## Layout

| File | What |
|---|---|
| `poster.tex` | The poster. Placeholders left: site URL in the QR code (`\qrcode{...}`). |
| `figures/` | Generated PDFs/PNGs + `table_models.tex`; committed so the poster builds without rerunning experiments. |
| `experiments/run_experiments.py` | Sub-period metrics, stationary block bootstrap (paired across runs), correlation heatmap data. Excludes Sprinter (3-year horizon). |
| `experiments/make_figures.py` | All figures and the LaTeX table. |
