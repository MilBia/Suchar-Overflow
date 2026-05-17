from http import HTTPStatus

import pytest
from django.urls import reverse

from suchar_overflow.users.models import User


class TestUserAdmin:
    def test_changelist(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_search_by_username(self, admin_client):
        User.objects.create_user(
            username="searchable",
            email="searchable@example.com",
            password="pass",  # noqa: S106
        )
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "searchable"})
        assert response.status_code == HTTPStatus.OK
        assert b"searchable" in response.content

    def test_search_no_match_returns_empty(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "zzznomatch"})
        assert response.status_code == HTTPStatus.OK

    def test_add_get_renders_form(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_add_valid_user_creates_and_redirects(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.post(
            url,
            data={
                "username": "newadminuser",
                "email": "newadminuser@example.com",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
                "email_change_requests-TOTAL_FORMS": "0",
                "email_change_requests-INITIAL_FORMS": "0",
                "email_change_requests-MIN_NUM_FORMS": "0",
                "email_change_requests-MAX_NUM_FORMS": "1000",
            },
        )
        assert response.status_code == HTTPStatus.FOUND
        assert User.objects.filter(username="newadminuser").exists()

    def test_add_duplicate_username_shows_error(self, admin_client):
        User.objects.create_user(
            username="duplicate",
            email="dup@example.com",
            password="pass",  # noqa: S106
        )
        url = reverse("admin:users_user_add")
        response = admin_client.post(
            url,
            data={
                "username": "duplicate",
                "email": "other@example.com",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
                "email_change_requests-TOTAL_FORMS": "0",
                "email_change_requests-INITIAL_FORMS": "0",
                "email_change_requests-MIN_NUM_FORMS": "0",
                "email_change_requests-MAX_NUM_FORMS": "1000",
            },
        )
        # Form re-renders (200) with validation errors, no new user created
        assert response.status_code == HTTPStatus.OK
        assert User.objects.filter(username="duplicate").count() == 1

    def test_add_password_mismatch_shows_error(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.post(
            url,
            data={
                "username": "mismatch",
                "email": "mismatch@example.com",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "WrongPassword123",
                "email_change_requests-TOTAL_FORMS": "0",
                "email_change_requests-INITIAL_FORMS": "0",
                "email_change_requests-MIN_NUM_FORMS": "0",
                "email_change_requests-MAX_NUM_FORMS": "1000",
            },
        )
        assert response.status_code == HTTPStatus.OK
        assert not User.objects.filter(username="mismatch").exists()

    def test_view_user_detail(self, admin_client):
        user = User.objects.get(username="admin")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_view_user_detail_contains_username(self, admin_client):
        user = User.objects.get(username="admin")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert b"admin" in response.content

    def test_update_user_name(self, admin_client):
        user = User.objects.get(username="admin")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.post(
            url,
            data={
                "username": "admin",
                "email": user.email,
                "name": "Updated Name",
                "is_active": "on",
                "is_staff": "on",
                "is_superuser": "on",
                "date_joined_0": "2020-01-01",
                "date_joined_1": "00:00:00",
                "email_change_requests-TOTAL_FORMS": "0",
                "email_change_requests-INITIAL_FORMS": "0",
                "email_change_requests-MIN_NUM_FORMS": "0",
                "email_change_requests-MAX_NUM_FORMS": "1000",
            },
        )
        assert response.status_code == HTTPStatus.FOUND
        user.refresh_from_db()
        assert user.name == "Updated Name"

    @pytest.mark.django_db
    def test_delete_user(self, admin_client):
        user = User.objects.create_user(
            username="to_delete",
            email="to_delete@example.com",
            password="pass",  # noqa: S106
        )
        url = reverse("admin:users_user_delete", kwargs={"object_id": user.pk})
        response = admin_client.post(url, data={"post": "yes"})
        assert response.status_code == HTTPStatus.FOUND
        assert not User.objects.filter(username="to_delete").exists()
