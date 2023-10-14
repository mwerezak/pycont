"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/10
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .io import SerialConfig, SocketConfig
from ._models import get_controller_for_model

if TYPE_CHECKING:
    from typing import Union, Optional, Type
    from collections.abc import Collection
    from .io import PumpIO
    from .controller import PumpController

class ValvePosition(Enum):
    Input = 'i'
    Output = 'o'
    Bypass = 'b'
    Extra = 'e'

    One = '1'
    Two = '2'
    Three = '3'
    Four = '4'
    Five = '5'
    Six = '6'

    def is_6way(self) -> bool:
        return self in _VALVE_6WAY_LIST

    @classmethod
    def get_6way_position(cls, pos_num: int) -> ValvePosition:
        """Get the corresponding 6-way valve position for integers 1..6"""
        return _VALVE_6WAY_LIST[pos_num - 1]

    @classmethod
    def try_decode(cls, raw_pos: str) -> Optional[ValvePosition]:
        if raw_pos in cls.__members__ .values():
            return cls(raw_pos)
        return None

#: 6 way valve
_VALVE_6WAY_LIST = (
    ValvePosition.One,
    ValvePosition.Two,
    ValvePosition.Three,
    ValvePosition.Four,
    ValvePosition.Five,
    ValvePosition.Six,
)


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
    model: str
    address: Address
    total_volume: float
    micro_step_mode: Microstep = Microstep.Mode2
    top_velocity: int = 6000
    initialize_valve_position: ValvePosition = ValvePosition.Input

    @classmethod
    def from_dict(cls, pump_name: str, pump_config: dict) -> PumpConfig:
        pump_config['address'] = Address.from_switch(pump_config.pop('switch'))
        pump_config['total_volume'] = float(pump_config.pop('volume'))
        return cls(name = pump_name, **pump_config)

    def get_controller_type(self) -> Type[PumpController]:
        """Lookup the controller type based on the pump model."""
        return get_controller_for_model(self.model)

    def create_pump(self, pump_io: PumpIO) -> PumpController:
        """Construct a pump controller from this config."""
        pump_controller = self.get_controller_type()
        return pump_controller(pump_io, self)


@dataclass(frozen=True)
class BusConfig:
    io_config: Union[SerialConfig, SocketConfig]
    pumps: Collection[PumpConfig]

    @classmethod
    def from_dict(cls, bus_config: dict, pump_defaults: dict = None) -> BusConfig:
        pumps = []
        for pump_name, pump_config in bus_config['pumps'].items():
            full_pump_config = {} if pump_defaults is None else dict(pump_defaults)
            full_pump_config.update(pump_config)
            pumps.append(PumpConfig.from_dict(pump_name, full_pump_config))

        return cls(
            io_config = cls._io_config_from_dict(bus_config['io']),
            pumps = tuple(pumps),
        )

    @staticmethod
    def _io_config_from_dict(io_config: dict) -> Union[SocketConfig, SerialConfig]:
        io_type = io_config.pop('type') if 'type' in io_config else 'serial'
        if io_type == 'serial':
            return SerialConfig(**io_config)
        elif io_type == 'socket':
            return  SocketConfig(**io_config)
        else:
            raise ValueError("unsupported I/O type: " + io_type)
