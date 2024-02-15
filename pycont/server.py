""" Synchronize access to a pump control bus (a PumpIO instance) from multiple clients
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2024/02/12
"""

from __future__ import annotations

import logging
from multiprocessing.managers import BaseManager, BaseProxy
from typing import TYPE_CHECKING, TypeVar

from .io import PumpIO

if TYPE_CHECKING:
    from typing import Any, Type, Callable
    from collections.abc import Iterable


_log = logging.getLogger(__name__)


def _make_proxy_method(name: str) -> Callable:
    def method(self, /, *args, **kwargs):
        return self._callmethod(name, args, kwargs)
    method.__name__ = name
    return method

def _make_proxy_property(name: str) -> property:
    def prop_get(self, /):
        return self._callmethod('__getattribute__', [name])

    def prop_set(self, /, value):
        return self._callmethod('__setattr__', [name, value])

    prop_get.__name__ = name
    prop_set.__name__ = name
    return property(prop_get, prop_set)

def _make_proxy(name: str, methods: Iterable[str], properties: Iterable[str]) -> Type:
    class_dict = {}

    for method_name in methods:
        class_dict[method_name] = _make_proxy_method(method_name)

    for prop_name in properties:
        class_dict[prop_name] = _make_proxy_property(prop_name)

    exposed = (
        '__getattribute__', '__setattr__', *class_dict.keys()
    )

    Proxy = type(name, (BaseProxy,), class_dict)
    Proxy._exposed_ = exposed
    return Proxy


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

        proxy_type = _make_proxy(
            f'{cls.__name__}.{proxy_name}',
            methods = (
                'send_packet',
                'send_packet_and_read_response',
            ),
            properties = (
                'default_poll_interval',
            ),
        )
        setattr(cls, proxy_name, proxy_type)
        cls._PumpManager.register(io_name, io_type, proxytype=proxy_type)


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
