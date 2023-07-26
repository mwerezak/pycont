"""
Compatibility shim to allow PyCont to be used over a network socket bridge
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/07/26
"""

from __future__ import annotations

import os
import io
import time
from io import BytesIO
from typing import TYPE_CHECKING

import socket
if TYPE_CHECKING:
    from typing import Union, Optional

class SocketBridge:
    def __init__(self, timeout: Optional[float]):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)

        self._buf = BytesIO()

        self.hostname = None
        self.port = None

    def open(self, hostname: str, port: int) -> None:
        self.hostname = hostname
        self.port = port
        self._sock.connect((hostname, port))

    def _buf_pos(self) -> int:
        return self._buf.tell()

    def _buf_remaining(self) -> int:
        return len(self._buf.getbuffer()) - self._buf.tell()

    @property
    def timeout(self) -> Optional[float]:
        return self._sock.gettimeout()

    @timeout.setter
    def timeout(self, value: Optional[float]) -> None:
        self._sock.settimeout(value)

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
        timeout = self._sock.gettimeout()
        while not result.endswith(b'\n') and (timeout is None or time.time() - start < timeout):
            if self._buf_remaining() < self._BUF_FILL:
                data = self._sock.recv(self._BUF_FILL)

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
        self._sock.sendall(data)
        return len(data)

    def close(self) -> None:
        self._sock.close()

    if os.name == 'nt':
        _BLOCK_ERR = BlockingIOError
    # add platform specific exceptions here
    else:
        raise ValueError(f'unknown blocking exception for os: {os.name!r}')

    def reset_input_buffer(self) -> None:
        """Flush input buffer, discarding all its contents."""
        # enter non-blocking mode and call recv() until we would block
        timeout = self._sock.gettimeout()
        try:
            self._sock.settimeout(0)
            while True:
                self._sock.recv(1024)
        except self._BLOCK_ERR:
            pass
        finally:
            self._sock.settimeout(timeout)
