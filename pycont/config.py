"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/10
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .pump_protocol import Address, ValvePosition
from ._models import get_controller_for_model

if TYPE_CHECKING:
    from typing import Any, Type
    from collections.abc import Collection
    from .io import PumpIO
    from .controller import PumpController


class Microstep(Enum):
    Mode0 = 0
    Mode2 = 2

    def number_of_steps(self) -> int:
        return _N_STEP_MODE[self]

_N_STEP_MODE = {
    Microstep.Mode0 : 1,
    Microstep.Mode2 : 8,
}


@dataclass(frozen=True, kw_only=True)
class PumpConfig:
    """
    name: The name of the controller.
    address: Address of the controller.
    total_volume: Total volume of the pump.
    micro_step_mode: The mode which the microstep will use, default set to MICRO_STEP_MODE_2 (2)
    top_velocity: The top velocity of the pump, default set to 6000
    init_valve_pos: Sets the valve position, default set to VALVE_INPUT ('I')
    """

    name: str
    model: str
    address: Address
    total_volume: float
    micro_step_mode: Microstep = Microstep.Mode2
    top_velocity: int = 6000
    init_valve_pos: ValvePosition = ValvePosition.Input

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
class IOConfig:
    """See :meth:`PumpIO.from_config`"""
    io_type: str
    options: tuple[tuple[str, Any]]

@dataclass(frozen=True)
class BusConfig:
    io_config: IOConfig
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
    def _io_config_from_dict(io_config: dict) -> IOConfig:
        io_type = io_config.pop('type') if 'type' in io_config else 'serial'
        # noinspection PyTypeChecker
        return IOConfig(
            io_type,
            tuple(io_config.items()),
        )
