from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from django import forms
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Suchar
from .models import Tag

if TYPE_CHECKING:
    from typing import Any


class SucharForm(forms.ModelForm):
    tags_input = forms.CharField(
        required=False,
        label="Tagi",
        help_text=_(
            "Wpisz tagi oddzielone spacjami lub przecinkami"
            " (np. suchar, it, programowanie).",
        ),
        widget=forms.TextInput(
            attrs={"placeholder": "suchar, it, programowanie", "class": "form-control"},
        ),
    )

    class Meta:
        model = Suchar
        fields = ["text", "published_at"]
        widgets = {
            "published_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
            ),
        }
        labels = {
            "published_at": _("Publication Date"),
        }
        help_texts = {
            "published_at": _("Leave empty to publish immediately."),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Populate tags_input from existing tags
            self.fields["tags_input"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True),
            )

        # Make published_at optional so that empty value (publish now) is accepted
        self.fields["published_at"].required = False

    def clean_published_at(self) -> datetime:
        published_at = self.cleaned_data.get("published_at")
        if not published_at:
            return timezone.now()

        # Allow a small buffer for clock skew; reject dates more than 5 min in the past.
        if published_at < timezone.now() - timedelta(minutes=5):
            raise forms.ValidationError(
                _("Publication date cannot be in the past."),
            )
        return published_at

    def clean_tags_input(self) -> str:
        tags_input = self.cleaned_data.get("tags_input", "")
        normalized = tags_input.replace(",", " ")
        tag_names = [
            t.strip().lstrip("#") for t in normalized.split() if t.strip().lstrip("#")
        ]
        too_long = [t for t in tag_names if len(t) > 50]  # noqa: PLR2004
        if too_long:
            raise forms.ValidationError(
                _("Tag names must be 50 characters or fewer: %(tags)s"),
                params={"tags": ", ".join(too_long)},
            )
        return tags_input

    def clean_text(self) -> str:
        text = self.cleaned_data.get("text", "")
        if len(text) > 2000:  # noqa: PLR2004
            raise forms.ValidationError(
                _("Joke cannot exceed 2000 characters (currently %(count)d)."),
                params={"count": len(text)},
            )
        return text

    def save(self, commit: bool = True) -> Suchar:  # noqa: FBT001, FBT002
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self._save_tags(instance)
        else:
            _base_save_m2m = self.save_m2m

            def save_m2m() -> None:
                _base_save_m2m()
                self._save_tags(instance)

            # BaseModelForm.save(commit=False) itself sets self.save_m2m as an
            # instance attribute (not a real method) — django-stubs types it as
            # a method for autocomplete purposes, so mypy sees this as
            # reassigning a method. Matches Django's own implementation pattern.
            self.save_m2m = save_m2m  # type: ignore[method-assign]
        return instance

    def _save_tags(self, instance: Suchar) -> None:
        tags_input = self.cleaned_data.get("tags_input", "")
        # Replace commas with spaces to handle both separators
        tags_input = tags_input.replace(",", " ")
        tag_names = [
            t.strip().lstrip("#") for t in tags_input.split() if t.strip().lstrip("#")
        ]

        tags = []
        for name in tag_names:
            slug = slugify(name)
            if not slug:
                continue
            # Try to find by slug first to avoid duplicates
            tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name})
            tags.append(tag)

        instance.tags.set(tags)
