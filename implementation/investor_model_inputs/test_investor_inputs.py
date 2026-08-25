import tempfile
import unittest
from pathlib import Path

from investor_inputs import DEFAULT_PROFILES, convert_profile, export_examples


class InvestorInputsTest(unittest.TestCase):
    def test_growth_conversion(self) -> None:
        result = convert_profile("Growth", DEFAULT_PROFILES["Growth"])
        self.assertAlmostEqual(
            sum(result["normalized_preference_weights"].values()), 1.0, places=5
        )
        markowitz = result["model_inputs"]["markowitz_mean_variance"]
        self.assertEqual(markowitz["target_annual_return"], 0.12)
        self.assertEqual(markowitz["risk_aversion"], 5.0)
        self.assertEqual(markowitz["max_turnover"], 1.0)

    def test_retirement_is_more_conservative(self) -> None:
        growth = convert_profile("Growth", DEFAULT_PROFILES["Growth"])
        retirement = convert_profile("Retirement", DEFAULT_PROFILES["Retirement"])
        self.assertGreater(
            retirement["model_inputs"]["markowitz_mean_variance"]["risk_aversion"],
            growth["model_inputs"]["markowitz_mean_variance"]["risk_aversion"],
        )
        self.assertLess(
            retirement["model_inputs"]["cvar_optimization"]["max_turnover"],
            growth["model_inputs"]["cvar_optimization"]["max_turnover"],
        )

    def test_exports_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            json_path, csv_path = export_examples(directory)
            self.assertTrue(Path(json_path).is_file())
            self.assertTrue(Path(csv_path).is_file())


if __name__ == "__main__":
    unittest.main()
