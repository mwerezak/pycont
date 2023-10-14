"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/10
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .._logger import create_logger
from ..config import ValvePosition
from ..io import PumpIO, PumpIOTimeOutError

from . import PumpController
from .multipump import MultiPumpController

from ..io import (
    DEFAULT_IO_TIMEOUT,
    DEFAULT_IO_BAUDRATE,
)

from .base import (
    MAX_REPEAT_WRITE_AND_READ,
    MAX_REPEAT_OPERATION,
)

if TYPE_CHECKING:
    pass


class VirtualPumpIO(PumpIO):
    def open(self, port, baudrate=DEFAULT_IO_BAUDRATE, timeout=DEFAULT_IO_TIMEOUT):
        self._serial = None

    def close(self):
        pass

    def flushInput(self):
        pass

    def write(self, packet):
        str_to_send = packet.to_string()
        self.logger.debug("Virtually sending {}".format(str_to_send))

    def readline(self):
        raise PumpIOTimeOutError

    def write_and_readline(self, packet):
        raise PumpIOTimeOutError




class VirtualController(PumpController):

    @property
    def max_top_velocity(self) -> int:
        return 6000

    @property
    def number_of_steps(self) -> int:
        return 3000

    def initialize(self, valve_position=None, max_repeat=MAX_REPEAT_OPERATION, secure=True):
        raise NotImplementedError

    def initialize_valve_right(self, operand_value=0, wait=True):
        raise NotImplementedError

    def initialize_valve_left(self, operand_value=0, wait=True):
        raise NotImplementedError

    def initialize_no_valve(self, operand_value=0, wait=True):
        raise NotImplementedError

    def initialize_valve_only(self, operand_string='0,0', wait=True):
        raise NotImplementedError

    def is_idle(self):
        return True

    def is_busy(self):
        return False

    def is_initialized(self):
        return True

    def init_all_pump_parameters(self, secure=True):
        pass

    def set_microstep_mode(self, micro_step_mode):
        pass

    def set_top_velocity(self, top_velocity, max_repeat=MAX_REPEAT_OPERATION, secure=True):
        pass

    def get_top_velocity(self):
        return 10000

    def get_plunger_position(self):
        return 0

    def pump(self, volume_in_ml, from_valve=None, speed_in=None, wait=False, secure=True):
        pass

    def deliver(self, volume_in_ml, to_valve=None, speed_out=None, wait=False, secure=True):
        pass

    def go_to_volume(self, volume_in_ml, speed=None, wait=False, secure=True):
        return True

    def go_to_max_volume(self, speed=None, wait=False):
        return True

    current_valve_position: ValvePosition
    def get_valve_position(self, max_repeat=MAX_REPEAT_OPERATION):
        if self.current_valve_position is not None:
            return self.current_valve_position
        else:
            return ValvePosition.Input

    def set_valve_position(self, valve_position, max_repeat=MAX_REPEAT_OPERATION, secure=True):
        self.current_valve_position = valve_position
        return True

    def set_eeprom_config(self, operand_value):
        pass

    def get_eeprom_config(self):
        return None


class VirtualMultiPumpController(MultiPumpController):
    def __init__(self, setup_config):
        self.logger = create_logger(self.__class__.__name__)
        self.pumps = {}
        self._io = []

        # Sets groups and default configs if provided in the config dictionary
        self.groups = setup_config['groups'] if 'groups' in setup_config else {}
        self.default_config = setup_config['default'] if 'default' in setup_config else {}

        if "hubs" in setup_config:  # This implements the "new" behaviour with multiple hubs
            for hub_config in setup_config["hubs"]:
                # Each hub has its own I/O config. Create a PumpIO object per each hub and reuse it with -1 after append
                self._io.append(VirtualPumpIO.from_config(hub_config['io']))
                for pump_name, pump_config in list(hub_config['pumps'].items()):
                    full_pump_config = self._default_pump_config(pump_config)
                    self.pumps[pump_name] = VirtualC3000Controller.from_config(self._io[-1], pump_name, full_pump_config)
        else:  # This implements the "old" behaviour with one hub per object instance / json file
            self._io = VirtualPumpIO.from_config(setup_config['io'])
            for pump_name, pump_config in list(setup_config['pumps'].items()):
                full_pump_config = self._default_pump_config(pump_config)
                self.pumps[pump_name] = VirtualC3000Controller.from_config(self._io, pump_name, full_pump_config)

        self.set_pumps_as_attributes()

    def smart_initialize(self, secure=True):
        pass
