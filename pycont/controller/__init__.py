"""
.. module:: controller
   :platform: Unix
   :synopsis: A module used for controlling the pumps.

.. moduleauthor:: Jonathan Grizou <Jonathan.Grizou@gla.ac.uk>
.. moduleauthor:: Mike Werezak <Mike.Werezak@nrcan-rncan.gc.ca>

"""

# -*- coding: utf-8 -*-

from __future__ import annotations

from .._models import pump_model

from ..config import Microstep

from .base import PumpController, MaxRetriesExceededError, PumpHardwareError


@pump_model('C3000')
class C3000Controller(PumpController):
    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


@pump_model('C24000')
class C24000Controller(PumpController):
    """Untested!"""

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


@pump_model('CX6000')
class CX6000Controller(PumpController):
    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


@pump_model('CX48000')
class CX48000Controller(PumpController):
    """Untested!"""

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


# seems to be common to both C/CX series pumps
COMMON_MAX_TOP_VELOCITY = {
    Microstep.Mode0 : 6000,
    Microstep.Mode2 : 48000,
}

N_STEP_INCREMENTS = {
    C3000Controller   :  3000,
    C24000Controller  : 24000,
    CX6000Controller  :  6000,
    CX48000Controller : 48000,
}
