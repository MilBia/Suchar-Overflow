import pytest
from django.utils.safestring import SafeString

from suchar_overflow.achievements.admin import AchievementAdmin
from suchar_overflow.achievements.admin import AchievementAdminForm
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
        data = {
            "name": "New Series",
            "slug": "new-series",
            "description": "A new tiered achievement",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
            "generate_tiers": "on",
            "tier_thresholds": "",
        }
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors
        assert not Achievement.objects.filter(slug="new-series").exists()

    def test_generate_tiers_checked_with_non_numeric_thresholds_fails_validation(
        self,
    ) -> None:
        data = {
            "name": "New Series",
            "slug": "new-series-2",
            "description": "A new tiered achievement",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": "1",
            "theme": "",
            "tier": str(Achievement.Tier.NONE),
            "is_secret": False,
            "generate_tiers": "on",
            "tier_thresholds": "not, numbers",
        }
        form = AchievementAdminForm(data=data)

        assert not form.is_valid()
        assert "tier_thresholds" in form.errors

    def test_generate_tiers_checked_with_valid_thresholds_is_valid(self) -> None:
        """Creation with a real threshold list stays unaffected by the fix."""
        data = {
            "name": "New Series",
            "slug": "new-series-3",
            "description": "A new tiered achievement",
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
