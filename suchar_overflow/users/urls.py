from django.urls import path
from django.views.generic import TemplateView

from .views import activate_view
from .views import email_change_confirm_view
from .views import email_change_done_view
from .views import email_change_initiate_view
from .views import email_change_revoke_view
from .views import signup_view
from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    # Email Change
    path(
        "email/change/",
        view=email_change_initiate_view,
        name="email_change_initiate",
    ),
    path("email/done/", view=email_change_done_view, name="email_change_done"),
    path(
        "email/verify/<str:token>/",
        view=email_change_confirm_view,
        name="email_change_verify",
    ),
    path(
        "email/revoke/<str:token>/",
        view=email_change_revoke_view,
        name="email_change_revoke",
    ),
    path("signup/", view=signup_view, name="signup"),
    path(
        "signup/done/",
        view=TemplateView.as_view(template_name="registration/signup_done.html"),
        name="signup_done",
    ),
    path("activate/<uidb64>/<token>/", view=activate_view, name="activate"),
    path("<str:username>/", view=user_detail_view, name="detail"),
]
