"""Guard the explicit `list_select_related` pins added for issue #203, point 3.

Django 6.1's `ChangeList.apply_select_related` derives the join set from the FKs
in `list_display` automatically — but only while `list_select_related` is left at
its `False` default. The four admin classes below declare it explicitly, which
opts them out of that derivation. This test keeps each frozen list identical to
what Django would derive, so a later FK added to `list_display` is not silently
dropped from the changelist join (the N+1 issue #203 set out to avoid).
"""

from typing import TYPE_CHECKING

import pytest
from django.contrib import admin
from django.test import RequestFactory

from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.users.models import EmailChangeRequest

if TYPE_CHECKING:
    from django.db.models import Model

    from suchar_overflow.users.models import User

PINNED_ADMIN_MODELS = [Suchar, Vote, UserAchievement, EmailChangeRequest]


@pytest.mark.django_db
@pytest.mark.parametrize("model", PINNED_ADMIN_MODELS)
def test_admin_select_related_matches_list_display_derivation(
    model: type[Model],
    admin_user: User,
) -> None:
    model_admin = admin.site.get_model_admin(model)
    request = RequestFactory().get("/")
    request.user = admin_user
    changelist = model_admin.get_changelist_instance(request)

    select_related = model_admin.list_select_related
    # Only the explicit-list form is guarded here; True/False mean "let Django
    # decide" and there is nothing to keep in sync.
    assert not isinstance(select_related, bool)

    derived = sorted(changelist.get_select_related_fields())
    declared = sorted(select_related)
    assert derived == declared, (
        f"{model_admin.__class__.__name__}.list_select_related {declared!r} has "
        f"drifted from what list_display would derive: {derived!r}"
    )
