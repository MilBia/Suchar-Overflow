from typing import Any
from typing import cast

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client
from django.test import RequestFactory
from django.urls import reverse
from django.utils.safestring import SafeString
from django.utils.translation import override
from modeltranslation.translator import translator

from suchar_overflow.achievements.admin import TIER_LADDER
from suchar_overflow.achievements.admin import TRANSLATED_FIELDS
from suchar_overflow.achievements.admin import AchievementAdmin
from suchar_overflow.achievements.admin import AchievementAdminForm
from suchar_overflow.achievements.admin import parse_tier_thresholds
from suchar_overflow.achievements.admin import sub_tier_translation_kwargs
from suchar_overflow.achievements.models import Achievement


@pytest.mark.django_db
class TestAchievementAdmin:
    def test_icon_preview_with_braces_in_content(self) -> None:
        """Test that icon_preview handles SVG with braces without crashing."""
        # Create an Achievement with SVG containing braces
        achievement = Achievement.objects.create(
            name="Test Achievement",
            slug="test-achievement",
            description="A test achievement",
            icon_content="<svg><style>.cls{fill:red}</style></svg>",
            category="LIFETIME",
            event_type="SUCHAR_POSTED",
            metric="COUNT_SUCHAR",
            threshold=1,
        )

        # Create an AchievementAdmin instance
        admin = AchievementAdmin(Achievement, None)

        # Call icon_preview - should not raise KeyError/IndexError
        result = admin.icon_preview(achievement)

        # Result should be SafeString (safe HTML)
        assert isinstance(result, SafeString)
        # Result should contain the SVG content
        assert ".cls{fill:red}" in result
        # Result should be wrapped in the div
        assert "width: 32px; height: 32px;" in result

    def test_icon_preview_with_multiple_braces(self) -> None:
        """Test icon_preview with multiple braces in different contexts."""
        achievement = Achievement.objects.create(
            name="Complex SVG",
            slug="complex-svg",
            description="SVG with multiple braces",
            icon_content="<svg><defs><style>{.class1{fill:blue}.class2{stroke:green}}</style></defs></svg>",
            category="LIFETIME",
            event_type="SUCHAR_POSTED",
            metric="COUNT_SUCHAR",
            threshold=1,
        )

        admin = AchievementAdmin(Achievement, None)
        result = admin.icon_preview(achievement)

        assert isinstance(result, SafeString)
        assert ".class1{fill:blue}" in result
        assert ".class2{stroke:green}" in result

    def test_icon_preview_without_content(self) -> None:
        """Test that icon_preview returns dash when no icon content."""
        achievement = Achievement.objects.create(
            name="No Icon",
            slug="no-icon",
            description="Achievement with no icon",
            icon_content="",
            category="LIFETIME",
            event_type="SUCHAR_POSTED",
            metric="COUNT_SUCHAR",
            threshold=1,
        )

        admin = AchievementAdmin(Achievement, None)
        result = admin.icon_preview(achievement)

        assert result == "-"

    def test_icon_preview_with_normal_svg(self) -> None:
        """Test that icon_preview works with normal SVG without braces."""
        achievement = Achievement.objects.create(
            name="Simple Icon",
            slug="simple-icon",
            description="Simple SVG icon",
            icon_content='<svg><circle cx="16" cy="16" r="15"/></svg>',
            category="LIFETIME",
            event_type="SUCHAR_POSTED",
            metric="COUNT_SUCHAR",
            threshold=1,
        )

        admin = AchievementAdmin(Achievement, None)
        result = admin.icon_preview(achievement)

        assert isinstance(result, SafeString)
        assert 'cx="16"' in result
        assert 'cy="16"' in result


@pytest.mark.django_db
class TestAchievementAdminForm:
    """Regression coverage for issue #330.

    generate_tiers/tier_thresholds are plain form fields (not model fields),
    so nothing pre-populates them from the instance on GET. Before the fix,
    editing ANY existing Achievement without also filling those two fields
    failed validation, even though save_model only ever consults them when
    creating a brand new Achievement.
    """

    @staticmethod
    def _base_field_data(achievement: Achievement) -> dict[str, str | bool]:
        return {
            "name": achievement.name,
            "slug": achievement.slug,
            "description": achievement.description,
            "icon_content": achievement.icon_content,
            "category": achievement.category,
            "event_type": achievement.event_type,
            "metric": achievement.metric,
            "threshold": str(achievement.threshold),
            "theme": achievement.theme,
            "tier": str(achievement.tier),
            "is_secret": achievement.is_secret,
        }

    @staticmethod
    def _new_achievement_data(
        slug: str,
        **overrides: str | bool,
    ) -> dict[str, str | bool]:
        """Field data for a brand new (unsaved) Achievement submission."""
        data: dict[str, str | bool] = {
            "name": "New Series",
            "slug": slug,
            "description": "A new tiered achievement",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
        }
        data.update(overrides)
        return data

    def test_editing_existing_achievement_without_tier_fields_is_valid(self) -> None:
        """Saving an unrelated edit (e.g. toggling is_secret) must not require
        generate_tiers/tier_thresholds to be filled in.
        """
        achievement = Achievement.objects.create(
            name="Existing Achievement",
            slug="existing-achievement",
            description="An existing achievement being edited",
            icon_content="<svg></svg>",
            category=Achievement.Category.LIFETIME,
            event_type=Achievement.EventType.SUCHAR_POSTED,
            metric=Achievement.Metric.COUNT_SUCHAR,
            threshold=1,
            is_secret=False,
        )

        data = self._base_field_data(achievement)
        data["is_secret"] = True
        # generate_tiers/tier_thresholds intentionally omitted, as a real
        # browser submission of an untouched form section would.
        form = AchievementAdminForm(data=data, instance=achievement)

        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.is_secret is True

    def test_generate_tiers_checked_with_empty_thresholds_fails_validation(
        self,
    ) -> None:
        """The presence/parseability check must not be silently dropped by
        making the fields optional.
        """
        data = self._new_achievement_data(
            "new-series",
            generate_tiers="on",
            tier_thresholds="",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors
        assert not Achievement.objects.filter(slug="new-series").exists()

    def test_generate_tiers_checked_with_non_numeric_thresholds_fails_validation(
        self,
    ) -> None:
        data = self._new_achievement_data(
            "new-series-2",
            generate_tiers="on",
            tier_thresholds="not, numbers",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors

    def test_generate_tiers_checked_with_typo_in_one_token_fails_validation(
        self,
    ) -> None:
        """A single mistyped token (letter O for zero) must be a hard
        validation error, not a silently shorter ladder ('20' dropped).
        """
        data = self._new_achievement_data(
            "new-series-typo",
            generate_tiers="on",
            tier_thresholds="5, 10, 2O, 50",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors
        assert not Achievement.objects.filter(slug="new-series-typo").exists()

    def test_generate_tiers_checked_with_valid_thresholds_is_valid(self) -> None:
        """Creation with a real threshold list stays unaffected by the fix."""
        data = self._new_achievement_data(
            "new-series-3",
            generate_tiers="on",
            tier_thresholds="5,10,25,50,100",
        )
        form = AchievementAdminForm(data=data)

        assert form.is_valid(), form.errors

    def test_generate_tiers_checked_with_single_threshold_fails_validation(
        self,
    ) -> None:
        """A lone threshold sets the base to Bronze but save_model's
        `thresholds[1:]` loop would then create zero sub-tiers — reject it
        instead of silently generating a "ladder" of one rung.
        """
        data = self._new_achievement_data(
            "new-series-single",
            generate_tiers="on",
            tier_thresholds="5",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors

    def test_generate_tiers_checked_with_too_many_thresholds_fails_validation(
        self,
    ) -> None:
        """There are only 5 tiers (Bronze..Diamond) for save_model to use;
        a 6th threshold would silently be ignored by the `tier_idx <
        len(TIER_LADDER)` guard instead of failing loudly.
        """
        data = self._new_achievement_data(
            "new-series-toomany",
            generate_tiers="on",
            tier_thresholds="5,10,15,20,25,30",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors

    def test_generate_tiers_checked_with_descending_thresholds_fails_validation(
        self,
    ) -> None:
        """Descending input would invert the ladder (Bronze=100 harder than
        Diamond=25), which contradicts the AchievementEngine's assumption
        that later tiers are strictly harder.
        """
        data = self._new_achievement_data(
            "new-series-descending",
            generate_tiers="on",
            tier_thresholds="100,50,25",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors

    def test_generate_tiers_checked_with_duplicate_thresholds_fails_validation(
        self,
    ) -> None:
        data = self._new_achievement_data(
            "new-series-duplicate",
            generate_tiers="on",
            tier_thresholds="5,10,10,20",
        )
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors

    def test_editing_existing_achievement_with_generate_tiers_checked_fails(
        self,
    ) -> None:
        """generate_tiers/tier_thresholds stay visible in the edit fieldsets,
        but save_model only ever builds a ladder `if not change`. Without
        this check, checking generate_tiers on an edit would pass validation
        and produce a silent no-op — a "saved successfully" message with no
        tiers actually created.
        """
        achievement = Achievement.objects.create(
            name="Existing Series",
            slug="existing-series",
            description="An existing achievement",
            icon_content="<svg></svg>",
            category=Achievement.Category.LIFETIME,
            event_type=Achievement.EventType.SUCHAR_POSTED,
            metric=Achievement.Metric.COUNT_SUCHAR,
            threshold=1,
        )
        data = self._base_field_data(achievement)
        data["generate_tiers"] = "on"
        data["tier_thresholds"] = "5,10,25,50,100"
        form = AchievementAdminForm(data=data, instance=achievement)

        assert not form.is_valid()
        assert "generate_tiers" in form.errors
        assert not Achievement.objects.filter(
            slug__startswith="existing-series-",
        ).exists()


@pytest.mark.django_db
class TestParseTierThresholds:
    """Direct unit coverage for the shared parsing/validation helper."""

    def test_parses_comma_separated_integers(self) -> None:
        assert parse_tier_thresholds("5,10,25,50,100") == [5, 10, 25, 50, 100]

    def test_strips_whitespace_around_tokens(self) -> None:
        assert parse_tier_thresholds(" 5, 10 , 25 ") == [5, 10, 25]

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Podaj przynajmniej"):
            parse_tier_thresholds("")

    def test_raises_on_blank_string(self) -> None:
        with pytest.raises(ValueError, match="Podaj przynajmniej"):
            parse_tier_thresholds("   ")

    def test_raises_on_non_digit_token(self) -> None:
        with pytest.raises(ValueError, match="2O"):
            parse_tier_thresholds("5,10,2O,50")

    def test_raises_on_empty_token_between_commas(self) -> None:
        with pytest.raises(ValueError, match="pusty fragment"):
            parse_tier_thresholds("5,,10")


@pytest.mark.django_db
class TestAchievementAdminSaveModelTierGeneration:
    """Integration coverage: save_model() actually persists the full ladder
    on creation, not just the individual pieces clean() validates.
    """

    def test_creates_full_tier_ladder_on_creation(self) -> None:
        data: dict[str, Any] = {
            "name": "Ladder Base",
            "slug": "ladder-base",
            "description": "A generated tier ladder",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
            "generate_tiers": "on",
            "tier_thresholds": "5,10,25,50,100",
        }
        form = AchievementAdminForm(data=data)
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)

        admin_instance = AchievementAdmin(Achievement, None)
        request = RequestFactory().post("/")
        admin_instance.save_model(request, obj, form, change=False)

        created = Achievement.objects.filter(slug__startswith="ladder-base").order_by(
            "threshold",
        )
        assert list(created.values_list("threshold", "tier")) == [
            (5, TIER_LADDER[0]),
            (10, TIER_LADDER[1]),
            (25, TIER_LADDER[2]),
            (50, TIER_LADDER[3]),
            (100, TIER_LADDER[4]),
        ]
        assert created.count() == len(TIER_LADDER)


class TestAchievementAdminIconContentPermission:
    """#335: ``icon_preview`` renders raw ``icon_content`` SVG through
    ``mark_safe`` into the admin changelist, so only superusers may edit the
    field — a non-superuser staffer must not be able to inject markup that
    runs in another admin's session.

    #379: this class is also the guard for the frontend. ``icon_content`` is
    rendered unescaped with ``|safe`` in ``achievements/_card.html``,
    ``base.html`` and ``users/user_detail.html`` (twice), and injected with
    ``innerHTML`` by ``project.js`` — all of which are deliberate, and all of
    which rest on exactly the assumption asserted below: the field is never
    offered in a non-superuser's admin form. Sanitizing instead was rejected
    because it breaks ``currentColor`` and style inheritance in the icons. If
    these assertions ever have to change, revisit those four render sites first.
    """

    @staticmethod
    def _fieldset_fields(*, is_superuser: bool) -> set[str]:
        admin_instance = AchievementAdmin(Achievement, None)
        request = RequestFactory().get("/")
        request.user = get_user_model()(is_staff=True, is_superuser=is_superuser)
        fields: set[str] = set()
        for _label, opts in admin_instance.get_fieldsets(request):
            fields.update(cast("tuple[str, ...]", opts["fields"]))
        return fields

    def test_superuser_fieldsets_include_icon_content(self) -> None:
        assert "icon_content" in self._fieldset_fields(is_superuser=True)

    def test_non_superuser_fieldsets_exclude_icon_content(self) -> None:
        assert "icon_content" not in self._fieldset_fields(is_superuser=False)


def _make_translated_base(base: Achievement, values: dict[str, str]) -> None:
    """Set localized field variants by dynamic name.

    ``setattr`` with a runtime name keeps mypy (django-stubs has no view of
    modeltranslation's dynamically added ``name_en`` & co.) and ruff quiet,
    while still going through the real modeltranslation descriptors.
    """
    for field_name, value in values.items():
        setattr(base, field_name, value)


def _pl_tier_label(tier: Achievement.Tier) -> str:
    """The Polish tier label as the code under test resolves it.

    Can't be a hard-coded literal: CI runs without compiled ``.mo`` files
    (issue #242), so ``override("pl")`` may yield the English msgid instead
    of the translation. Tests still pin the surrounding text exactly.
    """
    with override("pl"):
        return str(tier.label)


@pytest.mark.django_db
class TestSubTierTranslationCopy:
    """#369: generated sub-tiers must copy *every* configured language
    variant of the translated fields (name/description/theme), not only the
    admin's currently active language.

    Before the fix, ``save_model`` built sub-tiers with
    ``Achievement.objects.create(name=obj.name, ...)``. modeltranslation
    (with ``MODELTRANSLATION_AUTO_POPULATE`` off) rewrites those bare kwargs
    into the *default* language column only, so the non-default variants an
    admin typed into the modeltranslation tabs (``name_en`` & co.) were
    silently dropped from every generated sub-tier and stayed ``None`` —
    English admins then saw the Polish text via ``MODELTRANSLATION_FALLBACK``.
    """

    @staticmethod
    def _create_ladder_with_both_languages() -> None:
        data: dict[str, Any] = {
            "name": "Ladder Base",
            "slug": "ladder-base",
            "description": "A generated tier ladder",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
            "generate_tiers": "on",
            # base -> Bronze/5, then Silver/10 + Gold/25 as generated sub-tiers.
            "tier_thresholds": "5,10,25",
        }
        form = AchievementAdminForm(data=data)
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)
        # Simulate the admin filling in both modeltranslation tabs.
        _make_translated_base(
            obj,
            {
                "name_pl": "Baza PL",
                "name_en": "Base EN",
                "description_pl": "Opis PL",
                "description_en": "Description EN",
                "theme_pl": "MotywPL",
                "theme_en": "ThemeEN",
            },
        )

        AchievementAdmin(Achievement, None).save_model(
            RequestFactory().post("/"),
            obj,
            form,
            change=False,
        )

    @staticmethod
    def _localized(slug: str) -> dict[str, Any]:
        """Raw localized columns of a reloaded row (bypasses the descriptor)."""
        return cast(
            "dict[str, Any]",
            Achievement.objects.filter(slug=slug)
            .values(
                "name_pl",
                "name_en",
                "description_pl",
                "description_en",
                "theme_pl",
                "theme_en",
            )
            .get(),
        )

    def test_sub_tiers_carry_every_language_variant(self) -> None:
        self._create_ladder_with_both_languages()

        silver = self._localized("ladder-base-silver")
        gold = self._localized("ladder-base-gold")

        # The English tier label *is* the msgid, so it resolves the same with
        # or without compiled catalogs — assert it exactly, on both sub-tiers.
        assert silver["name_en"] == "Base EN (Silver)"
        assert gold["name_en"] == "Base EN (Gold)"
        for row in (silver, gold):
            assert row["description_en"] == "Description EN"
            assert row["theme_en"] == "ThemeEN"

        # The Polish label token is catalog-dependent and CI runs without
        # compiled .mo files (issue #242), so pin the prefix + the label
        # resolved the same way, and separately prove each sub-tier carries
        # *its own* tier's label rather than a shared/wrong one.
        pl_silver_label = _pl_tier_label(Achievement.Tier.SILVER)
        pl_gold_label = _pl_tier_label(Achievement.Tier.GOLD)
        assert pl_silver_label != pl_gold_label
        assert silver["name_pl"] == f"Baza PL ({pl_silver_label})"
        assert gold["name_pl"] == f"Baza PL ({pl_gold_label})"
        for row in (silver, gold):
            assert row["description_pl"] == "Opis PL"
            assert row["theme_pl"] == "MotywPL"

    def test_english_admin_reads_english_through_the_descriptor(self) -> None:
        """End-to-end: an EN-active reader gets the English text, not the
        Polish fallback.
        """
        self._create_ladder_with_both_languages()
        silver = Achievement.objects.get(slug="ladder-base-silver")

        with override("en"):
            assert silver.name == "Base EN (Silver)"
            assert silver.description == "Description EN"
        with override("pl"):
            assert silver.name == f"Baza PL ({_pl_tier_label(Achievement.Tier.SILVER)})"

    def test_ladder_creation_is_symmetric_under_an_english_admin_session(
        self,
    ) -> None:
        """The Polish default session is not special — building the ladder
        with EN active must copy both variants identically.
        """
        with override("en"):
            self._create_ladder_with_both_languages()

        silver = self._localized("ladder-base-silver")
        assert silver["name_en"] == "Base EN (Silver)"
        assert silver["description_en"] == "Description EN"
        assert (
            silver["name_pl"] == f"Baza PL ({_pl_tier_label(Achievement.Tier.SILVER)})"
        )
        assert silver["description_pl"] == "Opis PL"

    def test_base_row_untouched_language_stays_empty_on_sub_tiers(self) -> None:
        """An admin who never opened the EN tab must not get half-English
        sub-tiers — an unfilled base variant stays unfilled downstream.
        """
        data: dict[str, Any] = {
            "name": "Only PL",
            "slug": "only-pl",
            "description": "polish only",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
            "generate_tiers": "on",
            "tier_thresholds": "5,10",
        }
        form = AchievementAdminForm(data=data)
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)
        # LANGUAGE_CODE is "pl" in tests, so form.save set name_pl only.
        AchievementAdmin(Achievement, None).save_model(
            RequestFactory().post("/"),
            obj,
            form,
            change=False,
        )

        silver = self._localized("only-pl-silver")
        assert not silver["name_en"]
        assert not silver["description_en"]
        assert (
            silver["name_pl"] == f"Only PL ({_pl_tier_label(Achievement.Tier.SILVER)})"
        )

    def test_helper_builds_localized_kwargs_for_all_languages(self) -> None:
        base = Achievement()
        _make_translated_base(
            base,
            {
                "name_pl": "Baza PL",
                "name_en": "Base EN",
                "description_pl": "Opis",
                "description_en": "Desc",
                "theme_pl": "Mpl",
                "theme_en": "Men",
            },
        )

        kwargs = sub_tier_translation_kwargs(base, Achievement.Tier.SILVER)

        assert kwargs == {
            "name_pl": f"Baza PL ({_pl_tier_label(Achievement.Tier.SILVER)})",
            "name_en": "Base EN (Silver)",
            "description_pl": "Opis",
            "description_en": "Desc",
            "theme_pl": "Mpl",
            "theme_en": "Men",
        }

    def test_helper_leaves_unfilled_variant_none(self) -> None:
        base = Achievement()
        _make_translated_base(base, {"name_pl": "Baza PL"})

        kwargs = sub_tier_translation_kwargs(base, Achievement.Tier.SILVER)

        assert kwargs == {
            "name_pl": f"Baza PL ({_pl_tier_label(Achievement.Tier.SILVER)})",
            "name_en": None,
            "description_pl": None,
            "description_en": None,
            "theme_pl": None,
            "theme_en": None,
        }

    def test_translated_fields_match_translation_options(self) -> None:
        """Guard against ``TRANSLATED_FIELDS`` drifting from the real
        ``AchievementTranslationOptions.fields`` (translation.py).
        """
        opts = translator.get_options_for_model(Achievement)
        assert set(TRANSLATED_FIELDS) == set(opts.fields)  # type: ignore[attr-defined]

    def test_admin_add_view_end_to_end_copies_en_variant(
        self,
        admin_client: Client,
    ) -> None:
        """Drive the real admin add view: ``TabbedTranslationAdmin`` swaps the
        ``name``/``description``/``theme`` form fields for ``*_pl``/``*_en``,
        so a POST that fills the EN tab must reach the generated sub-tiers.
        """
        response = admin_client.post(
            reverse("admin:achievements_achievement_add"),
            data={
                "name_pl": "Baza PL",
                "name_en": "Base EN",
                "slug": "ladder-base",
                "description_pl": "Opis PL",
                "description_en": "Description EN",
                "icon_content": "<svg></svg>",
                "category": Achievement.Category.LIFETIME,
                "event_type": Achievement.EventType.SUCHAR_POSTED,
                "metric": Achievement.Metric.COUNT_SUCHAR,
                "threshold": "1",
                "theme_pl": "MotywPL",
                "theme_en": "ThemeEN",
                "tier": str(Achievement.Tier.NONE),
                "generate_tiers": "on",
                "tier_thresholds": "5,10,25",
            },
        )
        if response.status_code != 302:  # noqa: PLR2004
            pytest.fail(response.context["adminform"].form.errors.as_text())

        silver = self._localized("ladder-base-silver")
        assert silver["name_en"] == "Base EN (Silver)"
        assert silver["description_en"] == "Description EN"
        assert silver["theme_en"] == "ThemeEN"
        assert (
            silver["name_pl"] == f"Baza PL ({_pl_tier_label(Achievement.Tier.SILVER)})"
        )
        assert silver["theme_pl"] == "MotywPL"

    def test_ladder_generation_rolls_back_the_base_row_on_a_sub_tier_failure(
        self,
    ) -> None:
        """A mid-loop failure must not leave a half-built ladder — the base
        row and any earlier sub-tiers roll back with it.
        """
        # A pre-existing row on a sub-tier slug makes the Gold create() raise
        # IntegrityError partway through the loop.
        Achievement.objects.create(
            slug="clash-gold",
            icon_content="<svg></svg>",
            category=Achievement.Category.LIFETIME,
            event_type=Achievement.EventType.SUCHAR_POSTED,
            metric=Achievement.Metric.COUNT_SUCHAR,
            threshold=1,
        )
        data: dict[str, Any] = {
            "name": "Clash",
            "slug": "clash",
            "description": "d",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
            "generate_tiers": "on",
            "tier_thresholds": "5,10,25",
        }
        form = AchievementAdminForm(data=data)
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)

        with pytest.raises(IntegrityError):
            AchievementAdmin(Achievement, None).save_model(
                RequestFactory().post("/"),
                obj,
                form,
                change=False,
            )

        assert not Achievement.objects.filter(slug="clash").exists()
        assert not Achievement.objects.filter(slug="clash-silver").exists()
