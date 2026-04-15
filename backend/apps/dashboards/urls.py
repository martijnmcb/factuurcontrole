from django.urls import path

from .views import ClientDashboardView, ClientRefreshStatusView, ClientRefreshView, ControlReportView, DashboardHomeView, DrilldownView

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="dashboard_home"),
    path("clients/<slug:slug>/", ClientDashboardView.as_view(), name="client_dashboard"),
    path("clients/<slug:slug>/refresh/", ClientRefreshView.as_view(), name="client_refresh"),
    path("clients/<slug:slug>/refresh-status/", ClientRefreshStatusView.as_view(), name="client_refresh_status"),
    path("clients/<slug:slug>/drilldown/", DrilldownView.as_view(), name="client_drilldown"),
    path("clients/<slug:slug>/controls/<int:control_id>/", ControlReportView.as_view(), name="control_report"),
]
