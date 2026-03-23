from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.views.generic import TemplateView

from apps.analytics.services import DuckDBAnalyticsService
from apps.clients.models import Client
from apps.clients.services import get_accessible_clients


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clients"] = get_accessible_clients(self.request.user)
        return context


class ClientContextMixin(LoginRequiredMixin):
    analytics_service_class = DuckDBAnalyticsService

    def get_client(self) -> Client:
        client = get_accessible_clients(self.request.user).filter(slug=self.kwargs["slug"]).first()
        if not client:
            raise Http404("Client not found")
        return client

    def analytics_service(self) -> DuckDBAnalyticsService:
        return self.analytics_service_class()

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


class ClientDashboardView(ClientContextMixin, TemplateView):
    template_name = "dashboards/client_dashboard.html"

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
        return context


class DrilldownView(ClientContextMixin, TemplateView):
    template_name = "dashboards/drilldown.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        context["client"] = client
        context["available_run_ids"] = available_run_ids
        context["selected_run_id"] = selected_run_id
        context["rows"] = analytics.get_driftable_rows(client.slug, selected_run_id)
        context["executed_controls"] = analytics.get_executed_controls(client.slug, selected_run_id)
        return context


class ControlReportView(ClientContextMixin, TemplateView):
    template_name = "dashboards/control_1_report.html"

    def get_template_names(self):
        if int(self.kwargs["control_id"]) == 10:
            return ["dashboards/control_10_report.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        analytics = self.analytics_service()
        available_run_ids = self.get_available_run_ids(client)
        selected_run_id = self.get_selected_run_id(available_run_ids)
        control_id = int(self.kwargs["control_id"])
        context["client"] = client
        context["available_run_ids"] = available_run_ids
        context["selected_run_id"] = selected_run_id
        context["control_id"] = control_id
        context["implemented"] = control_id in {1, 8}
        if control_id == 1:
            summary, rows = analytics.get_control_1_report(client.slug, selected_run_id)
            context["summary"] = summary
            context["rows"] = rows
            context["control_title"] = "Controle 1 - Bestelling ook in SW?"
            context["control_explanation"] = (
                "Controle of er van een rit op de factuur ook een bestelling is in de schema's of losse ritten in SmartWheels."
            )
            context["template_variant"] = "control_1"
        elif control_id == 8:
            summary, rows = analytics.get_control_8_report(client.slug, selected_run_id)
            context["summary"] = summary
            context["rows"] = rows
            context["control_title"] = "Controle 8 - Overschrijden reistijd"
            context["control_explanation"] = (
                "Controle op ritten waarbij de geplande reistijd de toegestane maximale reistijd overschrijdt."
            )
            context["template_variant"] = "control_8"
        elif control_id == 10:
            selected_route_key = self.request.GET.get("route_key")
            summary, route_options, selected_route_key, actual_points, replanned_points, route_detail_rows = analytics.get_control_10_report(
                client.slug,
                selected_run_id,
                selected_route_key,
            )
            context["summary"] = summary
            context["route_options"] = route_options
            context["selected_route_key"] = selected_route_key
            context["actual_points"] = actual_points
            context["replanned_points"] = replanned_points
            context["route_detail_rows"] = route_detail_rows
            context["control_title"] = "Controle 10 - Routekaart (optimalisatie)"
            context["control_explanation"] = (
                "Vergelijk de werkelijke stopvolgorde met de herplande volgorde op basis van netto instap- en uitstaptijden."
            )
            context["template_variant"] = "control_10"
        else:
            context["summary"] = None
            context["rows"] = []
            context["control_title"] = f"Controle {control_id}"
            context["control_explanation"] = "Voor deze controle is de detailpagina nog niet uitgewerkt."
            context["template_variant"] = "placeholder"
        return context
