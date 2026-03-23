from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from apps.clients.models import Client
from sync_pipeline.parquet.datasets import append_history_dataset, write_current_dataset
from sync_pipeline.parquet.manifest import update_manifest
from sync_pipeline.sqlserver.connection import create_connection
from sync_pipeline.sqlserver.extractor import (
    _discover_table_mapping,
    extract_controls,
    extract_current_runs,
    extract_current_runs_frame,
    extract_ritten_detail,
    extract_routes_detail,
    extract_va_ritten_detail,
)

logger = logging.getLogger(__name__)

FIELD_ALIASES = {
    "stuurtabel_id": ["stuurtabelid"],
    "rit_id": ["ritid", "ritten_id", "rit_nr", "ritnummer"],
    "route_id": ["routeid", "route_nr", "routenummer"],
    "vervoerder": ["vervoerder_naam"],
    "perceel": ["perceelnummer"],
    "ritdatum": ["rit_datum", "datum"],
    "controlecode": ["controle_code", "controlecode_done", "controlecode_controle", "control_code"],
    "controle_uitkomst": ["uitkomst", "controle_resultaat", "controle_uitkomst_code", "resultaat"],
    "afwijkingsbedrag": ["afwijkings_bedrag", "bedrag", "deviation_amount"],
    "uitgevoerd": ["done", "is_done", "uitgevoerd_done", "executed", "completed"],
    "timestamp": ["timestamp_done", "executed_at", "done_at", "created_at", "updated_at"],
}

CONTROL_RESULT_PATTERN = re.compile(r"^resultaat_(\d+)$")


@dataclass
class SyncJobResult:
    records_synced: int
    message: str
    metadata: dict = field(default_factory=dict)


def _snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower()


def _normalize_source_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()
    normalized.columns = [_snake_case(column) for column in normalized.columns]
    return normalized


def _resolve_aliases(dataframe: pd.DataFrame, canonical_columns: list[str]) -> pd.DataFrame:
    resolved = dataframe.copy()
    for canonical in canonical_columns:
        if canonical in resolved.columns:
            continue
        for alias in FIELD_ALIASES.get(canonical, []):
            if alias in resolved.columns:
                resolved[canonical] = resolved[alias]
                break
    return resolved


def _coerce_types(dataframe: pd.DataFrame, datetime_columns: list[str], numeric_columns: list[str]) -> pd.DataFrame:
    normalized = dataframe.copy()
    for column in datetime_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_datetime(normalized[column], errors="coerce")
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "uitgevoerd" in normalized.columns:
        truthy_values = {"1", "true", "yes", "ja", "y"}
        normalized["uitgevoerd"] = (
            normalized["uitgevoerd"]
            .map(lambda value: str(value).strip().lower() in truthy_values if pd.notna(value) else False)
            .astype(bool)
        )
    return normalized


def _add_metadata_columns(dataframe: pd.DataFrame, client_slug: str, sync_timestamp: datetime) -> pd.DataFrame:
    normalized = _normalize_source_frame(dataframe)
    normalized["client_slug"] = client_slug
    normalized["synced_at"] = sync_timestamp
    if "stuurtabel_id" in normalized.columns:
        normalized["stuurtabel_id"] = pd.to_numeric(normalized["stuurtabel_id"], errors="coerce")
    return normalized


def _prepare_ritten_detail(
    dataframe: pd.DataFrame,
    client_slug: str,
    current_ids: list[int],
    sync_timestamp: datetime,
) -> pd.DataFrame:
    normalized = _add_metadata_columns(dataframe, client_slug, sync_timestamp)
    if "stuurtabel_id" in normalized.columns and current_ids:
        normalized = normalized[normalized["stuurtabel_id"].isin(current_ids)]
    return _coerce_types(normalized, datetime_columns=["datum", "ritdatum", "synced_at"], numeric_columns=["stuurtabel_id", "id", "route_id", "bedrag_ex_btw", "perceel"])


def _prepare_routes_detail(
    dataframe: pd.DataFrame,
    client_slug: str,
    current_ids: list[int],
    sync_timestamp: datetime,
) -> pd.DataFrame:
    normalized = _add_metadata_columns(dataframe, client_slug, sync_timestamp)
    if "stuurtabel_id" in normalized.columns and current_ids:
        normalized = normalized[normalized["stuurtabel_id"].isin(current_ids)]
    return _coerce_types(normalized, datetime_columns=["datum", "synced_at"], numeric_columns=["stuurtabel_id", "id", "bedrag_ex_btw"])


def _prepare_va_ritten_detail(
    dataframe: pd.DataFrame,
    client_slug: str,
    current_ids: list[int],
    sync_timestamp: datetime,
) -> pd.DataFrame:
    normalized = _add_metadata_columns(dataframe, client_slug, sync_timestamp)
    if "stuurtabel_id" in normalized.columns and current_ids:
        normalized = normalized[normalized["stuurtabel_id"].isin(current_ids)]
    return _coerce_types(
        normalized,
        datetime_columns=["datum", "ritdatum", "synced_at"],
        numeric_columns=["stuurtabel_id", "id", "route_id", "bedrag_ex_btw", "perceel"],
    )


def _prepare_executed_controls(
    dataframe: pd.DataFrame,
    client_slug: str,
    current_ids: list[int],
    sync_timestamp: datetime,
) -> pd.DataFrame:
    normalized = _add_metadata_columns(dataframe, client_slug, sync_timestamp)
    normalized = _resolve_aliases(normalized, ["stuurtabel_id", "controlecode", "uitgevoerd", "timestamp", "omschrijving"])
    if "controlecode" not in normalized.columns and "controle_id" in normalized.columns:
        normalized["controlecode"] = normalized["controle_id"]
    if "uitgevoerd" not in normalized.columns:
        normalized["uitgevoerd"] = True
    if "timestamp" not in normalized.columns:
        normalized["timestamp"] = pd.NaT
    if "omschrijving" not in normalized.columns:
        normalized["omschrijving"] = pd.NA
    if "stuurtabel_id" in normalized.columns and current_ids:
        normalized = normalized[normalized["stuurtabel_id"].isin(current_ids)]
    source_columns = set(_normalize_source_frame(dataframe).columns)
    if "uitgevoerd" not in source_columns and "uitgevoerd" in normalized.columns:
        normalized["uitgevoerd"] = normalized["uitgevoerd"].fillna(True)
    return _coerce_types(
        normalized,
        datetime_columns=["timestamp", "synced_at"],
        numeric_columns=["stuurtabel_id", "controle_id", "controlecode"],
    )


def _coerce_deviation_flag(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    as_text = series.astype("string").str.strip().str.lower()
    deviation_text = as_text.str.contains(r"afwijk|deviat|niet|fout|overschrij", na=False)
    ok_text = as_text.str.fullmatch(r"(ok|true|ja|yes|goed|voldoet|0)", na=False)
    return deviation_text | ((numeric.notna()) & (numeric != 0) & ~ok_text)


def _stringify_mixed_value(series: pd.Series) -> pd.Series:
    return series.map(lambda value: pd.NA if pd.isna(value) else str(value)).astype("string")


def _expand_control_results(
    dataframe: pd.DataFrame,
    entity_type: str,
    entity_id_column: str,
    date_column: str,
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(
            columns=[
                "client_slug",
                "stuurtabel_id",
                "entity_type",
                "entity_id",
                "datum",
                "vervoerder",
                "perceel",
                "controle_id",
                "resultaat",
                "tekst",
                "controlewaarde",
                "dempelwaarde",
                "is_deviation",
                "synced_at",
            ]
        )

    selected_date_column = date_column if date_column in dataframe.columns else "rit_datum" if "rit_datum" in dataframe.columns else "datum" if "datum" in dataframe.columns else None
    perceel_column = "perceel" if "perceel" in dataframe.columns else "perceel_id" if "perceel_id" in dataframe.columns else None

    result_columns = []
    for column in dataframe.columns:
        match = CONTROL_RESULT_PATTERN.match(column)
        if match:
            result_columns.append((int(match.group(1)), column))

    long_rows: list[pd.DataFrame] = []
    for control_id, result_column in sorted(result_columns):
        frame = pd.DataFrame(
            {
                "client_slug": dataframe["client_slug"],
                "stuurtabel_id": dataframe["stuurtabel_id"],
                "entity_type": entity_type,
                "entity_id": dataframe[entity_id_column] if entity_id_column in dataframe.columns else pd.NA,
                "datum": dataframe[selected_date_column] if selected_date_column else pd.NaT,
                "vervoerder": dataframe["vervoerder"] if "vervoerder" in dataframe.columns else pd.NA,
                "perceel": dataframe[perceel_column] if perceel_column else pd.NA,
                "controle_id": control_id,
                "resultaat": dataframe[result_column],
                "tekst": dataframe.get(f"tekst_{control_id}", pd.Series(pd.NA, index=dataframe.index)),
                "controlewaarde": dataframe.get(f"controlewaarde_{control_id}", pd.Series(pd.NA, index=dataframe.index)),
                "dempelwaarde": dataframe.get(f"dempelwaarde_{control_id}", pd.Series(pd.NA, index=dataframe.index)),
                "synced_at": dataframe["synced_at"],
            }
        )
        frame["resultaat"] = _stringify_mixed_value(frame["resultaat"])
        frame["tekst"] = _stringify_mixed_value(frame["tekst"])
        frame["controlewaarde"] = _stringify_mixed_value(frame["controlewaarde"])
        frame["dempelwaarde"] = _stringify_mixed_value(frame["dempelwaarde"])
        frame["is_deviation"] = _coerce_deviation_flag(frame["resultaat"])
        long_rows.append(frame)

    if not long_rows:
        return pd.DataFrame()

    combined = pd.concat(long_rows, ignore_index=True)
    return combined[combined["resultaat"].notna() | combined["tekst"].notna()].reset_index(drop=True)


def _raw_frame_columns(dataframe: pd.DataFrame) -> list[str]:
    return [str(column) for column in dataframe.columns]


def sync_client(client_slug: str) -> SyncJobResult:
    client = Client.objects.select_related("data_source_config").get(slug=client_slug, is_active=True)
    return run_client_sync(client)


def run_client_sync(client: Client) -> SyncJobResult:
    if not hasattr(client, "data_source_config"):
        return SyncJobResult(records_synced=0, message="Client has no datasource config", metadata={})

    sync_timestamp = datetime.now(UTC)
    with create_connection(client.data_source_config) as connection:
        discovered_tables = _discover_table_mapping(connection)
        current_runs_frame = extract_current_runs_frame(connection, client.data_source_config, discovered_tables)
        current_ids = extract_current_runs(connection, client.data_source_config, discovered_tables)
        rg_ids: list[int] = []
        va_ids: list[int] = []
        if not current_runs_frame.empty and "soortvervoer" in current_runs_frame.columns:
            for row in current_runs_frame.itertuples(index=False):
                if pd.isna(row.stuurtabel_id):
                    continue
                soortvervoer = "" if pd.isna(row.soortvervoer) else str(row.soortvervoer).strip().upper()
                if soortvervoer == "VA":
                    va_ids.append(int(row.stuurtabel_id))
                else:
                    rg_ids.append(int(row.stuurtabel_id))
        else:
            rg_ids = current_ids

        ritten_raw = extract_ritten_detail(connection, rg_ids, client.data_source_config, discovered_tables)
        routes_raw = extract_routes_detail(connection, rg_ids, client.data_source_config, discovered_tables)
        va_ritten_raw = extract_va_ritten_detail(connection, va_ids, client.data_source_config, discovered_tables)
        controls_raw = extract_controls(connection, current_ids, client.data_source_config, discovered_tables)

    ritten_detail = _prepare_ritten_detail(ritten_raw, client.slug, current_ids, sync_timestamp)
    routes_detail = _prepare_routes_detail(routes_raw, client.slug, current_ids, sync_timestamp)
    va_ritten_detail = _prepare_va_ritten_detail(va_ritten_raw, client.slug, current_ids, sync_timestamp)
    executed_controls = _prepare_executed_controls(controls_raw, client.slug, current_ids, sync_timestamp)
    ritten_controls_long = _expand_control_results(ritten_detail, "rit", "id", "datum")
    routes_controls_long = _expand_control_results(routes_detail, "route", "id", "datum")
    va_ritten_controls_long = _expand_control_results(va_ritten_detail, "va_rit", "id", "datum")

    history_counts = {
        "ritten_detail": append_history_dataset(ritten_detail, client.slug, "ritten_detail", sync_timestamp),
        "routes_detail": append_history_dataset(routes_detail, client.slug, "routes_detail", sync_timestamp),
        "va_ritten_detail": append_history_dataset(va_ritten_detail, client.slug, "va_ritten_detail", sync_timestamp),
        "executed_controls": append_history_dataset(executed_controls, client.slug, "executed_controls", sync_timestamp),
        "ritten_controls_long": append_history_dataset(ritten_controls_long, client.slug, "ritten_controls_long", sync_timestamp),
        "routes_controls_long": append_history_dataset(routes_controls_long, client.slug, "routes_controls_long", sync_timestamp),
        "va_ritten_controls_long": append_history_dataset(va_ritten_controls_long, client.slug, "va_ritten_controls_long", sync_timestamp),
    }

    run_descriptions: dict[int, str | None] = {}
    run_transport_types: dict[int, str | None] = {}
    if not current_runs_frame.empty:
        current_runs_frame["stuurtabel_id"] = pd.to_numeric(current_runs_frame["stuurtabel_id"], errors="coerce")
        for row in current_runs_frame.itertuples(index=False):
            if pd.notna(row.stuurtabel_id):
                run_descriptions[int(row.stuurtabel_id)] = None if pd.isna(row.omschrijving) else str(row.omschrijving)
                run_transport_types[int(row.stuurtabel_id)] = None if pd.isna(row.soortvervoer) else str(row.soortvervoer)

    current_counts = {
        "ritten_detail": write_current_dataset(ritten_detail, client.slug, "ritten_detail"),
        "routes_detail": write_current_dataset(routes_detail, client.slug, "routes_detail"),
        "va_ritten_detail": write_current_dataset(va_ritten_detail, client.slug, "va_ritten_detail"),
        "executed_controls": write_current_dataset(executed_controls, client.slug, "executed_controls"),
        "ritten_controls_long": write_current_dataset(ritten_controls_long, client.slug, "ritten_controls_long"),
        "routes_controls_long": write_current_dataset(routes_controls_long, client.slug, "routes_controls_long"),
        "va_ritten_controls_long": write_current_dataset(va_ritten_controls_long, client.slug, "va_ritten_controls_long"),
        "manifest": update_manifest(client.slug, current_ids, sync_timestamp, run_descriptions, run_transport_types),
    }

    metadata = {
        "current_ids": current_ids,
        "current_counts": current_counts,
        "history_counts": history_counts,
        "sync_timestamp": sync_timestamp.isoformat(),
        "discovered_tables": discovered_tables,
        "run_descriptions": run_descriptions,
        "run_transport_types": run_transport_types,
        "raw_source_columns": {
            "ritten_detail": _raw_frame_columns(ritten_raw),
            "routes_detail": _raw_frame_columns(routes_raw),
            "va_ritten_detail": _raw_frame_columns(va_ritten_raw),
            "executed_controls": _raw_frame_columns(controls_raw),
        },
    }
    records_synced = sum(current_counts.values()) - current_counts["manifest"]

    logger.info(
        "Client sync completed",
        extra={"client_slug": client.slug, "current_ids": current_ids, "current_counts": current_counts},
    )
    return SyncJobResult(records_synced=records_synced, message="Sync completed", metadata=metadata)
