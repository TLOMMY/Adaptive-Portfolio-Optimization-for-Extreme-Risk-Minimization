"""Registry of portfolio models.  Order here is the order the site shows them."""

from __future__ import annotations

from .base import Model
from .cvar import CvarModel
from .equal import EqualWeightModel
from .markowitz import MarkowitzModel
from .robust import RobustModel

MODELS: dict[str, Model] = {
    m.key: m
    for m in [
        CvarModel(),
        MarkowitzModel("sample"),
        MarkowitzModel("ledoit_wolf"),
        RobustModel(),
        EqualWeightModel(),
    ]
}
STORY_MODEL = "cvar"        # the model the narrative part of the site runs on


def get_model(key: str) -> Model:
    try:
        return MODELS[key]
    except KeyError:
        raise KeyError(f"unknown model {key!r}; choose from {list(MODELS)}") from None


def model_meta(m: Model) -> dict:
    return {"key": m.key, "name": m.name, "blurb": m.blurb, "solver": m.solver}


__all__ = ["Model", "MODELS", "STORY_MODEL", "get_model", "model_meta"]
