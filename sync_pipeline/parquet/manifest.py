from __future__ import annotations

from datetime import datetime

import pandas as pd

from .datasets import write_current_dataset


def build_manifest(
    client_slug: str,
    stuurtabel_ids: list[int],
    sync_timestamp: datetime,
    descriptions: dict[int, str | None] | None = None,
    transport_types: dict[int, str | None] | None = None,
) -> pd.DataFrame:
    descriptions = descriptions or {}
    transport_types = transport_types or {}
    return pd.DataFrame(
        {
            "client_slug": [client_slug for _ in stuurtabel_ids],
            "stuurtabel_id": stuurtabel_ids,
            "omschrijving": [descriptions.get(stuurtabel_id) for stuurtabel_id in stuurtabel_ids],
            "soortvervoer": [transport_types.get(stuurtabel_id) for stuurtabel_id in stuurtabel_ids],
            "is_current": [True for _ in stuurtabel_ids],
            "sync_timestamp": [sync_timestamp for _ in stuurtabel_ids],
        }
    )


def update_manifest(
    client_slug: str,
    stuurtabel_ids: list[int],
    sync_timestamp: datetime,
    descriptions: dict[int, str | None] | None = None,
    transport_types: dict[int, str | None] | None = None,
) -> int:
    manifest_df = build_manifest(client_slug, stuurtabel_ids, sync_timestamp, descriptions, transport_types)
    return write_current_dataset(manifest_df, client_slug, "manifest")
