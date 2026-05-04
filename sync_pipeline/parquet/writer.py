from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd


def _normalize_object_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()
    for column in normalized.columns:
        series = normalized[column]
        if series.dtype != "object":
            continue

        non_null = series.dropna()
        if non_null.empty:
            continue

        if non_null.map(lambda value: isinstance(value, (pd.Timestamp, datetime, date))).any():
            as_datetime = pd.to_datetime(series, errors="coerce")
            if as_datetime.notna().sum() == len(non_null):
                normalized[column] = as_datetime
                continue

        as_numeric = pd.to_numeric(series, errors="coerce")
        if as_numeric.notna().sum() == len(non_null):
            normalized[column] = as_numeric

    return normalized


def write_parquet(dataframe: pd.DataFrame, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_object_columns(dataframe)
    normalized.to_parquet(path, index=False)
    return len(dataframe.index)
