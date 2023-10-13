"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/13
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Type, Callable
    from .base import PumpController


#: Model registry
_PUMP_MODEL_TO_TYPE: dict[str, Type[PumpController]] = {}

def pump_model(model_name: str) -> Callable:
    """Decorator for registering a controller type with a model name"""
    def decorator(cls: Type[PumpController]) -> Type[PumpController]:
        if model_name in _PUMP_MODEL_TO_TYPE:
            raise ValueError(f"a controller is already registered for '{model_name}'")
        _PUMP_MODEL_TO_TYPE[model_name] = cls
        return cls
    return decorator

def get_controller_for_model(model_name: str) -> Type[PumpController]:
    pump_controller = _PUMP_MODEL_TO_TYPE.get(model_name)
    if pump_controller is None:
        raise KeyError(f"no controller is registered for model '{model_name}'")
    return pump_controller
