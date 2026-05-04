from django.db import models

from apps.core.models import TimeStampedModel


class ControlContent(TimeStampedModel):
    SOORTVERVOER_CHOICES = (
        ("", "Algemeen"),
        ("RG", "RG"),
        ("VA", "VA"),
    )

    control_id = models.IntegerField()
    soortvervoer = models.CharField(max_length=10, blank=True, choices=SOORTVERVOER_CHOICES, default="")
    title_override = models.CharField(max_length=255, blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    explanation = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["control_id", "soortvervoer"]
        constraints = [
            models.UniqueConstraint(
                fields=["control_id", "soortvervoer"],
                name="uniq_control_content_control_soortvervoer",
            )
        ]
        verbose_name = "Control content"
        verbose_name_plural = "Control content"

    def __str__(self) -> str:
        suffix = f" [{self.soortvervoer}]" if self.soortvervoer else ""
        return f"Controle {self.control_id}{suffix}"
