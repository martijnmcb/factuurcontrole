from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django import forms

from apps.clients.models import Client, ClientAccess

from .models import User


class UserAdminForm(forms.ModelForm):
    clients = forms.ModelMultipleChoiceField(
        queryset=Client.objects.filter(is_active=True).order_by("name"),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple("clients", is_stacked=False),
        help_text="Select the clients this user may access.",
    )

    class Meta:
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["clients"].initial = Client.objects.filter(user_access__user=self.instance).order_by("name")

    def save(self, commit=True):
        user = super().save(commit=commit)
        self._selected_clients = list(self.cleaned_data.get("clients", []))
        return user

    def save_m2m(self):
        super().save_m2m()
        if not hasattr(self, "_selected_clients"):
            return
        user = self.instance
        selected_ids = {client.pk for client in self._selected_clients}
        ClientAccess.objects.filter(user=user).exclude(client_id__in=selected_ids).delete()
        existing_ids = set(ClientAccess.objects.filter(user=user).values_list("client_id", flat=True))
        ClientAccess.objects.bulk_create(
            [ClientAccess(user=user, client=client) for client in self._selected_clients if client.pk not in existing_ids]
        )


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserAdminForm
    fieldsets = DjangoUserAdmin.fieldsets + (("Platform", {"fields": ("role", "clients")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (("Platform", {"fields": ("role", "clients")}),)
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
