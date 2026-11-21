# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import json

import pytest

from source.configHandler.confighandler import ConfigHandler

CATALOGUE = {
    "airTemperature": {"unit": "°C", "minValue": -40, "maxValue": 50},
    "windSpeed": {"unit": "m/s", "minValue": 0},
    "seaTemperature": {"unit": "°C", "minValue": -2, "maxValue": 35},
    "batteryVoltage": {"unit": "V"},
}


@pytest.fixture
def handler(tmp_path):
    path = tmp_path / "station_variables.json"
    path.write_text(json.dumps(CATALOGUE), encoding="utf-8")
    handler = ConfigHandler()
    handler.variables_file = str(path)
    return handler


def test_default_catalogue_lives_next_to_the_station_files():
    assert ConfigHandler().variables_file == "config/variables/station_variables.json"


def test_limits_are_read_as_min_max_pairs(handler):
    limits = handler.get_variable_limits()

    assert limits["airTemperature"] == (-40, 50)
    assert limits["seaTemperature"] == (-2, 35)


def test_a_missing_bound_is_none(handler):
    limits = handler.get_variable_limits()

    assert limits["windSpeed"] == (0, None)
    assert limits["batteryVoltage"] == (None, None)


def test_missing_catalogue_gives_no_limits_instead_of_failing(tmp_path):
    handler = ConfigHandler()
    handler.variables_file = str(tmp_path / "absent.json")

    assert handler.get_variable_limits() == {}


def test_invalid_catalogue_gives_no_limits_instead_of_failing(tmp_path):
    path = tmp_path / "station_variables.json"
    path.write_text("{not json", encoding="utf-8")
    handler = ConfigHandler()
    handler.variables_file = str(path)

    assert handler.get_variable_limits() == {}


def test_catalogue_is_read_once(handler):
    first = handler.get_variable_limits()
    open(handler.variables_file, "w", encoding="utf-8").write("{}")

    assert handler.get_variable_limits() is first
