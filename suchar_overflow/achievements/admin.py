from django.contrib import admin
from django.utils.html import format_html

from .models import Achievement
from .models import UserAchievement


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "icon_preview",
        "category",
        "event_type",
        "metric",
        "threshold",
    )
    list_filter = ("category", "event_type", "metric")
    search_fields = ("name", "slug", "description")

    fieldsets = (
        (
            "General Info",
            {
                "fields": ("name", "slug", "description", "icon_content"),
            },
        ),
        (
            "Rules",
            {
                "fields": ("category", "event_type", "metric", "threshold"),
            },
        ),
    )

    @admin.display(description="Icon")
    def icon_preview(self, obj):
        if obj.icon_content:
            # We wrap the SVG in a div with fixed size for the admin list
            return format_html(
                '<div style="width: 32px; height: 32px;">{}</div>',
                format_html(obj.icon_content),
            )
        return "-"


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "achievement", "awarded_at", "is_seen")
    list_filter = ("is_seen", "awarded_at", "achievement__category")
    search_fields = ("user__username", "user__email", "achievement__name")
    autocomplete_fields = ("user", "achievement")
    readonly_fields = ("awarded_at",)
