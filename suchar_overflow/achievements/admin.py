from typing import TYPE_CHECKING
from typing import Any
from typing import cast

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import override
from modeltranslation.admin import TabbedTranslationAdmin
from modeltranslation.utils import build_localized_fieldname

from .models import Achievement
from .models import SchedulerRun
from .models import UserAchievement

if TYPE_CHECKING:
    from django.contrib.admin.options import _FieldsetSpec
    from django.http import HttpRequest


# The sub-tiers save_model() can generate, in ascending difficulty order.
# NONE is deliberately excluded — it is the "no ladder" default, not a rung.
TIER_LADDER = [
    Achievement.Tier.BRONZE,
    Achievement.Tier.SILVER,
    Achievement.Tier.GOLD,
    Achievement.Tier.PLATINUM,
    Achievement.Tier.DIAMOND,
]

# A ladder needs a base rung plus at least one sub-tier to mean anything —
# tier_thresholds="5" alone would set the base to Bronze/5 and silently
# generate zero sub-tiers.
MIN_TIER_THRESHOLDS = 2

# The fields modeltranslation manages for Achievement — mirrors
# AchievementTranslationOptions.fields in translation.py.
# test_translated_fields_match_translation_options guards against drift.
TRANSLATED_FIELDS = ("name", "description", "theme")


def parse_tier_thresholds(raw: str) -> list[int]:
    """Parse a comma-separated thresholds string into a list of ints.

    Strict on purpose: raises ValueError (with a user-facing Polish message)
    on an empty string or any token that isn't a whole non-negative integer,
    instead of silently dropping the bad token — a typo like '2O' (letter O)
    for '20' must surface as a validation error, not a quietly shorter ladder.
    """
    if not raw.strip():
        empty_msg = "Podaj przynajmniej jeden próg, np. '5,10,25,50,100'."
        raise ValueError(empty_msg)
    thresholds = []
    for token in raw.split(","):
        stripped = token.strip()
        if not stripped:
            blank_entry_msg = "Lista progów zawiera pusty fragment — sprawdź przecinki."
            raise ValueError(blank_entry_msg)
        if not stripped.isdigit():
            invalid_entry_msg = (
                f"'{stripped}' nie jest poprawną liczbą całkowitą — sprawdź progi."
            )
            raise ValueError(invalid_entry_msg)
        thresholds.append(int(stripped))
    return thresholds


def sub_tier_translation_kwargs(
    base: Achievement,
    tier: Achievement.Tier,
) -> dict[str, str | None]:
    """Localized field kwargs for a generated sub-tier.

    ``save_model`` builds each sub-tier with ``Achievement.objects.create()``.
    With ``MODELTRANSLATION_AUTO_POPULATE`` off, modeltranslation only rewrites
    the bare ``name=``/``description=``/``theme=`` kwargs into the *default*
    language column — so the non-default variants an admin typed into the
    modeltranslation tabs (``name_en`` & co.) were silently dropped from every
    generated sub-tier and stayed ``None`` (#369). Copy every configured
    language variant here instead, suffixing each ``name`` with the tier label
    resolved in that same language. An unfilled base variant stays unfilled.
    """
    kwargs: dict[str, str | None] = {}
    for lang in settings.MODELTRANSLATION_LANGUAGES:
        for field_name in TRANSLATED_FIELDS:
            localized_name = build_localized_fieldname(field_name, lang)
            value = getattr(base, localized_name, None)
            if field_name == "name" and value:
                with override(lang):
                    value = f"{value} ({tier.label})"
            kwargs[localized_name] = value
    return kwargs


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
        if cleaned_data is None or not cleaned_data.get("generate_tiers"):
            return cleaned_data

        # save_model() only ever generates a ladder `if not change` (creation
        # only) — but generate_tiers/tier_thresholds stay visible in the edit
        # fieldsets too, so without this check an admin editing an existing
        # Achievement could tick generate_tiers, fill in thresholds, pass
        # validation, and get a silent no-op (a "saved successfully" message
        # with no tiers actually created). Reject it explicitly instead.
        if self.instance.pk:
            self.add_error(
                "generate_tiers",
                "Automatyczne generowanie tierów jest dostępne wyłącznie "
                "podczas tworzenia nowego osiągnięcia.",
            )
            return cleaned_data

        raw_thresholds = cleaned_data.get("tier_thresholds") or ""
        try:
            thresholds = parse_tier_thresholds(raw_thresholds)
        except ValueError as exc:
            self.add_error("tier_thresholds", str(exc))
            return cleaned_data

        if not MIN_TIER_THRESHOLDS <= len(thresholds) <= len(TIER_LADDER):
            self.add_error(
                "tier_thresholds",
                f"Podaj od {MIN_TIER_THRESHOLDS} do {len(TIER_LADDER)} progów "
                "rozdzielonych przecinkami — pierwszy to baza (Bronze), "
                "kolejne tworzą pod-tiery.",
            )
        elif thresholds != sorted(thresholds) or len(thresholds) != len(
            set(thresholds),
        ):
            self.add_error(
                "tier_thresholds",
                "Progi muszą rosnąć ściśle od najmniejszego do największego, "
                "bez powtórzeń.",
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

    def get_fieldsets(
        self,
        request: HttpRequest,
        obj: Achievement | None = None,
    ) -> _FieldsetSpec:
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        # icon_content is raw SVG that icon_preview mark_safe's into the admin
        # changelist — keep it superuser-only so non-superuser staff can't
        # inject markup that runs in another admin's session (#335).
        filtered = []
        for name, opts in fieldsets:
            new_opts = dict(opts)
            new_opts["fields"] = tuple(f for f in opts["fields"] if f != "icon_content")
            filtered.append((name, new_opts))
        return cast("_FieldsetSpec", filtered)

    @admin.display(description="Icon")
    def icon_preview(self, obj: Achievement) -> str:
        if obj.icon_content:
            # We wrap the SVG in a div with fixed size for the admin list.
            # mark_safe is deliberate here and on the frontend (#335, #379):
            # icon_content is trusted (data migrations and superusers only —
            # see get_fieldsets above) and the SVG must stay raw to keep
            # currentColor and the inherited styling working.
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
                    # One ladder = base row + N sub-tiers, all or nothing.
                    # The real admin POST already runs inside
                    # ModelAdmin.changeform_view's transaction.atomic(), but a
                    # direct save_model() call (tests, scripts) is not — and a
                    # mid-loop failure would otherwise leave a half-built
                    # ladder behind.
                    with transaction.atomic():
                        # Modify base object to be TIER 1 and have threshold[0]
                        obj.threshold = thresholds[0]
                        obj.tier = Achievement.Tier.BRONZE
                        super().save_model(request, obj, form, change)

                        # Create sub-tiers, using the same TIER_LADDER order
                        # clean() validated tier_thresholds' length against.
                        for idx, t_val in enumerate(thresholds[1:]):
                            tier_idx = idx + 1
                            if tier_idx < len(TIER_LADDER):
                                tier = TIER_LADDER[tier_idx]
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
                                    # Copy *every* language variant, not just
                                    # the admin's active one (#369). The bare
                                    # name/description/theme above are kept so a
                                    # sub-tier's raw (unlocalized) columns match
                                    # the base row the admin form writes —
                                    # modeltranslation's descriptor and its
                                    # queryset both read the localized columns,
                                    # so search_fields does NOT hit these.
                                    **sub_tier_translation_kwargs(obj, tier),
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
