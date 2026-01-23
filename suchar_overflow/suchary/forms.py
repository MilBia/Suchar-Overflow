from django import forms
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
        fields = ["text"]

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
