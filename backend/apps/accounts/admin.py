from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm
from django.contrib.admin.utils import flatten_fieldsets
from django import forms
from copy import deepcopy

from apps.clients.models import Client, ClientAccess

from .models import User


class ClientAccessAdminFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["clients"].initial = Client.objects.filter(user_access__user=self.instance).order_by("name")

    def save(self, commit=True):
        user = super().save(commit=commit)
        self._selected_clients = list(self.cleaned_data.get("clients", []))
        if commit:
            self.sync_clients()
        return user

    def sync_clients(self):
        if not hasattr(self, "_selected_clients"):
            return
        user = self.instance
        selected_ids = {client.pk for client in self._selected_clients}
        ClientAccess.objects.filter(user=user).exclude(client_id__in=selected_ids).delete()
        existing_ids = set(ClientAccess.objects.filter(user=user).values_list("client_id", flat=True))
        ClientAccess.objects.bulk_create(
            [ClientAccess(user=user, client=client) for client in self._selected_clients if client.pk not in existing_ids]
        )


class UserAdminForm(ClientAccessAdminFormMixin, forms.ModelForm):
    clients = forms.ModelMultipleChoiceField(
        queryset=Client.objects.filter(is_active=True).order_by("name"),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple("clients", is_stacked=False),
        help_text="Select the clients this user may access.",
    )

    class Meta:
        model = User
        fields = "__all__"


class UserAdminCreationForm(ClientAccessAdminFormMixin, AdminUserCreationForm):
    clients = forms.ModelMultipleChoiceField(
        queryset=Client.objects.filter(is_active=True).order_by("name"),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple("clients", is_stacked=False),
        help_text="Select the clients this user may access.",
    )

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserAdminForm
    add_form = UserAdminCreationForm
    fieldsets = DjangoUserAdmin.fieldsets + (("Platform", {"fields": ("role", "clients")}),)
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "usable_password", "password1", "password2"),
            },
        ),
        ("Platform", {"fields": ("email", "role", "clients")}),
    )
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    def get_form(self, request, obj=None, change=False, **kwargs):
        base_form = self.add_form if obj is None else self.form
        kwargs["form"] = base_form
        kwargs["fields"] = tuple(
            field_name
            for field_name in flatten_fieldsets(self.get_fieldsets(request, obj))
            if field_name != "clients"
        )
        form_class = admin.ModelAdmin.get_form(self, request, obj, change=change, **kwargs)
        if "clients" not in form_class.base_fields and "clients" in base_form.base_fields:
            form_class.base_fields["clients"] = deepcopy(base_form.base_fields["clients"])
        return form_class

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if hasattr(form, "sync_clients"):
            form.sync_clients()
