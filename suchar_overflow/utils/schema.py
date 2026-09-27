"""API schemas shared by the django-ninja routers."""

from ninja import Schema


class Message(Schema):
    """A response that carries only a human-readable message."""

    message: str
