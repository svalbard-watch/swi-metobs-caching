# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import requests
import pandas as pd
import numpy as np
import os

from .datasource import DataSource


class HolfuySource(DataSource):
    """
    A data source integration for the Frost API provided by MET Norway.
    This class allows fetching metadata, real-time, and historical weather data
    from specific weather stations.

    Attributes:
        BASE_URL (str): The base URL for the Frost API.
        session (requests.Session): A session object for making authenticated API requests.
    """

    def __init__(self, api_key=None):
        """
        Initialize the FrostSource instance with the given client ID.

        Args:
            client_id (str): The client ID for authenticating with the Frost API.
        """
        super().__init__(api_key=os.getenv("SWI_HOLFUY_API_KEY", api_key))
        self.session = requests.Session()

    def fetch_station_data(self, station_id):
        """
        Fetch metadata for a specific station.

        Args:
            station_id (str): The ID of the weather station.

        Returns:
            dict: A dictionary containing station metadata if successful.
            None: If an error occurs during the request.
        """
        return {}
        endpoint = f"{self.BASE_URL}/sources/v0.jsonld"
        params = {"ids": station_id}
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            self.logger.info(f"Fetched station data for {station_id}")
            return data
        except requests.exceptions.RequestException as e:
            self._handle_error(e)
            return None

    def fetch_realtime_data(self, station_id):
        """
        Retrieve real-time weather data for a specific station.

        Args:
            station_id (str): The ID of the weather station.

        Returns:
            dict: A dictionary containing transformed real-time weather data if successful.
            None: If an error occurs during the request.
        """
        endpoint = f"https://api.holfuy.com/live/?s={station_id}&m=JSON&tu=C&su=m/s&utc"

        try:
            # Send the API key in the POST body (Holfuy supports this) so it
            # never appears in the URL, access logs, or exception strings.
            response = self.session.post(endpoint, data={"pw": self.api_key})
            response.raise_for_status()
            raw_data = response.json()
            self.logger.info(f"Fetched real-time data for {station_id}")
            return self.transform_realtime_data(raw_data, station_id)
        except requests.exceptions.RequestException as e:
            self._handle_error(e)
            return None

    def fetch_timeseries_data(self, station_id, start_time, end_time, return_df=False):
        """
        Query historical weather data for a specific time range.

        Args:
            return_df: Return the data as a dictionary for API response or pandas dataframe.
            station_id (str): The ID of the weather station.
            start_time (str): The start time for the query in ISO 8601 format.
            end_time (str): The end time for the query in ISO 8601 format.

        Returns:
            dict: A dictionary containing transformed historical weather data if successful.
            None: If an error occurs during the request.
        """
        start_str = (pd.to_datetime(start_time) - pd.Timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        end_str = (pd.to_datetime(end_time) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        endpoint = f"https://api.holfuy.com/archive/?s={station_id}&m=JSON&tu=C&su=m/s&utc&type=1&start_date={start_str}&stop_date={end_str}"

        try:
            # API key goes in the POST body, not the URL (keeps it out of logs).
            response = self.session.post(endpoint, data={"pw": self.api_key})
            response.raise_for_status()
            raw_data = response.json()
            self.logger.info(
                f"Fetched timeseries data for {station_id} from {start_time} to {end_time}"
            )
            return self.transform_timeseries_data(
                raw_data,
                station_id,
                return_df=return_df,
                start_time=start_time,
                end_time=end_time,
            )
        except requests.exceptions.RequestException as e:
            self._handle_error(e)
            return None

    def transform_timeseries_data(
        self,
        raw_data,
        station_id,
        return_df=False,
        resample="60min",
        start_time=None,
        end_time=None,
    ):
        """
        Transform raw historical data into a time series format.

        Args:
            return_df (bool): Should a DataFrame be returned instead of raw data.
            resample (str): Resampling interval for the data (e.g., '30min', '1H'), default = '60min'.
            raw_data (dict): Raw data retrieved from the Frost API.
            station_id (str): The ID of the weather station.

        Returns:
            dict: Transformed data containing a list of timestamped observations.
            pd.DataFrame: DataFrame with resampled and transformed data if `return_df` is True.
            None: If an error occurs during transformation.
        """
        try:
            # Fetch variable mapping for the station
            variable_mapping = self.config.get_variable(station_id)

            timeseries = []

            for m in raw_data.get("measurements", []):
                ts = {}

                if m["dateTime"]:
                    ts["timestamp"] = (
                        pd.to_datetime(m["dateTime"]).strftime("%Y-%m-%dT%H:%M:%S.%f")[
                            :-3
                        ]
                        + "Z"
                    )
                else:
                    raise ("No TimeStamp found in the API Answer")

                for key, value in variable_mapping.items():
                    if m.get(value):
                        ts[key] = float(m[value])
                    elif m.get(value.split("_")[0]) and m.get(value.split("_")[0]).get(
                        value.split("_")[1]
                    ):
                        ts[key] = float(m[value.split("_")[0]][value.split("_")[1]])
                    else:
                        ts[key] = np.nan

                timeseries.append(ts)

            # Create DataFrame from the timeseries data
            df = pd.DataFrame(timeseries)

            # Ensure 'timestamp' is parsed as datetime
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)

            # print(type(start_time), end_time, df)

            if start_time and end_time and not df.empty:
                df = df[
                    (df.index >= pd.to_datetime(start_time).tz_localize("UTC"))
                    & (df.index <= pd.to_datetime(end_time).tz_localize("UTC"))
                ]
            elif start_time and not df.empty:
                df = df[df.index >= pd.to_datetime(start_time).tz_localize("UTC")]
            elif end_time and not df.empty:
                df = df[df.index <= pd.to_datetime(end_time).tz_localize("UTC")]

            # Resample if required
            if resample != "AUTO" and not df.empty:
                df = df.resample(resample).mean()
                df.dropna(inplace=True)

            # Return DataFrame or raw timeseries list
            if return_df:
                return df

            self.logger.info(
                "Transformed raw time series data into the specified structure dynamically."
            )
            return {"id": station_id, "timeseries": self.df_to_timeserie(df)}

        except Exception as e:
            self._handle_error(e)
            return None

    def transform_realtime_data(self, raw_data, station_id):
        """
        Transform raw real-time data into a structured format.

        Args:
            raw_data (dict): Raw data retrieved from the Frost API.
            station_id (str): The ID of the weather station.

        Returns:
            dict: Transformed data containing the latest observation for each variable.
            None: If an error occurs during transformation or if no valid data is found.
        """
        try:
            variable_mapping = self.config.get_variable(station_id)
            # print(variable_mapping)
            ts = {}

            if raw_data["dateTime"]:
                ts["timestamp"] = (
                    pd.to_datetime(raw_data["dateTime"]).strftime(
                        "%Y-%m-%dT%H:%M:%S.%f"
                    )[:-3]
                    + "Z"
                )
            else:
                raise ("No TimeStamp found in the API Answer")

            for key, value in variable_mapping.items():
                if raw_data.get(value):
                    ts[key] = raw_data[value]
                elif raw_data.get(value.split("_")[0]) and raw_data.get(
                    value.split("_")[0]
                ).get(value.split("_")[1]):
                    ts[key] = raw_data[value.split("_")[0]][value.split("_")[1]]
                else:
                    ts[key] = None

            # print(ts)
            return {"id": station_id, "timeseries": [ts]}

        except Exception as e:
            self._handle_error(e)
            return None

    def is_station_online(self, station_id, max_inactive_minutes=120):
        """
        Determine whether a given station is 'online' by checking the timestamp of
        its most recent real-time observation. If the latest data is less than
        `max_age_hours` old, the station is considered online.

        Args:
            station_id (str): The ID of the weather station.
            max_age_hours (int): Maximum age (in hours) of the latest observation
                                 to still consider the station 'online'.

        Returns:
            bool: True if the station is considered online, False otherwise.
        """

        endpoint = f"https://api.holfuy.com/live/?s={station_id}&m=JSON&tu=C&su=m/s&utc"

        try:
            # API key in the POST body, not the URL (keeps it out of logs).
            response = self.session.post(endpoint, data={"pw": self.api_key})
            response.raise_for_status()
            response_json = response.json()
        except requests.exceptions.RequestException as e:
            self._handle_error(e)
            return False

        if not ("error" in response_json.keys() or "errorCode" in response_json.keys()):
            return True
        else:
            self.logger.warning(f"Station Holfuy {station_id} is offline.")
            return False
