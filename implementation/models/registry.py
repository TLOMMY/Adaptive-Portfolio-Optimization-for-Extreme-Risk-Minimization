"""Model registry for the shared integration backtester."""

from __future__ import annotations

from collections.abc import Callable

from .cvar import fit_cvar
from .mvo import fit_mvo
from .robust_mvo import fit_robust_mvo

MODEL_REGISTRY: dict[str, Callable] = {
    "mvo": fit_mvo,
    "markowitz_mean_variance": fit_mvo,
    "cvar": fit_cvar,
    "cvar_optimization": fit_cvar,
    "robust_mvo": fit_robust_mvo,
    "robust_minimum_variance": fit_robust_mvo,
}


def get_model(name: str) -> Callable:
    """Return a registered model or raise a helpful configuration error."""
    try:
        return MODEL_REGISTRY[name.lower()]
    except KeyError as exc:
        choices = ", ".join(sorted(MODEL_REGISTRY))
        raise KeyError(f"unknown model {name!r}; choose one of: {choices}") from exc
