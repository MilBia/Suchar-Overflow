"""Logging handlers."""

from typing import TYPE_CHECKING

from django.utils import log

from suchar_overflow.utils.db import releases_db_connections

if TYPE_CHECKING:
    import logging


class AdminEmailHandler(log.AdminEmailHandler):
    """``AdminEmailHandler`` that doesn't strand a DB connection (#447).

    The report reads ``request.user``, which can hit the DB. Under ASGI,
    ``log_response`` runs in an executor thread that ``request_finished`` never
    cleans up (see ``suchar_overflow.utils.db``), both for exceptions and for any
    >= 400 response a view returns, so the connection has to be released here.
    """

    @releases_db_connections
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
