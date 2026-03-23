from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

import duckdb
from django.conf import settings


@dataclass
class DashboardMetrics:
    total_checked: int = 0
    total_deviations: int = 0
    deviation_percentage: float = 0.0
    deviation_amount: float = 0.0


@dataclass
class RunOption:
    stuurtabel_id: int
    omschrijving: str | None = None
    soortvervoer: str | None = None


@dataclass
class ControlReportSummary:
    total_checked: int = 0
    total_deviations: int = 0
    deviation_percentage: float = 0.0


@dataclass
class ControlRouteOption:
    route_nummer: str
    route_datum: str | None = None
    improvement_minutes: float | None = None
    label: str | None = None
    route_key: str | None = None


@dataclass
class ExecutedControlOption:
    control_id: int | None
    label: str


class DuckDBAnalyticsService:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = str(database_path or settings.DUCKDB_PATH)

    def connect(self):
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(self.database_path)

    def _dataset_glob(self, client_slug: str, dataset: str) -> str:
        return str(settings.DATA_DIR / f"client={client_slug}" / f"dataset={dataset}" / "current" / "*.parquet")

    def _table_exists(self, path_glob: str) -> bool:
        return any(Path(path_glob.rsplit("/", 1)[0]).glob("*.parquet"))

    def _dataset_columns(self, conn, path_glob: str) -> set[str]:
        query = f"DESCRIBE SELECT * FROM read_parquet('{path_glob}')"
        rows = conn.execute(query).fetchall()
        return {row[0] for row in rows}

    def _run_filter_sql(self, stuurtabel_id: int | None, prefix: str = "") -> str:
        if stuurtabel_id is None:
            return ""
        qualified = f"{prefix}stuurtabel_id" if prefix else "stuurtabel_id"
        return f" AND {qualified} = {int(stuurtabel_id)}"

    def _strip_location_code(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        return re.sub(r"^\d{5}\s+", "", text)

    def _float_or_none(self, value):
        return None if value is None else float(value)

    def _dataset_family(self, client_slug: str, stuurtabel_id: int | None) -> tuple[str, str]:
        if stuurtabel_id is None:
            return "ritten_detail", "ritten_controls_long"
        run_option = self.get_run_option(client_slug, stuurtabel_id)
        if run_option and (run_option.soortvervoer or "").upper() == "VA":
            return "va_ritten_detail", "va_ritten_controls_long"
        return "ritten_detail", "ritten_controls_long"

    def get_current_run_ids(self, client_slug: str) -> list[RunOption]:
        path_glob = self._dataset_glob(client_slug, "manifest")
        if not self._table_exists(path_glob):
            return []

        with self.connect() as conn:
            columns = self._dataset_columns(conn, path_glob)
            description_column = "omschrijving" if "omschrijving" in columns else "NULL AS omschrijving"
            transport_column = "soortvervoer" if "soortvervoer" in columns else "NULL AS soortvervoer"
            query = f"""
                SELECT stuurtabel_id, {description_column}, {transport_column}
                FROM read_parquet('{path_glob}')
                WHERE is_current = TRUE
                ORDER BY stuurtabel_id DESC
            """
            return [
                RunOption(stuurtabel_id=row[0], omschrijving=row[1], soortvervoer=row[2])
                for row in conn.execute(query).fetchall()
            ]

    def get_run_option(self, client_slug: str, stuurtabel_id: int) -> RunOption | None:
        for option in self.get_current_run_ids(client_slug):
            if option.stuurtabel_id == stuurtabel_id:
                return option
        return None

    def get_dashboard_metrics(self, client_slug: str, stuurtabel_id: int | None = None) -> DashboardMetrics:
        detail_dataset, control_dataset = self._dataset_family(client_slug, stuurtabel_id)
        ritten_glob = self._dataset_glob(client_slug, detail_dataset)
        controls_glob = self._dataset_glob(client_slug, control_dataset)
        if not self._table_exists(ritten_glob):
            return DashboardMetrics()

        with self.connect() as conn:
            total_checked = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM read_parquet('{ritten_glob}')
                WHERE 1=1 {self._run_filter_sql(stuurtabel_id)}
                """
            ).fetchone()[0]
            total_deviations = 0
            deviation_percentage = 0.0
            if self._table_exists(controls_glob):
                deviation_query = f"""
                    SELECT COUNT(DISTINCT entity_id)
                    FROM read_parquet('{controls_glob}')
                    WHERE is_deviation = TRUE {self._run_filter_sql(stuurtabel_id)}
                """
                total_deviations = conn.execute(deviation_query).fetchone()[0]
            if total_checked:
                deviation_percentage = round(100.0 * total_deviations / total_checked, 2)
            return DashboardMetrics(
                total_checked=total_checked,
                total_deviations=total_deviations,
                deviation_percentage=deviation_percentage,
                deviation_amount=0.0,
            )

    def get_control_breakdown(self, client_slug: str, stuurtabel_id: int | None = None):
        _, control_dataset = self._dataset_family(client_slug, stuurtabel_id)
        path_glob = self._dataset_glob(client_slug, control_dataset)
        if not self._table_exists(path_glob):
            return []

        with self.connect() as conn:
            query = f"""
                SELECT controle_id, COUNT(*) AS total
                FROM read_parquet('{path_glob}')
                WHERE is_deviation = TRUE {self._run_filter_sql(stuurtabel_id)}
                GROUP BY controle_id
                ORDER BY controle_id
            """
            return conn.execute(query).fetchall()

    def get_executed_controls(self, client_slug: str, stuurtabel_id: int | None = None):
        path_glob = self._dataset_glob(client_slug, "executed_controls")
        if not self._table_exists(path_glob):
            return []

        with self.connect() as conn:
            columns = self._dataset_columns(conn, path_glob)
            has_description = "omschrijving" in columns
            select_description = "omschrijving" if has_description else "NULL AS omschrijving"
            order_description = ", omschrijving" if has_description else ""
            query = f"""
                SELECT DISTINCT
                    COALESCE(controlecode, controle_id) AS control_id,
                    {select_description}
                FROM read_parquet('{path_glob}')
                WHERE uitgevoerd = TRUE {self._run_filter_sql(stuurtabel_id)}
                ORDER BY control_id{order_description}
            """
            rows = conn.execute(query).fetchall()
            controls: list[ExecutedControlOption] = []
            for control_id, omschrijving in rows:
                if control_id is None and not omschrijving:
                    continue
                if omschrijving:
                    label = f"{control_id} - {omschrijving}" if control_id is not None else str(omschrijving)
                else:
                    label = str(control_id)
                controls.append(ExecutedControlOption(control_id=control_id, label=label))
            return controls

    def get_driftable_rows(self, client_slug: str, stuurtabel_id: int | None = None):
        _, control_dataset = self._dataset_family(client_slug, stuurtabel_id)
        path_glob = self._dataset_glob(client_slug, control_dataset)
        if not self._table_exists(path_glob):
            return []

        with self.connect() as conn:
            query = f"""
                SELECT entity_id, vervoerder, perceel, datum, controle_id, resultaat, tekst
                FROM read_parquet('{path_glob}')
                WHERE is_deviation = TRUE {self._run_filter_sql(stuurtabel_id)}
                ORDER BY datum DESC NULLS LAST, controle_id
                LIMIT 100
            """
            return conn.execute(query).fetchall()

    def get_control_1_report(self, client_slug: str, stuurtabel_id: int | None = None):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), []

        with self.connect() as conn:
            filter_sql = self._run_filter_sql(stuurtabel_id)
            summary_query = f"""
                SELECT
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_1, 0) <> 0 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
            """
            total_checked, total_deviations = conn.execute(summary_query).fetchone()
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            detail_query = f"""
                SELECT
                    datum,
                    klant_nummer,
                    reiziger_naam,
                    locatie_van,
                    postcode_van,
                    bestelde_vertrektijd,
                    locatie_naar,
                    postcode_naar,
                    bestelde_aankomsttijd,
                    tekst_1 AS match_uitleg,
                    bedrag_ex_btw,
                    status_rit,
                    route_nummer
                FROM read_parquet('{path_glob}')
                WHERE COALESCE(resultaat_1, 0) <> 0 {filter_sql}
                ORDER BY datum, klant_nummer, reiziger_naam
                LIMIT 500
            """
            rows = []
            for row in conn.execute(detail_query).fetchall():
                row = list(row)
                row[3] = self._strip_location_code(row[3])
                row[6] = self._strip_location_code(row[6])
                rows.append(tuple(row))
            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                rows,
            )

    def get_control_8_report(self, client_slug: str, stuurtabel_id: int | None = None):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), []

        with self.connect() as conn:
            filter_sql = self._run_filter_sql(stuurtabel_id)
            summary_query = f"""
                SELECT
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_8, 0) <> 0 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE geplande_instap_tijd IS NOT NULL
                  AND geplande_uitstap_tijd IS NOT NULL
                  {filter_sql}
            """
            total_checked, total_deviations = conn.execute(summary_query).fetchone()
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            detail_query = f"""
                SELECT
                    datum,
                    klant_nummer,
                    reiziger_naam,
                    locatie_van,
                    locatie_naar,
                    geplande_instap_tijd,
                    geplande_uitstap_tijd,
                    dempelwaarde_8 AS max_reistijd,
                    controlewaarde_8 AS geplande_reistijd,
                    (controlewaarde_8 - dempelwaarde_8) AS overschrijding,
                    gerealiseerde_instap_tijd,
                    gerealiseerde_uitstap_tijd,
                    CASE
                        WHEN gerealiseerde_instap_tijd IS NOT NULL AND gerealiseerde_uitstap_tijd IS NOT NULL
                        THEN date_diff(
                            'minute',
                            CAST(gerealiseerde_instap_tijd AS TIME),
                            CAST(gerealiseerde_uitstap_tijd AS TIME)
                        )
                        ELSE NULL
                    END AS real_reistijd
                FROM read_parquet('{path_glob}')
                WHERE COALESCE(resultaat_8, 0) <> 0 {filter_sql}
                ORDER BY overschrijding DESC NULLS LAST, datum, klant_nummer
                LIMIT 500
            """
            rows = []
            for row in conn.execute(detail_query).fetchall():
                row = list(row)
                row[3] = self._strip_location_code(row[3])
                row[4] = self._strip_location_code(row[4])
                rows.append(tuple(row))
            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                rows,
            )

    def get_control_10_report(self, client_slug: str, stuurtabel_id: int | None = None, route_key: str | None = None):
        routes_glob = self._dataset_glob(client_slug, "routes_detail")
        ritten_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(routes_glob) or not self._table_exists(ritten_glob):
            return ControlReportSummary(), [], None, [], []

        with self.connect() as conn:
            filter_sql = self._run_filter_sql(stuurtabel_id)
            summary_query = f"""
                SELECT
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_10, 0) <> 0 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{routes_glob}')
                WHERE route_nummer IS NOT NULL {filter_sql}
            """
            total_checked, total_deviations = conn.execute(summary_query).fetchone()
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            routes_query = f"""
                SELECT
                    CAST(datum AS DATE) AS route_datum,
                    CAST(route_nummer AS VARCHAR) AS route_nummer,
                    COALESCE(resultaat_10, 0) AS resultaat_10,
                    controlewaarde_10,
                    tekst_10
                FROM read_parquet('{routes_glob}')
                WHERE route_nummer IS NOT NULL
                  AND COALESCE(resultaat_10, 0) <> 0
                  {filter_sql}
                ORDER BY COALESCE(controlewaarde_10, 0) DESC, route_datum DESC, route_nummer
            """
            route_rows = conn.execute(routes_query).fetchall()
            route_options = [
                ControlRouteOption(
                    route_datum=str(row[0]) if row[0] is not None else None,
                    route_nummer=row[1],
                    improvement_minutes=self._float_or_none(row[3]),
                    label=(
                        f"{row[0]} - {row[1]} - {row[3]} min"
                        if row[3] is not None
                        else f"{row[0]} - {row[1]}"
                    ),
                    route_key=f"{row[0]}__{row[1]}",
                )
                for row in route_rows
            ]

            valid_route_keys = {option.route_key for option in route_options}
            selected_route_key = route_key if route_key in valid_route_keys else route_options[0].route_key if route_options else None
            selected_route = None
            selected_date = None
            if selected_route_key:
                selected_date, selected_route = selected_route_key.split("__", 1)
            actual_points: list[dict] = []
            replanned_points: list[dict] = []
            route_detail_rows = []

            if selected_route and selected_date:
                points_query = f"""
                    SELECT
                        id,
                        datum,
                        klant_nummer,
                        reiziger_naam,
                        locatie_van,
                        postcode_van,
                        latitude_van,
                        longitude_van,
                        bestelde_vertrektijd,
                        netto_instap,
                        locatie_naar,
                        postcode_naar,
                        latitude_naar,
                        longitude_naar,
                        bestelde_aankomsttijd,
                        netto_uitstap,
                        geplande_instap_tijd,
                        geplande_uitstap_tijd,
                        netto_herplan_instap,
                        netto_herplan_uitstap,
                        controlewaarde_8,
                        dempelwaarde_8,
                        tekst_8,
                        vervoerder
                    FROM read_parquet('{ritten_glob}')
                    WHERE route_nummer = '{selected_route}'
                      AND CAST(datum AS DATE) = DATE '{selected_date}'
                      {filter_sql}
                    ORDER BY id, datum
                """
                rows = conn.execute(points_query).fetchall()
                actual_events = []
                replanned_events = []
                for row in rows:
                    (
                        ride_id,
                        datum,
                        klant_nummer,
                        reiziger_naam,
                        locatie_van,
                        postcode_van,
                        latitude_van,
                        longitude_van,
                        bestelde_vertrektijd,
                        netto_instap,
                        locatie_naar,
                        postcode_naar,
                        latitude_naar,
                        longitude_naar,
                        bestelde_aankomsttijd,
                        netto_uitstap,
                        geplande_instap_tijd,
                        geplande_uitstap_tijd,
                        netto_herplan_instap,
                        netto_herplan_uitstap,
                        controlewaarde_8,
                        dempelwaarde_8,
                        tekst_8,
                        vervoerder,
                    ) = row

                    if latitude_van is not None and longitude_van is not None and netto_instap is not None:
                        label = f"{self._strip_location_code(locatie_van)} - {reiziger_naam or ''}".strip(" -")
                        actual_events.append(
                            {
                                "ride_id": ride_id,
                                "event_type": "pickup",
                                "label": label,
                                "lat": float(latitude_van),
                                "lng": float(longitude_van),
                                "time": str(netto_instap),
                            }
                        )
                    if latitude_naar is not None and longitude_naar is not None and netto_uitstap is not None:
                        label = f"{self._strip_location_code(locatie_naar)} - {reiziger_naam or ''}".strip(" -")
                        actual_events.append(
                            {
                                "ride_id": ride_id,
                                "event_type": "dropoff",
                                "label": label,
                                "lat": float(latitude_naar),
                                "lng": float(longitude_naar),
                                "time": str(netto_uitstap),
                            }
                        )
                    if latitude_van is not None and longitude_van is not None and netto_herplan_instap is not None:
                        label = f"{self._strip_location_code(locatie_van)} - {reiziger_naam or ''}".strip(" -")
                        replanned_events.append(
                            {
                                "ride_id": ride_id,
                                "event_type": "pickup",
                                "label": label,
                                "lat": float(latitude_van),
                                "lng": float(longitude_van),
                                "time": str(netto_herplan_instap),
                            }
                        )
                    if latitude_naar is not None and longitude_naar is not None and netto_herplan_uitstap is not None:
                        label = f"{self._strip_location_code(locatie_naar)} - {reiziger_naam or ''}".strip(" -")
                        replanned_events.append(
                            {
                                "ride_id": ride_id,
                                "event_type": "dropoff",
                                "label": label,
                                "lat": float(latitude_naar),
                                "lng": float(longitude_naar),
                                "time": str(netto_herplan_uitstap),
                            }
                        )

                    route_detail_rows.append(
                        (
                            datum,
                            klant_nummer,
                            reiziger_naam,
                            geplande_instap_tijd,
                            self._strip_location_code(locatie_van),
                            postcode_van,
                            geplande_uitstap_tijd,
                            self._strip_location_code(locatie_naar),
                            postcode_naar,
                            None
                            if geplande_instap_tijd is None or geplande_uitstap_tijd is None
                            else int(
                                (
                                    datetime.combine(datetime.today(), geplande_uitstap_tijd)
                                    - datetime.combine(datetime.today(), geplande_instap_tijd)
                                ).total_seconds()
                                / 60
                            ),
                            bestelde_aankomsttijd,
                            bestelde_vertrektijd,
                            netto_instap,
                            netto_uitstap,
                            netto_herplan_instap,
                            netto_herplan_uitstap,
                            vervoerder,
                        )
                    )

                actual_events.sort(key=lambda item: (item["time"], item["ride_id"], item["event_type"]))
                replanned_events.sort(key=lambda item: (item["time"], item["ride_id"], item["event_type"]))
                actual_points = [
                    {**item, "index": index + 1}
                    for index, item in enumerate(actual_events)
                ]
                replanned_points = [
                    {**item, "index": index + 1}
                    for index, item in enumerate(replanned_events)
                ]

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                route_options,
                selected_route_key,
                actual_points,
                replanned_points,
                route_detail_rows,
            )
