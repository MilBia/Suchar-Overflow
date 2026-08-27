import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.text import slugify

from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.forms import SucharForm
from suchar_overflow.suchary.models import Tag

if TYPE_CHECKING:
    from suchar_overflow.suchary.models import Suchar
    from suchar_overflow.users.models import User


def form_data(**kwargs: str) -> dict[str, str]:
    """Return minimal valid form data, overridable via kwargs."""
    return {"text": "A fine joke", "published_at": "", **kwargs}


# ---------------------------------------------------------------------------
# clean_published_at
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_published_at_empty_defaults_to_now() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(published_at=""))
    form.instance.author = user
    assert form.is_valid(), form.errors
    # Should resolve to "now" (within a few seconds)
    published = form.cleaned_data["published_at"]
    assert abs((published - timezone.now()).total_seconds()) < 5  # noqa: PLR2004


@pytest.mark.django_db
def test_published_at_future_date_is_valid() -> None:
    user = make_user("author")
    future = timezone.now() + timedelta(days=3)
    form = SucharForm(data=form_data(published_at=future.strftime("%Y-%m-%dT%H:%M")))
    form.instance.author = user
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_published_at_recent_past_within_buffer_is_valid() -> None:
    """Dates up to 5 minutes in the past should be accepted (network/clock drift)."""
    user = make_user("author")
    slight_past = timezone.now() - timedelta(minutes=3)
    form = SucharForm(
        data=form_data(published_at=slight_past.strftime("%Y-%m-%dT%H:%M")),
    )
    form.instance.author = user
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_published_at_old_past_date_is_rejected() -> None:
    user = make_user("author")
    old_past = timezone.now() - timedelta(minutes=10)
    form = SucharForm(data=form_data(published_at=old_past.strftime("%Y-%m-%dT%H:%M")))
    form.instance.author = user
    assert not form.is_valid()
    assert "published_at" in form.errors


# ---------------------------------------------------------------------------
# _save_tags / tag parsing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tags_comma_separated() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="it, python, linux"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    slugs = set(instance.tags.values_list("slug", flat=True))
    assert slugs == {"it", "python", "linux"}


@pytest.mark.django_db
def test_tags_space_separated() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="it python linux"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    slugs = set(instance.tags.values_list("slug", flat=True))
    assert slugs == {"it", "python", "linux"}


@pytest.mark.django_db
def test_tags_mixed_separators() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="it, python linux"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    assert instance.tags.count() == 3  # noqa: PLR2004


@pytest.mark.django_db
def test_tags_empty_input_clears_tags() -> None:
    user = make_user("author")
    # Pre-create a tag to ensure clearing works
    Tag.objects.create(name="IT", slug="it")
    form = SucharForm(data=form_data(tags_input=""))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    assert instance.tags.count() == 0


@pytest.mark.django_db
def test_tags_deduplication_same_slug() -> None:
    """Submitting the same tag twice (or different capitalisation) creates one tag."""
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="Python, python, PYTHON"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    assert instance.tags.count() == 1
    tag = instance.tags.first()
    assert tag is not None
    assert tag.slug == "python"


@pytest.mark.django_db
def test_tags_reuse_existing_tag() -> None:
    """If a tag with the same slug already exists it is reused, not duplicated."""
    user = make_user("author")
    existing = Tag.objects.create(name="IT", slug="it")
    form = SucharForm(data=form_data(tags_input="it"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    assert Tag.objects.filter(slug="it").count() == 1
    tag = instance.tags.first()
    assert tag is not None
    assert tag.pk == existing.pk


@pytest.mark.django_db
def test_tags_invalid_slug_skipped() -> None:
    """Tags whose slugify result is empty (pure punctuation) are silently skipped."""
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="python, !!!, ---"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    slugs = set(instance.tags.values_list("slug", flat=True))
    assert "python" in slugs
    # The purely-punctuation entries should not have created any tag
    assert all(s.isidentifier() or "-" in s for s in slugs)
    # Most importantly: no crash and only valid tags remain
    assert instance.tags.count() == 1


@pytest.mark.django_db
def test_save_m2m_applies_tags() -> None:
    """save(commit=False) + save_m2m() must apply tags without accessing _save_tags."""
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="it, python"))
    form.instance.author = user
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()

    slugs = set(instance.tags.values_list("slug", flat=True))
    assert slugs == {"it", "python"}


# ---------------------------------------------------------------------------
# clean_tags_input
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tag_at_limit_is_accepted() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="x" * 50))
    form.instance.author = user
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_tag_too_long_is_rejected() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="x" * 51))
    form.instance.author = user
    assert not form.is_valid()
    assert "tags_input" in form.errors


@pytest.mark.django_db
def test_mixed_tags_one_too_long_is_rejected() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(tags_input="python, " + "x" * 51))
    form.instance.author = user
    assert not form.is_valid()
    assert "tags_input" in form.errors


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_text_at_limit_is_accepted() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(text="x" * 2000))
    form.instance.author = user
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_text_too_long_is_rejected() -> None:
    user = make_user("author")
    form = SucharForm(data=form_data(text="x" * 2001))
    form.instance.author = user
    assert not form.is_valid()
    assert "text" in form.errors


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_text_is_required() -> None:
    form = SucharForm(data={"text": "", "published_at": ""})
    assert not form.is_valid()
    assert "text" in form.errors


# ---------------------------------------------------------------------------
# _save_tags — bulk instead of a get_or_create loop (issue #203, point 2)
# ---------------------------------------------------------------------------


def save_with_tags(user: User, tags_input: str) -> Suchar:
    """Save a SucharForm with the given raw tag input and return the instance."""
    form = SucharForm(data=form_data(tags_input=tags_input))
    form.instance.author = user
    assert form.is_valid(), form.errors
    return form.save()


def tag_slugs(suchar: Suchar) -> set[str]:
    return set(suchar.tags.values_list("slug", flat=True))


@pytest.mark.django_db
def test_save_tags_creates_missing_tags() -> None:
    user = make_user("tags_new")
    suchar = save_with_tags(user, "python, django")

    assert tag_slugs(suchar) == {"python", "django"}
    assert Tag.objects.get(slug="python").name == "python"


@pytest.mark.django_db
def test_save_tags_reuses_existing_tags() -> None:
    user = make_user("tags_existing")
    existing = Tag.objects.create(name="Python", slug="python")

    suchar = save_with_tags(user, "Python")

    assert tag_slugs(suchar) == {"python"}
    assert Tag.objects.filter(slug="python").count() == 1
    # The pre-existing spelling must win — no rename, no duplicate row.
    existing.refresh_from_db()
    assert existing.name == "Python"


@pytest.mark.django_db
def test_save_tags_mixes_existing_and_new() -> None:
    user = make_user("tags_mixed")
    Tag.objects.create(name="python", slug="python")

    suchar = save_with_tags(user, "python django rust")

    assert tag_slugs(suchar) == {"python", "django", "rust"}
    assert Tag.objects.filter(slug__in=["python", "django", "rust"]).count() == 3  # noqa: PLR2004


@pytest.mark.django_db
def test_save_tags_deduplicates_repeated_slugs() -> None:
    user = make_user("tags_dupes")

    suchar = save_with_tags(user, "Python python #PYTHON")

    assert tag_slugs(suchar) == {"python"}
    assert Tag.objects.filter(slug="python").count() == 1
    # First spelling typed wins.
    assert Tag.objects.get(slug="python").name == "Python"


@pytest.mark.django_db
def test_save_tags_skips_names_that_slugify_to_nothing() -> None:
    user = make_user("tags_empty_slug")

    suchar = save_with_tags(user, "!!! python ???")

    assert tag_slugs(suchar) == {"python"}


@pytest.mark.django_db
def test_save_tags_with_no_input_clears_tags() -> None:
    user = make_user("tags_none")

    suchar = save_with_tags(user, "")

    assert tag_slugs(suchar) == set()


@pytest.mark.django_db
def test_save_tags_query_count_does_not_scale_with_tag_count() -> None:
    """Tag persistence must be bulk, not one get_or_create per tag."""
    user = make_user("tags_perf")

    def tag_query_count(tags_input: str) -> int:
        with CaptureQueriesContext(connection) as ctx:
            save_with_tags(user, tags_input)
        return len([q for q in ctx.captured_queries if '"suchary_tag"' in q["sql"]])

    few = tag_query_count(" ".join(f"few{i}" for i in range(2)))
    many = tag_query_count(" ".join(f"many{i}" for i in range(8)))

    assert few == many, f"tag queries scale with tag count: {few} vs {many}"


@pytest.mark.django_db
def test_save_tags_logs_when_a_name_collision_drops_a_tag(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A pre-existing name under a different slug is skipped, not fatal, logged.

    ``Tag.name`` is unique, so ``bulk_create(ignore_conflicts=True)`` silently
    drops the insert for a new slug whose name already belongs to another row.
    The suchar still saves; the dropped tag gets a warning rather than nothing.
    """
    user = make_user("tags_name_clash")
    typed = "żółw"
    dropped_slug = slugify(typed)
    # Same name, a different slug — the admin's urlify.js vs. python slugify
    # divergence that makes this reachable in a Polish-language app.
    Tag.objects.create(name=typed, slug=f"{dropped_slug}-admin")

    with caplog.at_level(logging.WARNING, logger="suchar_overflow.suchary.forms"):
        suchar = save_with_tags(user, f"{typed} python")

    assert tag_slugs(suchar) == {"python"}
    assert Tag.objects.filter(slug=dropped_slug).count() == 0
    assert any(
        dropped_slug in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    ), caplog.records
