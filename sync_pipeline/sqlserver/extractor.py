from __future__ import annotations

import re
from collections.abc import Sequence

import pandas as pd

from apps.clients.models import DataSourceConfig

RUN_ID_CANDIDATES = [
    "stuurtabel_id",
    "stuurtabelid",
    "stuur_tabel_id",
    "stuurtabel_id",
    "stuur_tabelid",
    "id",
]


def _snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower()


def _normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()
    normalized.columns = [_snake_case(column) for column in normalized.columns]
    return normalized


def _find_first_matching_column(dataframe: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    columns = set(dataframe.columns)
    for candidate in candidates:
        normalized_candidate = _snake_case(candidate)
        if normalized_candidate in columns:
            return normalized_candidate
    return None


def _build_in_clause(values: Sequence[int]) -> tuple[str, list[int]]:
    placeholders = ", ".join("?" for _ in values)
    return f"({placeholders})", list(values)


def _read_dataframe(connection, query: str, params: Sequence[object] | None = None) -> pd.DataFrame:
    cursor = connection.cursor()
    cursor.execute(query, list(params or []))
    columns = [column[0] for column in cursor.description] if cursor.description else []
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def _configured_schema(config: DataSourceConfig | None) -> str | None:
    if not config:
        return "facturatie"
    for key in ("schema", "default_schema", "source_schema"):
        value = config.extra_params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "facturatie"


def _configured_table_overrides(config: DataSourceConfig | None) -> dict[str, str]:
    if not config:
        return {}
    raw = config.extra_params.get("source_tables", {})
    return raw if isinstance(raw, dict) else {}


def _qualify_table_name(table_name: str, schema: str | None) -> str:
    return f"[{schema}].[{table_name}]" if schema else f"[{table_name}]"


def _discover_table_mapping(connection) -> dict[str, str]:
    query = """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
    """
    dataframe = _read_dataframe(connection, query)
    mapping: dict[str, str] = {}
    if dataframe.empty:
        return mapping
    normalized = _normalize_columns(dataframe)
    for row in normalized.itertuples(index=False):
        schema = getattr(row, "table_schema", None)
        table_name = getattr(row, "table_name", None)
        if not schema or not table_name:
            continue
        mapping[str(table_name).lower()] = _qualify_table_name(str(table_name), str(schema))
    return mapping


def _resolve_table_name(
    connection,
    logical_name: str,
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> str:
    overrides = _configured_table_overrides(config)
    if logical_name in overrides and isinstance(overrides[logical_name], str):
        return overrides[logical_name]

    schema = _configured_schema(config)
    if schema:
        return _qualify_table_name(logical_name, schema)

    discovered_tables = discovered_tables or {}
    if logical_name.lower() in discovered_tables:
        return discovered_tables[logical_name.lower()]

    return _qualify_table_name(logical_name, "dbo")


def extract_current_runs(
    connection,
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> list[int]:
    dataframe = extract_current_runs_frame(connection, config, discovered_tables)
    if dataframe.empty:
        return []
    ids = pd.to_numeric(dataframe["stuurtabel_id"], errors="coerce").dropna().tolist()
    return [int(value) for value in ids]


def extract_current_runs_frame(
    connection,
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    table_name = _resolve_table_name(connection, "stuurtabel2_last", config, discovered_tables)
    dataframe = _normalize_columns(_read_dataframe(connection, f"SELECT * FROM {table_name}"))
    run_id_column = _find_first_matching_column(dataframe, RUN_ID_CANDIDATES)
    if not run_id_column:
        return pd.DataFrame(columns=["stuurtabel_id", "omschrijving"])
    dataframe["stuurtabel_id"] = pd.to_numeric(dataframe[run_id_column], errors="coerce")
    if "omschrijving" not in dataframe.columns:
        dataframe["omschrijving"] = pd.NA
    if "soortvervoer" not in dataframe.columns:
        dataframe["soortvervoer"] = pd.NA
    return dataframe[["stuurtabel_id", "omschrijving", "soortvervoer"]].dropna(subset=["stuurtabel_id"]).drop_duplicates()


def _extract_filtered_table(
    connection,
    table_name: str,
    stuurtabel_ids: Sequence[int],
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    if not stuurtabel_ids:
        return pd.DataFrame()
    resolved_table = _resolve_table_name(connection, table_name, config, discovered_tables)
    dataframe = _normalize_columns(_read_dataframe(connection, f"SELECT * FROM {resolved_table}"))
    run_id_column = _find_first_matching_column(dataframe, RUN_ID_CANDIDATES)
    if not run_id_column:
        return dataframe
    dataframe["stuurtabel_id"] = pd.to_numeric(dataframe[run_id_column], errors="coerce")
    filtered = dataframe[dataframe["stuurtabel_id"].isin(stuurtabel_ids)]
    return filtered


def _extract_unfiltered_table(
    connection,
    table_name: str,
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    resolved_table = _resolve_table_name(connection, table_name, config, discovered_tables)
    return _normalize_columns(_read_dataframe(connection, f"SELECT * FROM {resolved_table}"))


def extract_ritten_detail(
    connection,
    stuurtabel_ids: Sequence[int],
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    return _extract_filtered_table(connection, "gecontroleerdeRittenDetail", stuurtabel_ids, config, discovered_tables)


def extract_routes_detail(
    connection,
    stuurtabel_ids: Sequence[int],
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    return _extract_filtered_table(connection, "gecontroleerdeRoutesDetail", stuurtabel_ids, config, discovered_tables)


def extract_va_ritten_detail(
    connection,
    stuurtabel_ids: Sequence[int],
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    return _extract_filtered_table(connection, "gecontroleerdeVARittenDetail", stuurtabel_ids, config, discovered_tables)


def _candidate_join_keys(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    candidates = ["stuurtabel_id", "controle_id", "controlecode", "id"]
    return [column for column in candidates if column in left.columns and column in right.columns]


def extract_controls(
    connection,
    stuurtabel_ids: Sequence[int],
    config: DataSourceConfig | None = None,
    discovered_tables: dict[str, str] | None = None,
) -> pd.DataFrame:
    controle_df = _extract_unfiltered_table(connection, "controle", config, discovered_tables)
    controle_done_df = _extract_filtered_table(connection, "controleDone", stuurtabel_ids, config, discovered_tables)

    if not controle_df.empty and "controle_id" not in controle_df.columns:
        if "id" in controle_df.columns:
            controle_df["controle_id"] = controle_df["id"]
        elif "controlecode" in controle_df.columns:
            controle_df["controle_id"] = controle_df["controlecode"]

    if not controle_done_df.empty and "controle_id" not in controle_done_df.columns:
        if "id" in controle_done_df.columns:
            controle_done_df["controle_id"] = controle_done_df["id"]
        elif "controlecode" in controle_done_df.columns:
            controle_done_df["controle_id"] = controle_done_df["controlecode"]

    if controle_df.empty and controle_done_df.empty:
        return pd.DataFrame()
    if controle_done_df.empty:
        return controle_df
    if controle_df.empty:
        return controle_done_df

    join_keys = _candidate_join_keys(controle_done_df, controle_df)
    if not join_keys and "stuurtabel_id" in controle_df.columns and "stuurtabel_id" in controle_done_df.columns:
        join_keys = ["stuurtabel_id"]

    if not join_keys:
        return controle_done_df

    merged = controle_done_df.merge(controle_df, on=join_keys, how="left", suffixes=("_done", "_controle"))

    if "omschrijving_controle" in merged.columns and "omschrijving" not in merged.columns:
        merged["omschrijving"] = merged["omschrijving_controle"]
    if "omschrijving_done" in merged.columns and "omschrijving" not in merged.columns:
        merged["omschrijving"] = merged["omschrijving_done"]

    return merged
