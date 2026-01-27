from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import EmailChangeRequest
from .models import User


class EmailChangeRequestInline(admin.TabularInline):
    model = EmailChangeRequest
    extra = 0
    readonly_fields = ["old_email", "new_email", "status", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EmailChangeRequest)
class EmailChangeRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "old_email", "new_email", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["user__username", "user__email", "new_email"]
    date_hierarchy = "created_at"


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
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    list_display = ["username", "name", "email", "is_superuser", "suchar_count"]
    search_fields = ["name", "username", "email"]
    inlines = [EmailChangeRequestInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(_suchar_count=Count("suchary"))

    @admin.display(description=_("Jokes"), ordering="_suchar_count")
    def suchar_count(self, obj):
        return obj._suchar_count  # noqa: SLF001
