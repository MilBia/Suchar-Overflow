from django.urls import path

from .views import SucharCreateView
from .views import SucharListView
from .views import vote_suchar

app_name = "suchary"

urlpatterns = [
    path("", SucharListView.as_view(), name="list"),
    path("add/", SucharCreateView.as_view(), name="add"),
    path("<int:pk>/vote/", vote_suchar, name="vote"),
]
