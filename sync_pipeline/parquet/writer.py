from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_parquet(dataframe: pd.DataFrame, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_parquet(path, index=False)
    return len(dataframe.index)
