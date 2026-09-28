"""The ``utils`` app is installed under its own config (#455)."""

from django.apps import apps

from suchar_overflow.utils.apps import UtilsConfig


def test_utils_app_is_installed() -> None:
    config = apps.get_app_config("suchar_utils")
    assert isinstance(config, UtilsConfig)
    assert config.name == "suchar_overflow.utils"
