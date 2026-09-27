"""The shared ``Message`` API schema (#455)."""

import pydantic
import pytest

from suchar_overflow.utils.schema import Message


def test_message_round_trips() -> None:
    assert Message(message="Gotowe").model_dump() == {"message": "Gotowe"}


def test_message_requires_the_message_field() -> None:
    with pytest.raises(pydantic.ValidationError):
        Message.model_validate({})
