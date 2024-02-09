"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/13
"""

from __future__ import annotations

import time
import serial
import socket
import select
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ._logger import create_logger
from .config import Address, IOConfig

from .dtprotocol import (
   DTInstructionPacket,
   DTStatus,
   DTStatusDecodeError,
   DTStart,
   DTStop,
)

if TYPE_CHECKING:
    from typing import Optional, Any


#: default Input/Output (I/O) Baudrate
DEFAULT_IO_BAUDRATE = 9600

#: Default timeout for I/O operations
DEFAULT_IO_TIMEOUT = 1.0


class PumpIOTimeOutError(Exception):
    """
    Exception for when the response time is greater than the timeout threshold.
    """
    pass


class PumpIO(ABC):
    default_poll_interval = 0.1

    @abstractmethod
    def send_packet(self, packet: DTInstructionPacket) -> None:
        """Send a packet without waiting for the response. Any response will be discarded."""
        raise NotImplementedError

    @abstractmethod
    def send_packet_and_read_response(self, packet: DTInstructionPacket) -> DTStatus:
        """Send a packet and return the first response addressed from the same bus address to which the packet was sent.

        Raises:
            PumpIOTimeOutError: If no response was received before the timeout period expired.
        """
        raise NotImplementedError

    @staticmethod
    def from_config(config: IOConfig) -> PumpIO:
        opts = dict(config.options)
        if config.io_type == "serial":
            return SerialIO(**opts)

        if config.io_type == "socket":
            sock = socket.socket(
                family = opts.get('family', socket.AF_INET),
                type = opts.get('sock_type', socket.SOCK_STREAM)
            )
            sockopts = opts.get('sockopts', ())
            for level, name, value in sockopts:
                sock.setsockopt(level, name, value)

            address = opts.get('address')
            if address is not None:
                sock.connect(address)

            return SocketIO(sock, timeout=opts.get('timeout', DEFAULT_IO_TIMEOUT))

        raise ValueError("unsupported I/O type: " + config.io_type)


class SerialIO(PumpIO):
    """
    Pump I/O communication over a serial port.
    """

    _serial: serial.Serial = None

    def __init__(self, port: str, baudrate: int = DEFAULT_IO_BAUDRATE, timeout: float = DEFAULT_IO_TIMEOUT):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._log = create_logger(self.__class__.__name__)
        self._lock = threading.Lock()

        self.open()

    def __del__(self):
        """
        Closes the communication via close()
        """
        self.close()

    def __enter__(self) -> SerialIO:
        if not self.is_connected():
            self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Closes the communication via close()

        Args:
            exc_type (Exception): The type of Exception.

            exc_value (Exception): The value associated with the Exception.

            traceback (str): Location of where the exception occurred.

        """
        self.close()

    def open(self) -> None:
        """
        Opens communication with the hardware.
        """
        # use non-blocking reads, so timeout is set to 0
        # the timeout attribute on self only applies to send_packet_and_read_response() and is handled there.
        self._serial = serial.Serial(self.port, self.baudrate, timeout=0)
        self._log.debug("Opening port '%s'", self._serial, extra=self._debug_info())

    def close(self) -> None:
        """
        Closes the communication with the hardware.
        """
        # This happens when serial.Serial fails in PumpIO.open(), so that PumpIO._serial is None.
        # Or if the PumpIO never opened a connection.
        if self._serial is not None:
            self._serial.close()
            self._log.debug("Closing port '%s'", self._serial, extra=self._debug_info())
            del self._serial

    def is_connected(self) -> bool:
        return self._serial is not None

    def __bool__(self) -> bool:
        return self.is_connected()

    def _debug_info(self) -> dict[str, Any]:
        return dict(
            port = self._serial.port,
            baudrate = self._serial.baudrate,
            timeout = self._serial.timeout
        )

    def send_packet(self, packet: DTInstructionPacket) -> None:
        if self._serial is None:
            raise RuntimeError('connection is closed')

        with self._lock:
            self._send_packet(packet)

    def _send_packet(self, packet: DTInstructionPacket) -> None:
        """
        Writes a packet along the serial communication.

        Args:
            packet: The packet to send along the serial communication.

        .. note:: Unsure if this is the correct packet type (GAK).

        """
        bytes_to_send = packet.to_bytes()
        self._log.debug(f"Sending {bytes_to_send!r}")
        self._serial.write(bytes_to_send)

    def _read_response(self) -> Optional[DTStatus]:
        if self._serial is None:
            raise RuntimeError('connection is closed')

        msg = self._serial.readline()
        if not msg:
            return None

        try:
            self._log.debug(F"Received {msg!r}")
            response = DTStatus(msg)
        except DTStatusDecodeError:
            self._log.warning(f"Failed to decode response: {msg!r}")
            return None

        # filter out any packets not addressed to the bus master
        if response.address != Address.Master:
            return None
        return response

    def _get_next_response(self, poll_interval: float = 0.2) -> DTStatus:
        start_time = time.time()
        while (time.time() - start_time) < self.timeout:
            # try to read a response from the device
            response = self._read_response()
            if response is not None:
                return response

            time.sleep(poll_interval)

        self._log.debug("Timeout expired while waiting for response!")
        raise PumpIOTimeOutError

    def send_packet_and_read_response(self, packet: DTInstructionPacket) -> DTStatus:
        if self._serial is None:
            raise RuntimeError('connection is closed')

        with self._lock:
            # flush any incoming packets before beginning the new command
            self._serial.reset_input_buffer()

            self._send_packet(packet)
            return self._get_next_response()


class SocketIO(PumpIO):
    """
    Pump I/O communication over a socket-serial bridge.

    Not thread safe. If you need multiple threads then use a separate socket for each thread.

    Can accept an external lock in case access needs to be synchronized between multiple processes.
    Defaults to a new threading.Lock instance.
    """

    def __init__(self, sock: socket.socket, timeout: float = DEFAULT_IO_TIMEOUT, *, lock: Any = None):
        self.socket = sock
        self.timeout = timeout

        # use socket in nonblocking mode
        self.socket.settimeout(0)

        self._lock = lock if lock is not None else threading.Lock()
        self._buf = bytearray()
        self._log = create_logger(self.__class__.__name__)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        self.socket.close()

    def is_connected(self) -> bool:
        try:
            self.socket.send(b'')
        except:
            return False
        else:
            return True

    def __bool__(self) -> bool:
        return self.is_connected()

    def send_packet(self, packet: DTInstructionPacket) -> None:
        with self._lock:
            self._send_packet(packet)

    def _send_packet(self, packet: DTInstructionPacket) -> None:
        bytes_to_send = packet.to_bytes()
        self._log.debug(f"Sending {bytes_to_send!r}")
        self.socket.sendall(bytes_to_send)

    # why didn't they just use bytes?
    _dtstart = DTStart.encode()
    _dtstop = DTStop.encode()
    def _extract_next_response_from_buffer(self, buf: bytearray) -> Optional[bytes]:
        start_idx = buf.find(self._dtstart)
        if start_idx < 0:
            buf.clear()
            return None

        stop_idx = buf.find(self._dtstop, start_idx)
        if stop_idx < 0:
            return None

        split_idx = stop_idx + len(self._dtstop)
        response = bytes(buf[start_idx:split_idx])
        del buf[:split_idx]
        return response


    def _recv(self) -> Optional[bytes]:
        ready, _, _ = select.select([self.socket], (), (), 0)
        if not ready:
            return None
        return self.socket.recv(4096)

    def _recv_status(self) -> Optional[DTStatus]:
        data = self._recv()

        if data is None:
            return None

        if data == b'':
            raise EOFError('socket closed on remote end')

        self._buf += data

        while (msg := self._extract_next_response_from_buffer(self._buf)) is not None:
            response = DTStatus(msg)
            if response.address == Address.Master:
                self._log.debug(F"Received {msg!r}")
                return response

        return None

    def _reset_input_buffer(self) -> None:
        while self._recv() is not None:
            pass
        self._buf.clear()

    def send_packet_and_read_response(self, packet: DTInstructionPacket) -> DTStatus:
        with self._lock:
            self._reset_input_buffer()

            self._send_packet(packet)

            start_time = time.time()
            while (time.time() - start_time) < self.timeout:
                response = self._recv_status()
                if response is not None:
                    return response
                time.sleep(0.2)

            raise PumpIOTimeOutError
