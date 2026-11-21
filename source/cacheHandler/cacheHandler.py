# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import sys
import os


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from source.configHandler.confighandler import ConfigHandler
from source.datasource.datasourceFactory import get_datasource

from source.logger.logger import Logger

import json
from datetime import datetime, timedelta, timezone
import shutil
import pandas as pd


class CacheHandler:
    def __init__(self, directory="./data/", path_config=None, cleaning_list=None):
        """
        Initialize a CacheHandler instance to manage caching of station data.

        Args:
            directory (str): The base directory where cache files are stored.
                Default is './cache/'.
            path_config (dict, optional): A dictionary mapping cache entry names to file paths.
                If None, defaults to:
                    {
                        'station_status': 'cache_stations_status.json',
                        'station_metadata_single': './000_stations_metadata/',
                        'realtime_data': './111_data_realtime/',
                        'hourly_data' : './111_hourly_data/',
                        'online': './000_status_online_stations/',
                        'offline': './000_status_offline_stations/',
                    }
            cleaning_list (list, optional): A list of cache entry keys to be cleared during cache operations.
                Default is ['online', 'offline'].

        Returns:
            None
        """
        self.directory = directory
        self.logger = Logger.setup_logger("CacheHandler")
        self.config = ConfigHandler()
        self.online_stations = []

        os.makedirs(self.directory, exist_ok=True)

        if path_config is None:
            self.path_config = {
                "station_status": "./realtime/000_stations_status/",
                "realtime_data": "./realtime/000_latest_obs/",
                "historical": "./historical/000_long_timeseries/",
                "hourly_data": "./realtime/000_hourly_data/",
                "online": "./realtime/000_status_online_stations/",
                "offline": "./realtime/000_status_offline_stations/",
            }
        else:
            self.path_config = path_config

        if cleaning_list is None:
            self.cleaning_list = ["online", "offline"]
        else:
            self.cleaning_list = cleaning_list

    def cache_stations_status(self):
        """
        Retrieve and cache the status and metadata for all stations.

        This method iterates over all available stations, checks if they are online, retrieves their metadata and available
        variables, and compiles a status report with a timestamp for each station. The resulting list of station states is
        written to a JSON cache file. Additionally, it clears specific cache entries as defined by the cleaning list.

        Args:
            None

        Returns:
            list: A list of dictionaries, each containing station information such as id, name, type, location, variables,
                  status (online/offline), last_updated timestamp, project, and icon.
        """
        self.logger.info("Starting to cache station statuses...")

        stations = self.config.get_stations(type="all")
        self.logger.info(f"Retrieved {len(stations)} stations for processing.")

        state = {}
        online = {}
        offline = {}

        for station_id in stations:
            try:
                self.logger.debug(f"Processing station status for: {station_id}")
                datasource = get_datasource(station_id, config=self.config)
                is_online = datasource.is_station_online(station_id)
                self.logger.debug(
                    f"Station {station_id} online status: {'online' if is_online else 'offline'}"
                )

                if is_online:
                    self.online_stations.append(station_id)

                metadata = self.config.get_metadata(station_id) or {}
                variables = self.config.get_variable(station_id)
                timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                infos = {
                    "id": station_id,
                    "name": metadata.get("name", "Unknown"),
                    "type": metadata.get("type", "Unknown"),
                    "location": {
                        "lat": metadata.get("lat", None),
                        "lon": metadata.get("lon", None),
                    },
                    "variables": list(variables.keys()) if variables else [],
                    "status": "online" if is_online else "offline",
                    "last_updated": timestamp or "Unknown",
                    "project": metadata.get("project", "Unknown"),
                    "icon": metadata.get("icon", "/static/images/red_dot.png"),
                }

                state[station_id] = infos
                if is_online:
                    online[station_id] = infos
                else:
                    offline[station_id] = infos

                self.logger.info(f"Successfully processed station {station_id}")

            except Exception as e:
                self.logger.error(
                    f"Error processing station {station_id}: {e}", exc_info=True
                )

        self.logger.info(
            f"Finished caching station statuses. Total stations processed: {len(state)}"
        )

        self._write_cache(
            state, os.path.join(self.path_config.get("station_status"), "all_dict.json")
        )
        self._write_cache(
            online,
            os.path.join(self.path_config.get("station_status"), "online_dict.json"),
        )
        self._write_cache(
            offline,
            os.path.join(self.path_config.get("station_status"), "offline_dict.json"),
        )

        # self._clear_cache(self.cleaning_list)

        return state

    def cache_realtime_data(self):
        """
        Retrieve and cache real-time data for online stations.

        This method fetches real-time data from each online station using the appropriate data source. If the list of online
        stations is not already populated, it calls cache_stations_status to update it. For each online station, the real-time
        data is written to a JSON file located in the path specified by the 'realtime_data' key in path_config.

        Args:
            None

        Returns:
            None
        """

        self.logger.info("Starting to cache realtime data...")

        if self.online_stations is None or len(self.online_stations) == 0:
            self.logger.info(
                "Unknown station status. Starting collection and caching of the station status..."
            )
            self.cache_stations_status()

        if self.online_stations is None or len(self.online_stations) == 0:
            self.logger.warning("No online stations found. Skipping data caching.")
            return

        latest_station_data = {}

        for station in self.online_stations:
            try:
                self.logger.debug(f"Fetching real-time data for station: {station}")
                datasource = get_datasource(station, config=self.config)

                data = datasource.fetch_realtime_data(station)

                if not data:
                    self.logger.warning(
                        f"No data fetched for {station}, skipping cache write."
                    )
                    continue

                latest_station_data[station] = data

            except Exception as e:
                self.logger.error(
                    f"Error processing real-time data for {station}: {e}", exc_info=True
                )

        self._write_cache(
            latest_station_data,
            os.path.join(self.path_config.get("realtime_data"), "latest_dict.json"),
        )

        self.logger.info("Finished caching real-time data.")

    def cache_past_hourly_data(self, hours_ago=25):
        """
        Retrieve and cache hourly data for online stations.

        This method fetches hourly data from each online station using the appropriate data source. If the list of online
        stations is not already populated, it calls cache_stations_status to update it. For each online station, the hourly
        data is written to a JSON file located in a subdirectory specified by the 'hourly_data' key in path_config.

        Args:
            hours_ago (int): Number of hours ago to fetch data for. Default is 1.

        Returns:
            None
        """
        self.logger.info("Starting to cache hourly data...")

        self.path_config.get("hourly_data", "/hourly_data/")

        if self.online_stations is None or len(self.online_stations) == 0:
            self.logger.info(
                "Unknown station status. Starting collection and caching of the station status..."
            )
            self.cache_stations_status()

        if self.online_stations is None or len(self.online_stations) == 0:
            self.logger.warning("No online stations found. Skipping data caching.")
            return

        # Calculate the start and end times for the hourly data
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_ago)
        start_of_day = end_time.replace(hour=0, minute=0, second=0, microsecond=0)

        result = {-i: {} for i in range(1, hours_ago + 1)}

        for station in self.online_stations:
            try:
                self.logger.debug(f"Fetching hourly data for station: {station}")
                datasource = get_datasource(station, config=self.config)

                # print(datetime.utcnow().isoformat(),(start_time - timedelta(hours=12)).isoformat(), type((start_time - timedelta(hours=12)).isoformat()))
                data = datasource.fetch_timeseries_data(
                    station,
                    (start_time - timedelta(hours=12)).isoformat().split("+")[0],
                    (end_time).isoformat().split("+")[0],
                    return_df=True,
                )

                if data is None:
                    self.logger.warning(
                        f"No hourly data returned for {station}, skipping it."
                    )
                    continue

                path_parquet = os.path.join(
                    self.path_config.get("historical", "./000_long_timeseries/"),
                    station,
                    f"{end_time.strftime('%Y-%m-%d')}.parquet",
                )
                self._atomic_write_parquet(
                    data[
                        (data.index <= pd.to_datetime(end_time))
                        & (data.index >= pd.to_datetime(start_of_day))
                    ],
                    path_parquet,
                )

                data = datasource.df_to_timeserie(
                    data[
                        (data.index <= pd.to_datetime(end_time))
                        & (data.index >= pd.to_datetime(start_time))
                    ]
                )

                data = {"id": station, "timeseries": data}

                if not data or "timeseries" not in data:
                    self.logger.warning(
                        f"No data fetched for {station}, skipping cache write."
                    )
                    continue

                # Create a subdirectory for each hourly shift
                for shift in range(1, hours_ago + 1):
                    shift_time = end_time - timedelta(hours=shift)
                    # shift_path = os.path.join(hourly_data_path, f"-{shift}")

                    # Find the corresponding data entry for the shift
                    entry = next(
                        (
                            e
                            for e in data["timeseries"]
                            if e["timestamp"].startswith(shift_time.isoformat()[:13])
                        ),
                        None,
                    )
                    if entry:
                        # Prepare the data structure with a single record in timeseries
                        data_to_cache = {"id": station, "timeseries": [entry]}
                        result[-shift][station] = data_to_cache
                    else:
                        data_to_cache = {"id": station, "timeseries": None}
                        result[-shift][station] = data_to_cache
                        self.logger.warning(
                            f"No data entry found for {station} at shift {shift}."
                        )

            except Exception as e:
                self.logger.error(
                    f"Error processing hourly data for {station}: {e}", exc_info=True
                )

        for key, value in result.items():
            path = os.path.join(
                self.path_config.get("hourly_data", "./000_hourly_data/"), f"{key}.json"
            )
            self._write_cache(value, path)

        self.logger.info("Finished caching hourly data.")

    def _clear_cache(self, entries):
        """
        Clear specified cache entries by deleting their corresponding files or directories.

        This private method iterates over the list of cache entry keys provided, retrieves each corresponding path from
        path_config, constructs the full path by joining with the base cache directory, and deletes the file or directory using
        the _delete_path method.

        Args:
            entries (list): A list of keys corresponding to cache entries to be cleared (e.g., ['online', 'offline']).

        Returns:
            None
        """

        self.logger.info(f"Starting cache clearing for {len(entries)} entries.")

        for entry in entries:
            file_path = self.path_config.get(entry)
            if file_path is None:
                self.logger.warning(f"No path configured for cache entry: {entry}")
                continue
            file_path = os.path.join(self.directory, file_path)

            if file_path:  # Ensure the path is valid
                self.logger.debug(f"Attempting to delete cache entry: {file_path}")
                self._delete_path(file_path)
            else:
                self.logger.warning(f"Invalid cache path for entry: {entry}")

        self.logger.info("Cache clearing completed.")

    def _atomic_write_parquet(self, df, filename):
        path = os.path.join(self.directory, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        df.to_parquet(path + ".tmp")

        os.replace(path + ".tmp", path)

    def _write_cache(self, json_data, filename):
        """
        Write JSON-serializable data to a cache file.

        This private method constructs the full file path by combining the base cache directory with the provided filename,
        ensures that any necessary subdirectories exist, and writes the data as JSON to the file.

        Args:
            json_data (dict or list): The data to be written to the cache file in JSON format.
            filename (str): The relative path (including filename) where the data should be written.

        Returns:
            None
        """

        # Construct the full file path
        file_path = os.path.join(self.directory, filename)

        # Extract the directory path from the filename and ensure it exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            with open(file_path + ".tmp", "w", encoding="utf-8") as file:
                json.dump(json_data, file, indent=4)
            os.replace(file_path + ".tmp", file_path)
            self.logger.info(f"Cache written successfully to {file_path}")
        except Exception as e:
            self.logger.error(f"Error writing cache to {file_path}: {e}", exc_info=True)

    def _read_cache(self, struct):
        """
        Read and return JSON data from a cache file.

        This private method constructs the full file path by joining the base cache directory with the provided structure,
        attempts to read and parse the JSON data from the file, and returns it. If the file is not found or an error occurs,
        an appropriate message is logged and None is returned.

        Args:
            struct (str): The relative file path or structure identifier for the cache file to be read.

        Returns:
            dict or list: The JSON data from the cache file if successfully read.
            None: If the file is not found or an error occurs during reading.
        """
        file_path = os.path.join(self.directory, struct)
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                self.logger.info(f"Cache read successfully from {file_path}")
                return data
        except FileNotFoundError:
            self.logger.warning(f"Cache file {file_path} not found.")
            return None
        except json.JSONDecodeError:
            self.logger.error(f"Error decoding JSON from {file_path}.")
            return None
        except Exception as e:
            self.logger.error(f"Error reading cache from {file_path}: {e}")
            return

    def _delete_path(self, path):
        """
        Delete the specified file or directory.

        This private method checks whether the provided path corresponds to a file or a directory. If it is a file, it
        is deleted using os.remove; if it is a directory, it is deleted recursively using shutil.rmtree. Appropriate log messages
        are recorded based on the outcome.

        Args:
            path (str): The path to the file or directory to be deleted.

        Returns:
            None
        """

        try:
            if os.path.isfile(path):  # Check if it's a file
                os.remove(path)
                self.logger.info(f"File deleted: {path}")
            elif os.path.isdir(path):  # Check if it's a directory
                shutil.rmtree(path)
                self.logger.info(f"Directory deleted: {path}")
            else:
                self.logger.warning(f"Path not found: {path}")
        except Exception as e:
            self.logger.error(f"Error deleting {path}: {e}", exc_info=True)
