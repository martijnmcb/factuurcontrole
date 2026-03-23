from __future__ import annotations

import os
from collections.abc import Mapping

import pyodbc

from apps.clients.models import DataSourceConfig

PIPELINE_INTERNAL_EXTRA_PARAM_KEYS = {
    "schema",
    "default_schema",
    "source_schema",
    "source_tables",
}


def _serialize_extra_params(extra_params: Mapping[str, object] | None) -> list[str]:
    if not extra_params:
        return []
    parts: list[str] = []
    for key, value in extra_params.items():
        if key in PIPELINE_INTERNAL_EXTRA_PARAM_KEYS:
            continue
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue
        parts.append(f"{key}={value}")
    return parts


def _resolve_driver(configured_driver: str | None) -> str:
    available_drivers = pyodbc.drivers()
    preferred_drivers = [
        configured_driver,
        os.getenv("SQLSERVER_DRIVER"),
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
    ]

    for driver in preferred_drivers:
        if driver and driver in available_drivers:
            return driver

    sql_server_drivers = [driver for driver in available_drivers if "sql server" in driver.lower()]
    if sql_server_drivers:
        return sql_server_drivers[-1]

    raise pyodbc.Error(
        "No compatible SQL Server ODBC driver found. Installed drivers: "
        + ", ".join(available_drivers or ["<none>"])
    )


def create_connection(config: DataSourceConfig):
    driver = _resolve_driver(config.driver)
    server = getattr(config, "server", "") or getattr(config, "host", "")
    trust_server_certificate = os.getenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yes")
    timeout = os.getenv("SQLSERVER_CONNECT_TIMEOUT", "30")

    connection_parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={config.database}",
        f"TrustServerCertificate={trust_server_certificate}",
        f"Connection Timeout={timeout}",
    ]

    if config.username and config.password:
        connection_parts.extend([f"UID={config.username}", f"PWD={config.password}"])
    else:
        connection_parts.append("Trusted_Connection=yes")

    connection_parts.extend(_serialize_extra_params(config.extra_params))
    return pyodbc.connect(";".join(connection_parts))
