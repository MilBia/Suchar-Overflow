from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import Achievement
from .models import UserAchievement


class AchievementAdminForm(forms.ModelForm):
    generate_tiers = forms.BooleanField(
        help_text="Zaznacz aby automatycznie wygenerować z tego drabinkę Tierów.",
    )
    tier_thresholds = forms.CharField(
        help_text=(
            "Opcjonalne. Podaj progi np. '5,10,25,50,100'. "
            "Pierwszy próg to baza, a 4 kolejne powstaną same."
        ),
    )

    class Meta:
        model = Achievement
        fields = (
            "name",
            "slug",
            "description",
            "icon_content",
            "category",
            "event_type",
            "metric",
            "threshold",
            "theme",
            "tier",
            "generate_tiers",
            "tier_thresholds",
            "is_secret",
        )


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    form = AchievementAdminForm
    list_display = (
        "name",
        "icon_preview",
        "tier",
        "theme",
        "category",
        "event_type",
        "metric",
        "threshold",
        "is_secret",
    )
    list_filter = ("tier", "theme", "category", "event_type", "metric", "is_secret")
    search_fields = ("name", "slug", "description", "theme")

    fieldsets = (
        (
            "General Info",
            {
                "fields": ("name", "slug", "description", "icon_content", "is_secret"),
            },
        ),
        (
            "Progression",
            {
                "fields": ("theme", "tier", "generate_tiers", "tier_thresholds"),
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

    def save_model(self, request, obj, form, change):
        if not change and form.cleaned_data.get("generate_tiers"):
            thresholds_str = form.cleaned_data.get("tier_thresholds", "")
            if thresholds_str:
                thresholds = [
                    int(x.strip())
                    for x in thresholds_str.split(",")
                    if x.strip().isdigit()
                ]
                if thresholds:
                    # Modify base object to be TIER 1 and have threshold[0]
                    obj.threshold = thresholds[0]
                    obj.tier = Achievement.Tier.BRONZE
                    super().save_model(request, obj, form, change)

                    # Create sub-tiers
                    tiers = [
                        Achievement.Tier.BRONZE,
                        Achievement.Tier.SILVER,
                        Achievement.Tier.GOLD,
                        Achievement.Tier.PLATINUM,
                        Achievement.Tier.DIAMOND,
                    ]
                    for idx, t_val in enumerate(thresholds[1:]):
                        tier_idx = idx + 1
                        if tier_idx < len(tiers):
                            tier = tiers[tier_idx]
                            tier_label = str(tier.name).lower()
                            Achievement.objects.create(
                                name=f"{obj.name} ({tier.label})",
                                slug=f"{obj.slug}-{tier_label}",
                                description=obj.description,
                                icon_content=obj.icon_content,
                                category=obj.category,
                                event_type=obj.event_type,
                                metric=obj.metric,
                                threshold=t_val,
                                theme=obj.theme,
                                tier=tier,
                                is_secret=obj.is_secret,
                            )
                    return

        super().save_model(request, obj, form, change)


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "achievement", "awarded_at", "is_seen")
    list_filter = ("is_seen", "awarded_at", "achievement__category")
    search_fields = ("user__username", "user__email", "achievement__name")
    autocomplete_fields = ("user", "achievement")
    readonly_fields = ("awarded_at",)
