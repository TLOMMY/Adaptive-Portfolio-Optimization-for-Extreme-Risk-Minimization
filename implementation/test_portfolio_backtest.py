import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from portfolio_backtest import (
    BacktestWindow,
    compute_returns,
    equal_weight_model,
    evaluate_weights,
    run_backtest,
    split_train_test,
)
from data_pipeline import build_market_period_windows, load_adjusted_close_csv, save_adjusted_close_csv
from day2_baseline import run_equal_weight_baseline


class PortfolioBacktestTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range("2020-01-01", periods=12, freq="D")
        self.prices = pd.DataFrame(
            {
                "AAA": np.linspace(100, 111, len(dates)),
                "BBB": np.linspace(100, 106, len(dates)),
            },
            index=dates,
        )
        self.returns = compute_returns(self.prices)

    def test_train_test_ranges_do_not_overlap(self):
        train, test = split_train_test(
            self.returns,
            self.returns.index[0],
            self.returns.index[4],
            self.returns.index[4],
            self.returns.index[-1],
        )
        self.assertEqual(len(train.index.intersection(test.index)), 0)

    def test_overlapping_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            split_train_test(
                self.returns,
                self.returns.index[0],
                self.returns.index[5],
                self.returns.index[4],
                self.returns.index[-1],
            )

    def test_equal_weight_metrics_use_test_data(self):
        test = self.returns.iloc[4:]
        metrics = evaluate_weights(equal_weight_model(self.returns.iloc[:4]), test)
        self.assertAlmostEqual(metrics["test_observations"], len(test))
        self.assertTrue(np.isfinite(metrics["sharpe_ratio"]))

    def test_backtest_returns_standard_tables(self):
        window = BacktestWindow(
            "demo",
            self.returns.index[0],
            self.returns.index[4],
            self.returns.index[4],
            self.returns.index[-1],
        )
        metrics, weights = run_backtest(
            self.returns,
            [window],
            equal_weight_model,
            model_name="equal_weight",
            profile_name="balanced",
        )
        self.assertEqual(len(metrics), 1)
        self.assertEqual(set(weights["asset"]), {"AAA", "BBB"})
        self.assertAlmostEqual(float(weights["weight"].sum()), 1.0)
        self.assertEqual(metrics.loc[0, "model"], "equal_weight")

    def test_fit_model_never_receives_test_rows(self):
        window = BacktestWindow(
            "leakage_check",
            self.returns.index[0],
            self.returns.index[4],
            self.returns.index[4],
            self.returns.index[-1],
        )
        observed = {}

        def spy_model(train_returns, profile_config):
            del profile_config
            observed["last_train_date"] = train_returns.index.max()
            return equal_weight_model(train_returns)

        metrics, _ = run_backtest(
            self.returns,
            [window],
            spy_model,
            model_name="spy",
        )
        self.assertLess(observed["last_train_date"], metrics.loc[0, "test_start"])

    def test_csv_round_trip_and_multiple_period_baseline(self):
        dates = pd.date_range("2014-01-01", periods=2500, freq="D")
        prices = pd.DataFrame(
            {
                "AAA": 100.0 * (1.0001 ** np.arange(len(dates))),
                "BBB": 100.0 * (1.0002 ** np.arange(len(dates))),
            },
            index=dates,
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            save_adjusted_close_csv(prices, path)
            loaded = load_adjusted_close_csv(path)
            self.assertEqual(list(loaded.columns), ["AAA", "BBB"])
            returns = compute_returns(loaded)
            windows = build_market_period_windows(
                returns,
                [("period_a", "2018-01-01", "2018-03-31"), ("period_b", "2019-01-01", "2019-03-31")],
                train_years=2,
            )
            self.assertEqual(len(windows), 2)
            metrics, weights = run_equal_weight_baseline(
                loaded,
                [("period_a", "2018-01-01", "2018-03-31"), ("period_b", "2019-01-01", "2019-03-31")],
                train_years=2,
            )
            self.assertEqual(len(metrics), 2)
            self.assertEqual(len(weights), 4)


if __name__ == "__main__":
    unittest.main()
