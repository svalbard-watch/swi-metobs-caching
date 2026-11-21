# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import sys
import os
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from abc import ABC, abstractmethod
from source.logger.logger import Logger
from source.configHandler.confighandler import ConfigHandler

config_files = [
    "static/config/fixed_stations.json",
    "static/config/mobile_stations.json",
]


class DataSource(ABC):
    """
    An abstract base class for data sources that fetch and process weather or
    observational data from an external API.

    Attributes:
        api_key (str): API key used for authentication with the data source.
        logger (logging.Logger): Logger for recording actions and errors.
    """

    def __init__(self, api_key=None):
        """
        Initialize the DataSource with an optional API key and set up a logger.

        Args:
            api_key (str, optional): API key for authenticating with the data source.
        """
        self.api_key = api_key
        self.logger = Logger.setup_logger(self.__class__.__name__)
        self.config = ConfigHandler()

    @abstractmethod
    def fetch_station_data(self, station_id):
        """
        Fetch metadata or configuration for a station.

        Args:
            station_id (str): The ID of the station to fetch data for.

        Returns:
            dict: Metadata or configuration for the station.
        """
        pass

    @abstractmethod
    def fetch_realtime_data(self, station_id):
        """
        Retrieve real-time observational data for a specific station.

        Args:
            station_id (str): The ID of the station to fetch real-time data for.

        Returns:
            dict: Transformed real-time data.
        """
        pass

    @abstractmethod
    def fetch_timeseries_data(self, station_id, start_time, end_time, return_df=False):
        """
        Query historical data for a specific station and time range.

        Args:
            return_df: Return the data as a dictionary for API response or pandas dataframe.
            station_id (str): The ID of the station to fetch data for.
            start_time (str): The start of the time range in ISO 8601 format.
            end_time (str): The end of the time range in ISO 8601 format.

        Returns:
            dict: Transformed historical data.
        """
        pass

    @abstractmethod
    def transform_realtime_data(self, raw_data, station_id):
        """
        Process and format raw real-time data into a standardized structure.

        Args:
            raw_data (dict): Raw data retrieved from the data source.
            station_id (str): The ID of the station associated with the data.

        Returns:
            dict: Processed and formatted real-time data.
        """
        pass

    @abstractmethod
    def transform_timeseries_data(self, raw_data, station_id, return_df, resample):
        """
        Process and format raw historical data into a standardized structure.

        Args:
            raw_data (dict): Raw data retrieved from the data source.
            station_id (str): The ID of the station associated with the data.

        Returns:
            dict: Processed and formatted time series data.
        """
        pass

    @abstractmethod
    def is_station_online(self, station_id, max_inactive_minutes=120):
        """

        Args:
            station_id (str): The ID of the station associated with the data.
            max_inactive_minutes (int): The maximum number of minutes allowed for a station. Default is 120 minutes.

        Returns:
            bool: True if station online, False otherwise.
        """
        pass

    # Query-string parameters whose values are secrets and must never be logged.
    _SECRET_QS_RE = re.compile(
        r"([?&](?:pw|password|api_key|apikey|token|key)=)[^&\s]+", re.IGNORECASE
    )

    def _handle_error(self, error):
        """
        Log and handle errors during data fetching or processing.

        Any secret that rode in a request URL (e.g. Holfuy's ``pw``) is redacted
        from the message, since exception strings include the full request URL.

        Args:
            error (Exception): The exception that occurred.
        """
        message = self._SECRET_QS_RE.sub(r"\1<redacted>", str(error))
        self.logger.error(f"Error occurred: {message}")

    def df_to_timeserie(self, df):
        """
        Convert a DataFrame to a list of time series observations.

        Args:
            df (pd.DataFrame): Input DataFrame where the index is the timestamp.

        Returns:
            list: A list of dictionaries representing time series data.
        """
        try:
            keys = df.columns.tolist()  # Get column names
            timeserie = []

            for index, row in df.iterrows():
                lat, lon = None, None
                obs = {
                    "timestamp": index.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                }  # Use the index as the timestamp
                for key in keys:
                    if key == "latitude":
                        lat = row.get(key, None)
                    elif key == "longitude":
                        lon = row.get(key, None)
                    else:
                        obs[key] = float(
                            f"{row[key]:.2f}"
                        )  # Access row data using the column name

                if lat and lon:
                    obs["location"] = {
                        "lat": float(f"{lat:.4f}"),
                        "lon": float(f"{lon:.4f}"),
                    }
                timeserie.append(obs)

            return timeserie

        except Exception as e:
            self._handle_error(e)
            return None
