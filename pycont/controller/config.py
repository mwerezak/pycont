"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/10
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Union

class ValvePosition(Enum):
    Input = 'I'
    Output = 'O'
    Bypass = 'B'
    Extra = 'E'

    One = '1'
    Two = '2'
    Three = '3'
    Four = '4'
    Five = '5'
    Six = '6'

    def __eq__(self, other: Union[str, ValvePosition]) -> bool:
        if isinstance(other, str):
            return self.value == other
        return super().__eq__(other)

    def is_6way(self) -> bool:
        return self.value in _VALVE_6WAY_LIST

    @classmethod
    def try_decode(cls, raw_pos: str) -> Optional[ValvePosition]:
        result = _DECODE_POSITION.get(raw_pos)
        if result is not None:
            return result
        if raw_pos in _VALVE_6WAY_LIST:
            return cls(raw_pos)
        return None

_DECODE_POSITION = {
    'i' : ValvePosition.Input,
    'o' : ValvePosition.Output,
    'b' : ValvePosition.Bypass,
    'e' : ValvePosition.Extra,
}

#: 6 way valve
_VALVE_6WAY_LIST = ('1', '2', '3', '4', '5', '6')

class Microstep(Enum):
    Mode0 = 0
    Mode2 = 2

    def number_of_steps(self) -> int:
        return _N_STEP_MODE[self]

    def max_top_velocity(self) -> int:
        return _MAX_TOP_VELOCITY[self]

_N_STEP_MODE = {
    Microstep.Mode0 : 3000,
    Microstep.Mode2 : 24000,
}

_MAX_TOP_VELOCITY = {
    Microstep.Mode0 : 6000,
    Microstep.Mode2 : 48000,
}

@dataclass(frozen=True, kw_only=True)
class PumpConfig:
    """
    name: The name of the controller.
    address: Address of the controller.
    total_volume: Total volume of the pump.
    micro_step_mode: The mode which the microstep will use, default set to MICRO_STEP_MODE_2 (2)
    top_velocity: The top velocity of the pump, default set to 6000
    initialize_valve_position: Sets the valve position, default set to VALVE_INPUT ('I')
    """

    name: str
    address: str
    total_volume: float
    micro_step_mode: Microstep = Microstep.Mode2
    top_velocity: int = 6000
    initialize_valve_position: ValvePosition = ValvePosition.Input
