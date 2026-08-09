import pytest
from django.utils.html import escape
from django.utils.safestring import SafeString

from suchar_overflow.achievements.admin import AchievementAdmin
from suchar_overflow.achievements.models import Achievement


@pytest.mark.django_db
class TestAchievementAdmin:
    def test_icon_preview_with_braces_in_content(self):
        """Test that icon_preview handles SVG with braces without crashing."""
        # Create an Achievement with SVG containing braces
        achievement = Achievement.objects.create(
            name="Test Achievement",
            slug="test-achievement",
            description="A test achievement",
            icon_content='<svg><style>.cls{fill:red}</style></svg>',
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
        assert 'width: 32px; height: 32px;' in result

    def test_icon_preview_with_multiple_braces(self):
        """Test icon_preview with multiple braces in different contexts."""
        achievement = Achievement.objects.create(
            name="Complex SVG",
            slug="complex-svg",
            description="SVG with multiple braces",
            icon_content='<svg><defs><style>{.class1{fill:blue}.class2{stroke:green}}</style></defs></svg>',
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

    def test_icon_preview_without_content(self):
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

    def test_icon_preview_with_normal_svg(self):
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
