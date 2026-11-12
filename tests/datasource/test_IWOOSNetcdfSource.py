# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest
import xarray as xr

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from source.datasource.IWOOSNetcdfSource import IWOOSNetcdfSource


STATION_ID = "IWOOS_id5"

STATION_METADATA = {
    "id": STATION_ID,
    "url": "https://thredds.met.no/thredds/dodsC/misc/IWOOS/%Y_IWOOS_id5.nc",
    "variables": {
        "waveHeight": "pHs0",
        "wavePeriodLow": "pT02",
        "wavePeriodHigh": "pT24",
        "seaTemperature": "temperature_calibrated_at_positions",
    },
}


@pytest.fixture
def iwoos_source():
    """
    An IWOOSNetcdfSource instance with a mocked ConfigHandler so no real
    config/stations files or network calls are involved.
    """
    source = IWOOSNetcdfSource()
    source.config = MagicMock()
    source.config.get_metadata.return_value = dict(STATION_METADATA)
    source.config.get_variable.return_value = dict(STATION_METADATA["variables"])
    return source


@pytest.fixture
def sample_dataset():
    """
    A synthetic NetCDF dataset shaped like a real IWOOS file: wave stats and
    GPS reported together on an "obs_waves_imu" dimension without an explicit
    coordinate, and a temperature profile reported on an "obs_temp" dimension
    with a separate "positions" (depth) coordinate stored as byte strings,
    the way THREDDS/OPeNDAP serves them.
    """
    return xr.Dataset(
        data_vars={
            "pHs0": ("obs_waves_imu", [0.1, 0.2, 0.3]),
            "pT02": ("obs_waves_imu", [10.0, 11.0, 12.0]),
            "pT24": ("obs_waves_imu", [5.0, 6.0, 7.0]),
            "lat": ("obs_waves_imu", [78.1, 78.2, 78.3]),
            "lon": ("obs_waves_imu", [16.1, 16.2, 16.3]),
            "time_waves_imu": (
                "obs_waves_imu",
                pd.to_datetime(
                    [
                        "2024-01-01T00:00:00",
                        "2024-01-01T01:00:00",
                        "2024-01-01T02:00:00",
                    ]
                ),
            ),
            "temperature_calibrated_at_positions": (
                ("obs_temp", "positions"),
                [[5.0, 5.5], [6.0, 6.5]],
            ),
            "time_temp": (
                "obs_temp",
                pd.to_datetime(["2024-01-01T00:30:00", "2024-01-01T01:30:00"]),
            ),
            "time": 0.0,
        },
        coords={
            "positions": ("positions", np.array([b"0.00", b"0.10"])),
        },
    )


# ---------------------------------------------------------------------------
# fetch_station_data
# ---------------------------------------------------------------------------


def test_fetch_station_data_returns_empty_dict(iwoos_source):
    assert iwoos_source.fetch_station_data(STATION_ID) == {}


# ---------------------------------------------------------------------------
# open_data
# ---------------------------------------------------------------------------


def test_open_data_pivots_and_renames(iwoos_source, sample_dataset):
    with patch("xarray.open_dataset", return_value=sample_dataset):
        df = iwoos_source.open_data(STATION_ID)

    assert sorted(df.columns) == sorted(
        [
            "waveHeight",
            "wavePeriodLow",
            "wavePeriodHigh",
            "lat",
            "lon",
            "seaTemperature_0.00",
            "seaTemperature_0.10",
        ]
    )
    assert df.index.name == "time"
    assert list(df.index) == sorted(df.index)

    wave_row = df.loc["2024-01-01 01:00:00"]
    assert wave_row["waveHeight"] == pytest.approx(0.2)
    assert wave_row["lat"] == pytest.approx(78.2)

    temp_row = df.loc["2024-01-01 00:30:00"]
    assert temp_row["seaTemperature_0.00"] == pytest.approx(5.0)
    assert temp_row["seaTemperature_0.10"] == pytest.approx(5.5)


def test_open_data_missing_url_raises(iwoos_source):
    iwoos_source.config.get_metadata.return_value = {"variables": {}}
    with pytest.raises(ValueError, match="url"):
        iwoos_source.open_data(STATION_ID)


def test_open_data_missing_variables_raises(iwoos_source):
    iwoos_source.config.get_metadata.return_value = {"url": "https://example.com/%Y.nc"}
    with pytest.raises(ValueError, match="variables"):
        iwoos_source.open_data(STATION_ID)


# ---------------------------------------------------------------------------
# transform_realtime_data
# ---------------------------------------------------------------------------


@pytest.fixture
def async_realtime_df():
    """
    Mirrors the real data: waves, temperature and GPS are reported at
    different, non-overlapping timestamps, so no single row is complete.
    """
    index = pd.to_datetime(
        [
            "2024-01-01T09:00:00",
            "2024-01-01T10:00:00",
            "2024-01-01T10:30:00",
        ]
    )
    return pd.DataFrame(
        {
            "seaTemperature_0.00": [8.5793, np.nan, np.nan],
            "waveHeight": [np.nan, np.nan, 0.0407],
            "wavePeriodLow": [np.nan, np.nan, 11.3086],
            "wavePeriodHigh": [np.nan, np.nan, np.nan],
            "lat": [np.nan, 78.3837, np.nan],
            "lon": [np.nan, 16.3614, np.nan],
        },
        index=index,
    )


def test_transform_realtime_data_takes_latest_value_per_column(
    iwoos_source, async_realtime_df
):
    result = iwoos_source.transform_realtime_data(async_realtime_df, STATION_ID)

    assert result["id"] == STATION_ID
    observation = result["timeseries"][0]

    # Overall timestamp is the most recent index entry across all sensors.
    assert observation["timestamp"] == "2024-01-01T10:30:00.000Z"

    # Location uses the latest known fix, even though it isn't in the last row.
    assert observation["location"] == {"lat": 78.3837, "lon": 16.3614}

    # Each variable reports its own latest known reading.
    assert observation["seaTemperature_0.00"] == 8.58
    assert observation["waveHeight"] == 0.04
    assert observation["wavePeriodLow"] == 11.31

    # A column with no valid data at all is reported as "NA".
    assert observation["wavePeriodHigh"] == "NA"


def test_transform_realtime_data_missing_location(iwoos_source):
    index = pd.to_datetime(["2024-01-01T09:00:00"])
    df = pd.DataFrame(
        {
            "waveHeight": [0.1],
            "lat": [np.nan],
            "lon": [np.nan],
        },
        index=index,
    )

    result = iwoos_source.transform_realtime_data(df, STATION_ID)
    observation = result["timeseries"][0]

    assert "location" not in observation
    assert observation["waveHeight"] == 0.1


def test_transform_realtime_data_empty_dataframe_returns_none(iwoos_source):
    df = pd.DataFrame(columns=["waveHeight", "lat", "lon"])
    assert iwoos_source.transform_realtime_data(df, STATION_ID) is None


def test_transform_realtime_data_invalid_input_returns_none(iwoos_source):
    # A plain dict has no `.empty`/`.index`, so this exercises the error path.
    assert iwoos_source.transform_realtime_data({}, STATION_ID) is None


# ---------------------------------------------------------------------------
# transform_timeseries_data
# ---------------------------------------------------------------------------


@pytest.fixture
def hourly_timeseries_df():
    index = pd.to_datetime(
        ["2024-01-01T00:00:00", "2024-01-01T01:00:00", "2024-01-01T02:00:00"]
    )
    return pd.DataFrame(
        {
            "waveHeight": [0.1, 0.2, 0.3],
            "wavePeriodLow": [10.0, 11.0, 12.0],
            "wavePeriodHigh": [5.0, 6.0, 7.0],
            "seaTemperature_0.00": [4.0, 4.5, 5.0],
            "lat": [78.1, 78.2, 78.3],
            "lon": [16.1, 16.2, 16.3],
        },
        index=index,
    )


def test_transform_timeseries_data_renames_lat_lon_to_location(
    iwoos_source, hourly_timeseries_df
):
    result = iwoos_source.transform_timeseries_data(
        hourly_timeseries_df, STATION_ID, return_df=False
    )

    assert result["id"] == STATION_ID
    assert len(result["timeseries"]) == 3

    first = result["timeseries"][0]
    assert first["location"] == {"lat": 78.1, "lon": 16.1}
    assert first["waveHeight"] == pytest.approx(0.1)
    assert first["seaTemperature_0.00"] == pytest.approx(4.0)


def test_transform_timeseries_data_return_df(iwoos_source, hourly_timeseries_df):
    df = iwoos_source.transform_timeseries_data(
        hourly_timeseries_df, STATION_ID, return_df=True
    )

    assert "latitude" in df.columns
    assert "longitude" in df.columns
    assert "lat" not in df.columns
    assert list(df["waveHeight"]) == pytest.approx([0.1, 0.2, 0.3])


def test_transform_timeseries_data_empty_dataframe(iwoos_source):
    empty_df = pd.DataFrame(
        columns=[
            "waveHeight",
            "wavePeriodLow",
            "wavePeriodHigh",
            "seaTemperature_0.00",
            "lat",
            "lon",
        ]
    )

    result = iwoos_source.transform_timeseries_data(empty_df, STATION_ID)

    assert result == {"id": STATION_ID, "timeseries": []}


# ---------------------------------------------------------------------------
# fetch_realtime_data / fetch_timeseries_data (integration with open_data)
# ---------------------------------------------------------------------------


def test_fetch_realtime_data_end_to_end(iwoos_source, async_realtime_df):
    with patch.object(iwoos_source, "open_data", return_value=async_realtime_df):
        result = iwoos_source.fetch_realtime_data(STATION_ID)

    assert result["id"] == STATION_ID
    assert result["timeseries"][0]["waveHeight"] == 0.04


def test_fetch_realtime_data_returns_none_on_error(iwoos_source):
    with patch.object(iwoos_source, "open_data", side_effect=RuntimeError("boom")):
        assert iwoos_source.fetch_realtime_data(STATION_ID) is None


def test_fetch_timeseries_data_end_to_end(iwoos_source, hourly_timeseries_df):
    with patch.object(iwoos_source, "open_data", return_value=hourly_timeseries_df):
        result = iwoos_source.fetch_timeseries_data(
            STATION_ID, "2024-01-01T00:00:00", "2024-01-01T02:00:00"
        )

    assert result["id"] == STATION_ID
    assert len(result["timeseries"]) == 3


def test_fetch_timeseries_data_returns_none_on_error(iwoos_source):
    with patch.object(iwoos_source, "open_data", side_effect=RuntimeError("boom")):
        result = iwoos_source.fetch_timeseries_data(
            STATION_ID, "2024-01-01T00:00:00", "2024-01-01T02:00:00"
        )

    assert result is None


# ---------------------------------------------------------------------------
# is_station_online
# ---------------------------------------------------------------------------


def test_is_station_online_true_for_recent_timestamp(iwoos_source):
    recent = datetime.now(timezone.utc) - timedelta(minutes=10)
    mock_data = {
        "timeseries": [
            {"timestamp": recent.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
        ]
    }
    with patch.object(iwoos_source, "fetch_realtime_data", return_value=mock_data):
        assert iwoos_source.is_station_online(STATION_ID) is True


def test_is_station_online_false_for_old_timestamp(iwoos_source):
    old = datetime.now(timezone.utc) - timedelta(hours=6)
    mock_data = {
        "timeseries": [{"timestamp": old.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}]
    }
    with patch.object(iwoos_source, "fetch_realtime_data", return_value=mock_data):
        assert iwoos_source.is_station_online(STATION_ID) is False


def test_is_station_online_false_when_no_data(iwoos_source):
    with patch.object(iwoos_source, "fetch_realtime_data", return_value=None):
        assert iwoos_source.is_station_online(STATION_ID) is False
