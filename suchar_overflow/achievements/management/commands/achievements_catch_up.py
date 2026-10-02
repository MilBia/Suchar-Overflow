"""Catch up scheduled achievement jobs missed while the ``cron`` service was down (#169, #462).

``rq cron`` only knows future fire times, so ``compose/base/django/cron`` runs this
once before it starts the scheduler. Each catch-up is isolated: one failure (a
transient DB error at startup) must not block the others or the scheduler itself.
"""

import logging
from typing import TYPE_CHECKING
from typing import Any

from django.core.management.base import BaseCommand

from suchar_overflow.achievements.tasks import award_best_suchar_month_if_due
from suchar_overflow.achievements.tasks import award_best_suchar_year_if_due
from suchar_overflow.achievements.tasks import award_publication_achievements

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

CATCH_UPS: tuple[tuple[str, Callable[[], object]], ...] = (
    ("monthly", award_best_suchar_month_if_due),
    ("yearly", award_best_suchar_year_if_due),
    ("publication-achievement", award_publication_achievements),
)


class Command(BaseCommand):
    help = "Run the missed monthly/yearly contest awards and the publication sweep once."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401, ARG002
        for label, catch_up in CATCH_UPS:
            try:
                catch_up()
            except Exception:
                logger.exception("Failed to catch up missed %s scheduler run; continuing", label)
