from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.views.generic import TemplateView

from suchar_overflow.utils.views import bad_request
from suchar_overflow.utils.views import page_not_found
from suchar_overflow.utils.views import permission_denied
from suchar_overflow.utils.views import server_error

from .api import api

# Release the DB connections of the executor thread Django runs them in (#447).
handler400 = bad_request
handler403 = permission_denied
handler404 = page_not_found
# Always answers, even when 500.html itself raises — see server_error (#442).
handler500 = server_error

urlpatterns = [
    path("", TemplateView.as_view(template_name="pages/home.html"), name="home"),
    path(
        "about/",
        TemplateView.as_view(template_name="pages/about.html"),
        name="about",
    ),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("suchar_overflow.users.urls", namespace="users")),
    path("stats/", include("suchar_overflow.stats.urls", namespace="stats")),
    path("accounts/", include("django.contrib.auth.urls")),
    path(
        "achievements/",
        include("suchar_overflow.achievements.urls", namespace="achievements"),
    ),
    # Your stuff: custom urls includes go here
    path("i18n/", include("django.conf.urls.i18n")),
    path("suchary/", include("suchar_overflow.suchary.urls", namespace="suchary")),
    # API
    path("api/", api.urls),
    # ...
    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]


if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", server_error),
    ]
    # Guarded by INSTALLED_APPS, not just DEBUG: django-debug-toolbar is a dev-only
    # dependency, and importing debug_toolbar.toolbar loads its models, which needs
    # the app registered. debug_toolbar_urls() itself is a no-op without DEBUG.
    if "debug_toolbar" in settings.INSTALLED_APPS:
        from debug_toolbar.toolbar import debug_toolbar_urls

        urlpatterns += debug_toolbar_urls()
