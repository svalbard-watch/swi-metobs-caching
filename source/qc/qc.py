# SPDX-FileCopyrightText: 2025 Louis Pauchet <louis.pauchet@insa-rouen.fr>
# SPDX-License-Identifier:  EUPL-1.2

"""Minimal quality control for observation DataFrames.

Turns sentinel values and out-of-range values into NaN. There is no flagging
and no unit conversion: a value is either kept or dropped.
"""

import pandas as pd

# Values some loggers write instead of a real reading when a sensor fails.
DEFAULT_SENTINELS = (-100.0, -999.0, -9999.0)


def _limit_for(column, limits):
    """Return the (min, max) limit for a column, or None.

    An exact match wins. Otherwise a depth/height suffix is ignored, so
    ``seaTemperature_0.10`` uses the limits of ``seaTemperature``.
    """
    if column in limits:
        return limits[column]
    base = str(column).rsplit("_", 1)[0]
    return limits.get(base)


def apply_qc(df, limits=None, sentinels=DEFAULT_SENTINELS):
    """Return a copy of ``df`` with sentinel and out-of-range values set to NaN.

    Args:
        df (pd.DataFrame): Observations, one column per variable.
        limits (dict): ``{variable: (min, max)}``, both inclusive. Either bound
            may be None for "unbounded".
        sentinels (iterable): Exact values treated as "no reading".

    Returns:
        pd.DataFrame: A new DataFrame; ``df`` is not modified.
    """
    limits = limits or {}
    result = df.copy()

    for column in result.columns:
        if not pd.api.types.is_numeric_dtype(result[column]):
            continue

        series = result[column].mask(result[column].isin(list(sentinels)))

        limit = _limit_for(column, limits)
        if limit is not None:
            low, high = limit
            if low is not None:
                series = series.mask(series < low)
            if high is not None:
                series = series.mask(series > high)

        result[column] = series

    return result
