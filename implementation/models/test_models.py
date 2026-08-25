import unittest

import numpy as np
import pandas as pd

from models import fit_cvar, fit_mvo, fit_robust_mvo, get_model, get_model_config


class ModelAdapterTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.returns = pd.DataFrame(
            rng.normal(0.0003, 0.01, size=(300, 4)),
            columns=["A", "B", "C", "D"],
        )
        self.profile = {"risk_aversion": 5.0, "confidence_level": 0.95, "max_weight": 0.6, "iterations": 300}

    def _assert_valid(self, weights):
        self.assertEqual(list(weights.index), list(self.returns.columns))
        self.assertTrue(np.isfinite(weights.to_numpy()).all())
        self.assertTrue((weights >= -1e-9).all())
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=6)
        self.assertTrue((weights <= 0.6 + 1e-6).all())

    def test_mvo_adapter(self):
        self._assert_valid(fit_mvo(self.returns, self.profile))

    def test_cvar_adapter(self):
        self._assert_valid(fit_cvar(self.returns, self.profile))

    def test_kenta_profile_config_is_adapted(self):
        payload = {
            "profiles": [
                {
                    "category": "Growth",
                    "model_inputs": {
                        "cvar_optimization": {
                            "confidence_level": 0.95,
                            "target_annual_return": 0.12,
                        }
                    },
                }
            ]
        }
        config = get_model_config(payload, "Growth", "cvar_optimization", max_weight=0.35)
        self.assertEqual(config["confidence_level"], 0.95)
        self.assertEqual(config["max_weight"], 0.35)

    def test_mvo_enforces_target_return_and_turnover(self):
        current = pd.Series(0.25, index=self.returns.columns)
        config = {
            "risk_aversion": 5.0,
            "max_weight": 0.6,
            "target_annual_return": -0.07,
            "max_turnover": 0.2,
            "current_weights": current,
        }
        weights = fit_mvo(self.returns, config)
        expected_annual = self.returns.mean() * 252
        self.assertGreaterEqual(float(expected_annual @ weights), -0.07 - 1e-5)
        self.assertLessEqual(float((weights - current).abs().sum()), 0.2 + 1e-5)

    def test_cvar_enforces_target_return_and_turnover(self):
        current = pd.Series(0.25, index=self.returns.columns)
        config = {
            "confidence_level": 0.95,
            "max_weight": 0.6,
            "target_annual_return": -0.07,
            "max_turnover": 0.2,
            "current_weights": current,
        }
        weights = fit_cvar(self.returns, config)
        expected_annual = self.returns.mean() * 252
        self.assertGreaterEqual(float(expected_annual @ weights), -0.07 - 1e-5)
        self.assertLessEqual(float((weights - current).abs().sum()), 0.2 + 1e-5)

    def test_cvar_rejects_infeasible_target(self):
        config = {
            "confidence_level": 0.95,
            "max_weight": 0.6,
            "target_annual_return": 10.0,
        }
        with self.assertRaises(RuntimeError):
            fit_cvar(self.returns, config)

    def test_robust_mvo_adapter(self):
        weights = fit_robust_mvo(
            self.returns,
            {"max_weight": 0.6, "scenario_count": 3, "scenario_window": 120},
        )
        self._assert_valid(weights)

    def test_robust_mvo_enforces_target_and_turnover(self):
        current = pd.Series(0.25, index=self.returns.columns)
        config = {
            "max_weight": 0.6,
            "scenario_count": 3,
            "scenario_window": 120,
            "target_annual_return": -0.07,
            "max_turnover": 0.2,
            "current_weights": current,
        }
        weights = fit_robust_mvo(self.returns, config)
        expected_annual = self.returns.mean() * 252
        self.assertGreaterEqual(float(expected_annual @ weights), -0.07 - 1e-5)
        self.assertLessEqual(float((weights - current).abs().sum()), 0.2 + 1e-5)

    def test_model_registry(self):
        self.assertIs(get_model("ROBUST_MVO"), fit_robust_mvo)
        with self.assertRaises(KeyError):
            get_model("not_a_model")


if __name__ == "__main__":
    unittest.main()
