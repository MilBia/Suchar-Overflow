import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages.views import SuccessMessageMixin
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import RedirectView
from django.views.generic import UpdateView
from django.views.generic.edit import CreateView

from suchar_overflow.users.models import User

from .forms import EmailChangeForm
from .forms import UserCreationForm
from .models import EmailChangeRequest


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["latest_suchary"] = self.object.suchary.all().order_by("-created_at")[
            :5
        ]
        return context


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:detail", kwargs={"username": self.request.user.username})


user_redirect_view = UserRedirectView.as_view()


class SignupView(CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy("users:signup_done")
    template_name = "registration/signup.html"

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_active = False
        user.save()

        # Send activation email
        current_site = (
            settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "localhost:8000"
        )
        current_site = self.request.get_host()

        mail_subject = "Potwierdź, że masz poczucie humoru (Aktywacja konta)"
        message = render_to_string(
            "registration/activation_email.txt",
            {
                "user": user,
                "domain": current_site,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
                "protocol": "https" if self.request.is_secure() else "http",
            },
        )

        send_mail(mail_subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
        return redirect(self.success_url)


signup_view = SignupView.as_view()


class ActivateAccountView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = get_user_model().objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            return render(request, "registration/activation_complete.html")
        return render(request, "registration/activation_failed.html")


activate_view = ActivateAccountView.as_view()


class EmailChangeInitiateView(LoginRequiredMixin, FormView):
    form_class = EmailChangeForm
    template_name = "users/email_change_form.html"
    success_url = reverse_lazy("users:email_change_done")

    def form_valid(self, form):
        new_email = form.cleaned_data["email"]
        user = self.request.user

        # Create EmailChangeRequest
        email_request = EmailChangeRequest.objects.create(
            user=user,
            new_email=new_email,
            old_email=user.email,
        )

        # Domains
        current_site = self.request.get_host()
        protocol = "https" if self.request.is_secure() else "http"

        # Send Verification Email (New Address)
        verify_url = reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_request.verification_token)},
        )
        verify_link = f"{protocol}://{current_site}{verify_url}"

        mail_subject_new = "Potwierdź, że to Ty (Zmiana maila)"
        message_new = render_to_string(
            "users/email_verify_email.txt",
            {
                "user": user,
                "verify_link": verify_link,
                "new_email": new_email,
            },
        )
        send_mail(
            mail_subject_new,
            message_new,
            settings.DEFAULT_FROM_EMAIL,
            [new_email],
        )

        # Send Notification Email (Old Address) with Revocation Link
        revoke_url = reverse(
            "users:email_change_revoke",
            kwargs={"token": str(email_request.revocation_token)},
        )
        revoke_link = f"{protocol}://{current_site}{revoke_url}"

        mail_subject_old = (
            "Ktoś chce zmienić Twój adres e-mail (Mamy nadzieję, że to Ty)"
        )
        message_old = render_to_string(
            "users/email_notify_old_email.txt",
            {
                "user": user,
                "revoke_link": revoke_link,
                "new_email": new_email,
            },
        )
        send_mail(
            mail_subject_old,
            message_old,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )

        return super().form_valid(form)


email_change_initiate_view = EmailChangeInitiateView.as_view()


class EmailChangeDoneView(LoginRequiredMixin, RedirectView):
    pattern_name = "users:email_change_done"

    def get(self, request, *args, **kwargs):
        return render(request, "users/email_change_done.html")


email_change_done_view = EmailChangeDoneView.as_view()


class EmailChangeConfirmView(LoginRequiredMixin, View):
    def get(self, request, token):
        try:
            email_request = EmailChangeRequest.objects.get(verification_token=token)

            if email_request.status != EmailChangeRequest.Status.PENDING:
                return render(
                    request,
                    "users/email_change_failed.html",
                    {"error": "Link został już wykorzystany lub anulowany."},
                )

            # Check expiry (24h)
            if email_request.created_at < timezone.now() - datetime.timedelta(hours=24):
                email_request.status = EmailChangeRequest.Status.REVOKED  # Expired
                email_request.save()
                return render(
                    request,
                    "users/email_change_failed.html",
                    {"error": "Link wygasł (minęły 24h)."},
                )

            # Verify uniqueness agai
            if User.objects.filter(email=email_request.new_email).exists():
                return render(
                    request,
                    "users/email_change_failed.html",
                    {"error": "Email już zajęty."},
                )

            # Success
            user = email_request.user
            user.email = email_request.new_email
            user.save()

            # Mark as VERIFIED
            email_request.status = EmailChangeRequest.Status.VERIFIED
            email_request.save()

            return render(request, "users/email_change_complete.html")

        except (EmailChangeRequest.DoesNotExist, ValueError):
            return render(
                request,
                "users/email_change_failed.html",
                {"error": "Link jest nieprawidłowy."},
            )


email_change_confirm_view = EmailChangeConfirmView.as_view()


class EmailChangeRevokeView(LoginRequiredMixin, View):
    def get(self, request, token):
        try:
            email_request = EmailChangeRequest.objects.get(revocation_token=token)

            if email_request.status == EmailChangeRequest.Status.VERIFIED:
                # UNDO LOGIC
                user = email_request.user
                # Only undo if the current email is indeed the one we changed it to
                # (prevents undoing a LATER change by an OLDER token)
                if user.email == email_request.new_email:
                    user.email = email_request.old_email
                    user.save()
                    email_request.status = EmailChangeRequest.Status.REVOKED
                    email_request.save()
                    # We might want a different template for "Reverted" vs "Cancelled"
                    return render(
                        request,
                        "users/email_change_revoked.html",
                        {"reverted": True},
                    )
                # Email changed again in the meantime? Just mark revoked.
                email_request.status = EmailChangeRequest.Status.REVOKED
                email_request.save()
                return render(
                    request,
                    "users/email_change_revoked.html",
                    {"reverted": False},
                )

            if email_request.status == EmailChangeRequest.Status.PENDING:
                # Standard cancellation
                email_request.status = EmailChangeRequest.Status.REVOKED
                email_request.save()
                return render(
                    request,
                    "users/email_change_revoked.html",
                    {"reverted": False},
                )

            # Already revoked
            return render(request, "users/email_change_revoked.html")

        except (EmailChangeRequest.DoesNotExist, ValueError):
            return render(request, "users/email_change_revoked.html")


email_change_revoke_view = EmailChangeRevokeView.as_view()
