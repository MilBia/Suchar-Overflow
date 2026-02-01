from http import HTTPStatus

import pytest
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.users.forms import UserAdminChangeForm
from suchar_overflow.users.models import User
from suchar_overflow.users.tests.factories import UserFactory
from suchar_overflow.users.views import UserRedirectView
from suchar_overflow.users.views import UserUpdateView
from suchar_overflow.users.views import user_detail_view

pytestmark = pytest.mark.django_db


class TestUserUpdateView:
    """
    TODO:
        extracting view initialization code as class-scoped fixture
        would be great if only pytest-django supported non-function-scoped
        fixture db access -- this is a work-in-progress for now:
        https://github.com/pytest-dev/pytest-django/pull/258
    """

    def dummy_get_response(self, request: HttpRequest):
        return None

    def test_get_success_url(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request
        assert view.get_success_url() == f"/users/{user.username}/"

    def test_get_object(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert view.get_object() == user

    def test_form_valid(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")

        # Add the session/message middleware to the request
        SessionMiddleware(self.dummy_get_response).process_request(request)
        MessageMiddleware(self.dummy_get_response).process_request(request)
        request.user = user

        view.request = request

        # Initialize the form
        form = UserAdminChangeForm()
        form.cleaned_data = {}
        form.instance = user
        view.form_valid(form)

        messages_sent = [m.message for m in messages.get_messages(request)]
        assert messages_sent == [_("Information successfully updated")]


class TestUserRedirectView:
    def test_get_redirect_url(self, user: User, rf: RequestFactory):
        view = UserRedirectView()
        request = rf.get("/fake-url")
        request.user = user

        view.request = request
        assert view.get_redirect_url() == f"/users/{user.username}/"


class TestUserDetailView:
    def test_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = UserFactory()
        response = user_detail_view(request, username=user.username)

        assert response.status_code == HTTPStatus.OK

    def test_not_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = AnonymousUser()
        response = user_detail_view(request, username=user.username)
        login_url = reverse(settings.LOGIN_URL)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == f"{login_url}?next=/fake-url/"

    def test_stats_calculation(self, user: User, rf: RequestFactory, client):
        """Verify that total_score and suchar_count are correctly calculated."""
        # Create one joke with 1 upvote (funny)
        s1 = Suchar.objects.create(text="Joke 1", author=user)
        Vote.objects.create(suchar=s1, user=user, is_funny=True)

        # Create duplicated vote on another joke to verify distinct counting?
        # Vote unique_together constraint prevents multiple votes by same user.
        # So to test distinct=True we need multiple votes on user's jokes.
        # Create 2nd joke with 1 dry vote from another user
        other_user = UserFactory()
        s2 = Suchar.objects.create(text="Joke 2", author=user)
        Vote.objects.create(suchar=s2, user=other_user, is_dry=True)

        # Total score: 1 (Funny) + 1 (Dry) = 2
        # Total count: 2

        client.force_login(user)
        response = client.get(f"/users/{user.username}/")

        assert response.status_code == HTTPStatus.OK
        # Verify total_score = 2
        expected_score = 2
        assert response.context["object"].total_score == expected_score
        # Verify suchar_count = 2 (not 3 due to joins)
        expected_count = 2
        assert response.context["suchar_count"] == expected_count
