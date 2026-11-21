# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from source.qc.qc import apply_qc

from .datasource import DataSource

DEFAULT_PORTAL_URL = "https://observations.unis.no/catalog"
REQUEST_TIMEOUT_SECONDS = 60
REALTIME_WINDOW_HOURS = 6


class UNISPortalSource(DataSource):
    """
    Data source for the UNIS observations portal (open-csi-publisher).

    The portal serves each dataset as JSON at ``{base}/datasets/{id}/data``:
    one array per variable, aligned with ``time`` (UTC), ``null`` for gaps.
    The DataFrames returned keep a UTC-aware index, as the cache handler expects.
    The station id is the portal dataset id. The station ``url`` is the portal
    base URL; it falls back to ``SWI_UNIS_PORTAL_URL`` and then to the public
    UNIS portal. The values of the station ``variables`` mapping are portal
    column names (e.g. ``wind_speed_mean``).

    Mobile platforms publish their position as ``latitude`` and ``longitude``
    columns, which are passed through when present.
    """

    def __init__(self, api_key=None):
        super().__init__(api_key=api_key)

    def fetch_station_data(self, station_id):
        """The portal metadata is not used by SWI; returns an empty dict."""
        return {}

    def _base_url(self, station_id):
        metadata = self.config.get_metadata(station_id) or {}
        url = (
            metadata.get("url")
            or os.getenv("SWI_UNIS_PORTAL_URL")
            or DEFAULT_PORTAL_URL
        )
        return url.rstrip("/")

    def _fetch_raw(self, station_id, start_time, end_time):
        """Fetch a window of raw portal data as a DataFrame indexed by UTC time."""
        response = requests.get(
            f"{self._base_url(station_id)}/datasets/{station_id}/data",
            params={"start": start_time, "end": end_time, "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()

        df = pd.DataFrame(payload)
        if df.empty or "time" not in df.columns:
            return pd.DataFrame(index=pd.DatetimeIndex([], name="time"))
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df.set_index("time").sort_index()

    def fetch_realtime_data(self, station_id):
        """Latest observation per variable within the last few hours, or None."""
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start = (now - timedelta(hours=REALTIME_WINDOW_HOURS)).isoformat(
                timespec="seconds"
            )
            raw_data = self._fetch_raw(
                station_id, start, now.isoformat(timespec="seconds")
            )
            self.logger.info(f"Fetched real-time data for {station_id}")
            return self.transform_realtime_data(raw_data, station_id)
        except Exception as e:
            self._handle_error(e)
            return None

    def fetch_timeseries_data(self, station_id, start_time, end_time, return_df=False):
        """Historical data for a time range, as a dict or (return_df) a DataFrame."""
        try:
            raw_data = self._fetch_raw(station_id, start_time, end_time)
            self.logger.info(
                f"Fetched timeseries data for {station_id} from {start_time} to {end_time}"
            )
            return self.transform_timeseries_data(
                raw_data, station_id, return_df=return_df
            )
        except Exception as e:
            self._handle_error(e)
            return None

    def _select_and_clean(self, raw_data, station_id):
        """Keep the mapped columns under their SWI names, then apply QC."""
        mapping = self.config.get_variable(station_id) or {}
        columns = {}
        for key, portal_name in mapping.items():
            if portal_name is None:
                continue
            if portal_name not in raw_data.columns:
                self.logger.warning(
                    f"{station_id}: portal column '{portal_name}' not available"
                )
                continue
            columns[portal_name] = key
        # Position of mobile platforms.
        for position in ("latitude", "longitude"):
            if position in raw_data.columns:
                columns[position] = position

        df = raw_data[list(columns)].rename(columns=columns)
        return apply_qc(df, self.config.get_variable_limits())

    def transform_timeseries_data(
        self, raw_data, station_id, return_df=False, resample="60min"
    ):
        """Map to SWI variables, apply QC and resample (default: hourly mean)."""
        try:
            df = self._select_and_clean(raw_data, station_id)
            if resample != "AUTO" and not df.empty:
                df = df.resample(resample).mean()
            df = df.dropna(how="all")

            if return_df:
                return df
            return {"id": station_id, "timeseries": self.df_to_timeserie(df)}
        except Exception as e:
            self._handle_error(e)
            return None

    def transform_realtime_data(self, raw_data, station_id):
        """Latest valid value of each variable; None when there is no data."""
        try:
            df = self._select_and_clean(raw_data, station_id).dropna(how="all")
            if df.empty:
                return None

            observation = {
                "timestamp": df.index.max().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            }
            latest = {}
            for column in df.columns:
                values = df[column].dropna()
                latest[column] = values.iloc[-1] if not values.empty else None

            if (
                latest.get("latitude") is not None
                and latest.get("longitude") is not None
            ):
                observation["location"] = {
                    "lat": round(float(latest["latitude"]), 6),
                    "lon": round(float(latest["longitude"]), 6),
                }
            for column, value in latest.items():
                if column in ("latitude", "longitude"):
                    continue
                observation[column] = "NA" if value is None else round(float(value), 2)

            return {"id": station_id, "timeseries": [observation]}
        except Exception as e:
            self._handle_error(e)
            return None

    def is_station_online(self, station_id, max_inactive_minutes=120):
        """True when the latest observation is newer than ``max_inactive_minutes``."""
        data = self.fetch_realtime_data(station_id)
        try:
            stamp = data["timeseries"][0]["timestamp"]
            latest = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except TypeError, KeyError, IndexError, ValueError:
            self.logger.info(f"Station {station_id} is considered OFFLINE (no data).")
            return False

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_inactive_minutes)
        online = latest >= cutoff
        self.logger.info(
            f"Station {station_id} last timestamp = {latest}; "
            f"{'ONLINE' if online else 'OFFLINE'}."
        )
        return online
