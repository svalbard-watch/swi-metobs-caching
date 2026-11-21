# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from source.cacheHandler.cacheHandler import CacheHandler
from source.configHandler.confighandler import ConfigHandler
from source.datasource.UNISPortalSource import UNISPortalSource

PATHS = {
    "station_status": "status/",
    "realtime_data": "realtime/",
    "historical": "historical/",
    "hourly_data": "hourly/",
    "online": "online/",
    "offline": "offline/",
}


@pytest.fixture
def handler(tmp_path):
    ch = CacheHandler(directory=str(tmp_path), path_config=PATHS, cleaning_list=[])
    ch.config = MagicMock(spec=ConfigHandler)
    return ch


def hourly_index(hours=6):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return pd.DatetimeIndex(
        [now - timedelta(hours=h) for h in range(hours, 0, -1)], tz="UTC"
    )


def good_datasource():
    df = pd.DataFrame({"airTemperature": [-10.0] * 6}, index=hourly_index())
    datasource = MagicMock()
    datasource.fetch_timeseries_data.return_value = df
    datasource.df_to_timeserie.side_effect = UNISPortalSource().df_to_timeserie
    return datasource


def test_one_failing_station_does_not_abort_the_hourly_run(handler, tmp_path):
    failing = MagicMock()
    failing.fetch_timeseries_data.return_value = None  # e.g. portal returned HTTP 500
    datasources = {"broken": failing, "healthy": good_datasource()}
    handler.online_stations = ["broken", "healthy"]

    with patch(
        "source.cacheHandler.cacheHandler.get_datasource",
        side_effect=lambda station, config=None: datasources[station],
    ):
        handler.cache_past_hourly_data(hours_ago=3)

    written = json.loads((tmp_path / "hourly" / "-1.json").read_text(encoding="utf-8"))
    assert "healthy" in written
    assert written["healthy"]["timeseries"][0]["airTemperature"] == -10.0


def test_unis_portal_source_runs_through_the_hourly_cache(handler, tmp_path):
    index = hourly_index()
    payload = {
        "time": [t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S") for t in index],
        "air_temperature_mean": [-12.5] * len(index),
    }
    response = MagicMock()
    response.json.return_value = payload

    source = UNISPortalSource()
    source.config = MagicMock()
    source.config.get_metadata.return_value = {
        "id": "portal_station",
        "url": "https://observations.unis.no/catalog",
    }
    source.config.get_variable.return_value = {"airTemperature": "air_temperature_mean"}
    source.config.get_variable_limits.return_value = {"airTemperature": (-40, 50)}
    handler.online_stations = ["portal_station"]

    with (
        patch("requests.get", return_value=response),
        patch("source.cacheHandler.cacheHandler.get_datasource", return_value=source),
    ):
        handler.cache_past_hourly_data(hours_ago=3)

    written = json.loads((tmp_path / "hourly" / "-1.json").read_text(encoding="utf-8"))
    assert written["portal_station"]["timeseries"][0]["airTemperature"] == -12.5
    assert list((tmp_path / "historical" / "portal_station").glob("*.parquet"))
