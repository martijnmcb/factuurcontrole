from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from django.conf import settings

from .writer import write_parquet


def dataset_root(client_slug: str, dataset: str) -> Path:
    return settings.DATA_DIR / f"client={client_slug}" / f"dataset={dataset}"


def current_dataset_dir(client_slug: str, dataset: str) -> Path:
    return dataset_root(client_slug, dataset) / "current"


def history_dataset_dir(client_slug: str, dataset: str) -> Path:
    return dataset_root(client_slug, dataset) / "history"


def _replace_directory_atomic(source_dir: Path, target_dir: Path) -> None:
    backup_dir = target_dir.with_name(f"{target_dir.name}.__bak__")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if target_dir.exists():
        target_dir.replace(backup_dir)
    source_dir.replace(target_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)


def write_current_dataset(dataframe: pd.DataFrame, client_slug: str, dataset: str) -> int:
    target_dir = current_dataset_dir(client_slug, dataset)
    temp_dir = target_dir.with_name(f"{target_dir.name}.__tmp__.{uuid.uuid4().hex}")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    if not dataframe.empty:
        write_parquet(dataframe, temp_dir / "part-0001.parquet")

    _replace_directory_atomic(temp_dir, target_dir)
    return len(dataframe.index)


def append_history_dataset(
    dataframe: pd.DataFrame,
    client_slug: str,
    dataset: str,
    sync_timestamp: datetime,
) -> int:
    if dataframe.empty:
        return 0

    total_rows = 0
    year = sync_timestamp.strftime("%Y")
    month = sync_timestamp.strftime("%m")
    stamp = sync_timestamp.strftime("%Y%m%d%H%M%S")
    base_dir = history_dataset_dir(client_slug, dataset)

    if "stuurtabel_id" not in dataframe.columns:
        return 0

    for stuurtabel_id, partition in dataframe.groupby("stuurtabel_id", dropna=False):
        partition_value = "unknown" if pd.isna(stuurtabel_id) else str(int(stuurtabel_id))
        destination = base_dir / f"year={year}" / f"month={month}" / f"stuurtabel_id={partition_value}" / f"{stamp}.parquet"
        total_rows += write_parquet(partition, destination)

    return total_rows
