from factory import Faker
from factory import post_generation
from factory.django import DjangoModelFactory

from suchar_overflow.users.models import User


class UserFactory(DjangoModelFactory[User]):
    username = Faker("user_name")
    email = Faker("email")
    name = Faker("name")

    @post_generation
    def password(self: User, create: bool, extracted: str | None, **kwargs):  # noqa: FBT001
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Save again the instance if creating and at least one hook ran."""
        # skip_postgeneration_save is registered dynamically by DjangoOptions
        # via OptionDefault, not a static attribute factory-boy's stubs declare.
        if create and results and not cls._meta.skip_postgeneration_save:  # type: ignore[attr-defined]
            # Some post-generation hooks ran, and may have modified us.
            instance.save()

    class Meta:
        model = User
        django_get_or_create = ["username"]
