"""Model adapters for the shared portfolio backtester."""

from .mvo import fit_mvo
from .cvar import fit_cvar
from .profile_config import get_model_config, load_profile_export
from .registry import MODEL_REGISTRY, get_model
from .robust_mvo import fit_robust_mvo

__all__ = [
    "fit_mvo", "fit_cvar", "fit_robust_mvo", "MODEL_REGISTRY", "get_model",
    "get_model_config", "load_profile_export",
]
