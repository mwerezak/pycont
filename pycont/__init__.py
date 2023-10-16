"""
Custom library designed to control Tricontinent C-series syringe pumps.

.. moduleauthor:: Jonathan Grizou <Jonathan.Grizou@gla.ac.uk>

"""
from ._logger import __logger_root_name__
from .config import ValvePosition, Microstep, PumpConfig, Address
from .controller import C3000Controller, C24000Controller, CX6000Controller, CX48000Controller, PumpController
from .controller.multipump import MultiPumpController

import logging
logging.getLogger(__logger_root_name__).addHandler(logging.NullHandler())
