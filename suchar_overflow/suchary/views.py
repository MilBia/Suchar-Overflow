from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.contrib import messages
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.http import Http404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin
from suchar_overflow.users.models import User

from .forms import SucharForm
from .models import Suchar
from .models import Vote

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http import HttpResponse

_PER_PAGE = 10


class SucharListView(View):
    template_name = "suchary/suchar_list.html"

    async def get(self, request: HttpRequest) -> HttpResponse:
        qs = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .filter(published_at__lte=timezone.now())
            .annotate(
                # distinct=True is required, not cosmetic: the `?q=` branch
                # below adds a second multi-valued JOIN (suchar -> tags) that
                # runs *parallel* to this one (suchar -> votes). That JOIN is
                # a LEFT OUTER and its tag predicate is OR'd with the text
                # predicate in WHERE, so a suchar with N tags contributes N
                # duplicated vote rows per vote inside the same GROUP BY --
                # whether the phrase matched its text or one of its tags. A
                # plain COUNT would then report N x the real vote count
                # (#196). The trailing `.distinct()` on the queryset only
                # dedupes the result rows, after these aggregates are
                # already computed.
                funny_count=Count(
                    "votes",
                    filter=Q(votes__is_funny=True),
                    distinct=True,
                ),
                dry_count=Count(
                    "votes",
                    filter=Q(votes__is_dry=True),
                    distinct=True,
                ),
            )
        )

        user = await request.auser()
        if user.is_authenticated:
            qs = qs.annotate(
                user_is_funny=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=user,
                    ).values("is_funny")[:1],
                ),
                user_is_dry=Subquery(
                    Vote.objects.filter(
                        suchar=OuterRef("pk"),
                        user=user,
                    ).values("is_dry")[:1],
                ),
            )

        sort = request.GET.get("sort")
        if sort == "top":
            qs = qs.order_by("-funny_count", "-dry_count", "-created_at")
        else:
            qs = qs.order_by("-created_at")

        q = request.GET.get("q")
        if q:
            qs = qs.filter(Q(text__icontains=q) | Q(tags__name__icontains=q)).distinct()

        tag = request.GET.get("tag")
        if tag:
            qs = qs.filter(tags__slug=tag)

        author = request.GET.get("author")
        if author:
            qs = qs.filter(author__username=author)

        page_number = request.GET.get("page", 1)

        def _paginate_and_render() -> HttpResponse:
            paginator = Paginator(qs, per_page=_PER_PAGE)
            try:
                page = paginator.page(page_number)
            except InvalidPage as exc:
                raise Http404 from exc
            return render(
                request,
                self.template_name,
                {
                    "page_obj": page,
                    "suchary": page.object_list,
                    "paginator": paginator,
                    "is_paginated": page.has_other_pages(),
                },
            )

        return await sync_to_async(_paginate_and_render)()


class SucharCreateView(AsyncLoginRequiredMixin):
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def get(self, request: HttpRequest) -> HttpResponse:
        return await sync_to_async(render)(
            request,
            self.template_name,
            {"form": SucharForm()},
        )

    async def post(self, request: HttpRequest) -> HttpResponse:
        form = SucharForm(request.POST)  # safe: no instance, no DB in __init__
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )

        def _save() -> None:
            suchar = form.save(commit=False)
            # AsyncLoginRequiredMixin already rejects anonymous requests.
            assert isinstance(request.user, User)
            suchar.author = request.user
            suchar.save()
            form.save_m2m()

        await sync_to_async(_save)()
        messages.success(request, gettext("Your suchar has been posted."))
        return redirect(self.success_url)


class SucharUpdateView(AsyncLoginRequiredMixin, AsyncUserPassesTestMixin):  # type: ignore[misc]
    template_name = "suchary/suchar_form.html"
    success_url = reverse_lazy("suchary:list")

    async def _get_suchar(self, pk: int) -> Suchar:
        try:
            return await Suchar.objects.select_related("author").aget(pk=pk)
        except Suchar.DoesNotExist as exc:
            raise Http404 from exc

    async def test_func(self) -> bool:  # type: ignore[override]
        suchar = await self._get_suchar(self.kwargs["pk"])
        return suchar.author == self.request.user

    async def _reject_if_published(
        self,
        request: HttpRequest,
        suchar: Suchar,
    ) -> HttpResponse | None:
        """Return the "too late to edit" response if suchar is published, else None."""
        if suchar.is_published:
            return await sync_to_async(render)(
                request,
                "suchary/edit_too_late.html",
                status=403,
            )
        return None

    async def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        suchar = await self._get_suchar(pk)
        too_late = await self._reject_if_published(request, suchar)
        if too_late is not None:
            return too_late
        # SucharForm.__init__ reads existing tags from DB when given an instance
        form = await sync_to_async(SucharForm)(instance=suchar)
        return await sync_to_async(render)(request, self.template_name, {"form": form})

    async def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        suchar = await self._get_suchar(pk)
        too_late = await self._reject_if_published(request, suchar)
        if too_late is not None:
            return too_late
        # SucharForm.__init__ reads existing tags from DB when given an instance
        form = await sync_to_async(SucharForm)(request.POST, instance=suchar)
        if not await sync_to_async(form.is_valid)():
            return await sync_to_async(render)(
                request,
                self.template_name,
                {"form": form},
            )
        await sync_to_async(form.save)()
        messages.success(request, gettext("Your suchar has been updated."))
        return redirect(self.success_url)
