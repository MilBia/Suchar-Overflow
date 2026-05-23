from datetime import timedelta

from django import forms
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Suchar
from .models import Tag


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Populate tags_input from existing tags
            self.fields["tags_input"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True),
            )

        # Make published_at optional so that empty value (publish now) is accepted
        self.fields["published_at"].required = False

    def clean_published_at(self):
        published_at = self.cleaned_data.get("published_at")
        if not published_at:
            return timezone.now()

        # Allow a small buffer for clock skew; reject dates more than 5 min in the past.
        if published_at < timezone.now() - timedelta(minutes=5):
            raise forms.ValidationError(
                _("Publication date cannot be in the past."),
            )
        return published_at

    def save(self, commit=True):  # noqa: FBT002
        instance = super().save(commit=commit)
        if commit:
            self._save_tags(instance)
        return instance

    def _save_tags(self, instance):
        tags_input = self.cleaned_data.get("tags_input", "")
        # Replace commas with spaces to handle both separators
        tags_input = tags_input.replace(",", " ")
        tag_names = [t.strip() for t in tags_input.split() if t.strip()]

        tags = []
        for name in tag_names:
            slug = slugify(name)
            if not slug:
                continue
            # Try to find by slug first to avoid duplicates
            tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name})
            tags.append(tag)

        instance.tags.set(tags)
