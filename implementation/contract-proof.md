# Contract Proof

## Data contract

- `compute_returns` validates a positive adjusted-close DataFrame.
- Returns are aligned across all assets and exclude the first undefined row.

## Leakage contract

- `split_train_test` rejects `test_start < train_end`.
- `run_backtest` calls `fit_model(train, profile_config)` before evaluation.
- Test returns are passed only to `evaluate_weights`.

## Output contract

- Metrics are one row per model/profile/evaluation window.
- Weights are long-form one row per asset and window.
- Weights are validated as finite, non-negative, and normalized to one.
