from django.contrib import admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from .models import Suchar
from .models import Tag
from .models import Vote


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


class VoteInline(admin.TabularInline):
    model = Vote
    extra = 0
    readonly_fields = ["user", "value"]
    can_delete = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Suchar)
class SucharAdmin(admin.ModelAdmin):
    list_display = ["id", "short_text_display", "author", "created_at", "total_votes"]
    list_filter = ["created_at", "tags"]
    search_fields = ["text", "author__username", "author__name"]
    autocomplete_fields = ["author", "tags"]
    inlines = [VoteInline]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(_total_votes=Count("votes"))

    @admin.display(description=_("Text"))
    def short_text_display(self, obj):
        limit = 75
        return (obj.text[:limit] + "...") if len(obj.text) > limit else obj.text

    @admin.display(description=_("Votes"), ordering="_total_votes")
    def total_votes(self, obj):
        return obj._total_votes  # noqa: SLF001


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["user", "suchar", "value"]
    list_filter = ["value"]
    search_fields = ["user__username", "suchar__text"]
    autocomplete_fields = ["user", "suchar"]
