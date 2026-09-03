from typing import TYPE_CHECKING

from django.contrib import admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from .models import Suchar
from .models import Tag
from .models import Vote

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


class VoteInline(admin.TabularInline):
    model = Vote
    extra = 0
    readonly_fields = ["user", "is_funny", "is_dry"]
    can_delete = True

    def has_add_permission(
        self,
        _request: HttpRequest,
        _obj: Suchar | None = None,
    ) -> bool:
        return False


@admin.register(Suchar)
class SucharAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "short_text_display",
        "author",
        "created_at",
        "total_votes",
        "is_overdried",
        "edit_count",
    ]
    # Pins the changelist join explicitly. Django 6.1's ChangeList would derive
    # the same set from the FKs in list_display on its own
    # (ChangeList.get_select_related_fields), but ONLY while list_select_related
    # is left at its False default — declaring it here opts these classes out of
    # that auto-derivation. So this changes no SQL today; its job is to make the
    # join explicit and survive a Django-internal change. test_admin_select_related
    # guards that this list stays equal to what list_display would derive, so a
    # later FK added to list_display isn't silently dropped from the join.
    list_select_related = ["author"]
    list_filter = ["created_at", "tags", "is_overdried"]
    search_fields = ["text", "author__username", "author__name"]
    autocomplete_fields = ["author", "tags"]
    # Engine-managed state — surfaced for moderation, never hand-edited:
    # is_overdried is the dry-out latch (#294), edit_count the repeat-edit
    # counter (#297, "never decremented — the engine only awards").
    readonly_fields = ["is_overdried", "edit_count"]
    inlines = [VoteInline]
    date_hierarchy = "created_at"

    def get_queryset(self, request: HttpRequest) -> QuerySet[Suchar]:
        queryset = super().get_queryset(request)
        return queryset.annotate(_total_votes=Count("votes"))

    @admin.display(description=_("Text"))
    def short_text_display(self, obj: Suchar) -> str:
        limit = 75
        return (obj.text[:limit] + "...") if len(obj.text) > limit else obj.text

    @admin.display(description=_("Votes"), ordering="_total_votes")
    def total_votes(self, obj: Suchar) -> int:
        return obj._total_votes  # type: ignore[attr-defined] # noqa: SLF001


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["user", "suchar", "is_funny", "is_dry"]
    # See SucharAdmin above — explicit, kept equal to Django's own derivation
    # by test_admin_select_related.
    list_select_related = ["user", "suchar"]
    list_filter = ["is_funny", "is_dry"]
    search_fields = ["user__username", "suchar__text"]
    autocomplete_fields = ["user", "suchar"]
