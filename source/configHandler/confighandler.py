# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import json
from source.logger.logger import Logger
import difflib

config_files = [
    "config/stations/fixed_stations.json",
    "config/stations/mobile_stations.json",
]

variables_file = "config/variables/station_variables.json"


class StationNotFoundError(Exception):
    """
    Exception raised when a station is not found in the configuration files.
    """

    def __init__(self, station_id, suggestions=None):
        message = f"Station ID '{station_id}' not found."
        if suggestions:
            message += f" Did you mean: {', '.join(suggestions)}?"
        super().__init__(message)
        self.station_id = station_id
        self.suggestions = suggestions


class ConfigHandler:
    """
    A handler for managing configuration files and providing station-specific data.

    Attributes:
        config_files (list): List of file paths to configuration JSON files.
        _cached_configs (list or None): Cached configuration data, loaded once and reused.
        logger (logging.Logger): Logger instance for logging actions and errors.
    """

    def __init__(self):
        """
        Initialize the ConfigHandler with default configuration files and logger.
        """
        self.config_files = config_files
        self._cached_configs = None
        self._cached_credential = None
        self.variables_file = variables_file
        self._cached_limits = None
        self.logger = Logger.setup_logger(self.__class__.__name__)

    def get_variable_limits(self):
        """
        Read the plausible value range of each variable from the variable catalogue.

        A missing or unreadable catalogue is not an error: the run continues
        without range checks. The result is cached after the first call.

        Returns:
            dict: ``{variable: (min, max)}``; a bound is None when not defined.
        """
        if self._cached_limits is not None:
            return self._cached_limits

        limits = {}
        try:
            with open(self.variables_file, encoding="utf-8") as file:
                catalogue = json.load(file)
            for name, entry in catalogue.items():
                limits[name] = (entry.get("minValue"), entry.get("maxValue"))
        except (OSError, ValueError, AttributeError) as e:
            self.logger.warning(
                f"No variable limits loaded from {self.variables_file}: {e}"
            )
            limits = {}

        self._cached_limits = limits
        return limits

    def get_variable(self, station_id):
        """
        Fetch a mapping of variable identifiers for a specific station.

        Args:
            station_id (str): The ID of the station.

        Returns:
            dict: Mapping of variable element IDs to names, or None if not found.

        Raises:
            ValueError: If `station_id` is not provided.
        """
        if not station_id:
            raise ValueError("station_id must be provided")

        configs = self._load_config()
        for config in configs:
            if config.get("id") == station_id:
                return config.get("variables", None)

        suggestions = difflib.get_close_matches(
            station_id,
            [config.get("id") for config in configs if "id" in config],
            n=3,
            cutoff=0.6,
        )
        raise StationNotFoundError(station_id, suggestions)

    def get_metadata(self, station_id):
        """
        Fetch metadata for a specific station.

        Args:
            station_id (str): The ID of the station.

        Returns:
            dict: Metadata for the station, or None if not found.

        Raises:
            ValueError: If `station_id` is not provided.
        """
        if not station_id:
            raise ValueError("station_id must be provided")

        configs = self._load_config()
        for config in configs:
            if config.get("id") == station_id:
                if "datasource" not in config:
                    # config["datasource"] = "FrostDatasource"
                    pass
                return config
        return None

    def get_stations(self, type="all"):
        """
        Get a list of station IDs based on the specified type.

        Args:
            type (str): Type of stations to fetch. Options are:
                - "all": Return all station IDs.
                - "mobile": Return IDs of mobile stations.
                - "fixed": Return IDs of fixed stations.

        Returns:
            list: List of station IDs matching the specified type.

        Raises:
            AssertionError: If `type` is not one of ["all", "mobile", "fixed"].
        """
        assert type in ["all", "mobile", "fixed"], (
            "Type must be one of ['all', 'mobile', 'fixed']"
        )

        configs = self._load_config()
        stations = []
        for config in configs:
            if type == "all" or config.get("type") == type:
                stations.append(config.get("id"))
        return stations

    def _load_config(self):
        """
        Load configurations from a list of JSON files.

        Each configuration dictionary is augmented with a 'station_type'
        field. If the configuration contains the key 'mobile', the station_type
        is set to 'mobile'; otherwise it defaults to 'fixed'.

        Returns:
            list: A combined list of configuration dictionaries from all files.

        Notes:
            - Caches the configuration data to avoid repeated file I/O.
            - Logs and handles errors such as missing files or invalid JSON.

        Raises:
            FileNotFoundError: If a configuration file is not found.
            json.JSONDecodeError: If a configuration file contains invalid JSON.
        """
        if self._cached_configs is not None:
            return self._cached_configs

        configs = []
        for file in self.config_files:
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    # Ensure we have a list of config dictionaries
                    config_list = data if isinstance(data, list) else [data]
                    for config in config_list:
                        # Add station type: if the config contains the key 'mobile',
                        # mark it as 'mobile', otherwise default to 'fixed'
                        if "mobile" in file:
                            config["type"] = "mobile"
                        else:
                            config["type"] = "fixed"
                    configs.extend(config_list)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                self._handle_error(e)

        self._cached_configs = configs
        return configs

    def _handle_error(self, error):
        """
        Log and handle errors that occur during configuration loading or data fetching.

        Args:
            error (Exception): The exception that occurred.
        """
        self.logger.error(f"Error occurred: {error}")
