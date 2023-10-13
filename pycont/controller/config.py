"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/10
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional

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

_N_STEP_MODE = {
    Microstep.Mode0 : 1,
    Microstep.Mode2 : 8,
}

class Address(Enum):
    Switch0 = '1'
    Switch1 = '2'
    Switch2 = '3'
    Switch3 = '4'
    Switch4 = '5'
    Switch5 = '6'
    Switch6 = '7'
    Switch7 = '8'
    Switch8 = '9'
    Switch9 = ':'
    SwitchA = ';'
    SwitchB = '<'
    SwitchC = '='
    SwitchD = '>'
    SwitchE = '?'
    SwitchF = '@'
    Broadcast = '_',

    @classmethod
    def from_switch(cls, switch: str) -> Address:
        return _ADDRESS_FROM_SWITCH[switch]

_ADDRESS_FROM_SWITCH = {
    '0' : Address.Switch0,
    '1' : Address.Switch1,
    '2' : Address.Switch2,
    '3' : Address.Switch3,
    '4' : Address.Switch4,
    '5' : Address.Switch5,
    '6' : Address.Switch6,
    '7' : Address.Switch7,
    '8' : Address.Switch8,
    '9' : Address.Switch9,
    'A' : Address.SwitchA,
    'B' : Address.SwitchB,
    'C' : Address.SwitchC,
    'D' : Address.SwitchD,
    'E' : Address.SwitchE,
    'F' : Address.SwitchF,
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
    address: Address
    total_volume: float
    micro_step_mode: Microstep = Microstep.Mode2
    top_velocity: int = 6000
    initialize_valve_position: ValvePosition = ValvePosition.Input
