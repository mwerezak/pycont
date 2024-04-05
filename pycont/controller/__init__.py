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

from ..config import Microstep, ValveSet

from .base import PumpController, MaxRetriesExceededError, PumpHardwareError


## C-Series

C_SERIES_VALVES = {
    ValveSet.ThreePortY      : 1,
    ValveSet.FourPort90      : 2,
    ValveSet.ThreeWayDist    : 11,
    ValveSet.ThreeWayDistIOE : 4,
    ValveSet.TValve90        : 5,
    ValveSet.SixWayDist      : 7,
    ValveSet.FourPortLoop    : 9,
}

@pump_model('C3000')
class C3000Controller(PumpController):
    valve_set_config = C_SERIES_VALVES

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


@pump_model('C24000')
class C24000Controller(PumpController):
    """Untested!"""

    valve_set_config = C_SERIES_VALVES

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


## CX-Series

CX_SERIES_VALVES = {
    ValveSet.ThreePortY        : 1,
    ValveSet.FourPort90        : 2,
    ValveSet.ThreeWayDistLarge : 3,
    ValveSet.ThreeWayDist      : 11,
    ValveSet.ThreeWayDistIOE   : 4,
    ValveSet.TValve90          : 5,
    ValveSet.SixWayDist        : 7,
    ValveSet.FourPortLoop      : 9,
}

@pump_model('CX6000')
class CX6000Controller(PumpController):
    valve_set_config = CX_SERIES_VALVES

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


@pump_model('CX48000')
class CX48000Controller(PumpController):
    """Untested!"""

    valve_set_config = CX_SERIES_VALVES

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS[type(self)] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


## Seems to be common to both C/CX series pumps

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
