from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

from care_reminders.apps import PLUGIN_NAME

DAY_PART_TIMES = {
    "morning": "09:00",
    "noon": "13:00",
    "evening": "18:00",
    "night": "21:00",
}

DEFAULTS = {
    "TIME_ZONE": None,
    "DAY_PART_TIMES": DAY_PART_TIMES,
    "SNOOZE_MINUTES": 10,
    "OCCURRENCE_HORIZON_DAYS": 14,
    "ALARM_LOOKBACK_HOURS": 2,
    "ALARM_HORIZON_DAYS": 7,
    "ALARM_TOKEN_MAX_AGE": 14 * 24 * 60 * 60,
}


class PluginSettings:
    """Optional plug configs from PLUGIN_CONFIGS / env, then defaults."""

    def __init__(self, plugin_name: str, defaults: dict[str, Any]) -> None:
        self.plugin_name = plugin_name
        self.defaults = defaults
        self._cached_attrs: set[str] = set()

    def __getattr__(self, attr: str) -> Any:
        if attr not in self.defaults:
            raise AttributeError(f"Invalid setting: '{attr}'")

        val = self.defaults[attr]
        try:
            val = self.user_settings[attr]
        except KeyError:
            env = os.environ.get(f"CARE_REMINDERS_{attr}")
            if env is not None:
                val = env if not isinstance(val, int) else int(env)

        if attr == "TIME_ZONE" and not val:
            val = getattr(settings, "TIME_ZONE", "Asia/Kolkata")

        self._cached_attrs.add(attr)
        setattr(self, attr, val)
        return val

    @property
    def user_settings(self) -> dict:
        if not hasattr(self, "_user_settings"):
            self._user_settings = getattr(settings, "PLUGIN_CONFIGS", {}).get(self.plugin_name, {})
        return self._user_settings

    def reload(self) -> None:
        for attr in self._cached_attrs:
            delattr(self, attr)
        self._cached_attrs.clear()
        if hasattr(self, "_user_settings"):
            delattr(self, "_user_settings")


plugin_settings = PluginSettings(PLUGIN_NAME, defaults=DEFAULTS)


@receiver(setting_changed)
def reload_plugin_settings(*args, **kwargs) -> None:
    if kwargs.get("setting") == "PLUGIN_CONFIGS":
        plugin_settings.reload()
