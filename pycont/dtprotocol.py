# -*- coding: utf-8 -*-

from __future__ import annotations

import itertools
from enum import Enum
from typing import TYPE_CHECKING

from ._logger import create_logger

if TYPE_CHECKING:
    from typing import Union, Optional
    from collections.abc import Iterable
    from .pump_protocol import PumpCommand


DTStart = '/'
DTStop = '\r'


class Address(Enum):
    Switch0 = '1'
    Switch1 = '2'
    Switch2 = '3'
    Switch3 = '4'
    Switch4 = '5'
    Switch5 = '6'
    Switch6 = '7'
    Switch7 = '8'
    Switch8 = '9'
    Switch9 = ':'
    SwitchA = ';'
    SwitchB = '<'
    SwitchC = '='
    SwitchD = '>'
    SwitchE = '?'
    SwitchF = '@'
    Master = '0'
    Broadcast = '_'

    @classmethod
    def from_switch(cls, switch: str) -> Address:
        return _ADDRESS_FROM_SWITCH[switch]

_ADDRESS_FROM_SWITCH = {
    '0' : Address.Switch0,
    '1' : Address.Switch1,
    '2' : Address.Switch2,
    '3' : Address.Switch3,
    '4' : Address.Switch4,
    '5' : Address.Switch5,
    '6' : Address.Switch6,
    '7' : Address.Switch7,
    '8' : Address.Switch8,
    '9' : Address.Switch9,
    'A' : Address.SwitchA,
    'B' : Address.SwitchB,
    'C' : Address.SwitchC,
    'D' : Address.SwitchD,
    'E' : Address.SwitchE,
    'F' : Address.SwitchF,
}




class DTCommand(object):

    """ This class is used to represent a DTcommand.

        Args:
            command: The command to be sent

            operand: The parameter of the command, None by default

        (for more details see http://www.tricontinent.com/products/cseries-syringe-pumps)
        """

    def __init__(self, command: Union[str, PumpCommand], operand: str = ''):
        # temporary hack until 6-way support is added to PumpCommand
        command = getattr(command, 'value', command)
        self.command = command.encode()
        self.operand = operand.encode()

    def to_array(self) -> bytearray:
        return bytearray(itertools.chain(self.command, self.operand))

    def to_bytes(self) -> bytes:
        return bytes(itertools.chain(self.command, self.operand))

    def __str__(self):
        return "command: " + str(self.command.decode()) + " operand: " + str(self.operand)


class DTInstructionPacket:
    """ This class is used to represent a DT instruction packet.

        Args:
            address: The address to talk to

            dtcommands: List of DTCommand

        (for more details see http://www.tricontinent.com/products/cseries-syringe-pumps)
        """

    def __init__(self, address: Address, dtcommands: Iterable[DTCommand]):
        self.address = address.value.encode()
        self.dtcommands = tuple(dtcommands)

    def to_array(self) -> bytearray:
        return bytearray(itertools.chain(
            DTStart.encode(),
            self.address,
            *(dtcommand.to_bytes() for dtcommand in self.dtcommands),
            DTStop.encode(),
        ))

    def to_bytes(self) -> bytes:
        return bytes(self.to_array())


# TODO do all processing in bytes and eliminate this
class DTStatusDecodeError(Exception): pass

class DTStatus(object):
    """ This class is used to represent a DTstatus, the response of the device from a command.

        Args:
            response: The response from the device

        (for more details see http://www.tricontinent.com/products/cseries-syringe-pumps)
        """

    address: Optional[Address]
    status: Optional[str]
    data: Optional[str]

    def __init__(self, response: bytes):
        self.logger = create_logger(self.__class__.__name__)
        try:
            raw_response = response.decode()
        except UnicodeDecodeError:
            raise DTStatusDecodeError('Could not decode {!r}'.format(response)) from None

        self.status = None
        self.data = None
        self._extract_response_parts(raw_response)

    def _extract_response_parts(self, response: str) -> None:
        info = response.rstrip().rstrip('\x03').lstrip(DTStart)

        try:
            self.address = Address(info[0])
        except ValueError:
            self.address = None

        if self.address == Address.Master:
            self.status, self.data = info[1], info[2:]
