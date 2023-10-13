"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/13
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import serial
import threading

from .._logger import create_logger

from ..socket_bridge import SocketBridge

#: Represents the Broadcast of the C3000
from ..dtprotocol import DTInstructionPacket

from ..config import (
    SerialConfig, SocketConfig,
    DEFAULT_IO_BAUDRATE, DEFAULT_IO_TIMEOUT,
)

if TYPE_CHECKING:
    from typing import Union, Optional, Any



class PumpIO:
    """
    This class deals with the pump I/O instructions.
    """

    _serial: Optional[Union[serial.serialposix.Serial, serial.serialwin32.Serial, SocketBridge]]

    def __init__(self, serial = None):
        self.logger = create_logger(self.__class__.__name__)

        self.lock = threading.Lock()

        self._serial = serial

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

    def open_connection(self, config: Union[SerialConfig, SocketConfig]) -> None:
        if isinstance(config, SerialConfig):
            self.open_serial(config.port, config.baudrate, config.timeout)
        elif isinstance(config, SocketConfig):
            self.open_socket(config.hostname, config.port, config.timeout)
        else:
            ValueError(f"invalid I/O config: {type(config)}")

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
