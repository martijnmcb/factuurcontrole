from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
import re

import duckdb
from django.conf import settings

from .models import ControlContent


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
class ControlTrendPoint:
    stuurtabel_id: int
    label: str
    total_deviations: int
    total_checked: int
    deviation_percentage: float


@dataclass
class Control11ClassRow:
    emission_class: str
    vehicles: int
    rides: int
    ride_percentage: float
    client_km: float
    client_km_percentage: float | None


@dataclass
class Control11VehicleRow:
    kenteken: str
    emission_class: str
    inzetdagen: int
    routes: int
    rides: int


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


CONTROL_DEFINITIONS = {
    1: {"title": "Controle 1 - Bestelling ook in SW?", "entity": "rit", "metric_label": "Afwijkingen"},
    2: {"title": "Controle 2 - Tijdig afwezig gemeld?", "entity": "rit", "metric_label": "Tijdig afwezig gemeld, wel op factuur"},
    3: {"title": "Controle 3 - Routes zonder reizigers", "entity": "route", "metric_label": "Routes zonder reizigers"},
    4: {"title": "Controle 4", "entity": "rit", "metric_label": "Geen output"},
    5: {"title": "Controle 5", "entity": "route", "metric_label": "Afwijkingen"},
    7: {"title": "Controle 7 - RDW Controle kenteken", "entity": "route", "metric_label": "Afwijkingen"},
    8: {"title": "Controle 8 - Overschrijden reistijd", "entity": "rit", "metric_label": "Overschrijden max reistijd"},
    9: {"title": "Controle 9 - Controle stiptheid", "entity": "rit", "metric_label": "Afwijkingen"},
    10: {"title": "Controle 10 - Routekaart (optimalisatie)", "entity": "route", "metric_label": "Herplanning sneller"},
    11: {"title": "Controle 11 - Emissie klasse", "entity": "rit", "metric_label": "Afwijkingen"},
    12: {"title": "Controle 12 - Brandstofsoort", "entity": "rit", "metric_label": "Afwijkingen"},
    13: {"title": "Controle 13", "entity": "rit", "metric_label": "Overzicht"},
    14: {"title": "Controle 14 - Route overlap", "entity": "route", "metric_label": "Meer dan 1 route gelijktijdig in voertuig"},
    15: {"title": "Controle 15 - Leegrijd in route", "entity": "route", "metric_label": "Afwijkingen"},
    16: {"title": "Controle 16 - Indicatie rolstoel", "entity": "rit", "metric_label": "Afwijkingen"},
    17: {"title": "Controle 17 - Indicatie solo", "entity": "rit", "metric_label": "Afwijkingen"},
    18: {"title": "Controle 18 - Postcode controle", "entity": "rit", "metric_label": "Afwijkingen"},
    19: {"title": "Controle 19 - Ritten dubbel op factuur", "entity": "rit", "metric_label": "Afwijkingen"},
    20: {"title": "Controle 20 - Kosten per rit", "entity": "route", "metric_label": "Kosten per rit"},
    21: {"title": "Controle 21 - Leegtijd tussen routes", "entity": "route", "metric_label": "Afwijkingen"},
    22: {"title": "Controle 22 - Solo klant ook solo vervoerd?", "entity": "rit", "metric_label": "Afwijkingen"},
    23: {"title": "Controle 23 - Indicatie controle", "entity": "rit", "metric_label": "Afwijkingen"},
    24: {"title": "Controle 24 - Controle levering data", "entity": "rit", "metric_label": "Afwijkingen"},
    1001: {"title": "Controle 1001 - Heeft client een geldig WMO profiel", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1002: {"title": "Controle 1002 - Heeft client alle indicaties", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1003: {"title": "Controle 1003 - Is juiste voertuig gestuurd", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1004: {"title": "Controle 1004 - Emissieklasse voertuigen VA ritten", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1005: {"title": "Controle 1005 - Brandstof voertuigen VA ritten", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1006: {"title": "Controle 1006 - Leeftijd voertuigen VA ritten", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1007: {"title": "Controle 1007 - Heeft vervoerder voldoende dataaangeleverd", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
    1008: {"title": "Controle 1008 - Solo gemarkeerde client gecombineerd", "entity": "rit", "metric_label": "Ritten met afwijkingen"},
}

NON_DEVIATION_CONTROL_IDS = {20}


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

    def _format_cell(self, column: str, value):
        if value is None:
            return ""
        if column == "datum":
            if isinstance(value, datetime):
                return value.strftime("%d-%m-%Y")
            if isinstance(value, str):
                normalized = value.strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", normalized):
                    try:
                        parsed = datetime.fromisoformat(normalized)
                        return parsed.strftime("%d-%m-%Y")
                    except ValueError:
                        pass
        if isinstance(value, str):
            normalized = value.strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", normalized):
                try:
                    parsed = datetime.fromisoformat(normalized)
                    if column in {"bestelde_aankomsttijd", "bestelde_vertrektijd", "geplande_instap_tijd", "geplande_uitstap_tijd"}:
                        return parsed.strftime("%H:%M")
                    return parsed.strftime("%d/%m/%Y %H:%M")
                except ValueError:
                    pass
            if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
                try:
                    parsed_date = date.fromisoformat(normalized)
                    return parsed_date.strftime("%d-%m-%Y")
                except ValueError:
                    pass
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y %H:%M")
        if column in {"datum", "rit_datum"} and isinstance(value, date):
            return value.strftime("%d-%m-%Y")
        if isinstance(value, time):
            return value.strftime("%H:%M")
        time_like_column = (
            "tijd" in column
            or column.startswith("netto_")
            or column.endswith("_uitstap")
            or column.endswith("_instap")
            or column.endswith("_start")
        )
        if time_like_column:
            if hasattr(value, "strftime"):
                return value.strftime("%H:%M")
            return str(value)[:5] if len(str(value)) >= 5 else str(value)
        return value

    def _dataset_family(self, client_slug: str, stuurtabel_id: int | None) -> tuple[str, str]:
        if stuurtabel_id is None:
            return "ritten_detail", "ritten_controls_long"
        run_option = self.get_run_option(client_slug, stuurtabel_id)
        if run_option and (run_option.soortvervoer or "").upper() == "VA":
            return "va_ritten_detail", "va_ritten_controls_long"
        return "ritten_detail", "ritten_controls_long"

    def get_control_definition(self, control_id: int):
        return CONTROL_DEFINITIONS.get(
            control_id,
            {"title": f"Controle {control_id}", "entity": "rit", "metric_label": "Afwijkingen"},
        )

    def get_control_content(self, control_id: int, soortvervoer: str | None = None) -> ControlContent | None:
        normalized = (soortvervoer or "").strip().upper()
        queryset = ControlContent.objects.filter(control_id=control_id, is_active=True)
        if normalized:
            scoped = queryset.filter(soortvervoer=normalized).first()
            if scoped:
                return scoped
        return queryset.filter(soortvervoer="").first()

    def get_control_5_report(self, client_slug: str, stuurtabel_id: int | None, limit: int = 100, offset: int = 0):
        path_glob = self._dataset_glob(client_slug, "routes_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), [], 0

        with self.connect() as conn:
            columns = self._dataset_columns(conn, path_glob)
            if "tekst_5" not in columns and "resultaat_5" not in columns:
                return ControlReportSummary(), [], 0

            filter_sql = self._run_filter_sql(stuurtabel_id)
            deviation_condition = "COALESCE(resultaat_5, 0) <> 0 OR tekst_5 IS NOT NULL"
            total_checked = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
                """
            ).fetchone()[0]
            total_deviations = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE ({deviation_condition}) {filter_sql}
                """
            ).fetchone()[0]
            total_rows = total_deviations
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            query = f"""
                SELECT
                    CAST(datum AS DATE) AS route_date,
                    route_nummer,
                    route_naam,
                    postcode_eerste,
                    postcode_via,
                    postcode_laatste,
                    tekst_5,
                    aantal_lopers,
                    aantal_rollers
                FROM read_parquet('{path_glob}')
                WHERE ({deviation_condition}) {filter_sql}
                ORDER BY route_date, route_nummer
                LIMIT {int(limit)} OFFSET {int(offset)}
            """
            rows = []
            for row in conn.execute(query).fetchall():
                route_date = row[0]
                rows.append(
                    {
                        "route_date": route_date.strftime("%Y-%m-%d") if route_date else "",
                        "route_date_label": route_date.strftime("%d-%m-%Y") if route_date else "",
                        "route_nummer": row[1] or "",
                        "route_naam": row[2] or "",
                        "van": row[3] or "",
                        "via": row[4] or "",
                        "naar": row[5] or "",
                        "foutmelding": row[6] or "",
                        "lopers": row[7] or 0,
                        "rollers": row[8] or 0,
                    }
                )

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                rows,
                total_rows or 0,
            )

    def get_control_5_route_detail(self, client_slug: str, stuurtabel_id: int | None, route_nummer: str, route_date: str):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return []

        with self.connect() as conn:
            query = f"""
                SELECT
                    CAST(datum AS DATE) AS datum,
                    route_nummer,
                    bestelde_aankomsttijd,
                    bestelde_vertrektijd,
                    klant_nummer,
                    reiziger_naam,
                    locatie_van,
                    plaats_van,
                    locatie_naar,
                    plaats_naar,
                    geplande_instap_tijd,
                    geplande_uitstap_tijd,
                    afwezigheids_melding
                FROM read_parquet('{path_glob}')
                WHERE route_nummer = ?
                  AND CAST(datum AS DATE) = CAST(? AS DATE)
                  {self._run_filter_sql(stuurtabel_id)}
                ORDER BY COALESCE(geplande_instap_tijd, bestelde_vertrektijd), klant_nummer, reiziger_naam
            """
            rows = []
            for row in conn.execute(query, [route_nummer, route_date]).fetchall():
                rows.append(
                    (
                        self._format_cell("datum", row[0]),
                        row[1] or "",
                        self._format_cell("bestelde_aankomsttijd", row[2]),
                        self._format_cell("bestelde_vertrektijd", row[3]),
                        row[4] or "",
                        row[5] or "",
                        self._strip_location_code(row[6]),
                        row[7] or "",
                        self._strip_location_code(row[8]),
                        row[9] or "",
                        self._format_cell("geplande_instap_tijd", row[10]),
                        self._format_cell("geplande_uitstap_tijd", row[11]),
                        row[12] or "",
                    )
                )
            return rows

    def is_deviation_control(self, control_id: int | None) -> bool:
        return control_id is not None and int(control_id) not in NON_DEVIATION_CONTROL_IDS

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
                    WHERE is_deviation = TRUE
                      AND COALESCE(controle_id, -1) NOT IN ({", ".join(str(control_id) for control_id in sorted(NON_DEVIATION_CONTROL_IDS))})
                      {self._run_filter_sql(stuurtabel_id)}
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
        breakdown = []
        executed_controls = self.get_executed_controls(client_slug, stuurtabel_id)
        for control in executed_controls:
            if not self.is_deviation_control(control.control_id):
                continue
            control_id = int(control.control_id)
            total = self.get_control_deviation_count(client_slug, control_id, stuurtabel_id)
            definition = self.get_control_definition(control_id)
            control_name = control.label.split(" - ", 1)[1] if " - " in control.label else definition["title"]
            total_checked = self.get_control_checked_count(client_slug, control_id, stuurtabel_id)
            deviation_percentage = round((100.0 * total / total_checked), 2) if total_checked else 0.0
            breakdown.append(
                {
                    "control_id": control_id,
                    "control_name": control_name,
                    "total_deviations": total,
                    "total_checked": total_checked,
                    "deviation_percentage": deviation_percentage,
                }
            )
        return breakdown

    def get_control_deviation_count(self, client_slug: str, control_id: int, stuurtabel_id: int | None = None) -> int:
        path_glob, _checked_condition, deviation_condition = self._control_trend_query_parts(client_slug, control_id, stuurtabel_id)
        if path_glob is None or deviation_condition is None or not self._table_exists(path_glob):
            return 0

        filter_sql = self._run_filter_sql(stuurtabel_id)
        with self.connect() as conn:
            query = f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE {deviation_condition} {filter_sql}
            """
            return conn.execute(query).fetchone()[0] or 0

    def get_control_checked_count(self, client_slug: str, control_id: int, stuurtabel_id: int | None = None) -> int:
        path_glob, checked_condition, _deviation_condition = self._control_trend_query_parts(client_slug, control_id, stuurtabel_id)
        if path_glob is None or checked_condition is None or not self._table_exists(path_glob):
            return 0

        filter_sql = self._run_filter_sql(stuurtabel_id)
        with self.connect() as conn:
            query = f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE {checked_condition} {filter_sql}
            """
            return conn.execute(query).fetchone()[0] or 0

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

    def get_driftable_rows(self, client_slug: str, stuurtabel_id: int | None = None, limit: int = 100, offset: int = 0):
        _, control_dataset = self._dataset_family(client_slug, stuurtabel_id)
        path_glob = self._dataset_glob(client_slug, control_dataset)
        if not self._table_exists(path_glob):
            return [], 0

        with self.connect() as conn:
            total_query = f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE is_deviation = TRUE {self._run_filter_sql(stuurtabel_id)}
            """
            total_rows = conn.execute(total_query).fetchone()[0]
            query = f"""
                SELECT entity_id, vervoerder, perceel, datum, controle_id, resultaat, tekst
                FROM read_parquet('{path_glob}')
                WHERE is_deviation = TRUE {self._run_filter_sql(stuurtabel_id)}
                ORDER BY datum DESC NULLS LAST, controle_id
                LIMIT {int(limit)} OFFSET {int(offset)}
            """
            return conn.execute(query).fetchall(), total_rows

    def get_control_1_report(self, client_slug: str, stuurtabel_id: int | None = None, limit: int = 100, offset: int = 0):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), [], 0

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
            total_rows = total_deviations or 0

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
                    route_nummer,
                    perceel_vervoerder
                FROM read_parquet('{path_glob}')
                WHERE COALESCE(resultaat_1, 0) <> 0 {filter_sql}
                ORDER BY datum, klant_nummer, reiziger_naam
                LIMIT {int(limit)} OFFSET {int(offset)}
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
                total_rows,
            )

    def get_control_1_trend(self, client_slug: str, stuurtabel_id: int | None = None, months: int = 6):
        selected_run = self.get_run_option(client_slug, stuurtabel_id) if stuurtabel_id is not None else None
        current_runs = self.get_current_run_ids(client_slug)
        if not current_runs:
            return None, []

        if selected_run is not None and selected_run.soortvervoer:
            current_runs = [
                run for run in current_runs
                if (run.soortvervoer or "").upper() == (selected_run.soortvervoer or "").upper()
            ]

        if stuurtabel_id is not None:
            selected_index = next((index for index, run in enumerate(current_runs) if run.stuurtabel_id == stuurtabel_id), None)
            if selected_index is None:
                return None, []
        else:
            selected_index = 0

        previous_run = current_runs[selected_index + 1] if selected_index + 1 < len(current_runs) else None
        trend_runs_desc = current_runs[selected_index:selected_index + max(int(months), 1)]
        trend_runs = list(reversed(trend_runs_desc))
        trend_ids = [run.stuurtabel_id for run in trend_runs]
        if not trend_ids:
            return previous_run, []

        path_glob = self._dataset_glob(client_slug, self._dataset_family(client_slug, stuurtabel_id)[0])
        if not self._table_exists(path_glob):
            return previous_run, []

        id_list = ", ".join(str(int(run_id)) for run_id in trend_ids)
        with self.connect() as conn:
            query = f"""
                SELECT
                    stuurtabel_id,
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_1, 0) <> 0 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE stuurtabel_id IN ({id_list})
                GROUP BY stuurtabel_id
            """
            row_map = {
                row[0]: {
                    "total_checked": row[1] or 0,
                    "total_deviations": row[2] or 0,
                }
                for row in conn.execute(query).fetchall()
            }

        trend_points = []
        for run in trend_runs:
            counts = row_map.get(run.stuurtabel_id, {"total_checked": 0, "total_deviations": 0})
            total_checked = counts["total_checked"]
            total_deviations = counts["total_deviations"]
            trend_points.append(
                ControlTrendPoint(
                    stuurtabel_id=run.stuurtabel_id,
                    label=run.omschrijving or str(run.stuurtabel_id),
                    total_deviations=total_deviations,
                    total_checked=total_checked,
                    deviation_percentage=round((100.0 * total_deviations / total_checked), 2) if total_checked else 0.0,
                )
            )

        return previous_run, trend_points

    def get_control_trend(self, client_slug: str, control_id: int, stuurtabel_id: int | None = None, months: int = 6):
        selected_run = self.get_run_option(client_slug, stuurtabel_id) if stuurtabel_id is not None else None
        current_runs = self.get_current_run_ids(client_slug)
        if not current_runs:
            return None, []

        if selected_run is not None and selected_run.soortvervoer:
            current_runs = [
                run for run in current_runs
                if (run.soortvervoer or "").upper() == (selected_run.soortvervoer or "").upper()
            ]

        if stuurtabel_id is not None:
            selected_index = next((index for index, run in enumerate(current_runs) if run.stuurtabel_id == stuurtabel_id), None)
            if selected_index is None:
                return None, []
        else:
            selected_index = 0

        previous_run = current_runs[selected_index + 1] if selected_index + 1 < len(current_runs) else None
        trend_runs_desc = current_runs[selected_index:selected_index + max(int(months), 1)]
        trend_runs = list(reversed(trend_runs_desc))
        trend_ids = [run.stuurtabel_id for run in trend_runs]
        if not trend_ids:
            return previous_run, []

        path_glob, checked_condition, deviation_condition = self._control_trend_query_parts(client_slug, control_id, stuurtabel_id)
        if path_glob is None or not self._table_exists(path_glob):
            return previous_run, []

        id_list = ", ".join(str(int(run_id)) for run_id in trend_ids)
        with self.connect() as conn:
            query = f"""
                SELECT
                    stuurtabel_id,
                    SUM(CASE WHEN {checked_condition} THEN 1 ELSE 0 END) AS total_checked,
                    SUM(CASE WHEN {deviation_condition} THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE stuurtabel_id IN ({id_list})
                GROUP BY stuurtabel_id
            """
            row_map = {
                row[0]: {
                    "total_checked": row[1] or 0,
                    "total_deviations": row[2] or 0,
                }
                for row in conn.execute(query).fetchall()
            }

        trend_points = []
        for run in trend_runs:
            counts = row_map.get(run.stuurtabel_id, {"total_checked": 0, "total_deviations": 0})
            total_checked = counts["total_checked"]
            total_deviations = counts["total_deviations"]
            trend_points.append(
                ControlTrendPoint(
                    stuurtabel_id=run.stuurtabel_id,
                    label=run.omschrijving or str(run.stuurtabel_id),
                    total_deviations=total_deviations,
                    total_checked=total_checked,
                    deviation_percentage=round((100.0 * total_deviations / total_checked), 2) if total_checked else 0.0,
                )
            )

        return previous_run, trend_points

    def _control_trend_query_parts(self, client_slug: str, control_id: int, stuurtabel_id: int | None):
        if control_id == 1:
            return self._dataset_glob(client_slug, "ritten_detail"), "TRUE", "COALESCE(resultaat_1, 0) <> 0"
        if control_id == 8:
            return (
                self._dataset_glob(client_slug, "ritten_detail"),
                "geplande_instap_tijd IS NOT NULL AND geplande_uitstap_tijd IS NOT NULL",
                "geplande_instap_tijd IS NOT NULL AND geplande_uitstap_tijd IS NOT NULL AND COALESCE(resultaat_8, 0) <> 0",
            )
        if control_id == 10:
            return (
                self._dataset_glob(client_slug, "routes_detail"),
                "route_nummer IS NOT NULL",
                "route_nummer IS NOT NULL AND COALESCE(resultaat_10, 0) <> 0",
            )
        if control_id == 11:
            return self._dataset_glob(client_slug, "ritten_detail"), "TRUE", "COALESCE(resultaat_11, 0) > 1"
        if control_id == 1004:
            return self._dataset_glob(client_slug, "va_ritten_detail"), "TRUE", "COALESCE(resultaat_1004, 0) <> 0"
        if control_id == 1005:
            return self._dataset_glob(client_slug, "va_ritten_detail"), "TRUE", "COALESCE(resultaat_1005, 0) <> 0"

        definition = self.get_control_definition(control_id)
        entity = definition["entity"]
        detail_dataset = "routes_detail" if entity == "route" else self._dataset_family(client_slug, stuurtabel_id)[0]
        path_glob = self._dataset_glob(client_slug, detail_dataset)
        result_column = f"resultaat_{control_id}"
        text_column = f"tekst_{control_id}"

        with self.connect() as conn:
            if not self._table_exists(path_glob):
                return None, None, None
            columns = self._dataset_columns(conn, path_glob)
            if result_column not in columns and text_column not in columns:
                return None, None, None

        deviation_parts = []
        if result_column in columns:
            deviation_parts.append(f"COALESCE({result_column}, 0) <> 0")
        if text_column in columns:
            deviation_parts.append(f"{text_column} IS NOT NULL")
        deviation_condition = " OR ".join(deviation_parts) if deviation_parts else "FALSE"
        return path_glob, "TRUE", f"({deviation_condition})"

    def get_control_8_report(self, client_slug: str, stuurtabel_id: int | None = None, limit: int = 100, offset: int = 0):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), [], 0

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
            total_rows = total_deviations or 0

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
                LIMIT {int(limit)} OFFSET {int(offset)}
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
                total_rows,
            )

    def get_control_10_report(
        self,
        client_slug: str,
        stuurtabel_id: int | None = None,
        route_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        routes_glob = self._dataset_glob(client_slug, "routes_detail")
        ritten_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(routes_glob) or not self._table_exists(ritten_glob):
            return ControlReportSummary(), [], None, [], [], [], 0, None, None

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
            route_detail_total = 0
            actual_duration_minutes = None
            replanned_duration_minutes = None

            if selected_route and selected_date:
                total_points_query = f"""
                    SELECT COUNT(*)
                    FROM read_parquet('{ritten_glob}')
                    WHERE route_nummer = '{selected_route}'
                      AND CAST(datum AS DATE) = DATE '{selected_date}'
                      {filter_sql}
                """
                route_detail_total = conn.execute(total_points_query).fetchone()[0]
                duration_query = f"""
                    SELECT
                        CASE
                            WHEN MIN(netto_instap) IS NOT NULL AND MAX(netto_uitstap) IS NOT NULL
                            THEN date_diff('minute', MIN(netto_instap), MAX(netto_uitstap))
                            ELSE NULL
                        END AS actual_duration_minutes,
                        CASE
                            WHEN MIN(netto_herplan_instap) IS NOT NULL AND MAX(netto_herplan_uitstap) IS NOT NULL
                            THEN date_diff('minute', MIN(netto_herplan_instap), MAX(netto_herplan_uitstap))
                            ELSE NULL
                        END AS replanned_duration_minutes
                    FROM read_parquet('{ritten_glob}')
                    WHERE route_nummer = '{selected_route}'
                      AND CAST(datum AS DATE) = DATE '{selected_date}'
                      {filter_sql}
                """
                actual_duration_minutes, replanned_duration_minutes = conn.execute(duration_query).fetchone()
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
                    LIMIT {int(limit)} OFFSET {int(offset)}
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
                route_detail_total,
                actual_duration_minutes,
                replanned_duration_minutes,
            )

    def get_control_11_report(self, client_slug: str, stuurtabel_id: int | None = None, limit: int = 100, offset: int = 0):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), 0, [], [], False, 0

        filter_sql = self._run_filter_sql(stuurtabel_id)
        valid_plate_sql = "kenteken IS NOT NULL AND TRIM(kenteken) NOT IN ('', '00-00-00', 'XX-XX-XX', '-  -  -', '  -  -  ')"
        emission_class_expr = """
            CASE
                WHEN controlewaarde_11 IN ('Z', 'Z/Z') THEN 'Z'
                WHEN controlewaarde_11 IN ('6', '6/6') THEN '6'
                ELSE controlewaarde_11
            END
        """
        client_km_expr = (
            "COALESCE(km_tarief, 0)"
            " + COALESCE(extrakm_start, 0)"
            " + COALESCE(extrakm_rolstoel, 0)"
            " + COALESCE(extrakm_individueel, 0)"
            " + COALESCE(extrakm_kleinschalig, 0)"
            " + COALESCE(extrakm_personenauto, 0)"
            " + COALESCE(extrakm_bus, 0)"
            " + COALESCE(extrakm_voorin, 0)"
        )

        with self.connect() as conn:
            summary_query = f"""
                SELECT
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_11, 0) > 1 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
            """
            total_checked, total_deviations = conn.execute(summary_query).fetchone()

            class_query = f"""
                WITH classified AS (
                    SELECT
                        stuurtabel_id,
                        CAST(datum AS DATE) AS datum,
                        route_nummer,
                        kenteken,
                        {emission_class_expr} AS emission_class
                    FROM read_parquet('{path_glob}')
                    WHERE controlewaarde_11 IS NOT NULL
                      AND {valid_plate_sql}
                      {filter_sql}
                ),
                class_rides AS (
                    SELECT
                        emission_class,
                        COUNT(DISTINCT kenteken) AS vehicles,
                        COUNT(*) AS rides
                    FROM classified
                    GROUP BY 1
                ),
                class_client_km AS (
                    SELECT
                        {emission_class_expr} AS emission_class,
                        SUM({client_km_expr}) AS client_km
                    FROM read_parquet('{path_glob}')
                    WHERE controlewaarde_11 IS NOT NULL
                      AND {valid_plate_sql}
                      {filter_sql}
                    GROUP BY 1
                )
                SELECT
                    cr.emission_class,
                    cr.vehicles,
                    cr.rides,
                    COALESCE(ck.client_km, 0) AS client_km
                FROM class_rides cr
                LEFT JOIN class_client_km ck ON ck.emission_class = cr.emission_class
                ORDER BY cr.vehicles DESC, cr.rides DESC, cr.emission_class
            """
            class_rows_raw = conn.execute(class_query).fetchall()
            total_classified_rides = sum(row[2] for row in class_rows_raw)
            total_client_km = sum(float(row[3] or 0) for row in class_rows_raw)
            kilometer_available = total_client_km > 0

            class_rows = [
                Control11ClassRow(
                    emission_class=row[0],
                    vehicles=row[1],
                    rides=row[2],
                    ride_percentage=round((100.0 * row[2] / total_classified_rides), 2) if total_classified_rides else 0.0,
                    client_km=float(row[3] or 0),
                    client_km_percentage=round((100.0 * float(row[3] or 0) / total_client_km), 2) if kilometer_available else None,
                )
                for row in class_rows_raw
            ]

            total_vehicle_rows_query = f"""
                SELECT COUNT(*)
                FROM (
                    SELECT kenteken, {emission_class_expr} AS emission_class
                    FROM read_parquet('{path_glob}')
                    WHERE controlewaarde_11 IS NOT NULL
                      AND {valid_plate_sql}
                      {filter_sql}
                    GROUP BY kenteken, emission_class
                ) t
            """
            total_vehicle_rows = conn.execute(total_vehicle_rows_query).fetchone()[0]

            detail_query = f"""
                SELECT
                    kenteken,
                    {emission_class_expr} AS emission_class,
                    COUNT(DISTINCT CAST(datum AS DATE)) AS inzetdagen,
                    COUNT(DISTINCT route_nummer) AS routes,
                    COUNT(*) AS rides
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_11 IS NOT NULL
                  AND {valid_plate_sql}
                  {filter_sql}
                GROUP BY kenteken, emission_class
                ORDER BY emission_class, rides DESC, kenteken
                LIMIT {int(limit)} OFFSET {int(offset)}
            """
            vehicle_rows = [
                Control11VehicleRow(
                    kenteken=row[0],
                    emission_class=row[1],
                    inzetdagen=row[2],
                    routes=row[3],
                    rides=row[4],
                )
                for row in conn.execute(detail_query).fetchall()
            ]

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=round((100.0 * total_deviations / total_checked), 2) if total_checked else 0.0,
                ),
                total_classified_rides,
                class_rows,
                vehicle_rows,
                kilometer_available,
                total_vehicle_rows,
            )

    def get_control_1004_report(self, client_slug: str, stuurtabel_id: int | None = None):
        path_glob = self._dataset_glob(client_slug, "va_ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), [], [], [], []

        filter_sql = self._run_filter_sql(stuurtabel_id)
        with self.connect() as conn:
            summary_query = f"""
                SELECT
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_1004, 0) <> 0 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
            """
            total_checked, total_deviations = conn.execute(summary_query).fetchone()
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            emission_classes = [
                row[0]
                for row in conn.execute(
                    f"""
                    SELECT DISTINCT controlewaarde_1004
                    FROM read_parquet('{path_glob}')
                    WHERE controlewaarde_1004 IS NOT NULL
                      {filter_sql}
                    ORDER BY controlewaarde_1004
                    """
                ).fetchall()
            ]

            weekly_rows = []
            weekly_data = conn.execute(
                f"""
                SELECT
                    EXTRACT('week' FROM rit_datum) AS iso_week,
                    controlewaarde_1004,
                    COUNT(DISTINCT kenteken) AS vehicles
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_1004 IS NOT NULL
                  {filter_sql}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """
            ).fetchall()
            weekly_matrix: dict[int, dict[str, int]] = {}
            for week, emission_class, vehicles in weekly_data:
                weekly_matrix.setdefault(int(week), {})[emission_class] = vehicles
            for week in sorted(weekly_matrix):
                row = {"label": str(week), "values": [], "total": 0}
                for emission_class in emission_classes:
                    value = weekly_matrix[week].get(emission_class, 0)
                    row["values"].append(value)
                    row["total"] += value
                weekly_rows.append(row)

            trip_rows_raw = conn.execute(
                f"""
                SELECT
                    controlewaarde_1004,
                    COUNT(*) AS trips
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_1004 IS NOT NULL
                  {filter_sql}
                GROUP BY 1
                ORDER BY trips DESC, controlewaarde_1004
                """
            ).fetchall()
            total_trips = sum(row[1] for row in trip_rows_raw)
            trip_rows = [
                {
                    "emission_class": row[0],
                    "trips": row[1],
                    "percentage": round((100.0 * row[1] / total_trips), 2) if total_trips else 0.0,
                }
                for row in trip_rows_raw
            ]

            distance_rows_raw = conn.execute(
                f"""
                SELECT
                    controlewaarde_1004,
                    SUM(COALESCE(afstand_direct, 0)) AS afstand_direct_sum
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_1004 IS NOT NULL
                  {filter_sql}
                GROUP BY 1
                ORDER BY afstand_direct_sum DESC, controlewaarde_1004
                """
            ).fetchall()
            total_distance = sum(float(row[1] or 0) for row in distance_rows_raw)
            distance_rows = [
                {
                    "emission_class": row[0],
                    "distance": float(row[1] or 0),
                    "percentage": round((100.0 * float(row[1] or 0) / total_distance), 2) if total_distance else 0.0,
                }
                for row in distance_rows_raw
            ]

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                emission_classes,
                weekly_rows,
                trip_rows,
                distance_rows,
            )

    def get_control_1005_report(self, client_slug: str, stuurtabel_id: int | None = None):
        path_glob = self._dataset_glob(client_slug, "va_ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), [], [], [], []

        filter_sql = self._run_filter_sql(stuurtabel_id)
        with self.connect() as conn:
            summary_query = f"""
                SELECT
                    COUNT(*) AS total_checked,
                    SUM(CASE WHEN COALESCE(resultaat_1005, 0) <> 0 THEN 1 ELSE 0 END) AS total_deviations
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
            """
            total_checked, total_deviations = conn.execute(summary_query).fetchone()
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            fuel_types = [
                row[0]
                for row in conn.execute(
                    f"""
                    SELECT DISTINCT controlewaarde_1005
                    FROM read_parquet('{path_glob}')
                    WHERE controlewaarde_1005 IS NOT NULL
                      {filter_sql}
                    ORDER BY controlewaarde_1005
                    """
                ).fetchall()
            ]

            weekly_rows = []
            weekly_data = conn.execute(
                f"""
                SELECT
                    EXTRACT('week' FROM rit_datum) AS iso_week,
                    controlewaarde_1005,
                    COUNT(DISTINCT kenteken) AS vehicles
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_1005 IS NOT NULL
                  {filter_sql}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """
            ).fetchall()
            weekly_matrix: dict[int, dict[str, int]] = {}
            for week, fuel_type, vehicles in weekly_data:
                weekly_matrix.setdefault(int(week), {})[fuel_type] = vehicles
            for week in sorted(weekly_matrix):
                row = {"label": str(week), "values": [], "total": 0}
                for fuel_type in fuel_types:
                    value = weekly_matrix[week].get(fuel_type, 0)
                    row["values"].append(value)
                    row["total"] += value
                weekly_rows.append(row)

            trip_rows_raw = conn.execute(
                f"""
                SELECT
                    controlewaarde_1005,
                    COUNT(*) AS trips
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_1005 IS NOT NULL
                  {filter_sql}
                GROUP BY 1
                ORDER BY trips DESC, controlewaarde_1005
                """
            ).fetchall()
            total_trips = sum(row[1] for row in trip_rows_raw)
            trip_rows = [
                {
                    "fuel_type": row[0],
                    "trips": row[1],
                    "percentage": round((100.0 * row[1] / total_trips), 2) if total_trips else 0.0,
                }
                for row in trip_rows_raw
            ]

            distance_rows_raw = conn.execute(
                f"""
                SELECT
                    controlewaarde_1005,
                    SUM(COALESCE(afstand_direct, 0)) AS afstand_direct_sum
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_1005 IS NOT NULL
                  {filter_sql}
                GROUP BY 1
                ORDER BY afstand_direct_sum DESC, controlewaarde_1005
                """
            ).fetchall()
            total_distance = sum(float(row[1] or 0) for row in distance_rows_raw)
            distance_rows = [
                {
                    "fuel_type": row[0],
                    "distance": float(row[1] or 0),
                    "percentage": round((100.0 * float(row[1] or 0) / total_distance), 2) if total_distance else 0.0,
                }
                for row in distance_rows_raw
            ]

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                fuel_types,
                weekly_rows,
                trip_rows,
                distance_rows,
            )

    def get_control_12_report(self, client_slug: str, stuurtabel_id: int | None = None):
        path_glob = self._dataset_glob(client_slug, "ritten_detail")
        if not self._table_exists(path_glob):
            return ControlReportSummary(), 0, [], [], []

        filter_sql = self._run_filter_sql(stuurtabel_id)
        with self.connect() as conn:
            total_checked = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
                """
            ).fetchone()[0]

            fuel_types = [
                row[0]
                for row in conn.execute(
                    f"""
                    SELECT DISTINCT controlewaarde_12
                    FROM read_parquet('{path_glob}')
                    WHERE controlewaarde_12 IS NOT NULL
                      AND TRIM(CAST(controlewaarde_12 AS VARCHAR)) <> ''
                      {filter_sql}
                    ORDER BY controlewaarde_12
                    """
                ).fetchall()
            ]

            classified_rides = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_12 IS NOT NULL
                  AND TRIM(CAST(controlewaarde_12 AS VARCHAR)) <> ''
                  {filter_sql}
                """
            ).fetchone()[0]

            daily_rows_raw = conn.execute(
                f"""
                SELECT
                    CAST(datum AS DATE) AS report_date,
                    controlewaarde_12,
                    COUNT(*) AS rides
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_12 IS NOT NULL
                  AND TRIM(CAST(controlewaarde_12 AS VARCHAR)) <> ''
                  {filter_sql}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """
            ).fetchall()

            daily_totals_raw = conn.execute(
                f"""
                SELECT
                    CAST(datum AS DATE) AS report_date,
                    COUNT(*) AS rides
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_12 IS NOT NULL
                  AND TRIM(CAST(controlewaarde_12 AS VARCHAR)) <> ''
                  {filter_sql}
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()

            daily_totals = {
                row[0]: row[1]
                for row in daily_totals_raw
            }
            daily_matrix: dict[date, dict[str, int]] = {}
            for report_date, fuel_type, rides in daily_rows_raw:
                daily_matrix.setdefault(report_date, {})[fuel_type] = rides

            daily_rows = []
            for report_date in sorted(daily_matrix):
                total_rides = daily_totals.get(report_date, 0)
                cells = []
                for fuel_type in fuel_types:
                    rides = daily_matrix[report_date].get(fuel_type, 0)
                    percentage = round((100.0 * rides / total_rides), 2) if total_rides else 0.0
                    cells.append(
                        {
                            "fuel_type": fuel_type,
                            "rides": rides,
                            "percentage": percentage,
                        }
                    )
                daily_rows.append(
                    {
                        "label": report_date.strftime("%d-%m-%Y") if report_date else "",
                        "sort_value": report_date.strftime("%Y-%m-%d") if report_date else "",
                        "cells": cells,
                        "total": total_rides,
                    }
                )

            monthly_rows_raw = conn.execute(
                f"""
                SELECT
                    STRFTIME(CAST(datum AS DATE), '%Y-%m') AS report_month,
                    controlewaarde_12,
                    COUNT(*) AS rides
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_12 IS NOT NULL
                  AND TRIM(CAST(controlewaarde_12 AS VARCHAR)) <> ''
                  {filter_sql}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """
            ).fetchall()

            monthly_totals_raw = conn.execute(
                f"""
                SELECT
                    STRFTIME(CAST(datum AS DATE), '%Y-%m') AS report_month,
                    COUNT(*) AS rides
                FROM read_parquet('{path_glob}')
                WHERE controlewaarde_12 IS NOT NULL
                  AND TRIM(CAST(controlewaarde_12 AS VARCHAR)) <> ''
                  {filter_sql}
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()

            monthly_totals = {row[0]: row[1] for row in monthly_totals_raw}
            monthly_matrix: dict[str, dict[str, int]] = {}
            for report_month, fuel_type, rides in monthly_rows_raw:
                monthly_matrix.setdefault(report_month, {})[fuel_type] = rides

            monthly_rows = []
            for report_month in sorted(monthly_matrix):
                total_rides = monthly_totals.get(report_month, 0)
                cells = []
                for fuel_type in fuel_types:
                    rides = monthly_matrix[report_month].get(fuel_type, 0)
                    percentage = round((100.0 * rides / total_rides), 2) if total_rides else 0.0
                    cells.append(
                        {
                            "fuel_type": fuel_type,
                            "rides": rides,
                            "percentage": percentage,
                        }
                    )
                monthly_rows.append(
                    {
                        "label": report_month,
                        "sort_value": report_month,
                        "cells": cells,
                        "total": total_rides,
                    }
                )

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=classified_rides or 0,
                    deviation_percentage=round((100.0 * classified_rides / total_checked), 2) if total_checked else 0.0,
                ),
                classified_rides or 0,
                fuel_types,
                daily_rows,
                monthly_rows,
            )

    def get_control_13_report(self, client_slug: str, stuurtabel_id: int | None = None):
        ritten_glob = self._dataset_glob(client_slug, "ritten_detail")
        routes_glob = self._dataset_glob(client_slug, "routes_detail")
        if not self._table_exists(ritten_glob):
            return {
                "total_checked": 0,
                "vehicles": 0,
                "coverage_percentage": 0.0,
                "average_age": None,
            }, [], {"inzetdagen": 0, "passagiers": 0}, []

        filter_sql = self._run_filter_sql(stuurtabel_id)
        route_filter_sql = self._run_filter_sql(stuurtabel_id, "r.")
        with self.connect() as conn:
            summary_row = conn.execute(
                f"""
                WITH base AS (
                    SELECT
                        kenteken,
                        controlewaarde_13
                    FROM read_parquet('{ritten_glob}')
                    WHERE kenteken IS NOT NULL
                      AND TRIM(kenteken) <> ''
                      AND (
                        controlewaarde_13 IS NOT NULL
                        OR dempelwaarde_13 IS NOT NULL
                        OR resultaat_13 IS NOT NULL
                        OR tekst_13 IS NOT NULL
                      )
                      {filter_sql}
                )
                SELECT
                    COUNT(*) AS total_checked,
                    COUNT(DISTINCT kenteken) AS total_vehicles,
                    COUNT(DISTINCT CASE WHEN controlewaarde_13 IS NOT NULL THEN kenteken END) AS vehicles_with_age,
                    AVG(TRY_CAST(controlewaarde_13 AS DOUBLE)) AS average_age
                FROM base
                """
            ).fetchone()

            rows = conn.execute(
                f"""
                WITH base AS (
                    SELECT
                        kenteken,
                        CAST(datum AS DATE) AS ritdatum,
                        dempelwaarde_13,
                        controlewaarde_13,
                        tekst_13
                    FROM read_parquet('{ritten_glob}')
                    WHERE kenteken IS NOT NULL
                      AND TRIM(kenteken) <> ''
                      AND (
                        controlewaarde_13 IS NOT NULL
                        OR dempelwaarde_13 IS NOT NULL
                        OR resultaat_13 IS NOT NULL
                        OR tekst_13 IS NOT NULL
                      )
                      {filter_sql}
                ),
                voertuig_type AS (
                    SELECT
                        r.kenteken,
                        MAX(r.voertuigtype) AS voertuigtype
                    FROM read_parquet('{routes_glob}') r
                    WHERE r.kenteken IS NOT NULL
                      AND TRIM(r.kenteken) <> ''
                      {route_filter_sql}
                    GROUP BY r.kenteken
                )
                SELECT
                    b.kenteken,
                    COUNT(DISTINCT b.ritdatum) AS inzetdagen,
                    COUNT(*) AS vervoerde_passagiers,
                    MAX(b.dempelwaarde_13) AS drempelwaarde,
                    MAX(b.controlewaarde_13) AS controlewaarde,
                    COALESCE(MAX(v.voertuigtype), '') AS voertuigtype,
                    COALESCE(MAX(b.tekst_13), '') AS inrichting
                FROM base b
                LEFT JOIN voertuig_type v ON v.kenteken = b.kenteken
                GROUP BY b.kenteken
                ORDER BY b.kenteken
                """
            ).fetchall()

            age_distribution_rows = conn.execute(
                f"""
                WITH vehicle_age AS (
                    SELECT
                        kenteken,
                        ROUND(AVG(TRY_CAST(controlewaarde_13 AS DOUBLE))) AS age_years
                    FROM read_parquet('{ritten_glob}')
                    WHERE kenteken IS NOT NULL
                      AND TRIM(kenteken) <> ''
                      AND controlewaarde_13 IS NOT NULL
                      {filter_sql}
                    GROUP BY kenteken
                )
                SELECT
                    CAST(age_years AS INTEGER) AS age_years,
                    COUNT(*) AS vehicles
                FROM vehicle_age
                WHERE age_years IS NOT NULL
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()

            report_rows = [
                {
                    "kenteken": row[0] or "",
                    "inzetdagen": row[1] or 0,
                    "vervoerde_passagiers": row[2] or 0,
                    "drempelwaarde": self._float_or_none(row[3]),
                    "controlewaarde": self._float_or_none(row[4]),
                    "type": row[5] or "",
                    "inrichting": row[6] or "",
                }
                for row in rows
            ]

            totals = {
                "inzetdagen": sum(row["inzetdagen"] for row in report_rows),
                "passagiers": sum(row["vervoerde_passagiers"] for row in report_rows),
            }
            total_checked = int(summary_row[0] or 0)
            total_vehicles = int(summary_row[1] or 0)
            vehicles_with_age = int(summary_row[2] or 0)
            average_age = self._float_or_none(summary_row[3])
            summary = {
                "total_checked": total_checked,
                "vehicles": total_vehicles,
                "coverage_percentage": round((100.0 * vehicles_with_age / total_vehicles), 2) if total_vehicles else 0.0,
                "average_age": average_age,
            }
            age_distribution = [
                {"label": str(int(row[0])), "value": int(row[1] or 0)}
                for row in age_distribution_rows
                if row[0] is not None
            ]
            return summary, report_rows, totals, age_distribution

    def get_control_20_report(self, client_slug: str, stuurtabel_id: int | None = None):
        kentallen_glob = self._dataset_glob(client_slug, "kentallen_route")
        if not self._table_exists(kentallen_glob):
            return {
                "total_checked": 0,
                "days_with_cost": 0,
                "coverage_percentage": 0.0,
                "average_cost": None,
                "total_rides": 0,
            }, [], [], []

        filter_sql = self._run_filter_sql(stuurtabel_id)
        with self.connect() as conn:
            summary_row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_rows,
                    COUNT(CASE WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL THEN 1 END) AS rows_with_cost,
                    SUM(COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)) AS total_rides,
                    CASE
                        WHEN SUM(
                            CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                            END
                        ) = 0 THEN NULL
                        ELSE SUM(
                            COALESCE(TRY_CAST(kosten_rit AS DOUBLE), 0)
                            * CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                              END
                        ) / SUM(
                            CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                            END
                        )
                    END AS average_cost
                FROM read_parquet('{kentallen_glob}')
                WHERE 1=1 {filter_sql}
                """
            ).fetchone()

            chart_rows = conn.execute(
                f"""
                SELECT
                    CAST(datum AS DATE) AS datum,
                    CASE
                        WHEN SUM(
                            CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                            END
                        ) = 0 THEN NULL
                        ELSE SUM(
                            COALESCE(TRY_CAST(kosten_rit AS DOUBLE), 0)
                            * CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                              END
                        ) / SUM(
                            CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                            END
                        )
                    END AS kosten_rit
                FROM read_parquet('{kentallen_glob}')
                WHERE 1=1 {filter_sql}
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()

            table_rows = conn.execute(
                f"""
                SELECT
                    CAST(datum AS DATE) AS datum,
                    SUM(COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)) AS n_ritten,
                    CASE
                        WHEN SUM(
                            CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                            END
                        ) = 0 THEN NULL
                        ELSE SUM(
                            COALESCE(TRY_CAST(kosten_rit AS DOUBLE), 0)
                            * CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                              END
                        ) / SUM(
                            CASE
                                WHEN TRY_CAST(kosten_rit AS DOUBLE) IS NOT NULL
                                THEN COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0)
                                ELSE 0
                            END
                        )
                    END AS kosten_rit
                FROM read_parquet('{kentallen_glob}')
                WHERE 1=1 {filter_sql}
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()

            monthly_rows = conn.execute(
                f"""
                WITH anchor AS (
                    SELECT COALESCE(
                        MAX(CASE WHEN 1=1 {filter_sql} THEN CAST(datum AS DATE) END),
                        MAX(CAST(datum AS DATE))
                    ) AS max_date
                    FROM read_parquet('{kentallen_glob}')
                ),
                filtered AS (
                    SELECT
                        DATE_TRUNC('month', datum)::DATE AS month_start,
                        TRY_CAST(kosten_rit AS DOUBLE) AS kosten_rit,
                        COALESCE(TRY_CAST(n_ritten AS DOUBLE), 0) AS n_ritten
                    FROM read_parquet('{kentallen_glob}'), anchor
                    WHERE anchor.max_date IS NOT NULL
                      AND CAST(datum AS DATE) >= DATE_TRUNC('month', anchor.max_date) - INTERVAL 11 MONTH
                      AND CAST(datum AS DATE) < DATE_TRUNC('month', anchor.max_date) + INTERVAL 1 MONTH
                )
                SELECT
                    month_start,
                    CASE
                        WHEN SUM(
                            CASE
                                WHEN kosten_rit IS NOT NULL THEN n_ritten
                                ELSE 0
                            END
                        ) = 0 THEN NULL
                        ELSE SUM(
                            COALESCE(kosten_rit, 0)
                            * CASE
                                WHEN kosten_rit IS NOT NULL THEN n_ritten
                                ELSE 0
                              END
                        ) / SUM(
                            CASE
                                WHEN kosten_rit IS NOT NULL THEN n_ritten
                                ELSE 0
                            END
                        )
                    END AS weighted_cost
                FROM filtered
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()

        total_checked = int(summary_row[0] or 0)
        rows_with_cost = int(summary_row[1] or 0)
        total_rides = int(summary_row[2] or 0)
        average_cost = self._float_or_none(summary_row[3])
        summary = {
            "total_checked": total_checked,
            "days_with_cost": rows_with_cost,
            "coverage_percentage": round((100.0 * rows_with_cost / total_checked), 2) if total_checked else 0.0,
            "average_cost": average_cost,
            "total_rides": total_rides,
        }
        chart_points = [
            {
                "label": row[0].strftime("%d-%m-%Y") if row[0] is not None else "",
                "value": self._float_or_none(row[1]),
            }
            for row in chart_rows
            if row[0] is not None
        ]
        table_data = [
            {
                "datum": row[0].strftime("%d-%m-%Y") if row[0] is not None else "",
                "n_ritten": int(row[1] or 0),
                "kosten_rit": self._float_or_none(row[2]),
            }
            for row in table_rows
        ]
        monthly_chart_points = [
            {
                "label": row[0].strftime("%Y-%m") if row[0] is not None else "",
                "value": self._float_or_none(row[1]),
            }
            for row in monthly_rows
            if row[0] is not None
        ]
        return summary, chart_points, table_data, monthly_chart_points

    def get_generic_control_report(
        self,
        client_slug: str,
        stuurtabel_id: int | None,
        control_id: int,
        limit: int = 100,
        offset: int = 0,
    ):
        definition = self.get_control_definition(control_id)
        entity = definition["entity"]
        detail_dataset = "routes_detail" if entity == "route" else self._dataset_family(client_slug, stuurtabel_id)[0]
        path_glob = self._dataset_glob(client_slug, detail_dataset)
        if not self._table_exists(path_glob):
            return ControlReportSummary(), [], [], 0

        result_column = f"resultaat_{control_id}"
        text_column = f"tekst_{control_id}"
        control_value_column = f"controlewaarde_{control_id}"
        threshold_column = f"dempelwaarde_{control_id}"

        with self.connect() as conn:
            columns = self._dataset_columns(conn, path_glob)
            if result_column not in columns and text_column not in columns:
                return ControlReportSummary(), [], [], 0

            filter_sql = self._run_filter_sql(stuurtabel_id)
            total_checked_query = f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE 1=1 {filter_sql}
            """
            total_checked = conn.execute(total_checked_query).fetchone()[0]

            deviation_condition_parts = []
            if result_column in columns:
                deviation_condition_parts.append(f"COALESCE({result_column}, 0) <> 0")
            if text_column in columns:
                deviation_condition_parts.append(f"{text_column} IS NOT NULL")
            deviation_condition = " OR ".join(deviation_condition_parts) if deviation_condition_parts else "FALSE"

            deviation_query = f"""
                SELECT COUNT(*)
                FROM read_parquet('{path_glob}')
                WHERE ({deviation_condition}) {filter_sql}
            """
            total_deviations = conn.execute(deviation_query).fetchone()[0]
            deviation_percentage = round((100.0 * total_deviations / total_checked), 3) if total_checked else 0.0

            if control_id == 1004:
                headers = ["Kenteken", "Emissieniveau", "Aantal ritten"]
                detail_query = f"""
                    SELECT
                        kenteken,
                        controlewaarde_1004,
                        COUNT(*) AS aantal_ritten
                    FROM read_parquet('{path_glob}')
                    WHERE ({deviation_condition}) {filter_sql}
                    GROUP BY kenteken, controlewaarde_1004
                    ORDER BY aantal_ritten DESC, kenteken
                    LIMIT {int(limit)} OFFSET {int(offset)}
                """
                rows = conn.execute(detail_query).fetchall()
                return (
                    ControlReportSummary(
                        total_checked=total_checked or 0,
                        total_deviations=total_deviations or 0,
                        deviation_percentage=deviation_percentage,
                    ),
                    headers,
                    rows,
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT kenteken, controlewaarde_1004
                            FROM read_parquet('{path_glob}')
                            WHERE ({deviation_condition}) {filter_sql}
                            GROUP BY kenteken, controlewaarde_1004
                        ) t
                        """
                    ).fetchone()[0],
                )
            elif control_id == 1005:
                headers = ["Kenteken", "Brandstof", "Aantal ritten"]
                detail_query = f"""
                    SELECT
                        kenteken,
                        controlewaarde_1005,
                        COUNT(*) AS aantal_ritten
                    FROM read_parquet('{path_glob}')
                    WHERE ({deviation_condition}) {filter_sql}
                    GROUP BY kenteken, controlewaarde_1005
                    ORDER BY aantal_ritten DESC, kenteken
                    LIMIT {int(limit)} OFFSET {int(offset)}
                """
                rows = conn.execute(detail_query).fetchall()
                return (
                    ControlReportSummary(
                        total_checked=total_checked or 0,
                        total_deviations=total_deviations or 0,
                        deviation_percentage=deviation_percentage,
                    ),
                    headers,
                    rows,
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT kenteken, controlewaarde_1005
                            FROM read_parquet('{path_glob}')
                            WHERE ({deviation_condition}) {filter_sql}
                            GROUP BY kenteken, controlewaarde_1005
                        ) t
                        """
                    ).fetchone()[0],
                )
            elif control_id == 1006:
                headers = ["Kenteken", "RitDatum", "Leeftijd voertuig", "Aantal gereden ritten", "Max leeftijd"]
                detail_query = f"""
                    SELECT
                        kenteken,
                        CAST(rit_datum AS DATE) AS rit_datum,
                        controlewaarde_1006,
                        COUNT(*) AS aantal_ritten,
                        dempelwaarde_1006
                    FROM read_parquet('{path_glob}')
                    WHERE ({deviation_condition}) {filter_sql}
                    GROUP BY kenteken, CAST(rit_datum AS DATE), controlewaarde_1006, dempelwaarde_1006
                    ORDER BY rit_datum DESC, kenteken
                    LIMIT {int(limit)} OFFSET {int(offset)}
                """
                rows = []
                for row in conn.execute(detail_query).fetchall():
                    rows.append(
                        (
                            row[0],
                            row[1].strftime("%d-%m-%Y") if row[1] is not None else "",
                            row[2],
                            row[3],
                            row[4],
                        )
                    )
                return (
                    ControlReportSummary(
                        total_checked=total_checked or 0,
                        total_deviations=total_deviations or 0,
                        deviation_percentage=deviation_percentage,
                    ),
                    headers,
                    rows,
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT kenteken, CAST(rit_datum AS DATE), controlewaarde_1006, dempelwaarde_1006
                            FROM read_parquet('{path_glob}')
                            WHERE ({deviation_condition}) {filter_sql}
                            GROUP BY kenteken, CAST(rit_datum AS DATE), controlewaarde_1006, dempelwaarde_1006
                        ) t
                        """
                    ).fetchone()[0],
                )
            elif control_id == 3:
                header_map = [
                    ("datum", "Datum"),
                    ("route_nummer", "Routenummer"),
                    ("kenteken", "Kenteken"),
                    ("postcode_eerste", "PostcodeEerste"),
                    ("postcode_via", "PostcodeVia"),
                    ("postcode_laatste", "PostcodeLaatste"),
                    ("passagiers_namen", "Passagiersnamen"),
                    ("geplande_start_tijd", "GeplandeStartTijd"),
                    ("geplande_uitstap", "GeplandeUitstap"),
                    ("gerealiseerde_start_tijd", "GerealiseerdeStartTijd"),
                    ("gerealiseerde_uitstap", "GerealiseerdeUitstap"),
                    (text_column, "Routedetail"),
                ]
            elif control_id == 5:
                header_map = [
                    ("datum", "Datum"),
                    ("route_nummer", "RouteNummer"),
                    ("route_naam", "RouteNaam"),
                    ("postcode_eerste", "Van"),
                    ("postcode_via", "Via"),
                    ("postcode_laatste", "Naar"),
                    (text_column, "Foutmelding"),
                    ("aantal_lopers", "Lopers"),
                    ("aantal_rollers", "Rollers"),
                ]
            elif control_id == 7:
                header_map = [
                    ("datum", "Datum"),
                    ("route_nummer", "Routenummer"),
                    ("kenteken", "Kenteken"),
                    (text_column, "Routedetail"),
                    ("voertuigtype", "Voertuigtype"),
                ]
            elif control_id == 9:
                header_map = [
                    ("datum", "Datum"),
                    ("klant_nummer", "KlantNummer"),
                    ("reiziger_naam", "ReizigerNaam"),
                    ("route_nummer", "RouteNummer"),
                    ("locatie_van", "Locatie van"),
                    ("postcode_van", "Postcode van"),
                    ("locatie_naar", "Locatie naar"),
                    ("postcode_naar", "Postcode naar"),
                    ("bestelde_vertrektijd", "Besteld vertrek"),
                    ("bestelde_aankomsttijd", "Besteld aankomst"),
                    ("gerealiseerde_instap_tijd", "Instap"),
                    ("gerealiseerde_uitstap_tijd", "Uitstap"),
                    (text_column, "Tekst"),
                    (control_value_column, "Controlewaarde"),
                    (threshold_column, "Drempelwaarde"),
                ]
            elif control_id == 14:
                header_map = [
                    ("datum", "Datum"),
                    ("kenteken", "Kenteken"),
                    ("route_nummer", "RouteNummer"),
                    ("route_naam", "RouteNaam"),
                    ("aantal_lopers", "Lopers"),
                    ("aantal_rollers", "Rollers"),
                    ("richting", "Richting"),
                    ("geplande_start_tijd", "Rit plan instap"),
                    ("geplande_uitstap", "Rit plan uitstap"),
                    ("gerealiseerde_start_tijd", "Rit realisatie instap"),
                    ("gerealiseerde_uitstap", "Rit realisatie uitstap"),
                    ("vervoerder", "Vervoerder"),
                    (text_column, "Tekst"),
                    (control_value_column, "Controlewaarde"),
                    (threshold_column, "Drempelwaarde"),
                ]
            elif control_id == 15:
                header_map = [
                    ("datum", "Datum"),
                    ("route_nummer", "Routenummer"),
                    ("route_naam", "Routenaam"),
                    ("kenteken", "Kenteken"),
                    ("postcode_eerste", "PostcodeEerste"),
                    ("postcode_via", "PostcodeVia"),
                    ("postcode_laatste", "PostcodeLaatste"),
                    (control_value_column, "Minuten leeg"),
                ]
            elif control_id == 18:
                header_map = [
                    ("datum", "Datum"),
                    ("klant_nummer", "KlantNummer"),
                    ("reiziger_naam", "ReizigerNaam"),
                    ("route_nummer", "RouteNummer"),
                    ("locatie_van", "Locatie van"),
                    ("straat_van", "Straat van"),
                    ("huisnummer_van", "Huisnummer van"),
                    ("postcode_van", "Postcode van"),
                    ("plaats_van", "Plaats van"),
                    ("locatie_naar", "Locatie naar"),
                    ("straat_naar", "Straat naar"),
                    ("huisnummer_naar", "Huisnummer naar"),
                    ("postcode_naar", "Postcode naar"),
                    ("plaats_naar", "Plaats naar"),
                    (text_column, "Omschrijving fout"),
                ]
            elif control_id == 22:
                header_map = [
                    ("datum", "Datum"),
                    ("route_nummer", "Routenummer"),
                    ("reiziger_naam", "Reizigersnaam"),
                    ("gerealiseerde_instap_tijd", "Gerealiseerde instaptijd"),
                    ("gerealiseerde_uitstap_tijd", "Gerealiseerde uitstaptijd"),
                    ("kenteken", "Kenteken"),
                    ("richting", "Richting"),
                    ("route_naam", "Routenaam"),
                    (text_column, "Medepassagiers"),
                ]
            elif control_id == 23:
                header_map = [
                    ("datum", "Datum"),
                    ("klant_nummer", "Klantnummer"),
                    ("reiziger_naam", "Reizigersnaam"),
                    ("richting", "Richting"),
                    ("status_rit", "StatusRit"),
                    (text_column, "Tekst_23"),
                ]
            elif control_id in {2, 16, 17, 19}:
                header_map = [
                    ("datum", "Datum"),
                    ("klant_nummer", "KlantNummer"),
                    ("reiziger_naam", "ReizigerNaam"),
                    ("route_nummer", "RouteNummer"),
                    ("locatie_van", "Locatie van"),
                    ("locatie_naar", "Locatie naar"),
                    ("bestelde_vertrektijd", "Besteld vertrek"),
                    ("bestelde_aankomsttijd", "Besteld aankomst"),
                    (text_column, "Tekst"),
                    (control_value_column, "Controlewaarde"),
                    (threshold_column, "Drempelwaarde"),
                ]
                if control_id != 2:
                    header_map.insert(5, ("postcode_van", "Postcode van"))
                    header_map.insert(7, ("postcode_naar", "Postcode naar"))
                    header_map.insert(10, ("geplande_instap_tijd", "Instap"))
                    header_map.insert(11, ("geplande_uitstap_tijd", "Uitstap"))
                    header_map.insert(12, ("netto_instap", "Netto instap"))
                    header_map.insert(13, ("netto_uitstap", "Netto uitstap"))
                    header_map.insert(14, ("vervoerder", "Vervoerder"))
                else:
                    header_map.insert(8, ("gerealiseerde_instap_tijd", "Gerealiseerde instap"))
                    header_map.insert(9, ("gerealiseerde_uitstap_tijd", "Gerealiseerde uitstap"))
            elif control_id == 1001:
                header_map = [
                    ("rit_datum", "RitDatum"),
                    ("klant_nummer", "KlantNummer"),
                    ("klantnaam", "Klantnaam"),
                    ("plaats_van", "Gemeentecode"),
                    (text_column, "Afwijking"),
                    ("rit_status", "RitStatus"),
                    ("ritnummer", "Ritnummer"),
                ]
            elif control_id == 1002:
                header_map = [
                    ("rit_datum", "RitDatum"),
                    ("klant_nummer", "KlantNummer"),
                    ("klantnaam", "Klantnaam"),
                    ("gerealiseerde_instap_tijd", "Instaptijd"),
                    ("gerealiseerde_uitstap_tijd", "Uitstaptijd"),
                    ("plaats_van", "Gemeentecode"),
                    (text_column, "Afwijking"),
                    ("rit_status", "RitStatus"),
                    ("ritnummer", "Ritnummer"),
                ]
            elif control_id == 1003:
                header_map = [
                    ("rit_datum", "RitDatum"),
                    ("klant_nummer", "KlantNummer"),
                    ("klantnaam", "Klantnaam"),
                    ("gerealiseerde_instap_tijd", "Instaptijd"),
                    ("gerealiseerde_uitstap_tijd", "Uitstaptijd"),
                    ("plaats_van", "Gemeentecode"),
                    (text_column, "Afwijking"),
                    ("rit_status", "RitStatus"),
                    ("kenteken", "Kenteken"),
                    ("ritnummer", "Ritnummer"),
                ]
            elif control_id == 1007:
                header_map = [
                    ("rit_datum", "RitDatum"),
                    ("klant_nummer", "KlantNummer"),
                    ("klantnaam", "Klantnaam"),
                    ("gerealiseerde_instap_tijd", "Instaptijd"),
                    ("gerealiseerde_uitstap_tijd", "Uitstaptijd"),
                    ("plaats_van", "Gemeentecode"),
                    (text_column, "Afwijking"),
                    ("rit_status", "RitStatus"),
                    ("ritnummer", "Ritnummer"),
                ]
            elif control_id == 1008:
                header_map = [
                    ("rit_datum", "RitDatum"),
                    ("bestelde_vertrektijd", "Besteld"),
                    ("klant_nummer", "KlantNummer"),
                    ("klantnaam", "Klantnaam"),
                    ("postcode_van", "Van"),
                    ("postcode_naar", "Naar"),
                    (text_column, "Medepassagiers"),
                ]
            elif entity == "route":
                header_map = [
                    ("datum", "Datum"),
                    ("kenteken", "Kenteken"),
                    ("route_nummer", "RouteNummer"),
                    ("route_naam", "RouteNaam"),
                    ("aantal_lopers", "Lopers"),
                    ("aantal_rollers", "Rollers"),
                    ("richting", "Richting"),
                    ("geplande_start_tijd", "Rit plan instap"),
                    ("geplande_uitstap", "Rit plan uitstap"),
                    ("gerealiseerde_start_tijd", "Rit realisatie instap"),
                    ("gerealiseerde_uitstap", "Rit realisatie uitstap"),
                    ("vervoerder", "Vervoerder"),
                    (result_column, "Resultaat"),
                    (text_column, "Tekst"),
                    (control_value_column, "Controlewaarde"),
                    (threshold_column, "Drempelwaarde"),
                ]
            else:
                header_map = [
                    ("datum", "Datum"),
                    ("klant_nummer", "KlantNummer"),
                    ("reiziger_naam", "ReizigerNaam"),
                    ("route_nummer", "RouteNummer"),
                    ("locatie_van", "Locatie van"),
                    ("postcode_van", "Postcode van"),
                    ("locatie_naar", "Locatie naar"),
                    ("postcode_naar", "Postcode naar"),
                    ("bestelde_vertrektijd", "Besteld vertrek"),
                    ("bestelde_aankomsttijd", "Besteld aankomst"),
                    ("geplande_instap_tijd", "Instap"),
                    ("geplande_uitstap_tijd", "Uitstap"),
                    ("netto_instap", "Netto instap"),
                    ("netto_uitstap", "Netto uitstap"),
                    ("vervoerder", "Vervoerder"),
                    (result_column, "Resultaat"),
                    (text_column, "Tekst"),
                    (control_value_column, "Controlewaarde"),
                    (threshold_column, "Drempelwaarde"),
                ]

            selected_columns = [column for column, _label in header_map if column in columns]
            headers = [label for column, label in header_map if column in columns]
            order_date_column = "datum" if "datum" in columns else "rit_datum" if "rit_datum" in columns else selected_columns[0]
            order_secondary_column = "vervoerder" if "vervoerder" in columns else selected_columns[1] if len(selected_columns) > 1 else selected_columns[0]

            detail_query = f"""
                SELECT {", ".join(selected_columns)}
                FROM read_parquet('{path_glob}')
                WHERE ({deviation_condition}) {filter_sql}
                ORDER BY {order_date_column}, {order_secondary_column}
                LIMIT {int(limit)} OFFSET {int(offset)}
            """
            rows = []
            for row in conn.execute(detail_query).fetchall():
                row = list(row)
                if entity == "rit":
                    if "locatie_van" in selected_columns:
                        row[selected_columns.index("locatie_van")] = self._strip_location_code(row[selected_columns.index("locatie_van")])
                    if "locatie_naar" in selected_columns:
                        row[selected_columns.index("locatie_naar")] = self._strip_location_code(row[selected_columns.index("locatie_naar")])
                formatted_row = [
                    self._format_cell(selected_columns[index], value)
                    for index, value in enumerate(row)
                ]
                rows.append(tuple(formatted_row))

            return (
                ControlReportSummary(
                    total_checked=total_checked or 0,
                    total_deviations=total_deviations or 0,
                    deviation_percentage=deviation_percentage,
                ),
                headers,
                rows,
                total_deviations or 0,
            )
