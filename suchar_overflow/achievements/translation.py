from modeltranslation.translator import TranslationOptions
from modeltranslation.translator import register

from .models import Achievement


@register(Achievement)
class AchievementTranslationOptions(TranslationOptions):
    fields = ("name", "description", "theme")
