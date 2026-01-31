from http import HTTPStatus

from django.urls import reverse

from suchar_overflow.users.models import User


class TestUserAdmin:
    def test_changelist(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_search(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "test"})
        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

        response = admin_client.post(
            url,
            data={
                "username": "test",
                "email": "test@example.com",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
                "email_change_requests-TOTAL_FORMS": "0",
                "email_change_requests-INITIAL_FORMS": "0",
                "email_change_requests-MIN_NUM_FORMS": "0",
                "email_change_requests-MAX_NUM_FORMS": "1000",
            },
        )
        assert response.status_code == HTTPStatus.FOUND
        assert User.objects.filter(username="test").exists()

    def test_view_user(self, admin_client):
        user = User.objects.get(username="admin")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK
