from django.urls import path

from . import views

app_name = "achievements"
urlpatterns = [
    path("", views.AchievementListView.as_view(), name="list"),
]
