from django.urls import path

from .views import ClientDashboardView, ControlReportView, DashboardHomeView, DrilldownView

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="dashboard_home"),
    path("clients/<slug:slug>/", ClientDashboardView.as_view(), name="client_dashboard"),
    path("clients/<slug:slug>/drilldown/", DrilldownView.as_view(), name="client_drilldown"),
    path("clients/<slug:slug>/controls/<int:control_id>/", ControlReportView.as_view(), name="control_report"),
]
