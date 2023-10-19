"""
.. module:: pump_protocol
   :platform: Unix
   :synopsis: A module which outlines the protocol for which the pumps will follow.

.. moduleauthor:: Jonathan Grizou <Jonathan.Grizou@gla.ac.uk>
.. moduleauthor:: Mike Werezak <mike.werezak@nrcan-rncan.gc.ca>

"""
# -*- coding: utf-8 -*-

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, NamedTuple

from ._logger import create_logger
from .dtprotocol import (
    DTCommand, DTInstructionPacket, Address,
)

if TYPE_CHECKING:
    from typing import Optional


#: Pump Command Set
class PumpCommand(Enum):
    #: Command to execute
    Execute = 'R'
    #: Command to initialise with the right valve position as output
    InitValveRight = 'Z'
    #: Command to initialise with the left valve position as output
    InitValveLeft = 'Y'
    #: Command to initialise with no valve
    InitNoValve = 'W'
    #: Command to initialise with valves only
    InitValveOnly = 'w'
    #: Command to invoke microstep mode
    MicroStepMode = 'N'
    #: Command to move the pump to a location
    MoveAbsolute = 'A'
    #: Command to access a specific pump
    MovePickup = 'P'
    #: Command to deliver payload
    MoveDeliver = 'D'
    #: Command to achieve top velocity
    SetTopVelocity = 'V'
    #: Command to access the EEPROM configuration
    SetEEPROMPumpConfig = 'U'      # Requires power restart to take effect
    SetEEPROMLowLevelParam = 'u'      # Requires power restart to take effect
    #: Command to terminate current operation
    Terminate = 'T'

    #: Command for the valve init_all_pump_parameters
    #: .. note:: Depending on EEPROM settings (U4 or U11) 4-way distribution valves either use IOBE or I<n>O<n>
    SelectValveInput = 'I'   # Depending on EEPROM settings (U4 or U11) 4-way distribution valves either use IOBE or I<n>O<n>
    #: Command for the valve output
    SelectValveOutput = 'O'
    #: Command for the valve bypass
    SelectValveBypass = 'B'
    #: Command for the extra valve
    SelectValveExtra = 'E'

    #: Command for the reporting the status
    ReportStatus = 'Q'
    #: Command for reporting hte plunger position
    ReportPlungerPosition = '?'
    #: Command for reporting the start velocity
    ReportStartVelocity = '?1'
    #: Command for reporting the peak velocity
    ReportTopVelocity = '?2'
    #: Command for reporting the cutoff velocity
    ReportCutoffVelocity = '?3'
    #: Command for reporting the valve position
    ReportValvePosition = '?6'
    #: Command for reporting initialisation
    ReportIsInitialized = '?19'
    #: Command for reporting the EEPROM
    ReportEEPROM = '?27'
    #: Command for reporting the status of J2-5 for 3 way-Y valve (i.e. 120 deg rotation)
    ReportJumper3Way = '?28'

class StatusCode(Enum):
    #: Idle/busy status when there are no errors
    Ok = '`@'
    #: Idle/busy status for initialization failure
    InitFailure = 'aA'
    #: Idle/busy status for invalid command
    InvalidCommand = 'bB'

    #: Idle/busy status for invalid operand
    InvalidOperand = 'cC'
    #: Idle/busy status for EEPROM failure
    EEPROMFailure = 'fF'
    #: Idle/busy status for pump not initialized
    NotInitialized = 'gG'
    #: Idle/busy status for plunger overload error
    PlungerOverload = 'iI'
    #: Idle/busy status for valve overload error
    ValveOverload = 'jJ'
    #: Idle/busy status for plunger not allowed to move
    PlungerStuck = 'kK'

    def is_error(self) -> bool:
        return self is not StatusCode.Ok

class PumpStatus(NamedTuple):
    busy: bool
    code: StatusCode

    def is_error(self) -> bool:
        return self.code.is_error()

    @classmethod
    def try_decode(cls, raw_code: str) -> Optional[PumpStatus]:
        return _STATUS_DECODE.get(raw_code)

_STATUS_DECODE = {
    raw_code : PumpStatus(busy, status_code)
    for status_code in StatusCode
    for busy, raw_code in zip((False, True), status_code.value)
}


class ValvePosition(Enum):
    Input = 'i'
    Output = 'o'
    Bypass = 'b'
    Extra = 'e'

    One = '1'
    Two = '2'
    Three = '3'
    Four = '4'
    Five = '5'
    Six = '6'

    def is_6way(self) -> bool:
        return self in _VALVE_6WAY_LIST

    @classmethod
    def get_6way_position(cls, pos_num: int) -> ValvePosition:
        """Get the corresponding 6-way valve position for integers 1..6"""
        return _VALVE_6WAY_LIST[pos_num - 1]

    @classmethod
    def try_decode(cls, raw_pos: str) -> Optional[ValvePosition]:
        return _VALVE_POS_DECODE.get(raw_pos)

_VALVE_POS_DECODE = {
    valve_pos.value : valve_pos
    for valve_pos in ValvePosition
}

#: 6 way valve
_VALVE_6WAY_LIST = (
    ValvePosition.One,
    ValvePosition.Two,
    ValvePosition.Three,
    ValvePosition.Four,
    ValvePosition.Five,
    ValvePosition.Six,
)


class PumpProtocol:
    """
    This class is used to represent the protocol which the pumps will follow when controlled.

    Args:
        address: Address of the pump.

    """
    def __init__(self, address: Address):
        self._log = create_logger(self.__class__.__name__)
        self.address = address

    def forge_packet(self, *dtcommands: DTCommand, execute: bool = True) -> DTInstructionPacket:
        """
        Creates a packet which will be sent to the device.

        Args:
            dtcommands: DTCommand or list of DTCommands.

            execute: Sets the execute value, True by default.

        Returns:
            DTInstructionPacket: The packet created.

        """
        self._log.debug("Forging packet with {} and execute set to {}".format(dtcommands, execute))
        dtcommands = list(dtcommands)
        if execute:
            dtcommands.append(DTCommand(PumpCommand.Execute))
        return DTInstructionPacket(self.address, dtcommands)

    """

    .. note:: The following functions should be generated automatically but not necessary as of yet.

    .. todo:: Generate these functions automatically.

    """

    # the functions below should be generated automatically but not really needed for now

    def forge_initialize_valve_right_packet(self, operand_value: int = 0) -> DTInstructionPacket:
        """
        Creates a packet for initialising the right valve.

        Args:
            operand_value: The value of the supplied operand, 0 by default.

        Returns:
            DTInstructionPacket: The packet created for initialising the right valve.

        """
        dtcommand = DTCommand(PumpCommand.InitValveRight, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_initialize_valve_left_packet(self, operand_value: int = 0) -> DTInstructionPacket:
        """
        Creates a packet for initialising the left valve.

        Args:
            operand_value: The value of the supplied operand, 0 by default.

        Returns:
            DTInstructionPacket: The packet created for initialising the left valve.

        """
        dtcommand = DTCommand(PumpCommand.InitValveLeft, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_initialize_no_valve_packet(self, operand_value: int = 0) -> DTInstructionPacket:
        """
        Creates a packet for initialising with no valves.

        Args:
            operand_value: The value of the supplied operand, 0 by default.

        Returns:
            DTInstructionPacket: The packet created for initialising with no valves.

        """
        dtcommand = DTCommand(PumpCommand.InitNoValve, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_initialize_valve_only_packet(self, operand_string: Optional[str] = None)\
            -> DTInstructionPacket:
        """
        Creates a packet for initialising with valves only.

        Args:
            operand_string: String representing the operand, None by default

        Returns:
            DTInstructionPacket: The packet created for initialising with valves only

        """
        dtcommand = DTCommand(PumpCommand.InitValveOnly, operand_string)
        return self.forge_packet(dtcommand)

    def forge_microstep_mode_packet(self, operand_value: int) -> DTInstructionPacket:
        """
        Creates a packet for initialising microstep mode.

        Args:
            operand_value: The value of the supplied operand.

        Returns:
            DTInstructionPacket: The packet created for initialising microstep mode.

        """
        if operand_value not in list(range(3)):
            raise ValueError('Microstep operand must be in [0-2], you entered {}'.format(operand_value))
        dtcommand = DTCommand(PumpCommand.MicroStepMode, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_move_to_packet(self, operand_value: int) -> DTInstructionPacket:
        """
        Creates a packet for moving the device to a location.

        Args:
            operand_value: The value of the supplied operand.

        Returns:
            DTInstructionPacket: The packet created for moving the device to a location.

        """
        dtcommand = DTCommand(PumpCommand.MoveAbsolute, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_pump_packet(self, operand_value: int) -> DTInstructionPacket:
        """
        Creates a packet for the pump action of the device.

        Args:
            operand_value: The value of the supplied operand

        Returns:
            DTInstructionPacket: The packet created for the pump action of the device.

        """
        dtcommand = DTCommand(PumpCommand.MovePickup, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_deliver_packet(self, operand_value: int) -> DTInstructionPacket:
        """
        Creates a packet for delivering the payload.

        Args:
            operand_value: The value of the supplied operand.

        Returns:
            DTInstructionPacket: The packet created for delivering the payload.

        """
        dtcommand = DTCommand(PumpCommand.MoveDeliver, str(operand_value))
        return self.forge_packet(dtcommand)

    def forge_top_velocity_packet(self, operand_value: int) -> DTInstructionPacket:
        """
        Creates a packet for the top velocity of the device.

        Args:
            operand_value: The value of the supplied operand.

        Returns:
            DTInstructionPacket: The packet created for the top velocity of the device.

        """
        dtcommand = DTCommand(PumpCommand.SetTopVelocity, str(int(operand_value)))
        return self.forge_packet(dtcommand)

    def forge_eeprom_config_packet(self, operand_value: int) -> DTInstructionPacket:
        """
        Creates a packet for accessing the EEPROM configuration of the device.

        Args:
            operand_value: The value of the supplied operand.

        Returns:
            DTInstructionPacket: The packet created for accessing the EEPROM configuration of the device.

        """
        dtcommand = DTCommand(PumpCommand.SetEEPROMPumpConfig, str(operand_value))
        return self.forge_packet(dtcommand, execute=False)

    def forge_eeprom_lowlevel_config_packet(self, sub_command: int = 20, operand_value: str = "pycont1")\
            -> DTInstructionPacket:
        """
        Creates a packet for accessing the EEPROM configuration of the device.

        Args:
            sub_command:  Sub-command value (0-20)
            operand_value: The value of the supplied operand.

        Returns:
            DTInstructionPacket: The packet created for accessing the EEPROM configuration of the device.

        """

        dtcommand = DTCommand(PumpCommand.SetEEPROMLowLevelParam, str(sub_command) + "_" + str(operand_value))
        return self.forge_packet(dtcommand, execute=False)

    def forge_valve_input_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for the input into a valve on the device.

        Returns:
            DTInstructionPacket: The packet created for the input into a valve on the device.

        """
        return self.forge_packet(DTCommand(PumpCommand.SelectValveInput))

    def forge_valve_output_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for the output from a valve on the device.

        Returns:
            DTInstructionPacket: The packet created for the output from a valve on the device.

        """
        return self.forge_packet(DTCommand(PumpCommand.SelectValveOutput))

    def forge_valve_bypass_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for bypassing a valve on the device.

        Returns:
            DTInstructionPacket: The packet created for bypassing a valve on the device.

        """
        return self.forge_packet(DTCommand(PumpCommand.SelectValveBypass))

    def forge_valve_extra_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for an extra valve.

        Returns:
            DTInstructionPacket: The packet created for an extra valve.

        """
        return self.forge_packet(DTCommand(PumpCommand.SelectValveBypass))

    def forge_valve_6way_packet(self, valve_position: str) -> DTInstructionPacket:
        """
        Creates a packet for the 6way valve on the device.

        Returns:
            DTInstructionPacket: The packet created for the input into a valve on the device.

        """
        return self.forge_packet(DTCommand('{}{}'.format(PumpCommand.SelectValveInput, valve_position)))

    def forge_report_status_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the device status.

        Returns:
            DTInstructionPacket: The packet created for reporting the device status.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportStatus))

    def forge_report_plunger_position_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the device's plunger position.

        Returns:
            DTInstructionPacket: The packet created for reporting the device's plunger position.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportPlungerPosition))

    def forge_report_start_velocity_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the device's start velocity.

        Returns:
            DTInstructionPacket: The packet created for reporting the device's starting velocity.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportStartVelocity))

    def forge_report_peak_velocity_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the device's peak velocity.

        Returns:
            DTInstructionPacket: The packet created for reporting the device's peak velocity.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportTopVelocity))

    def forge_report_cutoff_velocity_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the device's cutoff velocity.

        Returns:
            DTInstructionPacket: The packet created for reporting the device's cutoff velocity.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportCutoffVelocity))

    def forge_report_valve_position_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the device's valve position.

        Returns:
            DTInstructionPacket: The packet created for reporting the device's valve position.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportValvePosition))

    def forge_report_initialized_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the initialisation of the device.

        Returns:
            DTInstructionPacket: The packet created for reporting the initialisation of the device.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportIsInitialized))

    def forge_report_eeprom_packet(self) -> DTInstructionPacket:
        """
        Creates a packet for reporting the EEPROM.

        Returns:
            The packet for reporting the EEPROM.

        """
        return self.forge_packet(DTCommand(PumpCommand.ReportEEPROM))

    def forge_terminate_packet(self) -> DTInstructionPacket:
        """
        Creates the data packet for terminating the current command

        Returns:
            The packet for terminating any running command.

        """
        return self.forge_packet(DTCommand(PumpCommand.Terminate))
