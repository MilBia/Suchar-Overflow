"""Themed error pages — 404 / 403 / 403 CSRF / 500 (issue #286).

These templates are plain, JS-free and each carry a Polish "suchar". The one
non-obvious contract is `500.html`: Django's `django.views.defaults.server_error`
renders it with a bare `template.render()` — no request, no context processors.
`test_500_renders_without_request` mirrors that call exactly, so a template
change that makes 500.html raise under those conditions fails here rather than
in production. (It cannot catch a new context variable silently rendering as
an empty string — Django templates swallow that — only an outright render error.)

Expected copy is pulled through `gettext`, never hard-coded: CI never compiles
`locale/*.mo`, so `gettext` returns the (Polish) msgid unchanged — matching what
the template renders — while a stray locally-compiled catalog can't mask a drift.
"""

import pytest
from django.template.loader import get_template
from django.template.loader import render_to_string
from django.test import Client
from django.test import RequestFactory
from django.test import override_settings
from django.urls import reverse
from django.utils.translation import gettext

CONTEXT_PAGES = [
    (
        "404.html",
        "404 — ta strona wyparowała",
        "Była tak sucha, że wyparowała. Zostały tylko okruszki i ten komunikat.",
    ),
    (
        "403.html",
        "403 — wstęp wzbroniony",
        "Ochroniarz przeczytał ten suchar i teraz nikomu nie ufa. Tobie też nie.",
    ),
    (
        "403_csrf.html",
        "403 — formularz bez pieczątki",
        (
            "Serwer nie znalazł ważnego tokenu CSRF i na wszelki wypadek nie "
            "ruszył palcem. Odśwież stronę i spróbuj ponownie."
        ),
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("template_name", "title", "joke"), CONTEXT_PAGES)
def test_error_page_renders_themed_suchar(
    template_name: str,
    title: str,
    joke: str,
) -> None:
    request = RequestFactory().get("/nope/")
    html = render_to_string(template_name, {"request": request})

    assert 'class="error-page"' in html
    assert gettext(title) in html
    assert gettext(joke) in html
    assert reverse("home") in html


@pytest.mark.django_db
def test_500_renders_without_request() -> None:
    # Exactly how django.views.defaults.server_error renders it: no request,
    # no context, no context processors.
    html = get_template("500.html").render()

    assert 'class="error-page"' in html
    assert gettext("500 — coś chrupnęło") in html
    assert (
        gettext(
            "Serwer usłyszał suchar i się rozsypał. Już to naprawiamy — "
            "odśwież za chwilę.",
        )
        in html
    )
    assert reverse("home") in html


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_missing_url_serves_themed_404_through_middleware() -> None:
    # Complements the render_to_string checks above: proves 404.html is actually
    # wired as handler404 and reached through the full middleware stack, not just
    # renderable in isolation. DEBUG=False so Django uses the project template
    # rather than its own technical 404 page.
    response = Client().get("/no-such-url-exists/")

    assert response.status_code == 404  # noqa: PLR2004
    body = response.content.decode()
    assert 'class="error-page"' in body
    assert gettext("404 — ta strona wyparowała") in body
