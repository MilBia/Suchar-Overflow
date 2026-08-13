from django import forms
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = User


class UserCreationForm(admin_forms.UserCreationForm):
    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
        error_messages = {
            "username": {"unique": _("This username has already been taken.")},
        }


class UserAdminChangeForm(UserChangeForm):
    """Alias to UserChangeForm for compatibility."""


class UserAdminCreationForm(UserCreationForm):
    """Alias to UserCreationForm for compatibility."""


class EmailChangeForm(forms.Form):
    email = forms.EmailField(label=_("New Email Address"), required=True)

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("This email is already currently used."))
        return email
