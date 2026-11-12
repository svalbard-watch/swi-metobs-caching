# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from source.datasource.UNISPortalSource import UNISPortalSource

PORTAL = "https://observations.unis.no/catalog"
STATION_ID = "adventdalen_fivelflyene_10minute"

FIXED_METADATA = {
    "id": STATION_ID,
    "url": PORTAL,
    "variables": {
        "airTemperature": "air_temperature_mean",
        "windSpeed": "wind_speed",
        "relativeHumidity": "relative_humidity",
        "windSpeedGust": None,
    },
}

BOAT_ID = "hanna_resvoll_10min"
BOAT_METADATA = {
    "id": BOAT_ID,
    "url": PORTAL,
    "variables": {
        "airTemperature": "air_temperature",
        "windSpeed": "wind_speed_mean",
    },
}

LIMITS = {"airTemperature": (-40, 50), "relativeHumidity": (0, 100)}


def portal_payload(**columns):
    """A /data JSON body: one array per variable, aligned with `time`."""
    return {
        "time": [
            "2026-11-12T10:00:00",
            "2026-11-12T10:10:00",
            "2026-11-12T10:20:00",
        ],
        **columns,
    }


def response(payload=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return resp


def boat_payload():
    return portal_payload(
        air_temperature=[-13.5, -13.6, -13.7],
        wind_speed_mean=[1.0, 0.7, 0.9],
        latitude=[78.2257, 78.2258, 78.2259],
        longitude=[15.6288, 15.6289, 15.6290],
    )


@pytest.fixture
def source():
    src = UNISPortalSource()
    src.config = MagicMock()
    src.config.get_metadata.return_value = dict(FIXED_METADATA)
    src.config.get_variable.return_value = dict(FIXED_METADATA["variables"])
    src.config.get_variable_limits.return_value = dict(LIMITS)
    return src


@pytest.fixture
def boat_source(source):
    source.config.get_metadata.return_value = dict(BOAT_METADATA)
    source.config.get_variable.return_value = dict(BOAT_METADATA["variables"])
    return source


@pytest.fixture
def fixed_payload():
    return portal_payload(
        air_temperature_mean=[-15.1, -14.7, -100.0],
        wind_speed=[1.4, 1.2, 1.0],
        relative_humidity=[73.6, 79.0, 80.0],
        battery_voltage=[12.1, 12.1, 12.1],
    )


# ---------------------------------------------------------------------------
# fetch_station_data
# ---------------------------------------------------------------------------


def test_fetch_station_data_returns_empty_dict(source):
    assert source.fetch_station_data(STATION_ID) == {}


# ---------------------------------------------------------------------------
# fetch_timeseries_data
# ---------------------------------------------------------------------------


def test_request_targets_the_dataset_data_endpoint(source, fixed_payload):
    with patch("requests.get", return_value=response(fixed_payload)) as get:
        source.fetch_timeseries_data(
            STATION_ID, "2026-11-12T10:00:00", "2026-11-12T11:00:00"
        )

    args, kwargs = get.call_args
    assert args[0] == f"{PORTAL}/datasets/{STATION_ID}/data"
    assert kwargs["params"]["start"] == "2026-11-12T10:00:00"
    assert kwargs["params"]["end"] == "2026-11-12T11:00:00"
    assert kwargs["params"]["format"] == "json"
    assert kwargs["timeout"]


def test_trailing_slash_in_configured_url_is_ignored(source, fixed_payload):
    source.config.get_metadata.return_value = dict(FIXED_METADATA, url=PORTAL + "/")
    with patch("requests.get", return_value=response(fixed_payload)) as get:
        source.fetch_timeseries_data(STATION_ID, "2026-11-12T10:00:00", "x")

    assert get.call_args[0][0] == f"{PORTAL}/datasets/{STATION_ID}/data"


def test_timeseries_df_uses_config_keys_and_naive_utc_index(source, fixed_payload):
    with patch("requests.get", return_value=response(fixed_payload)):
        df = source.fetch_timeseries_data(
            STATION_ID,
            "2026-11-12T10:00:00",
            "2026-11-12T11:00:00",
            return_df=True,
        )

    assert set(df.columns) == {"airTemperature", "windSpeed", "relativeHumidity"}
    assert df.index.tz is None
    assert df.index.min() == pd.Timestamp("2026-11-12T10:00:00")


def test_timeseries_applies_qc_to_sentinels(source, fixed_payload):
    with patch("requests.get", return_value=response(fixed_payload)):
        df = source.fetch_timeseries_data(
            STATION_ID,
            "2026-11-12T10:00:00",
            "2026-11-12T11:00:00",
            return_df=True,
        )

    # -100 (sensor failure) must not reach the cache; the 10:00 hour keeps the
    # mean of the two good readings.
    assert df["airTemperature"].iloc[0] == pytest.approx(-14.9)


def test_timeseries_as_dict_has_id_and_timestamped_observations(source, fixed_payload):
    with patch("requests.get", return_value=response(fixed_payload)):
        result = source.fetch_timeseries_data(
            STATION_ID, "2026-11-12T10:00:00", "2026-11-12T11:00:00"
        )

    assert result["id"] == STATION_ID
    first = result["timeseries"][0]
    assert first["timestamp"] == "2026-11-12T10:00:00.000Z"
    assert first["windSpeed"] == pytest.approx(1.2, abs=0.01)


def test_variables_mapped_to_null_or_missing_in_portal_are_skipped(
    source, fixed_payload
):
    del fixed_payload["relative_humidity"]
    with patch("requests.get", return_value=response(fixed_payload)):
        df = source.fetch_timeseries_data(
            STATION_ID,
            "2026-11-12T10:00:00",
            "2026-11-12T11:00:00",
            return_df=True,
        )

    assert "windSpeedGust" not in df.columns
    assert "relativeHumidity" not in df.columns
    assert "airTemperature" in df.columns


def test_mobile_station_position_comes_from_latitude_longitude_columns(boat_source):
    with patch("requests.get", return_value=response(boat_payload())):
        result = boat_source.fetch_timeseries_data(
            BOAT_ID, "2026-11-12T10:00:00", "2026-11-12T11:00:00"
        )

    first = result["timeseries"][0]
    assert first["location"]["lat"] == pytest.approx(78.2258, abs=1e-3)
    assert first["location"]["lon"] == pytest.approx(15.6289, abs=1e-3)


def test_hourly_stations_are_not_degraded_by_resampling(source):
    payload = {
        "time": ["2026-11-12T09:00:00", "2026-11-12T10:00:00"],
        "wind_speed": [3.5, 3.7],
    }
    variables = {"windSpeed": "wind_speed"}
    source.config.get_variable.return_value = variables
    source.config.get_metadata.return_value = dict(FIXED_METADATA, variables=variables)
    with patch("requests.get", return_value=response(payload)):
        df = source.fetch_timeseries_data(
            STATION_ID, "2026-11-12T09:00:00", "2026-11-12T11:00:00", return_df=True
        )

    assert list(df["windSpeed"]) == [3.5, 3.7]


def test_timeseries_http_error_returns_none(source):
    with patch("requests.get", return_value=response(status=500)):
        result = source.fetch_timeseries_data(
            STATION_ID, "2026-11-12T10:00:00", "2026-11-12T11:00:00"
        )

    assert result is None


def test_timeseries_connection_error_returns_none(source):
    with patch("requests.get", side_effect=requests.ConnectionError("down")):
        result = source.fetch_timeseries_data(
            STATION_ID, "2026-11-12T10:00:00", "2026-11-12T11:00:00"
        )

    assert result is None


def test_timeseries_empty_window_gives_empty_result(source):
    with patch("requests.get", return_value=response({"time": []})):
        result = source.fetch_timeseries_data(
            STATION_ID, "2026-11-12T10:00:00", "2026-11-12T11:00:00"
        )

    assert result == {"id": STATION_ID, "timeseries": []}


# ---------------------------------------------------------------------------
# fetch_realtime_data
# ---------------------------------------------------------------------------


def test_realtime_asks_only_for_a_recent_window(source, fixed_payload):
    with patch("requests.get", return_value=response(fixed_payload)) as get:
        source.fetch_realtime_data(STATION_ID)

    start = datetime.fromisoformat(get.call_args.kwargs["params"]["start"])
    age = datetime.now(timezone.utc).replace(tzinfo=None) - start
    assert timedelta(hours=1) < age < timedelta(hours=12)


def test_realtime_takes_latest_valid_value_per_variable(source):
    payload = portal_payload(
        air_temperature_mean=[-15.1, -14.7, None],
        wind_speed=[1.4, None, 1.0],
        relative_humidity=[None, None, None],
    )
    with patch("requests.get", return_value=response(payload)):
        result = source.fetch_realtime_data(STATION_ID)

    obs = result["timeseries"][0]
    assert result["id"] == STATION_ID
    assert obs["timestamp"] == "2026-11-12T10:20:00.000Z"
    assert obs["airTemperature"] == -14.7
    assert obs["windSpeed"] == 1.0
    assert obs["relativeHumidity"] == "NA"


def test_realtime_ignores_sentinel_values(source, fixed_payload):
    with patch("requests.get", return_value=response(fixed_payload)):
        obs = source.fetch_realtime_data(STATION_ID)["timeseries"][0]

    assert obs["airTemperature"] == -14.7


def test_realtime_includes_location_for_boats(boat_source):
    with patch("requests.get", return_value=response(boat_payload())):
        obs = boat_source.fetch_realtime_data(BOAT_ID)["timeseries"][0]

    assert obs["location"] == {"lat": 78.2259, "lon": 15.629}


def test_realtime_returns_none_on_http_error(source):
    with patch("requests.get", return_value=response(status=500)):
        assert source.fetch_realtime_data(STATION_ID) is None


def test_realtime_returns_none_when_window_is_empty(source):
    with patch("requests.get", return_value=response({"time": []})):
        assert source.fetch_realtime_data(STATION_ID) is None


# ---------------------------------------------------------------------------
# is_station_online
# ---------------------------------------------------------------------------


def _realtime(minutes_old):
    stamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
    return {
        "id": STATION_ID,
        "timeseries": [
            {"timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
        ],
    }


def test_online_when_latest_observation_is_recent(source):
    with patch.object(source, "fetch_realtime_data", return_value=_realtime(15)):
        assert source.is_station_online(STATION_ID) is True


def test_offline_when_latest_observation_is_old(source):
    with patch.object(source, "fetch_realtime_data", return_value=_realtime(600)):
        assert source.is_station_online(STATION_ID) is False


def test_offline_when_portal_fails(source):
    with patch.object(source, "fetch_realtime_data", return_value=None):
        assert source.is_station_online(STATION_ID) is False


def test_max_inactive_minutes_can_be_widened(source):
    with patch.object(source, "fetch_realtime_data", return_value=_realtime(300)):
        assert source.is_station_online(STATION_ID, max_inactive_minutes=360) is True


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


def test_missing_url_falls_back_to_environment_then_default(source, fixed_payload):
    source.config.get_metadata.return_value = {
        "id": STATION_ID,
        "variables": FIXED_METADATA["variables"],
    }
    with patch.dict("os.environ", {"SWI_UNIS_PORTAL_URL": "https://example.test/c"}):
        with patch("requests.get", return_value=response(fixed_payload)) as get:
            source.fetch_timeseries_data(STATION_ID, "2026-11-12T10:00:00", "x")
    assert get.call_args[0][0] == f"https://example.test/c/datasets/{STATION_ID}/data"

    with patch.dict("os.environ", {}, clear=True):
        with patch("requests.get", return_value=response(fixed_payload)) as get:
            source.fetch_timeseries_data(STATION_ID, "2026-11-12T10:00:00", "x")
    assert get.call_args[0][0] == f"{PORTAL}/datasets/{STATION_ID}/data"


def test_source_is_registered_in_the_factory():
    from source.datasource.datasourceFactory import DATASOURCE_MAPPING

    assert DATASOURCE_MAPPING["UNISPortalSource"] is UNISPortalSource
