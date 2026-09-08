from typing import TYPE_CHECKING
from typing import Any

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from modeltranslation.admin import TabbedTranslationAdmin

from .models import Achievement
from .models import SchedulerRun
from .models import UserAchievement

if TYPE_CHECKING:
    from django.http import HttpRequest


def parse_tier_thresholds(raw: str) -> list[int]:
    """Parse a comma-separated thresholds string into ints.

    Blank entries and anything non-digit are silently dropped, matching the
    tolerant parsing `save_model` has always done on creation.
    """
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


class AchievementAdminForm(forms.ModelForm):
    # generate_tiers/tier_thresholds are plain form fields, not model fields,
    # so nothing pre-populates them from the instance on GET. They must stay
    # required=False or every edit of an existing Achievement (even one that
    # has nothing to do with tiers) fails validation — save_model only ever
    # consults them on creation (`not change`) anyway. clean() below enforces
    # that tier_thresholds is actually usable whenever generate_tiers is
    # checked, so that check isn't lost by making the fields optional.
    generate_tiers = forms.BooleanField(
        required=False,
        help_text="Zaznacz aby automatycznie wygenerować z tego drabinkę Tierów.",
    )
    tier_thresholds = forms.CharField(
        required=False,
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

    def clean(self) -> dict[str, Any] | None:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data
        if cleaned_data.get("generate_tiers") and not parse_tier_thresholds(
            cleaned_data.get("tier_thresholds") or "",
        ):
            self.add_error(
                "tier_thresholds",
                "Podaj przynajmniej jeden poprawny liczbowy próg "
                "(np. '5,10,25,50,100'), gdy zaznaczone jest generate_tiers.",
            )
        return cleaned_data


@admin.register(Achievement)
class AchievementAdmin(TabbedTranslationAdmin):
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
    def icon_preview(self, obj: Achievement) -> str:
        if obj.icon_content:
            # We wrap the SVG in a div with fixed size for the admin list
            return format_html(
                '<div style="width: 32px; height: 32px;">{}</div>',
                mark_safe(obj.icon_content),  # noqa: S308
            )
        return "-"

    def save_model(
        self,
        request: HttpRequest,
        obj: Achievement,
        form: AchievementAdminForm,
        change: bool,  # noqa: FBT001
    ) -> None:
        if not change and form.cleaned_data.get("generate_tiers"):
            thresholds_str = form.cleaned_data.get("tier_thresholds", "")
            if thresholds_str:
                thresholds = parse_tier_thresholds(thresholds_str)
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
    # Explicit changelist join; Django 6.1 would derive the same set from
    # list_display on its own, but declaring it opts out of that fallback
    # (see the note in suchary/admin.py). test_admin_select_related keeps
    # this list equal to what list_display would derive.
    list_select_related = ("user", "achievement")
    list_filter = ("is_seen", "awarded_at", "achievement__category")
    search_fields = ("user__username", "user__email", "achievement__name")
    autocomplete_fields = ("user", "achievement")
    readonly_fields = ("awarded_at",)


@admin.register(SchedulerRun)
class SchedulerRunAdmin(admin.ModelAdmin):
    list_display = ("job_id", "ran_at")

    def has_add_permission(self, _request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        _request: HttpRequest,
        _obj: SchedulerRun | None = None,
    ) -> bool:
        return False
