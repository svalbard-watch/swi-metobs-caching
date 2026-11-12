# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

import numpy as np
import pandas as pd
import pytest

from source.qc.qc import DEFAULT_SENTINELS, apply_qc


@pytest.fixture
def index():
    return pd.to_datetime(
        ["2024-01-01T00:00:00", "2024-01-01T01:00:00", "2024-01-01T02:00:00"]
    )


def test_sentinel_values_become_nan(index):
    df = pd.DataFrame({"airTemperature": [-100.0, 1.5, -999.0]}, index=index)

    result = apply_qc(df, limits={})

    assert np.isnan(result["airTemperature"].iloc[0])
    assert result["airTemperature"].iloc[1] == 1.5
    assert np.isnan(result["airTemperature"].iloc[2])


def test_default_sentinels_cover_the_values_seen_in_the_field():
    assert -100.0 in DEFAULT_SENTINELS
    assert -999.0 in DEFAULT_SENTINELS


def test_values_outside_limits_become_nan(index):
    df = pd.DataFrame({"relativeHumidity": [-5.0, 50.0, 120.0]}, index=index)

    result = apply_qc(df, limits={"relativeHumidity": (0, 100)})

    assert np.isnan(result["relativeHumidity"].iloc[0])
    assert result["relativeHumidity"].iloc[1] == 50.0
    assert np.isnan(result["relativeHumidity"].iloc[2])


def test_limits_are_inclusive(index):
    df = pd.DataFrame({"windDirection": [0.0, 180.0, 360.0]}, index=index)

    result = apply_qc(df, limits={"windDirection": (0, 360)})

    assert list(result["windDirection"]) == [0.0, 180.0, 360.0]


def test_a_missing_bound_means_unbounded(index):
    df = pd.DataFrame({"windSpeed": [-1.0, 5.0, 500.0]}, index=index)

    result = apply_qc(df, limits={"windSpeed": (0, None)})

    assert np.isnan(result["windSpeed"].iloc[0])
    assert result["windSpeed"].iloc[2] == 500.0


def test_columns_without_limits_are_only_sentinel_filtered(index):
    df = pd.DataFrame({"batteryVoltage": [12.1, 99999.0, -100.0]}, index=index)

    result = apply_qc(df, limits={"airTemperature": (-40, 50)})

    assert result["batteryVoltage"].iloc[1] == 99999.0
    assert np.isnan(result["batteryVoltage"].iloc[2])


def test_depth_suffixed_columns_use_the_base_variable_limits(index):
    df = pd.DataFrame(
        {
            "seaTemperature_0.10": [4.0, 85.0, 110.0],
            "seaTemperature_0.20": [3.0, 4.0, 5.0],
        },
        index=index,
    )

    result = apply_qc(df, limits={"seaTemperature": (-2, 35)})

    assert result["seaTemperature_0.10"].iloc[0] == 4.0
    assert np.isnan(result["seaTemperature_0.10"].iloc[1])
    assert np.isnan(result["seaTemperature_0.10"].iloc[2])
    assert list(result["seaTemperature_0.20"]) == [3.0, 4.0, 5.0]


def test_exact_column_limit_wins_over_base_variable_limit(index):
    df = pd.DataFrame({"seaTemperature_0.10": [40.0, 1.0, 2.0]}, index=index)

    result = apply_qc(
        df,
        limits={"seaTemperature": (-2, 35), "seaTemperature_0.10": (-2, 50)},
    )

    assert result["seaTemperature_0.10"].iloc[0] == 40.0


def test_non_numeric_columns_are_left_alone(index):
    df = pd.DataFrame({"sensorStatus": ["ok", "fault", "ok"]}, index=index)

    result = apply_qc(df, limits={"sensorStatus": (0, 1)})

    assert list(result["sensorStatus"]) == ["ok", "fault", "ok"]


def test_input_dataframe_is_not_modified(index):
    df = pd.DataFrame({"airTemperature": [-100.0, 1.0, 2.0]}, index=index)

    apply_qc(df, limits={"airTemperature": (-40, 50)})

    assert df["airTemperature"].iloc[0] == -100.0


def test_empty_dataframe_is_returned_unchanged():
    df = pd.DataFrame(columns=["airTemperature"])

    result = apply_qc(df, limits={"airTemperature": (-40, 50)})

    assert result.empty
    assert list(result.columns) == ["airTemperature"]
