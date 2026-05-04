from django.contrib import admin
from django.urls import include, path
from apps.accounts.views import LoginView, LogoutView, EmailVerificationView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/login/verify/", EmailVerificationView.as_view(), name="login_verify"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("", include("apps.dashboards.urls")),
]
