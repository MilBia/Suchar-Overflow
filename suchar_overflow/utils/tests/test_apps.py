"""The ``suchar_utils`` app is installed under its own config (#455, #450)."""

import pytest
from django.apps import apps

from suchar_overflow.utils.apps import UtilsConfig


def test_utils_app_is_installed() -> None:
    config = apps.get_app_config("suchar_utils")
    assert isinstance(config, UtilsConfig)
    assert config.name == "suchar_overflow.utils"
    assert config.label == "suchar_utils"


def test_bare_utils_label_is_not_registered() -> None:
    # The generic label is left free for a third-party app.
    with pytest.raises(LookupError, match="No installed app with label 'utils'"):
        apps.get_app_config("utils")
