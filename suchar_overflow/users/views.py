import asyncio
import datetime
import json

from asgiref.sync import sync_to_async
from django.db.models import Count
from django.db.models import Q
from django.db.models.functions import TruncDay
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.models import User

from .forms import EmailChangeForm
from .forms import UserCreationForm
from .models import ActivationToken
from .models import EmailChangeRequest
from .tasks import send_activation_email
from .tasks import send_email_change_emails


class UserDetailView(AsyncLoginRequiredMixin, View):
    template_name = "users/user_detail.html"

    async def get(self, request, username, *args, **kwargs):
        user = await sync_to_async(get_object_or_404)(User, username=username)
        if callable(getattr(request, "auser", None)):
            current_user = await request.auser()
        else:
            current_user = request.user
        context = await self._build_context(user, current_user == user)
        context["object"] = user
        return await sync_to_async(render)(request, self.template_name, context)

    async def _build_context(self, user, is_owner):
        context = {}

        # 1. QuerySets
        latest_suchary_qs = (
            user.suchary.filter(published_at__lte=timezone.now())
            .annotate(
                score=Count("votes"),
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
            .order_by("-created_at")[:5]
        )

        if is_owner:
            scheduled_suchary_qs = user.suchary.filter(
                published_at__gt=timezone.now(),
            ).order_by("published_at")
        else:
            scheduled_suchary_qs = None

        stats_fut = user.suchary.aaggregate(
            total_score=Count("votes"),
            funny_score=Count("votes", filter=Q(votes__is_funny=True)),
            dry_score=Count("votes", filter=Q(votes__is_dry=True)),
            total_count=Count("id", distinct=True),
        )

        best_joke_fut = (
            user.suchary.annotate(score=Count("votes", filter=Q(votes__is_funny=True)))
            .order_by("-score", "-created_at")
            .afirst()
        )

        last_30_days = timezone.now() - datetime.timedelta(days=30)
        activity_data_qs = (
            user.suchary.filter(created_at__gte=last_30_days)
            .annotate(date=TruncDay("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        async def fetch_list(qs):
            return [x async for x in qs]

        tasks = [
            fetch_list(latest_suchary_qs),
            stats_fut,
            best_joke_fut,
            fetch_list(activity_data_qs),
            self._get_heatmap_weeks(user),
        ]
        if is_owner:
            tasks.append(fetch_list(scheduled_suchary_qs))

        results = await asyncio.gather(*tasks)

        latest_suchary = results[0]
        stats = results[1]
        best_joke = results[2]
        activity_data = results[3]
        heatmap_weeks = results[4]
        scheduled_suchary = results[5] if is_owner else []

        context["latest_suchary"] = latest_suchary
        if is_owner:
            context["scheduled_suchary"] = scheduled_suchary

        user.total_score = stats["total_score"] or 0
        context["total_funny_score"] = stats["funny_score"] or 0
        context["total_dry_score"] = stats["dry_score"] or 0
        context["suchar_count"] = stats["total_count"] or 0

        # Global Rank — count users with more funny votes than this user
        higher_ranking_users = await (
            User.objects.annotate(
                score=Count("suchary__votes", filter=Q(suchary__votes__is_funny=True)),
            )
            .filter(score__gt=user.total_score)
            .acount()
        )
        context["global_rank"] = higher_ranking_users + 1
        context["best_joke"] = best_joke

        chart_labels = [entry["date"].strftime("%Y-%m-%d") for entry in activity_data]
        chart_values = [entry["count"] for entry in activity_data]
        context["activity_labels"] = json.dumps(chart_labels)
        context["activity_values"] = json.dumps(chart_values)

        context["reception_data"] = json.dumps(
            [stats["funny_score"] or 0, stats["dry_score"] or 0],
        )

        context["heatmap_weeks"] = heatmap_weeks
        return context

    async def _get_heatmap_weeks(self, user):
        today = timezone.now().date()
        # Go back approx 1 year
        start_date = today - datetime.timedelta(days=365)
        # Align start_date to the previous Monday to ensure the grid starts correctly
        # (Mon-Sun columns) weekday(): Mon=0 ... Sun=6
        days_to_subtract = start_date.weekday()
        start_date -= datetime.timedelta(days=days_to_subtract)

        # Get counts per day
        daily_counts_qs = (
            user.suchary.filter(created_at__date__gte=start_date)
            .annotate(date=TruncDay("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )
        daily_counts = [x async for x in daily_counts_qs]

        # Convert to dictionary for easy lookup
        counts_dict = {entry["date"].date(): entry["count"] for entry in daily_counts}

        heatmap_weeks = []
        current_week_days = []
        current_week_label = None

        current_date = start_date

        # Iterate day by day
        while current_date <= today:
            count = counts_dict.get(current_date, 0)

            # Month Label logic: Check if this week contains the 1st of a month
            # We assign the label to the current week
            if current_date.day == 1:
                # Use short month name.
                current_week_label = date_format(current_date, "b")

            # Determine level 0-4
            if count == 0:
                level = 0
            elif count == 1:
                level = 1
            elif count == 2:  # noqa: PLR2004
                level = 2
            elif count <= 4:  # noqa: PLR2004
                level = 3
            else:
                level = 4

            current_week_days.append(
                {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "count": count,
                    "level": level,
                },
            )

            # If Sunday (weekday 6), close the week
            if current_date.weekday() == 6:  # noqa: PLR2004
                heatmap_weeks.append(
                    {
                        "days": current_week_days,
                        "month_label": current_week_label,
                    },
                )
                current_week_days = []
                current_week_label = None

            current_date += datetime.timedelta(days=1)

        # Add partially filled last week if necessary
        if current_week_days:
            heatmap_weeks.append(
                {
                    "days": current_week_days,
                    "month_label": current_week_label,
                },
            )
        return heatmap_weeks


user_detail_view = UserDetailView.as_view()


class UserUpdateView(AsyncLoginRequiredMixin, View):
    model = User
    fields = ["name"]
    template_name = "users/user_form.html"

    def _form_class(self):
        return modelform_factory(self.model, fields=self.fields)

    async def get(self, request, *args, **kwargs):
        user = await request.auser()
        form = self._form_class()(instance=user)
        return await sync_to_async(render)(
            request,
            self.template_name,
            {"form": form, "object": user},
        )

    async def post(self, request, *args, **kwargs):
        user = await request.auser()
        form = self._form_class()(request.POST, instance=user)
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form, "object": user},
            )
        await sync_to_async(form.save)()
        return redirect(user.get_absolute_url())


user_update_view = UserUpdateView.as_view()


class UserRedirectView(AsyncLoginRequiredMixin, View):
    async def get(self, request, *args, **kwargs):
        user = await request.auser()
        return redirect(
            reverse("users:detail", kwargs={"username": user.username}),
        )


user_redirect_view = UserRedirectView.as_view()


class SignupView(View):
    template_name = "registration/signup.html"

    async def get(self, request, *args, **kwargs):
        form = UserCreationForm()
        return await sync_to_async(render)(request, self.template_name, {"form": form})

    async def post(self, request, *args, **kwargs):
        form = UserCreationForm(request.POST)
        valid = await sync_to_async(form.is_valid)()
        if not valid:
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )

        user = form.save(commit=False)
        user.is_active = False
        await user.asave()

        activation = await ActivationToken.objects.acreate(user=user)
        host = request.get_host()
        protocol = "https" if request.is_secure() else "http"
        await sync_to_async(send_activation_email)(
            user.pk,
            host,
            str(activation.token),
            protocol,
        )
        return redirect(reverse_lazy("users:signup_done"))


signup_view = SignupView.as_view()


class ActivateAccountView(View):
    async def get(self, request, token):
        try:
            activation = await ActivationToken.objects.select_related("user").aget(
                token=token,
            )
        except ActivationToken.DoesNotExist:
            return await sync_to_async(render)(
                request,
                "registration/activation_failed.html",
            )

        if not activation.is_valid():
            await activation.adelete()
            return await sync_to_async(render)(
                request,
                "registration/activation_failed.html",
            )

        user = activation.user
        user.is_active = True
        await user.asave()
        await activation.adelete()
        return await sync_to_async(render)(
            request,
            "registration/activation_complete.html",
        )


activate_view = ActivateAccountView.as_view()


class EmailChangeInitiateView(AsyncLoginRequiredMixin, View):
    template_name = "users/email_change_form.html"

    async def get(self, request, *args, **kwargs):
        form = EmailChangeForm()
        return await sync_to_async(render)(request, self.template_name, {"form": form})

    async def post(self, request, *args, **kwargs):
        form = EmailChangeForm(request.POST)
        valid = await sync_to_async(form.is_valid)()
        if not valid:
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )

        user = await request.auser()
        new_email = form.cleaned_data["email"]
        old_email = user.email

        email_request = await EmailChangeRequest.objects.acreate(
            user=user,
            new_email=new_email,
            old_email=old_email,
        )

        host = request.get_host()
        protocol = "https" if request.is_secure() else "http"
        verify_url = reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_request.verification_token)},
        )
        revoke_url = reverse(
            "users:email_change_revoke",
            kwargs={"token": str(email_request.revocation_token)},
        )
        verify_full = f"{protocol}://{host}{verify_url}"
        revoke_full = f"{protocol}://{host}{revoke_url}"

        await sync_to_async(send_email_change_emails)(
            user.pk,
            old_email,
            new_email,
            verify_full,
            revoke_full,
        )
        return redirect(reverse_lazy("users:email_change_done"))


email_change_initiate_view = EmailChangeInitiateView.as_view()


class EmailChangeDoneView(AsyncLoginRequiredMixin, View):
    async def get(self, request, *args, **kwargs):
        return await sync_to_async(render)(request, "users/email_change_done.html")


email_change_done_view = EmailChangeDoneView.as_view()


class EmailChangeConfirmView(AsyncLoginRequiredMixin, View):
    async def get(self, request, token):
        try:
            email_request = await EmailChangeRequest.objects.select_related(
                "user",
            ).aget(
                verification_token=token,
            )

            if email_request.status != EmailChangeRequest.Status.PENDING:
                return await sync_to_async(render)(
                    request,
                    "users/email_change_failed.html",
                    {"error": _("The link has already been used or cancelled.")},
                )

            if email_request.created_at < timezone.now() - datetime.timedelta(hours=24):
                email_request.status = EmailChangeRequest.Status.REVOKED
                await email_request.asave()
                return await sync_to_async(render)(
                    request,
                    "users/email_change_failed.html",
                    {"error": _("The link has expired (24 hours have passed).")},
                )

            if await User.objects.filter(email=email_request.new_email).aexists():
                return await sync_to_async(render)(
                    request,
                    "users/email_change_failed.html",
                    {"error": _("Email already taken.")},
                )

            user = email_request.user
            user.email = email_request.new_email
            await user.asave()

            email_request.status = EmailChangeRequest.Status.VERIFIED
            await email_request.asave()

            return await sync_to_async(render)(
                request,
                "users/email_change_complete.html",
            )

        except (EmailChangeRequest.DoesNotExist, ValueError):
            return await sync_to_async(render)(
                request,
                "users/email_change_failed.html",
                {"error": _("The link is invalid.")},
            )


email_change_confirm_view = EmailChangeConfirmView.as_view()


class EmailChangeRevokeView(AsyncLoginRequiredMixin, View):
    async def get(self, request, token):
        try:
            email_request = await EmailChangeRequest.objects.select_related(
                "user",
            ).aget(
                revocation_token=token,
            )

            if email_request.status == EmailChangeRequest.Status.VERIFIED:
                user = email_request.user
                if user.email == email_request.new_email:
                    user.email = email_request.old_email or ""
                    await user.asave()
                    email_request.status = EmailChangeRequest.Status.REVOKED
                    await email_request.asave()
                    return await sync_to_async(render)(
                        request,
                        "users/email_change_revoked.html",
                        {"reverted": True},
                    )
                email_request.status = EmailChangeRequest.Status.REVOKED
                await email_request.asave()
                return await sync_to_async(render)(
                    request,
                    "users/email_change_revoked.html",
                    {"reverted": False},
                )

            if email_request.status == EmailChangeRequest.Status.PENDING:
                email_request.status = EmailChangeRequest.Status.REVOKED
                await email_request.asave()
                return await sync_to_async(render)(
                    request,
                    "users/email_change_revoked.html",
                    {"reverted": False},
                )

            return await sync_to_async(render)(
                request,
                "users/email_change_revoked.html",
            )

        except (EmailChangeRequest.DoesNotExist, ValueError):
            return await sync_to_async(render)(
                request,
                "users/email_change_revoked.html",
            )


email_change_revoke_view = EmailChangeRevokeView.as_view()
