from django.urls import path

from . import views

app_name = "achievements"
urlpatterns = [
    path("", views.AchievementListView.as_view(), name="list"),
    path("inbox/", views.NotificationInboxView.as_view(), name="inbox"),
    path("stream/", views.achievement_stream, name="stream"),
]
