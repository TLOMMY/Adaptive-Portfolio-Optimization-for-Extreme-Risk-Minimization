# Team Progress Update

Thank you to everyone for the progress so far.

- **Kenta and Jia Qi:** designed the investor-profile decision factors and
  translated them into transparent model parameters for Growth, Balanced,
  Retirement, and Extreme Low Risk categories.
- **Mana:** implemented the initial MVO and historical-CVaR prototypes on the
  NVDA/AMD example data. I have integrated both formulations into shared
  adapters and added hard-constraint validation while preserving her model
  ownership for review.
- **Yesh:** built the interactive time-travel portfolio demo and the more
  complete AMPL/HiGHS backend, including profile constraints, walk-forward
  rebalancing, metrics, and the static JSON export consumed by the webpage.
- **Bowen:** integrated the data/backtest interface, no-look-ahead train/test
  boundary, equal-weight baseline, profile-config adapter, and constrained
  MVO/CVaR adapters. The local test suite now has 12 passing tests, and the
  three evaluation-period synthetic integration benchmark runs successfully.

## Remaining work before final output

1. Lock the shared universe, date range, adjusted-close/simple-return
   convention, and profile parameter table.
2. Run real-data walk-forward experiments over several market periods, with
   a separate evaluation segment for every period.
3. Decide whether Yesh's AMPL optimizer is the primary constrained strategy
   and show MVO/CVaR as comparable model outputs.
4. Export all model/profile results through the agreed static JSON contract
   and connect them to the existing webpage.
5. Verify charts, units, solver status, disclaimer, and final claims; then
   merge branches and rehearse the presentation.

The current synthetic benchmark is an engineering check only. It does not
support a claim that one strategy is financially superior.
