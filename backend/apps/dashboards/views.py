from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from urllib.parse import urlencode
import csv
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from apps.analytics.services import DuckDBAnalyticsService
from apps.clients.models import Client
from apps.clients.services import get_accessible_clients
from apps.sync_jobs.services import SyncOrchestrator
from apps.sync_jobs.models import SyncRun


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clients"] = get_accessible_clients(self.request.user)
        return context


class ClientContextMixin(LoginRequiredMixin):
    analytics_service_class = DuckDBAnalyticsService
    page_size = 100

    def get_client(self) -> Client:
        client = get_accessible_clients(self.request.user).filter(slug=self.kwargs["slug"]).first()
        if not client:
            raise Http404("Client not found")
        return client

    def analytics_service(self) -> DuckDBAnalyticsService:
        return self.analytics_service_class()

    def get_sync_orchestrator(self) -> SyncOrchestrator:
        return SyncOrchestrator()

    def can_refresh_client(self, client: Client) -> bool:
        role = getattr(self.request.user, "role", "")
        return bool(self.request.user.is_superuser or role in {"admin", "analyst"})

    def serialize_sync_run(self, sync_run: SyncRun | None) -> dict | None:
        if sync_run is None:
            return None
        progress = (sync_run.metadata or {}).get("progress", {})
        return {
            "id": sync_run.id,
            "status": sync_run.status,
            "started_at": sync_run.started_at.isoformat() if sync_run.started_at else None,
            "finished_at": sync_run.finished_at.isoformat() if sync_run.finished_at else None,
            "records_synced": sync_run.records_synced,
            "message": sync_run.message,
            "is_running": sync_run.status == "started",
            "progress": progress,
        }

    def get_available_run_ids(self, client: Client) -> list[int]:
        return self.analytics_service().get_current_run_ids(client.slug)

    def get_selected_run_id(self, available_run_ids) -> int | None:
        requested = self.request.GET.get("stuurtabel_id")
        valid_ids = [option.stuurtabel_id for option in available_run_ids]
        if requested:
            try:
                requested_id = int(requested)
            except ValueError:
                requested_id = None
            if requested_id in valid_ids:
                return requested_id
        return available_run_ids[0].stuurtabel_id if available_run_ids else None

    def get_page_number(self) -> int:
        try:
            page = int(self.request.GET.get("page", "1"))
        except ValueError:
            page = 1
        return max(1, page)

    def get_offset(self) -> int:
        return (self.get_page_number() - 1) * self.page_size

    def add_pagination_context(self, context, total_rows: int):
        page = self.get_page_number()
        total_pages = max(1, ((total_rows - 1) // self.page_size) + 1) if total_rows else 1
        query = self.request.GET.copy()
        if "page" in query:
            query.pop("page")
        context["page_size"] = self.page_size
        context["page"] = page
        context["total_rows"] = total_rows
        context["total_pages"] = total_pages
        context["has_previous"] = page > 1
        context["has_next"] = page < total_pages
        context["previous_page"] = page - 1
        context["next_page"] = page + 1
        context["pagination_query"] = urlencode(query, doseq=True)
        return context

    def format_minutes_label(self, minutes: int | None) -> str:
        if minutes is None:
            return "n.v.t."
        hours = minutes // 60
        remainder = minutes % 60
        if hours:
            return f"{hours}u {remainder:02d}m"
        return f"{remainder} min"

    def get_executed_control_description(self, executed_controls, control_id: int) -> str | None:
        for control in executed_controls:
            if control.control_id is None or int(control.control_id) != int(control_id):
                continue
            if " - " in control.label:
                return control.label.split(" - ", 1)[1].strip()
            return control.label.strip()
        return None

    def apply_control_content(
        self,
        context,
        analytics: DuckDBAnalyticsService,
        control_id: int,
        soortvervoer: str | None,
        executed_control_description: str | None,
        default_title: str,
        default_explanation: str,
    ):
        content = analytics.get_control_content(control_id, soortvervoer)
        context["control_title"] = (
            content.title_override
            if content and content.title_override
            else default_title
        )
        context["control_explanation"] = (
            content.explanation
            if content and content.explanation
            else content.short_description
            if content and content.short_description
            else executed_control_description
            if executed_control_description
            else default_explanation
        )
        context["control_short_description"] = content.short_description if content and content.short_description else executed_control_description
        context["control_content"] = content
        return context

    def _excel_column_name(self, index: int) -> str:
        name = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def _xlsx_sheet_xml(self, headers, rows) -> str:
        def cell_xml(ref: str, value) -> str:
            if value is None:
                text = ""
            else:
                text = str(value)
            return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'

        all_rows = [headers, *[list(row) for row in rows]]
        xml_rows = []
        for row_index, row in enumerate(all_rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                ref = f"{self._excel_column_name(col_index)}{row_index}"
                cells.append(cell_xml(ref, value))
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            '</worksheet>'
        )

    def _xlsx_workbook_response(self, filename: str, sheets):
        workbook_sheets = []
        workbook_rels = []
        content_overrides = []
        sheet_files = []

        for index, sheet in enumerate(sheets, start=1):
            workbook_sheets.append(
                f'<sheet name="{escape(sheet["name"][:31])}" sheetId="{index}" r:id="rId{index}"/>'
            )
            workbook_rels.append(
                '<Relationship '
                f'Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
            content_overrides.append(
                '<Override '
                f'PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            sheet_files.append((f"xl/worksheets/sheet{index}.xml", self._xlsx_sheet_xml(sheet["headers"], sheet["rows"])))

        workbook_rels.append(
            '<Relationship Id="rId999" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
        )

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(workbook_sheets)}</sheets>'
            '</workbook>'
        )
        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(workbook_rels)}'
            '</Relationships>'
        )
        root_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>'
        )
        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f'{"".join(content_overrides)}'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", root_rels_xml)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            archive.writestr("xl/styles.xml", styles_xml)
            for path, xml in sheet_files:
                archive.writestr(path, xml)

        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def get_control_export_bundle(self, analytics: DuckDBAnalyticsService, client_slug: str, selected_run_id: int | None, control_id: int):
        definition = analytics.get_control_definition(control_id)
        title = definition["title"]

        if control_id == 1:
            summary, rows, _ = analytics.get_control_1_report(client_slug, selected_run_id, 1_000_000, 0)
            headers = [
                "Datum", "KlantNummer", "ReizigerNaam", "Locatie van", "Postcode van", "Vertrek",
                "Locatie naar", "Postcode naar", "Aankomst", "Match", "Ritprijs", "StatusRit",
                "Routenummer", "Perceelvervoerder",
            ]
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}
        if control_id == 8:
            summary, rows, _ = analytics.get_control_8_report(client_slug, selected_run_id, 1_000_000, 0)
            headers = [
                "Ritdatum", "KlantNummer", "ReizigerNaam", "Locatie van", "Locatie naar",
                "Geplande Instap", "Geplande Uitstap", "Max reistijd", "Geplande reistijd",
                "Overschrijding", "Realisatie in", "Realisatie uit", "RealReisTijd",
            ]
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}
        if control_id == 10:
            (
                summary,
                route_options,
                _selected_route_key,
                _actual_points,
                _replanned_points,
                _route_detail_rows,
                _total,
                _actual_duration_minutes,
                _replanned_duration_minutes,
            ) = analytics.get_control_10_report(
                client_slug,
                selected_run_id,
                None,
                1,
                0,
            )
            headers = [
                "RouteKey", "Datum", "KlantNummer", "ReizigerNaam", "Geplande instap", "Locatie van",
                "Postcode van", "Geplande uitstap", "Locatie naar", "Postcode naar", "Geplande reistijd",
                "Besteld aankomst", "Besteld vertrek", "Netto instap", "Netto uitstap",
                "Herplan instap", "Herplan uitstap", "Vervoerder",
            ]
            rows = []
            for route in route_options:
                (
                    _summary,
                    _opts,
                    _selected,
                    _actual,
                    _replanned,
                    detail_rows,
                    _count,
                    _actual_duration_minutes,
                    _replanned_duration_minutes,
                ) = analytics.get_control_10_report(
                    client_slug,
                    selected_run_id,
                    route.route_key,
                    1_000_000,
                    0,
                )
                rows.extend([(route.route_key, *row) for row in detail_rows])
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}
        if control_id == 11:
            summary, _classified_rides, _class_rows, vehicle_rows, _kilometer_available, _total = analytics.get_control_11_report(
                client_slug,
                selected_run_id,
                1_000_000,
                0,
            )
            headers = ["Kenteken", "Emissieklasse", "Inzetdagen", "Routes", "Ritten"]
            rows = [(row.kenteken, row.emission_class, row.inzetdagen, row.routes, row.rides) for row in vehicle_rows]
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}
        if control_id == 1004:
            summary, emission_classes, weekly_rows, trip_rows, distance_rows = analytics.get_control_1004_report(
                client_slug,
                selected_run_id,
            )
            headers = ["Type", "Dimensie", *[str(emission_class) for emission_class in emission_classes], "Totaal", "Percentage"]
            rows = []
            for row in weekly_rows:
                rows.append(("Voertuigen per ISO week", row["label"], *row["values"], row["total"], ""))
            for row in trip_rows:
                rows.append(("Ritten per emissieniveau", row["emission_class"], *["" for _ in emission_classes], row["trips"], f'{row["percentage"]}%'))
            for row in distance_rows:
                rows.append(("Afgelegde reizigers kilometers per emissieniveau", row["emission_class"], *["" for _ in emission_classes], row["distance"], f'{row["percentage"]}%'))
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}
        if control_id == 1005:
            summary, fuel_types, weekly_rows, trip_rows, distance_rows = analytics.get_control_1005_report(
                client_slug,
                selected_run_id,
            )
            headers = ["Type", "Dimensie", *[str(fuel_type) for fuel_type in fuel_types], "Totaal", "Percentage"]
            rows = []
            for row in weekly_rows:
                rows.append(("Voertuigen per ISO week", row["label"], *row["values"], row["total"], ""))
            for row in trip_rows:
                rows.append(("Ritten per brandstoftype", row["fuel_type"], *["" for _ in fuel_types], row["trips"], f'{row["percentage"]}%'))
            for row in distance_rows:
                rows.append(("Afgelegde reizigers kilometers per brandstoftype", row["fuel_type"], *["" for _ in fuel_types], row["distance"], f'{row["percentage"]}%'))
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}
        if control_id in {2, 3, 7, 9, 12, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 1001, 1002, 1003, 1007, 1008}:
            summary, headers, rows, _ = analytics.get_generic_control_report(
                client_slug,
                selected_run_id,
                control_id,
                1_000_000,
                0,
            )
            return {"summary": summary, "headers": headers, "rows": rows, "title": title}

        return {
            "summary": None,
            "headers": ["Info"],
            "rows": [("Geen exportmapping beschikbaar voor deze controle.",)],
            "title": title,
        }


class ClientDashboardView(ClientContextMixin, TemplateView):
    template_name = "dashboards/client_dashboard.html"

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "xlsx":
            return self.export_dashboard_workbook()
        return super().get(request, *args, **kwargs)

    def export_dashboard_workbook(self):
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        executed_controls = analytics.get_executed_controls(client.slug, selected_run_id)

        summary_headers = ["Control number", "Control name", "Total checked", "Total deviations", "Deviation %"]
        summary_rows = []
        sheets = []
        used_sheet_names = set()

        for control in executed_controls:
            if not analytics.is_deviation_control(control.control_id):
                continue
            bundle = self.get_control_export_bundle(analytics, client.slug, selected_run_id, int(control.control_id))
            control_name = control.label.split(" - ", 1)[1] if " - " in control.label else bundle["title"]
            summary = bundle["summary"]
            if summary is None:
                total_checked = 0
                total_deviations = 0
                deviation_percentage = 0.0
            else:
                total_checked = summary.total_checked
                total_deviations = summary.total_deviations
                deviation_percentage = summary.deviation_percentage
            summary_rows.append(
                (
                    control.control_id,
                    control_name,
                    total_checked,
                    total_deviations,
                    f"{deviation_percentage:.2f}%",
                )
            )

            sheet_name = f"control.{control.control_id}"
            if sheet_name in used_sheet_names:
                suffix = 2
                while f"{sheet_name}_{suffix}" in used_sheet_names:
                    suffix += 1
                sheet_name = f"{sheet_name}_{suffix}"
            used_sheet_names.add(sheet_name)
            sheets.append({"name": sheet_name, "headers": bundle["headers"], "rows": bundle["rows"]})

        workbook_sheets = [{"name": "summary", "headers": summary_headers, "rows": summary_rows}, *sheets]
        return self._xlsx_workbook_response(
            f"{client.slug}-dashboard-{selected_run_id}.xlsx",
            workbook_sheets,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        context["client"] = client
        context["available_run_ids"] = available_run_ids
        context["selected_run_id"] = selected_run_id
        context["metrics"] = analytics.get_dashboard_metrics(client.slug, selected_run_id)
        context["control_breakdown"] = analytics.get_control_breakdown(client.slug, selected_run_id)
        context["executed_controls"] = analytics.get_executed_controls(client.slug, selected_run_id)
        context["can_refresh_client"] = self.can_refresh_client(client)
        latest_sync = self.get_sync_orchestrator().get_latest_sync(client)
        context["latest_sync"] = latest_sync
        context["latest_sync_payload"] = self.serialize_sync_run(latest_sync)
        return context


class ClientRefreshView(ClientContextMixin, View):
    def post(self, request, *args, **kwargs):
        client = self.get_client()
        if not self.can_refresh_client(client):
            return HttpResponseForbidden("You are not allowed to refresh this client.")

        try:
            sync_run, started = self.get_sync_orchestrator().sync_client_async(client)
            if started:
                messages.success(request, f"Refresh started for {client.slug}. You can leave this page while it runs.")
            else:
                messages.info(request, f"A refresh for {client.slug} is already running.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Refresh failed for {client.slug}: {exc}")

        return redirect("client_dashboard", slug=client.slug)


class ClientRefreshStatusView(ClientContextMixin, View):
    def get(self, request, *args, **kwargs):
        client = self.get_client()
        latest_sync = self.get_sync_orchestrator().get_latest_sync(client)
        return JsonResponse({"sync_run": self.serialize_sync_run(latest_sync)})


class DrilldownView(ClientContextMixin, TemplateView):
    template_name = "dashboards/drilldown.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        page_size = self.page_size
        offset = self.get_offset()
        context["client"] = client
        context["available_run_ids"] = available_run_ids
        context["selected_run_id"] = selected_run_id
        rows, total_rows = analytics.get_driftable_rows(client.slug, selected_run_id, page_size, offset)
        context["rows"] = rows
        context["executed_controls"] = analytics.get_executed_controls(client.slug, selected_run_id)
        self.add_pagination_context(context, total_rows)
        return context


class ControlReportView(ClientContextMixin, TemplateView):
    template_name = "dashboards/control_1_report.html"

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") in {"csv", "xlsx"}:
            return self.export_table()
        return super().get(request, *args, **kwargs)

    def _csv_response(self, filename: str, headers, rows):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(list(row))
        return response

    def _excel_column_name(self, index: int) -> str:
        name = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def _xlsx_sheet_xml(self, headers, rows) -> str:
        def cell_xml(ref: str, value) -> str:
            if value is None:
                text = ""
            else:
                text = str(value)
            return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'

        all_rows = [headers, *[list(row) for row in rows]]
        xml_rows = []
        for row_index, row in enumerate(all_rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                ref = f"{self._excel_column_name(col_index)}{row_index}"
                cells.append(cell_xml(ref, value))
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            '</worksheet>'
        )

    def _xlsx_response(self, filename: str, headers, rows, sheet_name: str = "Report"):
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{escape(sheet_name[:31])}" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        )
        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            '</Relationships>'
        )
        root_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>'
        )
        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", root_rels_xml)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            archive.writestr("xl/styles.xml", styles_xml)
            archive.writestr("xl/worksheets/sheet1.xml", self._xlsx_sheet_xml(headers, rows))

        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _respond_export(self, filename_base: str, headers, rows, sheet_name: str = "Report"):
        export_format = self.request.GET.get("export", "csv")
        if export_format == "xlsx":
            return self._xlsx_response(f"{filename_base}.xlsx", headers, rows, sheet_name)
        return self._csv_response(f"{filename_base}.csv", headers, rows)

    def export_table(self):
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        control_id = int(self.kwargs["control_id"])
        table_name = self.request.GET.get("table", "main")

        if control_id == 1:
            _summary, rows, total_rows = analytics.get_control_1_report(client.slug, selected_run_id, 1_000_000, 0)
            headers = [
                "Datum",
                "KlantNummer",
                "ReizigerNaam",
                "Locatie van",
                "Postcode van",
                "Vertrek",
                "Locatie naar",
                "Postcode naar",
                "Aankomst",
                "Match",
                "Ritprijs",
                "StatusRit",
                "Routenummer",
                "Perceelvervoerder",
            ]
            return self._respond_export(f"{client.slug}-control-1-{selected_run_id}", headers, rows, "Control 1")
        if control_id == 5:
            _summary, rows, _total_rows = analytics.get_control_5_report(client.slug, selected_run_id, 1_000_000, 0)
            headers = ["Datum", "RouteNummer", "RouteNaam", "Van", "Via", "Naar", "Foutmelding", "Lopers", "Rollers"]
            export_rows = [
                (
                    row["route_date_label"],
                    row["route_nummer"],
                    row["route_naam"],
                    row["van"],
                    row["via"],
                    row["naar"],
                    row["foutmelding"],
                    row["lopers"],
                    row["rollers"],
                )
                for row in rows
            ]
            return self._respond_export(f"{client.slug}-control-5-{selected_run_id}", headers, export_rows, "Control 5")
        if control_id == 8:
            _summary, rows, total_rows = analytics.get_control_8_report(client.slug, selected_run_id, 1_000_000, 0)
            headers = [
                "Ritdatum",
                "KlantNummer",
                "ReizigerNaam",
                "Locatie van",
                "Locatie naar",
                "Geplande Instap",
                "Geplande Uitstap",
                "Max reistijd",
                "Geplande reistijd",
                "Overschrijding",
                "Realisatie in",
                "Realisatie uit",
                "RealReisTijd",
            ]
            return self._respond_export(f"{client.slug}-control-8-{selected_run_id}", headers, rows, "Control 8")
        if control_id == 10:
            selected_route_key = self.request.GET.get("route_key")
            _summary, _route_options, selected_route_key, _actual_points, _replanned_points, route_detail_rows, _total_rows = analytics.get_control_10_report(
                client.slug,
                selected_run_id,
                selected_route_key,
                1_000_000,
                0,
            )
            headers = [
                "Datum",
                "KlantNummer",
                "ReizigerNaam",
                "Geplande instap",
                "Locatie van",
                "Postcode van",
                "Geplande uitstap",
                "Locatie naar",
                "Postcode naar",
                "Geplande reistijd",
                "Besteld aankomst",
                "Besteld vertrek",
                "Netto instap",
                "Netto uitstap",
                "Herplan instap",
                "Herplan uitstap",
                "Vervoerder",
            ]
            route_suffix = selected_route_key or "route"
            return self._respond_export(
                f"{client.slug}-control-10-{selected_run_id}-{route_suffix}",
                headers,
                route_detail_rows,
                "Control 10",
            )
        if control_id == 11:
            _summary, _classified_rides, class_rows, vehicle_rows, _kilometer_available, _total_rows = analytics.get_control_11_report(
                client.slug,
                selected_run_id,
                1_000_000,
                0,
            )
            if table_name == "classes":
                headers = ["Emissieklasse", "Aantal voertuigen", "Aandeel ritten", "clientKM", "Aandeel clientKM"]
                rows = [
                    (
                        row.emission_class,
                        row.vehicles,
                        row.ride_percentage,
                        row.client_km,
                        row.client_km_percentage,
                    )
                    for row in class_rows
                ]
                return self._respond_export(f"{client.slug}-control-11-classes-{selected_run_id}", headers, rows, "Control 11 Classes")
            headers = ["Kenteken", "Emissieklasse", "Inzetdagen", "Routes", "Ritten"]
            rows = [
                (row.kenteken, row.emission_class, row.inzetdagen, row.routes, row.rides)
                for row in vehicle_rows
            ]
            return self._respond_export(f"{client.slug}-control-11-vehicles-{selected_run_id}", headers, rows, "Control 11 Vehicles")
        if control_id == 12:
            _summary, _classified_rides, fuel_types, daily_rows, monthly_rows = analytics.get_control_12_report(
                client.slug,
                selected_run_id,
            )
            if table_name == "months":
                headers = ["Maand"]
                for fuel_type in fuel_types:
                    headers.extend([f"{fuel_type} aantal", f"{fuel_type} %"])
                headers.append("Totaal")
                rows = []
                for row in monthly_rows:
                    export_row = [row["label"]]
                    for cell in row["cells"]:
                        export_row.extend([cell["rides"], cell["percentage"]])
                    export_row.append(row["total"])
                    rows.append(tuple(export_row))
                return self._respond_export(f"{client.slug}-control-12-months-{selected_run_id}", headers, rows, "Control 12 Months")

            headers = ["Datum"]
            for fuel_type in fuel_types:
                headers.extend([f"{fuel_type} aantal", f"{fuel_type} %"])
            headers.append("Totaal")
            rows = []
            for row in daily_rows:
                export_row = [row["label"]]
                for cell in row["cells"]:
                    export_row.extend([cell["rides"], cell["percentage"]])
                export_row.append(row["total"])
                rows.append(tuple(export_row))
            return self._respond_export(f"{client.slug}-control-12-{selected_run_id}", headers, rows, "Control 12")
        if control_id == 13:
            _summary, report_rows, totals, _age_distribution = analytics.get_control_13_report(client.slug, selected_run_id)
            headers = ["Kenteken", "Inzetdagen", "Vervoerde passagiers", "Drempelwaarde", "Controlewaarde", "Type", "inrichting"]
            rows = [
                (
                    row["kenteken"],
                    row["inzetdagen"],
                    row["vervoerde_passagiers"],
                    row["drempelwaarde"],
                    row["controlewaarde"],
                    row["type"],
                    row["inrichting"],
                )
                for row in report_rows
            ]
            rows.append(("Totaal", totals["inzetdagen"], totals["passagiers"], "", "", "", ""))
            return self._respond_export(f"{client.slug}-control-13-{selected_run_id}", headers, rows, "Control 13")
        if control_id == 1006:
            _summary, report_rows, totals, _age_distribution = analytics.get_control_1006_report(client.slug, selected_run_id)
            headers = ["Kenteken", "Inzetdagen", "Vervoerde passagiers", "Drempelwaarde", "Controlewaarde", "Type", "inrichting"]
            rows = [
                (
                    row["kenteken"],
                    row["inzetdagen"],
                    row["vervoerde_passagiers"],
                    row["drempelwaarde"],
                    row["controlewaarde"],
                    row["type"],
                    row["inrichting"],
                )
                for row in report_rows
            ]
            rows.append(("Totaal", totals["inzetdagen"], totals["passagiers"], "", "", "", ""))
            return self._respond_export(f"{client.slug}-control-1006-{selected_run_id}", headers, rows, "Control 1006")
        if control_id == 20:
            _summary, _chart_points, table_rows, _monthly_chart_points = analytics.get_control_20_report(client.slug, selected_run_id)
            headers = ["Datum", "Aantal ritten", "Gewogen kosten per rit"]
            rows = [
                (row["datum"], row["n_ritten"], row["kosten_rit"])
                for row in table_rows
            ]
            return self._respond_export(f"{client.slug}-control-20-{selected_run_id}", headers, rows, "Control 20")
        if control_id == 1004:
            _summary, emission_classes, weekly_rows, trip_rows, distance_rows = analytics.get_control_1004_report(
                client.slug,
                selected_run_id,
            )
            if table_name == "trips":
                headers = ["Emissieklasse", "Aantal ritten", "Aandeel ritten %"]
                rows = [(row["emission_class"], row["trips"], row["percentage"]) for row in trip_rows]
                return self._respond_export(f"{client.slug}-control-1004-trips-{selected_run_id}", headers, rows, "Control 1004 Trips")
            if table_name == "distance":
                headers = ["Emissieklasse", "Som afstand direct", "Aandeel afstand %"]
                rows = [(row["emission_class"], row["distance"], row["percentage"]) for row in distance_rows]
                return self._respond_export(f"{client.slug}-control-1004-distance-{selected_run_id}", headers, rows, "Control 1004 Distance")
            headers = ["Weeknummer", *emission_classes, "Totaal"]
            rows = [(row["label"], *row["values"], row["total"]) for row in weekly_rows]
            return self._respond_export(f"{client.slug}-control-1004-weeks-{selected_run_id}", headers, rows, "Control 1004 Weeks")
        if control_id == 1005:
            _summary, fuel_types, weekly_rows, trip_rows, distance_rows = analytics.get_control_1005_report(
                client.slug,
                selected_run_id,
            )
            if table_name == "trips":
                headers = ["Brandstof", "Aantal ritten", "Aandeel ritten %"]
                rows = [(row["fuel_type"], row["trips"], row["percentage"]) for row in trip_rows]
                return self._respond_export(f"{client.slug}-control-1005-trips-{selected_run_id}", headers, rows, "Control 1005 Trips")
            if table_name == "distance":
                headers = ["Brandstof", "Afgelegde reizigers kilometers", "Aandeel afstand %"]
                rows = [(row["fuel_type"], row["distance"], row["percentage"]) for row in distance_rows]
                return self._respond_export(f"{client.slug}-control-1005-distance-{selected_run_id}", headers, rows, "Control 1005 Distance")
            headers = ["Weeknummer", *fuel_types, "Totaal"]
            rows = [(row["label"], *row["values"], row["total"]) for row in weekly_rows]
            return self._respond_export(f"{client.slug}-control-1005-weeks-{selected_run_id}", headers, rows, "Control 1005 Weeks")
        if control_id in {2, 3, 7, 9, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 1001, 1002, 1003, 1006, 1007, 1008}:
            _summary, headers, rows, _total_rows = analytics.get_generic_control_report(
                client.slug,
                selected_run_id,
                control_id,
                1_000_000,
                0,
            )
            return self._respond_export(f"{client.slug}-control-{control_id}-{selected_run_id}", headers, rows, f"Control {control_id}")

        raise Http404("Export not available for this control")

    def get_template_names(self):
        if int(self.kwargs["control_id"]) == 10:
            return ["dashboards/control_10_report.html"]
        if int(self.kwargs["control_id"]) == 11:
            return ["dashboards/control_11_report.html"]
        if int(self.kwargs["control_id"]) == 12:
            return ["dashboards/control_12_report.html"]
        if int(self.kwargs["control_id"]) == 13:
            return ["dashboards/control_13_report.html"]
        if int(self.kwargs["control_id"]) == 1006:
            return ["dashboards/control_13_report.html"]
        if int(self.kwargs["control_id"]) == 20:
            return ["dashboards/control_20_report.html"]
        if int(self.kwargs["control_id"]) == 1004:
            return ["dashboards/control_1004_report.html"]
        if int(self.kwargs["control_id"]) == 1005:
            return ["dashboards/control_1005_report.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        control_id = int(self.kwargs["control_id"])
        selected_run = analytics.get_run_option(client.slug, selected_run_id) if selected_run_id is not None else None
        selected_soortvervoer = selected_run.soortvervoer if selected_run else None
        page_size = self.page_size
        offset = self.get_offset()
        context["client"] = client
        context["available_run_ids"] = available_run_ids
        context["selected_run_id"] = selected_run_id
        context["control_id"] = control_id
        definition = analytics.get_control_definition(control_id)
        context["implemented"] = control_id in {1, 4, 8, 10, 11, 12, 13, 20, 1004, 1005, 1006} or control_id in {2, 3, 5, 7, 9, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 1001, 1002, 1003, 1007, 1008}
        executed_controls = [control for control in analytics.get_executed_controls(client.slug, selected_run_id) if control.control_id is not None]
        executed_control_ids = [int(control.control_id) for control in executed_controls]
        executed_control_description = self.get_executed_control_description(executed_controls, control_id)
        if control_id in executed_control_ids:
            current_index = executed_control_ids.index(control_id)
            context["previous_control_id"] = executed_control_ids[current_index - 1] if current_index > 0 else None
            context["next_control_id"] = executed_control_ids[current_index + 1] if current_index + 1 < len(executed_control_ids) else None
        else:
            context["previous_control_id"] = None
            context["next_control_id"] = None
        previous_run, trend_points = analytics.get_control_trend(client.slug, control_id, selected_run_id, 6)
        previous_point = next(
            (point for point in trend_points if previous_run is not None and point.stuurtabel_id == previous_run.stuurtabel_id),
            None,
        )
        context["previous_run"] = previous_run
        context["previous_trend_point"] = previous_point
        context["trend_points"] = trend_points
        context["trend_max_deviations"] = max((point.total_deviations for point in trend_points), default=0)
        if control_id == 1:
            summary, rows, total_rows = analytics.get_control_1_report(client.slug, selected_run_id, page_size, offset)
            context["summary"] = summary
            context["rows"] = rows
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 1 - Bestelling ook in SW?",
                "Controle of er van een rit op de factuur ook een bestelling is in de schema's of losse ritten in SmartWheels.",
            )
            context["template_variant"] = "control_1"
            self.add_pagination_context(context, total_rows)
        elif control_id == 4:
            context["summary"] = None
            context["rows"] = []
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                definition["title"],
                "Dit is een interne controle om de individuele reistijden te bepalen. Deze controle geeft geen output.",
            )
            context["template_variant"] = "description_only"
        elif control_id == 5:
            summary, rows, total_rows = analytics.get_control_5_report(client.slug, selected_run_id, page_size, offset)
            context["summary"] = summary
            context["rows"] = rows
            context["control_entity_label"] = "routes"
            context["control_metric_label"] = definition["metric_label"]
            context["control5_route_detail_url"] = reverse("control_5_route_detail", kwargs={"slug": client.slug})
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                definition["title"],
                "Controle 5 detailweergave van routes waarbij de planning niet kon worden gemaakt.",
            )
            context["template_variant"] = "control_5"
            self.add_pagination_context(context, total_rows)
        elif control_id == 8:
            summary, rows, total_rows = analytics.get_control_8_report(client.slug, selected_run_id, page_size, offset)
            context["summary"] = summary
            context["rows"] = rows
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 8 - Overschrijden reistijd",
                "Controle op ritten waarbij de geplande reistijd de toegestane maximale reistijd overschrijdt.",
            )
            context["template_variant"] = "control_8"
            self.add_pagination_context(context, total_rows)
        elif control_id == 10:
            selected_route_key = self.request.GET.get("route_key")
            summary, route_options, selected_route_key, actual_points, replanned_points, route_detail_rows, total_rows, actual_duration_minutes, replanned_duration_minutes = analytics.get_control_10_report(
                client.slug,
                selected_run_id,
                selected_route_key,
                page_size,
                offset,
            )
            context["summary"] = summary
            context["route_options"] = route_options
            context["selected_route_key"] = selected_route_key
            context["actual_points"] = actual_points
            context["replanned_points"] = replanned_points
            context["route_detail_rows"] = route_detail_rows
            context["actual_duration_label"] = self.format_minutes_label(actual_duration_minutes)
            context["replanned_duration_label"] = self.format_minutes_label(replanned_duration_minutes)
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 10 - Routekaart (optimalisatie)",
                "Vergelijk de werkelijke stopvolgorde met de herplande volgorde op basis van netto instap- en uitstaptijden.",
            )
            context["template_variant"] = "control_10"
            self.add_pagination_context(context, total_rows)
        elif control_id == 11:
            summary, classified_rides, class_rows, vehicle_rows, kilometer_available, total_rows = analytics.get_control_11_report(
                client.slug,
                selected_run_id,
                page_size,
                offset,
            )
            context["summary"] = summary
            context["classified_rides"] = classified_rides
            context["class_rows"] = class_rows
            context["vehicle_rows"] = vehicle_rows
            context["kilometer_available"] = kilometer_available
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 11 - Emissieklasse voertuigen",
                "Per voertuig wordt via RDW de emissieklasse bepaald. Deze pagina toont de inzet van voertuigen per emissieklasse en, indien beschikbaar in de routegegevens, ook het aandeel kilometers per klasse.",
            )
            context["template_variant"] = "control_11"
            self.add_pagination_context(context, total_rows)
        elif control_id == 12:
            summary, classified_rides, fuel_types, daily_rows, monthly_rows = analytics.get_control_12_report(
                client.slug,
                selected_run_id,
            )
            context["summary"] = summary
            context["classified_rides"] = classified_rides
            context["fuel_types"] = fuel_types
            context["daily_rows"] = daily_rows
            context["monthly_rows"] = monthly_rows
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 12 - Brandstofsoort",
                "Overzicht per dag van het aantal en percentage van de gebruikte brandstofsoorten.",
            )
            context["template_variant"] = "control_12"
        elif control_id == 13:
            summary, report_rows, totals, age_distribution = analytics.get_control_13_report(client.slug, selected_run_id)
            context["summary"] = summary
            context["report_rows"] = report_rows
            context["totals"] = totals
            context["age_chart_labels"] = [row["label"] for row in age_distribution]
            context["age_chart_values"] = [row["value"] for row in age_distribution]
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 13",
                "Overzicht per kenteken van inzetdagen, vervoerde passagiers en de controlewaarden voor deze controle.",
            )
            context["template_variant"] = "control_13"
        elif control_id == 1006:
            summary, report_rows, totals, age_distribution = analytics.get_control_1006_report(client.slug, selected_run_id)
            context["summary"] = summary
            context["report_rows"] = report_rows
            context["totals"] = totals
            context["age_chart_labels"] = [row["label"] for row in age_distribution]
            context["age_chart_values"] = [row["value"] for row in age_distribution]
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 1006 - Leeftijd voertuigen VA ritten",
                "Overzicht per kenteken van inzetdagen, vervoerde passagiers en voertuigleeftijd voor VA-ritten.",
            )
            context["template_variant"] = "control_13"
        elif control_id == 20:
            summary, chart_points, table_rows, monthly_chart_points = analytics.get_control_20_report(client.slug, selected_run_id)
            context["summary"] = summary
            context["table_rows"] = table_rows
            context["cost_chart_labels"] = [point["label"] for point in chart_points]
            context["cost_chart_values"] = [point["value"] for point in chart_points]
            context["monthly_cost_chart_labels"] = [point["label"] for point in monthly_chart_points]
            context["monthly_cost_chart_values"] = [point["value"] for point in monthly_chart_points]
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 20 - Kosten per rit",
                "Overzicht van de kosten per rit op basis van kentallen_route, geplot per datum.",
            )
            context["template_variant"] = "control_20"
        elif control_id == 1004:
            summary, emission_classes, weekly_rows, trip_rows, distance_rows = analytics.get_control_1004_report(
                client.slug,
                selected_run_id,
            )
            context["summary"] = summary
            context["emission_classes"] = emission_classes
            context["weekly_rows"] = weekly_rows
            context["trip_rows"] = trip_rows
            context["distance_rows"] = distance_rows
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 1004 - Emissieklasse voertuigen VA ritten",
                "Overzicht van VA-voertuiginzet per emissieniveau, uitgesplitst naar ISO-week, aantal ritten en som van afstand_direct.",
            )
            context["template_variant"] = "control_1004"
        elif control_id == 1005:
            summary, fuel_types, weekly_rows, trip_rows, distance_rows = analytics.get_control_1005_report(
                client.slug,
                selected_run_id,
            )
            context["summary"] = summary
            context["fuel_types"] = fuel_types
            context["weekly_rows"] = weekly_rows
            context["trip_rows"] = trip_rows
            context["distance_rows"] = distance_rows
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                "Controle 1005 - Brandstof voertuigen VA ritten",
                "Overzicht van VA-voertuiginzet per brandstofsoort, uitgesplitst naar ISO-week, aantal ritten en afgelegde reizigers kilometers.",
            )
            context["template_variant"] = "control_1005"
        elif control_id in {2, 3, 5, 7, 9, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 1001, 1002, 1003, 1007, 1008}:
            summary, headers, rows, total_rows = analytics.get_generic_control_report(
                client.slug,
                selected_run_id,
                control_id,
                page_size,
                offset,
            )
            context["summary"] = summary
            context["generic_headers"] = headers
            context["rows"] = rows
            context["control_entity_label"] = "routes" if definition["entity"] == "route" else "ritten"
            context["control_metric_label"] = definition["metric_label"]
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                definition["title"],
                "Eerste versie van deze controlepagina op basis van het huidige Parquet-model en de Power BI layout. Businesslogica en kolomkeuze worden later per controle verder aangescherpt.",
            )
            context["template_variant"] = "generic"
            self.add_pagination_context(context, total_rows)
        else:
            context["summary"] = None
            context["rows"] = []
            self.apply_control_content(
                context,
                analytics,
                control_id,
                selected_soortvervoer,
                executed_control_description,
                f"Controle {control_id}",
                "Voor deze controle is de detailpagina nog niet uitgewerkt.",
            )
            context["template_variant"] = "placeholder"
        return context


class Control5RouteDetailView(ClientContextMixin, View):
    def get(self, request, *args, **kwargs):
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        route_nummer = request.GET.get("route_nummer", "").strip()
        route_date = request.GET.get("route_date", "").strip()
        if not route_nummer or not route_date:
            return JsonResponse({"error": "route_nummer and route_date are required"}, status=400)

        rows = analytics.get_control_5_route_detail(client.slug, selected_run_id, route_nummer, route_date)
        headers = [
            "Datum",
            "RouteNummer",
            "Bestelde Aankomst",
            "Bestelde Vertrek",
            "KlantNummer",
            "ReizigerNaam",
            "Locatie van",
            "plaats_van",
            "Locatie naar",
            "plaats_naar",
            "Plan Instap",
            "Plan Uitstap",
            "AfwezigheidsMelding",
        ]
        return JsonResponse(
            {
                "headers": headers,
                "rows": rows,
                "route_nummer": route_nummer,
                "route_date": route_date,
            }
        )
