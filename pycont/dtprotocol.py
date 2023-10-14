# -*- coding: utf-8 -*-

import itertools
from typing import TYPE_CHECKING

from ._logger import create_logger
from .config import Address

if TYPE_CHECKING:
    from typing import Any, Union
    from collections.abc import Sequence

DTStart = '/'
DTStop = '\r'


class DTCommand(object):

    """ This class is used to represent a DTcommand.

        Args:
            command: The command to be sent

            operand: The parameter of the command, None by default

        (for more details see http://www.tricontinent.com/products/cseries-syringe-pumps)
        """

    def __init__(self, command: str, operand: str = None):
        self.command = command.encode()
        if operand is not None:
            self.operand = operand.encode()
        else:
            self.operand = None  # type: ignore

    def to_array(self) -> bytearray:
        if self.operand is None:
            chain = itertools.chain(self.command)
        else:
            chain = itertools.chain(self.command, self.operand)
        return bytearray(chain)

    def to_string(self) -> bytes:
        return bytes(self.to_array())

    def __str__(self):
        return "command: " + str(self.command.decode()) + " operand: " + str(self.operand)


class DTInstructionPacket:
    """ This class is used to represent a DT instruction packet.

        Args:
            address: The address to talk to

            dtcommands: List of DTCommand

        (for more details see http://www.tricontinent.com/products/cseries-syringe-pumps)
        """

    def __init__(self, address: str, dtcommands: Sequence[DTCommand]):
        self.address = address.encode()
        self.dtcommands = dtcommands

    def to_array(self) -> bytearray:
        return bytearray(itertools.chain(
            DTStart.encode(),
            self.address,
            *(dtcommand.to_string() for dtcommand in self.dtcommands),
            DTStop.encode(),
        ))

    def to_string(self) -> bytes:
        return bytes(self.to_array())


class DTStatusDecodeError(Exception): pass

class DTStatus(object):
    """ This class is used to represent a DTstatus, the response of the device from a command.

        Args:
            response: The response from the device

        (for more details see http://www.tricontinent.com/products/cseries-syringe-pumps)
        """

    def __init__(self, response: bytes):
        self.logger = create_logger(self.__class__.__name__)
        try:
            raw_response = response.decode()
        except UnicodeDecodeError:
            raise DTStatusDecodeError('Could not decode {!r}'.format(response)) from None

        self.address, self.status, self.data = self._extract_response_parts(raw_response)

    def _extract_response_parts(self, response: str) -> tuple[Union[Address, str], str, str]:
        info = response.rstrip().rstrip('\x03').lstrip(DTStart)

        address = info[0]
        try:
            address = Address(address)
        except ValueError:
            self.logger.warning(f"Invalid address {info[0]!r}")

        return address, info[1], info[2:]  # address, status, data

