from datetime import timedelta

import pytest
from django.utils import timezone

from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.forms import SucharForm
from suchar_overflow.suchary.models import Tag


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
