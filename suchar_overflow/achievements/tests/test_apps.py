from suchar_overflow.achievements.apps import AchievementsConfig


def test_is_no_scheduler_command_detects_plain_management_command():
    assert AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "migrate"],
    )


def test_is_no_scheduler_command_detects_command_after_global_flags():
    assert AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "--settings=config.settings.test", "migrate"],
    )


def test_is_no_scheduler_command_false_for_runserver():
    assert not AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "runserver"],
    )


def test_is_no_scheduler_command_does_not_misfire_on_unrelated_argument():
    """A _NO_SCHEDULER word (e.g. "check") appearing as some other command's
    own argument, rather than as the command name itself, must not match."""
    assert not AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "test", "-k", "check"],
    )
