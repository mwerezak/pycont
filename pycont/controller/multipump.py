"""
| Author: Mike Werezak <mike.werezak@canada.ca>
| Created: 2023/10/10
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .._logger import create_logger
from ..config import ValvePosition, BusConfig
from ..io import PumpIO
from . import PumpController

if TYPE_CHECKING:
    from typing import Any, Union, Optional


class MultiPumpController(object):
    """
    This class deals with controlling multiple pumps on one or more hubs at a time.

    Args:
        setup_config: The configuration of the setup.

    """
    def __init__(self, *config: BusConfig, groups: dict = None):
        self.logger = create_logger(self.__class__.__name__)
        self.pumps: dict[str, PumpController] = {}

        # Sets groups and default configs if provided in the config dictionary
        self.groups = {} if groups is None else groups

        for bus_config in config:
            pump_io = PumpIO()
            pump_io.open(bus_config.io_config)

            for pump_config in bus_config.pumps:
                self.pumps[pump_config.name] = pump_config.create_pump(pump_io)

        # Adds pumps as attributes
        self.set_pumps_as_attributes()

    @classmethod
    def from_config(cls, setup_config: dict) -> 'MultiPumpController':
        groups = setup_config['groups'] if 'groups' in setup_config else {}

        pump_defaults = setup_config['default'] if 'default' in setup_config else {}

        if 'hubs' in setup_config:
            # This implements the "new" behaviour with multiple hubs
            config = []
            for hub_config in setup_config['hubs']:
                config.append(BusConfig.from_dict(hub_config, pump_defaults))
            return cls(*config, groups = groups)

        else:
            # This implements the "old" behaviour with one hub per object instance / json file
            return cls(BusConfig.from_dict(setup_config, pump_defaults), groups=groups)

    @classmethod
    def from_configfile(cls, setup_configfile: Union[str, Path]) -> 'MultiPumpController':
        """
        Obtains the configuration data from the supplied configuration file.

        Args:
            cls: The initialising class.

            setup_configfile: The configuration file.

        Returns:
            MultiPumpController: A new MultiPumpController object with the configuration set from the config file.

        """
        with open(setup_configfile) as f:
            return cls.from_config(json.load(f))

    def set_pumps_as_attributes(self) -> None:
        """
        Sets the pumps as attributes.
        """
        for pump_name, pump in list(self.pumps.items()):
            if hasattr(self, pump_name):
                self.logger.warning(f"Pump named {pump_name} is a reserved attribute, please change name or do not use "
                                    f"this pump in attribute mode, rather use pumps['{pump_name}'']")
            else:
                setattr(self, pump_name, pump)

    def get_pumps(self, pump_names: list[str]) -> list[PumpController]:
        """
        Obtains a list of all pumps with name in pump_names.

        Args:
            pump_names: A list of the pump names

        Returns:
            pumps: A list of the pump objects.

        """
        pumps = []
        for pump_name in pump_names:
            try:
                pumps.append(self.pumps[pump_name])
            except KeyError:
                pass
        return pumps

    def get_pumps_in_group(self, group_name: str) -> Optional[list[PumpController]]:
        """
        Obtains a list of all pumps with group_name.

        Args:
            group_name: The group name

        Returns:
            pumps: A list of the pump objects in the group. None for non-existing groups.

        """
        pumps = []
        try:
            pump_list = self.groups[group_name]
        except KeyError:
            return None

        for pump_name in pump_list:
            pumps.append(self.pumps[pump_name])
        return pumps

    def get_all_pumps(self) -> dict[str, PumpController]:
        """
        Obtains a list of all pumps.

        Returns:
            pumps: A list of the all the pump objects in the Controller.

        """

        return self.pumps

    def apply_command_to_pumps(self, pump_names: list[str], command: str, *args, **kwargs) -> dict[str, Any]:
        """
        Applies a given command to the pumps.

        Args:
            pump_names (List): List containing the pump names.

            command (str): The command to apply.

            *args: Variable length argument list.

            **kwargs: Arbitrary keyword arguments.

        Returns:
            returns (Dict): Dictionary of the functions return.

        """
        returns = {}
        for pump_name in pump_names:
            func = getattr(self.pumps[pump_name], command)
            returns[pump_name] = func(*args, **kwargs)

        return returns

    def apply_command_to_all_pumps(self, command: str, *args, **kwargs) -> dict[str, Any]:
        """
        Applies a given command to all of the pumps.

        Args:
            command (str): The command to apply.

            *args: Variable length argument list.

            **kwargs: Arbitrary keyword arguments.

        Returns:
            returns (Dict): Dictionary of the functions.

        """
        return self.apply_command_to_pumps(list(self.pumps.keys()), command, *args, **kwargs)

    def apply_command_to_group(self, group_name: str, command: str, *args, **kwargs) -> dict[str, Any]:
        """
        Applies a given command to the group.

        Args:
            group_name: Name of the group.

            command: The command to apply.

            *args: Variable length argument list.

            **kwargs: Arbitrary keyword arguments.

        Returns:
            returns Dictionary of the functions.

        """
        return self.apply_command_to_pumps(self.groups[group_name], command, *args, **kwargs)

    def are_pumps_initialized(self) -> bool:
        """
        Determines if the pumps have been initialised.

        Returns:
            True: The pumps have been initialised.

            False: The pumps have not been initialised.

        """
        for pump in list(self.pumps.values()):
            if not pump.is_initialized():
                return False
        return True

    def smart_initialize(self, secure: bool = True) -> None:
        """
        Initialises the pumps, setting all parameters.

        Args:
            secure: Ensures everything is correct, default set to True.

        """
        for pump in list(self.pumps.values()):
            if not pump.is_initialized():
                pump.initialize_valve_only(wait=False)
        self.wait_until_all_pumps_idle()

        for pump in list(self.pumps.values()):
            if not pump.is_initialized():
                pump.set_valve_position(pump.config.init_valve_pos, secure=secure)
        self.wait_until_all_pumps_idle()

        for pump in list(self.pumps.values()):
            if not pump.is_initialized():
                pump.initialize_no_valve(wait=False)
        self.wait_until_all_pumps_idle()

        self.apply_command_to_all_pumps('init_all_pump_parameters', secure=secure)
        self.wait_until_all_pumps_idle()

    def wait_until_all_pumps_idle(self) -> None:
        """
        Sends the command 'wait_until_idle' to the pumps.
        """
        self.apply_command_to_all_pumps('wait_until_idle')

    def wait_until_group_idle(self, group_name: str) -> None:
        """
        Sends the command ' wait_until_idle' to all pumps of a group.
        """
        self.apply_command_to_group(group_name=group_name, command='wait_until_idle')

    def terminate_all_pumps(self) -> None:
        """
        Sends the command 'terminate' to all the pumps.
        """
        self.apply_command_to_all_pumps('terminate')

    def are_pumps_idle(self) -> bool:
        """
        Determines if the pumps are idle.

        Returns:
            True: The pumps are idle.

            False: The pumps are not idle.

        """
        for pump in list(self.pumps.values()):
            if not pump.is_idle():
                return False
        return True

    def are_pumps_busy(self) -> bool:
        """
        Determines if the pumps are busy.

        Returns:
            True: The pumps are busy.

            False: The pumps are not busy.

        """
        return not self.are_pumps_idle()

    def pump(self, pump_names: list[str], volume_in_ml: float, from_valve: str = None, speed_in: float = None,
             wait: bool = False, secure: bool = True) -> None:
        """
        Pumps the desired volume.

        Args:
            pump_names: The name of the pumps.

            volume_in_ml: The volume to be pumped.

            from_valve: The valve to pump from.

            speed_in: The speed at which to pump, default set to None.

            wait: Waits for the pumps to be idle, default set to False.

            secure: Ensures everything is correct, default set to False.

        """
        if speed_in is not None:
            self.apply_command_to_pumps(pump_names, 'set_top_velocity', speed_in, secure=secure)
        else:
            self.apply_command_to_pumps(pump_names, 'reset_top_velocity', secure=secure)

        if from_valve is not None:
            self.apply_command_to_pumps(pump_names, 'set_valve_position', from_valve, secure=secure)

        self.apply_command_to_pumps(pump_names, 'pump', volume_in_ml, speed_in=speed_in, wait=False)

        if wait:
            self.apply_command_to_pumps(pump_names, 'wait_until_idle')

    def deliver(self, pump_names: list[str], volume_in_ml: float, to_valve: str = None, speed_out: int = None,
                wait: bool = False, secure: bool = True) -> None:
        """
        Delivers the desired volume.

        Args:
            pump_names: The name of the pumps.

            volume_in_ml: The volume to be delivered.

            to_valve: The valve to deliver to.

            speed_out: The speed at which to deliver.

            wait: Wait for the pumps to be idle, default set to False.

            secure: Ensures everything is correct, default set to True.

        """
        if speed_out is not None:
            self.apply_command_to_pumps(pump_names, 'set_top_velocity', speed_out, secure=secure)
        else:
            self.apply_command_to_pumps(pump_names, 'reset_top_velocity', secure=secure)

        if to_valve is not None:
            self.apply_command_to_pumps(pump_names, 'set_valve_position', to_valve, secure=secure)

        self.apply_command_to_pumps(pump_names, 'deliver', volume_in_ml, speed_out=speed_out, wait=False)

        if wait:
            self.apply_command_to_pumps(pump_names, 'wait_until_idle')

    def transfer(self, pump_names: list[str], volume_in_ml: float, from_valve: str, to_valve: str,
                 speed_in: int = None, speed_out: int = None, secure: bool = True) -> None:
        """
        Transfers the desired volume between pumps.

        Args:
            pump_names: The name of the pumps.

            volume_in_ml: The volume to be transferred.

            from_valve: The valve to transfer from.

            to_valve: the valve to transfer to.

            speed_in: The speed at which to receive transfer, default set to None.

            speed_out: The speed at which to transfer, default set to None

            secure: Ensures that everything is correct, default set to False.

        """
        volume_transferred = float('inf')  # Temporary value for the first cycle only, see below
        for pump in self.get_pumps(pump_names):
            candidate_volume = min(volume_in_ml, pump.remaining_volume)  # Smallest target and remaining is candidate
            volume_transferred = min(candidate_volume, volume_transferred)  # Transferred is global minimum

        self.pump(pump_names, volume_transferred, from_valve, speed_in=speed_in, wait=True, secure=secure)
        self.deliver(pump_names, volume_transferred, to_valve, speed_out=speed_out, wait=True, secure=secure)

        remaining_volume_to_transfer = volume_in_ml - volume_transferred
        if remaining_volume_to_transfer > 0:
            self.transfer(pump_names, remaining_volume_to_transfer, from_valve, to_valve, speed_in, speed_out)

    def parallel_transfer(self, pumps_and_volumes_dict: dict, from_valve: ValvePosition, to_valve: ValvePosition,
                          speed_in: int = None, speed_out: int = None, secure: bool = True, wait: bool = False) -> bool:
        """
        Transfers the desired volume between pumps.

        Args:
            pumps_and_volumes_dict: The names and volumes to be pumped for each pump.

            from_valve: The valve to transfer from.

            to_valve: the valve to transfer to.

            speed_in: The speed at which to receive transfer, default set to None.

            speed_out: The speed at which to transfer, default set to None

            secure: Ensures that everything is correct, default set to False.

            wait: Wait for the pumps to be idle, default set to False.

        """

        remaining_volume = {}
        volume_to_transfer = {}

        # Wait until all the pumps have pumped to start deliver
        self.apply_command_to_pumps(list(pumps_and_volumes_dict.keys()), "wait_until_idle")

        # Pump the target volume (or the maximum possible) for each pump
        for pump_name, pump_target_volume in pumps_and_volumes_dict.items():
            # Get pump
            try:
                pump = self.pumps[pump_name]
            except KeyError:
                self.logger.warning(f"Pump specified {pump_name} not found in the controller! (Available: {self.pumps}")
                return False

            # Find the volume to transfer (maximum pumpable or target, whatever is lower)
            volume_to_transfer[pump_name] = min(pump_target_volume, pump.remaining_volume)
            pump.pump(volume_in_ml=volume_to_transfer[pump_name], from_valve=from_valve, speed_in=speed_in, wait=False,
                      secure=secure)

            # Calculate remaining volume
            remaining_volume[pump_name] = pump_target_volume - volume_to_transfer[pump_name]

        # Wait until all the pumps have pumped to start deliver
        self.apply_command_to_pumps(list(pumps_and_volumes_dict.keys()), "wait_until_idle")

        for pump_name, volume_to_deliver in volume_to_transfer.items():
            pump = self.pumps[pump_name]  # This cannot fail otherwise it would have failed in pumping ;)
            pump.deliver(volume_in_ml=volume_to_deliver, wait=False, to_valve=to_valve, speed_out=speed_out)

        left_to_pump = {pump: volume for pump, volume in remaining_volume.items() if volume > 0}
        if len(left_to_pump) > 0:
            self.parallel_transfer(left_to_pump, from_valve, to_valve, speed_in, speed_out, secure)
        elif wait is True:  # If no more pumping is needed wait if needed
            self.apply_command_to_pumps(list(pumps_and_volumes_dict.keys()), "wait_until_idle")
        return True
