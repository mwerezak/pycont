"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/13
"""

from __future__ import annotations

import serial
import socket
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._logger import create_logger

#: Represents the Broadcast of the C3000
from .dtprotocol import DTInstructionPacket

if TYPE_CHECKING:
    from typing import Union, Optional, Any


#: default Input/Output (I/O) Baudrate
DEFAULT_IO_BAUDRATE = 9600

#: Default timeout for I/O operations
DEFAULT_IO_TIMEOUT = 1.0

@dataclass(frozen=True)
class SerialConfig:
    port: str
    baudrate: int = DEFAULT_IO_BAUDRATE
    timeout: float = DEFAULT_IO_TIMEOUT

@dataclass(frozen=True)
class SocketConfig:
    hostname: str
    port: int
    timeout: float = DEFAULT_IO_TIMEOUT

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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((hostname, port))
        self._serial = SocketBridge(sock)
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


import os
import io
import time
from io import BytesIO

class SocketBridge:
    """Can be used with PumpIO to communicate over a socket-based serial bridge."""

    def __init__(self, sock: socket):
        self.socket = sock
        self._buf = BytesIO()

    @property
    def hostname(self) -> str:
        return self.socket.hostname

    @property
    def port(self) -> str:
        return self.socket.port

    def _buf_pos(self) -> int:
        return self._buf.tell()

    def _buf_remaining(self) -> int:
        return len(self._buf.getbuffer()) - self._buf.tell()

    def _trim_buffer(self) -> None:
        """Remove everything before the current buffer position"""
        pos = self._buf_pos()
        remaining = self._buf_remaining()
        buf_mem = self._buf.getbuffer()
        buf_mem[:remaining] = buf_mem[pos:pos+remaining]
        self._buf.truncate(remaining)

    _BUF_FILL = 4096
    def readline(self, size: int = -1) -> bytes:
        """Read and return one line from the stream. If size is specified, at most size bytes will be read."""

        result = bytearray()

        start = time.time()
        timeout = self.socket.gettimeout()
        while not result.endswith(b'\n') and (timeout is None or time.time() - start < timeout):
            if self._buf_remaining() < self._BUF_FILL:
                data = self.socket.recv(self._BUF_FILL)

                pos = self._buf_pos()
                try:
                    self._buf.seek(0, io.SEEK_END)
                    self._buf.write(data)
                finally:
                    self._buf.seek(pos)

            result.extend(self._buf.readline(size))

            if self._buf_pos() > self._BUF_FILL:
                self._trim_buffer()

        return bytes(result)

    def write(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """Write the bytes data to the port."""
        self.socket.sendall(data)
        return len(data)

    def close(self) -> None:
        self.socket.close()

    if os.name == 'nt':
        _BLOCK_ERR = BlockingIOError
    # add platform specific exceptions here
    else:
        raise ValueError(f'unknown blocking exception for os: {os.name!r}')

    def reset_input_buffer(self) -> None:
        """Flush input buffer, discarding all its contents."""
        # enter non-blocking mode and call recv() until we would block
        timeout = self.socket.gettimeout()
        try:
            self.socket.settimeout(0)
            while True:
                self.socket.recv(1024)
        except self._BLOCK_ERR:
            pass
        finally:
            self.socket.settimeout(timeout)
