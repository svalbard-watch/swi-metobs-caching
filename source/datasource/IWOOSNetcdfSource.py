# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2


from datetime import datetime, timedelta, timezone
import xarray as xr
import pandas as pd
import traceback

from .datasource import DataSource


class IWOOSNetcdfSource(DataSource):
    """
    A data source integration for IWOOS buoys served as THREDDS/OPeNDAP NetCDF
    datasets. This class allows fetching metadata, real-time, and historical
    weather data from specific weather stations.
    """

    def __init__(self, api_key=None):
        """
        Initialize the IWOOSNetcdfSource instance with the given client ID.

        Args:
            client_id (str): The client ID for authenticating with the Frost API.
        """
        super().__init__(api_key=api_key)

    def fetch_station_data(self, station_id):
        """
        Fetch metadata for a specific station. IWOOS don't provide any metadata.

        Args:
            station_id (str): The ID of the weather station.

        Returns:
            dict: A dictionary containing station metadata if successful.
            None: If an error occurs during the request.
        """
        return {}

    def fetch_realtime_data(self, station_id):
        """
        Retrieve real-time weather data for a specific station.

        Args:
            station_id (str): The ID of the weather station.

        Returns:
            dict: A dictionary containing transformed real-time weather data if successful.
            None: If an error occurs during the request.
        """
        try:
            self.logger.info(f"Fetched real-time data for {station_id}")
            return self.transform_realtime_data(self.open_data(station_id), station_id)
        except Exception as e:
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
        try:
            raw_data = self.open_data(station_id)[slice(start_time, end_time)]

            self.logger.info(
                f"Fetched timeseries data for {station_id} from {start_time} to {end_time}"
            )

            return self.transform_timeseries_data(
                raw_data, station_id, return_df=return_df
            )
        except Exception as e:
            self._handle_error(e)
            return None

    def transform_timeseries_data(
        self, raw_data, station_id, return_df=False, resample="60min"
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
            if resample != "AUTO" and not raw_data.empty:
                raw_data = raw_data.resample(resample).mean().interpolate()

            variable_mapping["latitude"] = "lat"
            variable_mapping["longitude"] = "lon"

            raw_data = raw_data.rename(
                columns={value: key for key, value in variable_mapping.items()}
            )

            if return_df:
                return raw_data

            self.logger.info(
                "Transformed raw time series data into the specified structure dynamically."
            )
            return {"id": station_id, "timeseries": self.df_to_timeserie(raw_data)}

        except Exception as e:
            self._handle_error(e)
            traceback.print_exc()
            return None

    def transform_realtime_data(self, raw_data, station_id):
        """
        Transform raw real-time data into a structured format.

        IWOOS sensors (waves, temperature profile, GPS) don't report on the same
        schedule, so a single row of `raw_data` is usually mostly NaN. The latest
        valid value is therefore taken independently for each column, rather than
        reading a single "most recent" row. Columns already carry their final
        names (set in `open_data`), including per-depth pivoted names such as
        `sea_temperature_0.10`.

        Args:
            raw_data (pd.DataFrame): Raw data retrieved from `open_data`, indexed by time.
            station_id (str): The ID of the weather station.

        Returns:
            dict: Transformed data containing the latest observation for each variable.
            None: If an error occurs during transformation or if no valid data is found.
        """
        try:
            if raw_data.empty:
                return None

            most_recent_date = raw_data.index.max()

            observation = {
                "timestamp": most_recent_date.tz_localize("UTC").strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                )[:-3]
                + "Z",
            }

            lat = raw_data["lat"].dropna()
            lon = raw_data["lon"].dropna()
            if not lat.empty and not lon.empty:
                observation["location"] = {
                    "lat": round(float(lat.iloc[-1]), 6),
                    "lon": round(float(lon.iloc[-1]), 6),
                }

            for column in raw_data.columns:
                if column in ("lat", "lon"):
                    continue
                values = raw_data[column].dropna()
                if values.empty:
                    observation[column] = "NA"
                    continue
                try:
                    observation[column] = round(float(values.iloc[-1]), 2)
                except Exception as e:
                    observation[column] = "NA"
                    self.logger.warning(
                        f"Error occurred while transforming variable '{column}': {e}"
                    )

            return {"id": station_id, "timeseries": [observation]}

        except Exception as e:
            self._handle_error(e)
            return None

    def is_station_online(self, station_id, max_inactive_minutes=200):
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
        data = self.fetch_realtime_data(station_id)
        if not data:
            self.logger.warning(f"No data returned for station {station_id}.")
            self.logger.info(f"Station {station_id} is considered OFFLINE.")
            return False

        # print(data)

        # Check if the data structure is as expected
        timeseries = data.get("timeseries")
        if not timeseries or len(timeseries) == 0:
            self.logger.warning(f"No timeseries entries for station {station_id}.")
            self.logger.info(f"Station {station_id} is considered OFFLINE.")
            return False

        # We'll take the first (and presumably most recent) timeseries entry
        latest_entry = timeseries[0]
        timestamp_str = latest_entry.get("timestamp")
        if not timestamp_str:
            self.logger.warning(f"No 'timestamp' field for station {station_id}.")
            self.logger.info(f"Station {station_id} is considered OFFLINE.")
            return False

        # Convert to Python datetime; handle trailing "Z" by replacing with UTC offset.
        try:
            latest_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError as e:
            self.logger.error(f"Error parsing timestamp for station {station_id}: {e}")
            return False

        # Define the cutoff time
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(
            minutes=max_inactive_minutes
        )

        # If the station reported data newer than the cutoff, it's "online"
        if latest_time >= cutoff_time:
            self.logger.info(
                f"Station {station_id} last timestamp = {latest_time} (< {max_inactive_minutes}min old). Considered ONLINE."
            )
            return True
        else:
            self.logger.info(
                f"Station {station_id} last timestamp = {latest_time}, older than {max_inactive_minutes}min. OFFLINE."
            )
            return False

    def open_data(self, station_id):
        config = self.config.get_metadata(station_id)
        template_url = config.get("url")

        if template_url is None:
            raise ValueError("The 'url' field is missing in the configuration.")
        template_url = datetime.now().strftime(template_url)

        variables_mapping = config.get("variables")
        if variables_mapping is None:
            raise ValueError("The 'variables' field is missing in the configuration.")

        variables_to_keep = list(variables_mapping.values()) + [
            "time",
            "lat",
            "lon",
            "time_temp",
            "time_waves_imu",
        ]

        ds = xr.open_dataset(template_url)[variables_to_keep].squeeze(drop=True)
        ds = ds.rename({v: k for k, v in variables_mapping.items()})

        observations_dim = [dim for dim in ds.dims if "obs" in dim]

        all_df = []

        for odim in observations_dim:
            self.logger.info(f"Processing observations dimension: {odim}")
            filtered_ds = ds[
                [var for var in ds.data_vars if odim in ds[var].dims]
            ].squeeze(drop=True)
            df = filtered_ds.to_dataframe().reset_index().drop(columns=[odim])

            variables = list(filtered_ds.data_vars)
            time_variables = [var for var in variables if "time" in var]
            if len(time_variables) != 1:
                raise ValueError(
                    f"Expected exactly one time variable, but found {len(time_variables)}: {time_variables}"
                )
            df.rename(columns={time_variables[0]: "time"}, inplace=True)

            if len(filtered_ds.coords) > 1:
                raise ValueError(
                    f"Expected maximum one remaining coordinate dimension, but found {len(filtered_ds.coords)}: {list(filtered_ds.coords)}"
                )
            elif len(filtered_ds.coords) == 1:
                coord_name = list(filtered_ds.coords)[0]
                try:
                    df[coord_name] = df[coord_name].str.decode("utf-8")
                except AttributeError:
                    pass  # The coordinate is not a byte string, so we can skip decoding

                pivoted_df = df.reset_index().pivot_table(
                    index="time",
                    columns=coord_name,
                    values=[
                        var for var in df.columns if var != coord_name and var != "time"
                    ],
                    aggfunc="mean",  # or 'first', 'last', etc.
                )

                new_columns = [f"{col[0]}_{col[1]}" for col in pivoted_df.columns]
                pivoted_df.columns = new_columns
                df = pivoted_df.reset_index()

            df.set_index("time", inplace=True)

            all_df.append(df)

        return pd.concat(all_df, axis=0).sort_index()
