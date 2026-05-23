from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "achievements"
urlpatterns = [
    path("", views.AchievementListView.as_view(), name="list"),
    path("mine/", views.MyAchievementsView.as_view(), name="mine"),
    path(
        "inbox/",
        RedirectView.as_view(pattern_name="achievements:mine", permanent=True),
        name="inbox",
    ),
    path("stream/", views.achievement_stream, name="stream"),
]
