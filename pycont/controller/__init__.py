"""
.. module:: controller
   :platform: Unix
   :synopsis: A module used for controlling the pumps.

.. moduleauthor:: Jonathan Grizou <Jonathan.Grizou@gla.ac.uk>
.. moduleauthor:: Mike Werezak <Mike.Werezak@nrcan-rncan.gc.ca>

"""

# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Union, Optional, Any

import serial
import threading

from .._logger import create_logger

from ..socket_bridge import SocketBridge

#: Represents the Broadcast of the C3000
from ..dtprotocol import DTInstructionPacket

from .config import ValvePosition, Microstep, PumpConfig, Address
from .base import PumpController, ControllerRepeatedError, PumpHWError


#: default Input/Output (I/O) Baudrate
DEFAULT_IO_BAUDRATE = 9600
#: Default timeout for I/O operations
DEFAULT_IO_TIMEOUT = 1


class PumpIO:
    """
    This class deals with the pump I/O instructions.
    """

    _serial: Optional[Union[serial.serialposix.Serial, serial.serialwin32.Serial, SocketBridge]]

    def __init__(self):
        self.logger = create_logger(self.__class__.__name__)

        self.lock = threading.Lock()

        self._serial = None

    @classmethod
    def from_config(cls, io_config: Dict) -> 'PumpIO':
        """
        Sets details laid out in the configuration .json file

        Args:
            cls: The initialising class.

            io_config: Dictionary holding the configuration data.
                port: The device name (depending on operating system. e.g. /dev/ttyUSB0 on GNU/Linux or COM3 on Windows.)
                baudrate: Baudrate of the communication, default set to DEFAULT_IO_BAUDRATE(9600)
                timeout: The timeout of communication, default set to DEFAULT_IO_TIMEOUT(1)

        Returns:
            PumpIO: New PumpIO object with the variables set from the configuration file.

        """
        instance = cls()

        io_type = io_config.get('type', 'serial')

        if io_type == 'serial':
            port = io_config['port']
            baudrate = io_config.get('baudrate', DEFAULT_IO_BAUDRATE)
            timeout = io_config.get('timeout', DEFAULT_IO_TIMEOUT)
            instance.open_serial(port, baudrate, timeout)

        elif io_type == 'socket':
            hostname = io_config['hostname']
            port = io_config['port']
            timeout = io_config.get('timeout', DEFAULT_IO_TIMEOUT)
            instance.open_socket(hostname, port, timeout)

        else:
            raise ValueError(f'unknown I/O type: {io_type!r}')

        return instance

    @classmethod
    def from_configfile(cls, io_configfile: Union[str, Path]) -> 'PumpIO':
        """
        Opens the configuration file and parses the data to be used in the from_config method.

        Args:
            cls: The initialising class.

            io_configfile: File which contains the configuration data.

        Returns:
            PumpIO: New PumpIO object with the variables set form the configuration file.

        """
        with open(io_configfile) as f:
            return cls.from_config(json.load(f))

    def __del__(self):
        """
        Closes the communication via close()
        """
        self.close()

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Closes the communication via close()

        Args:
            exc_type (Exception): The type of Exception.

            exc_value (Exception): The value associated with the Exception.

            traceback (str): Location of where the exception occurred.

        """
        self.close()

    def _debug_info(self) -> dict[str, Any]:
        info = { }

        if isinstance(self._serial, serial.Serial):
            info['port'] = self._serial.port
            info['baudrate'] = self._serial.baudrate
            info['timeout'] = self._serial.timeout

        if isinstance(self._serial, SocketBridge):
            info['hostname'] = self._serial.hostname
            info['port'] = self._serial.port

        return info

    def open_serial(self, port: str, baudrate: int = DEFAULT_IO_BAUDRATE, timeout: float = DEFAULT_IO_TIMEOUT) -> None:
        """
        Opens a communication with the hardware.

        Args:
            port: The port number on which the communication will take place.

            baudrate: The baudrate of the communication, default set to DEFAULT_IO_BAUDRATE(9600).

            timeout: The timeout of the communication, default set to DEFAULT_IO_TIMEOUT(1).

        """
        self._serial = serial.Serial(port, baudrate, timeout=timeout)
        self.logger.debug("Opening port '%s'", self._serial, extra=self._debug_info())

    def open_socket(self, hostname: str, port: int, timeout: float = DEFAULT_IO_TIMEOUT) -> None:
        """
        Opens a communication with the hardware over a network socket.

        Args:
            hostname: The hostname with which the communication will take place.

            port: The port number on which the communication will take place.

            timeout: The timeout of the communication, default set to DEFAULT_IO_TIMEOUT(1).

        """
        self._serial = SocketBridge(timeout)
        self._serial.open(hostname, port)
        self.logger.debug("Opening port '%s'", self._serial, extra=self._debug_info())

    def close(self) -> None:
        """
        Closes the communication with the hardware.
        """
        # This happens when serial.Serial fails in PumpIO.open(), so that PumpIO._serial is None.
        # Or if the PumpIO never opened a connection.
        if self._serial is not None:
            self._serial.close()
            self.logger.debug("Closing port '%s'", self._serial, extra=self._debug_info())
            self._serial = None

    def is_connected(self) -> bool:
        return self._serial is not None

    def __bool__(self) -> bool:
        return self.is_connected()

    def flush_input(self) -> None:
        """
        Flushes the input buffer of the serial communication.
        """
        if self._serial is None:
            raise RuntimeError('no open connection')
        self._serial.reset_input_buffer()

    def write(self, packet: DTInstructionPacket) -> None:
        """
        Writes a packet along the serial communication.

        Args:
            packet: The packet to send along the serial communication.

        .. note:: Unsure if this is the correct packet type (GAK).

        """
        if self._serial is None:
            raise RuntimeError('no open connection')

        str_to_send = packet.to_string()
        self.logger.debug("Sending {!r}".format(str_to_send))
        self._serial.write(str_to_send)

    def readline(self) -> bytes:
        """
        Reads a line from the serial communication.

        Raises:
            PumpIOTimeOutError: If the response time is greater than the timeout threshold.

        """
        if self._serial is None:
            raise RuntimeError('no open connection')

        msg = self._serial.readline()
        if msg:
            self.logger.debug("Received {}".format(msg))
            return msg
        else:
            self.logger.debug("Readline timeout!")
            raise PumpIOTimeOutError

    def write_and_readline(self, packet: DTInstructionPacket) -> bytes:
        """
        Writes a packet along the serial communication and waits for a response.

        Args:
            packet (DTInstructionPacket): The packet to be written.

        .. note:: Unsure if this is the correct packet type (GAK).

        Returns:
            response: The received response.

        Raises:
            PumpIOTimeOutError: If the response time is greater than the timeout threshold.
        """
        self.lock.acquire()
        self.flush_input()
        self.write(packet)
        try:
            response = self.readline()
            self.lock.release()
            return response
        except PumpIOTimeOutError as err:
            self.lock.release()
            raise err

class PumpIOTimeOutError(Exception):
    """
    Exception for when the response time is greater than the timeout threshold.
    """
    pass


# seems to be common to both C/CX series pumps
COMMON_MAX_TOP_VELOCITY = {
    Microstep.Mode0 : 6000,
    Microstep.Mode2 : 48000,
}

N_STEP_INCREMENTS = {
    'C3000'   :  3000,
    'C24000'  : 24000,
    'CX6000'  :  6000,
    'CX48000' : 48000,
}

class C3000Controller(PumpController):
    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS['C3000'] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


class C24000Controller(PumpController):
    """Untested!"""

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS['C24000'] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


class CX6000Controller(PumpController):
    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS['CX6000'] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]


class CX48000Controller(PumpController):
    """Untested!"""

    @property
    def number_of_steps(self) -> int:
        return N_STEP_INCREMENTS['CX48000'] * self.micro_step_mode.number_of_steps()

    @property
    def max_top_velocity(self) -> int:
        return COMMON_MAX_TOP_VELOCITY[self.micro_step_mode]
