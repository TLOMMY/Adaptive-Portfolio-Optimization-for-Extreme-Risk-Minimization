# Model Convention Sheet (to be completed by Yeshwanth)

This sheet keeps all model comparisons controlled by the same assumptions.

| Item | Proposed default | Owner / decision |
|---|---|---|
| Asset universe | 6-9 liquid ETFs | Team |
| Price field | Adjusted close | Team |
| Return frequency | Daily simple returns | Bowen encodes |
| Annualization | 252 trading days | Yeshwanth confirms |
| Training window | 1-3 years | Yeshwanth confirms |
| Evaluation window | 3-6 months | Yeshwanth confirms |
| Rebalance rule | Fixed quarterly or explicit windows | Yeshwanth confirms |
| Short selling | Disabled | Team |
| Full investment | Weights sum to 1 | Team |
| Maximum weight | To be fixed by profile | Kenta / Jia |
| Transaction costs | Zero for first pass, sensitivity later | Team |
| Primary metrics | Volatility, max drawdown, Sharpe, CVaR | Team |
| Model comparison | Equal weight, constrained MVO, selected extension | Mana / Bowen |

Do not change these values for one model only. Any change must be recorded and applied consistently to every comparison.
