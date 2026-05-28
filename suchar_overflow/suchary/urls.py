from django.urls import path

from .views import SucharCreateView
from .views import SucharListView
from .views import SucharUpdateView

app_name = "suchary"

urlpatterns = [
    path("", SucharListView.as_view(), name="list"),
    path("add/", SucharCreateView.as_view(), name="add"),
    path("update/<int:pk>/", SucharUpdateView.as_view(), name="update"),
]
