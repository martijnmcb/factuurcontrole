from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import Client

User = get_user_model()


def get_accessible_clients(user: User):
    if user.is_superuser or getattr(user, "role", "") == "admin":
        return Client.objects.filter(is_active=True)
    return Client.objects.filter(is_active=True, user_access__user=user).distinct()
