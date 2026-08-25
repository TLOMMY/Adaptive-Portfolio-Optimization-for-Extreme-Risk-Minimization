"""Adapt Kenta's exported profile schema to model adapter configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_profile_export(path: str | Path) -> Mapping[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def get_model_config(
    payload: Mapping[str, Any],
    category: str,
    model_name: str,
    *,
    max_weight: float,
    iterations: int = 1000,
) -> dict[str, object]:
    """Return a model config while making missing constraints explicit.

    `max_weight` is supplied by the final experiment convention because the
    current Kenta export does not yet contain an asset-concentration limit.
    The model adapter or backtester supplies `current_weights` at runtime;
    this export intentionally remains independent of a particular portfolio.
    """

    profiles = payload.get("profiles", [])
    profile = next((item for item in profiles if item.get("category") == category), None)
    if profile is None:
        raise KeyError(f"profile not found: {category}")
    params = profile.get("model_inputs", {}).get(model_name)
    if params is None:
        raise KeyError(f"model not found for {category}: {model_name}")
    config = dict(params)
    config["max_weight"] = float(max_weight)
    config["iterations"] = int(iterations)
    return config
