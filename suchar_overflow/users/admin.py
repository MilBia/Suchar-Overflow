from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import AuthToken
from .models import EmailChangeRequest
from .models import User

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import ModelForm
    from django.http import HttpRequest


class EmailChangeRequestInline(admin.TabularInline):
    model = EmailChangeRequest
    extra = 0
    readonly_fields = ["old_email", "new_email", "status", "created_at"]
    can_delete = False

    def has_add_permission(
        self,
        _request: HttpRequest,
        _obj: EmailChangeRequest | None = None,
    ) -> bool:
        return False


@admin.register(EmailChangeRequest)
class EmailChangeRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "old_email", "new_email", "status", "created_at"]
    # Explicit changelist join; Django 6.1 would derive the same set from
    # list_display on its own, but declaring it opts out of that fallback
    # (see the note in suchary/admin.py). test_admin_select_related keeps
    # this list equal to what list_display would derive.
    list_select_related = ["user"]
    list_filter = ["status", "created_at"]
    search_fields = ["user__username", "user__email", "new_email"]
    date_hierarchy = "created_at"


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    """Issue API tokens (#459). The clear text is shown once, in a message; only its hash is kept."""

    list_display = ["user", "created"]
    list_select_related = ["user"]
    readonly_fields = ["created"]
    fields = ["user", "created"]
    autocomplete_fields = ["user"]
    search_fields = ["user__username", "user__email"]
    actions = ["regenerate"]

    def get_readonly_fields(self, request: HttpRequest, obj: AuthToken | None = None) -> list[str]:
        # The owner of an existing token is fixed; use the "regenerate" action instead.
        return [*super().get_readonly_fields(request, obj), *(["user"] if obj else [])]

    def save_model(self, request: HttpRequest, obj: AuthToken, form: ModelForm, change: bool) -> None:  # noqa: FBT001
        if change:
            return  # nothing editable: the hash is never shown or replaced here
        raw_token = AuthToken.new_secret()
        obj.token_hash = AuthToken.hash_token(raw_token)
        super().save_model(request, obj, form, change)
        self._announce(request, obj.user, raw_token)

    @admin.action(description=_("Wygeneruj nowy token dla zaznaczonych użytkowników (unieważnia stary)"))
    def regenerate(self, request: HttpRequest, queryset: QuerySet[AuthToken]) -> None:
        for token in queryset.select_related("user"):
            _new, raw_token = AuthToken.issue(token.user)
            self._announce(request, token.user, raw_token)

    def _announce(self, request: HttpRequest, user: User, raw_token: str) -> None:
        self.message_user(
            request,
            _("Token użytkownika %(user)s (widoczny tylko raz): %(token)s")
            % {"user": user.username, "token": raw_token},
            messages.WARNING,
        )


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("name", "email")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    list_display = ["username", "name", "email", "is_superuser", "suchar_count"]
    search_fields = ["name", "username", "email"]
    inlines = [EmailChangeRequestInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[User]:
        queryset = super().get_queryset(request)
        return queryset.annotate(_suchar_count=Count("suchary"))

    @admin.display(description=_("Jokes"), ordering="_suchar_count")
    def suchar_count(self, obj: User) -> int:
        return obj._suchar_count  # type: ignore[attr-defined] # noqa: SLF001
