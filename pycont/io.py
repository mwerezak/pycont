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
from collections import defaultdict, deque
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ._logger import create_logger
from .config import Address

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


class SerialIO(PumpIO):
    """
    Pump I/O communication over a serial port.

    This class is thread-safe. Each of the PumpIO methods can be called from different threads.
    Different threads can communicate concurrently with different bus addresses using the same
    SerialIO instance.

    If a thread tries to communicate with a bus address while another thread is waiting for a
    response from the same address (i.e. two threads are trying to communicate with the *same*
    bus address), the second will be blocked until the first receives it's response (or timeout)."""

    _serial: serial.Serial = None
    _skipped: defaultdict[Address, deque[DTStatus]]
    _session_lock: defaultdict[Address, threading.Lock]

    def __init__(self, port: str, baudrate: int = DEFAULT_IO_BAUDRATE, timeout: float = DEFAULT_IO_TIMEOUT):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._log = create_logger(self.__class__.__name__)
        self._skipped = defaultdict(deque)
        self._io_lock = threading.Lock() # this lock protects both _serial and _skipped
        self._session_lock = defaultdict(threading.Lock)

        self.open()

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
        """
        Writes a packet along the serial communication.

        Args:
            packet: The packet to send along the serial communication.

        .. note:: Unsure if this is the correct packet type (GAK).

        """
        if self._serial is None:
            raise RuntimeError('connection is closed')

        # ALWAYS acquire the the session lock FIRST
        with self._session_lock[packet.address]:
            bytes_to_send = packet.to_string()
            self._log.debug(f"Sending {bytes_to_send!r}")
            with self._io_lock:
                self._serial.write(bytes_to_send)

    def _read_response(self) -> Optional[DTStatus]:
        if self._serial is None:
            raise RuntimeError('connection is closed')

        msg = self._serial.readline()
        if not msg:
            return None

        try:
            self._log.debug(F"Received {msg!r}")
            return DTStatus(msg)
        except DTStatusDecodeError:
            self._log.warning(f"Failed to decode response: {msg!r}")
            return None

    def _flush_all_responses_for_address(self, address: Address) -> None:
        while True:
            with self._io_lock:
                response = self._read_response()
                if response is None:
                    break

                if response.address != address:
                    self._skipped[address].append(response)

    def _get_next_response_for_address(self, address: Address) -> DTStatus:
        start_time = time.time()
        while (time.time() - start_time) < self.timeout:
            with self._io_lock:
                # first check to see if the response was received by another thread
                if len(self._skipped[address]) > 0:
                    return self._skipped[address].popleft()

                # try to read a response from the device
                while (response := self._read_response()) is not None:
                    if response.address != address:
                        self._skipped[response.address].append(response)
                        continue
                    return response

            time.sleep(0.2)

        self._log.debug("Timeout expired while waiting for response!")
        raise PumpIOTimeOutError

    def send_packet_and_read_response(self, packet: DTInstructionPacket) -> DTStatus:
        if self._serial is None:
            raise RuntimeError('connection is closed')

        address = packet.address
        with self._session_lock[address]:
            # flush any incoming responses for this address before beginning the new command
            self._flush_all_responses_for_address(address)
            self._skipped[address].clear()

            self.send_packet(packet)
            return self._get_next_response_for_address(address)


class SocketIO(PumpIO):
    """
    Pump I/O communication over a socket-serial bridge.

    Not thread safe. If you need multiple threads then use a separate socket for each thread.
    """

    def __init__(self, sock: socket.socket, timeout: float = DEFAULT_IO_TIMEOUT):
        self.socket = sock
        self.timeout = timeout

        # use socket in nonblocking mode
        self.socket.settimeout(0)

        self._buf = bytearray()
        self._log = create_logger(self.__class__.__name__)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        self.socket.close()

    def send_packet(self, packet: DTInstructionPacket) -> None:
        bytes_to_send = packet.to_string()
        self._log.debug(f"Sending {bytes_to_send!r}")
        self.socket.sendall(bytes_to_send)

    def _extract_next_response_from_buffer(self, buf: bytearray) -> Optional[DTStatus]:
        start_idx = buf.find(DTStart)
        if start_idx < 0:
            buf.clear()
            return None

        stop_idx = buf.find(DTStop, start_idx)
        if stop_idx < 0:
            return None

        split_idx = stop_idx + len(DTStop)
        response = buf[start_idx:split_idx]
        del buf[:split_idx]
        return DTStatus(response)

    def _recv_status(self) -> Optional[DTStatus]:
        ready = select.select([self.socket], (), (), 0)
        if not ready:
            return None

        self._buf += self.socket.recv(4096)
        return self._extract_next_response_from_buffer(self._buf)

    def send_packet_and_read_response(self, packet: DTInstructionPacket) -> DTStatus:
        # flush any previous responses
        while self._recv_status() is not None:
            pass

        self.send_packet(packet)

        start_time = time.time()
        while (time.time() - start_time) < self.timeout:
            response = self._recv_status()
            if response is not None and response.address == packet.address:
                return response

        raise PumpIOTimeOutError
