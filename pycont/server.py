""" Synchronize access to a pump control bus (a PumpIO instance) from multiple clients
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2024/02/12
"""

from __future__ import annotations

import logging
from multiprocessing.managers import BaseManager, BaseProxy
from typing import TYPE_CHECKING, TypeVar

from .dtprotocol import DTInstructionPacket, DTStatus
from .io import PumpIO

if TYPE_CHECKING:
    from typing import Any, Type


_log = logging.getLogger(__name__)


class _PumpIOProxy(BaseProxy, PumpIO):
    _exposed_ = (
        '__getattribute__',
        'send_packet',
        'send_packet_and_read_response',
    )

    def send_packet(self, packet: DTInstructionPacket) -> None:
        self._callmethod('send_packet', (packet,))

    def send_packet_and_read_response(self, packet: DTInstructionPacket) -> DTStatus:
        return self._callmethod('send_packet_and_read_response', (packet,))

    @property
    def default_poll_interval(self) -> float:
        return self._callmethod('__getattribute__', ('default_poll_interval',))


class PumpServer:
    """Synchronize access to a single PumpIO from multiple clients."""

    class _PumpManager(BaseManager): pass

    if TYPE_CHECKING:
        _IO = TypeVar('_IO', bound=PumpIO)
    @classmethod
    def register_pump_io_type(cls, io_type: Type[_IO]) -> None:
        io_name = io_type.__name__
        proxy_name = f'_{io_name}_Proxy'

        if hasattr(cls, proxy_name):
            raise ValueError(f"{io_type} is already registered or is using an invalid name")

        cls._PumpManager.register(io_name, io_type, proxytype=_PumpIOProxy)


    def __init__(self) -> None:
        self._sync = None
        self._proxy = None

    def get_proxy(self) -> PumpIO:
        """Return a serializable proxy that can be sent to remote clients."""
        if not self.is_running():
            raise RuntimeError("server is not running")
        return self._proxy

    def is_running(self) -> bool:
        return self._proxy is not None

    def start(self, io_type: Type[_IO], *args: Any, **kwargs: Any) -> None:
        """Start running the server.
        Ensures that the server port is resolved and the address
        is registered in the global registry before returning."""
        if self.is_running():
            raise RuntimeError("server is already running")

        _log.info("Starting pump server.")

        self._sync = self._PumpManager()
        self._sync.start()

        self._proxy = self._create_proxy(io_type, *args, **kwargs)

    def _create_proxy(self, io_type: Type[_IO], *args: Any, **kwargs: Any) -> PumpIO:
        proxy_ctor = getattr(self._sync, io_type.__name__)
        if proxy_ctor is None:
            raise ValueError(f"{io_type} is not registered. Use the register_pump_io_type() class method to register it before starting the server")
        return proxy_ctor(*args, **kwargs)

    def shutdown(self) -> None:
        if not self.is_running():
            raise RuntimeError("server is not running")

        self._sync.shutdown()
        _log.info("Pump server stopped.")

        self._proxy = None
        self._sync = None

    def join(self) -> None:
        if not self.is_running():
            raise RuntimeError("server is not running")
        self._sync.join()


# Register default IO types

from .io import SerialIO, SocketIO

PumpServer.register_pump_io_type(SerialIO)
PumpServer.register_pump_io_type(SocketIO)
