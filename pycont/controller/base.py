"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/12
"""

from __future__ import annotations

import time

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .._logger import create_logger

from ..config import Microstep, PumpConfig, ValveSet

from ..io import PumpIO, PumpIOTimeOutError

from ..dtprotocol import (
    DTInstructionPacket, DTStatus, DTStatusDecodeError,
)

from ..pump_protocol import ValvePosition, Address, StatusCode, PumpProtocol, PumpStatus

if TYPE_CHECKING:
    from typing import Optional
    from collections.abc import Mapping


#: Specifies a time to wait
WAIT_SLEEP_TIME = 0.1

#: Sets the maximum number of attempts to Write and Read
MAX_REPEAT_WRITE_AND_READ = 10

#: Sets the maximum time to repeat a specific operation
MAX_REPEAT_OPERATION = 10


class MaxRetriesExceededError(Exception):
    """
    Exception for when there has been too many repeat attempts.
    """
    pass


class PumpHardwareError(Exception):
    """
    Exception for when the pump encounters an hardware error.
    """
    def __init__(self, status_code: StatusCode, pump_name: str):
        self.status_code = status_code
        self.pump_name = pump_name

    def __str__(self) -> str:
        message = self._ERROR_MESSAGES.get(self.status_code, "Unknown error")
        return f"ERROR on pump {self.pump_name}: {message}"

    _ERROR_MESSAGES = {
        StatusCode.InitFailure : "Initialization failure!",
        StatusCode.InvalidCommand : "Invalid command!",
        StatusCode.InvalidOperand : "Invalid operand!",
        StatusCode.EEPROMFailure : "EEPROM failure!",
        StatusCode.NotInitialized : "Pump not initialized!",
        StatusCode.PlungerOverload : "Plunger overload!",
        StatusCode.ValveOverload : "Valve overload!",
        StatusCode.PlungerStuck : "Plunger stuck!",
    }


class PumpController(ABC):
    """
    This class represents the main controller for the C3000.
    The controller is what controls the pumps.

    Args:
        pump_io: PumpIO object for communication.

        config: Pump configuration.
    Raises:
        ValueError: Invalid microstep mode.

    """
    def __init__(self, pump_io: PumpIO, config: PumpConfig):
        self._io = pump_io
        self.config = config

        self._log = create_logger(self.__class__.__name__)
        # self._cmd_buffer: deque[DTCommand] = deque()
        self._protocol = PumpProtocol(self.address)

        self.micro_step_mode = config.micro_step_mode
        self.total_volume = float(config.total_volume)  # in ml (float)
        self.default_top_velocity = config.top_velocity

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def address(self) -> Address:
        return self.config.address

    @property
    @abstractmethod
    def max_top_velocity(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def number_of_steps(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def valve_set_config(self) -> Mapping[ValveSet, int]:
        raise NotImplementedError

    @property
    def steps_per_ml(self) -> int:
        return int(self.number_of_steps / self.total_volume)

    ## Command Execution ##

    # def reset_commands(self) -> None:
    #     """Clear the contents of the command buffer."""
    #     self._cmd_buffer.clear()
    #
    # def exec_commands(self) -> None:
    #     """Execute all commands in the command buffer, then empty it."""
    #     self._cmd_buffer.append(DTCommand(PumpCommand.Execute))
    #     packet = DTInstructionPacket(self.address, self._cmd_buffer)
    #     self._cmd_buffer.clear()
    #     self._write_and_read_from_pump(packet)

    def _write_and_read_from_pump(
        self, packet: DTInstructionPacket, max_repeat: int = MAX_REPEAT_WRITE_AND_READ
    ) -> DTStatus:
        """
        Writes packets to and reads the response from the pump.

        Args:
            packet: The packet to be written.

            max_repeat: The maximum time to repeat the read/write operation.

        Returns:
            decoded_response: The decoded response.

        Raises:
            PumpIOTimeOutError: If the response time is greater than the timeout threshold.

            ControllerRepeatedError: Error in decoding.

        """
        for retry in range(max_repeat):
            self._log.debug(f"Write and read{f' (retry {retry}/{max_repeat-1})' if retry > 0 else ''}: {packet}")

            try:
                return self._io.send_packet_and_read_response(packet)
            except PumpIOTimeOutError:
                self._log.debug("Timeout, trying again!")
            except DTStatusDecodeError as err:
                self._log.debug(f"Decode error, trying again! {err}")

            time.sleep(0.2)

        self._log.warning("Failed to communicate, maximum number of retries exceeded!")
        raise MaxRetriesExceededError('Repeated Error from pump {}'.format(self.name))

    def volume_to_step(self, volume_in_ml: float) -> int:
        """
        Determines the number of steps for a given volume.

        Args:
            volume_in_ml: Volume in millilitres.

        Returns:
            int(round(volume_in_ml * self.steps_per_ml))

        """
        return int(round(volume_in_ml * self.steps_per_ml))

    def step_to_volume(self, step: int) -> float:
        """
        Determines the volume in a specific step.

        Args:
            step: Step number.

        Returns:
            step / float(self.steps_per_ml)

        """
        return step / float(self.steps_per_ml)

    def is_idle(self) -> bool:
        """
        Determines if the pump is idle or Busy

        Returns:
            True: The pump is idle.

            False: The pump is not idle.

        Raises:
            ValueError: Value returned from the pump is not valid.

        """
        report_status_packet = self._protocol.forge_report_status_packet()
        response = self._write_and_read_from_pump(report_status_packet)

        status = PumpStatus.try_decode(response.status)
        if status is None:
            raise ValueError(f"The pump replied status {response.status!r}, could not decode")

        if status.is_error():
            raise PumpHardwareError(status.code, self.name)

        return not status.busy


    def is_busy(self) -> bool:
        """
        Determines if the pump is busy.

        Returns:
            True: Pump is busy.

            False: Pump is idle.

        Raises:
            ValueError: Value returned from the pump is not valid.

        """
        return not self.is_idle()

    def wait_until_idle(self, *, poll_interval: Optional[float] = None) -> None:
        """
        Waits until the pump is not busy for WAIT_SLEEP_TIME, default set to 0.1
        """
        if poll_interval is None:
            poll_interval = self._io.default_poll_interval

        while self.is_busy():
            time.sleep(poll_interval)

    def is_initialized(self) -> bool:
        """
        Determines if the pump has been initialised.

        Returns:
            True: The pump is initialised.

            False: The pump is not initialised.

        """
        initialized_packet = self._protocol.forge_report_initialized_packet()
        response = self._write_and_read_from_pump(initialized_packet)
        return bool(int(response.data))

    def smart_initialize(self, valve_position: str = None, secure: bool = True) -> None:
        """
        Initialises the pump and sets all pump parameters.

        Args:
            valve_position (int): Position of the valve, default set None.

            secure (bool): Ensures that everything is correct, default set to True.

        """
        if not self.is_initialized():
            self.initialize(valve_position, secure=secure)
        self.init_all_pump_parameters(secure=secure)

    def initialize(self, valve_position: ValvePosition = None, max_repeat: int = MAX_REPEAT_OPERATION, secure: bool = True) -> bool:
        """
        Initialises the pump.

        Args:
            valve_position: Position of the valve, default set to None.

            max_repeat: Maximum number of times to repeat the operation, default set to MAX_REPEAT_OPERATION (10).

            secure: Ensures that everything is correct.

        Raises:
            ControllerRepeatedError: Too many failed attempts to initialise.

        """
        if valve_position is None:
            valve_position = self.config.init_valve_pos

        for _ in range(max_repeat):
            self.initialize_valve_only()
            self.set_valve_position(valve_position, secure=secure)
            self.initialize_no_valve()

            if self.is_initialized():
                return True

        self._log.debug("Too many failed attempts to initialize!")
        raise MaxRetriesExceededError('Repeated Error from pump {}'.format(self.name))

    def initialize_valve_right(self, operand_value: int = 0, wait: bool = True) -> None:
        """
        Initialises the right valve.

        Args:
            operand_value: Value of the supplied operand.

            wait: Whether or not to wait until the pump is idle, default set to True.

        """
        self._write_and_read_from_pump(self._protocol.forge_initialize_valve_right_packet(operand_value))
        if wait:
            self.wait_until_idle()

    def initialize_valve_left(self, operand_value: int = 0, wait: bool = True) -> None:
        """
        Initialises the left valve.

        Args:
            operand_value: Value of the supplied operand, default set to 0.

            wait: Whether or not to wait until the pump is idle, default set to True.

        """
        self._write_and_read_from_pump(self._protocol.forge_initialize_valve_left_packet(operand_value))
        if wait:
            self.wait_until_idle()

    def initialize_no_valve(self, operand_value: int = None, wait: bool = True) -> None:
        """
        Initialise with no valves.

        Args:
            operand_value: Value of the supplied operand.

            wait: Whether or not to wait until the pump is idle, default set to True.

        """

        if operand_value is None:
            if self.total_volume < 1:
                operand_value = 1  # Half plunger stall force for syringes with volume of 500 uL or less
            else:
                operand_value = 0

        self._write_and_read_from_pump(self._protocol.forge_initialize_no_valve_packet(operand_value))
        if wait:
            self.wait_until_idle()

    def initialize_valve_only(self, operand_string: str = '0,0', wait: bool = True) -> None:
        """
        Initialise with valves only.

        Args:
            operand_string: Value of the supplied operand.

            wait: Whether or not to wait until the pump is idle, default set to True.

        """
        self._write_and_read_from_pump(self._protocol.forge_initialize_valve_only_packet(operand_string))
        if wait:
            self.wait_until_idle()

    def init_all_pump_parameters(self, secure: bool = True) -> None:
        """
        Initialises the pump parameters, Microstep Mode, and Top Velocity.

        Args:
            secure (bool): Ensures that everything is correct, default set to True.

        """
        self.set_microstep_mode(self.micro_step_mode)
        self.wait_until_idle()  # just in case, but should not be needed

        self.set_top_velocity(self.default_top_velocity, secure=secure)
        self.wait_until_idle()  # just in case, but should not be needed

    def set_microstep_mode(self, micro_step_mode: Microstep) -> None:
        """
        Sets the microstep mode to use.

        Args:
            micro_step_mode: Mode to use.

        """
        self.micro_step_mode = micro_step_mode
        self._write_and_read_from_pump(self._protocol.forge_microstep_mode_packet(micro_step_mode.value))

    def check_top_velocity_within_range(self, top_velocity: int) -> bool:
        """
        Checks that the top velocity is within a maximum range.

        Args:
            top_velocity: The top velocity for the pump (in steps/second).

        Returns:
            True: Top velocity is within range.

        Raises:
            ValueError: Top velocity is out of range.

        """
        max_range = self.max_top_velocity
        if top_velocity in range(1, max_range + 1):
            return True
        else:
            raise ValueError('Top velocity {} is not in range'.format(top_velocity))

    @property
    def default_top_velocity(self) -> int:
        """
        Gets the default top velocity.

        Returns:
            self.default_top_velocity: The default top velocity.

        """
        return self._default_top_velocity

    @default_top_velocity.setter
    def default_top_velocity(self, top_velocity: int) -> None:
        """
        Sets the default top velocity.

        Args:
            top_velocity (int): The top velocity for the pump (steps/second).

        """
        self.check_top_velocity_within_range(top_velocity)
        self._default_top_velocity = top_velocity

    def reset_top_velocity(self, secure: bool = True) -> None:
        """
        Ensures that the top velocity is the default top velocity.

        Args:
            secure: Ensures that everything is correct, default set to True.

        """
        if self.get_top_velocity() != self.default_top_velocity:
            self.set_top_velocity(self.default_top_velocity, secure=secure)

    def set_top_velocity(self, top_velocity: int, max_repeat: int = MAX_REPEAT_OPERATION, secure: bool = True) -> bool:
        """
        Sets the top velocity for the pump.

        Args:
            top_velocity: The top velocity.

            max_repeat: Maximum number of times to repeat an operation, default set to MAX_REPEAT_OPERATION (10).

            secure: Ensures that everything is correct.

        Returns:
            True: Top velocity has been set.

        Raises:
            ControllerRepeatedError: Too many failed attempts at setting the top velocity.

        """
        for i in range(max_repeat):
            if self.get_top_velocity() == top_velocity:
                return True
            else:
                self._log.debug("Top velocity not set, change attempt {}/{}".format(i + 1, max_repeat))
            self.check_top_velocity_within_range(top_velocity)
            self._write_and_read_from_pump(self._protocol.forge_top_velocity_packet(top_velocity))
            # if do not want to wait and check things went well, return now
            if secure is False:
                return True

        self._log.debug(f"[PUMP {self.name}] Too many failed attempts in set_top_velocity!")
        raise MaxRetriesExceededError(f'Repeated Error from pump {self.name}')

    def get_top_velocity(self) -> int:
        """
        Gets the current top velocity.

        Returns:
            top_velocity: The current top velocity (steps/second).

        """
        top_velocity_packet = self._protocol.forge_report_peak_velocity_packet()
        response = self._write_and_read_from_pump(top_velocity_packet)
        return int(response.data)

    def get_plunger_position(self) -> int:
        """
        Gets the current position of the plunger.

        Returns:
            steps: The position of the plunger (in steps).

        """
        plunger_position_packet = self._protocol.forge_report_plunger_position_packet()
        response = self._write_and_read_from_pump(plunger_position_packet)
        return int(response.data)

    @property
    def current_steps(self) -> int:
        """
        See get_plunger_position()
        """
        return self.get_plunger_position()

    @property
    def remaining_steps(self) -> int:
        """
        Gets the remaining number of steps.

        Returns:
            self.number_of_steps - self.current_steps

        """
        return self.number_of_steps - self.current_steps

    def get_volume(self) -> float:
        """
        See step_to_volume(), in ml

        Returns:
            self.step_to_volume(self.get_plunger_position())

        """
        return self.step_to_volume(self.get_plunger_position())  # in ml

    @property
    def current_volume(self) -> float:
        """
        See get_volume()

        Returns:
            self.get_volume()

        """
        return self.get_volume()

    @property
    def remaining_volume(self) -> float:
        """
        Gets the remaining volume.

        Returns:
            self.total_volume - self.current_volume
        """
        return self.total_volume - self.current_volume

    def is_volume_pumpable(self, volume_in_ml: float) -> bool:
        """
        Determines if the volume is pumpable.

        Args:
            volume_in_ml: The supplied volume.

        Returns:
            True: If the number of steps is <= to the remaining steps.

            False: The number of steps is > than the remaining steps.

        """
        steps = self.volume_to_step(volume_in_ml)
        return steps <= self.remaining_steps

    def pump(self, volume_in_ml: float, from_valve: ValvePosition = None, speed_in: int = None, wait: bool = False,
             secure: bool = True) -> bool:
        """
        Sends the signal to initiate the pump sequence.

        .. warning:: Change of speed will last after the scope of this function but will be reset to default each time speed_in == None

        Args:
            volume_in_ml: Volume to pump (in mL).

            from_valve: Pump using the valve, default set to None.

            speed_in: Speed to pump, default set to None.

            wait: Waits for the pump to be idle, default set to False.

            secure: Ensures everything is correct, default set to True.

        Returns:
            True: The supplied volume is pumpable.

            False: Supplied volume is not pumpable.

        """
        if self.is_volume_pumpable(volume_in_ml):

            if speed_in is not None:
                self.set_top_velocity(speed_in, secure=secure)
            else:
                self.reset_top_velocity(secure=secure)

            if from_valve is not None:
                self.set_valve_position(from_valve, secure=secure)

            self.pickup_move(volume_in_ml)

            if wait:
                self.wait_until_idle()

            return True
        else:
            return False

    def pickup_move(self, volume_in_ml: float) -> None:
        steps_to_pump = self.volume_to_step(volume_in_ml)
        packet = self._protocol.forge_pump_packet(steps_to_pump)
        self._write_and_read_from_pump(packet)

    def is_volume_deliverable(self, volume_in_ml: float) -> bool:
        """
        Determines if the supplied volume is deliverable.

        Args:
            volume_in_ml: The supplied volume in mL.

        Returns:
            True: The number of steps is <= the current steps.

            False: The number of steps is > the current steps.

        """
        steps = self.volume_to_step(volume_in_ml)
        return steps <= self.current_steps

    def deliver(self, volume_in_ml: float, to_valve: ValvePosition = None, speed_out: int = None, wait: bool = False,
                secure: bool = True) -> bool:
        """
        Delivers the volume payload.

        .. warning:: Change of speed will last after the scope of this function but will be reset to default each time speed_out == None

        Args:
            volume_in_ml: The supplied volume to deliver.

            to_valve: The valve to deliver the payload to, default set to None.

            speed_out: The speed of delivery, default set to None.

            wait: Waits for the pump to be idle, default set to False.

            secure: Ensures that everything is correct, default set to False.

        """
        if self.is_volume_deliverable(volume_in_ml):

            if volume_in_ml == 0:
                return True

            if speed_out is not None:
                self.set_top_velocity(speed_out, secure=secure)
            else:
                self.reset_top_velocity(secure=secure)

            if to_valve is not None:
                self.set_valve_position(to_valve, secure=secure)

            self.deliver_move(volume_in_ml)

            if wait:
                self.wait_until_idle()

            return True
        else:
            return False

    def deliver_move(self, volume_in_ml: float) -> None:
        steps_to_deliver = self.volume_to_step(volume_in_ml)
        packet = self._protocol.forge_deliver_packet(steps_to_deliver)
        self._write_and_read_from_pump(packet)

    def transfer(self, volume_in_ml: float, from_valve: ValvePosition, to_valve: ValvePosition, speed_in: int = None,
                 speed_out: int = None) -> None:
        """
        Transfers the desired volume in mL.

        Args:
            volume_in_ml: The volume to transfer.

            from_valve: The valve to transfer from.

            to_valve: The valve to transfer to.

            speed_in: The speed of transfer to valve, default set to None.

            speed_out: The speed of transfer from the valve, default set to None.

        """
        while volume_in_ml > 1e-3:
            volume_transferred = min(volume_in_ml, self.remaining_volume)
            self.pump(volume_transferred, from_valve, speed_in=speed_in, wait=True)
            self.deliver(volume_transferred, to_valve, speed_out=speed_out, wait=True)
            volume_in_ml -= volume_transferred

    def is_volume_valid(self, volume_in_ml: float) -> bool:
        """
        Determines if the supplied volume is valid.

        Args:
            volume_in_ml: The supplied volume.

        Returns:
            True: The supplied volume is <= the total volume and >= 0

            False: The supplied volume is > total volume or < 0

        """
        return 0 <= volume_in_ml <= self.total_volume

    def go_to_volume(self, volume_in_ml: float, speed: int = None, wait: bool = False, secure: bool = True) -> bool:
        """
        Moves the pump to the desired volume.

        .. warning:: Change of speed will last after the scope of this function but will be reset to default each time speed == None

        Args:
            volume_in_ml: The supplied volume.

            speed: The speed of movement, default set to None.

            wait: Waits for the pump to be idle, default set to False.

            secure: Ensures that everything is correct, default set to True.

        Returns:
            True: The supplied volume is valid.

            False: THe supplied volume is not valid.

        """
        if self.is_volume_valid(volume_in_ml):

            if speed is not None:
                self.set_top_velocity(speed, secure=secure)
            else:
                self.reset_top_velocity(secure=secure)

            steps = self.volume_to_step(volume_in_ml)
            packet = self._protocol.forge_move_to_packet(steps)
            self._write_and_read_from_pump(packet)

            if wait:
                self.wait_until_idle()

            return True
        else:
            return False

    def go_to_max_volume(self, speed: int = None, wait: bool = False) -> None:
        """
        Moves the pump to the maximum volume.

        Args:
            speed: The speed of movement, default set to None.

            wait: Waits until the pump is idle, default set to False.

        Returns:
            True: The maximum volume is valid.

            False: The maximum volume is not valid.

        """
        self.go_to_volume(self.total_volume, speed=speed, wait=wait)

    def get_raw_valve_position(self) -> str:
        """
        Gets the raw value of the valve's position.

        Returns:
            raw_valve_position: The raw position of the valve.

        """
        valve_position_packet = self._protocol.forge_report_valve_position_packet()
        response = self._write_and_read_from_pump(valve_position_packet)
        return response.data

    def get_valve_position(self, max_repeat: int = MAX_REPEAT_OPERATION) -> ValvePosition:
        """
        Gets the position of the valve.

        Args:
            max_repeat: Maximum number of times to repeat an operation, default set to MAX_REPEAT_OPERATION (10).

        Returns:
            The position of the valve.

        Raises:
            ValueError: The valve position is not valid/unknown.

        """
        raw_valve_position = None
        for i in range(max_repeat):
            raw_valve_position = self.get_raw_valve_position()
            valve_position = ValvePosition.try_decode(raw_valve_position)
            if valve_position is not None:
                return valve_position
            self._log.debug(f"Valve position request failed attempt {i+1}/{max_repeat}, {raw_valve_position} unknown")
        raise ValueError(f'Valve position received was {raw_valve_position}. It is unknown')

    def set_valve_position(self, valve_position: ValvePosition, max_repeat: int = MAX_REPEAT_OPERATION, secure: bool = True) -> bool:
        """
        Sets the position of the valve.

        Args:
            valve_position: Position of the valve.

            max_repeat: maximum number of times to repeat an operation, default set to MAX_REPEAT_OPERATION (10).

            secure: Ensures that everything is correct, default set to True.

        Returns:
            True: The valve position has been set.

        Raises:
            ValueError: The valve position is invalid/unknown.

            ControllerRepeatedError: Too many failed attempts in set_valve_position.

        """
        for retry in range(max_repeat):

            if self.get_valve_position() == valve_position:
                return True
            elif retry > 0:
                self._log.debug("Valve not in position, retry {}/{}".format(retry, max_repeat - 1))

            if valve_position == ValvePosition.Input:
                valve_position_packet = self._protocol.forge_valve_input_packet()
            elif valve_position == ValvePosition.Output:
                valve_position_packet = self._protocol.forge_valve_output_packet()
            elif valve_position == ValvePosition.Bypass:
                valve_position_packet = self._protocol.forge_valve_bypass_packet()
            elif valve_position == ValvePosition.Extra:
                valve_position_packet = self._protocol.forge_valve_extra_packet()
            elif valve_position.is_6way():
                valve_position_packet = self._protocol.forge_valve_6way_packet(valve_position.value)
            else:
                raise ValueError('Valve position unknown: {}'.format(valve_position))

            self._write_and_read_from_pump(valve_position_packet)

            # if do not want to wait and check things went well, return now
            if secure is False:
                return True

            self.wait_until_idle()

        self._log.debug("[PUMP {}] Too many failed attempts in set_valve_position!".format(self.name))
        raise MaxRetriesExceededError('Repeated Error from pump {}'.format(self.name))

    def set_eeprom_config(self, operand_value: int) -> None:
        """
        Sets the configuration of the EEPROM on the pumps.

        Args:
            operand_value: The value of the supplied operand.

        """
        eeprom_config_packet = self._protocol.forge_eeprom_config_packet(operand_value)
        self._write_and_read_from_pump(eeprom_config_packet)

        eeprom_sign_packet = self._protocol.forge_eeprom_lowlevel_config_packet(sub_command=20, operand_value="pycont1")
        self._write_and_read_from_pump(eeprom_sign_packet)

        if operand_value == 1:
            print("####################################################")
            print("3-Way Y-Valve: Connect jumper to pin 5 (bottom pin) below address switch at back of pump")
            print("Unpower and repower the pump to activate changes!")
            print("####################################################")
        else:
            print("####################################################")
            print("Unpower and repower the pump to make changes active!")
            print("####################################################")

    def set_eeprom_valve_set(self, valve_set: ValveSet) -> None:
        """
        Sets the EEPROM config of the pump to use the valve type specified by a ValveSet enumeration value,
        if the pump model supports it.

        Raises:
            ValueError: If the pump model does not support the given valve set.
        """
        operand_value = self.valve_set_config.get(valve_set)
        if operand_value is None:
            raise ValueError(f"valve set {valve_set} is not supported by this pump")
        self.set_eeprom_config(operand_value)

    def set_eeprom_lowlevel_config(self, command: int, operand: str) -> None:
        """
        Sets the configuration of the EEPROM on the pumps.

        Args:
            command: The value of the command to be issued.
            operand: The value of the supplied operand.

        """
        eeprom_packet = self._protocol.forge_eeprom_lowlevel_config_packet(sub_command=command, operand_value=operand)
        self._write_and_read_from_pump(eeprom_packet)

    def get_eeprom_config(self) -> str:
        """
        Gets the EEPROM configuration.

        Returns:
            eeprom_config: The configuration of the EEPROM.

        """
        response = self._write_and_read_from_pump(self._protocol.forge_report_eeprom_packet())
        return response.data

    def get_current_valve_config(self) -> str:
        """
        Infers the current valve configuration based on the EEPROM data.
        """
        current_eeprom_config = self.get_eeprom_config().split(',')
        valve_config = current_eeprom_config[10]
        # Valve config: IOBEXYZ
        # [I]nput, [O]utput, [B]ypass, [E]xtra positions: n*90 deg (e.g. 0 -> 0 deg, 2 -> 180 deg)
        # [X], [Y] allow plunger movement in [B] and [E], respectively (Y=1 for DIST to enable delivering to E!)
        # [Z] swap the bypass and extra position on a 4-position valve if a [Y] initialization command is issued.

        if valve_config == "2013100":
            # flash_eeprom_3_way_t_valve() AND flash_eeprom_3_way_y_valve(). Difference is jumper J2-5, check with ?28
            current_valve_config = "3-WAY"
        elif valve_config == "2033110":
            # flash_eeprom_4_way_dist_valve()
            current_valve_config = "4-WAY dist"
        elif valve_config == "2130001":
            # flash_eeprom_4_way_nondist_valve()
            current_valve_config = "4-WAY nondist"
        else:
            # e.g. DEBUG:pycont.DTStatus:Received /0`10,75,14,62,1,1,20,10,48,210,2013010,0,0,0,0,0,25,20,15,0000000
            print(valve_config)
            current_valve_config = "Unknown"

        return current_valve_config

    def terminate(self) -> None:
        """
        Sends the command to terminate the current action.
        """
        self._write_and_read_from_pump(self._protocol.forge_terminate_packet())



