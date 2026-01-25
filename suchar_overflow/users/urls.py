from django.urls import path
from django.views.generic import TemplateView

from .views import activate_view
from .views import signup_view
from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("signup/", view=signup_view, name="signup"),
    path(
        "signup/done/",
        view=TemplateView.as_view(template_name="registration/signup_done.html"),
        name="signup_done",
    ),
    path("activate/<uidb64>/<token>/", view=activate_view, name="activate"),
    path("<str:username>/", view=user_detail_view, name="detail"),
]
