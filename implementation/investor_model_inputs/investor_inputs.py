"""Convert investor priority scores into portfolio-model input parameters.

The score-to-parameter mappings are explicit scenario assumptions for a
demonstration. They are not statistically estimated investor preferences.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping


FACTOR_NAMES = ("return_requirement", "risk_protection", "liquidity_turnover")

DEFAULT_PROFILES: dict[str, dict[str, int]] = {
    "Growth": {
        "return_requirement": 3,
        "risk_protection": 2,
        "liquidity_turnover": 1,
    },
    "Balanced": {
        "return_requirement": 2,
        "risk_protection": 2,
        "liquidity_turnover": 2,
    },
    "Retirement": {
        "return_requirement": 1,
        "risk_protection": 3,
        "liquidity_turnover": 3,
    },
    "Extreme Low Risk": {
        "return_requirement": 1,
        "risk_protection": 3,
        "liquidity_turnover": 2,
    },
}

# Transparent demonstration assumptions. Edit these tables for another scenario.
SCENARIO_MAPPINGS: dict[str, dict[int, float]] = {
    "target_annual_return": {1: 0.04, 2: 0.08, 3: 0.12},
    "markowitz_risk_aversion": {1: 1.0, 2: 5.0, 3: 10.0},
    "cvar_confidence_level": {1: 0.90, 2: 0.95, 3: 0.99},
    "robust_uncertainty_radius": {1: 0.05, 2: 0.10, 3: 0.20},
    "max_turnover": {1: 1.00, 2: 0.50, 3: 0.20},
}


def _validate_scores(scores: Mapping[str, int]) -> None:
    missing = set(FACTOR_NAMES) - set(scores)
    extra = set(scores) - set(FACTOR_NAMES)
    if missing or extra:
        raise ValueError(
            f"Scores must contain exactly {FACTOR_NAMES}; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for factor, value in scores.items():
        if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3):
            raise ValueError(f"{factor} must be an integer score in {{1, 2, 3}}")


def normalized_weights(scores: Mapping[str, int]) -> dict[str, float]:
    """Normalize the three ordinal scores so that their weights sum to one."""
    _validate_scores(scores)
    total = sum(scores.values())
    return {factor: round(scores[factor] / total, 6) for factor in FACTOR_NAMES}


def convert_profile(category: str, scores: Mapping[str, int]) -> dict[str, Any]:
    """Return shared metadata and model-ready dictionaries for one category."""
    _validate_scores(scores)
    return_score = scores["return_requirement"]
    risk_score = scores["risk_protection"]
    turnover_score = scores["liquidity_turnover"]

    shared_constraints = {
        "target_annual_return": SCENARIO_MAPPINGS["target_annual_return"][return_score],
        "max_turnover": SCENARIO_MAPPINGS["max_turnover"][turnover_score],
        "long_only": True,
        "fully_invested": True,
    }

    return {
        "category": category,
        "priority_scores": {factor: scores[factor] for factor in FACTOR_NAMES},
        "normalized_preference_weights": normalized_weights(scores),
        "model_inputs": {
            "markowitz_mean_variance": {
                "objective": "maximize_mean_variance_utility",
                "risk_aversion": SCENARIO_MAPPINGS["markowitz_risk_aversion"][risk_score],
                **shared_constraints,
                "required_market_inputs": [
                    "expected_annual_returns",
                    "annual_covariance_matrix",
                    "current_weights",
                ],
            },
            "cvar_optimization": {
                "objective": "minimize_cvar",
                "confidence_level": SCENARIO_MAPPINGS["cvar_confidence_level"][risk_score],
                **shared_constraints,
                "required_market_inputs": [
                    "historical_or_simulated_return_scenarios",
                    "current_weights",
                ],
            },
            "robust_minimum_variance": {
                "objective": "minimize_worst_case_variance",
                "covariance_uncertainty_radius": SCENARIO_MAPPINGS[
                    "robust_uncertainty_radius"
                ][risk_score],
                **shared_constraints,
                "required_market_inputs": [
                    "expected_annual_returns",
                    "annual_covariance_matrix",
                    "current_weights",
                    "uncertainty_set_calibration_data",
                ],
            },
        },
    }


def build_all_profiles(
    profiles: Mapping[str, Mapping[str, int]] = DEFAULT_PROFILES,
) -> dict[str, Any]:
    """Build the complete, versioned export object."""
    return {
        "schema_version": "1.0",
        "units": {
            "target_annual_return": "decimal annual rate",
            "max_turnover": "sum(abs(new_weight - current_weight))",
        },
        "scenario_mappings": SCENARIO_MAPPINGS,
        "profiles": [convert_profile(category, scores) for category, scores in profiles.items()],
    }


def _flatten_for_csv(profile: Mapping[str, Any], model_name: str) -> dict[str, Any]:
    scores = profile["priority_scores"]
    weights = profile["normalized_preference_weights"]
    params = profile["model_inputs"][model_name]
    row: dict[str, Any] = {
        "category": profile["category"],
        "model": model_name,
        **{f"score_{key}": value for key, value in scores.items()},
        **{f"weight_{key}": value for key, value in weights.items()},
    }
    for key, value in params.items():
        row[key] = "|".join(value) if isinstance(value, list) else value
    return row


def export_examples(output_dir: str | Path) -> tuple[Path, Path]:
    """Export nested JSON and flat CSV files."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    payload = build_all_profiles()

    json_path = destination / "model_inputs.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )

    rows = [
        _flatten_for_csv(profile, model_name)
        for profile in payload["profiles"]
        for model_name in profile["model_inputs"]
    ]
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    csv_path = destination / "model_inputs.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="examples",
        help="Directory for model_inputs.json and model_inputs.csv",
    )
    args = parser.parse_args()
    json_path, csv_path = export_examples(args.output_dir)
    print(f"Created {json_path}")
    print(f"Created {csv_path}")


if __name__ == "__main__":
    main()
