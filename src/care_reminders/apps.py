from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

PLUGIN_NAME = "care_reminders"


class CareRemindersConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = _("Care reminders")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import care_reminders.signals  # noqa: F401
