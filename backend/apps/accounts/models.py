from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db import models

from apps.core.models import TimeStampedModel


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    ANALYST = "analyst", "Analyst"
    VIEWER = "viewer", "Viewer"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.VIEWER)

    def __str__(self) -> str:
        return self.get_username()


class EmailLoginCode(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_login_codes")
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None
